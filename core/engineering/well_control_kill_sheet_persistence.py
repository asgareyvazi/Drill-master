"""Canonical historical snapshot + reproducibility for Well Control **kill
sheet** runs — DrillMaster's FOURTH persistent engineering calculation and its
first *composite* one (mission: Calculation #4 = Well Control Kill Sheet).

Why this is different from the first three
------------------------------------------
Torque & Drag, Casing and Cement are each a SINGLE engine call whose
``EngineeringResult`` is the complete answer, so their snapshot freezes one
engine's kwargs and reconstruction re-runs that one engine. The kill sheet is a
**composite**: :func:`compute_kill_sheet` runs three ``WellControlEngine`` calls
(``kill_mw``, ``maasp``, ``kick_volume``) plus domain-level derived arithmetic
(string/annular volumes, ICP, FCP, strokes) and a linear choke schedule, and
returns a bespoke :class:`~core.engineering.well_control_kill_sheet.KillSheetResult`.

Therefore the historical claim is owned by the **composite**, not by the three
sub-engines (mission §51/§70). We do NOT persist three separate sub-engine
results as competing truths. Instead:

* The snapshot freezes the composite's canonical, Qt-free input object
  (:class:`WellControlKillSheetInputs`) — already in canonical units (ft / in /
  ppg / psi / psi·ft⁻¹ / bbl / bbl·stroke⁻¹), including the immutable pipe
  program. Reconstruction rebuilds that object with ``from_dict`` and re-runs
  the SAME ``compute_kill_sheet`` that produced the run — so a reloaded run is
  checked against the identical composite code path (mission §29/§31).
* The stored result is the WHOLE correctness-relevant ``KillSheetResult`` (every
  scalar, both nested detail lists, and the full choke schedule), so
  whole-result verification is a true whole-result claim (mission §13/§14).
* The snapshot records the engine ``method`` (a human-readable calculation
  method identifier, NOT a git/file hash — mission §11) and a snapshot
  ``schema_version`` so an algorithm change is detectable, not silently
  reproduced (mission §10).

Reference semantics (mission §35/§36): the kill-sheet pipe program is a MIXED
reference — components may come from the built-in ``AddPipeDialog.PIPE_DB``
presets, the optional persisted DrillPipe catalog, or manual entry. But the
calculation only ever consumes the numeric ``od``/``id``/``length``/``type`` of
each segment, which are frozen into the snapshot. Reconstruction therefore needs
NO live catalog lookup and NO current UI state, so this record stores NO
reference fingerprint (claiming catalog traceability would be misleading).

No new engine, no formula change, canonical units preserved exactly.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from core.engineering.well_control_kill_sheet import (
    WellControlKillSheetInputs,
    compute_kill_sheet,
)

# Bump ONLY when the snapshot's meaning changes in a way affecting
# reconstruction. v1 = frozen canonical WellControlKillSheetInputs.as_dict().
SNAPSHOT_SCHEMA_VERSION = 1


def build_snapshot(
    *, inputs: WellControlKillSheetInputs, method: str
) -> Dict[str, Any]:
    """Build the deterministic historical snapshot for one kill-sheet run.

    ``inputs`` is the exact canonical input object the composite consumed. Its
    ``as_dict()`` is self-contained and JSON-serializable (canonical units,
    immutable pipe tuple). We deliberately drop the input object's ``display``
    echo of raw UI units from the reproducible payload's identity role — it is
    presentation-only — but keep it under a separate ``display`` key so history
    can render the operator's original numbers without it ever feeding a formula.
    """
    payload = inputs.as_dict()
    display = payload.pop("display", {})
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "method": method,
        "canonical_inputs": payload,
        "display": display,
    }


def snapshot_to_inputs(snapshot: Mapping[str, Any]) -> WellControlKillSheetInputs:
    """Reconstruct the canonical input object from a stored snapshot.

    Built ONLY from the frozen snapshot — never from any current UI/catalog
    state. Raises if the snapshot is structurally invalid (caller maps that to
    UNREADABLE).
    """
    canonical = dict(snapshot.get("canonical_inputs", {}) or {})
    # display is presentation-only; not required to reconstruct the calculation,
    # but preserved on the rebuilt object so re-serialization round-trips.
    canonical.setdefault("display", dict(snapshot.get("display", {}) or {}))
    return WellControlKillSheetInputs.from_dict(canonical)


def recalculate_from_snapshot(snapshot: Mapping[str, Any]):
    """Re-run the real composite kill-sheet from a stored snapshot.

    Uses the existing :func:`compute_kill_sheet` — no reimplementation of the
    composite math — so a reloaded historical run is checked against the same
    code path that produced it. Returns a ``KillSheetResult`` (which exposes the
    ``success``/``values``/``error`` protocol the shared verifier consumes).
    """
    return compute_kill_sheet(snapshot_to_inputs(snapshot))


# Result-summary keys promoted to queryable columns on the persisted record.
# These are the headline engineering claims of a kill-sheet run (safety-critical
# figures an operator scans in a history list).
SUMMARY_KEYS = (
    "kill_mw_ppg",
    "icp_psi",
    "fcp_psi",
    "maasp_psi",
    "total_well_vol_bbl",
    "stk_total",
    "kick_height_ft",
)


def _clean_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def result_summary(result: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """Extract the headline scalar claims from a kill-sheet result dict."""
    return {k: _clean_number(result.get(k)) for k in SUMMARY_KEYS}
