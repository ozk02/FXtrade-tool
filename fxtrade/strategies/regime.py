"""ADXレジームフィルター戦略。

「相場に合わない手法を止める」ための仕組み。ADX（トレンドの強さ）を見て、

    ADX >= threshold → トレンド相場   → 順張り戦略(既定: ma_cross)に任せる
    ADX <  threshold → レンジ相場     → 逆張り戦略(既定: price_percent)に任せる

単体の戦略を強くするより、環境に合わせて使い分けるほうが効果が出やすい。

実装上の要点:
  * 建玉を持っている間は担当を切り替えない。エントリした戦略が最後まで面倒を見る。
    （途中で担当が替わると、相手の戦略が「知らない建玉」を扱うことになるため）
  * 担当外の戦略にも毎足データを渡して指標を温めておく（移動平均に穴を空けない）。
    ただしその際はノーポジとして渡し、返ってきたシグナルは捨てる。
  * ADXが確定するまで（およそ period*2 本）は warmup_hold=True なら売買しない。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from ..indicators import ADX
from ..models import Candle, Position
from .base import Signal, SignalType, Strategy


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _as_strategy(spec, default_name: str) -> Strategy:
    """設定(dict/str/インスタンス)から戦略を作る。"""
    if isinstance(spec, Strategy):
        return spec
    from . import build_strategy  # 循環importを避けるため遅延import

    if spec is None:
        return build_strategy(default_name, {})
    if isinstance(spec, str):
        return build_strategy(spec, {})
    return build_strategy(spec.get("name", default_name), spec.get("params", {}))


class RegimeFilterStrategy(Strategy):
    name = "regime"

    def __init__(
        self,
        trend=None,
        ranging=None,
        adx_period: int = 14,
        adx_threshold: float = 25.0,
        warmup_hold: bool = True,
    ):
        self.trend = _as_strategy(trend, "ma_cross")
        self.ranging = _as_strategy(ranging, "price_percent")
        self.adx_period = int(adx_period)
        self.adx_threshold = _dec(adx_threshold)
        self.warmup_hold = bool(warmup_hold)
        self.reset()

    def reset(self) -> None:
        self.trend.reset()
        self.ranging.reset()
        self._adx = ADX(self.adx_period)
        self._owner: Optional[Strategy] = None   # 建玉を持っている側
        self._active: Strategy = self.ranging
        self.regime = "warmup"
        self.adx_value: Optional[Decimal] = None

    @property
    def stop_loss_pct(self) -> Decimal:
        """エンジンのロット計算用。いま担当している戦略の損切り幅を返す。"""
        active = self._owner or self._active
        return _dec(getattr(active, "stop_loss_pct", Decimal("1.0")))

    # ------------------------------------------------------------------
    def on_candle(self, candle: Candle, position: Optional[Position]) -> Signal:
        adx = self._adx.update(candle.high, candle.low, candle.close)
        self.adx_value = adx

        if adx is None:
            self.regime = "warmup"
            trend_on = False
        else:
            trend_on = adx >= self.adx_threshold
            self.regime = "trend" if trend_on else "range"

        # 建玉が無いなら担当は解除。あるなら建てた戦略に任せ続ける。
        if position is None:
            self._owner = None
        active = self._owner if self._owner is not None else (self.trend if trend_on else self.ranging)
        self._active = active

        # 両方に足を渡して指標を温める。担当外にはノーポジとして渡し、結果は捨てる。
        active_signal = Signal.hold()
        for strategy in (self.trend, self.ranging):
            sig = strategy.on_candle(candle, position if strategy is active else None)
            if strategy is active:
                active_signal = sig

        # ADX未確定のうちは新規建てしない（既存建玉の決済は通す）。
        if self.warmup_hold and adx is None and position is None:
            return Signal.hold()

        if active_signal.type is SignalType.ENTER:
            self._owner = active
        elif active_signal.type is SignalType.EXIT:
            self._owner = None

        return active_signal

    # ------------------------------------------------------------------
    def status(self) -> str:
        """UI/ログ表示用の現在状態。"""
        adx = "-" if self.adx_value is None else f"{self.adx_value:.1f}"
        who = getattr(self._active, "name", "-")
        return f"ADX={adx} regime={self.regime} active={who}"
