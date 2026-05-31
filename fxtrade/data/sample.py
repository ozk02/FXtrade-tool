"""検証用の合成（ランダムウォーク）マーケットデータ生成。

実データが無くてもバックテストやデモを動かせるようにするためのもの。
seed を固定すれば再現性がある。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

from ..models import Candle


def generate_random_walk(
    n: int = 500,
    start_price: float = 148.0,
    volatility: float = 0.15,
    start: datetime | None = None,
    step: timedelta = timedelta(hours=1),
    seed: int | None = 42,
) -> List[Candle]:
    """ランダムウォークで n 本のローソク足を生成する。

    start_price から始め、各足で ±volatility 程度動く。USD/JPY を想定した既定値。
    """
    rng = random.Random(seed)
    start = start or datetime(2024, 1, 1)
    price = start_price
    candles: List[Candle] = []
    ts = start
    for _ in range(n):
        o = price
        # ドリフト無しの正規乱数で変動させる。
        drift = rng.gauss(0, volatility)
        c = max(0.01, o + drift)
        hi = max(o, c) + abs(rng.gauss(0, volatility / 2))
        lo = min(o, c) - abs(rng.gauss(0, volatility / 2))
        vol = rng.randint(500, 2000)
        candles.append(
            Candle.from_row(
                ts,
                round(o, 3),
                round(hi, 3),
                round(lo, 3),
                round(c, 3),
                vol,
            )
        )
        price = c
        ts += step
    return candles
