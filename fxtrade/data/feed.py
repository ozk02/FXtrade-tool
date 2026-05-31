"""マーケットデータ供給のインターフェース。"""

from __future__ import annotations

from typing import Iterable, Iterator, Protocol

from ..models import Candle


class MarketDataFeed(Protocol):
    """ローソク足を時系列順に返すデータ供給源。

    バックテストでもライブでも同じインターフェースで扱えるようにする。
    """

    def candles(self) -> Iterable[Candle]:
        ...


class IterableFeed:
    """任意の Candle イテラブルをラップする最小実装。"""

    def __init__(self, candles: Iterable[Candle]):
        self._candles = list(candles)

    def candles(self) -> Iterator[Candle]:
        return iter(self._candles)

    def __len__(self) -> int:
        return len(self._candles)
