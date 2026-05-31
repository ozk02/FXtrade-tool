import unittest
from datetime import datetime
from decimal import Decimal

from fxtrade.models import Candle, Position, Side
from fxtrade.strategies.base import SignalType
from fxtrade.strategies.price_percent import PricePercentStrategy


def candle(price, ts=None):
    p = Decimal(str(price))
    return Candle(ts or datetime(2024, 1, 1), p, p, p, p, Decimal("0"))


class TestPricePercentStrategy(unittest.TestCase):
    def test_long_enters_after_drop(self):
        s = PricePercentStrategy(entry_drop_pct=1.0, trail_anchor=False, anchor_price=100.0)
        # 100 -> 99.5 (-0.5%) はまだエントリしない
        self.assertEqual(s.on_candle(candle(99.5), None).type, SignalType.HOLD)
        # 100 -> 98.9 (-1.1%) でロングエントリ
        sig = s.on_candle(candle(98.9), None)
        self.assertEqual(sig.type, SignalType.ENTER)
        self.assertEqual(sig.side, Side.BUY)

    def test_take_profit(self):
        s = PricePercentStrategy(take_profit_pct=1.0, stop_loss_pct=0.5)
        pos = Position("USD_JPY", Side.BUY, Decimal("1000"), Decimal("100"), datetime(2024, 1, 1))
        # +1.2% で利確
        sig = s.on_candle(candle(101.2), pos)
        self.assertEqual(sig.type, SignalType.EXIT)

    def test_stop_loss(self):
        s = PricePercentStrategy(take_profit_pct=1.0, stop_loss_pct=0.5)
        pos = Position("USD_JPY", Side.BUY, Decimal("1000"), Decimal("100"), datetime(2024, 1, 1))
        # -0.6% で損切り
        sig = s.on_candle(candle(99.4), pos)
        self.assertEqual(sig.type, SignalType.EXIT)

    def test_hold_within_band(self):
        s = PricePercentStrategy(take_profit_pct=1.0, stop_loss_pct=0.5)
        pos = Position("USD_JPY", Side.BUY, Decimal("1000"), Decimal("100"), datetime(2024, 1, 1))
        self.assertEqual(s.on_candle(candle(100.3), pos).type, SignalType.HOLD)

    def test_short_enters_after_rise(self):
        s = PricePercentStrategy(entry_drop_pct=1.0, direction="short", trail_anchor=False, anchor_price=100.0)
        sig = s.on_candle(candle(101.5), None)
        self.assertEqual(sig.type, SignalType.ENTER)
        self.assertEqual(sig.side, Side.SELL)

    def test_invalid_params(self):
        with self.assertRaises(ValueError):
            PricePercentStrategy(direction="sideways")
        with self.assertRaises(ValueError):
            PricePercentStrategy(take_profit_pct=0)


if __name__ == "__main__":
    unittest.main()
