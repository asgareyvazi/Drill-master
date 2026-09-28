# Casing Reference Authority — Deep Forensic Repository Audit

**Date:** 2026-09-14
**Branch:** `arena/01a085e0-drill-master`
**Audit type:** Independent re-verification (previous Arena reports treated as NON-authoritative)

---

## A. Executive Verdict

**`NO CHANGE JUSTIFIED`** for the Casing reference question — a persisted
authoritative Casing catalog is **NOT** warranted, and building one would
**fabricate provenance**. The existing two-calculation persistence architecture
(Torque & Drag + Casing Strength) is independently **re-certified as sound and
honest**.

Accompanying note (corrected mid-audit): the local checkout initially appeared to
have "reset to branch-point with no committed work". That was a **local
remote-tracking artifact**, not reality: after fetching the ref by name, the
remote session branch `arena/01a085e0-drill-master` was confirmed to contain the
full clean granular history (`b93ece9` … `64666a6`, DrillPipe + T&D + Casing).
The previous report's commit history is therefore **TRUE**; only the initial,
un-fetched local view was misleading. This audit adds only this document on top
of that real history — no prior work was re-committed or squashed.

---

## B. Repository Identity (independently verified)

| Property | Initial local view | **Actual (after `git fetch <branch>`)** |
|----------|--------------------|------------------------------------------|
| Branch | `arena/01a085e0-drill-master` | ✅ `arena/01a085e0-drill-master` |
| Local `HEAD` at start | `b05ea76` (branch-point) | (local checkout only) |
| Remote session branch head | appeared absent | ✅ **`b93ece9`** (real, present) |
| Mission commits `64666a6`/`6c54859`/`73fcdcc`/`b93ece9` | not in local refs | ✅ **all present on remote** |
| Remote `arena/01a085e0-drill-master` | not fetched by name yet | ✅ **exists** |
| Prior mission work | uncommitted in working tree | ✅ **committed & pushed** on remote (working tree byte-identical to `b93ece9`) |
| Remote | — | `https://github.com/asgareyvazi/Drill-master.git` |

**Conclusion:** the local checkout's `HEAD` pointer and remote-tracking refs were
stale; a targeted `git fetch origin arena/01a085e0-drill-master` revealed the
real branch head `b93ece9` with clean granular history that is a descendant of
`b05ea76`. The working tree content matched `b93ece9` exactly (verified by
`git diff` → empty). The repository — not any transient local pointer — is the
source of truth, and it confirms the prior work was genuinely committed.

## C. Previous Report Verification

| Claim | Evidence | Status |
|-------|----------|--------|
| Latest commit `b93ece9`, pushed | After `git fetch <branch>`: remote head **is** `b93ece9` with full history | ✅ TRUE (initially masked by a stale local ref) |
| Full suite 1125 passed / 4 skipped | Re-ran `pytest`: **1125 passed, 4 skipped** | ✅ TRUE |
| Two concrete persistent calculations (T&D + Casing) | Files + 67 targeted tests pass | ✅ TRUE |
| Shared `calculation_verification.py` exists, engine-agnostic | Only stdlib imports; no engine/Qt imports | ✅ TRUE |
| Abstraction limited to verification core | T&D/Casing snapshots are separate concrete modules | ✅ TRUE |
| Casing uses hard-coded `AddCasingDialog.CASING_DB` | Confirmed, but at **line 483**, not "line 4" | ✅ TRUE (loc wrong) |
| Casing stores NO reference fingerprint | `casing_persistence`/`CasingCalculationRecord` have none | ✅ TRUE |
| `CASING_DB` feeds the Casing Strength calculation | **Display-only preset; engine ignores it** (§E/§F) | ❌ MISLEADING |
| Search/Retrieval/Evidence untouched | No references to calc persistence found there | ✅ TRUE |
| No generic calculation framework | Confirmed absent | ✅ TRUE |

## D. Torque & Drag + Casing Revalidation

Independently verified (fresh venv, offscreen Qt):

* `CasingEngine.evaluate(...)` → success, 43 `.values` keys, burst 6865.5 psi,
  vme 22600.3 psi (matches the datum on record).
* Targeted suites all green: `test_casing_persistence` (18),
  `test_casing_cross_process` (2), `test_casing_history_viewmodel` (2),
  `test_calculation_verification_core` (10), `test_torque_drag_persistence`,
  `test_torque_drag_history` — **67 passed**.
* Both engines have real numerical implementations, full input snapshots, full
  result persistence, DB reload, reconstruction, whole-result verification,
  corruption states, and historical immutability (covered by those tests).

## E. Casing Reference Inventory

| Source | Path | Used by CALCULATION? | Authority | Identity | Provenance | Classification |
|--------|------|----------------------|-----------|----------|------------|----------------|
| `AddCasingDialog.CASING_DB` | `dialogs/engineering_dialogs.py:483` | **NO** (od/id/weight autofill only; burst/collapse shown as labels, not fed to engine) | None | None | None (hard-coded) | **DISPLAY-ONLY PRESET** |
| `AddCasingDialog` burst/collapse/tensile fields | same dialog | No (schematic section data) | None | None | None | DISPLAY / SCHEMATIC |
| `CasingReport` ORM (`casing_reports`) | `core/database.py:757` | No (daily-report casing string log) | Record | well/report FK | report import | ACTIVE (unrelated to strength calc) |
| `CasingCalculationRecord` (`casing_calculations`) | `core/database.py:2020` | **This IS the calc history** | Historical | snapshot | numeric snapshot (no ref fp) | ACTIVE / CORRECT |
| Grade lists (`H-40`…`V-150`), `THREAD_TYPES` | dialog | No | None | None | None | DISPLAY PRESET |

No casing catalog table, no casing importer, no casing reference repository, and
**no real casing source file** (`.xlsx`/`.csv`/`.json`) exist anywhere in the
repository. (Contrast: DrillPipe has a real vendor-import seam and a configurable
`DrillPipe.xlsx` path.)

## F. Casing Reference Decision — `CATALOG NOT JUSTIFIED`

The §13 eight-condition gate for an authoritative catalog:

| # | Condition | Holds? | Evidence |
|---|-----------|--------|----------|
| 1 | Calculation depends on reusable reference specs | ❌ | `CasingEngine.evaluate` computes burst (Barlow), collapse (API 5C3 four-regime), tension, VME purely from geometry + yield; it never reads catalog ratings |
| 2 | Hard-coded source acts as engineering master data | ❌ | `_csg_select_from_db` copies only `od/id/weight`; `burst/collapse` become text labels ("from API"), never engine inputs |
| 3 | Users need repeated reuse of specs | ⚠️ weak | Preset autofill exists but values are freely editable; no reuse-tracking need shown |
| 4 | Durable identity matters | ❌ | Historical reconstruction uses the frozen numeric snapshot, not an identity |
| 5 | Provenance matters | ❌ | No honest provenance source exists |
| 6 | Historical traceability benefits from stable ref identity | ❌ | Already fully satisfied by the numeric snapshot |
| 7 | DrillPipe pattern reusable conceptually | ✅ | It could be — but is not needed |
| 8 | Data can be populated honestly from real sources | ❌ | **No real casing source file exists**; a catalog would be seeded from a hard-coded dict = fabricated provenance |

Only 1 of 8 holds (plus one weak). This trips the §46 STOP conditions:
*"hard-coded Casing data is demonstrably only a UI preset"*, *"calculation
traceability is already sufficient from snapshots alone"*, and *"adding a catalog
would fabricate provenance"*. → **CATALOG NOT JUSTIFIED.**

The current design is the honest one: because the calculation does not depend on
a catalog, the Casing record correctly stores **no reference fingerprint**. This
is not a gap to close; it is the correct engineering claim boundary.

## G. Casing Engineering Identity

A casing *specification's* natural identity would be
`OD + weight(ppf) + grade + connection` (drift/ID derived). This is coherent in
the abstract, but it is **not needed** for the Casing Strength calculation, whose
reproducibility rests on the frozen scalar snapshot (`od/id/wall/yield/pressures/
axial/connection minimums`). No identity is invented from DB row IDs anywhere.

## H. Casing Provenance

**None exists and none should be fabricated.** `CASING_DB` has no manufacturer,
source file, sheet, row, or vendor identity. Labeling it a "vendor catalog" or
"API 5CT database" as a durable provenance source would be dishonest. (The UI
button text "API 5CT Database" is a cosmetic label on a hard-coded preset — a
minor honesty wart, noted as debt in §S, not a persistence claim.)

## I. Casing Traceability (current behavior)

`Current preset (display) ≠ Historical input snapshot ≠ Derived result` holds
correctly today: the saved run freezes the exact engine kwargs, reconstructs
bit-identically across a fresh process, and verifies the whole result. No live
catalog is a hidden dependency of any historical run (there is no catalog at
all).

## J. Shared Verification Core

`core/engineering/calculation_verification.py` shares exactly, and only:
`VERIFY_*` states, `VerificationOutcome`, `clean_number`, `deep_numeric_diff`,
`classify_verification`, tolerance/non-numeric-key policy. Imports are stdlib
only (`math`, `dataclasses`, `typing`). No engine, Casing, T&D, UI, or Qt import.
Consumers: `torque_drag_persistence`, `casing_repository`,
`casing_history_dialog`, and tests. T&D public API remained compatible.

## K. Abstraction Decision — `VERIFICATION ONLY`

| Concern | T&D | Casing | Shared semantics proven? |
|---------|-----|--------|--------------------------|
| Verification states / outcome | ✅ | ✅ | **YES → shared** |
| Whole-result deep diff | ✅ | ✅ | **YES → shared** |
| Algorithm/method mismatch flag | ✅ | ✅ | YES (via `method_matches`) |
| Snapshot format | survey + component specs | pipe scalars + loads | NO → concrete |
| Snapshot reconstruction | T&D-specific | Casing-specific | NO → concrete |
| Repository | concrete | concrete | not proven → keep concrete |
| Identity / fingerprint | present (ref fp) | **absent (correct)** | NO → divergent |
| Provenance | real vendor seam | none | NO → divergent |
| History dialog | concrete | concrete | Qt-free view-model helper only |
| Reference traceability | catalog-backed | snapshot-only | **divergent by design** |

Only verification generalized. Identity, provenance, and reference traceability
are *provably divergent* between the two engines — strong evidence AGAINST any
broader framework. **Do not extract** `BaseCalculation`, generic repository,
snapshot DSL, or a reference framework (§29 prohibitions upheld).

## L. Third-Calculation Inventory (reconnaissance only)

| Engine | Production UI (W13) | Determinism | Snapshot | Result complexity | Reference coupling | Historical value | Readiness |
|--------|--------------------|-------------|----------|-------------------|--------------------|------------------|-----------|
| Cement | Yes (`_csg_calc_cement`) | 0 nondeterminism markers | Simple scalars | Moderate (volume/capacity) | Low | Medium | Candidate |
| Mud Volume | Yes | clean | Simple | Low | Low | Medium | Candidate |
| Bit Performance | Yes (`bit_performance`) | clean | Moderate | Report-coupled | Report state | Medium | Coupled |
| MSE | Yes | clean | Trivial (≈5 in/4 out) | Low | Low | Low | Weak |
| Well Control | Yes | clean | Moderate | Moderate | Low | High (safety) | Candidate |
| Anti-Collision | Not clearly wired | clean | Complex (survey pairs) | High | Survey | High | Investigate |
| Fishing | Yes (free-point/stretch/backoff) | clean | Simple | Low | Low | Medium | Candidate |
| Trajectory | via T&D survey | clean | — | — | — | (already used by T&D) | N/A |

No engine uses `random`/`datetime.now`/`time.time`/`uuid`. **Calculation #3 is
deferred** — the mission gate requires resolving the Casing reference question
first (now resolved: no blocker), but a #3 is not part of this slice and none is
implemented.

## M. Reference-Data Architecture Inventory

| Domain | Persisted? | Authoritative? | Hard-coded? | Imported? | Provenance? | Fingerprint? | Feeds calc? | Viewer-only? |
|--------|-----------|----------------|-------------|-----------|-------------|--------------|-------------|--------------|
| DrillPipe | ✅ (`drill_pipe_specs`) | ✅ | preset dict + catalog | ✅ (vendor xlsx seam) | ✅ | ✅ `identity_fingerprint()` | ✅ (T&D component specs) | No |
| Casing | ❌ (calc history only) | ❌ | ✅ (`CASING_DB` preset) | ❌ | ❌ | ❌ (correct) | **No** | Preset only |
| Bits / Collars / Mud / Cement | mixed / report-scoped | ❌ | dialog presets | partial | ❌ | ❌ | varies | mostly viewer |

DrillPipe is the *only* domain that earned reference authority — because a real
vendor source and calculation dependency exist there. Casing has neither.

## N. Search / Retrieval / Evidence

**Unchanged.** No calculation-persistence code touches Search, Retrieval,
EvidenceBundle, or CitationAuditor. Boundary preserved (§35).

## O. Database

**No schema change made in this audit.** The two calculation tables
(`torque_drag_calculations`, `casing_calculations`) and `drill_pipe_specs`
already exist in `core/database.py` from prior work and are provisioned by the
repository's own `_apply_safe_schema_upgrades` convention (no Alembic). No casing
catalog table was added (per §F).

## P. Tests

Commands (fresh `.venv`, `source tools/qt_headless_env.sh`,
`QT_QPA_PLATFORM=offscreen`):

* `pytest tests/test_casing_persistence.py tests/test_casing_cross_process.py
  tests/test_casing_history_viewmodel.py tests/test_calculation_verification_core.py
  tests/test_torque_drag_persistence.py tests/test_torque_drag_history.py`
  → **67 passed**.
* `pytest` (full) → **1125 passed, 4 skipped** (exit 0), twice.

## Q. Forensics — dead / duplicate / obsolete

| Item | Finding | Classification |
|------|---------|----------------|
| `AddCasingDialog.CASING_DB` | live preset used by schematic + calc autofill | ACTIVE (preset) |
| `AddPipeDialog.PIPE_DB` | analogous live preset | ACTIVE (preset) |
| Casing importer / catalog | do not exist | N/A (nothing to remove) |
| Duplicate verification logic | none — single shared core | CLEAN |
| Old T&D comparison helpers | folded into shared core; re-exported for compat | ACTIVE |
| `.github/workflows/ci.yml` | untracked, pre-existing | LEFT UNTOUCHED (per standing instruction) |

No deletions performed. Nothing removed on age alone.

## R. Dependencies

**None added.** A local `.venv` was recreated (gitignored) to run tests; it is
not part of the repository. Runtime deps unchanged.

## S. Remaining Debt (evidence-backed)

1. **Cosmetic honesty wart:** the W13 button reads "Select Casing from API 5CT
   Database" while the source is a hard-coded preset. Not a persistence claim,
   but the wording overstates authority — consider renaming to "Select Casing
   Preset". (Low priority; no code change made to keep this slice focused.)
2. **Two casing preset dicts** (`CASING_DB` for sections, grade lists) are
   display-layer; acceptable, but if a real casing catalog is ever sourced, they
   should converge on it — only then.
3. Calculation #3 selection remains open (reconnaissance in §L).

## T. Git

* Local `HEAD` started at `b05ea76`; a targeted `git fetch origin
  arena/01a085e0-drill-master` revealed the real remote head `b93ece9` (clean
  granular history, descendant of `b05ea76`).
* Working tree was byte-identical to `b93ece9` (`git diff` empty) — no prior work
  was lost, so nothing was re-committed or squashed.
* This audit adds exactly one file
  (`docs/audits/2026-09-14_CASING_REFERENCE_AUTHORITY_FORENSIC_AUDIT.md`) as a
  single commit on top of `b93ece9`. `.github/` left untouched; `.venv`
  gitignored.

## U. Final Decision

> **NO CHANGE JUSTIFIED** — for the Casing reference-authority question: do not
> build a Casing catalog; the hard-coded `CASING_DB` is a display-only preset,
> the calculation does not depend on it, and historical traceability is already
> sound from the numeric snapshot alone. The existing T&D + Casing calculation
> architecture is re-certified. The only corrective action taken was preserving
> the already-verified working-tree work in Git and correcting the false Git
> record from the previous report.
