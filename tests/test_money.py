"""Decimal-safe money helpers and the cost-summary correction (M43)."""
from __future__ import annotations

import copy
import decimal
import json
import math
from decimal import Decimal

import pytest

from core.cost_semantics import complete_total, format_money, summarize_costs
from core.engineering.result import EngineeringError
from core.money import MAX_MINOR_UNITS, sum_money, to_decimal, to_minor_units


# ---------------------------------------------------------------- to_decimal

@pytest.mark.parametrize("value, expected", [
    (0.1, Decimal("0.1")), (0.3, Decimal("0.3")), (2.675, Decimal("2.675")), (-12.5, Decimal("-12.5")),
    (0, Decimal(0)), (0.0, Decimal("0.0")), (-0.0, Decimal("-0.0")), (7, Decimal(7)),
    (1e15, Decimal("1000000000000000.0")), (5e-324, Decimal("5e-324")),
    (" 12.50 ", Decimal("12.50")), ("1e3", Decimal("1E+3")), (Decimal("3.14"), Decimal("3.14")),
])
def test_to_decimal_is_the_shortest_round_trip_decimal(value, expected):
    result = to_decimal(value)
    assert result == expected
    if isinstance(value, float):
        assert float(result) == value  # nothing lost relative to the stored float


@pytest.mark.parametrize("value", [None, ""])
def test_to_decimal_keeps_unknown_unknown(value):
    assert to_decimal(value) is None


@pytest.mark.parametrize("value", [True, False, "abc", "1,000", "nan", "inf", float("nan"), float("inf"),
                                   -math.inf, Decimal("NaN"), Decimal("Infinity"), [1], object()])
def test_invalid_and_non_finite_amounts_raise_the_existing_error_type(value):
    with pytest.raises(EngineeringError):
        to_decimal(value)


# ---------------------------------------------------------------- sum_money

def _float_accumulate(values):
    """Plain left-to-right binary float addition.

    Not the built-in ``sum``: from Python 3.12 it compensates float rounding
    (Neumaier), so its results differ between supported versions.
    """
    total = 0.0
    for value in values:
        total += value
    return total


def test_binary_float_accumulation_is_removed():
    assert _float_accumulate([0.1, 0.2]) != 0.3 and sum_money([0.1, 0.2]) == 0.3
    assert _float_accumulate([0.1] * 10) != 1.0 and sum_money([0.1] * 10) == 1.0
    assert sum_money([1_000_000.10, 0.20]) == 1_000_000.30
    assert sum_money([0.1, -0.1, 0.3, -0.3]) == 0.0


def test_sum_money_keeps_the_complete_total_contract_and_float_type():
    for values in ([], [1.0, None], [None]):
        assert sum_money(values) is None and complete_total(values) is None
    result = sum_money([10, 2.5, Decimal("0.25"), "1.25"])
    assert type(result) is float and result == 14.0
    for values in ([12.34, 56.78], [1e6, 2e6, 3.5], [100, -40.25]):
        assert sum_money(values) == pytest.approx(complete_total(values), rel=1e-15)


def test_sum_money_handles_extreme_magnitudes_exactly():
    assert sum_money([1e300, 1e-300]) == 1e300
    assert sum_money([9_007_199_254_740_993, 0]) == float(9_007_199_254_740_993)
    with pytest.raises(EngineeringError):
        sum_money([1e308, 1e308])  # overflows float: refused, never inf


def test_sum_money_rejects_invalid_members():
    with pytest.raises(EngineeringError):
        sum_money([1.0, float("nan")])
    with pytest.raises(EngineeringError):
        sum_money([1.0, True])


# ---------------------------------------------------------------- minor units

@pytest.mark.parametrize("value, rounding, expected", [
    (2.675, decimal.ROUND_HALF_UP, (268, False)),
    (2.665, decimal.ROUND_HALF_UP, (267, False)),
    (2.665, decimal.ROUND_HALF_EVEN, (266, False)),
    (2.675, decimal.ROUND_HALF_EVEN, (268, False)),
    (-2.665, decimal.ROUND_HALF_UP, (-267, False)),
    (-2.665, decimal.ROUND_HALF_EVEN, (-266, False)),
    (12.5, decimal.ROUND_HALF_UP, (1250, True)),
    (0, decimal.ROUND_HALF_EVEN, (0, True)),
    ("0.005", decimal.ROUND_DOWN, (0, False)),
])
def test_minor_units_use_the_explicit_rule_and_report_inexact_conversions(value, rounding, expected):
    assert to_minor_units(value, scale=2, rounding=rounding) == expected


def test_minor_units_validate_rule_scale_and_range():
    assert to_minor_units(None, scale=2, rounding=decimal.ROUND_HALF_EVEN) is None
    with pytest.raises(ValueError):
        to_minor_units(1.0, scale=2, rounding="nearest")
    for scale in (-1, 7, 2.0, True):
        with pytest.raises(ValueError):
            to_minor_units(1.0, scale=scale, rounding=decimal.ROUND_HALF_EVEN)
    assert to_minor_units(Decimal(MAX_MINOR_UNITS), scale=0, rounding=decimal.ROUND_HALF_EVEN) == (MAX_MINOR_UNITS, True)
    with pytest.raises(EngineeringError):
        to_minor_units(1e17, scale=2, rounding=decimal.ROUND_HALF_EVEN)


# ---------------------------------------------------------------- cost summary

def _rows(pairs, currency="USD"):
    return [{"currency": currency, "category": "Rig", "planned_cost": p, "actual_cost": a} for p, a in pairs]


def test_exactly_on_budget_totals_have_zero_variance_not_negative_residue():
    rows = _rows([(0.3, 0.1), (0.0, 0.2)])
    snapshot = copy.deepcopy(rows)
    totals = summarize_costs(rows)
    assert totals["total_planned"] == totals["total_actual"] == 0.3
    assert totals["variance"] == 0.0 and not math.copysign(1, totals["variance"]) < 0
    assert format_money(totals["variance"], "USD") == "USD 0.00"
    assert totals["groups"][0]["variance"] == 0.0
    assert rows == snapshot  # summarizing never mutates the records


def test_cost_summary_contract_is_otherwise_unchanged():
    assert summarize_costs([])["status"] == "no-records"
    unknown = summarize_costs(_rows([(1.0, 2.0)], currency=None))
    assert unknown["status"] == "unknown-currency" and unknown["total_planned"] is None
    mixed = summarize_costs(_rows([(1.0, 2.0)]) + _rows([(1.0, 2.0)], currency="EUR"))
    assert mixed["status"] == "multi-currency" and mixed["total_actual"] is None
    incomplete = summarize_costs(_rows([(1.0, None), (2.0, 3.0)]))
    assert incomplete["total_planned"] == 3.0 and incomplete["total_actual"] is None
    assert incomplete["variance"] is None
    under = summarize_costs(_rows([(1000.0, 750.25)]))
    assert under["variance"] == 249.75 and type(under["variance"]) is float


def test_display_and_serialization_are_unchanged():
    # Display keeps Python float formatting of the stored binary value.
    assert format_money(2.675, "USD") == "USD 2.67"
    assert format_money(1234567.891, "usd") == "USD 1,234,567.89"
    assert format_money(None, None) == "— (currency unknown)"
    totals = summarize_costs(_rows([(1.1, 2.2)]))
    assert json.loads(json.dumps(totals))["total_planned"] == 1.1
