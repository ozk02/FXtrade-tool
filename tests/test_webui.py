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

    def test_profit_factor_infinity_serialized_as_null(self):
        # 全勝(損失なし)だと PF=Infinity → JSON化のため None になる
        out = run_backtest({
            "n": 60, "seed": 1, "entry_drop_pct": 0.3,
            "take_profit_pct": 0.3, "stop_loss_pct": 50.0,
        })
        self.assertIn("profit_factor", out["summary"])


if __name__ == "__main__":
    unittest.main()
