import unittest
from decimal import Decimal

from fxtrade.indicators import ADX, EMA, SMA, make_ma


class TestMovingAverages(unittest.TestCase):
    def test_sma_waits_for_period_then_averages_window(self):
        s = SMA(3)
        self.assertIsNone(s.update(1))
        self.assertIsNone(s.update(2))
        self.assertEqual(s.update(3), Decimal(2))     # (1+2+3)/3
        self.assertEqual(s.update(4), Decimal(3))     # (2+3+4)/3 ← 窓が進む
        self.assertTrue(s.ready)

    def test_ema_seeds_with_sma_then_smooths(self):
        e = EMA(3)
        e.update(1); e.update(2)
        self.assertIsNone(e.value)
        self.assertEqual(e.update(3), Decimal(2))     # シード = (1+2+3)/3
        # k = 2/(3+1) = 0.5 → 2 + (6-2)*0.5 = 4
        self.assertEqual(e.update(6), Decimal(4))

    def test_make_ma_and_invalid(self):
        self.assertIsInstance(make_ma("sma", 5), SMA)
        self.assertIsInstance(make_ma("ema", 5), EMA)
        with self.assertRaises(ValueError):
            make_ma("wma", 5)


class TestADX(unittest.TestCase):
    def _feed(self, adx, closes, halfrange=0.2):
        for c in closes:
            adx.update(c + halfrange, c - halfrange, c)

    def test_strong_trend_gives_high_adx(self):
        adx = ADX(14)
        self._feed(adx, [100 + i * 0.5 for i in range(60)])
        self.assertIsNotNone(adx.value)
        self.assertGreater(adx.value, Decimal(25))      # トレンド判定の目安を超える
        self.assertGreater(adx.plus_di, adx.minus_di)   # 上昇なので +DI 優勢

    def test_choppy_range_gives_low_adx(self):
        adx = ADX(14)
        closes = [100.0 + (0.3 if i % 2 == 0 else -0.3) for i in range(60)]
        self._feed(adx, closes, halfrange=0.1)
        self.assertIsNotNone(adx.value)
        self.assertLess(adx.value, Decimal(25))

    def test_downtrend_has_minus_di_dominant(self):
        adx = ADX(14)
        self._feed(adx, [100 - i * 0.5 for i in range(60)])
        self.assertGreater(adx.minus_di, adx.plus_di)

    def test_none_until_warmed_up(self):
        adx = ADX(14)
        # 1本目は前足が無いので必ず None、確定までは None が続く。
        self.assertIsNone(adx.update(100.2, 99.8, 100))
        self.assertFalse(adx.ready)
        self._feed(adx, [100 + i * 0.1 for i in range(10)])
        self.assertIsNone(adx.value)


if __name__ == "__main__":
    unittest.main()
