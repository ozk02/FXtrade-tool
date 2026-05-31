"""ペーパートレード用の仮想ブローカー。

成行は即時約定。スプレッド/手数料を簡易にモデル化できる。
建玉・現金の会計は PositionBook に委譲し、約定価格（スプレッド）だけここで決める。
バックテストとライブ（デモ）の双方でこのブローカーを使える。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from ..models import Fill, Order, OrderType, Position, Side
from .position_book import PositionBook


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


class PaperBroker:
    def __init__(
        self,
        initial_cash=1_000_000,
        spread_pips: float = 0.2,
        pip_size: float = 0.01,  # USD/JPY は 0.01、クロス無し通貨は 0.0001
        commission_per_unit: float = 0.0,
    ):
        self._book = PositionBook(initial_cash)
        self.initial_cash = _dec(initial_cash)
        self.spread = _dec(spread_pips) * _dec(pip_size)
        self.commission_per_unit = _dec(commission_per_unit)

    @property
    def cash(self) -> Decimal:
        return self._book.cash

    @property
    def trades(self):
        return self._book.trades

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._book.get(symbol)

    def positions(self) -> List[Position]:
        return self._book.all()

    def _exec_price(self, side: Side, price: Decimal) -> Decimal:
        # 買いは ask(=mid+半スプレッド)、売りは bid(=mid-半スプレッド) で約定。
        half = self.spread / Decimal("2")
        return price + half if side is Side.BUY else price - half

    def submit(self, order: Order, price: Decimal, timestamp) -> Fill:
        units = _dec(order.units)
        if units <= 0:
            raise ValueError("order units must be positive")

        exec_price = self._exec_price(order.side, _dec(price))
        if order.order_type is OrderType.LIMIT and order.limit_price is not None:
            # 簡易: 指値が約定可能なら指値価格で約定。
            exec_price = _dec(order.limit_price)

        commission = self.commission_per_unit * units
        self._book.apply_fill(order.symbol, order.side, units, exec_price, timestamp, commission, order.reason)
        return Fill(order=order, price=exec_price, units=units, timestamp=timestamp, commission=commission)

    def equity(self, mark_prices: Dict[str, Decimal]) -> Decimal:
        return self._book.equity(mark_prices)
