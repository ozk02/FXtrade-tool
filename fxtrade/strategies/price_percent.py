"""価格と％で売買する戦略。

考え方:
  * 参照価格（anchor）から一定 % 下落したらロングでエントリ（押し目買い）。
    direction="short" の場合は一定 % 上昇でショートエントリ（戻り売り）。
  * エントリ後、含み益が take_profit_pct に達したら利確。
  * 含み損が stop_loss_pct に達したら損切り。
  * anchor を固定値で指定することも、未指定なら最初に見た価格を anchor にすることも可能。
    trail_anchor=True にすると、ノーポジ時に anchor を「より有利な価格」へ追従させ、
    上下どちらに動いても押し目/戻りを拾えるようにする。

すべて % ベースなので「価格と％で売買する」という要件をそのまま表現している。
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
    ):
        if direction not in ("long", "short"):
            raise ValueError("direction must be 'long' or 'short'")
        if entry_drop_pct <= 0 or take_profit_pct <= 0 or stop_loss_pct <= 0:
            raise ValueError("percentage parameters must be positive")

        self.entry_drop_pct = _dec(entry_drop_pct)
        self.take_profit_pct = _dec(take_profit_pct)
        self.stop_loss_pct = _dec(stop_loss_pct)
        self.direction = direction
        self.side = Side.BUY if direction == "long" else Side.SELL
        self._initial_anchor = _dec(anchor_price) if anchor_price is not None else None
        self.trail_anchor = trail_anchor
        self.anchor: Optional[Decimal] = self._initial_anchor

    def reset(self) -> None:
        self.anchor = self._initial_anchor

    def on_candle(self, candle: Candle, position: Optional[Position]) -> Signal:
        price = candle.close

        # ポジション保有中: 利確 / 損切り判定。
        if position is not None:
            move_pct = (price - position.entry_price) / position.entry_price * position.side.sign * Decimal("100")
            if move_pct >= self.take_profit_pct:
                return Signal.exit(reason=f"take profit {move_pct:.3f}% >= {self.take_profit_pct}%")
            if move_pct <= -self.stop_loss_pct:
                return Signal.exit(reason=f"stop loss {move_pct:.3f}% <= -{self.stop_loss_pct}%")
            return Signal.hold()

        # ノーポジ: anchor を確定 / 追従させる。
        if self.anchor is None:
            self.anchor = price

        if self.trail_anchor:
            # ロングなら「より高い価格」を anchor に（そこからの下落を押し目として拾う）。
            # ショートなら「より低い価格」を anchor に。
            if self.side is Side.BUY:
                self.anchor = max(self.anchor, price)
            else:
                self.anchor = min(self.anchor, price)

        change_pct = (price - self.anchor) / self.anchor * Decimal("100")

        if self.side is Side.BUY:
            # anchor から entry_drop_pct 以上下落したらロング。
            if change_pct <= -self.entry_drop_pct:
                self.anchor = None  # 次のノーポジ局面で取り直す
                return Signal.enter(Side.BUY, reason=f"price dropped {change_pct:.3f}% from anchor")
        else:
            # anchor から entry_drop_pct 以上上昇したらショート。
            if change_pct >= self.entry_drop_pct:
                self.anchor = None
                return Signal.enter(Side.SELL, reason=f"price rose {change_pct:.3f}% from anchor")

        return Signal.hold()
