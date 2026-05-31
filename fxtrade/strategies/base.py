"""戦略の共通インターフェース。

戦略は「現在の足」と「現在ポジションの有無」を受け取り、シグナルを返すだけの
純粋なロジックに保つ。発注・約定・残高管理はエンジン/ブローカー側の責務とする。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from ..models import Candle, Position, Side


class SignalType(enum.Enum):
    HOLD = "HOLD"
    ENTER = "ENTER"   # 新規建て（ノーポジ時）
    ADD = "ADD"       # 増し玉（ナンピン: 同方向に積み増す）
    EXIT = "EXIT"     # 手仕舞い（全決済）


@dataclass
class Signal:
    type: SignalType
    side: Optional[Side] = None  # ENTER / ADD のときの方向
    reason: str = ""
    # ENTER/ADD のロットを基準サイズの何倍にするか（ナンピンのマーチンゲール等に使う）。
    size_mult: Decimal = Decimal("1")

    @classmethod
    def hold(cls) -> "Signal":
        return cls(SignalType.HOLD)

    @classmethod
    def enter(cls, side: Side, reason: str = "", size_mult=Decimal("1")) -> "Signal":
        return cls(SignalType.ENTER, side=side, reason=reason, size_mult=Decimal(str(size_mult)))

    @classmethod
    def add(cls, side: Side, reason: str = "", size_mult=Decimal("1")) -> "Signal":
        return cls(SignalType.ADD, side=side, reason=reason, size_mult=Decimal(str(size_mult)))

    @classmethod
    def exit(cls, reason: str = "") -> "Signal":
        return cls(SignalType.EXIT, reason=reason)


class Strategy:
    """戦略の基底クラス。"""

    name = "base"

    def on_candle(self, candle: Candle, position: Optional[Position]) -> Signal:
        """各足ごとに呼ばれる。シグナルを返す。"""
        raise NotImplementedError

    def reset(self) -> None:
        """バックテストを複数回回す際などに内部状態を初期化する。"""
        pass
