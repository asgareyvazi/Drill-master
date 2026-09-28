> **HISTORICAL MISSION RECORD (Mission 27).** This file is preserved unedited as the evidence it produced. Its counts, hashes and verdicts describe the tree at that time and are superseded by the Mission 33 re-adjudication — see [M33_SEMANTIC_AUDIT.md](../../M33_SEMANTIC_AUDIT.md) and [M33_RELEASE_CERTIFICATION.md](../../M33_RELEASE_CERTIFICATION.md).

> **Historical audit.** Superseded for current readiness by [Mission 28](2026-09-22_M28_FORENSIC_RELEASE_GATE.md). Its tested implementation, certificate commit and current remote state are distinguished explicitly there.

# M27 independent forensic re-audit, repairs and release decision

**Date:** 2026-09-22 (UTC)  
**Decision: NOT RELEASE-CERTIFIABLE**  
**Audited base HEAD:** `c28bbef37cbac9de7abcfa693e7e21f678fa74ab`  
**Working branch:** `arena/01a0c945-drill-master`  
**Evidence boundary:** Linux source + exact runtime lock + offscreen Qt **stub** libraries + Python wheel; not Windows, an installed/frozen GUI, or production acceptance.

This report supersedes current-release interpretations of the earlier M26/M27
certificates. It does not retroactively endorse their test runs. Changes in this
session are a **working-tree patch on the above HEAD**, not a new committed SHA.
The source manifest and final source-gate transcript identify the tested files.
No commit, push, branch switch, reset, merge or branch deletion was performed.

## 1. Executive result

Material defects were reproduced and repaired in ownership enforcement,
attribution, report selection, NULL-time aggregation, exports, snapshot copying,
selection state, test isolation and release verification. The source gate is
stronger than compile+pytest and passes within its declared environment.

**Nevertheless, green source tests do not certify this product for release.**
There are demonstrated residual cost/plan/safety semantic defects (§8), no
remote CI result for this patch, no clean committed release artifact, and no
real Windows/installer/MinerU/production-DB acceptance. These are separate
limitations; the code defects are not excused as environment limitations.

Scope of the audit: repository-wide history/search/discovery, targeted deep
call/data-flow review and executable regression verification. This is **not a
claim that every leaf function, numerical formula, exception handler, third-party
provider or GUI interaction has been exhaustively verified**. PARTIAL below
means exactly that; previous COMPLETE labels do not upgrade the evidence.

## 2. Repository reality

Commands executed before editing: `git status --short`, `git branch -vv`,
`git log --oneline --decorate -30`, `git remote -v`, `git rev-parse HEAD`,
`git diff`, `git diff --cached`, and `git ls-files` (507 tracked files).

- Initial worktree/index: clean; no untracked files.
- Initial clone: shallow/grafted at `c28bbef`. `git fetch --unshallow origin`
  recovered history; all remote heads were fetched into remote-tracking refs.
- Remote: `https://github.com/asgareyvazi/Drill-master.git`.
- Session branch has no upstream. This is a new, unpublished session branch,
  not evidence of a successful deployment/tracking relationship.
- Requested predecessor `origin/arena/01a085e0-drill-master` is **also at
  `c28bbef`**, not reported `3f52e2e`. The latter is an ancestor.
- Base already contains `95dd631` (lint/doc changes) and `c28bbef` (an earlier
  M27 certificate). Both were re-audited rather than trusted.
- Final worktree: intentional source/tests/docs/workflow changes; new files
  listed by Git. No original user edits were overwritten. `.venv`, wheel/build
  outputs and caches are ignored, not release evidence committed into source.

### Branch classification (freshly fetched)

`HEAD-only / branch-only` is `git rev-list --left-right --count HEAD...origin/NAME`
at the audited base. Ancestor status proves reachable content, not permission
to delete someone else's active collaboration branch.

| Branch | Remote tip | Divergence | Classification | Evidence / action |
|---|---|---:|---|---|
| `arena/01a0c945-drill-master` | local `c28bbef` | — | ACTIVE | Current session; retain |
| `arena/01a085e0-drill-master` | `c28bbef` | 0 / 0 | ACTIVE | Requested predecessor, same tree; retain |
| `arena/01a056c5-drill-master` | `02dd3e1` | 99 / 0 | MERGED-SAFE-TO-DELETE | Ancestor, no unique reachable commits; not deleted |
| `arena/01a05747-drill-master` | `c7e7697` | 90 / 0 | MERGED-SAFE-TO-DELETE | Ancestor, no unique reachable commits; not deleted |
| `arena/01a07094-drill-master` | `ad7ea0d` | 70 / 0 | MERGED-SAFE-TO-DELETE | Ancestor, no unique reachable commits; not deleted |
| `arena/01a0801f-drill-master` | `b05ea76` | 65 / 0 | MERGED-SAFE-TO-DELETE | Ancestor, no unique reachable commits; not deleted |
| `drill-Master` | `02053eb` | 94 / 3 | UNMERGED-REVIEW-REQUIRED | Two merge commits and unique PDF upload `02053eb`; retain |

`drill-Master`'s unique document is
`12 - DDR OEOC-201 AZNS-166 2025-Nov-07 (1404.08.16).pdf` (740,510 bytes).
It was identified from the commit tree; not imported or silently copied into
this branch, and not counted as executed real-PDF acceptance.

## 3. Independent M24–M27 reconstruction

History inspected includes `2722020..8e176fa` and the required `8e176fa..HEAD`.
The latter has ten commits, ending at `c28bbef`, not the older M26 tip.

| Claim → commit | Implementation / consumer trace | Tests / audit outcome |
|---|---|---|
| W7 three-state stock → `0527e95` | fuel/water semantics → W7 inputs/persistence/display | `test_w7_null_zero_semantics`, W7 subprocess smoke; no replacement stock model added |
| Bore-aware W12, milestones → `74e1246` | W12 scope helpers → DailyReport/DrillingParameters FK queries → charts; section planned_days, not depth/50 | W12 scope/milestone tests pass; latest-report/section/NULL-time gaps independently fixed here |
| Import→selection retains bore → `dd34ad9` | atomic import result → `_targeted_refresh` → `select_full_context` → bore/section/report | import-to-selection domain and subprocess tests; no guessed bore added |
| Bore identity reconciliation → `302c253` | `get_or_create_wellbore` → `_reconcile_wellbore_identity` → importer | discriminator and identity-conflict tests; conflicting identities remain errors |
| Export scope metadata → `bba9324` | report engines collect well-level data → HTML/Excel consumers | report scope metadata tests pass; labels do not prove all NULL/cost reductions correct |
| Whole-well UI labels → `2949d5b` | Planning/AFE/export UI wrappers, not new numerical engines | whole-well label tests; cost remains well-scoped |
| M25 certification → `8e176fa` | document only | Not runtime implementation evidence |
| Ambiguous legacy children → `9c7720a` | W12 legacy well/date fallback rejects >1 row | Existing tests pass; did not handle >1 *linked* child or >1 report; repaired here |
| NPT NULL entries → `048faf3` | W12 keeps entry duration None and an unknown counter | Still published a partial sum as total/percentage; repaired with shared reducer |
| Missing depth → `7133723` | both Intelligence scopes use None without depth observations | Tests pass; daily progress and time reductions had remaining fabrication |
| Risk unknown inputs → `4f6e69e` | W12 `_risk_scores` → NOT ASSESSED | Risk tests pass; not proof of complete safety analytics correctness |
| Whole-well plan/intelligence labels → `2fe16b2` | W12 whole-well service callers and labels | Correct intended scope; plan numerical gaps remain (§8) |
| All report-linked owners → `f4bfd33` | structural discovery → `before_flush` → child scalar-FK validation | Covered 30 models, not parent edits or relationship synchronization; repaired here |
| Attribution 2-bores/1-section → `7a3bb4a` | **test-only** convergence coverage | Not a runtime fix; retained two-pass convergence + third-pass stability |
| M26 certification → `3f52e2e` | document only | Implementation tip `7a3bb4a` vs certification tip `3f52e2e` is valid historical distinction |
| Lint cleanup → `95dd631` | removal of imports in 107 files | **Not entirely behavior-neutral:** three release tests became vacuous; restored |
| Prior M27 certificate → `c28bbef` | document only | Workflow absent; lock-Python-3.10 claim disproved; superseded |

M26's SHA distinction was already corrected by `95dd631`. The new issue was
presenting a past tip/certificate as current repository reality. This report
keeps implementation tip, certificate commit, base HEAD and worktree changes
separate.

## 4. Findings and actual repairs

Each entry lists severity, root cause, affected implementation, impact and
verification. Unless explicitly called out as static-only, tests below ran
against real SQLAlchemy/SQLite or actual production reader functions, not a
mocked numerical result.

### F01 — HIGH — Parent ownership edits stranded unchanged children

- File/functions: `core/database.py`, `_enforce_ownership_integrity`, hierarchy
  checks. Only new/dirty child rows were checked. Moving a DailyReport to a
  different well, moving a Section to another bore, or moving a Wellbore to
  another well could leave existing dependents contradictory.
- Fix: query/revalidate affected dependents only on ownership changes, using
  the identity map so simultaneous coherent edits work. Deleted rows excluded.
- Evidence: three new parameterized cases failed before the fix; now rollback
  prevents corruption. Coherent same-transaction moves pass.
- Tests: `tests/test_ownership_parent_edits.py`, existing wellbore and M26
  ownership suites.

### F02 — HIGH — ORM relationship assignment bypassed `before_flush`

- File/functions: same guard; SQLAlchemy synchronizes relationship FK columns
  during flush. `SafetyReport(well_id=A, report=report_of_B)` had report_id NULL
  when checked, then committed a cross-well row.
- Evidence: independent in-memory reproduction printed persisted well 1 versus
  report well 2 on the old guard.
- Fix: retain affected objects, validate synchronized values in
  `after_flush_postexec` before transaction commit, clear pending state on
  rollback; defer early checks on relationship edits to avoid rejecting a
  coherent relationship/scalar move.
- Tests: new and existing relationship assignment, coherent parent/child move,
  rollback and unchanged-child tests. NULL report_id still infers nothing.

### F03 — HIGH — Legacy/raw-SQL contradictions were accepted on startup

- Single-column FKs check existence, not owner agreement. Raw SQL is outside ORM
  events; an externally corrupted file could reopen successfully.
- Fix: `_verify_stored_ownership` joins hierarchy and all structurally discovered
  report-linked owner pairs inside the schema-upgrade transaction. Contradiction
  fails initialization explicitly, without repair/backfill or rewriting owners.
- Test: disposable file database, raw SQL mismatch satisfying ordinary FKs,
  reopen rejected, original row retained. Existing migration/null/credential
  suites pass. Live raw/bulk SQL remains outside the supported ORM write guard;
  no new DB-trigger framework was invented.

### F04 — HIGH — Attribution preview/apply inconsistency and wrong-bore fallback

- File: `core/scope_attribution.py`, `_compute`, `_classify_section`.
- A known bore with no sections could be assigned its sibling's sole section.
  Analyze used the pre-resolution bore while apply used the just-written bore.
  Existing foreign-well owners could be counted as ALREADY/covered.
- Fix: shared hypothetical effective bore; filter incompatible section
  candidates; classify contradictory existing ownership INVALID for both
  dimensions and perform no writes. Analyze/coverage remain read-only.
- Four new cases failed before repair. Tests cover filtered/unfiltered scans,
  preview/apply parity, wrong-bore sole section, existing legacy contradictions,
  1:1, 1:many, many:1, many:many and repeated execution.
- Explicit boundary: two bores + one section + NULL/NULL still resolves section
  on pass 1, bore via section on pass 2, then stabilizes on pass 3. It is
  convergent, **not** a promise of single-pass full attribution. Production
  search found `coverage()` in data quality, no automatic `resolve()` caller.

### F05 — HIGH — W12 guessed a report/linked child and could show another section

- File/functions: `tabs/w12_Analysis.py`, `get_today_data`, legacy fallback,
  report/section selection handlers and daily-card rendering.
- `.first()` selected between same-date reports and linked parameter/mud rows;
  legacy fallback did not restrict report_id to NULL. Bore-wide daily lookup
  could ignore selected section. Cached daily cards could outlive selection.
- Fix: explicitly selected report must match scope; otherwise require a unique
  report on the latest scoped date. Multiple linked rows yield unknown, not a
  fallback. Legacy rows must have NULL report_id. Daily cards additionally filter
  the selected section, while aggregate KPI/chart queries deliberately remain
  bore-wide. Clear caches on report/section change and stale card text on no
  result; absent main activity displays “—”, not invented “Drilling”.
- Tests: same-date ambiguity, explicit report outside bore, duplicate linked
  parameters, selected-section daily cards versus bore-wide aggregate, legacy
  compatibility; existing W12 and import/selection subprocess smoke.

### F06 — HIGH — Unknown duration became zero/partial-complete time facts

- Files: `core/operations_intelligence.py`, W12, W16 allocation consumer,
  `core/report_engine.py` DDR/EOWR/NPT paths.
- `duration or 0` and SQL SUM hid missing rows; NPT percentage used incomplete
  denominators. Explicit zero productive hours could incorrectly become None.
- Fix: small Qt-free `core/operational_time.py::summarize_time_logs` shared by
  these readers. Empty rows mean unknown; explicit zero remains zero; missing,
  negative or nonfinite duration cannot form a complete total. Known subtotal
  and unknown counters are separate. NULL NPT classification is not productive.
  NPT may remain known when only a productive duration is missing, but its
  percentage/total/productive duration remain unknown.
- W12's previously green partial-total test now asserts `total_npt=None`,
  `known_npt_hours=2`, and unknown percentage. This changes the erroneous
  expectation, not the evidence to match a false green.
- Tests: all three service scopes, empty/NULL/zero/positive/mixed time, W12,
  report parity. Negative control substituted the HEAD service (only adding a
  total-hours output alias): **4 failures / 1 pass**, confirming the new tests
  detect the old numerical behavior; see evidence transcript.

### F07 — MEDIUM — NPT period/export inconsistency and empty-time crash

- File: `core/report_engine.py`, `NPTReportEngine`.
- Period-filtered numerator used whole-well report_count; actual cost with no
  logs compared `None > 0`, causing collection failure. HTML/Excel formatters
  assumed all durations/totals numeric.
- Fix: report count uses identical date limits; use shared time reducer and
  canonical NPT allocation; withhold period cost allocation when whole-well
  costs have no proven period attribution. Unknown totals, category values,
  events and percentages render blank/“—”; no independent export recalculation.
- Tests: actual openpyxl output inspected, HTML built for NULL/zero/positive,
  no-time + stored-cost case, period count and no whole-well-cost allocation to
  a date subset. PDF uses the same HTML, but real Windows PDF rendering is not
  certified by these tests.

### F08 — MEDIUM — Fabricated progress and loss of explicit mud zero

- File: `core/operations_intelligence.py::analyze_well`.
- One depth or gaps in dates were presented as daily progress; truthiness
  removed known zero PV/mud observations; all-NULL cost values became zero.
- Fix: progress requires two consecutive dated reports with known endpoints;
  use explicit None checks for trends and known cost values.
- Test: missing/one/zero-progress depth observations; existing trend and KPI
  regression suites. Whole-well multi-bore daily progress still needs a business
  definition (§8); no claim of complete cross-bore progress correctness.

### F09 — MEDIUM — Snapshot JSON aliasing before persistence

- File: `core/report_snapshot.py::serialize_value` returned the original list/
  dictionary. Nested edits could mutate a not-yet-persisted historical snapshot.
- Fix: deep-copy JSON containers. Neither reference nor result is promoted to
  historical input.
- Test: mutate live nested values and returned nested snapshot in both
  directions; each remains independent. Existing lifecycle snapshot tests pass.

### F10 — HIGH — Selection accepted a report from a different section

- File: `core/selection_manager.py::_ownership_conflict`, all selection methods.
- Well/bore guards omitted section; selecting a new ID without payload retained
  the old entity's data/name.
- Fix: explicit report/section conflict rejected; changed ID without new payload
  resets payload to `{}`. Unknown owner fields still do not fabricate identity.
- Evidence: section-conflict + four entity-payload cases failed before repair;
  now pass alongside existing cascade/restore/import tests.

### F11 — HIGH — Prior lint cleanup erased executable import checks

- Commit/file: `95dd631`, `tests/test_release.py`.
- Three checks had only `assert True` after F401 autofix removed their test
  actions. Test count stayed unchanged, so prior “behavior-neutral” claim was
  false for verification behavior.
- Fix: importlib imports with actual assertions, explicit public-symbol checks,
  and fresh-process cycle smoke. No unused-import autofix can erase the actions.
- Tests: restored tests run in the full suite and in the targeted release run.

### F12 — HIGH — Explicit ENV disabled pytest database isolation

- File: `tests/conftest.py`; data-path isolation occurred only if ENV was unset.
- Fix: always allocate temporary data/DB/config/log/backup paths; preserve the
  explicit mode and restore the prior environment afterward. Explicit
  production credential tests can still exercise fail-closed behavior without
  touching an operator database.
- Tests: sentinel operator file preserved for test/development/production modes,
  plus credential and package-smoke isolation suites.

### F13 — MEDIUM — Release gate accepted incomplete evidence

- File: `verify_release.py`; previously compile+collect+pytest, allowed xfail/
  xpass and mismatched accounting; no identity/dependency/build checks.
- Fix: full SHA/worktree check (dirty requires explicit development opt-in),
  runtime pin checks + pip check, required JSON/resources, E722/F821, pinned
  historical lint population/ceiling, compile, collection/result accounting,
  xfail/xpass/deselection rejection, real wheel build and resource/test exclusion
  checks. Output explicitly excludes Windows/production acceptance.
- Tests: 11 gate negative cases, corrected old inconsistent collection mock,
  actual dirty-worktree refusal, final successful development gate.
- Scope limit: no cryptographic dependency hashes, external build isolation
  resolves setuptools/wheel, and no Windows binary reproducibility claim.

### F14 — MEDIUM — Lock/CI/Windows runbook contradicted source

- `requirements-lock.txt` claims Python 3.10 but contourpy 1.3.3 cannot resolve
  for 3.10. Exact 3.11 lock installs and tests; 3.12/3.13 wheel-resolution checks
  only, not runtime execution. Pins were **not** changed merely to fit the host.
- Header/docs now state locked 3.11–3.13; package metadata still declares a
  wider ranged-dependency source compatibility window (not independently
  certified on 3.10).
- CI file absent at base HEAD despite living-document claims. Added minimal
  read-only workflow with 3.11/3.12/3.13 matrix, real Qt libraries, pinned test
  tooling and the source gate. No remote run/push has been claimed.
- Windows build default now matches documented Python 3.12; explicit native
  exit-code checks prevent pip/PyInstaller failure from flowing to a success
  message; mismatched reused virtualenv rejected. PowerShell changes have only
  static/source test evidence here, **not Windows execution**.
- Acceptance runbook installs missing pytest/build tools, checks native failures,
  configures MinerU's separate integration input and lists real installer/
  upgrade/uninstall requirements. Supplied nonexistent DDR path now fails rather
  than skipping. Optional unset paths still skip honestly.

### F15 — LOW — Provably shadowed/duplicate declarations

- Removed `CalculatorBridge.mse = MSEEngine`, already overwritten in the same
  class by callable `mse(**kwargs)`. Actual AI caller uses that method; method
  unchanged. Removed duplicate identical `m3` volume conversion dictionary key.
- These are the only dead-code deletions, aside from replacement of defective
  code. No unique legacy module, migration, artifact or branch was deleted.

## 5. Architecture, call graphs and consumers

### Reference ≠ historical input ≠ derived result

Reviewed chains:

- DrillPipe workbook → header/row parser (`drill_pipe_import`) →
  `DrillPipeSpec.from_vendor_row` → normalized identity/provenance →
  `DrillPipeReferenceRepository.import_specs` → DB reference catalog → selector
  → copied component inputs → `TorqueDragEngine` → historical calculation repo.
  Imports are intentionally per-row upserts with outcome counts, **not** a
  whole-workbook atomic transaction. Conflicts are not silent overwrites.
- T&D snapshot stores survey/components/parameters and reference fingerprints;
  replay reads the snapshot, not current master. Casing/Cement/Well Control/MSE/
  Mud Volume have separate persisted input/result records and verification paths.
- Daily report revision builder reads report-owned children. Engineering histories
  are independently versioned, not fed back as DDR source input. Nested JSON
  detachment was the concrete aliasing repair here.
- Tests independently executed include reference conflict/idempotence/normalization,
  catalog selection, persistence and cross-process replay suites, plus snapshot/
  lifecycle tests. This does not certify every catalog vendor or every historical
  production file; master/current/reference semantics remain PARTIAL as a
  repository-wide assertion.

### Engineering capability classification

| Capability | Runtime chain reviewed | Persistence / tested boundary | Classification |
|---|---|---|---|
| Anti-collision | W13/widget + AI → bridge → AntiCollisionEngine | Engine/UI smoke; no universal historical slice claimed | PARTIAL / SCREENING, no ISCWSA certification |
| Torque & Drag | UI/AI → bridge → TorqueDragEngine → result | T&D repository, history, cross-process tests | PARTIAL soft-string screening |
| Casing | W13 → CasingEngine.evaluate → result | Casing repository/replay/ground-truth tests | PARTIAL, not full API/connection qualification |
| Cement | W13/AI → CementEngine.job_volumes → result | Cement repository/replay/worksheet tests | Implemented worksheet, PARTIAL design |
| Fishing | facade/UI → FishingEngine | Ground-truth/integration tests; no dedicated history asserted | PARTIAL / SCREENING |
| Well control | legacy facade/W13 → canonical WellControlEngine; composite kill sheet | Kill-sheet repository/replay and ICP/FCP consolidation tests | Implemented calculation kit, not operational field acceptance |
| Trajectory | UI/facades → canonical MCM core | parity/validation tests, trajectory records | Implemented MCM, uncertainty outside scope |
| Mud | UI → volume/rheology/hydraulics engines | Mud-volume persisted slice + calculator tests | Implemented deterministic subset |
| Bit/MSE | UI/AI → BitPerformanceEngine/MSEEngine/hydraulics | MSE persisted slice + weighted ROP tests | Implemented subset, not universal performance prediction |
| Actual/plan | DB aggregation → ActualVsPlanEngine → W12/exports | Tests exist; residual aggregation semantics below | PARTIAL |
| Cost/economics | CostRecord → cost semantics/UI/report reductions | AFE and known-cost tests, no NPV/payroll engine | PARTIAL; mixed currency unresolved |

`require_number`/`optional_number` reject missing/nonfinite/bool engineering
inputs. Tests exercise important feet/metres, ppg/PCF, psi, klbf/lbf, torque,
annular geometry and trajectory conversions. An EngineeringResult is a data
contract, not blanket numerical certification; arbitrary nested result payloads
and every Excel/PDF/JSON boundary were not exhaustively audited. No new
engineering model or restricted ML dependency was added.

### W12 scope ledger

| Reader/output | Input/query/join/aggregation scope | UI/output meaning |
|---|---|---|
| Shared KPI, ROP, performance/time-depth/NPT charts | well or selected bore; parameter/time joins use report_id → DailyReport | Bore-level aggregate; legacy NULL bore excluded |
| Daily cards | same well/bore plus selected section; explicit report or unique latest date | Single report, not an arbitrary `.first()` |
| Milestones | sections belonging to selected bore; stored planned_days | Section milestones within bore; no synthetic 5 days/depth÷50 |
| Cost/allocation | whole well CostRecord + whole-well time | Whole-well label; not bore cost |
| Plan variance, Intelligence | explicitly `analyze_well` / whole-well plan | Whole-well label; still subject to residual semantic defects |
| Data quality | selected report | Does not certify whole-bore quality |

The `.first()` search was contextual, not blindly removed: primary-key lookups
and boolean-existence probes are SAFE; timestamp-ranked latest plans with ties
remain AMBIGUOUS without a documented tie-break/active-plan contract; report/
linked-child ambiguity was UNSAFE and repaired. A search match is not itself
proof of a bug.

### Duplication/dead-code classification

| Path | Classification / evidence |
|---|---|
| `operational_time.summarize_time_logs` | CANONICAL for repaired time readers; DB plan aggregation still a separate residual path |
| `cost_semantics` | CANONICAL variance/allocation helpers, not complete cost currency aggregation |
| W12/Intelligence/EOWR/NPT time implementations | Former DUPLICATE reductions replaced with shared reducer in this patch |
| DB `get_actual_vs_plan`, CostReport category sums | DUPLICATE/remaining aggregation logic; not declared complete |
| `CalculatorBridge`, engineering core compatibility facades | WRAPPER/canonical owners according to method; actual callers retained |
| `core/db_models.py` | WRAPPER/re-export compatibility, not safely deletable unused code |
| `compare_plan_activities` | LEGACY; no production caller found in search; retained (public helper) |
| `profile_import_engine`, old mapping/template paths | LEGACY compatibility; canonical import path is different; retained |
| `tools/qt_headless_env.sh` | EXPERIMENTAL test-environment aid, not packaging/runtime dependency |
| dated audit/recovery scripts | HISTORICAL evidence, not production entrypoints; retained |
| shadowed bridge attribute / identical conversion key | DEAD/DUPLICATE, removed with usage inspection |
| `get_rig_financial_summary`, NPV/IRR/payback/payroll engine | NOT FOUND in runtime source; do not invent a replacement economy model |

Repository-wide tracked-Python string scan found 183 `.first(`, 252 `or 0`,
635 `except Exception`, 0 TODO, 0 FIXME and 3 NotImplemented occurrences at the
scan point. A broader runtime regression-pattern search returned 1,338 lines.
These are discovery counts, **not 1,338 individually proven defects or cleared
paths**. Legacy lint also remains; no “lint-clean” claim is made.

## 6. Release, integrations and data safety

- Database uses explicit SQLite schema version **3**, not Alembic. There are
  no tracked Alembic migration heads to certify. Fresh and existing-file
  migrations, future-version rejection, nullable preservation, FK installation,
  import rollback and calculation table provisioning run in tests. Startup
  owner scanning now closes the externally written contradiction gap.
- Backup uses SQLite online backup; disposable DB backup tests executed. Full
  real-customer restore/upgrade/failure-recovery acceptance is NOT VERIFIED.
- `runtime_config` separates user data from install files. Package smoke uses
  a TemporaryDirectory, removes inherited bootstrap passwords and restores
  environment. Tests verify it does not target an operator DB.
- MinerU is a subprocess integration, optional and excluded from the core
  PyInstaller bundle. Adapter output → RawDocument/normalization/review → atomic
  save is the inspected chain. Command/failure/provenance tests are not a real
  MinerU parse. No real external provider was installed or enabled.
- AI tools dispatch engineering requests to deterministic engines/bridge;
  extraction/mapping remains evidence/review-oriented. No direct LLM numerical
  persistence bypass was established in the reviewed paths. Real provider/model
  behavior and every optional path remain unverified.
- Python wheel build actually ran and required config resources were inspected;
  source test files are excluded. Wheel != Windows frozen bundle. Build isolation
  resolved build tools from the index, so this is not bit-for-bit reproducibility.
- `package_smoke.py --run` is the real EXE gate. The supplied fake bundle test
  and `test_real_windows_bundle_smoke_when_provided` structural check do not
  establish a running Windows application, installer or GUI.
- `gh` reported **zero check-runs for `c28bbef`**. The listed historical Actions
  runs were dependency graph jobs on another SHA, not application CI evidence.
  No push/remote workflow verification was attempted for this patch.

## 7. Executed evidence

Evidence files live in [`m27-independent-evidence/`](m27-independent-evidence/).

### Environment

Python 3.11.2, Linux x86_64; clean `.venv` installed all 26 exact runtime pins.
Notable versions: SQLAlchemy 2.0.36, PySide6 6.8.1.1, NumPy 2.1.3, pandas 2.2.3,
bcrypt 4.2.1; pytest 9.1.1; Ruff **0.16.6**; build 1.6.1. `pip check` passes.

Initial normal test collection failed with **15 errors** because `libGL.so.1`
was absent. Apt through HTTP and HTTPS failed to retrieve Debian indices; the
required packages could not be installed. The existing repository helper built
no-op GL/EGL/xkb/dbus stubs, with `QT_QPA_PLATFORM=offscreen`. This is a source
logic/raster-smoke boundary, **not native Qt/GL capability or GUI acceptance**.

### Final source gate

Command:

```bash
QT_STUB_DIR=/home/user/qt-libs LD_LIBRARY_PATH=/home/user/qt-libs \
QT_QPA_PLATFORM=offscreen .venv/bin/python verify_release.py \
  --allow-dirty --expected-sha c28bbef37cbac9de7abcfa693e7e21f678fa74ab
```

**1,553 collected; 1,549 passed; 4 skipped; 0 failed; 0 errors;
0 xfailed; 0 xpassed; 0 deselected.** Pytest duration **270.17 seconds**,
19 warnings. Source-gate process exit **0**. The complete gate was rerun after
the final runtime change (section-scoped daily cards); earlier intermediate
runs are not substituted for this final result. This adds 47 collected cases
over the 1,506-case base population, while also restoring three previously
vacuous checks without changing their count.

Transcript: [`source-gate.txt`](m27-independent-evidence/source-gate.txt).
Exact runtime/config/test file fingerprints:
[`source-sha256.json`](m27-independent-evidence/source-sha256.json).

- Compileall: VERIFIED for source/entrypoints/tests/packaging targets.
- Ruff E722/F821: VERIFIED, no findings.
- Full-config ratchet: **5,369** findings in the historical
  `core dialogs tabs tests` population, ceiling 5,375; **not** lint-clean.
  Running Ruff on the entire repository has a different population; do not
  compare its count against this scoped ceiling. Ruff 0.16.6 is enforced.
- Wheel: real build plus zip/resource/test-exclusion checks VERIFIED.
- Default clean gate: correctly refused this dirty development worktree; the
  successful command does not turn the worktree into a clean published release.
- Negative controls: 4 attribution, 3 parent, 5 selection regressions observed
  failing before fixes; time-service old-behavior substitution gives 4 failures
  and 1 pass. These expected failures are **not** failures in the final suite.

Skips in the full run are the separate real DDR XLSX path, real DDR PDF path,
real MinerU integration input, and actual Windows bundle opt-ins. They are not
counted as verified capabilities.

Additional run explicitly supplied the **tracked repository workbook**
`08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx` to `test_ddr_acceptance.py`:
**1 passed / 1 skipped (PDF) / 1 warning, 5.39 s**. This exercised the real
workbook's canonical IR/review/atomic save path. It is not independently
human-validated acceptance of a new customer's production DDR, and no PDF or
MinerU pass is inferred from it.

Lock wheel-resolution probes: Python 3.12 and 3.13 on the host's Linux platform
resolved; Python 3.10 failed at contourpy 1.3.3. No runtime result on 3.10,
3.12, 3.13 or Windows is implied by a pip dry-run.

## 8. Demonstrated remaining code defects and exact follow-up gates

These prevent a repository-wide correctness certificate even if Windows becomes
available. The patch is **not a claim to have fixed every material defect**.

| ID / severity | File / function / root cause | Evidence / impact | Why unresolved; acceptance needed |
|---|---|---|---|
| R01 HIGH | Intelligence, DB/W16/CostReport aggregations sum costs without a currency domain; W12/W16/report formatting assumes dollars | Disposable DB with 100 USD + 100 EUR yields `total_cost=200.0`; not a valid monetary total. Raw residual probe saved. CostRecord also retains client-side zero defaults and other readers collapse NULL values. | Requires one agreed multi-currency/unknown-cost output contract across UI, DB summaries and all exports; cannot safely invent FX rates or an OPEX/payroll model. Implement currency-separated or explicitly unavailable totals, NULL/zero roundtrip tests and UI/HTML/Excel parity before certification. |
| R02 MEDIUM | `DatabaseManager.get_planned_total_days`, `get_actual_vs_plan`; truthiness fallback, >0 ROP filtering, duplicate time reductions | Stored zero planned days reads back None; plan path drops zero ROP; incomplete recorded time can still be treated as a total outside the repaired readers. Probe and direct source trace recorded. | Remaining cross-consumer plan/actual contract repair, not environment limitation. Requires zero/NULL/mixed-duration cases through DB → W12/Planning → Plan HTML/Excel and active-plan/tied-date resolution. This pass did not complete that additional rewrite/verification. |
| R03 MEDIUM | `OperationsIntelligenceService.analyze_well`, safety reductions | With no SafetyReport rows, emits 0 days_without_lti / 0 LTI / 0 near misses. “No evidence” is not “measured zero incidents”. | Needs safety completeness propagated through insight and UI consumers and nullable/default input audit. Current W12 risk NOT ASSESSED tests do not prove this separate path; do not treat it as fixed. |
| R04 MEDIUM | Whole-well `daily_progress`, report/rig-day counts | Even with consecutive dates, whole-well rows may represent different bores; len(reports) is not necessarily distinct rig days. | Requires explicit whole-well multi-bore progress/day definition, tied-date and missing-day cases; do not silently sum bore depths or choose first report. |
| R05 MEDIUM | Broad fallback/exception and legacy scope paths | Repository-wide scan includes hundreds of broad handlers and unreviewed per-consumer `.first()`/`or 0` uses; wrappers/legacy paths remain. | Review coverage is incomplete, not proof those paths are all defects. Targeted invariant tests and source tracing required before replacing this PARTIAL assessment with VERIFIED. No blanket regex rewrite was made. |

No runtime source implementation of payroll locking, taxes/insurance allocation,
CAPEX cash flow, standby/moving economics, NPV, IRR or payback was established.
`IRR` in the currency selector is Iranian rial, not internal rate of return.
Those requested economic capabilities are NOT-APPLICABLE to certifying the
existing simple CostRecord model; they were not fabricated to satisfy a checklist.

### Environmental / release-process blockers (separate from code defects)

| Boundary | Status / exact evidence needed |
|---|---|
| Current patch publication | Not committed/pushed. Review patch, record exact commit/tree, rerun clean gate, publish only approved branch; no stale base-SHA certification. |
| GitHub CI | Configured in worktree, not executed remotely. Require successful application workflow for exact final SHA and supported matrix. |
| Native Linux Qt | System libraries unavailable here. Repeat source/UI subprocess suite with real libraries; stub run cannot certify GL/Qt platform behavior. |
| Windows Python 3.12 / frozen EXE | BLOCKED BY ENVIRONMENT. Locked install, full source tests, PyInstaller build, actual EXE smoke, first launch, resources, import/export on clean Windows. |
| Installer/upgrade/uninstall | BLOCKED. Run non-portable Inno build, clean install, upgrade prior DB/files, backup/restore, data preservation on uninstall; retain hashes and logs. |
| Production DB | NOT VERIFIED. Test a secured disposable copy with explicit backups, migrations, integrity checks and failure recovery; never run against live data as a test. |
| Real MinerU/customer DDR | BLOCKED. External managed executable/version + real source + generated assets/provenance/review + human checked canonical values + atomic save/export. Repository XLSX run is a narrower result. |

## 9. Documentation corrections

- README/TESTING now distinguish configured CI from executed CI, source gate
  from Windows acceptance, declared source Python range from the lock range,
  historical test counts from this run, and explicit dirty-worktree verification.
- DEPLOYMENT/Windows acceptance align on Python 3.12; native command failures,
  verification tooling, real integration inputs and installer follow-up are explicit.
- Production readiness names this session and says NOT RELEASE-CERTIFIABLE;
  old dated import audit tables are retained as historical evidence only.
- Engineering living documents name the current branch; original historical
  branch references remain historical. Screening/worksheet limitations retained;
  no engine upgraded to field-certified/COMPLETE because tests passed.
- Prior M27 certificate has a prominent superseding erratum for absent workflow,
  invalid 3.10 lock claim, import-test removal and Qt stub boundary.
- M26 implementation/certificate SHA distinction verified; not replaced with a
  made-up future commit hash. Current base and uncommitted fixes are explicit.
- Lock header corrected; **no runtime version pin was changed**.
- Migration source comments corrected to describe actual v3 upgrade/FK behavior.

## 10. Final certification matrix

VERIFIED is always limited to the evidence in its row, never product-wide.

| Area | Status | Evidence | Remaining risk |
|---|---|---|---|
| Git / branch integrity | VERIFIED | Fetched history, ancestor/divergence, exact base SHA, clean initial state | Final patch intentionally uncommitted/unpublished |
| Architecture | PARTIAL | Reference/input/result trace, persistence/replay suites, JSON alias repair | Not every legacy/history consumer exhaustively proved |
| Well/Wellbore/Section scope | PARTIAL | Cross-bore tests; W12 report/section ambiguity repair; parent/relationship guard | Other legacy readers and whole-well progress definition |
| Ownership integrity | VERIFIED | 30-model discovery, parent + relationship + rollback tests, startup SQL contradiction scan | Supported ORM/startup boundary; live external raw writes unsupported |
| Scope attribution | VERIFIED | Read-only preview/apply parity, INVALID ownership, wrong-bore regression, convergence tests | Explicit two-pass resolution case, not single-pass guarantee |
| W12 | PARTIAL | Bore aggregates, daily section/report selection, NULL-time and UI smoke | Cost/plan residuals; real interactive GUI not accepted |
| Operations Intelligence | PARTIAL | Scope joins, time/progress/mud-zero repairs, full service tests | R01/R03/R04 |
| Engineering engines | PARTIAL | Canonical engine/bridge and ground-truth/replay tests | Screening/design limits; no field certification |
| Cost / OPEX | FAILED | Stored-cost path inspected; mixed currency defect independently reproduced | R01; no full economic/payroll engine |
| Plan / Forecast | FAILED | Real zero/readback and source reductions show contradiction | R02/R04; remaining forecast/plan consumer review |
| Reports | PARTIAL | NPT period + NULL HTML/Excel tests, DDR/EOWR shared time, scope metadata | Cost/Plan residuals, real Windows PDF acceptance |
| Imports | PARTIAL | Normalization/identity/atomicity suites; repository workbook acceptance | Other vendors/company documents and PDF/MinerU |
| UI selection | PARTIAL | Cascades, section rejection, stale payload repair, subprocess smoke | Real Windows interaction/restore acceptance |
| AI boundary | PARTIAL | Deterministic tool dispatch and canonical reviewed extraction chain | Real providers/models and all optional paths unverified |
| Security / credentials | PARTIAL | Bootstrap/reset/production fail-closed tests; always-isolated pytest paths | Full application permission/security review and installed first-run acceptance |
| Database / migrations | PARTIAL | Fresh/legacy/future/nullable/FK/atomic tests and startup owner rejection | Real production-copy restore/upgrade; no Alembic architecture |
| Tests | VERIFIED | Final collection/accounting + negative controls + complete locked source suite | Stub environment and opt-in skips are explicit exclusions |
| CI | CLAIMED-BUT-UNVERIFIED | Workflow supplied; zero remote checks for audited base | Need run on exact final published SHA |
| Dependencies | PARTIAL | Exact 3.11 install, pip check, 3.12/3.13 resolution, 3.10 failure | Other-runtime execution, Windows wheels, hashes/build reproducibility |
| Packaging | PARTIAL | Actual wheel + resource checks; static spec/build and fake-bundle tests | No real Windows frozen binary executed |
| Windows acceptance | BLOCKED | No Windows environment | Execute full documented native acceptance |
| MinerU / DDR | PARTIAL | Optional-boundary tests; tracked workbook IR/review/save run | External MinerU + real customer PDF + human validation |
| Documentation | PARTIAL | Living claims corrected and prior certificate superseded | Historical records intentionally retained, not all old claims independently rerun |
| Cleanup / branch hygiene | VERIFIED | Ancestor classification, unique PDF retained, two proven dead declarations removed | No branch deletion/publication authorized or performed |

## Release gate

**NOT RELEASE-CERTIFIABLE.**

The verified boundary is real and useful: exact-lock Linux source regressions,
explicit Qt-stub limitations, lint defect/ratchet checks, dependency/resource
checks, negative regression controls and a real Python wheel build. It is not a
production release. Remaining demonstrated semantic defects plus unpublished
CI and missing native acceptance prohibit issuing
“RELEASE-CANDIDATE — VERIFIED FOR THE VERIFIED BOUNDARY” as a product certificate.
