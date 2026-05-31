"""ブローカーインターフェース。

エンジンはこのインターフェースだけに依存する。ペーパートレードでも
実ブローカーでも、同じコードで売買ループを回せるようにするのが目的。
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Protocol

from ..models import Fill, Order, Position


class Broker(Protocol):
    def submit(self, order: Order, price: Decimal, timestamp) -> Fill:
        """注文を出して約定結果を返す。"""
        ...

    def get_position(self, symbol: str) -> Optional[Position]:
        ...

    def positions(self) -> List[Position]:
        ...

    @property
    def cash(self) -> Decimal:
        ...

    def equity(self, mark_prices: dict) -> Decimal:
        """mark_prices: {symbol: price} を使った有効証拠金。"""
        ...
