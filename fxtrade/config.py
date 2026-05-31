"""設定の読み込み。

YAML が使える環境では YAML を、無ければ JSON を読む。
外部依存を避けるため PyYAML が無くても JSON で完結できるようにしてある。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict


@dataclass
class StrategyConfig:
    name: str = "price_percent"
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskConfig:
    # 1トレードで取るリスク（口座残高に対する割合, %）
    risk_per_trade_pct: Decimal = Decimal("1.0")
    # 1ポジションの最大ロット（通貨単位）
    max_units: Decimal = Decimal("100000")
    # 同時に持てる最大ポジション数
    max_positions: int = 1


@dataclass
class BrokerConfig:
    name: str = "paper"  # paper | rakuten
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    symbol: str = "USD_JPY"
    initial_cash: Decimal = Decimal("1000000")
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    broker: BrokerConfig = field(default_factory=BrokerConfig)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Config":
        d = dict(d or {})
        strat = d.get("strategy", {}) or {}
        risk = d.get("risk", {}) or {}
        broker = d.get("broker", {}) or {}

        def dec(v, default):
            return Decimal(str(v)) if v is not None else default

        risk_cfg = RiskConfig(
            risk_per_trade_pct=dec(risk.get("risk_per_trade_pct"), Decimal("1.0")),
            max_units=dec(risk.get("max_units"), Decimal("100000")),
            max_positions=int(risk.get("max_positions", 1)),
        )
        return cls(
            symbol=d.get("symbol", "USD_JPY"),
            initial_cash=dec(d.get("initial_cash"), Decimal("1000000")),
            strategy=StrategyConfig(
                name=strat.get("name", "price_percent"),
                params=strat.get("params", {}) or {},
            ),
            risk=risk_cfg,
            broker=BrokerConfig(
                name=broker.get("name", "paper"),
                params=broker.get("params", {}) or {},
            ),
        )

    @classmethod
    def load(cls, path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        data = _parse(text, path)
        return cls.from_dict(data)


def _parse(text: str, path: str) -> Dict[str, Any]:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore

            return yaml.safe_load(text) or {}
        except ImportError:
            # PyYAML 不在時のフォールバック: ごく単純な YAML サブセットを JSON 的に解釈する。
            return _mini_yaml(text)
    return json.loads(text)


def _mini_yaml(text: str) -> Dict[str, Any]:
    """インデントベースの最小限 YAML パーサ（このプロジェクトの設定形式のみ対応）。

    PyYAML が無い環境でも example 設定を読めるようにするための簡易実装。
    複雑な YAML には対応しないので、必要なら JSON 設定を使うこと。
    """
    root: Dict[str, Any] = {}
    stack = [(-1, root)]

    def coerce(v: str) -> Any:
        v = v.strip()
        if v == "":
            return {}
        if v.lower() in ("true", "false"):
            return v.lower() == "true"
        if v.lower() in ("null", "~"):
            return None
        try:
            if "." in v or "e" in v.lower():
                return float(v)
            return int(v)
        except ValueError:
            return v.strip("'\"")

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key, _, val = line.strip().partition(":")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        if val.strip() == "":
            child: Dict[str, Any] = {}
            parent[key.strip()] = child
            stack.append((indent, child))
        else:
            parent[key.strip()] = coerce(val)
    return root
