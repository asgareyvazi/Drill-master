"""Engine-agnostic core for historical calculation verification.

This module holds ONLY the parts of calculation verification that are genuinely
independent of any specific engineering engine, extracted after two concrete
implementations (Torque & Drag and Casing) demonstrated an identical contract
(mission §18/§19: abstract only what is truly shared, keep a small explicit
contract rather than a framework):

* the discrete verification STATES (``VERIFY_*``);
* the :class:`VerificationOutcome` value object;
* :func:`clean_number` (finite-float coercion, never bool/NaN/inf);
* :func:`deep_numeric_diff` — the recursive whole-result numeric comparison that
  makes MATCH an honest whole-result claim rather than a summary claim.

Everything engine-SPECIFIC — how a run's inputs are frozen into a snapshot, how
that snapshot is reconstructed into engine arguments, and which engine is run —
stays in the per-engine persistence modules
(``torque_drag_persistence``, ``casing_persistence``). This module never imports
an engine and knows nothing about surveys, casing loads, units, or summaries.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

# --------------------------------------------------------------------------
# Verification states. A discrete state (not a boolean) so callers can tell
# apart the meaningfully different outcomes:
#   MATCH            — recalculated result equals the stored result exactly
#   DIFFERENT        — engine ran, but the numbers differ (drift / algo change)
#   NOT_REPRODUCIBLE — engine could not run this snapshot (e.g. MISSING_INPUT)
#   UNREADABLE       — the stored record/snapshot is corrupt or has no result
# Verification is OBSERVATIONAL: callers must never rewrite the stored result.
# --------------------------------------------------------------------------
VERIFY_MATCH = "MATCH"
VERIFY_DIFFERENT = "DIFFERENT"
VERIFY_NOT_REPRODUCIBLE = "NOT_REPRODUCIBLE"
VERIFY_UNREADABLE = "UNREADABLE"

# Default absolute tolerance for comparing numeric result leaves. Engines round
# their reported values, so an exact stored run recomputes bit-identically; this
# only guards floating-point noise, never masks a real change.
DEFAULT_ABS_TOL = 1e-6

# Result keys that are textual/advisory metadata, not part of the numeric claim.
# Algorithm-method drift is reported separately via ``method_matches``.
DEFAULT_NON_NUMERIC_RESULT_KEYS = frozenset({
    "method", "scope", "warnings", "assumptions", "note", "formula", "unit",
})


def clean_number(value: Any) -> Optional[float]:
    """Return a finite float or ``None`` (never a bool, NaN or inf)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


@dataclass
class VerificationOutcome:
    """Result of checking a stored run against a fresh engine recalculation.

    ``status`` is one of the ``VERIFY_*`` constants. ``all_differences`` lists
    EVERY diverging numeric field across the whole result (deep comparison), so
    drift in a non-summary field cannot hide behind a summary-only MATCH.
    ``stored``/``recalculated``/``differences`` are optional engine-specific
    *summary* projections a caller may attach for display. ``method_matches``
    records whether the stored engine ``method`` equals the current engine
    method — a False means a numeric match could be an algorithm change, and it
    must not be presented as exact reproduction.
    """

    status: str
    stored: Dict[str, Optional[float]] = field(default_factory=dict)
    recalculated: Dict[str, Optional[float]] = field(default_factory=dict)
    differences: List[Dict[str, Any]] = field(default_factory=list)
    all_differences: List[Dict[str, Any]] = field(default_factory=list)
    method_matches: bool = True
    detail: str = ""


def deep_numeric_diff(
    stored: Any,
    recalculated: Any,
    *,
    non_numeric_keys: frozenset = DEFAULT_NON_NUMERIC_RESULT_KEYS,
    abs_tol: float = DEFAULT_ABS_TOL,
    path: str = "",
) -> List[Dict[str, Any]]:
    """Recursively compare two result structures at every numeric/boolean leaf.

    Compares numbers with ``abs_tol`` and booleans by equality; ignores textual
    metadata in ``non_numeric_keys``. Structural mismatches (a number vs a list,
    or lists of different length) are reported. Returns a list of
    ``{"path", "stored", "recalculated"}`` for each divergence — empty means the
    full numeric result reproduced exactly.

    This is the single source of truth for "did the whole result reproduce?" and
    is deliberately engine-agnostic (mission §26: whole-result verification).
    """
    diffs: List[Dict[str, Any]] = []

    # Both mappings: compare the union of keys (skip non-numeric metadata).
    if isinstance(stored, Mapping) and isinstance(recalculated, Mapping):
        for key in set(stored.keys()) | set(recalculated.keys()):
            if key in non_numeric_keys:
                continue
            diffs.extend(deep_numeric_diff(
                stored.get(key), recalculated.get(key),
                non_numeric_keys=non_numeric_keys, abs_tol=abs_tol,
                path=f"{path}.{key}" if path else str(key)))
        return diffs

    # Both sequences (but not strings): compare element-wise.
    if (isinstance(stored, (list, tuple)) and
            isinstance(recalculated, (list, tuple))):
        if len(stored) != len(recalculated):
            diffs.append({"path": path or "(root)",
                          "stored": f"len={len(stored)}",
                          "recalculated": f"len={len(recalculated)}"})
            return diffs
        for i, (a, b) in enumerate(zip(stored, recalculated)):
            diffs.extend(deep_numeric_diff(
                a, b, non_numeric_keys=non_numeric_keys, abs_tol=abs_tol,
                path=f"{path}[{i}]"))
        return diffs

    # Booleans are meaningful result flags (e.g. buckling.any) — exact equality.
    if isinstance(stored, bool) or isinstance(recalculated, bool):
        if stored != recalculated:
            diffs.append({"path": path or "(root)",
                          "stored": stored, "recalculated": recalculated})
        return diffs

    # Numeric leaves: tolerant comparison via clean_number (drops NaN/inf).
    a_num = clean_number(stored)
    b_num = clean_number(recalculated)
    if a_num is not None or b_num is not None:
        if a_num is None or b_num is None or abs(a_num - b_num) > abs_tol:
            diffs.append({"path": path or "(root)",
                          "stored": stored, "recalculated": recalculated})
        return diffs

    # Non-numeric, non-bool leaves (strings etc.) are not part of the numeric
    # claim — ignored (method drift is reported via ``method_matches``).
    return diffs


def classify_verification(
    stored_result: Mapping[str, Any],
    recalc: Any,
    *,
    snapshot_method: Optional[str],
    current_method: Optional[str],
    non_numeric_keys: frozenset = DEFAULT_NON_NUMERIC_RESULT_KEYS,
    abs_tol: float = DEFAULT_ABS_TOL,
) -> VerificationOutcome:
    """Classify a recalculation against a stored result (engine-agnostic).

    ``recalc`` is an already-computed engine result exposing ``.success``,
    ``.values`` and ``.error`` (the shape all DrillMaster engines return); the
    caller is responsible for reconstructing/running its own engine and for
    catching reconstruction exceptions (→ UNREADABLE) before calling this.
    Does not mutate anything.
    """
    method_matches = (current_method is None) or (snapshot_method == current_method)

    if not getattr(recalc, "success", False):
        return VerificationOutcome(
            status=VERIFY_NOT_REPRODUCIBLE,
            method_matches=method_matches,
            detail=getattr(recalc, "error", "engine did not produce a result"),
        )

    if not stored_result:
        return VerificationOutcome(
            status=VERIFY_UNREADABLE,
            method_matches=method_matches,
            detail="stored record has no result to verify against",
        )

    all_diffs = deep_numeric_diff(
        stored_result, recalc.values,
        non_numeric_keys=non_numeric_keys, abs_tol=abs_tol)
    return VerificationOutcome(
        status=VERIFY_MATCH if not all_diffs else VERIFY_DIFFERENT,
        all_differences=all_diffs,
        method_matches=method_matches,
    )
