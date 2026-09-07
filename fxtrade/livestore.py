"""ライブ配信用の状態ストア。

MT4のEAから送られてくる口座状況（残高・建玉・損益）を保持し、
公開ページに渡すためのスナップショットを作る。

方針:
  * 受信データは**信用しない**。ホワイトリストした項目だけを型変換して取り込む。
  * 口座番号は末尾4桁だけ残す（公開ページに晒さないため）。
  * 時刻はサーバー受信時刻を使う（送信側の時計を信用しない）。
  * 履歴は上限付きリングバッファ。無制限に溜めない。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

# 受信を受け付ける上限（DoS/事故対策）
MAX_POSITIONS = 50
MAX_STR = 64
# これを過ぎたら「オフライン」表示にする秒数
OFFLINE_AFTER_SEC = 120


def _num(v, default=0.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    # NaN / inf はJSONにできないので弾く
    if f != f or f in (float("inf"), float("-inf")):
        return default
    return f


def _text(v, limit=MAX_STR) -> str:
    if v is None:
        return ""
    return str(v)[:limit]


def mask_account(value) -> str:
    """口座番号は末尾4桁だけ見せる。"""
    s = _text(value, 32)
    if len(s) <= 4:
        return "*" * len(s)
    return "*" * (len(s) - 4) + s[-4:]


def normalize(payload: Dict[str, Any]) -> Dict[str, Any]:
    """受信JSONを、公開してよい形に正規化する。"""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")

    positions: List[Dict[str, Any]] = []
    raw_positions = payload.get("positions") or []
    if isinstance(raw_positions, list):
        for p in raw_positions[:MAX_POSITIONS]:
            if not isinstance(p, dict):
                continue
            side = _text(p.get("side"), 8).upper()
            positions.append(
                {
                    "side": side if side in ("BUY", "SELL") else "?",
                    "symbol": _text(p.get("symbol"), 16),
                    "lots": _num(p.get("lots")),
                    "open_price": _num(p.get("open_price")),
                    "profit": _num(p.get("profit")),
                }
            )

    return {
        "account": mask_account(payload.get("account")),
        "broker": _text(payload.get("broker")),
        "symbol": _text(payload.get("symbol"), 16),
        "currency": _text(payload.get("currency"), 8),
        "balance": _num(payload.get("balance")),
        "equity": _num(payload.get("equity")),
        "margin_level": _num(payload.get("margin_level")),
        "profit_open": _num(payload.get("profit_open")),
        "profit_today": _num(payload.get("profit_today")),
        "trades_today": int(_num(payload.get("trades_today"))),
        "regime": _text(payload.get("regime"), 16),
        "note": _text(payload.get("note"), 120),
        "positions": positions,
    }


class LiveStore:
    """最新状態と資産推移履歴を保持する（スレッドセーフ）。"""

    def __init__(self, max_history: int = 2880):
        self._lock = threading.Lock()
        self._latest: Optional[Dict[str, Any]] = None
        self._updated_at: float = 0.0
        self._history: deque = deque(maxlen=max_history)

    def update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = normalize(payload)
        now = time.time()
        with self._lock:
            self._latest = data
            self._updated_at = now
            self._history.append({"t": now, "equity": data["equity"], "balance": data["balance"]})
        return data

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            latest = dict(self._latest) if self._latest else None
            updated_at = self._updated_at
            history = list(self._history)
        if latest is None:
            return {"online": False, "waiting": True, "latest": None, "history": []}
        age = time.time() - updated_at
        return {
            "online": age <= OFFLINE_AFTER_SEC,
            "waiting": False,
            "age_sec": round(age, 1),
            "updated_at": updated_at,
            "latest": latest,
            "history": history,
        }

    def clear(self) -> None:
        with self._lock:
            self._latest = None
            self._updated_at = 0.0
            self._history.clear()
