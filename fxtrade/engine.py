"""ライブ/ペーパー売買のエンジン。

データフィードから足を1本ずつ受け取り、戦略のシグナルに従って
ブローカーへ発注する。バックテストもこの on_candle を共有して使うため、
ナンピン/トレーリング等のロジックがライブと検証で必ず一致する。

リアルタイム運用では feed を「最新足が来たら yield するジェネレータ」に
差し替えるだけでよい設計にしている。
"""

from __future__ import annotations

import logging
from decimal import ROUND_DOWN, Decimal
from typing import Iterable

from .models import Candle, Order, OrderType, Position
from .risk import RiskManager
from .strategies.base import SignalType, Strategy

logger = logging.getLogger("fxtrade.engine")


class TradingEngine:
    def __init__(self, symbol: str, strategy: Strategy, broker, risk: RiskManager):
        self.symbol = symbol
        self.strategy = strategy
        self.broker = broker
        self.risk = risk

    def _stop_loss_pct(self) -> Decimal:
        return Decimal(str(getattr(self.strategy, "stop_loss_pct", Decimal("0.5"))))

    def _base_units(self, price: Decimal, size_mult: Decimal) -> Decimal:
        equity = self.broker.equity({self.symbol: price})
        units = self.risk.position_size(equity, price, self._stop_loss_pct())
        units = (units * size_mult).to_integral_value(rounding=ROUND_DOWN)
        return units

    def on_candle(self, candle: Candle) -> None:
        position = self.broker.get_position(self.symbol)
        signal = self.strategy.on_candle(candle, position)
        price = candle.close

        if signal.type is SignalType.ENTER and position is None:
            if not self.risk.can_open(len(self.broker.positions())):
                return
            units = self._base_units(price, signal.size_mult)
            if units > 0:
                logger.info("ENTER %s %s units=%s @ %s (%s)", self.symbol, signal.side.value, units, price, signal.reason)
                self._submit(signal.side, units, price, candle.timestamp, signal.reason)

        elif signal.type is SignalType.ADD and position is not None:
            units = self._base_units(price, signal.size_mult)
            # 総ロットが max_units を超えないようにキャップする。
            available = self.risk.config.max_units - position.units
            units = min(units, available)
            if units > 0:
                logger.info("ADD %s %s units=%s @ %s (%s)", self.symbol, signal.side.value, units, price, signal.reason)
                self._submit(signal.side, units, price, candle.timestamp, signal.reason)

        elif signal.type is SignalType.EXIT and position is not None:
            logger.info("EXIT %s units=%s @ %s (%s)", self.symbol, position.units, price, signal.reason)
            self._submit(position.side.opposite, position.units, price, candle.timestamp, signal.reason)

    def _submit(self, side, units, price, timestamp, reason) -> None:
        self.broker.submit(
            Order(self.symbol, side, units, OrderType.MARKET, reason=reason),
            price,
            timestamp,
        )

    def run(self, feed: Iterable[Candle]) -> None:
        """フィードを最後まで（ライブなら無限に）流し続ける。"""
        for candle in feed:
            self.on_candle(candle)
