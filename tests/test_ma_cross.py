import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from fxtrade.models import Candle, Position, Side
from fxtrade.strategies.base import SignalType
from fxtrade.strategies.ma_cross import MACrossStrategy


def candle(price, ts=None):
    p = Decimal(str(price))
    return Candle(ts or datetime(2024, 1, 1), p, p, p, p, Decimal("0"))


def pos(side, units, entry):
    return Position("USD_JPY", side, Decimal(str(units)), Decimal(str(entry)), datetime(2024, 1, 1))


class TestMACross(unittest.TestCase):
    def _feed(self, strategy, prices, position=None):
        """価格列を流し、最後に返ったシグナルを返す。"""
        sig = None
        for p in prices:
            sig = strategy.on_candle(candle(p), position)
        return sig

    def test_golden_cross_enters_long(self):
        s = MACrossStrategy(fast_period=2, slow_period=4, ma_type="sma")
        # 下降 → 上昇に転じるとゴールデンクロスが発生する。
        signals = [s.on_candle(candle(p), None).type for p in [10, 9, 8, 7, 6, 9, 12, 15]]
        self.assertIn(SignalType.ENTER, signals)
        # 最後にENTERしたときの方向は買い
        s2 = MACrossStrategy(fast_period=2, slow_period=4, ma_type="sma")
        entered = None
        for p in [10, 9, 8, 7, 6, 9, 12, 15]:
            sig = s2.on_candle(candle(p), None)
            if sig.type is SignalType.ENTER:
                entered = sig
                break
        self.assertIsNotNone(entered)
        self.assertEqual(entered.side, Side.BUY)

    def test_dead_cross_enters_short_when_allowed(self):
        s = MACrossStrategy(fast_period=2, slow_period=4, ma_type="sma", allow_short=True)
        entered = None
        for p in [6, 7, 8, 9, 10, 7, 4, 1]:
            sig = s.on_candle(candle(p), None)
            if sig.type is SignalType.ENTER:
                entered = sig
                break
        self.assertIsNotNone(entered)
        self.assertEqual(entered.side, Side.SELL)

    def test_no_short_entry_when_disallowed(self):
        s = MACrossStrategy(fast_period=2, slow_period=4, ma_type="sma", allow_short=False)
        sides = []
        for p in [6, 7, 8, 9, 10, 7, 4, 1]:
            sig = s.on_candle(candle(p), None)
            if sig.type is SignalType.ENTER:
                sides.append(sig.side)
        self.assertNotIn(Side.SELL, sides)

    def test_opposite_cross_exits_position(self):
        s = MACrossStrategy(fast_period=2, slow_period=4, ma_type="sma", stop_loss_pct=0, take_profit_pct=0)
        held = pos(Side.BUY, 1000, 10)
        # 上昇でMAを整えてから下落に転じさせる
        last = self._feed(s, [10, 11, 12, 13, 14, 15], held)
        self.assertEqual(last.type, SignalType.HOLD)
        exited = None
        for p in [12, 9, 6, 3]:
            sig = s.on_candle(candle(p), held)
            if sig.type is SignalType.EXIT:
                exited = sig
                break
        self.assertIsNotNone(exited)
        self.assertIn("cross", exited.reason)

    def test_stop_loss_exits_and_waits_for_next_cross(self):
        s = MACrossStrategy(fast_period=2, slow_period=4, ma_type="sma", stop_loss_pct=1.0)
        held = pos(Side.BUY, 1000, 100)
        # -2% は損切り
        sig = s.on_candle(candle(98), held)
        self.assertEqual(sig.type, SignalType.EXIT)
        self.assertIn("stop loss", sig.reason)
        # 損切り直後にノーポジでも、記憶した方向は消えているので即再エントリしない
        self.assertEqual(s.on_candle(candle(98), None).type, SignalType.HOLD)

    def test_take_profit(self):
        s = MACrossStrategy(fast_period=2, slow_period=4, stop_loss_pct=0, take_profit_pct=2.0)
        held = pos(Side.BUY, 1000, 100)
        self.assertEqual(s.on_candle(candle(101), held).type, SignalType.HOLD)
        self.assertEqual(s.on_candle(candle(103), held).type, SignalType.EXIT)

    def test_trailing_stop(self):
        s = MACrossStrategy(
            fast_period=2, slow_period=4, stop_loss_pct=0, take_profit_pct=0,
            trailing_enabled=True, trailing_pct=1.0, trailing_activate_pct=1.0,
        )
        held = pos(Side.BUY, 1000, 100)
        self.assertEqual(s.on_candle(candle(105), held).type, SignalType.HOLD)  # +5%で活性化
        sig = s.on_candle(candle(103), held)                                    # 2%戻し
        self.assertEqual(sig.type, SignalType.EXIT)
        self.assertIn("trailing", sig.reason)

    def test_invalid_params(self):
        with self.assertRaises(ValueError):
            MACrossStrategy(fast_period=50, slow_period=20)   # fast >= slow
        with self.assertRaises(ValueError):
            MACrossStrategy(trailing_enabled=True, trailing_pct=0)

    def test_no_signal_before_warmup(self):
        s = MACrossStrategy(fast_period=5, slow_period=20)
        for p in [100 + i for i in range(10)]:
            self.assertEqual(s.on_candle(candle(p), None).type, SignalType.HOLD)


if __name__ == "__main__":
    unittest.main()
