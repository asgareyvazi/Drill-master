"""Concrete fuel/water (W7 ``FuelWaterInventory``) derivation semantics — Qt-free.

This is NOT a generic inventory framework. It encodes the specific, established
rules for the fixed fuel/water schema so the W7 widget, persistence and any
reader agree on two things the codebase previously got wrong:

* ``days_remaining`` (remaining / daily_consumption) is only meaningful when
  BOTH the remaining balance is known AND the daily consumption is a known,
  strictly-positive rate. When consumption is zero (no burn) or unknown, the
  runway is UNKNOWN — represented as ``None`` (rendered "N/A"), never a
  fabricated ``0`` (which reads as an imminent-stockout critical alarm) and
  never infinity.

The three-state contract (None = unknown, 0.0 = reported zero, value) applies
to the physical *stock* fields; movement fields (consumed/received) default to
0.0 (no movement) exactly as the general-inventory domain does.
"""
from __future__ import annotations

from typing import Optional


def days_remaining(remaining: Optional[float],
                   daily_consumption: Optional[float]) -> Optional[float]:
    """Return runway in days, or None when it cannot be truthfully computed.

    None when the remaining balance is unknown, or when daily consumption is
    unknown or not strictly positive (zero burn has no finite runway and must
    NOT be reported as ``0`` days).
    """
    if remaining is None:
        return None
    if daily_consumption is None or daily_consumption <= 0:
        return None
    return float(remaining) / float(daily_consumption)


def is_low_stock(remaining: Optional[float],
                 daily_consumption: Optional[float],
                 threshold_days: float = 3.0) -> bool:
    """True only when a KNOWN runway is below ``threshold_days``.

    An unknown runway (missing remaining or non-positive/unknown consumption)
    must not raise a low-stock warning — silence beats a false alarm.
    """
    days = days_remaining(remaining, daily_consumption)
    return days is not None and days < threshold_days
