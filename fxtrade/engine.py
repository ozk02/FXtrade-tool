"""ライブ/ペーパー売買のエンジン。

データフィードから足を1本ずつ受け取り、戦略のシグナルに従って
ブローカーへ発注する。バックテストと同じ判定ロジックを使うが、
こちらは任意のブローカー（paper/rakuten）に対して動く。

リアルタイム運用では candles() を「最新足が来たら yield するジェネレータ」に
差し替えるだけでよい設計にしている。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterable, Optional

from .models import Candle, Order, OrderType
from .risk import RiskManager
from .strategies.base import SignalType, Strategy

logger = logging.getLogger("fxtrade.engine")


class TradingEngine:
    def __init__(self, symbol: str, strategy: Strategy, broker, risk: RiskManager):
        self.symbol = symbol
        self.strategy = strategy
        self.broker = broker
        self.risk = risk

    def on_candle(self, candle: Candle) -> None:
        position = self.broker.get_position(self.symbol)
        signal = self.strategy.on_candle(candle, position)
        sl_pct = getattr(self.strategy, "stop_loss_pct", Decimal("0.5"))

        if signal.type is SignalType.ENTER and position is None:
            if not self.risk.can_open(len(self.broker.positions())):
                return
            units = self.risk.position_size(
                self.broker.equity({self.symbol: candle.close}),
                candle.close,
                Decimal(str(sl_pct)),
            )
            if units > 0:
                logger.info("ENTER %s %s units=%s @ %s (%s)", self.symbol, signal.side.value, units, candle.close, signal.reason)
                self.broker.submit(
                    Order(self.symbol, signal.side, units, OrderType.MARKET, reason=signal.reason),
                    candle.close,
                    candle.timestamp,
                )
        elif signal.type is SignalType.EXIT and position is not None:
            logger.info("EXIT %s units=%s @ %s (%s)", self.symbol, position.units, candle.close, signal.reason)
            self.broker.submit(
                Order(self.symbol, position.side.opposite, position.units, OrderType.MARKET, reason=signal.reason),
                candle.close,
                candle.timestamp,
            )

    def run(self, feed: Iterable[Candle]) -> None:
        """フィードを最後まで（ライブなら無限に）流し続ける。"""
        for candle in feed:
            self.on_candle(candle)
