# FXtrade-tool

価格と％で売買する **FX自動売買ツール**（Python・外部依存ゼロで動作）。

「参照価格から N% 動いたらエントリ → +X% で利確 / −Y% で損切り」という、価格と
パーセンテージだけで完結するシンプルな戦略を、**バックテスト → ペーパートレード →
（差込み式の）実発注** の流れで扱えます。

> ⚠️ **楽天証券の実発注について（重要）**
> 楽天証券にはリテール向けの公開 FX REST API が（本ツール作成時点で）ありません。
> プログラム発注は通常 **MarketSpeed II RSS**（Windows + Excel + 楽天RSS）等を介します。
> 本ツールの `rakuten` ブローカーは、その連携を安全に差し込むための**テンプレート**で、
> 既定では `dry_run` かつ実発注部分は未実装（誤発注防止）です。
> まずは `paper`（シミュレーション）で戦略を検証してください。
> 投資は自己責任です。本ツールは学習・検証目的で提供されます。

## 特長

- **外部ライブラリ不要** — Python 3.9+ 標準ライブラリのみ。`pip install` 不要ですぐ動く。
- **価格＋％戦略** (`PricePercentStrategy`) — 押し目買い/戻り売り、％利確・％損切り、anchor追従。
- **ナンピン（増し玉）** — 初回建値から N% ずつ不利方向へ進むたびに積み増し（回数・ロット倍率を指定可能）。
- **トレーリングストップ** — 最有利値からの戻り % で利を伸ばしつつ手仕舞い（発動しきい値も指定可能）。
- **バックテスト** — 勝率・PF・最大ドローダウン・損益を集計。
- **ペーパートレード** — 仮想ブローカーで売買ループを再現（ライブと同じコードパス）。
- **差し替え可能なブローカー** — `paper` / `rakuten`(差込み口)。`Broker` プロトコルで拡張可能。
- **リスク管理** — 1トレードのリスク%からロット自動計算、最大ポジション数の制御。
- **ブラウザUI** — `python3 -m fxtrade ui` でフォーム＆チャート表示。コマンド不要で試せる。
- **テスト付き** — `unittest` で 30 ケース。

## いちばん簡単：ブラウザUIで動かす 🖱️

コマンドが苦手な方はこれだけでOK。証券口座・ネット接続・追加インストールは不要です。

```bash
python3 -m fxtrade ui
```

自動でブラウザが開きます（開かなければ http://localhost:8000 を開く）。
左のフォームで通貨ペア・利確/損切り%・ナンピン・トレーリング等を設定し、
**「▶ デモ実行」** を押すと、価格チャート（▲買い ▼売り）・資産推移グラフ・
勝率や損益などの成績・トレード明細が表示されます。スライダー感覚で何度でも試せます。

> 表示されるのはツール内蔵のシミュレーション結果です。実際の発注は行いません。

## コマンドで動かす

```bash
# 1) 検証用の合成データ(CSV)を生成
python3 -m fxtrade gen-data --n 800 --out data/sample.csv

# 2) バックテスト（合成データ）
python3 -m fxtrade backtest --n 800 --seed 11

# 3) バックテスト（CSV + 設定ファイル、トレード明細付き）
python3 -m fxtrade backtest --csv data/sample.csv --config config.example.yaml --show-trades

# 4) ペーパートレード（デモ）
python3 -m fxtrade paper --config config.example.yaml --n 300
```

## 設定

`config.example.yaml` をコピーして編集します（YAML or JSON。PyYAML 不在でも簡易YAMLを読みます）。

```yaml
symbol: USD_JPY
initial_cash: 1000000
strategy:
  name: price_percent
  params:
    direction: long          # long(押し目買い) / short(戻り売り)
    entry_drop_pct: 0.5      # anchorから何%動いたらエントリ
    take_profit_pct: 1.0     # 利確(%)
    stop_loss_pct: 0.5       # 損切り(%)
    trail_anchor: true
    # ナンピン（％下落ごとの増し玉）
    nanpin_enabled: true
    nanpin_step_pct: 0.5     # 初回建値から何%ごとに増し玉
    max_nanpin: 3            # 最大増し玉回数
    nanpin_size_mult: 1.0    # 増し玉ごとのロット倍率
    # トレーリングストップ
    trailing_enabled: true
    trailing_pct: 0.5        # 最有利値から何%戻したら手仕舞い
    trailing_activate_pct: 0.5  # 含み益が何%でトレーリング開始(0=常時)
risk:
  risk_per_trade_pct: 1.0    # 1トレードで取るリスク(残高の%)
  max_units: 100000          # ★ナンピン時はこれが「総ロット」の上限になる
  max_positions: 1
broker:
  name: paper                # paper / rakuten
  params:
    spread_pips: 0.2
    pip_size: 0.01
```

## ヒストリカルCSVのフォーマット

```csv
timestamp,open,high,low,close,volume
2024-01-01T00:00:00,148.10,148.30,148.00,148.25,1000
```

`volume` 列は省略可。`timestamp` は ISO 8601 等の一般的な形式に対応。

## アーキテクチャ

```
fxtrade/
├── models.py            基本データ型 (Candle/Order/Position/Trade, Decimal計算)
├── config.py            設定読み込み (YAML/JSON, PyYAML不要のフォールバック)
├── risk.py              リスク管理・ポジションサイジング
├── engine.py            ライブ/ペーパー売買エンジン
├── backtest.py          バックテストエンジン + 統計
├── cli.py               CLI (ui / gen-data / backtest / paper)
├── webui.py             ブラウザUI (標準ライブラリのみのWebサーバ+画面)
├── data/                マーケットデータ供給 (CSV / 合成データ)
├── strategies/          戦略 (base + price_percent, レジストリ)
└── brokers/             ブローカー
    ├── base.py          Broker プロトコル
    ├── position_book.py 建玉/現金/約定履歴の共通会計
    ├── paper.py         ペーパートレード(仮想ブローカー)
    ├── rss_bridge.py    Excel/RSS 橋渡し (実機=xlwings/pywin32, テスト=Fake)
    └── rakuten.py       楽天 MarketSpeed II RSS 連携 (fetch_price/_place_order)
```

楽天 RSS 連携の VBA 発注マクロのサンプルは `docs/rss_order_macro.vba`、設定例は
`config.rakuten.example.yaml` を参照。

設計の要点:
- **戦略は純粋ロジック** — 足とポジションを受け取りシグナルを返すだけ。発注はエンジン/ブローカー。
- **バックテストとライブで同じ判定ロジック** を共有。
- **ブローカーはプロトコル** — `paper` で検証し、`rakuten` 等へ差し替え可能。

### ナンピン / トレーリングの挙動メモ

- 1本の足で実行するアクションは1つ。判定の優先順位は
  **損切り → トレーリング → 利確 → ナンピン**。
- そのため `stop_loss_pct` を `nanpin_step_pct` より小さくすると、増し玉する前に損切りされます。
  ナンピンを効かせたい場合は `stop_loss_pct` を十分大きく（または損切りを広め）に設定してください。
- ナンピンの増し玉価格は**初回建値**を基準に `nanpin_step_pct × 回数` で深くなります。
- 増し玉の合計ロットは `risk.max_units` を上限にキャップされます。
- トレーリングは `trailing_activate_pct` の含み益に達してから有効化され、平均建値ではなく
  **最有利値からの戻り幅**で手仕舞いを判定します。

> ⚠️ ナンピンは含み損を抱えたまま積み増す手法で、相場が一方向に動き続けると損失が急拡大します。
> 必ずデモ/バックテストでリスクを把握してください。

### 新しい戦略を追加する

`fxtrade/strategies/base.py` の `Strategy` を継承し、`strategies/__init__.py` の
`REGISTRY` に登録するだけです。

### 楽天証券 MarketSpeed II RSS 連携（実発注）

`fxtrade/brokers/rakuten.py` に **MarketSpeed II RSS 連携を具体実装済み**です。
Excel 経由（`xlwings` / `pywin32`）でセル読み書き・VBA マクロ実行を行います。

**前提（重要）**
- **Windows + Excel + MarketSpeed II（RSS 有効）** が必須。Python から Excel を操作します。
- 気配取得は RSS のマーケット関数（セル関数）を読む安全な方式。
- 発注は**誤発注防止のため VBA 発注マクロ経由**。Python はパラメータをセルに書き、
  あなたの発注マクロを `Application.Run` で呼び、結果セルを読みます。
- **RSS の発注対象は国内株式・先物等**が中心で、店頭FX(楽天FX)の自動発注の可否は
  契約・規約に依存します。関数名・売買区分コード・セル位置は環境差があるため
  `cell_map` で**設定可能**にしてあります。必ず公式
  「MARKETSPEED II RSS 関数リファレンス」で確認してください。

**セットアップ手順**
1. Windows で MarketSpeed II を起動し、RSS（Excel アドイン）を有効化。
2. `pip install xlwings`（または `pip install pywin32`）。
3. Excel で取引用ブックを開き、`docs/rss_order_macro.vba` を参考に発注マクロ
   `RssSendOrder` を実装（★RSS の発注関数は公式リファレンスに合わせて置換）。
4. `config.rakuten.example.yaml` をコピーし、`cell_map`（セル配置）・`symbol_codes`
   （RSS 銘柄コード）・売買区分コードを自分のシートに合わせて編集。
5. **まず `dry_run: true` のまま**実行し、発注フロー/価格取得を検証。
   ```bash
   python3 -m fxtrade paper --config config.rakuten.example.yaml
   ```
6. 十分に確認できたら `dry_run: false` にして少額で実発注テスト。

**動作の流れ**
- `fetch_price(symbol)`: `quote_code_cell` に銘柄コードを書き、`quote_value_cell` に
  RSS 関数式を投入 → 数値が入るまでポーリングして現在値を返す。
- `submit()`（`dry_run=False`）: 発注セル群へパラメータを書き込み → `order_macro` を実行 →
  `order_status_cell` が成功トークン（または数値の注文番号）になるまで待ち、
  `fill_price_cell` から約定価格を取得して建玉に反映。失敗時は `RuntimeError`。
- `dry_run=True` のときは実発注せず、参照価格で擬似約定して建玉のみ更新（ログに `[DRY-RUN]`）。

> ⚠️ 実発注は必ず**利用規約・約款を確認**し、自己責任で。誤発注・損失の責任は負いません。

## テスト

```bash
python3 -m unittest discover -s tests -v
```

## 免責

本ソフトウェアは教育・検証目的で提供されます。実取引による損失について作者は責任を負いません。
必ずデモ/ペーパートレードで十分に検証し、自己責任で利用してください。
