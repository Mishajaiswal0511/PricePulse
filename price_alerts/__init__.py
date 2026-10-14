"""PricePulse: Reliable Price Alert Engine.

A production-grade, dependency-free command-line alert engine for financial price series.
Evaluates level crossings and moving-average crossovers with exact numerical precision.
"""

from price_alerts.data_loader import PriceRecord, load_prices
from price_alerts.rules import BaseRule, LevelRule, MACrossRule, load_rules
from price_alerts.engine import Alert, run_engine

__all__ = [
    "PriceRecord",
    "load_prices",
    "BaseRule",
    "LevelRule",
    "MACrossRule",
    "load_rules",
    "Alert",
    "run_engine",
]
