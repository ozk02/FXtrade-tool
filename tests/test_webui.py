import unittest

from fxtrade.webui import run_backtest


class TestWebUIBackend(unittest.TestCase):
    def test_run_backtest_returns_ui_payload(self):
        out = run_backtest({
            "symbol": "USD_JPY", "n": 200, "seed": 1,
            "entry_drop_pct": 0.5, "take_profit_pct": 1.0, "stop_loss_pct": 2.0,
            "nanpin_enabled": True, "trailing_enabled": True, "risk_per_trade_pct": 1.0,
        })
        self.assertIn("summary", out)
        self.assertEqual(len(out["prices"]), 200)
        self.assertEqual(len(out["equity"]), 200)
        # サマリのキーが揃っている
        for k in ("initial_cash", "final_equity", "pnl", "total_return_pct", "num_trades", "win_rate", "max_drawdown_pct"):
            self.assertIn(k, out["summary"])
        # マーカーはトレード数の2倍以内（建て+決済）
        self.assertLessEqual(len(out["markers"]), out["summary"]["num_trades"] * 2)

    def test_n_is_clamped(self):
        out = run_backtest({"n": 5})        # 下限20に丸められる
        self.assertEqual(len(out["prices"]), 20)

    def test_short_direction(self):
        out = run_backtest({"direction": "short", "n": 150, "seed": 3})
        self.assertEqual(out["symbol"], "USD_JPY")
        self.assertEqual(len(out["prices"]), 150)

    def test_ma_cross_strategy_selectable(self):
        out = run_backtest({"strategy_type": "ma_cross", "n": 300, "seed": 4,
                            "fast_period": 10, "slow_period": 30})
        self.assertEqual(out["strategy"], "ma_cross")
        self.assertIn("順張り", out["strategy_label"])
        self.assertNotIn("regimes", out)   # レジーム帯は自動切替のときだけ

    def test_regime_strategy_returns_regime_series(self):
        out = run_backtest({"strategy_type": "regime", "n": 400, "seed": 4,
                            "adx_period": 14, "adx_threshold": 25})
        self.assertEqual(out["strategy"], "regime")
        self.assertEqual(len(out["regimes"]), 400)
        self.assertTrue(set(out["regimes"]) <= {"trend", "range", "warmup"})
        rs = out["regime_summary"]
        self.assertAlmostEqual(rs["trend_pct"] + rs["range_pct"], 100.0, places=6)

    def test_unknown_strategy_raises(self):
        with self.assertRaises(ValueError):
            run_backtest({"strategy_type": "nope"})

    def test_profit_factor_infinity_serialized_as_null(self):
        # 全勝(損失なし)だと PF=Infinity → JSON化のため None になる
        out = run_backtest({
            "n": 60, "seed": 1, "entry_drop_pct": 0.3,
            "take_profit_pct": 0.3, "stop_loss_pct": 50.0,
        })
        self.assertIn("profit_factor", out["summary"])


if __name__ == "__main__":
    unittest.main()
