"""楽天証券 MarketSpeed II RSS 連携ブローカー（具体実装）。

== 重要 / IMPORTANT =========================================================
* MarketSpeed II RSS は **Windows + Excel + MarketSpeed II** が前提のアドインです。
  本ブローカーは Excel 経由（xlwings / pywin32）でセル読み書き・マクロ実行を行います。
* **気配取得**は RSS のマーケット関数をセルに入れて値を読む安全な方式です。
* **発注**は、誤発注防止のため「パラメータをセルに書く → ユーザーの VBA 発注マクロを
  実行 → 結果セルを読む」という境界で連携します（VBA マクロ例は README 参照）。
* RSS の **発注対象は国内株式・先物等**で、楽天FX(店頭FX)の自動発注の可否は契約・規約に
  依存します。関数名・セル位置・売買区分コードは環境差があるため **CellMap で設定可能**に
  してあります。必ず公式の「MARKETSPEED II RSS 関数リファレンス」で確認してください。
* 既定は `dry_run=True`（実発注しない）。十分な検証後に明示的に False にしてください。
  投資は自己責任です。
============================================================================
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from ..models import Fill, Order, OrderType, Position, Side
from .position_book import PositionBook
from .rss_bridge import FakeRSSBridge, RSSBridge, poll

logger = logging.getLogger("fxtrade.broker.rakuten")


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


@dataclass
class RSSCellMap:
    """Excel シート上の連携セル配置。各自のシートに合わせて設定する。

    quote_formula_template には {code} が使え、quote_code_cell に書いた銘柄コードを
    参照する RSS 関数文字列を指定する。関数名はバージョンにより異なるため要確認。
    """

    # --- 気配取得 ---
    quote_code_cell: str = "B1"
    quote_value_cell: str = "B2"
    quote_formula_template: str = '=RssMarket({code},"現在値")'
    # bid/ask を分けて使う場合（任意）
    bid_cell: Optional[str] = None
    ask_cell: Optional[str] = None

    # --- 発注パラメータ書き込み先 ---
    order_code_cell: str = "E1"
    order_side_cell: str = "E2"
    order_qty_cell: str = "E3"
    order_type_cell: str = "E4"
    order_price_cell: str = "E5"
    # --- 発注トリガと結果 ---
    order_macro: str = "RssSendOrder"   # ユーザー定義の VBA 発注マクロ名
    order_status_cell: str = "E6"       # マクロが結果(成功/失敗)を書くセル
    fill_price_cell: str = "E7"         # 約定価格（取得できれば）
    order_id_cell: str = "E8"           # 注文番号（取得できれば）

    # --- コード/区分のマッピング ---
    # symbol -> RSS銘柄コード（例: {"USD_JPY": "USDJPY"} や 株式なら証券コード）
    symbol_codes: Dict[str, str] = field(default_factory=dict)
    buy_code: Any = "BUY"               # 売買区分(買)。株式RSSなら数値コード等に変更。
    sell_code: Any = "SELL"             # 売買区分(売)
    market_type: Any = "MARKET"
    limit_type: Any = "LIMIT"
    # マクロ成功を示すステータス値（いずれかに一致で成功扱い）
    success_tokens: tuple = ("OK", "DONE", "SUCCESS", "約定", "受付")


class RakutenBroker:
    def __init__(
        self,
        cell_map: Optional[RSSCellMap] = None,
        bridge: Optional[RSSBridge] = None,
        workbook: Optional[str] = None,
        sheet: str = "Sheet1",
        dry_run: bool = True,
        initial_cash: float = 0,
        poll_interval: float = 0.3,
        poll_timeout: float = 10.0,
        **kwargs,
    ):
        # cell_map は dict でも受け取れるようにする（設定ファイル由来）。
        if isinstance(cell_map, dict):
            cell_map = _cellmap_from_dict(cell_map)
        self.cell_map = cell_map or RSSCellMap()
        # symbol_codes をトップレベル指定でも上書きできるようにする。
        if "symbol_codes" in kwargs:
            self.cell_map.symbol_codes.update(kwargs["symbol_codes"])

        self.dry_run = dry_run
        self.workbook = workbook
        self.sheet = sheet
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self._bridge = bridge  # None なら実機接続時に遅延生成
        self._book = PositionBook(initial_cash)

    # --- Broker プロトコル ----------------------------------------------------

    @property
    def cash(self) -> Decimal:
        return self._book.cash

    @property
    def trades(self):
        return self._book.trades

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._book.get(symbol)

    def positions(self) -> List[Position]:
        return self._book.all()

    def equity(self, mark_prices: Dict[str, Decimal]) -> Decimal:
        return self._book.equity(mark_prices)

    def submit(self, order: Order, price: Decimal, timestamp) -> Fill:
        if _dec(order.units) <= 0:
            raise ValueError("order units must be positive")
        if self.dry_run:
            exec_price = _dec(price)
            logger.warning(
                "[DRY-RUN] %s %s %s @ %s (%s) — 実発注しません",
                order.symbol, order.side.value, order.units, exec_price, order.reason,
            )
            self._book.apply_fill(order.symbol, order.side, order.units, exec_price, timestamp, reason=order.reason)
            return Fill(order=order, price=exec_price, units=_dec(order.units), timestamp=timestamp)
        return self._place_order(order, price, timestamp)

    # --- RSS 連携の具体実装 ----------------------------------------------------

    def _get_bridge(self) -> RSSBridge:
        if self._bridge is None:
            from .rss_bridge import ExcelRSSBridge  # 遅延 import（Windows 依存）

            self._bridge = ExcelRSSBridge(workbook=self.workbook, sheet=self.sheet)
        return self._bridge

    def _code(self, symbol: str) -> str:
        return self.cell_map.symbol_codes.get(symbol, symbol)

    def fetch_price(self, symbol: str) -> Decimal:
        """RSS のマーケット関数経由で現在値を取得する。"""
        b = self._get_bridge()
        cm = self.cell_map
        code = self._code(symbol)
        # 銘柄コードを書き、RSS 関数式を値セルへ投入（{code} を実コードに展開）。
        b.set(cm.quote_code_cell, code)
        b.set(cm.quote_value_cell, cm.quote_formula_template.format(code=_quote(code)))
        # RSS は非同期更新のため、数値が入るまで待つ。
        value = poll(
            lambda: b.get(cm.quote_value_cell),
            _is_number,
            interval=self.poll_interval,
            timeout=self.poll_timeout,
        )
        return _to_decimal(value)

    def fetch_bid_ask(self, symbol: str) -> tuple[Optional[Decimal], Optional[Decimal]]:
        """bid/ask セルが設定されていれば取得する（任意）。"""
        cm = self.cell_map
        if not cm.bid_cell or not cm.ask_cell:
            return None, None
        b = self._get_bridge()
        bid = _to_decimal(b.get(cm.bid_cell)) if _is_number(b.get(cm.bid_cell)) else None
        ask = _to_decimal(b.get(cm.ask_cell)) if _is_number(b.get(cm.ask_cell)) else None
        return bid, ask

    def _place_order(self, order: Order, price: Decimal, timestamp) -> Fill:
        """実発注。発注パラメータをセルに書き、VBA 発注マクロを実行して結果を待つ。"""
        b = self._get_bridge()
        cm = self.cell_map
        code = self._code(order.symbol)
        side_code = cm.buy_code if order.side is Side.BUY else cm.sell_code
        type_code = cm.limit_type if order.order_type is OrderType.LIMIT else cm.market_type

        # 発注パラメータを書き込み、前回結果をクリアしてからマクロ起動。
        b.set(cm.order_code_cell, code)
        b.set(cm.order_side_cell, side_code)
        b.set(cm.order_qty_cell, int(order.units))
        b.set(cm.order_type_cell, type_code)
        b.set(cm.order_price_cell, "" if order.order_type is OrderType.MARKET else float(order.limit_price or price))
        b.set(cm.order_status_cell, "")
        b.set(cm.fill_price_cell, "")

        logger.info("RSS 発注: %s %s %s units type=%s", code, order.side.value, int(order.units), type_code)
        b.run_macro(cm.order_macro)

        # マクロが結果を書くまで待つ。
        status = poll(
            lambda: b.get(cm.order_status_cell),
            lambda v: v not in (None, ""),
            interval=self.poll_interval,
            timeout=self.poll_timeout,
        )
        if not _is_success(status, cm.success_tokens):
            raise RuntimeError(f"RSS 発注が失敗しました: status={status!r}")

        # 約定価格は取得できればそれを、無ければ参照価格を使う。
        raw_fill = b.get(cm.fill_price_cell)
        exec_price = _to_decimal(raw_fill) if _is_number(raw_fill) else _dec(price)
        order_id = b.get(cm.order_id_cell)
        logger.info("RSS 約定: status=%s price=%s id=%s", status, exec_price, order_id)

        self._book.apply_fill(order.symbol, order.side, order.units, exec_price, timestamp, reason=order.reason)
        return Fill(order=order, price=exec_price, units=_dec(order.units), timestamp=timestamp)


# --- ヘルパ ------------------------------------------------------------------

def _quote(code: str) -> str:
    """RSS 関数式に埋め込むため、文字列コードはダブルクォートで囲う。"""
    return f'"{code}"'


def _is_number(v) -> bool:
    if v is None or v == "":
        return False
    if isinstance(v, (int, float, Decimal)):
        return True
    try:
        Decimal(str(v))
        return True
    except (InvalidOperation, ValueError):
        return False


def _to_decimal(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _is_success(status, tokens) -> bool:
    s = str(status).strip()
    # 数値の注文番号が返る運用もあるため、数値なら成功扱い。
    if _is_number(status):
        return True
    return any(tok in s for tok in tokens)


def _cellmap_from_dict(d: dict) -> RSSCellMap:
    cm = RSSCellMap()
    for k, v in (d or {}).items():
        if hasattr(cm, k):
            setattr(cm, k, v)
    return cm
