"""Canonical historical snapshot + reproducibility for Torque & Drag runs.

This module is the Qt-free domain core of calculation persistence. It turns the
*exact* inputs of one Torque & Drag execution into a deterministic, serializable
**historical input snapshot**, and reconstructs that snapshot back into engine
arguments so the run can be re-executed and its result independently checked —
long after the mutable master reference catalog has changed.

Design rules honored (see docs/audits/2026-09-13_CALCULATION_PERSISTENCE.md):

* The snapshot stores the full engineering inputs actually used (survey +
  component specs + scalar parameters), NOT just a mutable reference id. A
  reference *fingerprint* is retained per component for traceability, but the
  numeric fields needed to recompute are frozen in the snapshot itself, so
  reconstruction never depends on the current catalog (mission §5, §7, §9).
* It records the engine ``method`` and a snapshot ``schema_version`` so a future
  numerical change to the algorithm is detectable rather than silently
  rewriting history (mission §13).
* It introduces NO new engine and NO new normalization; it calls the existing
  ``TorqueDragEngine`` and preserves canonical units exactly (ppf stays ppf —
  no mass conversion; diameters stay inches) (mission §26).
* It is independent of Qt, of Python object identity and of row ordering
  (mission §7).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional

from core.engineering.calculation_verification import (
    DEFAULT_NON_NUMERIC_RESULT_KEYS as _NON_NUMERIC_RESULT_KEYS,
    VERIFY_DIFFERENT,
    VERIFY_MATCH,
    VERIFY_NOT_REPRODUCIBLE,
    VERIFY_UNREADABLE,
    VerificationOutcome,
    classify_verification,
    deep_numeric_diff as _deep_numeric_diff,
)

# Snapshot format version. Bump ONLY when the snapshot's meaning changes in a
# way that affects reconstruction; readers use it to stay backward-compatible.
SNAPSHOT_SCHEMA_VERSION = 1

# The canonical scalar parameters of a T&D run and their engine-argument names.
_SCALAR_KEYS = (
    "mud_density_ppg",
    "friction_factor",
    "wob_klbf",
    "wellbore_id_in",
)

# Canonical per-component fields the engine consumes (mission §26: exact units).
_COMPONENT_NUMERIC = ("od", "id", "length", "weight")
_COMPONENT_TEXT = ("type", "name", "grade", "connection", "serial")


def _clean_number(value: Any) -> Optional[float]:
    """Return a finite float or ``None`` (never a bool, NaN or inf)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _canonical_component(comp: Mapping[str, Any]) -> Dict[str, Any]:
    """Freeze one drill-string component into snapshot form.

    Numeric engineering fields are preserved exactly (no rounding — rounding
    happens only inside the engine's reported result). A ``reference_fingerprint``
    is carried through verbatim when present so the historical run remembers WHICH
    catalog reference identity it used, without depending on that catalog later.
    """
    out: Dict[str, Any] = {}
    for key in _COMPONENT_NUMERIC:
        num = _clean_number(comp.get(key))
        if num is not None:
            out[key] = num
    for key in _COMPONENT_TEXT:
        val = comp.get(key)
        if val not in (None, ""):
            out[key] = str(val)
    fp = comp.get("reference_fingerprint")
    if fp:
        out["reference_fingerprint"] = str(fp)
    return out


def _canonical_survey(survey: List[Mapping[str, Any]]) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    for station in survey or []:
        row: Dict[str, float] = {}
        for key in ("md", "inc", "azi"):
            num = _clean_number(station.get(key))
            if num is not None:
                row[key] = num
        rows.append(row)
    return rows


def build_snapshot(
    *,
    survey: List[Mapping[str, Any]],
    components: List[Mapping[str, Any]],
    mud_density_ppg: Any,
    friction_factor: Any,
    wob_klbf: Any = 0.0,
    wellbore_id_in: Any = None,
    method: str,
) -> Dict[str, Any]:
    """Build the deterministic historical input snapshot for one T&D run.

    The returned dict is JSON-serializable and self-contained: it holds every
    input needed to re-run the calculation exactly, plus the engine ``method``
    and snapshot ``schema_version`` for reproducibility auditing.
    """
    scalars: Dict[str, Any] = {
        "mud_density_ppg": _clean_number(mud_density_ppg),
        "friction_factor": _clean_number(friction_factor),
        "wob_klbf": _clean_number(wob_klbf) or 0.0,
        "wellbore_id_in": _clean_number(wellbore_id_in),
    }
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "method": method,
        "survey": _canonical_survey(list(survey or [])),
        "components": [_canonical_component(c) for c in (components or [])],
        "parameters": scalars,
    }


def reference_fingerprints(snapshot: Mapping[str, Any]) -> List[str]:
    """Every distinct catalog reference identity used by the snapshot's string.

    This answers "which reference identities did this calculation use?" — a
    different question from "what exact inputs were used" (which the whole
    snapshot answers). Order-preserving, de-duplicated.
    """
    seen: List[str] = []
    for comp in snapshot.get("components", []) or []:
        fp = comp.get("reference_fingerprint")
        if fp and fp not in seen:
            seen.append(fp)
    return seen


def snapshot_to_engine_args(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Reconstruct engine keyword arguments from a stored snapshot.

    The result is exactly what :meth:`TorqueDragEngine.calculate` expects, built
    only from the frozen snapshot — never from the live catalog. Non-engine
    metadata (``reference_fingerprint``) is stripped from components so the
    engine contract is unchanged.
    """
    params = snapshot.get("parameters", {}) or {}
    components: List[Dict[str, Any]] = []
    for comp in snapshot.get("components", []) or []:
        components.append({k: v for k, v in comp.items()
                           if k != "reference_fingerprint"})
    return {
        "survey": [dict(s) for s in snapshot.get("survey", []) or []],
        "bha": components,
        "mud_density_ppg": params.get("mud_density_ppg"),
        "friction_factor": params.get("friction_factor"),
        "wob_klbf": params.get("wob_klbf", 0.0) or 0.0,
        "wellbore_id_in": params.get("wellbore_id_in"),
    }


def recalculate_from_snapshot(snapshot: Mapping[str, Any]):
    """Re-run the real engine from a stored snapshot; returns EngineeringResult.

    Uses the existing ``TorqueDragEngine`` — no reimplementation of physics —
    so a reloaded historical run is checked against the same code path that
    produced it.
    """
    from core.engineering.engines.torque_drag import TorqueDragEngine

    args = snapshot_to_engine_args(snapshot)
    return TorqueDragEngine.calculate(**args)


# Result-summary keys promoted to queryable columns on the persisted record.
# These are the headline engineering claims of a T&D run.
SUMMARY_KEYS = (
    "hookload_pickup",
    "hookload_slackoff",
    "hookload_rotating",
    "surface_torque_rotating_ft_lbf",
    "total_buoyed_weight",
)


def result_summary(values: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """Extract the headline scalar claims from an engine ``values`` dict."""
    return {k: _clean_number(values.get(k)) for k in SUMMARY_KEYS}


# --------------------------------------------------------------------------
# Historical verification (mission §14–§18).
#
# The discrete states, the outcome value object and the engine-agnostic deep
# numeric comparison now live in ``core.engineering.calculation_verification``
# (shared with the Casing slice). This module keeps only the T&D-SPECIFIC parts:
# reconstructing the frozen snapshot, running the real T&D engine, and attaching
# the T&D summary projection. ``VERIFY_*``, ``VerificationOutcome`` and
# ``_deep_numeric_diff`` are re-exported above for backward compatibility.
# Verification is OBSERVATIONAL: it NEVER rewrites the stored result (§16).
# --------------------------------------------------------------------------
_VERIFY_ABS_TOL = 1e-6


def _summaries_differ(stored: Mapping[str, Optional[float]],
                      recalculated: Mapping[str, Optional[float]]
                      ) -> List[Dict[str, Any]]:
    """Return the list of summary keys whose values differ beyond tolerance."""
    diffs: List[Dict[str, Any]] = []
    for key in SUMMARY_KEYS:
        a = stored.get(key)
        b = recalculated.get(key)
        if a is None and b is None:
            continue
        if a is None or b is None or abs(a - b) > _VERIFY_ABS_TOL:
            diffs.append({"key": key, "stored": a, "recalculated": b})
    return diffs


def verify_saved_calculation(
    snapshot: Mapping[str, Any],
    stored_result: Mapping[str, Any],
    *,
    current_method: Optional[str] = None,
) -> VerificationOutcome:
    """Recompute a stored T&D run from its snapshot and classify the outcome.

    Pure/observational: it re-runs the real engine on the FROZEN snapshot only
    (never the live catalog) and compares the recalculated result against the
    stored one over the ENTIRE numeric result (deep diff via the shared core),
    so no non-summary drift can hide behind a MATCH. It does not mutate
    anything. ``current_method`` (if given) is compared to the snapshot's engine
    method so a numeric match under a changed algorithm is not silently reported
    as exact reproduction.
    """
    stored_summary = result_summary(stored_result or {})
    snap_method = (snapshot or {}).get("method")

    try:
        recalc = recalculate_from_snapshot(snapshot)
    except Exception as exc:  # corrupt/unreadable snapshot -> honest UNREADABLE
        method_matches = (current_method is None) or (snap_method == current_method)
        return VerificationOutcome(
            status=VERIFY_UNREADABLE,
            stored=stored_summary,
            method_matches=method_matches,
            detail=f"snapshot could not be reconstructed: {exc}",
        )

    outcome = classify_verification(
        stored_result or {}, recalc,
        snapshot_method=snap_method, current_method=current_method)

    # Attach the T&D-specific summary projection for the headline view.
    outcome.stored = stored_summary
    if getattr(recalc, "success", False):
        recalculated_summary = result_summary(recalc.values)
        outcome.recalculated = recalculated_summary
        outcome.differences = _summaries_differ(stored_summary,
                                                 recalculated_summary)
    return outcome

