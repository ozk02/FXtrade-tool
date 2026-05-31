"""建玉・現金・約定履歴の管理を共通化するヘルパー。

PaperBroker / RakutenBroker の双方がこれを使い、建て・増し玉・(部分)決済・
ドテンの会計処理を一箇所に集約する。約定価格の決定（スプレッド等）は呼び出し側の責務。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from ..models import Position, Side, Trade


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


class PositionBook:
    def __init__(self, initial_cash=0):
        self.cash = _dec(initial_cash)
        self.initial_cash = _dec(initial_cash)
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []

    def get(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def all(self) -> List[Position]:
        return list(self.positions.values())

    def apply_fill(
        self,
        symbol: str,
        side: Side,
        units: Decimal,
        exec_price: Decimal,
        timestamp,
        commission: Decimal = Decimal("0"),
        reason: str = "",
    ) -> None:
        """約定を反映して建玉・現金・履歴を更新する。"""
        units = _dec(units)
        exec_price = _dec(exec_price)
        commission = _dec(commission)
        if units <= 0:
            raise ValueError("fill units must be positive")

        existing = self.positions.get(symbol)

        if existing is None:
            self.positions[symbol] = Position(symbol, side, units, exec_price, timestamp)
            self.cash -= commission
        elif existing.side is side:
            # 同方向に増し玉（平均建値を更新）。
            total = existing.units + units
            existing.entry_price = (existing.entry_price * existing.units + exec_price * units) / total
            existing.units = total
            self.cash -= commission
        else:
            # 反対売買 → (部分)決済。
            close_units = min(existing.units, units)
            pnl = (exec_price - existing.entry_price) * existing.side.sign * close_units
            self.cash += pnl - commission
            self.trades.append(
                Trade(
                    symbol=symbol,
                    side=existing.side,
                    units=close_units,
                    entry_price=existing.entry_price,
                    exit_price=exec_price,
                    opened_at=existing.opened_at,
                    closed_at=timestamp,
                    pnl=pnl,
                    reason=reason,
                )
            )
            remaining = existing.units - close_units
            if remaining > 0:
                existing.units = remaining
            else:
                del self.positions[symbol]
                if units > close_units:
                    # 建玉を上回る注文 → ドテン（反対方向で新規）。
                    self.positions[symbol] = Position(symbol, side, units - close_units, exec_price, timestamp)

    def equity(self, mark_prices: Dict[str, Decimal]) -> Decimal:
        eq = self.cash
        for sym, pos in self.positions.items():
            mark = mark_prices.get(sym)
            if mark is not None:
                eq += pos.unrealized_pnl(_dec(mark))
        return eq
