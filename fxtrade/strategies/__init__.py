"""売買戦略。"""

from .base import Strategy, Signal, SignalType
from .price_percent import PricePercentStrategy

# 設定ファイルの strategy.name からクラスを引くためのレジストリ。
REGISTRY = {
    "price_percent": PricePercentStrategy,
}


def build_strategy(name: str, params: dict) -> Strategy:
    if name not in REGISTRY:
        raise ValueError(
            f"unknown strategy '{name}'. available: {', '.join(sorted(REGISTRY))}"
        )
    return REGISTRY[name](**(params or {}))


__all__ = [
    "Strategy",
    "Signal",
    "SignalType",
    "PricePercentStrategy",
    "REGISTRY",
    "build_strategy",
]
