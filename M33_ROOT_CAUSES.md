# M33 — root causes

Mission 33 · 2026-09-27 · base `c28bbef37cbac9de7abcfa693e7e21f678fa74ab`

Every entry states the defect, the mechanism that produced it, the evidence that proves it, the
fix (or the documented decision not to fix), and the control that would catch a regression.
Engine-default specific forensics (the "why 99.99", "why `or 0.0`" questions) are in
[`M33_ENGINE_DEFAULTS.md`](M33_ENGINE_DEFAULTS.md); this file states the systemic causes behind
them and the ones behind the M32 batch.

## A. Root causes fixed in this mission

### RC-1 — "missing" collapses into a plausible number at the last readable hop

**Symptom classes:** `sum(float(log.duration or 0))`, `fax = optional_number(...) or 0.0`,
`_clean_number(wob) or 0.0`, `spin.setValue(value)` against a widget whose range silently clamps.

**Mechanism:** the value enters as `None` (not recorded) and, at the point where it is *consumed
for a number*, a defensive `or 0` supplies a stand-in. Every layer that documented the correct
rule (`require_number`: *"never invent 0 for a missing engineering input"*; `casing_persistence`:
*"`None` optional loads are preserved as `None`"*; `evaluate`: safety factors gated on the load
being supplied) is upstream or downstream of that single expression, so the contract was already
stated in-repo and simply not applied at that hop.

**Why it was easy to miss:** with a zero load the physics answer is usually right (the API 5C3
baseline), so tests that check *numbers* pass; the damage is in the *record* (a run claiming
`axial_stress_psi: 0.0` / `fyax=80000.0`, a report claiming 99.99 m/hr, a KPI claiming 0 h of a
24 h day). The discriminating test must assert the *state* (`None` vs `0.0`, `n/a` vs a number),
not the value.

**Fix / controls:** M33-FIX-01 (data quality), M33-FIX-02 (casing echo), M33-FIX-03 (W3 clamp) —
each with a test that fails on the pre-fix source (`assert 99.99 == 150.0`,
`axial_stress_psi is None`) and a mutation control that reinstates the `or 0` and must be killed.

### RC-2 — a framework default silently becomes a domain limit

**Symptom:** the derived ROP display inherited Qt's `QDoubleSpinBox` maximum of **99.99**, so a
legal 150 m/hr value was truncated in the display, in the payload read from the display, and in
the row written to the database (and a stored 150 came back as 99.99). Nobody chose 99.99.

**Mechanism:** the widget's *range* had never been part of any contract; it was a framework
default that only became a domain limit because the widget feeds persistence. The nearest thing
to a domain statement was the validator (`core/validators.py`: `("avg_rop", 0, 500)`), which was
never connected to the widget.

**Fix / control:** the domain bound is now passed at the call site from the validator's own range,
and the display refuses to truncate at all (a value beyond the range widens the range; plausibility
stays the validator's job, which still warns). Mutants that remove the bound, the guard or both are
killed — including one survivor from the first mutation pass, which exposed that the call-site bound
was unasserted (the survivor was recorded, then closed by a test, not by re-running the harness).

### RC-3 — a fix recorded in evidence but absent from the worktree

**Symptom:** `M33-INC-001` — `core/professional_export.py` held only the *comment* of the M32
export fix (`4a3d5b44…`) while the M32 evidence recorded the fixed file (`96878cf6…`).

**Mechanism:** not attributed (the mission forbids speculation); the working hypothesis of a later
edit overwriting the fix cannot be proven from the available history, so it is recorded as
unattributed.

**Control:** every "fixed" file is now hash-verified against its recorded post-fix sha256 before the
claim is made, and each M33 fix carries its pre-fix hash (recovered from the Part-A manifest when
the file was dirty then, or from HEAD when it was clean). The re-application is recorded in
`m33-integrity-incidents.json`.

### RC-4 — a check that reports "0" when its input is missing is a fabricated measurement

**Symptom (fixed as M33-FIX-01):** the 24 h time-coverage metric summed unrecorded durations as
`0.0`, so one missing entry produced a *measured* coverage number, and `summary()` averaged it into
the score.

**Mechanism:** the metric had a single "computed" state; a missing input had no representation.
The same class of defect appears wherever a *derived KPI* is computed from data that may be absent
without an "unknown" state. The fix gives the metric three states (known / unknown / recorded zero),
excludes unknowns from aggregates, and exposes `confidence = known/total`.

## B. Root causes that are *decisions*, not defects (documented, not "fixed")

### RC-5 — T&D weight-on-bit has no "unknown" state, by design

`TorqueDragEngine.calculate(..., wob_klbf: float = 0.0, ...)` declares zero weight-on-bit in its own
signature; the only UI source is a spin box that always yields a number; negative is rejected. The
snapshot layer mirroring that default cannot change a result and cannot misreport an input (nothing
echoes WOB). Classified `VALID DOMAIN LIMIT / NO LIMIT REQUIRED` in
[`M33_ENGINE_DEFAULTS.md`](M33_ENGINE_DEFAULTS.md) (E-2, E-3). Changing it would be a speculative
redesign of a public engine signature.

### RC-6 — sentinel returns are an idiom, and only the *guarded* form is safe

A large share of the inventory is functions that return `None`/`False`/`{}` on a no-result path.
Two rules decide them per item: a branch that explicitly tests the sentinel makes it an idiom
(`R-RET-BRANCH` → intentional-by-design); a function whose *only* return is a sentinel, or whose
sentinel is not handled by any caller, stays `UNDER-REVIEW`. This asymmetry is deliberate: the
mission's "preserve missing vs explicit zero" rule is exactly about callers who cannot tell the
difference.

### RC-7 — the inventory's residual is dominated by *typing*, not by pattern

2 837 occurrences remain open; 963 of them need the concrete type of the tested subject and 339
need the default/caller contract of a function. The repository-wide binding index resolves a large
part of that automatically (the mission's earlier pass resolved hundreds), but the remainder is
domain work: each needs a human (or a much deeper call-graph) judgement about what the value can
be at that point. No rule was allowed to close them on shape alone — that is the anti-cheating
constraint, and it is the reason this mission does not claim closure.

## C. M32 fix re-verification (Part B summary)

All ten M32 fixes were re-verified against the *current* files, not against the M32 report: each
marker is present in the current source, the file hash is recorded, and the twelve targeted M32
regression tests re-run green (`tests/test_m31_scenarios.py`, 12 selected tests, all passed).
`M33-INC-001` is the one exception found and repaired. Details:
`docs/audits/m33-evidence/m33-m32-fix-reverification.json`. Independent behavioural re-verification
comes from the mutation matrix: 24/24 mutants killed, including the M32 fix mutants re-run in this
mission, with every mutated file restored byte-identically.
