import unittest
from datetime import datetime
from decimal import Decimal

from fxtrade.config import RiskConfig
from fxtrade.backtest import Backtester
from fxtrade.models import Candle, Position, Side
from fxtrade.risk import RiskManager
from fxtrade.strategies.base import SignalType
from fxtrade.strategies.price_percent import PricePercentStrategy


def candle(price, ts=None):
    p = Decimal(str(price))
    return Candle(ts or datetime(2024, 1, 1), p, p, p, p, Decimal("0"))


def long_pos(units, entry):
    return Position("USD_JPY", Side.BUY, Decimal(str(units)), Decimal(str(entry)), datetime(2024, 1, 1))


class TestNanpin(unittest.TestCase):
    def _strategy(self):
        return PricePercentStrategy(
            direction="long", anchor_price=100.0, trail_anchor=False,
            entry_drop_pct=1.0, take_profit_pct=10.0, stop_loss_pct=10.0,
            nanpin_enabled=True, nanpin_step_pct=1.0, max_nanpin=2,
        )

    def test_nanpin_adds_at_each_step(self):
        s = self._strategy()
        # 押し目買いでエントリ
        self.assertEqual(s.on_candle(candle(99.5), None).type, SignalType.HOLD)
        self.assertEqual(s.on_candle(candle(98.9), None).type, SignalType.ENTER)

        # 建玉発生（建値98.9, 1000通貨）
        pos = long_pos(1000, 98.9)
        # entry0確定の足。step1=1%下=約97.91。価格97.95はまだ。
        self.assertEqual(s.on_candle(candle(97.95), pos).type, SignalType.HOLD)
        # 97.8 は -1.11% でナンピン#1
        sig = s.on_candle(candle(97.8), pos)
        self.assertEqual(sig.type, SignalType.ADD)
        self.assertEqual(sig.side, Side.BUY)

        # 増し玉約定（2000通貨へ）→ add_countが進む
        pos2 = long_pos(2000, 98.35)
        # step2=2%下=約96.92。97.7はまだ。
        self.assertEqual(s.on_candle(candle(97.7), pos2).type, SignalType.HOLD)
        # 96.8 は entry0(98.9)から-2.12% でナンピン#2
        self.assertEqual(s.on_candle(candle(96.8), pos2).type, SignalType.ADD)

        # 3000通貨へ。max_nanpin=2に到達したのでこれ以上増し玉しない。
        pos3 = long_pos(3000, 97.86)
        self.assertEqual(s.on_candle(candle(95.0), pos3).type, SignalType.HOLD)

    def test_nanpin_increases_units_in_backtest(self):
        # 下落し続ける相場でナンピンが効き、建玉が積み上がること
        prices = [100, 98.9, 97.8, 96.7, 95.6]
        ts = datetime(2024, 1, 1)
        candles = []
        from datetime import timedelta
        for p in prices:
            candles.append(candle(p, ts))
            ts += timedelta(hours=1)

        s = PricePercentStrategy(
            direction="long", anchor_price=100.0, trail_anchor=False,
            entry_drop_pct=1.0, take_profit_pct=50.0, stop_loss_pct=50.0,
            nanpin_enabled=True, nanpin_step_pct=1.0, max_nanpin=3,
        )
        risk = RiskManager(RiskConfig(risk_per_trade_pct=Decimal("10"), max_units=Decimal("1000000")))
        bt = Backtester("USD_JPY", s, risk, initial_cash=1_000_000, spread_pips=0)
        result = bt.run(candles)
        # 複数回約定（初回+ナンピン）してから最終クローズ → トレード明細が1件以上
        self.assertGreaterEqual(result.num_trades, 1)


class TestTrailing(unittest.TestCase):
    def test_trailing_exits_after_activation_and_retrace(self):
        s = PricePercentStrategy(
            direction="long", anchor_price=100.0, trail_anchor=False, entry_drop_pct=1.0,
            take_profit_pct=100.0, stop_loss_pct=100.0,
            trailing_enabled=True, trailing_pct=0.5, trailing_activate_pct=1.0,
        )
        pos = long_pos(1000, 100.0)
        # 建値到達: まだ活性化しない（含み益0%）
        self.assertEqual(s.on_candle(candle(100.0), pos).type, SignalType.HOLD)
        # +2%で活性化、最高値102を記録、戻りなし
        self.assertEqual(s.on_candle(candle(102.0), pos).type, SignalType.HOLD)
        # 102から0.588%戻し → トレーリングで手仕舞い
        sig = s.on_candle(candle(101.4), pos)
        self.assertEqual(sig.type, SignalType.EXIT)
        self.assertIn("trailing", sig.reason)

    def test_trailing_not_triggered_before_activation(self):
        s = PricePercentStrategy(
            direction="long", anchor_price=100.0, trail_anchor=False, entry_drop_pct=1.0,
            take_profit_pct=100.0, stop_loss_pct=100.0,
            trailing_enabled=True, trailing_pct=0.5, trailing_activate_pct=2.0,
        )
        pos = long_pos(1000, 100.0)
        # +0.5%まで上げて0.5%戻しても、活性化前(2%未満)なので手仕舞いしない
        self.assertEqual(s.on_candle(candle(100.5), pos).type, SignalType.HOLD)
        self.assertEqual(s.on_candle(candle(100.0), pos).type, SignalType.HOLD)

    def test_invalid_nanpin_params(self):
        with self.assertRaises(ValueError):
            PricePercentStrategy(nanpin_enabled=True, nanpin_step_pct=0)
        with self.assertRaises(ValueError):
            PricePercentStrategy(trailing_enabled=True, trailing_pct=0)


if __name__ == "__main__":
    unittest.main()
