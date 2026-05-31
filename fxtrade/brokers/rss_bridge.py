"""MarketSpeed II RSS との橋渡し（Excel 連携）。

MarketSpeed II RSS は Windows 上の Excel アドインとして動作する。本モジュールは
Excel ワークシートに対する「セルの読み書き」と「VBA マクロ実行」を抽象化した
RSSBridge を定義し、実機用 (ExcelRSSBridge) とテスト用 (FakeRSSBridge) を提供する。

RSS の使い方の前提:
  * 気配取得 … セルに RSS のマーケット関数（例: =RssMarket("USDJPY","現在値")）を入れ、
    自動更新される値を読む。読み取りのみなので安全。
  * 発注       … セル関数で発注すると再計算で誤発注しうるため、RSS 公式でも
    VBA マクロから発注 API を呼ぶ方式が推奨される。本ツールは「パラメータをセルに書く →
    ユーザーの発注マクロを Application.Run で実行 → 結果セルを読む」という境界で連携する。

実機 (ExcelRSSBridge) は xlwings もしくは pywin32(win32com) が必要で Windows 専用。
依存は遅延 import するため、Linux 上でもこのモジュール自体の import は成功する。
"""

from __future__ import annotations

import time
from typing import Any, Protocol


class RSSBridge(Protocol):
    def get(self, cell: str) -> Any: ...
    def set(self, cell: str, value: Any) -> None: ...
    def run_macro(self, name: str, *args: Any) -> Any: ...
    def close(self) -> None: ...


class ExcelRSSBridge:
    """xlwings 優先・win32com フォールバックで動く実機用ブリッジ（Windows 専用）。

    workbook を指定すればそのブックを開き、未指定ならアクティブブックを使う。
    MarketSpeed II と RSS アドインが起動・有効化されている必要がある。
    """

    def __init__(self, workbook: str | None = None, sheet: str = "Sheet1", visible: bool = True):
        self._backend = None
        self._book = None
        self._sheet = None
        self._sheet_name = sheet
        self._init_backend(workbook, sheet, visible)

    def _init_backend(self, workbook, sheet, visible):
        # 1) xlwings（推奨: API がクリーン）
        try:
            import xlwings as xw  # type: ignore

            self._backend = "xlwings"
            self._xw = xw
            self._book = xw.Book(workbook) if workbook else xw.books.active
            self._book.app.visible = visible
            self._sheet = self._book.sheets[sheet]
            return
        except ImportError:
            pass

        # 2) pywin32 / win32com フォールバック
        try:
            import win32com.client  # type: ignore

            self._backend = "win32com"
            app = win32com.client.GetActiveObject("Excel.Application")
            app.Visible = visible
            wb = None
            if workbook:
                wb = app.Workbooks.Open(workbook)
            else:
                wb = app.ActiveWorkbook
            self._app = app
            self._book = wb
            self._sheet = wb.Worksheets(sheet)
            return
        except Exception as exc:  # pragma: no cover - 実機依存
            raise RuntimeError(
                "Excel への接続に失敗しました。Windows 上で MarketSpeed II / RSS と "
                "Excel を起動し、xlwings か pywin32 をインストールしてください。"
            ) from exc

    def get(self, cell: str) -> Any:
        if self._backend == "xlwings":
            return self._sheet.range(cell).value
        return self._sheet.Range(cell).Value

    def set(self, cell: str, value: Any) -> None:
        if self._backend == "xlwings":
            self._sheet.range(cell).value = value
        else:
            self._sheet.Range(cell).Value = value

    def run_macro(self, name: str, *args: Any) -> Any:
        if self._backend == "xlwings":
            return self._book.macro(name)(*args)
        return self._app.Run(name, *args)

    def close(self) -> None:  # pragma: no cover - 実機依存
        pass


class FakeRSSBridge:
    """テスト/オフライン検証用の擬似ブリッジ。

    セルを辞書として保持する。発注マクロ実行時の挙動は order_handler に委譲でき、
    既定では「ステータスセルに成功を書き、約定価格セルに参照価格を書く」動作をする。
    quotes に {セル名: 値 or callable} を渡すと、その値を返す気配を模擬できる。
    """

    def __init__(self, quotes: dict | None = None, order_handler=None):
        self.cells: dict[str, Any] = {}
        self._quotes = quotes or {}
        self._order_handler = order_handler
        self.macro_calls: list[tuple] = []

    def get(self, cell: str) -> Any:
        if cell in self._quotes:
            q = self._quotes[cell]
            return q(self.cells) if callable(q) else q
        return self.cells.get(cell)

    def set(self, cell: str, value: Any) -> None:
        self.cells[cell] = value

    def run_macro(self, name: str, *args: Any) -> Any:
        self.macro_calls.append((name, args))
        if self._order_handler is not None:
            return self._order_handler(self, name, args)
        return None

    def close(self) -> None:
        pass


def poll(read, predicate, interval: float = 0.3, timeout: float = 10.0, sleep=time.sleep):
    """read() の戻り値が predicate を満たすまで待ち、その値を返す。

    RSS の気配更新やマクロの非同期完了を待つために使う。timeout で例外。
    sleep は注入可能（テストでは即時化）。
    """
    deadline = time.monotonic() + timeout
    while True:
        value = read()
        if predicate(value):
            return value
        if time.monotonic() >= deadline:
            raise TimeoutError("RSS 応答がタイムアウトしました")
        sleep(interval)
