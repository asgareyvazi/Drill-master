"""Runway truth table: known zero use is not a zero-day runway or forecast."""
from __future__ import annotations

import math

import pytest

from core.mud_runway_semantics import assess_mud_runway


@pytest.mark.parametrize(
    ("stock", "rate", "observed", "days", "status"),
    [
        (100.0, 10.0, True, 10.0, "CALCULATED"),
        (10.0, 0.0, True, None, "NO_DEPLETION_RATE_OBSERVED"),
        (10.0, None, False, None, "NO_CONSUMPTION_HISTORY"),
        (None, 10.0, True, None, "UNKNOWN_STOCK"),
        (0.0, 10.0, True, 0.0, "CALCULATED"),
        (0.0, 0.0, True, None, "NO_DEPLETION_RATE_OBSERVED"),
        (-1.0, 1.0, True, None, "INVALID_STOCK"),
        (1.0, math.nan, True, None, "INVALID_CONSUMPTION_RATE"),
        (1e308, 1e-308, True, None, "RUNWAY_UNREPRESENTABLE"),
    ],
)
def test_runway_requires_known_stock_and_positive_observed_rate(
    stock, rate, observed, days, status
):
    result = assess_mud_runway(stock, rate, rate_observed=observed)
    assert result["days_remaining"] == days
    assert result["days_remaining_status"] == status


def test_known_zero_consumption_is_not_reported_as_a_forecast():
    result = assess_mud_runway(30.0, 0.0, rate_observed=True)
    assert result == {
        "days_remaining": None,
        "stock_status": "KNOWN",
        "consumption_rate_status": "KNOWN_ZERO",
        "days_remaining_status": "NO_DEPLETION_RATE_OBSERVED",
    }


def test_legacy_history_helper_uses_the_same_nullable_runway_contract():
    from core.engineering.core import MudLedgerEngine

    history = MudLedgerEngine.build_history([
        {"date": "2026-09-01", "product": "Barite", "used": 0, "closing": 40},
        {"date": "2026-09-02", "product": "Barite", "used": 0, "closing": 40},
    ])
    row = history["Barite"]
    assert row["consumption_rate"] == 0
    assert row["days_remaining"] is None
    assert row["days_remaining_status"] == "NO_DEPLETION_RATE_OBSERVED"
