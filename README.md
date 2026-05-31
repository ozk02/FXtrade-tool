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
- **バックテスト** — 勝率・PF・最大ドローダウン・損益を集計。
- **ペーパートレード** — 仮想ブローカーで売買ループを再現（ライブと同じコードパス）。
- **差し替え可能なブローカー** — `paper` / `rakuten`(差込み口)。`Broker` プロトコルで拡張可能。
- **リスク管理** — 1トレードのリスク%からロット自動計算、最大ポジション数の制御。
- **テスト付き** — `unittest` で 14 ケース。

## クイックスタート

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
risk:
  risk_per_trade_pct: 1.0    # 1トレードで取るリスク(残高の%)
  max_units: 100000
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
├── cli.py               CLI (gen-data / backtest / paper)
├── data/                マーケットデータ供給 (CSV / 合成データ)
├── strategies/          戦略 (base + price_percent, レジストリ)
└── brokers/             ブローカー (base + paper + rakuten差込み口)
```

設計の要点:
- **戦略は純粋ロジック** — 足とポジションを受け取りシグナルを返すだけ。発注はエンジン/ブローカー。
- **バックテストとライブで同じ判定ロジック** を共有。
- **ブローカーはプロトコル** — `paper` で検証し、`rakuten` 等へ差し替え可能。

### 新しい戦略を追加する

`fxtrade/strategies/base.py` の `Strategy` を継承し、`strategies/__init__.py` の
`REGISTRY` に登録するだけです。

### 楽天証券（実発注）を実装する場合

`fxtrade/brokers/rakuten.py` の `_place_order` / `fetch_price` を、MarketSpeed II RSS 等の
連携方式で実装します。**利用規約・約款を必ず確認**し、`dry_run=True` で十分に検証してから
実発注を有効化してください。

## テスト

```bash
python3 -m unittest discover -s tests -v
```

## 免責

本ソフトウェアは教育・検証目的で提供されます。実取引による損失について作者は責任を負いません。
必ずデモ/ペーパートレードで十分に検証し、自己責任で利用してください。
