"""Canonical historical snapshot + reproducibility for MSE (Teale) runs.

This is the Qt-free domain core of the FIFTH persistent engineering calculation
(mission: Calculation #5 = Mechanical Specific Energy, Teale 1965). It mirrors
the proven Torque & Drag / Casing / Cement principles — a deterministic,
serializable, self-contained historical input snapshot; reconstruction back into
engine arguments; and whole-result verification via the shared engine-agnostic
core — but it is again an INDEPENDENT concrete implementation because MSE's input
set and result differ from every prior calculation (mission §14/§43/§46: reuse
the proven verification core, keep snapshot/reconstruction concrete).

Design rules honored:

* The snapshot freezes the EXACT keyword arguments actually consumed by
  ``MSEEngine.calculate`` (WOB lbf, RPM, torque ft·lbf, ROP ft/hr, bit diameter
  in), so reconstruction never depends on any mutable/current UI state
  (mission §10/§15/§27). The one UI unit conversion (WOB klbf → lbf) happens
  BEFORE the snapshot is built, so the snapshot stores canonical engine units.
* No reference *fingerprint* is stored: every MSE input is a direct drilling
  parameter with no catalog/preset behind it — bit diameter in W13 is a direct
  user value, not a Bit-catalog lookup (mission §24/§25). Claiming reference
  traceability would be misleading; the numeric snapshot alone reconstructs the
  run.
* It records the engine ``method`` and a snapshot ``schema_version`` so an
  algorithm change is detectable, not silently reproduced (mission §22/§65).
* It introduces NO new engine and preserves canonical oilfield units exactly
  (lbf / rpm / ft·lbf / ft·hr⁻¹ / in — no conversion) (mission §12/§13).
* It is independent of Qt, Python object identity and dict ordering.

Note on the result contract (mission §18/§19): ``MSEEngine.calculate`` returns a
flat ``values`` dict — the headline ``mse_psi`` PLUS the decomposed
``axial_term_psi`` / ``rotary_term_psi``, the derived ``bit_area_in2`` and an
echo of the five inputs. All numeric leaves are correctness-relevant and are
persisted whole; the shared ``deep_numeric_diff`` compares them all, so
verification is a true whole-result claim, not a single-scalar claim.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

# Bump ONLY when the snapshot's meaning changes in a way affecting reconstruction.
SNAPSHOT_SCHEMA_VERSION = 1

# The exact keyword arguments MSEEngine.calculate consumes. Freezing precisely
# this set guarantees the snapshot reconstructs the engine call 1:1 (mission §10
# input contract). Kept in sync with the engine signature by a test.
_ENGINE_PARAMS = (
    "wob_lbf",
    "rpm",
    "torque_ft_lbf",
    "rop_ft_hr",
    "bit_diameter_in",
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
    """Build the deterministic historical input snapshot for one MSE run.

    ``inputs`` is the exact kwargs mapping used to call ``MSEEngine.calculate``
    (already in canonical engine units — WOB in lbf, not klbf). Numeric fields
    are frozen exactly (no rounding); missing fields are preserved as ``None`` so
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
    """Reconstruct ``MSEEngine.calculate`` kwargs from a stored snapshot.

    Built ONLY from the frozen snapshot — never from any current state. Unknown/
    extra keys are ignored; missing keys default to ``None`` so the engine
    contract (which rejects ``None`` as MISSING_INPUT) is honored exactly.
    """
    params = snapshot.get("parameters", {}) or {}
    return {key: params.get(key) for key in _ENGINE_PARAMS}


def recalculate_from_snapshot(snapshot: Mapping[str, Any]):
    """Re-run the real MSEEngine from a stored snapshot; returns the result.

    Uses the existing ``MSEEngine.calculate`` — no reimplementation of the Teale
    math — so a reloaded historical run is checked against the same code path
    that produced it.
    """
    from core.engineering.engines.mse import MSEEngine

    return MSEEngine.calculate(**snapshot_to_engine_args(snapshot))


# Result-summary keys promoted to queryable columns on the persisted record.
# These are the headline engineering claims of an MSE run.
SUMMARY_KEYS = (
    "mse_psi",
    "axial_term_psi",
    "rotary_term_psi",
    "bit_area_in2",
)


def result_summary(values: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """Extract the headline scalar claims from an engine ``values`` dict."""
    return {k: _clean_number(values.get(k)) for k in SUMMARY_KEYS}
