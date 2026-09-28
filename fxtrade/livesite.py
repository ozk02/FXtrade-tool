"""ライブ配信サイト（MT4のEAから受け取った口座状況を公開ページに表示する）。

構成:
    VPS上のMT4(EA) --[WebRequestでJSON POST]--> このサーバー --> 訪問者のブラウザ

エンドポイント:
    GET  /                  公開ダッシュボード（誰でも見られる）
    GET  /api/live/status   最新状態のJSON（公開・読み取り専用）
    POST /api/live          EAからの更新受付（★トークン必須）

セキュリティ方針:
    * 書き込み(POST)は共有トークン必須。トークン未設定ならサーバーは起動しない（フェイルクローズ）。
    * トークン比較は hmac.compare_digest（タイミング攻撃対策）。
    * 受信ボディにサイズ上限。JSONとして壊れていれば400。
    * 公開するのは正規化済みの数値のみ。口座番号は末尾4桁だけ。
    * パスワードや取引操作は一切扱わない（このサイトから発注はできない）。
"""

from __future__ import annotations

import hmac
import json
import os
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .livestore import OFFLINE_AFTER_SEC, LiveStore

MAX_BODY = 64 * 1024  # 受信ボディの上限(64KB)


class LiveHandler(BaseHTTPRequestHandler):
    store: LiveStore = None      # serve() が差し込む
    token: str = ""
    title: str = "FX ライブ配信"
    links: dict = {}

    def log_message(self, *args):
        pass  # アクセスログは出さない（必要ならここで記録）

    # --- GET -----------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            body = (PAGE.replace("__TITLE__", _escape(self.title))
                    .replace("__SOCIAL_PANEL__", _social_panel(self.links))).encode("utf-8")
            self._send(200, "text/html; charset=utf-8", body)
        elif path == "/api/live/status":
            self._json(200, self.store.snapshot())
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    # --- POST（EAからの更新） -------------------------------------------
    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/live":
            self._send(404, "text/plain; charset=utf-8", b"not found")
            return

        if not self._authorized():
            self._json(401, {"error": "invalid token"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._json(400, {"error": "bad content-length"})
            return
        if length <= 0 or length > MAX_BODY:
            self._json(413, {"error": "body too large or empty"})
            return

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
            data = self.store.update(payload)
        except (ValueError, UnicodeDecodeError) as exc:
            self._json(400, {"error": f"bad payload: {exc}"})
            return
        self._json(200, {"ok": True, "equity": data["equity"]})

    def _authorized(self) -> bool:
        supplied = self.headers.get("X-Auth-Token") or ""
        if not supplied and "?" in self.path:
            from urllib.parse import parse_qs, urlparse

            supplied = (parse_qs(urlparse(self.path).query).get("token") or [""])[0]
        return bool(self.token) and hmac.compare_digest(supplied, self.token)

    # --- helpers --------------------------------------------------------
    def _json(self, code, obj):
        self._send(code, "application/json; charset=utf-8", json.dumps(obj).encode("utf-8"))

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)


def _escape(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# 公式SNSの表示定義: (設定キー, 表示名, 背景, アイコン文字)
# ブランドロゴの画像は使わず、各社のブランドカラーと文字で表現する（外部ファイル不要）。
SOCIAL_SERVICES = [
    ("line", "公式LINE", "#06C755", "LINE"),
    ("x", "公式X", "#000000", "𝕏"),
    ("facebook", "公式Facebook", "#1877F2", "f"),
    ("instagram", "公式Instagram",
     "linear-gradient(45deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888)", "IG"),
]


def validate_links(links) -> dict:
    """SNSのURLを検証する。https:// 以外（javascript: など）は拒否する。

    空のものは無視するので、持っているSNSだけ指定すればよい。
    """
    out = {}
    for key, label, _bg, _icon in SOCIAL_SERVICES:
        url = ((links or {}).get(key) or "").strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"{label} のURLは https:// で始まる必要があります: {url}")
        out[key] = url
    return out


def render_social_links(links) -> str:
    """公式SNSボタンのHTMLを返す。スタイルは全てインライン（どのHPに貼っても崩れない）。"""
    links = validate_links(links)
    if not links:
        return ""
    buttons = []
    for key, label, bg, icon in SOCIAL_SERVICES:
        url = links.get(key)
        if not url:
            continue
        border = "border:1px solid #444;" if key == "x" else ""
        buttons.append(
            f'<a href="{_escape(url)}" target="_blank" rel="noopener noreferrer" '
            f'aria-label="{_escape(label)}" '
            f'style="display:inline-flex;align-items:center;gap:8px;padding:9px 16px;'
            f'border-radius:999px;background:{bg};{border}color:#fff;text-decoration:none;'
            f'font-weight:700;font-size:14px;font-family:system-ui,sans-serif;line-height:1;">'
            f'<span style="font-weight:800;">{_escape(icon)}</span>{_escape(label)}</a>'
        )
    return (
        '<div class="sns-links" style="display:flex;flex-wrap:wrap;gap:10px;justify-content:center;">'
        + "".join(buttons)
        + "</div>"
    )


def _social_panel(links) -> str:
    html = render_social_links(links)
    if not html:
        return ""
    return '<div class="panel"><h2>公式SNS</h2>' + html + "</div>"


def make_server(host: str, port: int, token: str, title: str = "FX ライブ配信",
                store: LiveStore = None, links: dict = None):
    """サーバーを組み立てて返す（テストから使えるように serve と分離）。"""
    if not token:
        raise ValueError(
            "公開トークンが未設定です。--token か環境変数 FXTRADE_LIVE_TOKEN を指定してください。"
        )
    store = store or LiveStore()
    links = validate_links(links)   # 起動時に検証（不正URLなら起動しない）

    handler = type("BoundLiveHandler", (LiveHandler,),
                   {"store": store, "token": token, "title": title, "links": links})
    server = ThreadingHTTPServer((host, port), handler)
    server.store = store
    return server


def serve(host: str = "0.0.0.0", port: int = 8080, token: str = "", title: str = "FX ライブ配信",
          links: dict = None) -> None:
    token = token or os.environ.get("FXTRADE_LIVE_TOKEN", "")
    server = make_server(host, port, token, title, links=links)
    print(f"ライブ配信サイトを起動しました → http://{host}:{port}")
    print(f"  公開ページ  : GET  /")
    print(f"  EAの送信先  : POST /api/live   (ヘッダ X-Auth-Token にトークン)")
    print(f"  {OFFLINE_AFTER_SEC}秒 更新が無いと『オフライン』表示になります。Ctrl+C で終了。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了します。")
        server.shutdown()


PAGE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root { --bg:#0b1220; --panel:#131f36; --ink:#e6edf7; --muted:#8ba0bf; --up:#34d399; --down:#f87171; --accent:#38bdf8; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:system-ui,"Hiragino Kaku Gothic ProN","Yu Gothic UI",sans-serif; }
  header { padding:14px 18px; display:flex; align-items:center; gap:12px; flex-wrap:wrap;
           background:linear-gradient(90deg,#0ea5e9,#6366f1); }
  header h1 { margin:0; font-size:18px; color:#fff; }
  .status { display:flex; align-items:center; gap:6px; font-size:13px; color:#fff;
            background:rgba(0,0,0,.25); padding:3px 10px; border-radius:999px; }
  .dot { width:9px; height:9px; border-radius:50%; background:#94a3b8; }
  .dot.on { background:#4ade80; box-shadow:0 0 8px #4ade80; animation:pulse 2s infinite; }
  .dot.off { background:#f87171; }
  @keyframes pulse { 50% { opacity:.35; } }
  .wrap { max-width:900px; margin:0 auto; padding:16px; }
  .hero { background:var(--panel); border-radius:14px; padding:20px; text-align:center; margin-bottom:14px; }
  .hero .k { font-size:12px; color:var(--muted); }
  .hero .equity { font-size:42px; font-weight:800; margin:4px 0; letter-spacing:-1px; }
  .hero .sub { font-size:15px; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px; margin-bottom:14px; }
  .card { background:var(--panel); border-radius:12px; padding:12px; text-align:center; }
  .card .k { font-size:11px; color:var(--muted); }
  .card .v { font-size:19px; font-weight:700; margin-top:3px; }
  .panel { background:var(--panel); border-radius:12px; padding:14px; margin-bottom:14px; }
  .panel h2 { font-size:13px; margin:0 0 10px; color:var(--accent); }
  svg { width:100%; height:auto; background:#0a1424; border-radius:8px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { padding:7px 8px; text-align:right; border-bottom:1px solid #24334d; }
  th:first-child,td:first-child,th:nth-child(2),td:nth-child(2) { text-align:left; }
  .up { color:var(--up); } .down { color:var(--down); } .muted { color:var(--muted); }
  .badge { display:inline-block; padding:1px 7px; border-radius:6px; font-size:11px; }
  .badge.BUY { background:#064e3b; color:#34d399; } .badge.SELL { background:#4c1d24; color:#f87171; }
  footer { text-align:center; font-size:11px; color:var(--muted); padding:18px; line-height:1.7; }
</style>
</head>
<body>
<header>
  <h1>📡 __TITLE__</h1>
  <span class="status"><span class="dot" id="dot"></span><span id="statusText">接続中…</span></span>
</header>

<div class="wrap">
  <div class="hero">
    <div class="k">有効証拠金（エクイティ）</div>
    <div class="equity" id="equity">—</div>
    <div class="sub" id="openPnl">—</div>
  </div>

  <div class="cards">
    <div class="card"><div class="k">残高</div><div class="v" id="balance">—</div></div>
    <div class="card"><div class="k">本日の損益</div><div class="v" id="today">—</div></div>
    <div class="card"><div class="k">本日の取引</div><div class="v" id="trades">—</div></div>
    <div class="card"><div class="k">証拠金維持率</div><div class="v" id="margin">—</div></div>
  </div>

  <div class="panel">
    <h2>資産推移</h2>
    <svg id="chart" viewBox="0 0 600 140" preserveAspectRatio="none"></svg>
  </div>

  <div class="panel">
    <h2>保有ポジション（<span id="posCount">0</span>）</h2>
    <table>
      <thead><tr><th>通貨</th><th>売買</th><th>ロット</th><th>建値</th><th>損益</th></tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </div>

  __SOCIAL_PANEL__

  <footer>
    <div id="meta" class="muted"></div>
    ⚠️ このページは運用状況の記録を表示しているだけで、投資助言ではありません。<br>
    表示内容の正確性は保証されません。投資判断はご自身の責任でお願いします。
  </footer>
</div>

<script>
const $ = id => document.getElementById(id);
const fmt = n => Math.round(n).toLocaleString();
const signed = n => (n >= 0 ? '+' : '') + fmt(n);
const cls = n => n >= 0 ? 'up' : 'down';

function drawChart(hist){
  const w=600,h=140,pad=8;
  if(!hist || hist.length < 2){ $('chart').innerHTML=''; return; }
  const vals = hist.map(p => p.equity);
  const min = Math.min(...vals), max = Math.max(...vals), range = (max-min)||1;
  const d = vals.map((v,i)=>{
    const x = pad + (w-2*pad)*(i/(vals.length-1));
    const y = h-pad - (h-2*pad)*((v-min)/range);
    return (i?'L':'M') + x.toFixed(1) + ' ' + y.toFixed(1);
  }).join(' ');
  const color = vals[vals.length-1] >= vals[0] ? '#34d399' : '#f87171';
  $('chart').innerHTML = `<path d="${d}" fill="none" stroke="${color}" stroke-width="2"/>`;
}

async function tick(){
  try{
    const r = await fetch('/api/live/status', {cache:'no-store'});
    const s = await r.json();

    if(s.waiting){
      $('dot').className='dot'; $('statusText').textContent='データ待ち';
      $('meta').textContent='EAからの初回送信を待っています。';
      return;
    }
    const d = s.latest;
    $('dot').className = 'dot ' + (s.online ? 'on':'off');
    $('statusText').textContent = s.online ? '配信中' : 'オフライン';

    $('equity').textContent = fmt(d.equity) + (d.currency ? ' ' + d.currency : '');
    $('openPnl').innerHTML = '含み損益 <span class="'+cls(d.profit_open)+'">'+signed(d.profit_open)+'</span>';
    $('balance').textContent = fmt(d.balance);
    $('today').innerHTML = '<span class="'+cls(d.profit_today)+'">'+signed(d.profit_today)+'</span>';
    $('trades').textContent = d.trades_today;
    $('margin').textContent = d.margin_level ? d.margin_level.toFixed(0)+'%' : '—';

    drawChart(s.history);

    $('posCount').textContent = d.positions.length;
    $('rows').innerHTML = d.positions.length ? d.positions.map(p=>`<tr>
        <td>${p.symbol||'-'}</td>
        <td><span class="badge ${p.side}">${p.side==='BUY'?'買':'売'}</span></td>
        <td>${p.lots}</td><td>${p.open_price}</td>
        <td class="${cls(p.profit)}">${signed(p.profit)}</td></tr>`).join('')
      : '<tr><td colspan="5" class="muted">ポジションなし</td></tr>';

    const bits = [];
    if(d.account) bits.push('口座 '+d.account);
    if(d.broker) bits.push(d.broker);
    if(d.regime) bits.push('相場: '+d.regime);
    bits.push(Math.round(s.age_sec)+'秒前に更新');
    $('meta').textContent = bits.join(' ／ ');
  }catch(e){
    $('dot').className='dot off'; $('statusText').textContent='接続エラー';
  }
}
tick();
setInterval(tick, 5000);
</script>
</body>
</html>
"""
