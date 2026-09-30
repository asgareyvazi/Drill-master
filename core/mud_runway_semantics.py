"""Operational runway semantics for the mud-chemical ledger.

A days-remaining estimate is only calculable from known, nonnegative stock and
an observed *positive* mean usage rate. No positive usage observed is not a
zero-day stockout and does not prove usage will remain zero indefinitely.
"""
from __future__ import annotations

import math
from typing import Any, Optional


def _finite_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def assess_mud_runway(
    closing_stock: Any,
    average_consumption: Any,
    *,
    rate_observed: bool,
) -> dict:
    """Return a numeric runway only when the available facts support one.

    ``rate_observed`` distinguishes an empty history from recorded days whose
    usage is zero. In the BulkMaterials domain, an absent daily movement is the
    established no-movement value (zero); no rows, however, are no history.
    """
    stock = _finite_number(closing_stock)
    rate = _finite_number(average_consumption)

    if closing_stock is None:
        stock_status = "UNKNOWN"
    elif stock is None or stock < 0:
        stock_status = "INVALID"
    else:
        stock_status = "KNOWN"

    if not rate_observed:
        rate_status = "NO_HISTORY"
    elif average_consumption is None:
        rate_status = "UNKNOWN"
    elif rate is None or rate < 0:
        rate_status = "INVALID"
    elif rate == 0:
        rate_status = "KNOWN_ZERO"
    else:
        rate_status = "KNOWN_POSITIVE"

    days_remaining = None
    if stock_status == "INVALID":
        runway_status = "INVALID_STOCK"
    elif rate_status == "INVALID":
        runway_status = "INVALID_CONSUMPTION_RATE"
    elif stock_status == "UNKNOWN":
        runway_status = "UNKNOWN_STOCK"
    elif rate_status == "NO_HISTORY":
        runway_status = "NO_CONSUMPTION_HISTORY"
    elif rate_status == "UNKNOWN":
        runway_status = "CONSUMPTION_RATE_UNKNOWN"
    elif rate_status == "KNOWN_ZERO":
        runway_status = "NO_DEPLETION_RATE_OBSERVED"
    else:
        # A known zero stock and positive recorded consumption truthfully yields
        # zero days; positive stock with zero observed usage does not. Guard the
        # derived value too: finite operands can still overflow on division.
        candidate = stock / rate
        if math.isfinite(candidate):
            days_remaining = candidate
            runway_status = "CALCULATED"
        else:
            runway_status = "RUNWAY_UNREPRESENTABLE"

    return {
        "days_remaining": days_remaining,
        "stock_status": stock_status,
        "consumption_rate_status": rate_status,
        "days_remaining_status": runway_status,
    }
