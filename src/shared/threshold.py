"""Threshold comparison logic used by the Matching Engine.

Evaluates whether a weather value triggers a user's alert rule.
Operators are validated as Enum at the API layer, but we also handle
unknown operators from DB (direct inserts, migrations) gracefully.
"""

import logging
from decimal import Decimal

from src.models.alert_rule import Operator

logger = logging.getLogger(__name__)


def evaluate_threshold(operator_str: str, weather_value: float, threshold: float) -> bool:
    """Return True if the weather_value triggers the rule."""
    try:
        op = Operator(operator_str)
    except ValueError:
        logger.error("Unknown operator in DB: %s, skipping rule", operator_str)
        return False

    # Use Decimal for precise comparison to avoid float issues
    wv = Decimal(str(weather_value))
    tv = Decimal(str(threshold))

    if op == Operator.GT:
        return wv > tv
    elif op == Operator.GTE:
        return wv >= tv
    elif op == Operator.LT:
        return wv < tv
    elif op == Operator.LTE:
        return wv <= tv
    elif op == Operator.EQ:
        return wv == tv

    return False
