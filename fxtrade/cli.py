"""コマンドラインインターフェース。

サブコマンド:
  gen-data   検証用の合成データ(CSV)を生成
  backtest   ヒストリカル/合成データで戦略をバックテスト
  paper      ペーパートレード(デモ)を実行
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from decimal import Decimal

from .backtest import Backtester
from .brokers import build_broker
from .config import Config
from .data.csv_feed import CSVFeed, write_csv
from .data.sample import generate_random_walk
from .engine import TradingEngine
from .risk import RiskManager
from .strategies import build_strategy


def _load_config(path: str | None) -> Config:
    if path:
        return Config.load(path)
    return Config()


def _candles_from_args(args):
    if getattr(args, "csv", None):
        return list(CSVFeed(args.csv).candles())
    return generate_random_walk(n=args.n, seed=args.seed)


def cmd_gen_data(args) -> int:
    candles = generate_random_walk(n=args.n, start_price=args.start_price, seed=args.seed)
    write_csv(args.out, candles)
    print(f"{len(candles)} 本のローソク足を生成しました -> {args.out}")
    return 0


def cmd_backtest(args) -> int:
    cfg = _load_config(args.config)
    if args.symbol:
        cfg.symbol = args.symbol
    strategy = build_strategy(cfg.strategy.name, cfg.strategy.params)
    risk = RiskManager(cfg.risk)
    candles = _candles_from_args(args)
    if not candles:
        print("データが空です。--csv か --n を確認してください。", file=sys.stderr)
        return 1

    bt = Backtester(
        symbol=cfg.symbol,
        strategy=strategy,
        risk=risk,
        initial_cash=cfg.initial_cash,
    )
    result = bt.run(candles)
    print(f"=== バックテスト結果 [{cfg.symbol}] / {cfg.strategy.name} ===")
    print(result.summary())
    if args.show_trades:
        print("\n--- トレード明細 ---")
        for t in result.trades:
            print(
                f"{t.opened_at:%Y-%m-%d %H:%M} {t.side.value:4} "
                f"{t.units} {t.entry_price}->{t.exit_price} "
                f"pnl={t.pnl:.2f} ({t.return_pct:.2f}%) {t.reason}"
            )
    return 0


def cmd_paper(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = _load_config(args.config)
    if args.symbol:
        cfg.symbol = args.symbol

    strategy = build_strategy(cfg.strategy.name, cfg.strategy.params)
    risk = RiskManager(cfg.risk)
    broker_params = dict(cfg.broker.params)
    broker_params.setdefault("initial_cash", cfg.initial_cash)
    broker = build_broker(cfg.broker.name, broker_params)

    engine = TradingEngine(cfg.symbol, strategy, broker, risk)
    candles = _candles_from_args(args)
    engine.run(candles)

    last = candles[-1].close if candles else Decimal("0")
    print("\n=== ペーパートレード終了 ===")
    print(f"現金       : {broker.cash:,.2f}")
    print(f"有効証拠金 : {broker.equity({cfg.symbol: last}):,.2f}")
    open_pos = broker.get_position(cfg.symbol)
    if open_pos:
        print(f"建玉       : {open_pos.side.value} {open_pos.units} @ {open_pos.entry_price}")
    trades = getattr(broker, "trades", [])
    print(f"約定トレード数: {len(trades)}")
    return 0


def cmd_ui(args) -> int:
    from .webui import serve

    serve(host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_live(args) -> int:
    from .livesite import serve as serve_live

    token = args.token or os.environ.get("FXTRADE_LIVE_TOKEN", "")
    if not token:
        print(
            "エラー: 公開トークンが必要です。\n"
            "  例) python3 -m fxtrade live --token あなたの秘密の文字列\n"
            "  または環境変数 FXTRADE_LIVE_TOKEN に設定してください。",
            file=sys.stderr,
        )
        return 1
    serve_live(host=args.host, port=args.port, token=token, title=args.title)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fxtrade", description="価格と％で売買するFX自動売買ツール")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("gen-data", help="検証用の合成データ(CSV)を生成")
    g.add_argument("--out", default="data/sample.csv")
    g.add_argument("--n", type=int, default=500)
    g.add_argument("--start-price", dest="start_price", type=float, default=148.0)
    g.add_argument("--seed", type=int, default=42)
    g.set_defaults(func=cmd_gen_data)

    b = sub.add_parser("backtest", help="戦略をバックテスト")
    b.add_argument("--config", default=None, help="設定ファイル(.yaml/.json)")
    b.add_argument("--csv", default=None, help="ヒストリカルCSV。未指定なら合成データ")
    b.add_argument("--symbol", default=None)
    b.add_argument("--n", type=int, default=500, help="合成データの本数")
    b.add_argument("--seed", type=int, default=42)
    b.add_argument("--show-trades", action="store_true")
    b.set_defaults(func=cmd_backtest)

    pp = sub.add_parser("paper", help="ペーパートレード(デモ)を実行")
    pp.add_argument("--config", default=None)
    pp.add_argument("--csv", default=None)
    pp.add_argument("--symbol", default=None)
    pp.add_argument("--n", type=int, default=500)
    pp.add_argument("--seed", type=int, default=42)
    pp.set_defaults(func=cmd_paper)

    ui = sub.add_parser("ui", help="ブラウザで使うデモトレードUIを起動")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8000)
    ui.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    ui.set_defaults(func=cmd_ui)

    lv = sub.add_parser("live", help="ライブ配信サイトを起動 (MT4のEAから状況を受信して公開)")
    lv.add_argument("--host", default="0.0.0.0")
    lv.add_argument("--port", type=int, default=8080)
    lv.add_argument("--token", default=None, help="EAからの送信を認証する秘密の文字列(必須)")
    lv.add_argument("--title", default="FX ライブ配信", help="ページのタイトル")
    lv.set_defaults(func=cmd_live)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
