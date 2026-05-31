"""リスク管理 / ポジションサイジング。

「1トレードあたり口座残高の何 % までリスクを取るか」からロット数を決める。
損切り幅（%）が分かっているので、リスク額 = 残高 * risk% とし、
units = リスク額 / (価格 * 損切り幅) で求める。
"""

from __future__ import annotations

from decimal import Decimal

from .config import RiskConfig


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


class RiskManager:
    def __init__(self, config: RiskConfig):
        self.config = config

    def position_size(self, equity: Decimal, price: Decimal, stop_loss_pct: Decimal) -> Decimal:
        """エントリ時のロット数（通貨単位）を返す。

        equity: 現在の有効証拠金
        price: エントリ想定価格
        stop_loss_pct: 損切りまでの値幅（%）
        """
        equity = _dec(equity)
        price = _dec(price)
        stop_loss_pct = _dec(stop_loss_pct)

        if price <= 0 or stop_loss_pct <= 0 or equity <= 0:
            return Decimal("0")

        risk_amount = equity * self.config.risk_per_trade_pct / Decimal("100")
        per_unit_risk = price * (stop_loss_pct / Decimal("100"))
        if per_unit_risk <= 0:
            return Decimal("0")

        units = risk_amount / per_unit_risk
        units = min(units, self.config.max_units)
        # 通貨単位は整数に丸める（1通貨未満は扱わない）。
        units = units.to_integral_value(rounding="ROUND_DOWN")
        return max(units, Decimal("0"))

    def can_open(self, open_positions: int) -> bool:
        return open_positions < self.config.max_positions
