"""売買戦略。"""

from .base import Strategy, Signal, SignalType
from .price_percent import PricePercentStrategy
from .ma_cross import MACrossStrategy
from .regime import RegimeFilterStrategy

# 設定ファイルの strategy.name からクラスを引くためのレジストリ。
REGISTRY = {
    "price_percent": PricePercentStrategy,   # 逆張り（価格と％）
    "ma_cross": MACrossStrategy,             # 順張り（移動平均クロス）
    "regime": RegimeFilterStrategy,          # ADXで順張り/逆張りを自動切替
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
    "MACrossStrategy",
    "RegimeFilterStrategy",
    "REGISTRY",
    "build_strategy",
]
