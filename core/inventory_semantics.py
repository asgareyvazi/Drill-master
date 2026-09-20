"""Canonical general-inventory semantics for DrillMaster — Qt-free.

One place that defines the three-state numeric contract and the closing-stock
derivation for the ``InventoryItem`` (W5 general consumable inventory) domain.
This is NOT a generic inventory framework: it encodes the concrete, already
established repository rules (the same trichotomy proven for ``BulkMaterials``)
so the W5 UI, persistence and any reader agree.

Contract:
    None  = not reported (unknown)
    0.0   = explicitly reported zero
    value = reported quantity

* ``opening_stock`` follows the trichotomy.
* ``received``/``used`` absent = no movement (0.0).
* ``current_stock`` (closing) = opening + received - used when opening is
  known, else None (never a fabricated 0).
* Carry-forward may only fill a MISSING opening from a previous closing; it
  never overwrites an explicitly supplied opening (including an explicit 0).
"""
from __future__ import annotations

from typing import Optional


def to_float_or_none(value) -> Optional[float]:
    """Parse a cell/value into float, preserving unknown as None.

    Empty string / None / unparseable -> None (unknown). An explicit "0" or
    0 -> 0.0 (a reported fact). This is the single place UI text is turned
    into the trichotomy, so blank cells never silently become zero.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == "":
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def derive_closing(opening: Optional[float],
                   received: Optional[float],
                   used: Optional[float]) -> Optional[float]:
    """Closing stock = opening + received - used, or None when opening unknown.

    Never returns a fabricated 0.0 when the opening is unknown.
    """
    if opening is None:
        return None
    return float(opening) + float(received or 0.0) - float(used or 0.0)


def normalize_movement(value) -> float:
    """received/used normalization: absent -> 0.0 (no movement)."""
    parsed = to_float_or_none(value)
    return 0.0 if parsed is None else parsed


def normalize_item_row(row: dict) -> dict:
    """Normalize a raw W5 inventory row dict into the persistence trichotomy.

    ``row`` may carry string cells (from the table). Returns a dict with:
    item_name, category, unit, opening_stock (None|0.0|value),
    received (float), used (float), min_level (None|value),
    max_level (None|value). Closing is derived by the caller/persistence.
    """
    return {
        "item_name": (str(row.get("item_name", "")).strip() or None),
        "category": (str(row.get("category", "")).strip() or None),
        "unit": (str(row.get("unit", "")).strip() or None),
        "opening_stock": to_float_or_none(row.get("opening_stock")),
        "received": normalize_movement(row.get("received")),
        "used": normalize_movement(row.get("used")),
        "min_level": to_float_or_none(row.get("min_level")),
        "max_level": to_float_or_none(row.get("max_level")),
    }
