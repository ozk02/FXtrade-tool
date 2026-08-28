"""移動平均クロス戦略（順張り / トレンドフォロー）。

考え方:
  * 短期移動平均が長期移動平均を上抜け（ゴールデンクロス）→ 買い
  * 下抜け（デッドクロス）→ 売り（allow_short=False なら手仕舞いのみ）
  * 反対方向のクロスが出たら手仕舞い（そのまま次の足でドテン）
  * 補助的に ％損切り・％利確・トレーリングも掛けられる

順張りは「勝率は低いが、当たったときに大きく取る」タイプ。レンジ相場では
細かい損切りが続くので、ADXレジームフィルター(RegimeFilterStrategy)と
組み合わせると噛み合いやすい。

クロスは「その足だけのイベント」なので、検出したら _pending に方向を記憶し、
ノーポジになった次の足でエントリする。これによりドテンが自然に成立する。
損切り/利確で降りた場合は _pending を消し、次のクロスまで待つ。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from ..indicators import make_ma
from ..models import Candle, Position, Side
from .base import Signal, Strategy


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


class MACrossStrategy(Strategy):
    name = "ma_cross"

    def __init__(
        self,
        fast_period: int = 20,
        slow_period: int = 50,
        ma_type: str = "ema",
        allow_short: bool = True,
        stop_loss_pct: float = 1.0,     # 0 で無効（ロット計算には既定値が使われる）
        take_profit_pct: float = 0.0,   # 0 で無効（クロスまで持つ）
        trailing_enabled: bool = False,
        trailing_pct: float = 1.0,
        trailing_activate_pct: float = 0.0,
    ):
        if fast_period < 1 or slow_period < 1:
            raise ValueError("periods must be >= 1")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        if trailing_enabled and trailing_pct <= 0:
            raise ValueError("trailing requires trailing_pct > 0")

        self.fast_period = int(fast_period)
        self.slow_period = int(slow_period)
        self.ma_type = (ma_type or "ema").lower()
        self.allow_short = bool(allow_short)
        self.stop_loss_pct = _dec(stop_loss_pct)
        self.take_profit_pct = _dec(take_profit_pct)
        self.trailing_enabled = bool(trailing_enabled)
        self.trailing_pct = _dec(trailing_pct)
        self.trailing_activate_pct = _dec(trailing_activate_pct)

        self.reset()

    def reset(self) -> None:
        self._fast = make_ma(self.ma_type, self.fast_period)
        self._slow = make_ma(self.ma_type, self.slow_period)
        self._prev_diff: Optional[Decimal] = None
        self._pending: Optional[Side] = None
        self._trail_best: Optional[Decimal] = None
        self._trail_active = False

    # ------------------------------------------------------------------
    def on_candle(self, candle: Candle, position: Optional[Position]) -> Signal:
        price = candle.close
        fast = self._fast.update(price)
        slow = self._slow.update(price)

        crossed_up = crossed_down = False
        if fast is not None and slow is not None:
            diff = fast - slow
            if self._prev_diff is not None:
                crossed_up = self._prev_diff <= 0 and diff > 0
                crossed_down = self._prev_diff >= 0 and diff < 0
            self._prev_diff = diff

        # クロスを検出したら次のエントリ方向として記憶する。
        if crossed_up:
            self._pending = Side.BUY
        elif crossed_down:
            self._pending = Side.SELL if self.allow_short else None

        if position is not None:
            return self._on_position(price, position, crossed_up, crossed_down)

        # ノーポジ: トレーリング状態をリセットし、記憶した方向でエントリ。
        self._trail_best = None
        self._trail_active = False
        if self._pending is not None:
            side = self._pending
            self._pending = None
            kind = "golden cross" if side is Side.BUY else "dead cross"
            return Signal.enter(side, reason=f"{kind} ({self.ma_type}{self.fast_period}/{self.slow_period})")
        return Signal.hold()

    # ------------------------------------------------------------------
    def _on_position(self, price: Decimal, position: Position, crossed_up: bool, crossed_down: bool) -> Signal:
        sign = position.side.sign
        move_pct = (price - position.entry_price) / position.entry_price * sign * Decimal("100")

        # 1) 損切り（最優先）。降りたら次のクロスまで待つ。
        if self.stop_loss_pct > 0 and move_pct <= -self.stop_loss_pct:
            self._pending = None
            return Signal.exit(reason=f"stop loss {move_pct:.3f}% <= -{self.stop_loss_pct}%")

        # 2) トレーリング
        if self.trailing_enabled:
            if self._trail_best is None or move_pct > self._trail_best:
                self._trail_best = move_pct
            if not self._trail_active and move_pct >= self.trailing_activate_pct:
                self._trail_active = True
            if self._trail_active and (self._trail_best - move_pct) >= self.trailing_pct:
                self._pending = None
                return Signal.exit(
                    reason=f"trailing stop: retraced {(self._trail_best - move_pct):.3f}% from +{self._trail_best:.3f}%"
                )

        # 3) 利確（0 なら無効＝クロスまで持つ）
        if self.take_profit_pct > 0 and move_pct >= self.take_profit_pct:
            self._pending = None
            return Signal.exit(reason=f"take profit {move_pct:.3f}% >= {self.take_profit_pct}%")

        # 4) 反対方向のクロスで手仕舞い（次の足でドテン）
        if (position.side is Side.BUY and crossed_down) or (position.side is Side.SELL and crossed_up):
            return Signal.exit(reason="opposite cross")

        return Signal.hold()
