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
from core.engineering.result import optional_number, require_number, EngineeringError


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
    p = optional_number(planned, "planned cost")
    a = optional_number(actual, "actual cost")
    if p is None or a is None:
        # One side unknown -> variance is unknown, not a half-truth.
        return None
    return require_number(p - a, "cost variance")


def percent_used(planned: Optional[float],
                 actual: Optional[float]) -> Optional[float]:
    """Actual as a percentage of planned. None when planned is unknown/zero."""
    p = optional_number(planned, "planned cost")
    actual = optional_number(actual, "actual cost")
    if p is None or actual is None:
        return None
    if p == 0:
        return None  # cannot express "% of zero budget" as a fact
    return require_number(require_number(actual, "actual cost") / p * 100.0, "percent used")


def allocate_npt_cost(actual_cost: Optional[float],
                      npt_hours: Optional[float],
                      total_hours: Optional[float]) -> Optional[float]:
    """Allocate stored actual cost across recorded NPT time.

    ``npt_cost = actual_cost * npt_hours / total_hours``. Returns ``None``
    (unknown) unless stored actual cost AND a positive total_hours exist — the
    same contract used by the report engine. No synthetic rig-day rate is ever
    introduced here.
    """
    actual_cost = optional_number(actual_cost, "actual cost")
    npt_hours = optional_number(npt_hours, "NPT hours")
    total_hours = optional_number(total_hours, "total hours")
    if actual_cost is None or total_hours in (None, 0) or npt_hours is None:
        return None
    if total_hours <= 0:
        return None
    if npt_hours < 0 or npt_hours > total_hours:
        raise EngineeringError("NPT hours must be between zero and total hours")
    return require_number(actual_cost * (npt_hours / total_hours), "allocated NPT cost")


def normalize_currency(value: Optional[str]) -> Optional[str]:
    """Return an explicit currency code or ``None`` (unknown).

    An empty/blank currency is unknown, NOT silently USD (§9).
    """
    if value is None:
        return None
    text = str(value).strip().upper()
    # These explicitly denote missing provenance, not monetary units. Do not
    # aggregate two UNKNOWN-labelled rows as though their currency were proven.
    if text in {"UNKNOWN", "UNSPECIFIED", "N/A", "NOT RECORDED", "NOT ASSESSED", "NONE", "NULL", "—"}:
        return None
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
        "currency": normalize_currency(row.get("currency", currency)),
        "afe_number": (afe_number or None),
        "cost_type": COST_TYPE_BUDGET,
        "status": row.get("status") or "Pending",
    }
    for key in ("description", "cost_date", "vendor", "invoice_number", "notes", "created_by", "created_at"):
        if key in row:
            data[key] = row[key]
    data["afe_number"] = row.get("afe_number", afe_number) if afe_number is None else afe_number
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
        row = dict(r)
        row["currency"] = normalize_currency(r.get("currency"))
        rows.append(row)
    rows.sort(key=lambda x: (x.get("category") or ""))
    return rows


def summarize_afe(rows: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Totals for a set of AFE rows using the canonical variance convention."""
    totals = summarize_costs(rows)
    return dict(totals, percent_used=percent_used(totals["total_planned"], totals["total_actual"]))


def complete_total(values):
    """A complete amount total, never a subtotal disguised as the total."""
    from core.engineering.result import optional_number
    values = [optional_number(v, "amount") for v in values]
    return require_number(sum(values), "amount total") if values and all(v is not None for v in values) else None


def summarize_costs(records):
    """CostRecord currency contract: no FX model, no project-currency inference.

    Single explicit currency permits totals; mixed/unknown currency does not.
    Category/currency groups remain available. NULL amounts invalidate that
    side's total, independently of the other side. Raw rows retain known facts.
    Accept ORM rows or their repository dict representation, not derived results.
    """
    def read(row, key):
        return row.get(key) if isinstance(row, dict) else getattr(row, key)

    records = list(records)
    grouped = {}
    for row in records:
        key = (normalize_currency(read(row, "currency")), read(row, "category") or "")
        grouped.setdefault(key, []).append(row)
    groups = []
    for (currency, category), rows in sorted(grouped.items(), key=lambda item: (item[0][0] or "", item[0][1])):
        planned = complete_total(read(r, "planned_cost") for r in rows) if currency else None
        actual = complete_total(read(r, "actual_cost") for r in rows) if currency else None
        groups.append(dict(currency=currency, category=category, planned=planned,
                           actual=actual, variance=canonical_variance(planned, actual)))
    currencies = {read_key[0] for read_key in grouped}
    currency = next(iter(currencies)) if len(currencies) == 1 and None not in currencies else None
    planned = complete_total(read(r, "planned_cost") for r in records) if currency else None
    actual = complete_total(read(r, "actual_cost") for r in records) if currency else None
    return {
        "currency": currency,
        "status": ("no-records" if not records else "unknown-currency" if None in currencies
                   else "multi-currency" if len(currencies) > 1 else "single-currency"),
        "total_planned": planned, "total_actual": actual,
        "variance": canonical_variance(planned, actual),
        "groups": groups,
    }


def format_money(value, currency):
    """Explicit currency codes work in text, HTML and spreadsheet labels."""
    currency = normalize_currency(currency)
    amount = f"{value:,.2f}" if value is not None else "—"
    return f"{currency} {amount}" if currency else f"{amount} (currency unknown)"
