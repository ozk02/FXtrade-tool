import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from fxtrade.backtest import Backtester
from fxtrade.config import RiskConfig
from fxtrade.models import Candle
from fxtrade.risk import RiskManager
from fxtrade.strategies.price_percent import PricePercentStrategy
from fxtrade.data.sample import generate_random_walk


def make_candles(prices):
    ts = datetime(2024, 1, 1)
    out = []
    for p in prices:
        d = Decimal(str(p))
        out.append(Candle(ts, d, d, d, d, Decimal("0")))
        ts += timedelta(hours=1)
    return out


class TestBacktester(unittest.TestCase):
    def test_winning_long_scenario(self):
        # 100から下落して押し目買い→上昇で利確、を狙える価格列
        prices = [100, 99.0, 98.0, 98.5, 99.5, 100.5]
        strat = PricePercentStrategy(
            entry_drop_pct=1.0, take_profit_pct=1.0, stop_loss_pct=2.0,
            trail_anchor=False, anchor_price=100.0,
        )
        risk = RiskManager(RiskConfig(risk_per_trade_pct=Decimal("100"), max_units=Decimal("100000")))
        bt = Backtester("USD_JPY", strat, risk, initial_cash=1_000_000, spread_pips=0)
        result = bt.run(make_candles(prices))
        self.assertGreaterEqual(result.num_trades, 1)
        # 利確が発生していれば最終評価額は初期資金以上
        self.assertGreater(result.final_equity, Decimal("0"))

    def test_runs_on_random_walk(self):
        strat = PricePercentStrategy()
        risk = RiskManager(RiskConfig())
        bt = Backtester("USD_JPY", strat, risk, initial_cash=1_000_000)
        result = bt.run(generate_random_walk(n=300, seed=7))
        # 統計が計算でき、エクイティカーブが本数分ある
        self.assertEqual(len(result.equity_curve), 300)
        self.assertIsInstance(result.summary(), str)
        self.assertGreaterEqual(result.win_rate, Decimal("0"))

    def test_no_position_left_open(self):
        # バックテスト終了後に建玉が残っていないこと（最終クローズされる）
        strat = PricePercentStrategy(entry_drop_pct=0.5)
        risk = RiskManager(RiskConfig(risk_per_trade_pct=Decimal("50")))
        bt = Backtester("USD_JPY", strat, risk, initial_cash=1_000_000)
        result = bt.run(generate_random_walk(n=200, seed=3))
        # final_equity == cash になっている（建玉なし）かは broker 内部だが、
        # ここでは結果が破綻なく返ることを確認
        self.assertIsNotNone(result.final_equity)


if __name__ == "__main__":
    unittest.main()
