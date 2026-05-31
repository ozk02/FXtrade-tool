"""バックテストエンジン。

ヒストリカルな足を順に戦略へ流し、PaperBroker 上で売買を再現して
損益・統計を集計する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, List, Optional

from .brokers.paper import PaperBroker
from .models import Candle, Order, OrderType, Side, Trade
from .risk import RiskManager
from .strategies.base import SignalType, Strategy


@dataclass
class BacktestResult:
    initial_cash: Decimal
    final_equity: Decimal
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Decimal] = field(default_factory=list)

    @property
    def total_return_pct(self) -> Decimal:
        if self.initial_cash == 0:
            return Decimal("0")
        return (self.final_equity - self.initial_cash) / self.initial_cash * Decimal("100")

    @property
    def num_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> Decimal:
        if not self.trades:
            return Decimal("0")
        wins = sum(1 for t in self.trades if t.pnl > 0)
        return Decimal(wins) / Decimal(len(self.trades)) * Decimal("100")

    @property
    def profit_factor(self) -> Decimal:
        gains = sum((t.pnl for t in self.trades if t.pnl > 0), Decimal("0"))
        losses = sum((-t.pnl for t in self.trades if t.pnl < 0), Decimal("0"))
        if losses == 0:
            return Decimal("0") if gains == 0 else Decimal("Infinity")
        return gains / losses

    @property
    def max_drawdown_pct(self) -> Decimal:
        peak = None
        max_dd = Decimal("0")
        for eq in self.equity_curve:
            if peak is None or eq > peak:
                peak = eq
            if peak and peak > 0:
                dd = (peak - eq) / peak * Decimal("100")
                if dd > max_dd:
                    max_dd = dd
        return max_dd

    def summary(self) -> str:
        return (
            f"初期資金     : {self.initial_cash:,.0f}\n"
            f"最終評価額   : {self.final_equity:,.2f}\n"
            f"トータル損益 : {self.final_equity - self.initial_cash:,.2f} "
            f"({self.total_return_pct:.2f}%)\n"
            f"トレード数   : {self.num_trades}\n"
            f"勝率         : {self.win_rate:.1f}%\n"
            f"PF           : {self.profit_factor:.2f}\n"
            f"最大DD       : {self.max_drawdown_pct:.2f}%"
        )


class Backtester:
    def __init__(
        self,
        symbol: str,
        strategy: Strategy,
        risk: RiskManager,
        initial_cash=1_000_000,
        spread_pips: float = 0.2,
        pip_size: float = 0.01,
    ):
        self.symbol = symbol
        self.strategy = strategy
        self.risk = risk
        self.initial_cash = Decimal(str(initial_cash))
        self.spread_pips = spread_pips
        self.pip_size = pip_size

    def run(self, candles: Iterable[Candle]) -> BacktestResult:
        self.strategy.reset()
        broker = PaperBroker(
            initial_cash=self.initial_cash,
            spread_pips=self.spread_pips,
            pip_size=self.pip_size,
        )
        equity_curve: List[Decimal] = []
        last_close: Optional[Decimal] = None

        # 戦略の損切り幅をサイジングに使う（無ければ既定 0.5%）。
        sl_pct = getattr(self.strategy, "stop_loss_pct", Decimal("0.5"))

        for candle in candles:
            last_close = candle.close
            position = broker.get_position(self.symbol)
            signal = self.strategy.on_candle(candle, position)

            if signal.type is SignalType.ENTER and position is None:
                if self.risk.can_open(len(broker.positions())):
                    units = self.risk.position_size(
                        broker.equity({self.symbol: candle.close}),
                        candle.close,
                        Decimal(str(sl_pct)),
                    )
                    if units > 0:
                        broker.submit(
                            Order(self.symbol, signal.side, units, OrderType.MARKET, reason=signal.reason),
                            candle.close,
                            candle.timestamp,
                        )
            elif signal.type is SignalType.EXIT and position is not None:
                broker.submit(
                    Order(self.symbol, position.side.opposite, position.units, OrderType.MARKET, reason=signal.reason),
                    candle.close,
                    candle.timestamp,
                )

            equity_curve.append(broker.equity({self.symbol: candle.close}))

        # テスト終了時に建玉が残っていれば最終価格で手仕舞いして損益を確定。
        position = broker.get_position(self.symbol)
        if position is not None and last_close is not None:
            broker.submit(
                Order(self.symbol, position.side.opposite, position.units, OrderType.MARKET, reason="backtest end close"),
                last_close,
                candle.timestamp,
            )

        final_equity = broker.equity({self.symbol: last_close} if last_close else {})
        return BacktestResult(
            initial_cash=self.initial_cash,
            final_equity=final_equity,
            trades=list(broker.trades),
            equity_curve=equity_curve,
        )
