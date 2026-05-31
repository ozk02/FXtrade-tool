import unittest
from datetime import datetime
from decimal import Decimal

from fxtrade.brokers.paper import PaperBroker
from fxtrade.models import Order, OrderType, Side


class TestPaperBroker(unittest.TestCase):
    def setUp(self):
        self.ts = datetime(2024, 1, 1)
        # スプレッド0で計算を簡単にする
        self.b = PaperBroker(initial_cash=1_000_000, spread_pips=0, commission_per_unit=0)

    def test_open_and_close_profit(self):
        self.b.submit(Order("USD_JPY", Side.BUY, Decimal("10000")), Decimal("100"), self.ts)
        pos = self.b.get_position("USD_JPY")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.units, Decimal("10000"))
        # 101 で決済 -> +1 * 10000 = +10000
        self.b.submit(Order("USD_JPY", Side.SELL, Decimal("10000")), Decimal("101"), self.ts)
        self.assertIsNone(self.b.get_position("USD_JPY"))
        self.assertEqual(self.b.cash, Decimal("1010000"))
        self.assertEqual(len(self.b.trades), 1)
        self.assertEqual(self.b.trades[0].pnl, Decimal("10000"))

    def test_short_profit_on_drop(self):
        self.b.submit(Order("USD_JPY", Side.SELL, Decimal("10000")), Decimal("100"), self.ts)
        self.b.submit(Order("USD_JPY", Side.BUY, Decimal("10000")), Decimal("99"), self.ts)
        self.assertEqual(self.b.cash, Decimal("1010000"))

    def test_averaging_in(self):
        self.b.submit(Order("USD_JPY", Side.BUY, Decimal("10000")), Decimal("100"), self.ts)
        self.b.submit(Order("USD_JPY", Side.BUY, Decimal("10000")), Decimal("102"), self.ts)
        pos = self.b.get_position("USD_JPY")
        self.assertEqual(pos.units, Decimal("20000"))
        self.assertEqual(pos.entry_price, Decimal("101"))  # 平均

    def test_equity_includes_unrealized(self):
        self.b.submit(Order("USD_JPY", Side.BUY, Decimal("10000")), Decimal("100"), self.ts)
        eq = self.b.equity({"USD_JPY": Decimal("100.5")})
        # 含み益 +0.5 * 10000 = 5000
        self.assertEqual(eq, Decimal("1005000"))

    def test_spread_applied(self):
        b = PaperBroker(initial_cash=1_000_000, spread_pips=1, pip_size=0.01)
        # 買いは ask = 100 + 0.005
        b.submit(Order("USD_JPY", Side.BUY, Decimal("10000")), Decimal("100"), self.ts)
        pos = b.get_position("USD_JPY")
        self.assertEqual(pos.entry_price, Decimal("100.005"))


if __name__ == "__main__":
    unittest.main()
