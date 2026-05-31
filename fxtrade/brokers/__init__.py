"""ブローカー（発注先）アダプタ。

paper: シミュレーション用の仮想ブローカー（即時約定）。
rakuten: 楽天証券向けアダプタの差込み口（実発注は環境依存・要資格情報）。
"""

from .base import Broker
from .paper import PaperBroker


def build_broker(name: str, params: dict):
    name = (name or "paper").lower()
    if name == "paper":
        return PaperBroker(**(params or {}))
    if name == "rakuten":
        # 実発注アダプタは重い依存を持ちうるため遅延 import する。
        from .rakuten import RakutenBroker

        return RakutenBroker(**(params or {}))
    raise ValueError(f"unknown broker '{name}'. available: paper, rakuten")


__all__ = ["Broker", "PaperBroker", "build_broker"]
