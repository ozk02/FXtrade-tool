"""楽天証券向けブローカーアダプタ（差込み口）。

重要 / IMPORTANT:
    楽天証券は、リテール向けの公開された FX 用 REST API を（本ツール作成時点で）
    提供していません。プログラムからの自動売買は一般に次のいずれかを介します:

      * MarketSpeed II RSS … Excel(Windows)上の RSS 関数で気配・約定を受け、
        発注関数（RssMarketOrder 等）で発注する仕組み。Windows + Excel + 楽天RSS が必要。
      * MarketSpeed II の画面操作自動化（RPA / UI 自動化）… 非推奨かつ規約要確認。

    したがって本クラスは「実発注ロジックを安全に差し込むためのテンプレート」であり、
    既定では NotImplementedError を投げて誤発注を防ぎます。実際に接続する場合は、
    利用規約・約款を必ず確認のうえ、_place_order などを各自の連携方式で実装してください。

    まずは PaperBroker（broker.name = "paper"）でバックテスト/デモ検証することを推奨します。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from ..models import Fill, Order, Position


class RakutenBroker:
    def __init__(
        self,
        bridge: str = "marketspeed_rss",
        dry_run: bool = True,
        **kwargs,
    ):
        """
        bridge: 連携方式の識別子（例: "marketspeed_rss"）。
        dry_run: True の間は実発注せずログのみ（安全側の既定）。
        kwargs: 接続情報（RSS の参照セル、口座番号など）を受け取る余地。
        """
        self.bridge = bridge
        self.dry_run = dry_run
        self.options = kwargs
        self._positions: Dict[str, Position] = {}
        self._cash = Decimal(str(kwargs.get("initial_cash", 0)))

    # --- 公開インターフェース（Broker プロトコル） -----------------------------

    def submit(self, order: Order, price: Decimal, timestamp) -> Fill:
        if self.dry_run:
            # 実発注しない。ログ目的の擬似約定を返す。
            return Fill(order=order, price=Decimal(str(price)), units=order.units, timestamp=timestamp)
        return self._place_order(order, price, timestamp)

    def get_position(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    def positions(self) -> List[Position]:
        return list(self._positions.values())

    @property
    def cash(self) -> Decimal:
        return self._cash

    def equity(self, mark_prices: Dict[str, Decimal]) -> Decimal:
        eq = self._cash
        for sym, pos in self._positions.items():
            mark = mark_prices.get(sym)
            if mark is not None:
                eq += pos.unrealized_pnl(Decimal(str(mark)))
        return eq

    # --- 実装すべき箇所 -------------------------------------------------------

    def _place_order(self, order: Order, price: Decimal, timestamp) -> Fill:
        """実発注。MarketSpeed II RSS 等への連携をここに実装する。

        例（MarketSpeed II RSS / Windows + Excel COM 経由の擬似コード）::

            # import win32com.client
            # xl = win32com.client.Dispatch("Excel.Application")
            # ws = xl.Workbooks(...).Worksheets(...)
            # ws.Range("発注セル").Value = f"=RssMarketOrder(...)"

        実装するまでは誤発注防止のため例外を送出する。
        """
        raise NotImplementedError(
            "RakutenBroker._place_order は未実装です。"
            "楽天証券には公開FX REST APIが無いため、MarketSpeed II RSS 等の連携を"
            "各自実装してください（dry_run=True での検証を推奨）。"
        )

    def fetch_price(self, symbol: str) -> Decimal:
        """RSS から現在気配を取得する想定の差込み口。"""
        raise NotImplementedError(
            "RakutenBroker.fetch_price は未実装です。RSS等から気配を取得する実装を追加してください。"
        )
