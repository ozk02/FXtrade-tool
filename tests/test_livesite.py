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


class TestSocialLinks(unittest.TestCase):
    ALL = {
        "line": "https://lin.ee/abc123",
        "x": "https://x.com/example",
        "facebook": "https://www.facebook.com/example",
        "instagram": "https://www.instagram.com/example/",
    }

    def test_renders_all_four_in_order(self):
        from fxtrade.livesite import render_social_links
        html = render_social_links(self.ALL)
        labels = ["公式LINE", "公式X", "公式Facebook", "公式Instagram"]
        positions = [html.index(f'aria-label="{l}"') for l in labels]
        self.assertEqual(positions, sorted(positions))   # LINE→X→Facebook→Instagram の順
        self.assertEqual(html.count('rel="noopener noreferrer"'), 4)
        self.assertEqual(html.count('target="_blank"'), 4)

    def test_only_configured_services_shown(self):
        from fxtrade.livesite import render_social_links
        html = render_social_links({"line": "https://lin.ee/a", "instagram": ""})
        self.assertIn("公式LINE", html)
        self.assertNotIn("公式Instagram", html)
        self.assertNotIn("公式X", html)

    def test_empty_returns_nothing(self):
        from fxtrade.livesite import render_social_links
        self.assertEqual(render_social_links({}), "")
        self.assertEqual(render_social_links(None), "")

    def test_rejects_non_https(self):
        from fxtrade.livesite import validate_links
        for bad in ("javascript:alert(1)", "http://x.com/a", "data:text/html,hi", "x.com/a", "https://"):
            with self.subTest(url=bad):
                with self.assertRaises(ValueError):
                    validate_links({"x": bad})

    def test_markup_in_url_is_escaped(self):
        from fxtrade.livesite import render_social_links
        html = render_social_links({"x": 'https://x.com/a"><script>alert(1)</script>'})
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_page_includes_panel_only_when_configured(self):
        with_links = make_server("127.0.0.1", 0, token="t", links=self.ALL)
        without = make_server("127.0.0.1", 0, token="t")
        try:
            for srv, expect in ((with_links, True), (without, False)):
                port = srv.server_address[1]
                t = threading.Thread(target=srv.serve_forever, daemon=True)
                t.start()
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as r:
                    html = r.read().decode()
                self.assertEqual("公式SNS" in html, expect)
                self.assertNotIn("__SOCIAL_PANEL__", html)   # プレースホルダが残らない
        finally:
            for srv in (with_links, without):
                srv.shutdown()
                srv.server_close()

    def test_server_refuses_bad_url_at_startup(self):
        with self.assertRaises(ValueError):
            make_server("127.0.0.1", 0, token="t", links={"line": "javascript:x"})


class TestSnsLinksCommand(unittest.TestCase):
    def run_cli(self, argv, env=None):
        import contextlib
        import io
        import os
        from unittest import mock

        from fxtrade.cli import main
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=False), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_prints_snippet(self):
        code, out, _ = self.run_cli(["sns-links", "--line-url", "https://lin.ee/a", "--x-url", "https://x.com/b"])
        self.assertEqual(code, 0)
        self.assertIn("公式LINE", out)
        self.assertIn("公式X", out)

    def test_reads_from_environment(self):
        code, out, _ = self.run_cli(["sns-links"], env={"FXTRADE_FACEBOOK_URL": "https://www.facebook.com/env"})
        self.assertEqual(code, 0)
        self.assertIn("facebook.com/env", out)

    def test_errors_when_nothing_given(self):
        import os
        from unittest import mock
        keys = ["FXTRADE_LINE_URL", "FXTRADE_X_URL", "FXTRADE_FACEBOOK_URL", "FXTRADE_INSTAGRAM_URL"]
        with mock.patch.dict(os.environ, {k: "" for k in keys}):
            code, _, err = self.run_cli(["sns-links"])
        self.assertEqual(code, 1)
        self.assertIn("1つも指定されていません", err)

    def test_errors_on_bad_url(self):
        code, _, err = self.run_cli(["sns-links", "--line-url", "http://line.me/x"])
        self.assertEqual(code, 1)
        self.assertIn("https://", err)


class TestSocialIcons(unittest.TestCase):
    ALL = TestSocialLinks.ALL

    def test_icons_link_to_each_account(self):
        from fxtrade.livesite import render_social_icons
        html = render_social_icons(self.ALL)
        for url in self.ALL.values():
            self.assertIn(f'href="{url}"', html)
        self.assertEqual(html.count("<svg"), 4)
        self.assertEqual(html.count('target="_blank"'), 4)
        self.assertEqual(html.count('rel="noopener noreferrer"'), 4)

    def test_icons_have_accessible_labels(self):
        from fxtrade.livesite import render_social_icons
        html = render_social_icons(self.ALL)
        for label in ("公式LINE", "公式X", "公式Facebook", "公式Instagram"):
            self.assertIn(f'aria-label="{label}"', html)   # 読み上げ用
            self.assertIn(f'title="{label}"', html)        # マウスを乗せたときの表示
        self.assertEqual(html.count('aria-hidden="true"'), 4)  # SVG自体は読み上げない

    def test_uses_official_brand_colors(self):
        from fxtrade.livesite import render_social_icons
        html = render_social_icons(self.ALL)
        self.assertIn('fill="#00C300"', html)   # LINE
        self.assertIn('fill="#000000"', html)   # X
        self.assertIn('fill="#0866FF"', html)   # Facebook
        self.assertIn('fill="url(#sns-ig-grad)"', html)   # Instagram はグラデーション

    def test_instagram_gradient_only_when_needed(self):
        from fxtrade.livesite import render_social_icons
        self.assertNotIn("linearGradient", render_social_icons({"x": "https://x.com/a"}))

    def test_icons_validate_and_escape_like_buttons(self):
        from fxtrade.livesite import render_social_icons
        with self.assertRaises(ValueError):
            render_social_icons({"line": "javascript:alert(1)"})
        html = render_social_icons({"x": 'https://x.com/a"><script>alert(1)</script>'})
        self.assertNotIn("<script>", html)
        self.assertEqual(render_social_icons({}), "")

    def test_cli_style_icons(self):
        code, out, _ = TestSnsLinksCommand().run_cli(
            ["sns-links", "--style", "icons", "--line-url", "https://lin.ee/a"])
        self.assertEqual(code, 0)
        self.assertIn('class="sns-icons"', out)
        self.assertIn("<svg", out)
