"""Canonical cost semantics for DrillMaster — Qt-free, domain-specific.

One place that defines what the product means by planned cost, actual cost,
variance, NPT-cost allocation, and how the W16 AFE worksheet maps to the
persisted ``CostRecord`` model. This is NOT a generic cost engine: it encodes
the concrete, already-established repository semantics so that every consumer
(W16 UI, W12 analysis, report engine, operations intelligence) agrees.

Established repository facts this module standardizes:

* ``CostRecord`` (well-scoped) is the authoritative persisted cost line.
* Variance sign convention is ``planned - actual`` (positive = under budget),
  matching ``get_cost_summary`` / ``get_actual_vs_plan`` / report engine.
* NPT cost is an allocation of *stored actual cost* by the NPT time fraction,
  never a synthetic rig-day-rate product (matches report_engine).
* Rig/spread day-rates are UI *assumptions*, never persisted actual cost.
* Unknown currency stays unknown; it is never fabricated to USD.
"""
from __future__ import annotations

from typing import Optional, List, Dict, Any


# Persisted CostRecord columns this helper reads/writes for the AFE worksheet.
AFE_PERSISTED_FIELDS = ("category", "planned_cost", "actual_cost", "currency",
                        "afe_number", "cost_type", "status")

# The single canonical cost_type discriminator meanings already present in the
# schema. We do not invent a new discriminator; we document the ones in use.
COST_TYPE_BUDGET = "AFE"    # a planned/budget line from an AFE worksheet
COST_TYPE_OPEX = "OPEX"     # default operational cost line


def canonical_variance(planned: Optional[float],
                       actual: Optional[float]) -> Optional[float]:
    """Return the one canonical variance: ``planned - actual``.

    Returns ``None`` (unknown) when neither side is known. A known side with an
    unknown other side is treated as the known value less zero only when the
    other value is explicitly zero; otherwise unknown propagates.
    """
    if planned is None and actual is None:
        return None
    p = float(planned) if planned is not None else None
    a = float(actual) if actual is not None else None
    if p is None or a is None:
        # One side unknown -> variance is unknown, not a half-truth.
        return None
    return p - a


def percent_used(planned: Optional[float],
                 actual: Optional[float]) -> Optional[float]:
    """Actual as a percentage of planned. None when planned is unknown/zero."""
    if planned is None or actual is None:
        return None
    p = float(planned)
    if p == 0:
        return None  # cannot express "% of zero budget" as a fact
    return float(actual) / p * 100.0


def allocate_npt_cost(actual_cost: Optional[float],
                      npt_hours: Optional[float],
                      total_hours: Optional[float]) -> Optional[float]:
    """Allocate stored actual cost across recorded NPT time.

    ``npt_cost = actual_cost * npt_hours / total_hours``. Returns ``None``
    (unknown) unless stored actual cost AND a positive total_hours exist — the
    same contract used by the report engine. No synthetic rig-day rate is ever
    introduced here.
    """
    if actual_cost is None or total_hours in (None, 0) or npt_hours is None:
        return None
    if total_hours <= 0:
        return None
    return float(actual_cost) * float(npt_hours) / float(total_hours)


def normalize_currency(value: Optional[str]) -> Optional[str]:
    """Return an explicit currency code or ``None`` (unknown).

    An empty/blank currency is unknown, NOT silently USD (§9).
    """
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def afe_row_to_cost_record(row: Dict[str, Any], well_id: int,
                           afe_number: Optional[str] = None,
                           currency: Optional[str] = None) -> Dict[str, Any]:
    """Map one AFE worksheet row to a CostRecord dict.

    ``row`` carries ``category``/``planned_cost``/``actual_cost`` (and an
    optional ``id`` for updates). Variance is recomputed canonically so the
    persisted value can never contradict the summary. Currency is preserved as
    given (unknown stays unknown).
    """
    planned = row.get("planned_cost")
    actual = row.get("actual_cost")
    data: Dict[str, Any] = {
        "well_id": well_id,
        "category": row.get("category") or "",
        "planned_cost": planned,
        "actual_cost": actual,
        "variance": canonical_variance(planned, actual),
        "currency": normalize_currency(currency),
        "afe_number": (afe_number or None),
        "cost_type": COST_TYPE_BUDGET,
        "status": row.get("status") or "Pending",
    }
    if row.get("id"):
        data["id"] = row["id"]
    return data


def cost_records_to_afe_rows(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract AFE worksheet rows from persisted CostRecord dicts.

    Only AFE/budget-kind rows are surfaced to the AFE worksheet; other OPEX
    lines are left to their own views. Deterministic order by category.
    """
    rows = []
    for r in records:
        if (r.get("cost_type") or "") != COST_TYPE_BUDGET:
            continue
        rows.append({
            "id": r.get("id"),
            "category": r.get("category") or "",
            "planned_cost": r.get("planned_cost"),
            "actual_cost": r.get("actual_cost"),
        })
    rows.sort(key=lambda x: (x.get("category") or ""))
    return rows


def summarize_afe(rows: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Totals for a set of AFE rows using the canonical variance convention."""
    planned_vals = [r.get("planned_cost") for r in rows if r.get("planned_cost") is not None]
    actual_vals = [r.get("actual_cost") for r in rows if r.get("actual_cost") is not None]
    total_planned = sum(float(v) for v in planned_vals) if planned_vals else None
    total_actual = sum(float(v) for v in actual_vals) if actual_vals else None
    return {
        "total_planned": total_planned,
        "total_actual": total_actual,
        "variance": canonical_variance(total_planned, total_actual),
        "percent_used": percent_used(total_planned, total_actual),
    }
