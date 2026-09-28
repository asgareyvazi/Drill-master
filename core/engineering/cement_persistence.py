"""Canonical historical snapshot + reproducibility for Cement job-volume runs.

This is the Qt-free domain core of the THIRD persistent engineering calculation
(mission: Calculation #3 = Cement job volumes). It mirrors the proven Torque &
Drag and Casing principles — a deterministic, serializable, self-contained
historical input snapshot; reconstruction back into engine arguments; and
whole-result verification via the shared engine-agnostic core — but it is again
an INDEPENDENT concrete implementation because cement's input/result classes
differ from both prior calculations (mission §33/§34: reuse the proven
verification core, keep snapshot/reconstruction concrete).

Design rules honored:

* The snapshot freezes the EXACT keyword arguments actually consumed by
  ``CementEngine.job_volumes`` (hole/casing geometry, excess, multi-leg slurry
  program, hydrostatic-column TVDs, pump rate), so reconstruction never depends
  on any mutable/current state (mission §20/§22).
* No reference *fingerprint* is stored: cement job-volume inputs are direct
  engineering values with no catalog/preset behind them, so claiming reference
  traceability would be misleading (mission §23). The numeric snapshot alone
  fully reconstructs the run.
* It records the engine ``method`` and a snapshot ``schema_version`` so an
  algorithm change is detectable, not silently reproduced (mission §32).
* It introduces NO new engine and preserves canonical units exactly
  (in / ft / ppg / bbl — no conversion) (mission §42).
* It is independent of Qt, Python object identity and dict ordering.

Note on the result contract (mission §21): ``CementEngine.job_volumes`` returns
mixed scalars PLUS nested ``lead``/``tail`` leg dicts and a
``stacked_hydrostatic`` layer list. All of these are correctness-relevant and
are persisted whole; the shared ``deep_numeric_diff`` compares them recursively,
so verification is a true whole-result claim, not a summary claim.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

# Bump ONLY when the snapshot's meaning changes in a way affecting reconstruction.
SNAPSHOT_SCHEMA_VERSION = 1

# The exact keyword arguments CementEngine.job_volumes consumes. Freezing
# precisely this set guarantees the snapshot reconstructs the engine call 1:1
# (mission §20 input contract). Kept in sync with the engine signature by a test.
_ENGINE_PARAMS = (
    "hole_size_in",
    "casing_od_in",
    "open_hole_length_ft",
    "excess_pct",
    "casing_id_in",
    "shoe_track_ft",
    "toc_md_ft",
    "shoe_md_ft",
    "slurry_density_ppg",
    "yield_ft3_sk",
    "mix_water_gal_sk",
    "lead_length_ft",
    "lead_density_ppg",
    "lead_yield_ft3_sk",
    "lead_mix_water_gal_sk",
    "tail_length_ft",
    "tail_density_ppg",
    "tail_yield_ft3_sk",
    "tail_mix_water_gal_sk",
    "tvd_column_ft",
    "spacer_length_ft",
    "spacer_density_ppg",
    "mud_density_ppg",
    "mud_tvd_ft",
    "spacer_tvd_ft",
    "lead_tvd_ft",
    "tail_tvd_ft",
    "shoe_tvd_ft",
    "pore_emw_ppg",
    "pump_rate_bbl_min",
)


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
    """Build the deterministic historical input snapshot for one cement run.

    ``inputs`` is the exact kwargs mapping used to call
    ``CementEngine.job_volumes``. Numeric fields are frozen exactly (no
    rounding); ``None`` optional fields are preserved as ``None`` so
    reconstruction reproduces the identical call. The returned dict is
    JSON-serializable and self-contained.
    """
    params: Dict[str, Any] = {}
    for key in _ENGINE_PARAMS:
        params[key] = _clean_number(inputs.get(key))
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "method": method,
        "parameters": params,
    }


def snapshot_to_engine_args(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Reconstruct ``CementEngine.job_volumes`` kwargs from a stored snapshot.

    Built ONLY from the frozen snapshot — never from any current state. Unknown/
    extra keys are ignored; missing keys default to ``None`` so the engine
    contract is honored exactly.
    """
    params = snapshot.get("parameters", {}) or {}
    return {key: params.get(key) for key in _ENGINE_PARAMS}


def recalculate_from_snapshot(snapshot: Mapping[str, Any]):
    """Re-run the real CementEngine from a stored snapshot; returns the result.

    Uses the existing ``CementEngine.job_volumes`` — no reimplementation of the
    volume/hydrostatic math — so a reloaded historical run is checked against
    the same code path that produced it.
    """
    from core.engineering.engines.cement import CementEngine

    return CementEngine.job_volumes(**snapshot_to_engine_args(snapshot))


# Result-summary keys promoted to queryable columns on the persisted record.
# These are the headline engineering claims of a cement job-volume run.
SUMMARY_KEYS = (
    "slurry_volume_bbl",
    "annular_with_excess_bbl",
    "displacement_volume_bbl",
    "total_pump_bbl",
    "sacks",
    "hydrostatic_psi",
)


def result_summary(values: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """Extract the headline scalar claims from an engine ``values`` dict."""
    return {k: _clean_number(values.get(k)) for k in SUMMARY_KEYS}
