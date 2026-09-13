# DrillPipe Reference — Source-of-Truth Forensic Certification

Date: 2026-09-13
Mission: Independently verify the DrillPipe reference implementation is
architecturally safe / production-ready; eliminate remaining source-of-truth
ambiguity with the smallest evidence-backed change; do not prematurely generalize.

Method: repository-as-source-of-truth. Every prior claim re-verified against the
checked-out code, tests, and runtime before any implementation.

---

## A. Repository Identity

| item | value |
|---|---|
| branch | `arena/01a085e0-drill-master` |
| HEAD (before this pass) | `0e0af51` (restored from remote after a session reset) |
| parent | `1557a08` (→ `2b72ed7` → `7a662c2`) |
| working tree | clean except untracked `.github/workflows/` (never committed) |
| remote | `origin` = GitHub `asgareyvazi/Drill-master`; branch tip `0e0af51` |

**Session-reset note:** the local checkout was found reset to the branch-point
`b05ea76` with all prior work appearing as uncommitted changes and `.venv`/`qt-libs`
gone. Recovery: `git fetch` + `git reset --hard 0e0af51` (remote had the real tip),
rebuild `.venv` from `requirements-lock.txt`, re-`source tools/qt_headless_env.sh`.
No committed work was lost.

## B. Previous claims independently verified

| Claim | Verified? | Evidence |
|---|---|---|
| HEAD contains DrillPipeSpec, normalizer, persistence, repo, race-fix, dialog integration, W13 wiring, Qt-free helpers, tests, docs | VERIFIED | files present; `git diff 1557a08..0e0af51` matches; code read |
| identity deterministic (5/5.0/5.000; case/space) | VERIFIED | runtime probe: all True |
| ppf not mass-converted; OD/ID stay inch | VERIFIED | component `{weight:19.5 ppf, od:5.0, id:4.276}`; T&D 165.23 klbf |
| ENRICHED never overwrites known values | VERIFIED | known+conflict→CONFLICT, known+invalid→UNCHANGED, known+unknown→UNCHANGED, unknown+valid→ENRICHED; stored value preserved every case |
| CONFLICT preserves stored row | VERIFIED | id stays 4.276 after conflicting upsert |
| race handling catches IntegrityError and reconciles | VERIFIED | outer try/except → `_upsert_once(insert_allowed=False)`; each attempt own `session_scope` |
| ground truth 165.229 klbf | VERIFIED | engine 165.23 |
| no fabricated/seeded catalog data | VERIFIED | `drill_pipe_specs` empty; PIPE_DB is standard nominal presets, not seeded DB rows |
| PIPE_DB used only in AddPipeDialog | VERIFIED | repo-wide grep: 5 refs, all in `dialogs/engineering_dialogs.py` |
| reference list ordering deterministic | **FALSE (was)** → FIXED | `repo.all()` had no ORDER BY → rowid/insertion order (see G) |

## C. Current architecture (actual dependency graph)

```
Production selection + calculation path:
  DrillPipeSpec (domain) ─ to_record_values/from_record_values ─┐
  DrillPipeReferenceRepository(BaseRepository)                  │  session_scope
     ▲ all()/get/upsert/import_specs                            ▼
  build_reference_choices (Qt-free)     DrillPipeSpecRecord (ORM, UNIQUE identity)
     ▼                                                          ▼
  AddPipeDialog Quick Select  ◄── PIPE_DB (built-in presets)   SQLite
     ▼
  wt_pipes (component dict) ──► TorqueDragEngine.calculate ──► EngineeringResult

Disconnected display-only path (NOT reference catalog, NOT used by any calc):
  DrillPipe.xlsx ─► w13._load_drill_pipe_db() ─► _drill_pipe_df ─► PandasTableModel viewer
```

## D. DrillPipe sources — classification

| Source | Role | Evidence |
|---|---|---|
| `DrillPipeSpec` | canonical domain model | frozen dataclass; identity/normalization |
| `DrillPipeReferenceRepository` / `drill_pipe_specs` | **authoritative persisted reference catalog** (user/vendor, carries manufacturer/model/provenance) | global-scoped ORM, UNIQUE identity |
| `AddPipeDialog.PIPE_DB` | **built-in standard nominal presets** (Case 2) — generic API geometries, NO manufacturer/model/provenance | dict read; entries like `5" 19.5# S-135` |
| `DrillPipe.xlsx` viewer | **display-only** external vendor-sheet preview; not connected to calc or repo | `_drill_pipe_df` only feeds a `PandasTableModel` |

## E. Source-of-truth decision (evidence-backed)

**No ambiguity exists between PIPE_DB and the persisted catalog, and they coexist
safely — verified, not assumed:**

* Disjoint label namespaces: persisted entries carry the `◆ ` prefix; presets never
  do. Runtime check: a persisted `5" 19.5# S-135` labels as
  `◆ (unbranded) 5" 19.5# S-135 NC50` — cannot byte-collide with the preset
  `5" 19.5# S-135`.
* Deterministic resolution: `_on_quick_selected` looks up `_reference_specs` (prefixed
  labels) first, else falls back to `PIPE_DB` — a selection always resolves to exactly
  one known source.
* Both are additive; neither overwrites the other; manual entry remains the default.

**Policy (matches existing architecture, no change required):**
`PERSISTED REPOSITORY = authoritative reusable reference master`;
`PIPE_DB = permanent built-in preset fallback (kept; standard nominal geometries)`;
`DrillPipe.xlsx = display-only viewer`. PIPE_DB is **not** retired — it is standard
industry presets, not vendor master data, and is the safe fallback when the catalog
is empty (rule 11).

## F. Identity / revision

Identity = normalized (mfr, model, od, weight, grade, connection) → deterministic
`identity_fingerprint`. Same identity + different engineering value ⇒ **CONFLICT**
(safe; never overwrites). No revision table exists and none added (no product rule in
repo requires it). Unicode-NFC normalization still absent; classified **A (harmless,
documented)** — reference identities in the repo are ASCII API designations; no
demonstrated correctness case, so not implemented (rule 15/16).

## G. The one defect found + fix

**`repo.all()` had no `ORDER BY`** → the Quick-Select reference list appeared in
SQLite rowid/insertion order (runtime-confirmed non-sorted, insert-order dependent).
This violates the "no accidental ordering dependence" requirement (§7).

**Fix (smallest, local):** `all()` now orders by the identity-forming columns
(od, weight, manufacturer, model, grade, connection) with `identity_fingerprint` as
final tie-break. Verified: identical output regardless of insert order; ascending by
OD. Two regression tests added.

No other change to repository semantics (NEW/UNCHANGED/ENRICHED/CONFLICT/INVALID,
race handling, transactions) — all re-verified correct and left untouched.

## H. UI selection (actual merge behavior)

`_on_type_changed` builds Quick Select as: `-- Manual Entry --`, then persisted
references (now deterministically ordered, `◆`-prefixed), then built-in presets.
`_on_quick_selected` resolves reference-first then preset. Empty/absent/broken repo →
zero reference rows, presets + manual intact (`_load_reference_specs` swallows repo
errors). Labels are engineering-meaningful (never a DB PK).

## I. W13 integration (production path)

`_wt_add_pipe`/`_wt_edit_pipe` build `AddPipeDialog(reference_repo=
self._drill_pipe_reference_repo())` (lazy; `None` when no `self.db`). Selected
component enters `wt_pipes` → `TorqueDragEngine.calculate` (line ~2382). Verified
end-to-end: persisted spec → dialog fields → component → engine → 165.23 klbf.

## J. Calculation traceability (reported, not changed)

`wt_pipes` stores numeric component values only (`type/od/id/length/weight/...`), not
the source reference identity. A calculation therefore does **not** record which
reference (or manual entry) produced its inputs; editing the catalog later would not
retroactively change any past calculation (values are copied by value). This is
**existing behavior**; capturing reference identity in results is a future
traceability enhancement — NOT implemented (requires a product decision; rule 19/22).

## K. Units

Canonical: OD/ID inches, weight ppf, tensile klbf — identical in domain, record,
component, and engine. `ppf` is never mass-converted. UnitManager untouched.

## L. Failure modes (verified)

Repo unavailable / empty / query exception → presets + manual entry intact, no
misleading data. Malformed/unusable persisted row (no OD or weight) → excluded from
choices (`build_reference_choices`), never becomes a component. Missing grade/
connection → not fabricated (only non-None fields populated).

## M. Test evidence (exact)

* Targeted (spec + repository + selection): **55 passed** (was 53; +2 ordering tests).
* Full regression: **1033 passed / 4 skipped** (baseline 1031/4; +2; 0 regressions,
  no Qt segfault).
* ruff debt **5489** (unchanged); E722=0; F821=0; compileall clean.
* Ground truth re-verified: 5" 19.5 ppf × 3048 m, BF=1−10/65.5=0.8473 → 165.229 klbf
  hand == 165.23 engine.

## N. Remaining risks (evidence-backed only)

1. Calculation-input provenance/traceability gap (J) — past calcs don't record source
   reference identity. Future enhancement; needs product decision.
2. Schema evolution: new *columns* on `drill_pipe_specs` still require a versioned
   migration entry (new *tables* auto-create). `payload_json` protects old data, not
   queryability. Documented limitation; no speculative Alembic added.
3. No production **import UI** yet — the repository is writable only programmatically
   (`import_specs`/`upsert`). This is the next justified product gap (see O).
4. Unicode-NFC identity normalization absent (harmless for ASCII API designations).

## O. Next vertical slice (from evidence)

**A production import path that populates `drill_pipe_specs` from a vendor sheet**,
reusing the existing Excel-import architecture and `DrillPipeSpec.from_vendor_row` +
`repository.import_specs` (which already returns a row-level summary). Rationale: the
read/selection/calculation chain is now complete and certified, but the catalog can
only be filled by code — the single missing arrow for real end-users is
`vendor file → normalized specs → catalog`. This is concrete, evidence-backed, and
does not require a generic framework.

---

## Verdict

**CERTIFIED WITH DOCUMENTED DEBT.**

The DrillPipe reference persistence, identity, ENRICHED/CONFLICT semantics,
concurrency handling, unit safety, UI merge, and W13→T&D calculation path are correct,
deterministic (ordering defect fixed), backward-compatible (PIPE_DB + manual entry
intact), and production-safe with no source-of-truth ambiguity. Documented debt: no
production import UI yet; calculation-input traceability does not record source
reference identity; column-level schema evolution needs manual migration entries;
Unicode-NFC identity normalization absent. None of these are blockers; each is
recorded with an evidence-backed rationale, and the next justified vertical slice
(vendor import) is identified.
