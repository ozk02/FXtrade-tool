"""ペーパートレード用の仮想ブローカー。

成行は即時約定。スプレッド/手数料を簡易にモデル化できる。
バックテストとライブ（デモ）の双方でこのブローカーを使える。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from ..models import Fill, Order, OrderType, Position, Side, Trade


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
        self._cash = _dec(initial_cash)
        self.initial_cash = _dec(initial_cash)
        self.spread = _dec(spread_pips) * _dec(pip_size)
        self.commission_per_unit = _dec(commission_per_unit)
        self._positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []

    @property
    def cash(self) -> Decimal:
        return self._cash

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    def positions(self) -> List[Position]:
        return list(self._positions.values())

    def _exec_price(self, side: Side, price: Decimal) -> Decimal:
        # 買いは ask(=mid+半スプレッド)、売りは bid(=mid-半スプレッド) で約定。
        half = self.spread / Decimal("2")
        return price + half if side is Side.BUY else price - half

    def submit(self, order: Order, price: Decimal, timestamp) -> Fill:
        price = _dec(price)
        units = _dec(order.units)
        if units <= 0:
            raise ValueError("order units must be positive")

        exec_price = self._exec_price(order.side, price)
        if order.order_type is OrderType.LIMIT and order.limit_price is not None:
            # 簡易: 指値が約定可能なら指値価格、不能ならエラー扱いにせず成行同様に約定。
            exec_price = _dec(order.limit_price)

        commission = self.commission_per_unit * units
        existing = self._positions.get(order.symbol)

        if existing is None:
            # 新規建て。
            self._positions[order.symbol] = Position(
                symbol=order.symbol,
                side=order.side,
                units=units,
                entry_price=exec_price,
                opened_at=timestamp,
            )
            self._cash -= commission
        elif existing.side is order.side:
            # 同方向に増し玉（平均約定価格を更新）。
            total_units = existing.units + units
            avg = (existing.entry_price * existing.units + exec_price * units) / total_units
            existing.units = total_units
            existing.entry_price = avg
            self._cash -= commission
        else:
            # 反対売買 → 決済（部分/全部）。
            close_units = min(existing.units, units)
            pnl = (exec_price - existing.entry_price) * existing.side.sign * close_units
            self._cash += pnl - commission
            self.trades.append(
                Trade(
                    symbol=order.symbol,
                    side=existing.side,
                    units=close_units,
                    entry_price=existing.entry_price,
                    exit_price=exec_price,
                    opened_at=existing.opened_at,
                    closed_at=timestamp,
                    pnl=pnl,
                    reason=order.reason,
                )
            )
            remaining = existing.units - close_units
            if remaining > 0:
                existing.units = remaining
            else:
                del self._positions[order.symbol]
                # 注文数が建玉を上回る場合はドテン（反対方向で新規）。
                if units > close_units:
                    self._positions[order.symbol] = Position(
                        symbol=order.symbol,
                        side=order.side,
                        units=units - close_units,
                        entry_price=exec_price,
                        opened_at=timestamp,
                    )

        return Fill(order=order, price=exec_price, units=units, timestamp=timestamp, commission=commission)

    def equity(self, mark_prices: Dict[str, Decimal]) -> Decimal:
        eq = self._cash
        for sym, pos in self._positions.items():
            mark = mark_prices.get(sym)
            if mark is not None:
                eq += pos.unrealized_pnl(_dec(mark))
        return eq
