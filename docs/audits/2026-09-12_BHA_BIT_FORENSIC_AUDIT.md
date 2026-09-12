# DrillMaster — BHA / Bit Longitudinal Architecture Forensic Audit

Date: 2026-09-12
Branch: `arena/01a085e0-drill-master`
Audited HEAD at start: `560c60d` (Wellbore v3 acceptance audit)
Corrective commit produced by this audit: recorded in §16 / git log

---

## 1. Repository Identity

Repository: `asgareyvazi/Drill-master`. The session started with local history
grafted/reset; the local branch was reconciled to the remote head `560c60d`
(mixed reset, working tree preserved) so ancestry matches the public repo. The
Wellbore v3 commits are present and reachable:

```text
560c60d Add Wellbore v3 forensic acceptance audit report
c0e91b8 Enforce Wellbore ownership integrity and close physical-FK gap
8a3d750 Introduce canonical Wellbore entity and migrate to schema v3
b31ea83 Correct commit topology in CI operationalization audit
```

## 2. Branch / HEAD

```text
branch:          arena/01a085e0-drill-master
HEAD (at start): 560c60d
working tree:    clean except untracked .github/workflows/ (CI track, blocked by
                 the GitHub App `workflows` permission — out of scope here)
```

## 3. Baseline Test Result (before any change)

```text
pytest:  885 passed, 4 skipped, 0 failed, 0 error   (~191s)
compile: OK (compileall core dialogs tabs tests)
E722:    0
F821:    0
ruff debt (core dialogs tabs tests, summed --statistics): 5489  (ceiling 5489)
python 3.11.2 · ruff 0.16.6 · pytest 9.1.1
```

## 4. Current BHA Architecture (as actually implemented)

`BHAReport` (`core/database.py`):

```text
id, well_id (FK wells, NOT NULL), report_id (FK daily_reports, nullable, CASCADE),
bha_name (NOT NULL), bha_data_json (JSON), created_at, updated_at
```

* BHA is a **per-daily-report snapshot**, not a longitudinal Run entity. Import
  and `save_bha_report` upsert **keyed on `report_id`** (one BHA row per DDR).
* Components live inside `bha_data_json` as an **ordered JSON list**
  (`bha_records`/`bha_record` in `core/domain_records.py`), preserving component
  order, tool type, OD/ID, length, serial, etc., as supplied. No separate
  component table, no serialized-equipment catalog.
* No `wellbore_id` / `section_id` column: wellbore/section context is carried
  **transitively** through `report_id → DailyReport.{wellbore_id, section_id}`.

## 5. Current Bit Architecture

`BitReport` (`core/database.py`):

```text
id, well_id (FK wells, NOT NULL), report_id (FK daily_reports, nullable, CASCADE),
report_date (NOT NULL), report_name, bit_records_json (JSON), created_at, updated_at
```

* Bit is likewise a **per-daily-report snapshot** keyed on `report_id`.
* Bit specification (size, type, IADC, serial, nozzles, manufacturer) and
  per-day run observations (depth, footage, hours, dull) are both carried inside
  `bit_records_json`. There is **no separate Bit-specification vs Bit-Run
  entity**, and **no separate physical-bit catalog** — identity is expressed by
  the serial/bit number recorded in the JSON, repeated across daily snapshots.

`DownholeEquipment` follows the identical snapshot pattern.

## 6. Entity Relationship Map

```text
Well (1) ─────< BHAReport         (well_id NOT NULL, report_id nullable)
Well (1) ─────< BitReport         (well_id NOT NULL, report_id nullable)
Well (1) ─────< DownholeEquipment (well_id NOT NULL, report_id nullable)

DailyReport (1) ─────< BHAReport / BitReport / DownholeEquipment  (report_id, CASCADE)
DailyReport ── wellbore_id ──> Wellbore ── well_id ──> Well
DailyReport ── section_id  ──> Section

=> BHA/Bit wellbore & section context is derived via report_id, not stored directly.
```

## 7. Identity Rules (as found)

* BHA snapshot identity = `report_id` (one per DDR); run continuity = stable
  `bha_name` repeated across snapshots.
* Bit snapshot identity = `report_id`; physical-bit continuity = serial / bit
  number inside `bit_records_json`.
* **Rig is never an identity key** for BHA/Bit (searched: no rig field
  participates in any BHA/Bit query, upsert, or dedup). Confirmed by test
  `test_rig_is_not_bha_bit_identity`.
* No fuzzy merging: identical model/size across DDRs are separate snapshots, and
  are only "the same run" to the extent the source repeats the same name/serial.

## 8. Ownership Rules

* Correct owner of a BHA/Bit **snapshot** is the **DailyReport** (hence Section
  and Wellbore transitively), with `well_id` as a denormalized guard column.
* `save_bha_report`, `save_downhole_equipment`, `save_formation_report` enforce
  `well_id == report.well_id` via `_require_report_well`. **`save_bit_report`
  did not** (Defect BHA-01, fixed).
* No persistence-boundary guard existed for BHA/Bit/Downhole, so a direct ORM
  flush could commit a snapshot whose `well_id` disagreed with its report
  (Defect BHA-02, fixed).

## 9. Import Source Lineage

```text
DDR (Excel/PDF) → extraction → normalization (core/domain_records: bha_record,
bha_records, named_record) → canonical extracted dict (bha_report / bha_components
/ bit_report / downhole_equipment) → DatabaseManager.save_imported_multi_tab_data_atomic
→ upsert keyed on report_id (well_id, report_id set from the SAME resolved well)
→ BHAReport / BitReport / DownholeEquipment rows.
```

* Because the importer always sets `well_id` and `report_id` from the one
  resolved well/report, the import path cannot produce a cross-well snapshot —
  verified: the full suite (including import tests) stays green with the new
  guard active.
* No-fabrication preserved: unmapped BHA/Bit fields raise review issues rather
  than inventing values; missing values stay `None`.

## 10. Multi-DDR Continuity Behaviour

A single physical BHA/Bit run spanning DDR 101–104 produces **four snapshots**
(one per DDR), each carrying the same `bha_name`/serial. This is the documented,
intended model (asserted by `test_well_centric_acceptance.py`:
"one snapshot per DDR for the same run"). It is a deliberate design, not a
defect. Limitation: there is no first-class Run entity, so cross-DDR run
aggregation must be computed from the shared name/serial (see §19 Remaining
Risks).

## 11. Re-import / Idempotency Behaviour

Re-importing the same DDR does **not** duplicate BHA/Bit rows (upsert on
`report_id`). Verified: `test_reimport_is_idempotent` (1 well, 1 report, 1 BHA,
1 Bit after a double import).

## 12. Sidetrack Isolation

Original-bore and sidetrack DDRs on one well — with identical section name, bit
size, BHA name, and rig — produce **separate** snapshots that map (via their
reports) to **distinct wellbores**. Verified:
`test_sidetrack_snapshots_isolated_from_original` (two bores, each BHA snapshot
resolves to exactly one, and the two differ). No cross-wellbore merge.

## 13. Physical SQLite Schema Verification

Confirmed with `PRAGMA table_info` / `foreign_key_list` / `foreign_key_check`:

* Fresh DB — `bha_reports`, `bit_reports`, `downhole_equipment` each carry
  **physical FKs**: `well_id → wells(id)` and `report_id → daily_reports(id)`
  (ON DELETE CASCADE). `report_id` nullable, `well_id` NOT NULL.
* Upgraded v2→v3 DB — the same physical FKs are **preserved** (these tables are
  not touched by the v3 upgrade, so unlike the newly-added `wellbore_id` columns
  they never lost their inline FKs). `foreign_key_check` empty.
* No unique indexes — consistent with the per-DDR snapshot model (dedup is by
  `report_id` upsert, not a DB constraint).

## 14. Defects Discovered

### BHA-01 — `save_bit_report` missing report/well ownership guard — HIGH
```text
ID:                BHA-01
Severity:          HIGH
Observed:          save_bit_report(well_A, {report_id: report_of_well_B, ...})
                   created a BitReport with well_id=A but report_id pointing to
                   well B. The sibling saves (BHA, Downhole, Formation) all call
                   _require_report_well; Bit alone omitted it.
Expected:          A bit snapshot must belong to the same well as its report;
                   the mismatch must be rejected.
Root cause:        Copy-paste divergence — the guard added to the other report-
                   scoped saves was never added to save_bit_report.
Evidence:          Probe B1 (well_id=1, report belongs to well 2 → accepted).
Fix:               Added self._require_report_well(...) at the top of
                   save_bit_report; the method now re-raises ownership errors
                   instead of swallowing them into None.
Regression test:   TestServiceOwnershipGuards::test_save_bit_report_rejects_cross_well_report
Verification:      Test passes; probe now raises ValueError.
```

### BHA-02 — No persistence-boundary ownership guard for BHA/Bit/Downhole — MEDIUM
```text
ID:                BHA-02
Severity:          MEDIUM
Observed:          A direct ORM flush of BitReport/BHAReport/DownholeEquipment
                   with well_id != report.well_id committed successfully. Only
                   the service helpers guarded ownership, so any non-helper save
                   path (or a future caller) could bypass it — inconsistent with
                   the Wellbore v3 chain, which is enforced at before_flush.
Expected:          The (well_id, report_id) coherence must hold at the
                   persistence boundary, on every save path.
Root cause:        The before_flush invariant added in Wellbore v3 covered only
                   Wellbore/Section/DailyReport, not the report-scoped snapshots.
Evidence:          Probe B3 (ORM cross-well BitReport accepted).
Fix:               Extended _enforce_ownership_integrity with
                   _check_report_scoped_well_ownership for BHAReport, BitReport,
                   DownholeEquipment: when report_id is set, well_id must equal
                   the report's well_id. NULL report_id (well-level snapshot) is
                   left valid — no fabricated ownership.
Regression test:   TestPersistenceBoundary::* (cross-well rejected for all three;
                   matching well and NULL report_id allowed).
Verification:      Tests pass; full suite green with the guard active.
```

No other defects were found. The per-DDR snapshot model, the transitive
wellbore/section linkage, re-import idempotency, sidetrack isolation, rig
non-identity, and the physical FKs are all correct and were left unchanged.

## 15. Root Causes (summary)

Both defects are the same class the Wellbore v3 audit addressed: a foreign key
proves a row exists but not that the owning `well_id` agrees. BHA-01 was a
missing service-layer guard; BHA-02 was the absence of the persistence-boundary
backstop for the report-scoped snapshot tables.

## 16. Fixes Made

All changes confined to `core/database.py` (production) plus one new test file:

* `save_bit_report`: added `_require_report_well` guard; re-raise
  `OwnershipIntegrityError`/`ValueError` instead of returning `None`.
* New module-level helpers `_resolve_daily_report` and
  `_check_report_scoped_well_ownership`; `_REPORT_SCOPED_WELL_MODELS` tuple;
  extended the existing `before_flush` `_enforce_ownership_integrity` dispatcher
  to cover BHAReport / BitReport / DownholeEquipment.

No schema change, no migration, no new entity, no UI/tab restructuring — the
established snapshot architecture is preserved.

## 17. Tests Added

`tests/test_bha_bit_ownership_integrity.py` (14 tests):
service-layer cross-well guards (Bit/BHA/Downhole + same-well OK);
persistence-boundary guards (ORM cross-well rejected for all three, matching
well OK, NULL report_id OK); longitudinal import behaviour (per-DDR snapshots,
re-import idempotency, sidetrack isolation, rig non-identity); physical-schema
FK verification.

## 18. Full Regression Result (after fixes)

```text
pytest:  899 passed, 4 skipped, 0 failed, 0 error   (~185s)
compile: OK
E722:    0
F821:    0
ruff debt (core dialogs tabs tests): 5489  (ceiling 5489 — unchanged, neutral)
```

No tests deleted, no assertions weakened, no new skip/xfail, ceiling unchanged.
Existing no-fabrication (`test_schematic_no_fabrication`, inventory zero
semantics) and Wellbore v3 integrity tests remain green.

## 19. Remaining Risks

* **No first-class BHA Run / Bit Run entity.** Run continuity across DDRs is
  implicit (shared `bha_name` / serial in JSON). This is adequate for daily
  reporting and does not block a future canonical KPI/Cost layer, but that
  layer will need to *derive* run aggregates by grouping snapshots on
  well/wellbore + name/serial + contiguous depth/date. If future requirements
  demand authoritative run-level footage/hours/dull with edit history, a
  dedicated `bha_runs` / `bit_runs` table (snapshots referencing a run_id) would
  be the correct next step — deliberately **not** done here (no demonstrated
  defect; §27 change policy).
* **Component data lives in JSON**, so there is no per-component FK/serial
  uniqueness at the DB level. Order and fields are preserved; cross-run
  component tracking (serialized-equipment reuse) is not modelled.
* **`report_id` nullable** permits a well-level snapshot with no wellbore/section
  context; this is intended for legacy/partial data and preserves "unknown", but
  such rows carry no bore attribution by design.

## 20. Certification Gates (A–R)

| Gate | Result | Evidence |
| --- | --- | --- |
| A — Repository identity | PASS | §1 (Wellbore commits present; branch reconciled to remote) |
| B — Baseline regression | PASS | §3 (885/4, clean) |
| C — BHA entity integrity | PASS | §4; cross-well now rejected (BHA-01/02) |
| D — Bit entity integrity | PASS | §5; BHA-01 fixed |
| E — Well ownership | PASS | §8; `well_id` NOT NULL + guards |
| F — Wellbore ownership | PASS | §12; transitive via report, sidetrack-isolated |
| G — Section ownership | PASS | §6; transitive via report_id → section_id |
| H — BHA longitudinal identity | PARTIAL | §10/§19; per-DDR snapshot, no Run entity (by design) |
| I — Bit longitudinal identity | PARTIAL | §10/§19; per-DDR snapshot, no Run entity (by design) |
| J — Multi-DDR continuity | PASS | §10; deterministic per-DDR snapshots |
| K — Re-import idempotency | PASS | §11; verified no duplication |
| L — Sidetrack isolation | PASS | §12; distinct wellbores, no merge |
| M — Physical SQLite constraints | PASS | §13; well_id + report_id FKs, fresh & upgraded |
| N — Migration safety | PASS | §13; FKs preserved on upgrade, foreign_key_check empty |
| O — Import lineage | PASS | §9; deterministic, no fabrication |
| P — API/service integrity | PASS | §14–16; Bit guard added, no swallowed ownership errors |
| Q — Full regression | PASS | §18 (899/4, gates green, debt neutral) |
| R — Production-readiness | PASS WITH REMAINING RISKS | §19; safe foundation, Run-entity deferred |

## 21. CI

```text
REMOTE CI = BLOCKED / NOT OBSERVED
```

The `.github/workflows/ci.yml` push remains blocked by the missing GitHub App
`workflows` permission; no Actions run exists. All results here are local and
are not represented as remote CI.

---

## Final Certification

```text
BHA / BIT ARCHITECTURE = PASS WITH REMAINING RISKS
REMOTE CI = BLOCKED / NOT OBSERVED
```

Rationale: BHA and Bit are Well-centric, Wellbore-aware (transitively, via each
snapshot's report), import-safe, re-import-idempotent, sidetrack-isolated, and
now ownership-consistent at both the service layer and the persistence boundary
on every save path. Two real ownership defects (one HIGH) were found and fixed
with minimal, architecture-preserving changes, backed by regression tests, with
no data loss and no fabricated identity. The single reason this is "PASS WITH
REMAINING RISKS" rather than an unqualified PASS is the absence of a first-class
BHA Run / Bit Run entity: the current per-DDR snapshot model is correct and
adequate today and does not block a future canonical Cost/KPI/Engineering layer,
but that layer will need to derive run aggregates from snapshots (or introduce
explicit run tables) — a deliberate, documented deferral, not a defect.
