import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from fxtrade.models import Candle, Position, Side
from fxtrade.strategies.base import Signal, SignalType, Strategy
from fxtrade.strategies.regime import RegimeFilterStrategy


class StubStrategy(Strategy):
    """呼ばれた回数と渡されたポジションを記録するテスト用戦略。"""

    def __init__(self, tag, signal_factory=None, stop_loss_pct=Decimal("1.0")):
        self.name = tag
        self.tag = tag
        self.calls = []
        self.signal_factory = signal_factory or (lambda c, p: Signal.hold())
        self.stop_loss_pct = stop_loss_pct

    def on_candle(self, candle, position):
        self.calls.append(position)
        return self.signal_factory(candle, position)

    def reset(self):
        self.calls = []


def bar(price, ts, spread=0.2):
    p = Decimal(str(price))
    h = p + Decimal(str(spread))
    l = p - Decimal(str(spread))
    return Candle(ts, p, h, l, p, Decimal("0"))


def trend_bars(n=60, start=100.0, step=0.5, t0=None):
    ts = t0 or datetime(2024, 1, 1)
    out = []
    for i in range(n):
        out.append(bar(start + i * step, ts))
        ts += timedelta(hours=1)
    return out


def range_bars(n=60, base=100.0, t0=None):
    ts = t0 or datetime(2024, 1, 1)
    out = []
    for i in range(n):
        out.append(bar(base + (0.3 if i % 2 == 0 else -0.3), ts, spread=0.1))
        ts += timedelta(hours=1)
    return out


class TestRegimeSwitching(unittest.TestCase):
    def test_trend_market_selects_trend_strategy(self):
        r = RegimeFilterStrategy(
            trend=StubStrategy("trend"), ranging=StubStrategy("range"),
            adx_period=14, adx_threshold=25,
        )
        for c in trend_bars():
            r.on_candle(c, None)
        self.assertEqual(r.regime, "trend")
        self.assertIs(r._active, r.trend)

    def test_range_market_selects_range_strategy(self):
        r = RegimeFilterStrategy(
            trend=StubStrategy("trend"), ranging=StubStrategy("range"),
            adx_period=14, adx_threshold=25,
        )
        for c in range_bars():
            r.on_candle(c, None)
        self.assertEqual(r.regime, "range")
        self.assertIs(r._active, r.ranging)

    def test_both_strategies_receive_every_candle(self):
        """担当外にもデータを渡して指標を温める（移動平均に穴を空けない）。"""
        t, g = StubStrategy("trend"), StubStrategy("range")
        r = RegimeFilterStrategy(trend=t, ranging=g, adx_period=14)
        bars = trend_bars(30)
        for c in bars:
            r.on_candle(c, None)
        self.assertEqual(len(t.calls), len(bars))
        self.assertEqual(len(g.calls), len(bars))

    def test_no_entry_during_warmup(self):
        always_enter = StubStrategy("range", lambda c, p: Signal.enter(Side.BUY, "x"))
        r = RegimeFilterStrategy(
            trend=StubStrategy("trend"), ranging=always_enter,
            adx_period=14, warmup_hold=True,
        )
        # ADXが確定するまでは売買しない
        first = r.on_candle(bar(100, datetime(2024, 1, 1)), None)
        self.assertEqual(first.type, SignalType.HOLD)
        self.assertEqual(r.regime, "warmup")


def drive(strategy, candles, position=None):
    """エンジンの売買ループを模擬する（ENTERで建玉が生まれ、EXITで消える）。"""
    last = None
    for c in candles:
        last = strategy.on_candle(c, position)
        if last.type is SignalType.ENTER:
            position = Position("USD_JPY", last.side, Decimal("1000"), c.close, c.timestamp)
        elif last.type is SignalType.EXIT:
            position = None
    return last, position


class TestOwnership(unittest.TestCase):
    def test_owner_keeps_control_after_regime_flips(self):
        """レンジ戦略が建てた玉は、トレンド相場になっても同じ戦略が面倒を見る。"""
        ranging = StubStrategy("range", lambda c, p: Signal.enter(Side.BUY, "range entry") if p is None else Signal.hold())
        trend = StubStrategy("trend", lambda c, p: Signal.exit("trend would exit"))
        r = RegimeFilterStrategy(trend=trend, ranging=ranging, adx_period=14, adx_threshold=25)

        # レンジ相場でADXを確定させ、レンジ戦略にエントリさせる。
        ts = datetime(2024, 1, 1)
        _, position = drive(r, range_bars(40, t0=ts))
        self.assertEqual(r.regime, "range")
        self.assertIsNotNone(position)
        self.assertIs(r._owner, ranging)

        # 建玉を持ったままトレンド相場に変わっても、担当はレンジ戦略のまま。
        sig, position = drive(r, trend_bars(40, t0=ts + timedelta(days=10)), position)
        self.assertEqual(r.regime, "trend")          # 相場はトレンドと判定
        self.assertIs(r._owner, ranging)             # でも担当は替わらない
        self.assertEqual(sig.type, SignalType.HOLD)  # trend の EXIT は採用されない
        self.assertIsNotNone(position)               # 決済もされていない

    def test_owner_cleared_when_position_closed(self):
        """決済されたら担当が外れ、次は現在のレジームに応じた戦略が担当する。"""
        ranging = StubStrategy("range", lambda c, p: Signal.enter(Side.BUY, "x") if p is None else Signal.exit("close"))
        trend = StubStrategy("trend")
        r = RegimeFilterStrategy(trend=trend, ranging=ranging, adx_period=14, adx_threshold=25)

        _, position = drive(r, range_bars(40))
        # エントリ→次の足で決済、を繰り返すので最終的にどちらかの状態で終わる。
        if position is None:
            self.assertIsNone(r._owner)
        else:
            self.assertIs(r._owner, ranging)

        # ノーポジのままトレンド相場に入れば、担当はトレンド戦略に移る。
        drive(r, trend_bars(60, t0=datetime(2024, 3, 1)), None)
        self.assertEqual(r.regime, "trend")
        self.assertIs(r._active, trend)

    def test_stop_loss_pct_follows_active_strategy(self):
        trend = StubStrategy("trend", stop_loss_pct=Decimal("3.0"))
        ranging = StubStrategy("range", stop_loss_pct=Decimal("0.5"))
        r = RegimeFilterStrategy(trend=trend, ranging=ranging, adx_period=14, adx_threshold=25)
        for c in range_bars(40):
            r.on_candle(c, None)
        self.assertEqual(r.stop_loss_pct, Decimal("0.5"))   # レンジ相場 → 逆張り側
        for c in trend_bars(60):
            r.on_candle(c, None)
        self.assertEqual(r.stop_loss_pct, Decimal("3.0"))   # トレンド相場 → 順張り側


class TestRegimeBuildFromConfig(unittest.TestCase):
    def test_nested_strategy_specs(self):
        from fxtrade.strategies import build_strategy

        r = build_strategy("regime", {
            "adx_period": 10,
            "adx_threshold": 30,
            "trend": {"name": "ma_cross", "params": {"fast_period": 5, "slow_period": 15}},
            "ranging": {"name": "price_percent", "params": {"take_profit_pct": 2.0}},
        })
        self.assertEqual(r.adx_period, 10)
        self.assertEqual(r.adx_threshold, Decimal("30"))
        self.assertEqual(r.trend.fast_period, 5)
        self.assertEqual(r.ranging.take_profit_pct, Decimal("2.0"))

    def test_defaults_are_ma_cross_and_price_percent(self):
        from fxtrade.strategies import build_strategy

        r = build_strategy("regime", {})
        self.assertEqual(r.trend.name, "ma_cross")
        self.assertEqual(r.ranging.name, "price_percent")

    def test_status_string(self):
        r = RegimeFilterStrategy(adx_period=14)
        for c in trend_bars(60):
            r.on_candle(c, None)
        self.assertIn("regime=", r.status())
        self.assertIn("ADX=", r.status())


if __name__ == "__main__":
    unittest.main()
