# DrillPipe Reference — Deep Forensic Post-Persistence Audit + Production Selection

Date: 2026-09-13
Mission: Verify the DrillPipe reference persistence is production-grade, then wire
the smallest **real** production slice connecting persisted canonical specs to an
existing engineering workflow.

Baseline entering this iteration: HEAD `1557a08`; full suite **1021 passed /
4 skipped** (this session's starting point; 1009 original + 12 persistence tests);
ruff debt 5489; E722=0; F821=0.

---

## A. Repository Identity

| item | value |
|---|---|
| branch | `arena/01a085e0-drill-master` |
| HEAD (before) | `1557a08` (== remote tip) |
| parent | `2b72ed7` |
| working tree | clean except untracked `.github/workflows/` (never committed) |
| remote | `origin` GitHub `asgareyvazi/Drill-master` |

## B. Previous-report verification

| Claim | Verdict | Evidence |
|---|---|---|
| HEAD is `1557a08` | VERIFIED | `git rev-parse HEAD` == remote tip |
| `DrillPipeSpecRecord` global table, UNIQUE identity | VERIFIED | model read; raw duplicate insert raises `UNIQUE` IntegrityError |
| `identity_fingerprint()` deterministic | VERIFIED | 5/5.0/5.000 collapse; case/space-insensitive; distinct specs differ |
| identity has minor limitation | PARTIALLY VERIFIED | no Unicode NFC normalization (café stays as-is) — documented, low risk |
| `payload_json` lossless round-trip | VERIFIED | extra/provenance/issues survive; columns == payload values |
| ENRICHED non-destructive | VERIFIED | fills only None fields; invalid/unknown incoming → None → no false enrich |
| CONFLICT never overwrites | VERIFIED | stored id/provenance/payload_json unchanged after conflicting upsert |
| import row-isolated | VERIFIED (RowResult path) | per-row `session_scope`; mixed batch keeps good rows |
| "row-isolated" against raised DB errors | FALSE (was) → FIXED | `upsert` did check-then-insert with **no** `IntegrityError` catch (race) |
| table auto-creates on real `initialize()` | VERIFIED | `drill_pipe_specs` + UNIQUE index present after `initialize()` |
| custom "migration" system | PARTIALLY VERIFIED | auto-creates **tables** idempotently; **columns** only via hand-written versioned lists — table-creation + limited migrations, not general schema evolution |
| end-to-end DB→spec→component→T&D proven | VERIFIED | recomputed ground truth 165.229 klbf (hand) == 165.23 (engine) |
| no fabricated/seeded data | VERIFIED | `drill_pipe_specs` empty; only source file is an operational DDR xlsx |

## C. Persistence architecture (actual)

```
DrillPipeSpec (domain, frozen dataclass, storage-agnostic)
   │  to_record_values() / from_record_values()  (bridge, NOT in ORM)
   ▼
DrillPipeReferenceRepository(BaseRepository)   upsert / import_specs / all / get
   │  session_scope() unit of work (commit/rollback/close)
   ▼
DrillPipeSpecRecord (ORM, global scope, UNIQUE identity_fingerprint)
   ▼
SQLite (WAL, FK ON) — table auto-created by DatabaseManager custom migration
```

## D. `drill_pipe_specs` schema

`id` PK; `identity_fingerprint` String(400) NOT NULL **UNIQUE**; canonical columns
`manufacturer/model` (String), `nominal_od_in/nominal_weight_ppf/nominal_id_in/
tool_joint_od_in/tool_joint_id_in/drift_in/tensile_rating_klbf` (Float);
`grade/connection` (String); provenance `source/source_revision/status`;
`payload_json` (Text, lossless snapshot); `created_at/updated_at`; `created_by`→users.
Canonical units: inches, ppf, klbf. Global-scoped (no well/report FK), mirroring
`procedure_templates`/`export_templates`.

## E. Identity / revision

Identity is the normalized tuple (mfr, model, od, weight, grade, connection),
fingerprinted deterministically. Revision A/B with the **same** identity but a
different ID/weight-descriptive value is currently treated as a **CONFLICT** (safe:
never overwrites). A repo-wide `source_revision` field exists on both the domain
`Provenance` and the ORM row; no dedicated revision *table* exists and none was added
(no product rule requires it yet). Verdict: current CONFLICT default is correct until
revisioning requirements exist. Minor limitation: identity text is not Unicode-NFC
normalized (documented).

## F. `payload_json` analysis

Round-trip verified lossless (canonical fields, provenance, issues, unmapped
`extra`). Consistency: columns are written from the *same* spec that produces
`payload_json` in one `to_record_values()` call, so they cannot diverge on write; the
repository never mutates one without the other (ENRICHED writes a full
`to_record_values()`). Not a hidden second database. Schema-evolution behaviour: a new
`DrillPipeSpec` field is preserved for old rows via `payload_json` on read; a new
queryable **column** would require a migration entry (documented limitation — no
versioning framework added).

## G. ENRICHED / CONFLICT semantics (detailed)

* ENRICHED only when incoming carries a descriptive field the stored row lacks
  (`None`→value); existing values are never changed.
* Invalid (`-3.0`, overflow) and unknown (`"n/a"`) incoming values normalize to
  `None` in the domain, so they can never enrich — verified they resolve to UNCHANGED.
* CONFLICT when any shared descriptive field differs materially; stored row fully
  preserved (id, provenance, payload_json).

## H. Transaction / concurrency safety

* Each `upsert` is one `session_scope` (commit/rollback/close) — a per-row
  transaction; `import_specs` therefore isolates rows.
* **Fix applied this iteration:** `upsert` now wraps the check-then-insert and, on a
  UNIQUE `IntegrityError` from a concurrent writer, retries reconciliation against the
  now-present row (`insert_allowed=False`) instead of propagating — resolving to
  UNCHANGED/ENRICHED/CONFLICT. Verified by forcing the IntegrityError branch.
* DB-level UNIQUE(identity_fingerprint) is the race backstop (verified: raw duplicate
  insert raises).

## I. Reference scope

Global reusable-reference precedent confirmed: `procedure_templates`,
`export_templates` (id PK, name, JSON payload, is_default, created_by, no scope FK).
`drill_pipe_specs` follows the same shape. `equipment_logs` is operational inventory
(well/report/section scoped) and correctly NOT the reference master.

## J. W13 production seam (the decisive finding)

Two competing, disconnected drill-pipe reference mechanisms already existed in
production, **neither** connected to the new repository:

1. `dialogs/engineering_dialogs.py::AddPipeDialog.PIPE_DB` — a hard-coded dict of
   ~40 presets feeding a "Quick Select" combo → `wt_pipes` → `TorqueDragEngine`.
   **This is the live reference-selection path** used by W13's Weight/T&D tab.
2. `tabs/w13_Engineering_Calculator.py::_load_drill_pipe_db()` — a raw Excel→pandas
   read-only table viewer that bypasses normalization/persistence entirely.

The T&D calculation reads component dicts `{type, od, id, length, weight}` from
`self.wt_pipes`, built by `AddPipeDialog`. That dialog's Quick Select is therefore the
exact, minimal production insertion point.

## K. Production integration decision — **Option 4 (minimal) + repo race-fix**

Make `AddPipeDialog` Quick Select ALSO offer persisted `DrillPipeReferenceRepository`
records, additively (built-in presets and manual entry both remain). This connects
the last missing arrow `REFERENCE REPOSITORY → REFERENCE SELECTION → COMPONENT →
CALCULATOR` through real production code, with no fabricated data (empty catalog →
dialog identical to before). Also fixed the concurrency correctness gap (H).

Rejected alternatives: a `ReferenceProvider`/generic catalog abstraction (§35 — no
second reference vertical exists yet to justify it); a Database Center / CRUD screen
(§29 — speculative); replacing manual entry (§21 — no catalog may be installed).

## L. Implementation (actual changes)

* `core/repositories/drill_pipe_reference_repository.py` — `upsert` split into an
  outer `IntegrityError`-catching wrapper + `_upsert_once`; race resolves instead of
  raising.
* `dialogs/engineering_dialogs.py` — Qt-free selection LOGIC helpers
  (`build_reference_choices`, `reference_spec_label`, `reference_component_fields`,
  `REFERENCE_LABEL_PREFIX`); `AddPipeDialog(..., reference_repo=None)` offers persisted
  specs in Quick Select (marked `◆`), populating canonical values on selection.
  Manual entry + built-in `PIPE_DB` untouched. Broken/empty repo degrades gracefully.
* `tabs/w13_Engineering_Calculator.py` — `_drill_pipe_reference_repo()` lazily builds
  the repo from `self.db` (None when no DB); `_wt_add_pipe`/`_wt_edit_pipe` pass it in.
* Tests: `tests/test_drillpipe_reference_selection.py` (new); race + UNIQUE tests
  added to `tests/test_drill_pipe_reference_repository.py`.

Design note: selection logic was deliberately extracted from the widget because
constructing a real `QDialog` in the shared headless pytest process is
environmentally fragile (a native Qt abort occurred only under full-suite ordering,
never in isolation). The Qt-free helpers are the real production code path and are
fully unit-tested; the dialog is a thin view over them.

## M. Tests / gates

* Targeted: reference-selection + repository + spec suites green.
* Full regression: **1031 passed / 4 skipped** (baseline 1021; +new tests; 0
  regressions, no segfault).
* Numerical ground truth independently recomputed: 165.229 klbf (hand) == 165.23
  (engine) for 5" 19.5 ppf × 3048 m, BF = 1 − 10/65.5 = 0.8473.
* ruff debt **5489** (unchanged); E722=0; F821=0; new files ruff-clean; compileall OK.

## N. Git

* Files changed: 4 modified + 1 new test + 1 new audit doc. No venv/cache/DB/xlsx/logs
  committed; `.github/workflows/` left untracked.

## Residual / future (documented, not built)

* Identity Unicode-NFC normalization (edge case).
* New queryable columns need a migration entry (payload_json protects data, not
  queryability).
* First real *writer*: a vendor-file import adapter → `import_specs` (the read seam is
  now live; the write seam remains the empty-catalog default until a source exists).
* Calculation-input provenance/traceability (which component value came from a
  reference identity vs manual) is a future `EngineeringResult` enhancement — not
  expanded here (§26/§27).
