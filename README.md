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
- **3つの売買ロジック** — 逆張り（価格と％）／順張り（移動平均クロス）／ADXで両者を自動切替。
- **価格＋％戦略** (`PricePercentStrategy`) — 押し目買い/戻り売り、％利確・％損切り、anchor追従。
- **ナンピン（増し玉）** — 初回建値から N% ずつ不利方向へ進むたびに積み増し（回数・ロット倍率を指定可能）。
- **トレーリングストップ** — 最有利値からの戻り % で利を伸ばしつつ手仕舞い（発動しきい値も指定可能）。
- **楽天MT4 用EA同梱** — 同じ戦略を MetaTrader 4 の自動売買EA (`mt4/PricePercentEA.mq4`) として実装。実FX自動売買はこちらが王道（[mt4/README.md](mt4/README.md)）。
- **バックテスト** — 勝率・PF・最大ドローダウン・損益を集計。
- **ペーパートレード** — 仮想ブローカーで売買ループを再現（ライブと同じコードパス）。
- **差し替え可能なブローカー** — `paper` / `rakuten`(差込み口)。`Broker` プロトコルで拡張可能。
- **リスク管理** — 1トレードのリスク%からロット自動計算、最大ポジション数の制御。
- **ブラウザUI** — `python3 -m fxtrade ui` でフォーム＆チャート表示。コマンド不要で試せる。
- **ライブ配信サイト** — EAから口座状況を受信し、公開ページでリアルタイム表示。
- **テスト付き** — `unittest` で 74 ケース。

## 実際にFX自動売買するなら：楽天MT4 用EA 🤖

楽天証券で自動売買するなら **楽天MT4** が王道です。同じ戦略を MetaTrader 4 の
EA（自動売買プログラム）として同梱しています。インストール・設定手順は
**[mt4/README.md](mt4/README.md)** を参照してください（`mt4/PricePercentEA.mq4`）。

下記のブラウザUI/コマンドはパラメータの感触を掴むためのシミュレーションです。
**感触を掴む → 楽天MT4のデモ口座でEAを検証 → 実運用**、の流れがおすすめです。

## いちばん簡単：ブラウザUIで動かす 🖱️

コマンドが苦手な方はこれだけでOK。証券口座・ネット接続・追加インストールは不要です。

```bash
python3 -m fxtrade ui
```

自動でブラウザが開きます（開かなければ http://localhost:8000 を開く）。
左のフォームで**売買ロジック**（逆張り／順張り／自動切替）・利確/損切り%・ナンピン・
トレーリング等を設定し、**「▶ デモ実行」** を押すと、価格チャート（▲買い ▼売り）・
資産推移グラフ・勝率や損益などの成績・トレード明細が表示されます。
ロジックを切り替えて同じ相場（同じシード）で比べると、型ごとの性格の違いが分かります。

> 表示されるのはツール内蔵のシミュレーション結果です。実際の発注は行いません。

### 自分のライブ配信サイトを作る 📡

MT4のEA（VPS上）から口座状況を送信し、自分のWebページでリアルタイム公開できます。

```bash
python3 -m fxtrade live --port 8080 --token "秘密の文字列" --title "私のFX運用ライブ"
```

有効証拠金・本日の損益・保有ポジション・資産推移グラフが表示され、2分更新が無いと
「オフライン」表示になります。EA側は `PublishEnabled=true` と送信先URL・トークンを設定するだけ。
動画配信と違いCPUをほぼ使わないので、FX専用VPSでも安全に動きます。

手順の詳細は **[docs/live-site.md](docs/live-site.md)**。

> ⚠️ 公開されるのは正規化された数値のみで、口座番号は末尾4桁だけ。パスワードは扱わず、
> このページから発注もできません。ただし**有料配信や投資助言にあたる行為は金融商品取引法の
> 登録が必要**になる場合があります。詳細は上記ドキュメントを参照。

### NAS / Docker で常時稼働させる 🐳

NAS（UGREEN NASync / Synology / QNAP など）や任意のDocker環境で動かせます。
NASは24時間動いているので、PCを立ち上げなくても**スマホやタブレットからいつでも**
デモ画面を開けます。

```bash
docker compose up -d      # 起動 → http://<NASのIP>:8000
```

手順の詳細は **[docs/nas-docker.md](docs/nas-docker.md)** を参照。

> ⚠️ このUIには認証がありません。**家庭内LAN限定**で使い、インターネットには公開しないでください。
> また、NASで動くのは**検証UIのみ**です（MT4での実売買はWindowsが必要なのでVPSを使ってください）。

### Windows: デスクトップのアイコンから起動する 🖥️

毎回コマンドを打たなくて済むように、ダブルクリックで起動できます。

1. プロジェクトフォルダ内の **`デスクトップにアイコンを作成.bat`** をダブルクリック
   （これで デスクトップに「FXデモトレード」アイコンが作られます）
2. 以降は デスクトップの **「FXデモトレード」** をダブルクリックするだけで起動

直接 **`run_ui.bat`** をダブルクリックしても起動できます。

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
├── indicators.py        逐次更新の指標 (SMA/EMA/ADX)
├── config.py            設定読み込み (YAML/JSON, PyYAML不要のフォールバック)
├── risk.py              リスク管理・ポジションサイジング
├── engine.py            ライブ/ペーパー売買エンジン
├── backtest.py          バックテストエンジン + 統計
├── cli.py               CLI (ui / live / gen-data / backtest / paper)
├── webui.py             ブラウザUI (標準ライブラリのみのWebサーバ+画面)
├── livesite.py          ライブ配信サイト (EAからの受信 + 公開ページ)
├── livestore.py         配信データの正規化・保持 (口座番号マスク等)
├── data/                マーケットデータ供給 (CSV / 合成データ)
├── strategies/          戦略 (base / price_percent / ma_cross / regime, レジストリ)
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

## 売買ロジック一覧

| name | タイプ | 中身 | 得意 | 弱点 |
|---|---|---|---|---|
| `price_percent` | 逆張り | anchorから N% 動いたら反対に張る | レンジ相場 | トレンドが続くと大やられ |
| `ma_cross` | 順張り | 短期MAが長期MAを抜けた向きに乗る | トレンド相場 | レンジで細かく負ける。勝率は低め(3〜4割) |
| `regime` | 自動切替 | ADXで相場を判定し、上2つを使い分ける | 環境変化 | ADXの判定は遅れる。万能ではない |

### `ma_cross`（順張り / トレンドフォロー）

ゴールデンクロスで買い、デッドクロスで売り。反対のクロスが出たら手仕舞いし、次の足でドテンします。
`take_profit_pct: 0` にすると利確せずクロスまで持つ「利大損小」型になります（順張りの本来の形）。

**勝率が低いのは仕様**です。負けを小さく切り、当たったトレンドで大きく取ることで期待値を出す型なので、
勝率で判断せず、トータル損益と最大ドローダウンを見てください。

### `regime`（ADXレジームフィルター）

ADX（トレンドの強さを 0〜100 で表す指標）を見て、担当する戦略を切り替えます。

```
ADX >= adx_threshold → トレンド相場 → trend 側の戦略（既定: ma_cross）
ADX <  adx_threshold → レンジ相場   → ranging 側の戦略（既定: price_percent）
```

設定例は `config.regime.example.yaml`。実装上の要点は2つあります。

- **建玉を持っている間は担当を替えません。** エントリした戦略が決済まで面倒を見ます
  （途中で替わると、相手の戦略が「自分が建てていない玉」を扱うことになるため）。
- **担当外の戦略にも毎足データを渡します。** そうしないと移動平均の履歴に穴が空きます。
  その際はノーポジとして渡し、返ってきたシグナルは捨てます。

ブラウザUIで `regime` を選ぶと、価格チャートに**トレンド相場と判定した区間が紫の帯**で表示され、
どこで切り替わったかが目で見えます。

> ⚠️ レジームフィルターは「相場に合わない手法を止める」ための仕組みで、**勝てるようになる保証はありません**。
> ADXの判定は本質的に遅れるため、切り替わりの初動では裏目に出ることもあります。

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

## ⚠️ 合成データの成績を信じすぎないこと

`--n` で生成される検証用データは**ランダムウォーク**です。つまり構造上、
**そもそも儲かる規則性が存在しません**。参考までに、30通りの乱数相場で
3つのロジックを回した結果（初期資金100万円・スプレッド0.2pips）:

| ロジック | 平均損益 | 勝った相場 |
|---|---|---|
| `price_percent` | -9,173円 | 13/30 |
| `ma_cross` | -3,362円 | 13/30 |
| `regime` | -7,428円 | 13/30 |

**どれも平均ではマイナス**です。これは実装の不具合ではなく、
「規則性の無いデータ＋取引コスト」なら当然そうなる、という当たり前の結果です。

したがって:

- 合成データで勝った/負けたは**ロジックの優劣の証拠になりません**（seedを変えれば逆転します）
- 意味のある検証をするには **実際のヒストリカルデータ（CSV）** を使ってください
- 良い成績が出るまで seed やパラメータを探すのは**カーブフィッティング**です。やめましょう

合成データは「動作確認」と「ロジックの性格（順張りは勝率が低い等）を体感する」ためのものと
割り切ってください。
