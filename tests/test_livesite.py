import json
import threading
import unittest
import urllib.error
import urllib.request

from fxtrade.livestore import LiveStore, mask_account, normalize
from fxtrade.livesite import make_server


class TestLiveStore(unittest.TestCase):
    def test_account_is_masked(self):
        self.assertEqual(mask_account("87654321"), "****4321")
        self.assertEqual(mask_account("12"), "**")
        self.assertEqual(mask_account(None), "")

    def test_normalize_coerces_and_defaults(self):
        d = normalize({"equity": "abc", "balance": 100, "trades_today": "3"})
        self.assertEqual(d["equity"], 0.0)        # 数値でなければ0
        self.assertEqual(d["balance"], 100.0)
        self.assertEqual(d["trades_today"], 3)
        self.assertEqual(d["positions"], [])

    def test_normalize_rejects_non_object(self):
        with self.assertRaises(ValueError):
            normalize(["not", "an", "object"])

    def test_normalize_caps_positions_and_side(self):
        many = [{"side": "buy", "lots": 1} for _ in range(200)]
        d = normalize({"positions": many})
        self.assertLessEqual(len(d["positions"]), 50)
        self.assertEqual(d["positions"][0]["side"], "BUY")
        odd = normalize({"positions": [{"side": "hack"}]})
        self.assertEqual(odd["positions"][0]["side"], "?")

    def test_nan_and_inf_are_rejected(self):
        d = normalize({"equity": float("nan"), "balance": float("inf")})
        self.assertEqual(d["equity"], 0.0)
        self.assertEqual(d["balance"], 0.0)
        json.dumps(d)   # JSON化できること

    def test_history_is_bounded(self):
        s = LiveStore(max_history=5)
        for i in range(20):
            s.update({"equity": i})
        self.assertEqual(len(s.snapshot()["history"]), 5)

    def test_snapshot_before_any_update(self):
        s = LiveStore()
        snap = s.snapshot()
        self.assertTrue(snap["waiting"])
        self.assertFalse(snap["online"])
        self.assertIsNone(snap["latest"])


class TestLiveServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = LiveStore()
        cls.server = make_server("127.0.0.1", 0, token="t0ken", store=cls.store)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def post(self, body, token="t0ken"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Auth-Token"] = token
        req = urllib.request.Request(self.url("/api/live"), data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_token_required(self):
        self.assertEqual(self.post({"equity": 1}, token=None)[0], 401)
        self.assertEqual(self.post({"equity": 1}, token="wrong")[0], 401)

    def test_valid_post_then_public_status(self):
        code, resp = self.post({"account": "87654321", "equity": 1012500, "balance": 1000000})
        self.assertEqual(code, 200)
        self.assertEqual(resp["equity"], 1012500.0)
        with urllib.request.urlopen(self.url("/api/live/status")) as r:
            snap = json.loads(r.read())
        self.assertTrue(snap["online"])
        self.assertEqual(snap["latest"]["account"], "****4321")   # 生の口座番号は出さない

    def test_broken_json_rejected(self):
        self.assertEqual(self.post(b"not json")[0], 400)

    def test_oversized_body_rejected(self):
        self.assertEqual(self.post(b"x" * 70000)[0], 413)

    def test_public_page_served(self):
        with urllib.request.urlopen(self.url("/")) as r:
            html = r.read().decode()
        self.assertEqual(r.status, 200)
        self.assertIn("<title>", html)
        self.assertNotIn("t0ken", html)      # トークンをページに出さない

    def test_unknown_path_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url("/secret"))
        self.assertEqual(ctx.exception.code, 404)

    def test_status_endpoint_needs_no_token(self):
        with urllib.request.urlopen(self.url("/api/live/status")) as r:
            self.assertEqual(r.status, 200)


class TestServerRequiresToken(unittest.TestCase):
    def test_make_server_fails_without_token(self):
        with self.assertRaises(ValueError):
            make_server("127.0.0.1", 0, token="")


if __name__ == "__main__":
    unittest.main()
