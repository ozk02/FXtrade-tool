"""CSV からヒストリカルデータを読み込むフィード。

想定フォーマット（ヘッダ行あり）::

    timestamp,open,high,low,close,volume
    2024-01-01T00:00:00,148.10,148.30,148.00,148.25,1000

timestamp は ISO 8601。volume 列は省略可能。
"""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
from typing import Iterator, List

from ..models import Candle


class CSVFeed:
    def __init__(self, path: str):
        self.path = path
        self._candles: List[Candle] = self._load()

    def _load(self) -> List[Candle]:
        out: List[Candle] = []
        with open(self.path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = _parse_ts(row["timestamp"])
                vol = row.get("volume") or "0"
                out.append(
                    Candle.from_row(
                        ts,
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        vol,
                    )
                )
        out.sort(key=lambda c: c.timestamp)
        return out

    def candles(self) -> Iterator[Candle]:
        return iter(self._candles)

    def __len__(self) -> int:
        return len(self._candles)


def _parse_ts(value: str) -> datetime:
    value = value.strip()
    # よくある形式を順に試す。
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    # ISO 8601 のフォールバック（タイムゾーン付きなど）。
    return datetime.fromisoformat(value)


def write_csv(path: str, candles: List[Candle]) -> None:
    """Candle のリストを CSV に書き出す（サンプルデータ生成用）。"""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for c in candles:
            writer.writerow(
                [
                    c.timestamp.isoformat(),
                    c.open,
                    c.high,
                    c.low,
                    c.close,
                    c.volume,
                ]
            )
