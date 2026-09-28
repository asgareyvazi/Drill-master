"""Canonical historical snapshot + reproducibility for Casing-strength runs.

This is the Qt-free domain core of the SECOND persistent engineering
calculation (mission: Calculation #2 = Casing strength). It mirrors the proven
Torque & Drag principles — a deterministic, serializable, self-contained
historical input snapshot; reconstruction back into engine arguments; and
whole-result verification via the shared engine-agnostic core — but it is an
INDEPENDENT concrete implementation because casing's input/result classes
differ from T&D (mission §17/§21: reuse principles, not code patterns blindly).

Design rules honored:

* The snapshot freezes the EXACT scalar inputs actually used by
  ``CasingEngine.evaluate`` (pipe geometry + optional loads + design factors +
  connection minimums), so reconstruction never depends on any mutable/current
  reference state (mission §5/§7/§23).
* No reference *fingerprint* is stored: the casing "database" in the UI is a
  hard-coded preset table with no durable identity/provenance, so claiming
  catalog traceability would be misleading (mission §13). The numeric snapshot
  alone fully reconstructs the run.
* It records the engine ``method`` and a snapshot ``schema_version`` so an
  algorithm change is detectable, not silently reproduced (mission §28).
* It introduces NO new engine and preserves canonical units exactly
  (in / psi / lbf — no conversion) (mission §26).
* It is independent of Qt, Python object identity and dict ordering.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

# Bump ONLY when the snapshot's meaning changes in a way affecting reconstruction.
SNAPSHOT_SCHEMA_VERSION = 1

# The exact keyword arguments CasingEngine.evaluate consumes. Freezing precisely
# this set guarantees the snapshot reconstructs the engine call 1:1 (mission
# §16 input contract). Kept in sync with the engine signature by a test.
_ENGINE_PARAMS = (
    "od_in",
    "id_in",
    "wall_in",
    "yield_psi",
    "internal_pressure_psi",
    "external_pressure_psi",
    "axial_tension_lbf",
    "burst_design_factor",
    "collapse_design_factor",
    "tension_design_factor",
    "yield_at_temp_psi",
    "connection_burst_psi",
    "connection_collapse_psi",
    "connection_tension_lbf",
    "weight_ppf",
)
# ``grade`` is a text identity field carried for the historical record.
_ENGINE_TEXT_PARAMS = ("grade",)


def _clean_number(value: Any) -> Optional[float]:
    """Return a finite float or ``None`` (never a bool, NaN or inf)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def build_snapshot(*, inputs: Mapping[str, Any], method: str) -> Dict[str, Any]:
    """Build the deterministic historical input snapshot for one casing run.

    ``inputs`` is the exact kwargs mapping used to call ``CasingEngine.evaluate``.
    Numeric fields are frozen exactly (no rounding); ``None`` optional loads are
    preserved as ``None`` so reconstruction reproduces the identical call. The
    returned dict is JSON-serializable and self-contained.
    """
    params: Dict[str, Any] = {}
    for key in _ENGINE_PARAMS:
        params[key] = _clean_number(inputs.get(key))
    for key in _ENGINE_TEXT_PARAMS:
        val = inputs.get(key)
        params[key] = str(val) if val not in (None, "") else ""
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "method": method,
        "parameters": params,
    }


def snapshot_to_engine_args(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Reconstruct ``CasingEngine.evaluate`` kwargs from a stored snapshot.

    Built ONLY from the frozen snapshot — never from any current reference
    state. Unknown/extra keys are ignored; missing keys default to ``None`` /
    ``""`` so the engine contract is honored exactly.
    """
    params = snapshot.get("parameters", {}) or {}
    args: Dict[str, Any] = {}
    for key in _ENGINE_PARAMS:
        args[key] = params.get(key)
    for key in _ENGINE_TEXT_PARAMS:
        args[key] = params.get(key, "") or ""
    return args


def recalculate_from_snapshot(snapshot: Mapping[str, Any]):
    """Re-run the real CasingEngine from a stored snapshot; returns the result.

    Uses the existing ``CasingEngine.evaluate`` — no reimplementation of physics
    — so a reloaded historical run is checked against the same code path that
    produced it.
    """
    from core.engineering.engines.casing import CasingEngine

    return CasingEngine.evaluate(**snapshot_to_engine_args(snapshot))


# Result-summary keys promoted to queryable columns on the persisted record.
# These are the headline engineering claims of a casing-strength run.
SUMMARY_KEYS = (
    "burst_rating_psi",
    "collapse_rating_psi",
    "pipe_body_yield_lbf",
    "governing_burst_psi",
    "governing_collapse_psi",
    "governing_tension_lbf",
)


def result_summary(values: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """Extract the headline scalar claims from an engine ``values`` dict."""
    return {k: _clean_number(values.get(k)) for k in SUMMARY_KEYS}
