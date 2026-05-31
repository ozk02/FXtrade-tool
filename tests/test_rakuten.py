import unittest
from datetime import datetime
from decimal import Decimal

from fxtrade.brokers.rakuten import RakutenBroker, RSSCellMap
from fxtrade.brokers.rss_bridge import FakeRSSBridge
from fxtrade.models import Order, OrderType, Side


TS = datetime(2024, 1, 1)


class TestRakutenDryRun(unittest.TestCase):
    def test_dry_run_does_not_touch_bridge_and_tracks_position(self):
        broker = RakutenBroker(dry_run=True, initial_cash=1_000_000)
        broker.submit(Order("USD_JPY", Side.BUY, Decimal("10000")), Decimal("148.00"), TS)
        pos = broker.get_position("USD_JPY")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.units, Decimal("10000"))
        # 反対売買で +1.00 * 10000 の損益
        broker.submit(Order("USD_JPY", Side.SELL, Decimal("10000")), Decimal("149.00"), TS)
        self.assertIsNone(broker.get_position("USD_JPY"))
        self.assertEqual(broker.cash, Decimal("1010000"))
        self.assertEqual(len(broker.trades), 1)


class TestRakutenFetchPrice(unittest.TestCase):
    def test_fetch_price_reads_rss_quote(self):
        cm = RSSCellMap(symbol_codes={"USD_JPY": "USDJPY"})
        # 値セルに RSS 気配が入っている状況を模擬。
        bridge = FakeRSSBridge(quotes={cm.quote_value_cell: 148.255})
        broker = RakutenBroker(cell_map=cm, bridge=bridge, dry_run=False, poll_timeout=1.0)
        price = broker.fetch_price("USD_JPY")
        self.assertEqual(price, Decimal("148.255"))
        # 銘柄コードと RSS 関数式が書き込まれていること。
        self.assertEqual(bridge.cells[cm.quote_code_cell], "USDJPY")
        self.assertIn("USDJPY", str(bridge.cells[cm.quote_value_cell]))


class TestRakutenPlaceOrder(unittest.TestCase):
    def _broker(self, status="OK", fill_price=148.30):
        cm = RSSCellMap(symbol_codes={"USD_JPY": "USDJPY"})

        def handler(bridge, name, args):
            # ユーザーの発注マクロを模擬: ステータスと約定価格を書き戻す。
            bridge.set(cm.order_status_cell, status)
            if fill_price is not None:
                bridge.set(cm.fill_price_cell, fill_price)
            bridge.set(cm.order_id_cell, "ORD123")

        bridge = FakeRSSBridge(order_handler=handler)
        return RakutenBroker(cell_map=cm, bridge=bridge, dry_run=False, poll_timeout=1.0), bridge, cm

    def test_place_order_success_updates_position(self):
        broker, bridge, cm = self._broker(status="OK", fill_price=148.30)
        fill = broker.submit(Order("USD_JPY", Side.BUY, Decimal("10000")), Decimal("148.00"), TS)
        self.assertEqual(fill.price, Decimal("148.30"))  # RSS約定価格が採用される
        pos = broker.get_position("USD_JPY")
        self.assertEqual(pos.units, Decimal("10000"))
        self.assertEqual(pos.entry_price, Decimal("148.30"))
        # 発注パラメータが正しく書かれたか
        self.assertEqual(bridge.cells[cm.order_code_cell], "USDJPY")
        self.assertEqual(bridge.cells[cm.order_side_cell], cm.buy_code)
        self.assertEqual(bridge.cells[cm.order_qty_cell], 10000)
        self.assertEqual(bridge.cells[cm.order_type_cell], cm.market_type)
        # 発注マクロが1回呼ばれた
        self.assertEqual(len(bridge.macro_calls), 1)
        self.assertEqual(bridge.macro_calls[0][0], cm.order_macro)

    def test_place_order_uses_reference_price_when_no_fill_price(self):
        broker, bridge, cm = self._broker(status="OK", fill_price=None)
        fill = broker.submit(Order("USD_JPY", Side.SELL, Decimal("5000")), Decimal("148.10"), TS)
        self.assertEqual(fill.price, Decimal("148.10"))

    def test_place_order_rejected_raises(self):
        broker, bridge, cm = self._broker(status="REJECTED")
        with self.assertRaises(RuntimeError):
            broker.submit(Order("USD_JPY", Side.BUY, Decimal("10000")), Decimal("148.00"), TS)
        # 発注失敗時は建玉が作られない
        self.assertIsNone(broker.get_position("USD_JPY"))

    def test_numeric_status_treated_as_success(self):
        # 注文番号(数値)が返る運用でも成功扱い
        broker, bridge, cm = self._broker(status=998877, fill_price=148.5)
        fill = broker.submit(Order("USD_JPY", Side.BUY, Decimal("1000")), Decimal("148.0"), TS)
        self.assertEqual(fill.price, Decimal("148.5"))


class TestCellMapFromDict(unittest.TestCase):
    def test_dict_cellmap_via_build(self):
        from fxtrade.brokers import build_broker

        broker = build_broker(
            "rakuten",
            {
                "dry_run": True,
                "initial_cash": 500000,
                "cell_map": {"order_macro": "MyOrder", "quote_value_cell": "Z9"},
            },
        )
        self.assertEqual(broker.cell_map.order_macro, "MyOrder")
        self.assertEqual(broker.cell_map.quote_value_cell, "Z9")
        self.assertTrue(broker.dry_run)


if __name__ == "__main__":
    unittest.main()
