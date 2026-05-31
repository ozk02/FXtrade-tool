"""売買ツール全体で使う基本データ型。

外部ライブラリに依存しないよう、標準ライブラリの dataclass / Enum のみで定義する。
価格や数量に float を使うと丸め誤差が出るため、金額計算には Decimal を用いる。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional


class Side(enum.Enum):
    """売買方向。"""

    BUY = "BUY"
    SELL = "SELL"

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY

    @property
    def sign(self) -> int:
        """ロングを +1、ショートを -1 として扱うための符号。"""
        return 1 if self is Side.BUY else -1


class OrderType(enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass(frozen=True)
class Candle:
    """1本のローソク足（OHLC）。"""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")

    @classmethod
    def from_row(cls, ts: datetime, o, h, l, c, v=0) -> "Candle":
        d = lambda x: x if isinstance(x, Decimal) else Decimal(str(x))
        return cls(ts, d(o), d(h), d(l), d(c), d(v))


@dataclass
class Order:
    """発注リクエスト。"""

    symbol: str
    side: Side
    units: Decimal
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[Decimal] = None
    reason: str = ""  # 戦略がエントリ/決済の根拠を残せるようにする


@dataclass
class Position:
    """建玉（保有ポジション）。units は常に正の数で、向きは side が持つ。"""

    symbol: str
    side: Side
    units: Decimal
    entry_price: Decimal
    opened_at: datetime

    def unrealized_pnl(self, price: Decimal) -> Decimal:
        """現在価格に対する評価損益（建玉通貨建て）。"""
        return (price - self.entry_price) * self.side.sign * self.units


@dataclass
class Fill:
    """約定結果。"""

    order: Order
    price: Decimal
    units: Decimal
    timestamp: datetime
    commission: Decimal = Decimal("0")


@dataclass
class Trade:
    """エントリから決済までの1往復の記録（バックテスト集計用）。"""

    symbol: str
    side: Side
    units: Decimal
    entry_price: Decimal
    exit_price: Decimal
    opened_at: datetime
    closed_at: datetime
    pnl: Decimal
    reason: str = ""

    @property
    def return_pct(self) -> Decimal:
        if self.entry_price == 0:
            return Decimal("0")
        return (self.exit_price - self.entry_price) / self.entry_price * self.side.sign * Decimal("100")


@dataclass
class AccountState:
    """口座の状態スナップショット。"""

    cash: Decimal
    equity: Decimal
    positions: list = field(default_factory=list)
