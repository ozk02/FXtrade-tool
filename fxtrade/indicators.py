"""テクニカル指標（逐次更新版）。

このツールは「足を1本ずつ戦略に渡す」設計なので、指標も1本ずつ更新できる形にする。
バックテストとライブで同じ計算結果になり、過去データ全体を持ち回る必要もない。
外部ライブラリ不要（標準ライブラリのみ）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


class SMA:
    """単純移動平均。"""

    def __init__(self, period: int):
        if period < 1:
            raise ValueError("period must be >= 1")
        self.period = int(period)
        self._buf: List[Decimal] = []
        self.value: Optional[Decimal] = None

    def update(self, price) -> Optional[Decimal]:
        self._buf.append(_dec(price))
        if len(self._buf) > self.period:
            self._buf.pop(0)
        if len(self._buf) == self.period:
            self.value = sum(self._buf) / Decimal(self.period)
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class EMA:
    """指数移動平均。最初の period 本の単純平均を初期値(シード)にする。"""

    def __init__(self, period: int):
        if period < 1:
            raise ValueError("period must be >= 1")
        self.period = int(period)
        self.k = Decimal(2) / (Decimal(self.period) + Decimal(1))
        self._seed: List[Decimal] = []
        self.value: Optional[Decimal] = None

    def update(self, price) -> Optional[Decimal]:
        p = _dec(price)
        if self.value is None:
            self._seed.append(p)
            if len(self._seed) == self.period:
                self.value = sum(self._seed) / Decimal(self.period)
            return self.value
        self.value = (p - self.value) * self.k + self.value
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


def make_ma(kind: str, period: int):
    """設定文字列から移動平均を生成する。"""
    kind = (kind or "ema").lower()
    if kind == "sma":
        return SMA(period)
    if kind == "ema":
        return EMA(period)
    raise ValueError("ma_type must be 'sma' or 'ema'")


class ADX:
    """Wilder の ADX（平均方向性指数）と +DI / -DI。

    ADX は「トレンドの強さ」を 0〜100 で表す指標で、向きは示さない。
    一般に 25 前後を境に、上ならトレンド相場・下ならレンジ相場と判断される。
    レジーム（相場環境）の判定に使う。

    計算は Wilder の平滑化に従う:
      TR  = max(高値-安値, |高値-前終値|, |安値-前終値|)
      +DM = 高値-前高値 (それが 前安値-安値 より大きく正のとき) それ以外 0
      -DM = 前安値-安値 (それが 高値-前高値 より大きく正のとき) それ以外 0
      +DI = 100 * 平滑(+DM) / 平滑(TR),  -DI も同様
      DX  = 100 * |+DI - -DI| / (+DI + -DI)
      ADX = DX を period 本 Wilder 平滑したもの

    値が確定するまで（およそ period*2 本）は update() が None を返す。
    """

    def __init__(self, period: int = 14):
        if period < 1:
            raise ValueError("period must be >= 1")
        self.period = int(period)
        self._prev_high: Optional[Decimal] = None
        self._prev_low: Optional[Decimal] = None
        self._prev_close: Optional[Decimal] = None
        # ウォームアップ用の蓄積
        self._tr_seed: List[Decimal] = []
        self._pdm_seed: List[Decimal] = []
        self._ndm_seed: List[Decimal] = []
        self._dx_seed: List[Decimal] = []
        # 平滑値
        self._str: Optional[Decimal] = None
        self._spdm: Optional[Decimal] = None
        self._sndm: Optional[Decimal] = None

        self.value: Optional[Decimal] = None
        self.plus_di: Optional[Decimal] = None
        self.minus_di: Optional[Decimal] = None

    @property
    def ready(self) -> bool:
        return self.value is not None

    def update(self, high, low, close) -> Optional[Decimal]:
        h, l, c = _dec(high), _dec(low), _dec(close)

        if self._prev_close is None:
            self._prev_high, self._prev_low, self._prev_close = h, l, c
            return None

        tr = max(h - l, abs(h - self._prev_close), abs(l - self._prev_close))
        up = h - self._prev_high
        down = self._prev_low - l
        zero = Decimal(0)
        pdm = up if (up > down and up > zero) else zero
        ndm = down if (down > up and down > zero) else zero
        self._prev_high, self._prev_low, self._prev_close = h, l, c

        if self._str is None:
            # 最初の period 本を単純合計して平滑値の初期値にする。
            self._tr_seed.append(tr)
            self._pdm_seed.append(pdm)
            self._ndm_seed.append(ndm)
            if len(self._tr_seed) < self.period:
                return None
            self._str = sum(self._tr_seed)
            self._spdm = sum(self._pdm_seed)
            self._sndm = sum(self._ndm_seed)
        else:
            p = Decimal(self.period)
            self._str = self._str - self._str / p + tr
            self._spdm = self._spdm - self._spdm / p + pdm
            self._sndm = self._sndm - self._sndm / p + ndm

        if self._str == 0:
            return self.value

        hundred = Decimal(100)
        self.plus_di = hundred * self._spdm / self._str
        self.minus_di = hundred * self._sndm / self._str
        di_sum = self.plus_di + self.minus_di
        dx = zero if di_sum == 0 else hundred * abs(self.plus_di - self.minus_di) / di_sum

        if self.value is None:
            self._dx_seed.append(dx)
            if len(self._dx_seed) == self.period:
                self.value = sum(self._dx_seed) / Decimal(self.period)
        else:
            p = Decimal(self.period)
            self.value = (self.value * (p - Decimal(1)) + dx) / p

        return self.value
