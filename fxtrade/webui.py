"""ブラウザで使える簡単なデモトレードUI（標準ライブラリのみ）。

`python3 -m fxtrade ui` で起動し、http://localhost:8000 を開く。
フォームで戦略パラメータを設定 → 「デモ実行」で バックテストを走らせ、
資産推移・価格チャート（売買マーカー付き）・成績サマリ・トレード明細を表示する。

外部依存ゼロ。チャートはJS側でSVGを描画する。
"""

from __future__ import annotations

import json
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .backtest import Backtester
from .config import RiskConfig
from .data.csv_feed import CSVFeed
from .data.sample import generate_random_walk
from .risk import RiskManager
from .strategies.price_percent import PricePercentStrategy


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _b(v) -> bool:
    return bool(v) and str(v).lower() not in ("false", "0", "off", "no")


def run_backtest(params: dict) -> dict:
    """フォームのパラメータでバックテストを実行し、UI向けJSONを返す。"""
    symbol = params.get("symbol") or "USD_JPY"
    initial_cash = _f(params.get("initial_cash"), 1_000_000)
    n = max(20, min(_i(params.get("n"), 500), 5000))
    seed = _i(params.get("seed"), 42)
    csv_path = params.get("csv") or None

    strategy = PricePercentStrategy(
        direction=params.get("direction") or "long",
        entry_drop_pct=_f(params.get("entry_drop_pct"), 0.5),
        take_profit_pct=_f(params.get("take_profit_pct"), 1.0),
        stop_loss_pct=_f(params.get("stop_loss_pct"), 2.0),
        trail_anchor=_b(params.get("trail_anchor", True)),
        nanpin_enabled=_b(params.get("nanpin_enabled")),
        nanpin_step_pct=_f(params.get("nanpin_step_pct"), 0.5),
        max_nanpin=_i(params.get("max_nanpin"), 3),
        nanpin_size_mult=_f(params.get("nanpin_size_mult"), 1.0),
        trailing_enabled=_b(params.get("trailing_enabled")),
        trailing_pct=_f(params.get("trailing_pct"), 0.5),
        trailing_activate_pct=_f(params.get("trailing_activate_pct"), 0.0),
    )
    risk = RiskManager(
        RiskConfig(
            risk_per_trade_pct=Decimal(str(_f(params.get("risk_per_trade_pct"), 1.0))),
            max_units=Decimal(str(_f(params.get("max_units"), 100000))),
            max_positions=_i(params.get("max_positions"), 1),
        )
    )

    if csv_path:
        candles = list(CSVFeed(csv_path).candles())
    else:
        candles = generate_random_walk(n=n, seed=seed, start_price=_f(params.get("start_price"), 148.0))

    bt = Backtester(symbol, strategy, risk, initial_cash=initial_cash, spread_pips=_f(params.get("spread_pips"), 0.2))
    result = bt.run(candles)

    timestamps = [c.timestamp.isoformat() for c in candles]
    prices = [float(c.close) for c in candles]
    equity = [float(e) for e in result.equity_curve]

    ts_index = {t: i for i, t in enumerate(timestamps)}
    trades = []
    markers = []
    for t in result.trades:
        oi = ts_index.get(t.opened_at.isoformat())
        ci = ts_index.get(t.closed_at.isoformat())
        trades.append(
            {
                "opened_at": t.opened_at.strftime("%m-%d %H:%M"),
                "closed_at": t.closed_at.strftime("%m-%d %H:%M"),
                "side": t.side.value,
                "units": float(t.units),
                "entry_price": float(t.entry_price),
                "exit_price": float(t.exit_price),
                "pnl": float(t.pnl),
                "return_pct": float(t.return_pct),
                "reason": t.reason,
            }
        )
        if oi is not None:
            markers.append({"i": oi, "price": float(t.entry_price), "kind": "entry", "side": t.side.value})
        if ci is not None:
            markers.append({"i": ci, "price": float(t.exit_price), "kind": "exit", "side": t.side.value})

    return {
        "summary": {
            "initial_cash": float(result.initial_cash),
            "final_equity": float(result.final_equity),
            "pnl": float(result.final_equity - result.initial_cash),
            "total_return_pct": float(result.total_return_pct),
            "num_trades": result.num_trades,
            "win_rate": float(result.win_rate),
            "profit_factor": (None if result.profit_factor == Decimal("Infinity") else float(result.profit_factor)),
            "max_drawdown_pct": float(result.max_drawdown_pct),
        },
        "timestamps": timestamps,
        "prices": prices,
        "equity": equity,
        "markers": markers,
        "trades": trades,
        "symbol": symbol,
    }


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # サーバーログを静かにする
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self):
        if self.path != "/api/run":
            self._send(404, "text/plain; charset=utf-8", b"not found")
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            params = json.loads(body.decode("utf-8") or "{}")
            result = run_backtest(params)
            payload = json.dumps(result).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", payload)
        except Exception as exc:  # フォーム値の不正などをUIに返す
            payload = json.dumps({"error": str(exc)}).encode("utf-8")
            self._send(400, "application/json; charset=utf-8", payload)

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}"
    print(f"デモトレードUIを起動しました → {url}")
    print("ブラウザが開かない場合は上のURLを手動で開いてください。Ctrl+C で終了。")
    if open_browser:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了します。")
        server.shutdown()


# 画面（HTML/CSS/JS を1ファイルに同梱。外部CDN不要）。
PAGE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FX自動売買 デモトレード</title>
<style>
  :root { --bg:#0f172a; --panel:#1e293b; --ink:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; --green:#34d399; --red:#f87171; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, "Hiragino Kaku Gothic ProN", "Yu Gothic UI", sans-serif; background:var(--bg); color:var(--ink); }
  header { padding:16px 20px; background:linear-gradient(90deg,#0ea5e9,#6366f1); color:#fff; }
  header h1 { margin:0; font-size:20px; }
  header p { margin:4px 0 0; font-size:13px; opacity:.9; }
  .wrap { display:flex; gap:16px; padding:16px; align-items:flex-start; flex-wrap:wrap; }
  .panel { background:var(--panel); border-radius:12px; padding:16px; box-shadow:0 1px 3px rgba(0,0,0,.4); }
  .form { width:330px; flex:0 0 auto; }
  .results { flex:1 1 480px; min-width:360px; }
  h2 { font-size:15px; margin:0 0 10px; color:var(--accent); }
  label { display:block; font-size:12px; color:var(--muted); margin:10px 0 3px; }
  input[type=number], select { width:100%; padding:7px 8px; border-radius:8px; border:1px solid #334155; background:#0b1220; color:var(--ink); font-size:14px; }
  .row { display:flex; gap:8px; }
  .row > div { flex:1; }
  .switch { display:flex; align-items:center; gap:8px; margin-top:12px; font-size:13px; color:var(--ink); }
  .switch input { width:18px; height:18px; }
  button { margin-top:16px; width:100%; padding:12px; border:0; border-radius:10px; background:var(--accent); color:#062a3a; font-weight:700; font-size:15px; cursor:pointer; }
  button:hover { filter:brightness(1.07); }
  .hint { font-size:11px; color:var(--muted); margin-top:2px; }
  .cards { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:14px; }
  .card { background:#0b1220; border-radius:10px; padding:10px; text-align:center; }
  .card .k { font-size:11px; color:var(--muted); }
  .card .v { font-size:18px; font-weight:700; margin-top:3px; }
  .chart-title { font-size:13px; color:var(--muted); margin:6px 0; }
  svg { width:100%; height:auto; background:#0b1220; border-radius:10px; }
  table { width:100%; border-collapse:collapse; font-size:12px; margin-top:6px; }
  th, td { padding:6px 8px; text-align:right; border-bottom:1px solid #243044; }
  th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align:left; }
  .pos { color:var(--green); } .neg { color:var(--red); }
  .muted { color:var(--muted); }
  .scroll { max-height:260px; overflow:auto; }
  .err { color:var(--red); font-size:13px; margin-top:10px; }
  .badge { display:inline-block; padding:1px 6px; border-radius:6px; font-size:11px; }
  .badge.BUY { background:#064e3b; color:#34d399; } .badge.SELL { background:#4c1d24; color:#f87171; }
  .note { font-size:11px; color:var(--muted); margin-top:14px; line-height:1.5; }
</style>
</head>
<body>
<header>
  <h1>📈 FX自動売買 デモトレード</h1>
  <p>実際のお金は使いません。パラメータを変えて「デモ実行」を押すだけ。</p>
</header>
<div class="wrap">
  <div class="panel form">
    <h2>① 設定</h2>
    <div class="row">
      <div><label>通貨ペア</label>
        <select id="symbol"><option>USD_JPY</option><option>EUR_JPY</option><option>GBP_JPY</option><option>EUR_USD</option></select></div>
      <div><label>初期資金(円)</label><input type="number" id="initial_cash" value="1000000" step="100000"></div>
    </div>
    <div class="row">
      <div><label>売買方向</label>
        <select id="direction"><option value="long">買い(押し目)</option><option value="short">売り(戻り)</option></select></div>
      <div><label>相場の本数</label><input type="number" id="n" value="500" step="100"></div>
    </div>

    <label>エントリ: 何%動いたら(entry)</label>
    <input type="number" id="entry_drop_pct" value="0.5" step="0.1">
    <div class="row">
      <div><label>利確 %</label><input type="number" id="take_profit_pct" value="1.0" step="0.1"></div>
      <div><label>損切り %</label><input type="number" id="stop_loss_pct" value="2.0" step="0.1"></div>
    </div>

    <label class="switch"><input type="checkbox" id="nanpin_enabled"> ナンピン(増し玉)を使う</label>
    <div class="row">
      <div><label>下落幅 %/回</label><input type="number" id="nanpin_step_pct" value="0.5" step="0.1"></div>
      <div><label>最大回数</label><input type="number" id="max_nanpin" value="3" step="1"></div>
    </div>

    <label class="switch"><input type="checkbox" id="trailing_enabled" checked> トレーリングストップを使う</label>
    <div class="row">
      <div><label>戻り幅 %</label><input type="number" id="trailing_pct" value="0.5" step="0.1"></div>
      <div><label>発動益 %</label><input type="number" id="trailing_activate_pct" value="0.5" step="0.1"></div>
    </div>

    <label>1トレードのリスク %（残高に対して）</label>
    <input type="number" id="risk_per_trade_pct" value="1.0" step="0.5">
    <div class="hint">乱数の相場で検証します。「シード」を固定すると同じ相場で比較できます。</div>
    <label>シード(乱数)</label><input type="number" id="seed" value="42" step="1">

    <button id="run">▶ デモ実行</button>
    <div id="err" class="err"></div>
    <div class="note">※これはツール内蔵のシミュレーションです。証券口座やネット接続は不要で、実発注は行いません。</div>
  </div>

  <div class="panel results">
    <h2>② 結果</h2>
    <div id="placeholder" class="muted">左で設定して「デモ実行」を押してください。</div>
    <div id="out" style="display:none">
      <div class="cards">
        <div class="card"><div class="k">損益</div><div class="v" id="c_pnl">-</div></div>
        <div class="card"><div class="k">リターン</div><div class="v" id="c_ret">-</div></div>
        <div class="card"><div class="k">勝率</div><div class="v" id="c_win">-</div></div>
        <div class="card"><div class="k">最大DD</div><div class="v" id="c_dd">-</div></div>
      </div>
      <div class="chart-title">価格チャート（▲買い ▼売り）</div>
      <svg id="priceChart" viewBox="0 0 600 220" preserveAspectRatio="none"></svg>
      <div class="chart-title">資産推移（有効証拠金）</div>
      <svg id="equityChart" viewBox="0 0 600 160" preserveAspectRatio="none"></svg>
      <div class="chart-title">トレード明細（<span id="tcount">0</span>件）</div>
      <div class="scroll">
        <table><thead><tr><th>建</th><th>方向</th><th>建値→決済</th><th>損益</th><th>%</th><th>理由</th></tr></thead>
        <tbody id="trows"></tbody></table>
      </div>
    </div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
const yen = n => (n>=0?'+':'') + Math.round(n).toLocaleString() + '円';
const pct = n => (n>=0?'+':'') + n.toFixed(2) + '%';
const cls = n => n>=0 ? 'pos' : 'neg';

function collect(){
  const ids = ['symbol','initial_cash','direction','n','entry_drop_pct','take_profit_pct','stop_loss_pct',
    'nanpin_step_pct','max_nanpin','trailing_pct','trailing_activate_pct','risk_per_trade_pct','seed'];
  const p = {};
  ids.forEach(i => p[i] = $(i).value);
  p.nanpin_enabled = $('nanpin_enabled').checked;
  p.trailing_enabled = $('trailing_enabled').checked;
  return p;
}

function pathFrom(arr, w, h, pad){
  const min = Math.min(...arr), max = Math.max(...arr);
  const range = (max-min) || 1;
  const n = arr.length;
  return arr.map((v,i)=>{
    const x = pad + (w-2*pad) * (n<=1?0:i/(n-1));
    const y = h-pad - (h-2*pad) * (v-min)/range;
    return (i===0?'M':'L') + x.toFixed(1) + ' ' + y.toFixed(1);
  }).join(' ');
}
function scaleXY(arr, w, h, pad){
  const min = Math.min(...arr), max = Math.max(...arr);
  const range = (max-min) || 1;
  const n = arr.length;
  return i => {
    const x = pad + (w-2*pad) * (n<=1?0:i/(n-1));
    const y = h-pad - (h-2*pad) * (arr[i]-min)/range;
    return [x,y];
  };
}

function drawPrice(prices, markers){
  const w=600,h=220,pad=10;
  const sc = scaleXY(prices, w, h, pad);
  let svg = `<path d="${pathFrom(prices,w,h,pad)}" fill="none" stroke="#38bdf8" stroke-width="1.5"/>`;
  markers.forEach(m=>{
    const [x,y] = sc(m.i);
    const entry = m.kind==='entry';
    const color = entry ? '#34d399' : '#f87171';
    const tri = entry ? `${x},${y-7} ${x-5},${y+3} ${x+5},${y+3}` : `${x},${y+7} ${x-5},${y-3} ${x+5},${y-3}`;
    svg += `<polygon points="${tri}" fill="${color}"/>`;
  });
  $('priceChart').innerHTML = svg;
}
function drawEquity(eq, base){
  const w=600,h=160,pad=10;
  let svg = '';
  // 初期資金ライン
  const min=Math.min(...eq,base), max=Math.max(...eq,base), range=(max-min)||1;
  const by = h-pad - (h-2*pad)*(base-min)/range;
  svg += `<line x1="${pad}" y1="${by}" x2="${w-pad}" y2="${by}" stroke="#475569" stroke-dasharray="4 4" stroke-width="1"/>`;
  const last = eq[eq.length-1] ?? base;
  const col = last>=base ? '#34d399' : '#f87171';
  svg += `<path d="${pathFrom(eq,w,h,pad)}" fill="none" stroke="${col}" stroke-width="1.8"/>`;
  $('equityChart').innerHTML = svg;
}

async function run(){
  $('err').textContent = '';
  $('run').textContent = '実行中…';
  $('run').disabled = true;
  try{
    const res = await fetch('/api/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(collect())});
    const data = await res.json();
    if(data.error){ $('err').textContent = 'エラー: ' + data.error; return; }
    const s = data.summary;
    $('placeholder').style.display='none';
    $('out').style.display='block';
    $('c_pnl').innerHTML = `<span class="${cls(s.pnl)}">${yen(s.pnl)}</span>`;
    $('c_ret').innerHTML = `<span class="${cls(s.total_return_pct)}">${pct(s.total_return_pct)}</span>`;
    $('c_win').textContent = s.win_rate.toFixed(0) + '%';
    $('c_dd').textContent = s.max_drawdown_pct.toFixed(1) + '%';
    drawPrice(data.prices, data.markers);
    drawEquity(data.equity, s.initial_cash);
    $('tcount').textContent = data.trades.length;
    $('trows').innerHTML = data.trades.map(t=>`<tr>
      <td class="muted">${t.opened_at}</td>
      <td><span class="badge ${t.side}">${t.side==='BUY'?'買':'売'}</span></td>
      <td>${t.entry_price.toFixed(3)}→${t.exit_price.toFixed(3)}</td>
      <td class="${cls(t.pnl)}">${yen(t.pnl)}</td>
      <td class="${cls(t.return_pct)}">${t.return_pct.toFixed(2)}</td>
      <td class="muted" style="text-align:left">${t.reason||''}</td></tr>`).join('') || '<tr><td colspan=6 class="muted">トレードなし</td></tr>';
  }catch(e){ $('err').textContent = '通信エラー: ' + e; }
  finally{ $('run').textContent='▶ デモ実行'; $('run').disabled=false; }
}
$('run').addEventListener('click', run);
run(); // 初回自動実行
</script>
</body>
</html>
"""
