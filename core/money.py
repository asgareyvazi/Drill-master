"""Decimal-safe helpers for monetary amounts (M43).

Persisted monetary columns are SQLAlchemy ``Float`` (binary floating point):
``cost_records.planned_cost / actual_cost / variance``, ``projects.budget``
and ``npt_reports.cost_impact``. They are NOT converted here; the persisted
representation change is owner-gated (docs/MONEY_MIGRATION.md).

These helpers remove error at calculation boundaries without changing types:

* :func:`to_decimal` - the exact decimal a user typed or a float shows.
  Floats convert through ``repr()`` (the shortest text that round-trips), so
  ``0.1`` becomes ``Decimal("0.1")``, not ``0.1000000000000000055...``.
  Validation is delegated to ``optional_number``, so exactly the inputs the
  cost code already accepts are accepted and the same ``EngineeringError`` is
  raised for booleans, non-numeric text and non-finite values.
* :func:`sum_money` - the complete-total contract of
  ``cost_semantics.complete_total`` (empty or any unknown -> ``None``) with an
  exact decimal sum, returned as the nearest ``float``. Float accumulation
  could make equal planned/actual totals differ in the last bits and show a
  negative "-0.00" variance; the exact sum does not.
* :func:`to_minor_units` - integer minor units for a future fixed-point
  representation. The rounding rule is a required argument: no policy is
  assumed (see the owner decisions in docs/MONEY_MIGRATION.md).

Display rounding is unchanged: ``cost_semantics.format_money`` keeps Python's
float formatting (the exact binary value, so ``2.675`` displays ``2.67``).
"""
from __future__ import annotations

import decimal
from decimal import Decimal
from typing import Iterable, Optional, Tuple

from core.engineering.result import EngineeringError, optional_number, require_number



def _exact_context(amounts) -> decimal.Context:
    """A context wide enough that adding ``amounts`` is exact (never rounds)."""
    finite = [a for a in amounts if a]
    if not finite:
        return decimal.Context(prec=28, traps=[decimal.Inexact])
    high = max(a.adjusted() for a in finite)
    low = min(a.as_tuple().exponent for a in finite)
    digits = high - low + len(finite).bit_length() + 2
    return decimal.Context(prec=max(28, digits), Emax=decimal.MAX_EMAX, Emin=decimal.MIN_EMIN,
                           traps=[decimal.Inexact, decimal.InvalidOperation])

# Range of a signed 64-bit SQLite INTEGER, the target of minor-unit storage.
MAX_MINOR_UNITS = 2 ** 63 - 1


def to_decimal(value, field: str = "amount") -> Optional[Decimal]:
    """Exact ``Decimal`` for an amount, or ``None`` when unknown."""
    number = optional_number(value, field)  # same acceptance/rejection as today
    if number is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        # Untrapped context: text Decimal cannot parse becomes NaN (no raise),
        # and then falls back to the already-validated float's shortest repr.
        parsed = decimal.Context(prec=120, traps=[]).create_decimal(value.strip())
        if parsed.is_finite():
            return parsed
    return Decimal(repr(number))


def sum_money(values: Iterable, field: str = "amount") -> Optional[float]:
    """Complete exact total of amounts; ``None`` if empty or any is unknown."""
    amounts = [to_decimal(v, field) for v in values]
    if not amounts or any(a is None for a in amounts):
        return None
    context = _exact_context(amounts)
    total = Decimal(0)
    for amount in amounts:
        total = context.add(total, amount)
    return require_number(float(total), f"{field} total")


def to_minor_units(value, *, scale: int, rounding: str, field: str = "amount") -> Optional[Tuple[int, bool]]:
    """``(minor_units, exact)`` for ``value`` at ``scale`` decimal places.

    ``rounding`` is one of the ``decimal.ROUND_*`` constants and must be given
    explicitly. ``exact`` is ``False`` when rounding changed the amount, which
    a migration must report rather than hide.
    """
    if rounding not in {decimal.ROUND_HALF_UP, decimal.ROUND_HALF_EVEN, decimal.ROUND_DOWN,
                        decimal.ROUND_UP, decimal.ROUND_CEILING, decimal.ROUND_FLOOR,
                        decimal.ROUND_HALF_DOWN, decimal.ROUND_05UP}:
        raise ValueError(f"unsupported rounding rule: {rounding!r}")
    if not isinstance(scale, int) or isinstance(scale, bool) or not 0 <= scale <= 6:
        raise ValueError("scale must be an integer between 0 and 6")
    amount = to_decimal(value, field)
    if amount is None:
        return None
    unit = Decimal(1).scaleb(-scale)
    quantized = amount.quantize(unit, rounding=rounding, context=decimal.Context(prec=120))
    minor = int(quantized.scaleb(scale, context=decimal.Context(prec=120)))
    if abs(minor) > MAX_MINOR_UNITS:
        raise EngineeringError(f"{field} is out of range for 64-bit minor units: {value!r}")
    return minor, quantized == amount
