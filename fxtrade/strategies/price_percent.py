"""価格と％で売買する戦略（ナンピン・トレーリングストップ対応）。

基本ロジック:
  * 参照価格（anchor）から entry_drop_pct だけ不利方向に動いたらエントリ。
    direction="long" は押し目買い、"short" は戻り売り。
  * 含み益が take_profit_pct に達したら利確、含み損が stop_loss_pct で損切り。

ナンピン（増し玉）:
  * nanpin_enabled=True のとき、最初のエントリ価格から
    nanpin_step_pct ずつ不利方向に進むたびに同方向へ積み増す（最大 max_nanpin 回）。
  * nanpin_size_mult で増し玉ごとのロット倍率を指定（>1 でマーチンゲール的）。
  * 利確・損切り・トレーリングは「平均建値」に対して判定する。

トレーリングストップ:
  * trailing_enabled=True のとき、建玉中の最有利値（ロングなら最高値）を記録し、
    そこから trailing_pct だけ戻したら手仕舞いする。
  * trailing_activate_pct を指定すると、含み益がそこに達してからトレーリングを有効化する。

判定の優先順位（1本の足で実行するのは1アクション）:
  損切り → トレーリング → 利確 → ナンピン
  （安全側: 先に損切りが効くため、stop_loss_pct < nanpin_step_pct だとナンピンしない）
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from ..models import Candle, Position, Side
from .base import Signal, Strategy


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


class PricePercentStrategy(Strategy):
    name = "price_percent"

    def __init__(
        self,
        entry_drop_pct: float = 0.5,
        take_profit_pct: float = 1.0,
        stop_loss_pct: float = 0.5,
        direction: str = "long",
        anchor_price: Optional[float] = None,
        trail_anchor: bool = True,
        # --- ナンピン ---
        nanpin_enabled: bool = False,
        nanpin_step_pct: float = 0.5,
        max_nanpin: int = 3,
        nanpin_size_mult: float = 1.0,
        # --- トレーリングストップ ---
        trailing_enabled: bool = False,
        trailing_pct: float = 0.5,
        trailing_activate_pct: float = 0.0,
    ):
        if direction not in ("long", "short"):
            raise ValueError("direction must be 'long' or 'short'")
        if entry_drop_pct <= 0 or take_profit_pct <= 0 or stop_loss_pct <= 0:
            raise ValueError("percentage parameters must be positive")
        if nanpin_enabled and (nanpin_step_pct <= 0 or max_nanpin < 1):
            raise ValueError("nanpin requires nanpin_step_pct > 0 and max_nanpin >= 1")
        if trailing_enabled and trailing_pct <= 0:
            raise ValueError("trailing requires trailing_pct > 0")

        self.entry_drop_pct = _dec(entry_drop_pct)
        self.take_profit_pct = _dec(take_profit_pct)
        self.stop_loss_pct = _dec(stop_loss_pct)
        self.direction = direction
        self.side = Side.BUY if direction == "long" else Side.SELL
        self._initial_anchor = _dec(anchor_price) if anchor_price is not None else None
        self.trail_anchor = trail_anchor

        self.nanpin_enabled = nanpin_enabled
        self.nanpin_step_pct = _dec(nanpin_step_pct)
        self.max_nanpin = int(max_nanpin)
        self.nanpin_size_mult = _dec(nanpin_size_mult)

        self.trailing_enabled = trailing_enabled
        self.trailing_pct = _dec(trailing_pct)
        self.trailing_activate_pct = _dec(trailing_activate_pct)

        self.reset()

    def reset(self) -> None:
        self.anchor: Optional[Decimal] = self._initial_anchor
        # ポジション状態の追跡（ブローカーの position から再構成する）。
        self._entry0: Optional[Decimal] = None  # 初回エントリ価格（ナンピン基準）
        self._add_count: int = 0
        self._prev_units: Decimal = Decimal("0")
        self._trail_best: Optional[Decimal] = None
        self._trailing_active: bool = False

    # ------------------------------------------------------------------
    def on_candle(self, candle: Candle, position: Optional[Position]) -> Signal:
        price = candle.close

        if position is None:
            return self._on_flat(price)
        return self._on_position(price, position)

    # ------------------------------------------------------------------
    def _on_flat(self, price: Decimal) -> Signal:
        # ノーポジになったので建玉追跡をリセット。
        self._entry0 = None
        self._add_count = 0
        self._prev_units = Decimal("0")
        self._trail_best = None
        self._trailing_active = False

        if self.anchor is None:
            self.anchor = price

        if self.trail_anchor:
            # ロングは「より高い値」、ショートは「より低い値」を anchor に追従させる。
            if self.side is Side.BUY:
                self.anchor = max(self.anchor, price)
            else:
                self.anchor = min(self.anchor, price)

        change_pct = (price - self.anchor) / self.anchor * Decimal("100")

        if self.side is Side.BUY and change_pct <= -self.entry_drop_pct:
            self.anchor = None
            return Signal.enter(Side.BUY, reason=f"price dropped {change_pct:.3f}% from anchor")
        if self.side is Side.SELL and change_pct >= self.entry_drop_pct:
            self.anchor = None
            return Signal.enter(Side.SELL, reason=f"price rose {change_pct:.3f}% from anchor")

        return Signal.hold()

    # ------------------------------------------------------------------
    def _on_position(self, price: Decimal, position: Position) -> Signal:
        # 約定によりロットが増えていれば、初回建値や増し玉回数を更新する。
        if position.units > self._prev_units:
            if self._entry0 is None:
                # 初回エントリ。建値はそのまま position.entry_price。
                self._entry0 = position.entry_price
                self._trail_best = price
            elif self._prev_units > 0:
                # 増し玉が約定した。
                self._add_count += 1
        self._prev_units = position.units

        sign = position.side.sign
        # 平均建値ベースの損益率(%)。
        move_pct = (price - position.entry_price) / position.entry_price * sign * Decimal("100")

        # 1) 損切り（最優先・安全側）
        if move_pct <= -self.stop_loss_pct:
            return Signal.exit(reason=f"stop loss {move_pct:.3f}% <= -{self.stop_loss_pct}%")

        # 2) トレーリングストップ
        if self.trailing_enabled:
            # 最有利値を更新。
            if self._trail_best is None:
                self._trail_best = price
            if position.side is Side.BUY:
                self._trail_best = max(self._trail_best, price)
            else:
                self._trail_best = min(self._trail_best, price)

            # 含み益が activate に達したら有効化（0 なら常時）。
            if not self._trailing_active and move_pct >= self.trailing_activate_pct:
                self._trailing_active = True

            if self._trailing_active:
                retrace_pct = (self._trail_best - price) / self._trail_best * sign * Decimal("100")
                if retrace_pct >= self.trailing_pct:
                    return Signal.exit(
                        reason=f"trailing stop: retraced {retrace_pct:.3f}% from {self._trail_best}"
                    )

        # 3) 利確
        if move_pct >= self.take_profit_pct:
            return Signal.exit(reason=f"take profit {move_pct:.3f}% >= {self.take_profit_pct}%")

        # 4) ナンピン（増し玉）
        if self.nanpin_enabled and self._add_count < self.max_nanpin and self._entry0:
            # 次の増し玉発動価格 = 初回建値から step_pct*(回数+1) だけ不利方向。
            step = self.nanpin_step_pct * (self._add_count + 1)
            move_from_entry0 = (price - self._entry0) / self._entry0 * sign * Decimal("100")
            if move_from_entry0 <= -step:
                return Signal.add(
                    position.side,
                    reason=f"nanpin #{self._add_count + 1}: {move_from_entry0:.3f}% from entry",
                    size_mult=self.nanpin_size_mult ** self._add_count,
                )

        return Signal.hold()
