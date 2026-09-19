"""Canonical historical snapshot + reproducibility for Mud Volume balance runs.

This is the Qt-free domain core of the SIXTH persistent engineering calculation
(mission: Calculation #6 = Mud Volume balance). It mirrors the proven
T&D / Casing / Cement / Kill-Sheet / MSE principles — a deterministic,
serializable, self-contained historical input snapshot; reconstruction back into
engine arguments; and whole-result verification via the shared engine-agnostic
core — but it is again an INDEPENDENT concrete implementation because the mud
volume balance input set and result differ from every prior calculation
(mission §21/§36/§39: reuse the proven verification core, keep
snapshot/reconstruction concrete).

Design rules honored:

* The snapshot freezes the EXACT keyword arguments actually consumed by
  ``MudVolumeEngine.balance`` (the eight bbl volume terms), so reconstruction
  never depends on any mutable/current UI state (mission §21/§23/§32).
* No reference *fingerprint* is stored: every input is a direct engineering
  volume in bbl with no catalog/preset behind it (mission §22). Claiming
  reference traceability would be misleading; the numeric snapshot alone
  reconstructs the run.
* It records the engine ``method`` and a snapshot ``schema_version`` so an
  algorithm change is detectable, not silently reproduced (mission §25).
* It introduces NO new engine and preserves the canonical unit (bbl) exactly —
  no conversion (mission §14/§15).
* It is independent of Qt, Python object identity and dict ordering.

Note on the result contract (mission §19): ``MudVolumeEngine.balance`` returns a
flat ``values`` dict — an echo of the eight inputs PLUS the derived
``final_volume_bbl`` and ``net_change_bbl``. All numeric leaves are
correctness-relevant and are persisted whole; the shared ``deep_numeric_diff``
compares them all, so verification is a true whole-result claim.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

# Bump ONLY when the snapshot's meaning changes in a way affecting reconstruction.
SNAPSHOT_SCHEMA_VERSION = 1

# The exact keyword arguments MudVolumeEngine.balance consumes. Freezing
# precisely this set guarantees the snapshot reconstructs the engine call 1:1
# (mission §13 input contract). Kept in sync with the engine signature by a test.
_ENGINE_PARAMS = (
    "active_volume_bbl",
    "additions_bbl",
    "losses_bbl",
    "transfers_in_bbl",
    "transfers_out_bbl",
    "returns_bbl",
    "dilution_bbl",
    "dumped_bbl",
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
    """Build the deterministic historical input snapshot for one balance run.

    ``inputs`` is the exact kwargs mapping used to call
    ``MudVolumeEngine.balance`` (canonical bbl). Numeric fields are frozen
    exactly (no rounding); missing optional fields are preserved as ``None`` so
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
    """Reconstruct ``MudVolumeEngine.balance`` kwargs from a stored snapshot.

    Built ONLY from the frozen snapshot — never from any current state. Unknown/
    extra keys are ignored. ``active_volume_bbl`` is required by the engine; the
    other seven default to ``0.0`` when absent, matching the engine's own
    optional-argument contract, so an old/partial snapshot reconstructs exactly.
    """
    params = snapshot.get("parameters", {}) or {}
    args: Dict[str, Any] = {}
    for key in _ENGINE_PARAMS:
        val = params.get(key)
        if key == "active_volume_bbl":
            args[key] = val  # required — pass through (None → MISSING_INPUT)
        else:
            args[key] = 0.0 if val is None else val
    return args


def recalculate_from_snapshot(snapshot: Mapping[str, Any]):
    """Re-run the real MudVolumeEngine from a stored snapshot; returns the result.

    Uses the existing ``MudVolumeEngine.balance`` — no reimplementation of the
    balance math — so a reloaded historical run is checked against the same code
    path that produced it.
    """
    from core.engineering.engines.mud_volume import MudVolumeEngine

    return MudVolumeEngine.balance(**snapshot_to_engine_args(snapshot))


# Result-summary keys promoted to queryable columns on the persisted record.
# These are the headline engineering claims of a mud volume balance run.
SUMMARY_KEYS = (
    "active_volume_bbl",
    "final_volume_bbl",
    "net_change_bbl",
)


def result_summary(values: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """Extract the headline scalar claims from an engine ``values`` dict."""
    return {k: _clean_number(values.get(k)) for k in SUMMARY_KEYS}
