# DrillMaster — real-user acceptance audit and remediation

**Decision: NOT PRODUCTION ACCEPTED**
Audit executed 2026-09-09. Requested report location retains the 2026-09-08 directory.

## 0. Latest targeted iteration — R18/R19 (2026-09-09)

**Overall: NOT PRODUCTION ACCEPTED. This iteration is partial, not full completion of the requested R18/R19 acceptance.**

Only R18/R19 and directly exposed save/context regressions were changed. The
193-file inventory below belongs to the previous broad audit and was **not rerun**.
The verified starting commit was `7d21679ee64012ba425302b9fbc7445dee334142`, on
`arena/01a0801f-drill-master`. A restored old Git HEAD was recovered by a same-branch
fast-forward after archiving/stashing and independently verifying 154 preserved
file hashes. The recovered baseline was clean before these changes.

### Results and limits

| Gate | Current result | Evidence |
|---|---|---|
| New focused regressions | **48 passed**, no failures/errors | `evidence/r18-r19/focused.txt` |
| R18 dirty/context regressions | **22 passed** | `evidence/r18-r19/dirty-contract.txt` |
| R19 legacy BHA preservation | **26 passed** | `evidence/r18-r19/bha-preservation.txt` |
| Save All/BHA/engineering/import subsystem | **298 passed** | `evidence/r18-r19/subsystem.txt` |
| Full suite, actual Golden A enabled | **786 passed, 6 skipped**, no failures/errors | `evidence/r18-r19/full.txt` |
| compileall / diff whitespace | **exit 0 / exit 0** | `evidence/r18-r19/final-exit-codes.txt` |
| R18 application-wide requirement | **PARTIAL / OPEN** — common mechanism implemented; unsupported and insufficiently verified legacy editor paths remain | Details below |
| R19 alternative C | **PASS in the executed report-scoped software/protocol scope:** named selection/inspection, read-only preservation and destructive-write guards | Editing/migration is **not implemented**; native GUI remains unverified |
| Native Windows/desktop acceptance | **BLOCKED / NOT VERIFIED** | Unchanged gates below |

### R18 implementation and boundary

- Existing `SaveOutcome`/`save_all` remains the sole outcome/coordinator architecture.
  Its backward-compatible status has an explicit `disposition`: `NO_CHANGES`,
  `SAVED`, `REVIEW_REQUIRED`, `VALIDATION_ERROR`, `SYSTEM_ERROR`,
  `CONTEXT_BLOCKED`, or existing `UNSUPPORTED`. Summaries distinguish no work
  from persisted operations and show leaf-section outcome counts.
- `DrillTabBase.save_changes` and explicit persistent-section bindings share
  local raw editor snapshots. Baselines are established at construction and
  declared successful load/save boundaries, **not on the first Save All**.
  Clean sections do not invoke their savers. No widget-to-database comparison,
  global monkey patch, second Save All coordinator or always-dirty rule was added.
  Default/read-only/no-op tabs have no pending sections.
- MainWindow Save All/current-tab Save and both AutoSave entry points route through
  that contract. Independent dirty sections keep the existing partial-success
  policy. Invalid/system/unsupported results remain dirty; confirmed persistence
  with retained review warnings is reported as review, not global success.
- Pending BaseTab context is preserved. False loader returns now fail the load.
  Each section also retains the context of its successful load plus load-failure
  state, so a superficially ready parent cannot lend readiness to a failed child.
  Load exceptions are propagated at inspected boundaries instead of silently
  acknowledging stale values.
- DDR no longer offers invalid “Save anyway?” and no longer blindly cascades
  saves into unrelated tabs. Its BaseTab report handler now really calls the
  loader (BaseTab already assigns the current ID); the duplicate direct
  MainWindow load connection was removed. Existing Well/DDR saves do not
  reselect the hierarchy and reload other pending editors. Equipment inventory,
  pipe and solid-control reads now use the selected report, not all well reports.
- Existing nullable-value restoration is used for Well/DDR scalar placeholders;
  explicit scalar edits are tracked separately. The test matrix verifies NULL,
  valid zero and invalid-text preservation through actual Downhole services.

**R18 is not closed. Important architectural limits discovered during this work:**

1. The manual schematic saver serializes only part of the model, while loading
   regenerates a schematic rather than restoring that saved document. Global
   Save All therefore returns **UNSUPPORTED and retains dirty state**, instead
   of falsely certifying a lossless save/reload. Rendering is not disabled.
   The separate legacy local schematic save/export behavior is not certified.
2. Procedure General/Checklist/Steps are separate from supplementary/PJSM and
   approval details that the existing `save_procedure` does not persist. The
   latter now have a distinct dirty boundary and explicit **UNSUPPORTED** outcome;
   saving General cannot mark them saved. Their persistence must be completed
   before claiming all valid dirty authoring fields can save/reload exactly.
3. The remaining legacy editor-specific payload/reload paths are **not proven
   application-wide** by this matrix. In particular Section Data has historical
   well/section/report routing (including legacy `save_data` paths passing
   `report_id=None`, and tally/bit well-level retrieval) requiring alignment.
   The new context guards do not constitute certification of those domain
   writers or of every nullable field. This is a source-level limit, not merely
   a missing Windows screenshot.

Consequently the requested condition “every valid dirty editor saves exactly and
reloads exactly” is **not accepted**. Green common-contract tests must not be used
to claim it. The safe unsupported outcomes are a stopgap, not completion of those
features or permission to discard the pending edits.

### R18 requested matrix — what was actually exercised

The production MainWindow Save All method, BaseTab methods, production bindings,
AutoSaveManager and Downhole managers/services are executed with table/widget
protocols and a real Production-mode SQLite database. This is **not native Qt**.

| Requested case | Executed evidence in `test_r18_r19_save_preservation.py` |
|---|---|
| All clean | Saver failure sentinels plus SQL observer: zero INSERT/UPDATE/DELETE |
| One valid dirty | One BHA save; clean equipment/formation callbacks prohibited |
| Two valid dirty | BHA + equipment persisted; exact saved-section count |
| Invalid + valid partial | Invalid BHA unchanged/dirty; independent equipment persisted |
| Cancelled edit/dialog | Actual cancelled Add BHA method; reverted edit also clean |
| Context changed / child load failed | Failed parent pending event and separately mismatched child snapshot block savers |
| Hidden clean | No write and NO_CHANGES |
| Read-only/no-op | Callback existence does not create pending work |
| Clean AutoSave | No callback/write |
| Dirty valid AutoSave | Confirmed one-section persistence |
| Failed save retains dirty | Injected persistence failure; actual DB unchanged |
| Success clears dirty | Successful retry and local button save; subsequent global/timer no-op |
| Exact save/reload | Normalized BHA records survive DB close/reinitialize and actual loader |
| NULL fidelity | Blank optional ID remains SQL/JSON NULL after another edit |
| Valid zero fidelity | Weight zero remains zero, not missing |
| Invalid never becomes NULL | Malformed length cannot overwrite prior valid record |
| Old report cannot write into new | New report stays empty; original report record unchanged after failed load |

Additional tests cover same-context reload failure, unsupported dirty work,
existing Well save with an invalid BHA sibling and preserved selection, legacy
read-only selection, and independent equipment persistence. These do not certify
all other editors' complete lifecycle.

### R19 choice C — preserve, inspect, explicitly do not edit

The historical widget source (`ad7ea0d`) actually reads a JSON string or object
mapping **original configuration name → component rows**; it formerly chose the
first key. The authoritative `BHAReport.bha_data_json` column holds that document;
`get_bha_report` exposes it as `bha_configs`. Current list-based persistence cannot
round-trip the named alternatives. No new schema or parallel BHA engine was added.

- Original names populate selector `itemData`. Both alternatives can be selected
  and inspected without renaming or flattening them. Named legacy documents,
  including single-name maps, stay read-only.
- Name/table editing and add/remove/save/delete controls are disabled for legacy
  data; callable mutation actions also reject it with a migration explanation.
  Selection/inspection never becomes dirty save work.
- Service writes, generic updates/deletes, repository updates/deletes and generic
  inserts that would hide a protected report behind a replacement record are
  rejected. Both import-upsert branches are guarded inside the existing atomic
  transaction; attempted replacement rolls back. Import rejection still uses
  the existing `PersistenceError` envelope, with an explicit legacy read-only
  reason; this is not advertised as successful editable import support.
- UI JSON archive writes the original selected BHA report document containing
  **all** alternatives, not just the displayed configuration. Cancel writes no
  file. Professional Excel exports both original configuration names and the
  complete raw document/lineage in its chunked Raw Data sheet.
- The fixture has two differently named configurations, different component
  order/dimensions/lengths, provenance, NULL and legitimate zero. It is tested as
  both a JSON object and historical JSON-encoded string. Load/list/select/inspect,
  restart/reload, write/delete/import rejection, no duplicate replacement record,
  JSON/Excel export and unchanged unselected alternatives are asserted.

This verifies the existing **report-scoped** workflow and public service/repository
paths. Direct administrative SQL, intentional whole-well/report destruction,
and discovery/selection of unrelated unscoped historical BHA report records are
not certified by this fixture. No claim of editable multi-configuration support
or automatic migration is made.

### Remaining mandatory acceptance gates

- **R18 source-level blockers above must be resolved**, followed by per-editor
  lifecycle tests; it is not enough to rerun the current green suite.
- Windows + Python 3.12 startup/first-run/login, native QMainWindow construction,
  each registered editor's initial snapshot/load/failed-load/save/cancel behavior,
  hidden/visible tab transitions, real Save All clicks and timer callbacks.
- Native legacy BHA selector/table read-only behavior, both configurations,
  archive file dialogs and real application restart; older unscoped BHA discovery
  is a separate unverified compatibility boundary.
- Native charts, all required PDF paths, actual Windows packaging/installer and
  installed-package smoke tests. Linux protocols/compileall do not prove these.
- Six full-suite skips are explicit in the log: actual PDF fixture, native Qt
  import repair, actual MinerU integration, Windows bundle, native startup and
  native tab checks. Golden B: **NOT AVAILABLE / NOT VERIFIED**.

Commands and execution boundaries: `evidence/r18-r19/commands.md`. Test DBs,
exports, credentials and temporary recovery archives are not committed.

## 1. Executive assessment

This iteration delivers implemented persistence, selection-state, calculation-presentation and reporting repairs, plus fresh Production-mode service exercises. It is **not completion of the requested desktop production acceptance**. Native startup fails before application construction because `libGL.so.1` is unavailable. Windows/Python 3.12 and an installed Windows package were not executed. The latest targeted status is in section 0: R18 remains partially open; R19 uses safe read-only alternative C in its tested report-scoped boundary, not editable migration support.

Usable within the executed scope:
- Secure first creation, authentication, database reopen, explicit hierarchy creation and offline recovery at service/CLI level.
- The actual, unchanged Golden A workbook through extraction, canonical mapping, atomic persistence, edits, disk reopen and replay.
- Individual report BHA save/delete, missing formation colors, nullable/zero-valued Downhole records and failed/pending selection protection, exercised through actual method bodies and real SQLite storage.
- HTML/Excel DDR, EOWR, NPT and Cost reports; Plan exports with an explicitly created plan; a 28-sheet professional Excel export including source lineage.
- Existing engineering tests and additional direct calculator exercises, within each engine's declared scope.

Not established: first-run wizard/login interaction, opening every native module, all editor dirty-state transitions, every dialog's cancel/invalid sequence, native charts, PDF output, peripheral external integrations, Windows installation or production engineering approval. Passing service tests is not a substitute for these gates.

## 2. Environment, branch and preservation

- Repository: `asgareyvazi/Drill-master`; branch: `arena/01a0801f-drill-master` throughout.
- Authoritative baseline: `ac3845fef8e848a62c6bd7a6f0a95601835572c3`. Prior `eb8041d` / `c7d9f2e` / credential remediation preserved.
- After the interrupted environment was reconstructed, Git initially pointed to `ad7ea0d` while the preserved working files contained the later changes. The expected remote `ac3845f` was fetched, work was archived/stashed, the **same branch was fast-forward merged**, and the preserved files were restored. SHA-256 checks matched all 121 protected files. No reset/revert, force push, alternate branch or user-file deletion was used.
- Linux x86-64, Python **3.11.2**; SQLite/system/package versions are recorded in `evidence/real-user-acceptance/environment.json`.
- Recreated virtual environment used `requirements.txt` plus pytest, pytest-qt and Ruff. This was **not** a Windows lockfile/bundle validation.
- Production acceptance database: a **new** `build/acceptance/production-complete/acceptance.db`. A generated temporary admin credential was supplied to the existing bootstrap interface. The first database contained **one user, zero companies and zero wells**. No Development fixture credentials/data were used for this Production workflow.
- Pytest retains the repository's explicit isolated test-mode fixtures; it must not be described as running every test in Production. New acceptance fixtures and the standalone Production run explicitly select Production.
- GitHub and PyPI were reachable from the reconstructed sandbox. Debian package endpoints were not: apt update/install could not obtain the missing Qt libraries. The user's local Internet outage did not imply that every sandbox network endpoint was unavailable.

## 3. Inspection and feature inventory

`source-inventory.json` records **193 Python files and 1,433 UI declarations/connections**, with source hashes, classes and methods. Scope includes startup, main window, core modules, repositories/models, tabs, dialogs, configuration adapters, packaging Python and tests. Configuration templates, Windows spec/installer/build scripts and prior audit reports were also examined. The inventory is an AST/source inventory, **not a claim that every line was behaviorally reviewed or every button clicked**.

Deeper semantic review followed the active paths through:
- `app.py`, `run.py`, runtime configuration, credential policy, bootstrap/login/settings/reset;
- `main_window.py`, `DrillTabBase`, selection and combo identity, Save All/AutoSave;
- shared database, named-record/mud/survey contracts, importer, source IR/reviews and repositories;
- operational tabs and their save/load methods, particularly Downhole, Drilling, Survey, Mud, Safety, Logistics, Equipment, Services and Planning;
- report/export engines, calculator bridge and engineering contracts.

Stable identities were checked against `core/combo_identity.py`. Downhole's named selector now carries domain names as `itemData`; no numeric Qt index is interpreted as a domain ID. Well repository resolution now honors project context and rejects ambiguity rather than choosing the first project/well.

Prior reports were treated as historical evidence. Their suite counts were not reused as current results. Golden A import/lifecycle and credential recovery were independently rerun. In particular, previously claimed report availability was contradicted by a fresh EOWR failure and repaired here.

### Module matrix

Legend: **G** = native GUI BLOCKED; **S** = real service/API storage or export executed; **P** = actual Python widget methods executed with table/control protocols, not Qt widgets; **SC** = synthetic schema CRUD only; **NV** = not verified; **N/A** = no persistent editing contract. A module is not accepted merely because SC passes.

| Module | Open | Create/Edit | Save | Reload | Delete | Runtime Errors | Status |
|---|---|---|---|---|---|---|---|
| Home/dashboard | G | N/A | N/A | NV | N/A | Startup blocked before window | BLOCKED |
| Company/project/well | G | S | S | S/reopen | S | Invalid date/context rejected after repair | Service verified; GUI blocked |
| Section/section data | G | S/SC | S/SC | S/SC | SC | None in executed schema path | GUI blocked |
| DDR/header | G | S | S | S/reopen/replay | S with children | None in final workflow | Service verified; GUI blocked |
| 24h/morning operations | G | S/SC | S/import | S | S report cascade | Missing time anchors retained for review | GUI blocked |
| Drilling/bit/casing/cement/trip sheet | G | S/SC | S/SC | S/SC | SC/S cascade | No unexpected final service error | GUI blocked |
| Downhole/formation | G | P + S | P + S | P + disk reopen | P/SC/S | R01–R06, R14–R16 repaired | GUI blocked |
| BHA/components | G | P + S | P + S | P + disk reopen | P + S | Current report fixed; legacy multi-config limitation | **Read-only software path verified; native NV (section 0)** |
| Wellbore schematic | G | SC | SC | SC | SC | Native rendering unknown | BLOCKED |
| Survey/trajectory | G | S | S | S/recalculation | S/SC | Missing azimuth is a review, not zero | GUI blocked |
| Mud/rheology/composition/chemicals | G | S | S | S/reopen | SC/S cascade | Unknown roles/composition remain review-required | GUI blocked |
| Surface equipment | G | S/SC | S/SC | S/SC | SC/S cascade | No unexpected final service error | GUI blocked |
| Logistics/POB/fuel/water/transport | G | S/SC | S/SC | S/SC | SC/S cascade | Optional dates preserved | GUI blocked |
| Safety/BOP/waste/incidents | G | S/SC | S/SC | S/SC | SC/S cascade | Empty collections valid; failures distinct | GUI blocked |
| Services/material requests | G | S/SC | S/SC | S/SC | SC/S cascade | No unexpected final service error | GUI blocked |
| Planning/lookahead | G | S/SC | S/SC | S/SC | SC/S cascade | No plan correctly gives no Plan export | GUI blocked |
| Cost management | G | SC + engine tests | SC | SC | SC | No invented default rig rate in tests | GUI blocked |
| Analysis/actual versus plan | G | Engine tests | SC for stored analysis | SC | SC | Deterministic tests pass | GUI blocked |
| Engineering calculator | G | Direct calls/tests | N/A for ephemeral calculators | NV native state | N/A | Expected missing/invalid input contracts | BLOCKED native |
| Export/reporting | G | S HTML/Excel/CSV | S files | S file reopen | N/A | EOWR/Excel repaired; PDF dependency blocked | **BLOCKED / partial coverage** |
| Procedures/checklists/PJSM/approvals | G | SC | SC | SC | SC | Approval authorization/workflow not proven | BLOCKED |
| Reference/knowledge tables | G | Inventory only | NV | NV | NV | Optional DrillPipe reference nonfatal by contract | BLOCKED |
| AI/knowledge/external tools | G | Registry/tests only | NV | NV | NV | Live model/provider/document integration unverified | BLOCKED |
| Settings/bootstrap/login/logout | G | Credential service/CLI | S credential creation | S auth reopen | S offline reset | Native interaction not reached; logout not exercised | BLOCKED native |
| Global Save All/AutoSave | G | P + S | P + S | S | N/A | Stale-context writes blocked; dirty policy incomplete | **FAIL: R18 remains** |

## 4. Defect register

Severity: P0 data loss/security/startup; P1 major workflow; P2 important; P3 minor. “Fixed” below means implementation plus the stated executable evidence, **not native Windows verification**. The named tests are in `tests/test_real_user_acceptance_regressions.py` unless noted.

| ID / severity | Reproduction and root cause | Repair / evidence | Status |
|---|---|---|---|
| R01 P1 | Load a persisted formation with absent/NULL `Color`. `named_record(FORMATION_FIELDS)` explicitly emits `None`; `get('Color','').startswith` therefore raises. Styling is optional, not required geology. | Only valid string QColor values affect presentation; neutral palette otherwise. Source color not fabricated. Parameterized absent/blank/invalid/non-string/color tests and DB reopen. | Fixed; native palette NV |
| R02 P1 | Load equipment with rotation hours `0` and optional dates NULL; `value or ''` loses zero, text serialization turns NULL/numbers into strings on unchanged save. | Named source snapshots separate domain/provenance from displayed text. Unchanged NULL/zero/numeric types restored; edited blanks explicitly clear. Three Downhole managers share this contract. | Fixed; `downhole_zero_null_and_persistence_reopen` |
| R03 P0 | Switch to empty/no report or fail JSON decoding; old tables could remain, or malformed data was silently treated as empty. | Clear report tables/BHA cache first, require selected report/well pair, never fall back to another report; malformed collections raise and context is not save-ready. Selection clear tested. | Fixed; `downhole_null_empty_corrupt_switch_clear` |
| R04 P1 | Save/Delete BHA announced success while changing only `self.bha_data`. Restart lost the action. | Current report's BHA is persisted/deleted through the DB; success follows a structured outcome. Cancel leaves DB unchanged; restart tested. | Fixed for a single report BHA; see R19 |
| R05 P1 | Failed callbacks were marked loaded; force refresh reset section/report before using them. | Pending parent load must succeed before downstream callbacks; failures stay pending with traceback. Force refresh snapshots hierarchy before resets. | Fixed; pending-parent and visible/hidden force-refresh tests |
| R06 P0 | A hidden tab receives new IDs but still contains old/empty editor values. Global Save All or timer directly calls its saver. | Shared coordinator checks successful context loading before mutation. Main and per-widget AutoSave use it. Independent ready sections still run; blocked section reports REVIEW_REQUIRED. | Fixed known stale-context path; dirty policy remains R18 |
| R07 P1 | Update an existing well with invalid spud-date text; old code silently replaced it with NULL and mutated the caller dictionary. | Existing `optional_date` contract validates a copied payload before persistence. Valid stored date survives rejected input. | Fixed |
| R08 P1 | Multiple projects or same-named wells: repository selected the first global match/project. | Scope identity resolution to the supplied project; require unique context or reject ambiguity. | Fixed; repository context test |
| R09 P1 | Edit a deleted ID via generic repository/database saver; absence silently became a new row. | Existing-ID updates now fail explicitly rather than recreating the record. | Fixed; deleted-identity test |
| R10 P1 | Import report engine for HTML/Excel with no Qt GUI libraries; module-level Qt imports blocked unrelated output. | Qt imports occur only inside PDF renderers. No new rendering/calculation engine. | Fixed for non-PDF; PDF remains blocked |
| R11 P1 | EOWR always rejects because `_collect_data` has no `plan` key; after removing that error, actual A's NULL survey geometry crashes formatting; Excel also assumed section dictionaries were ORM objects. | EOWR reports actual history without a plan; nullable numeric/text presentation; typed dictionary/ORM export. No geometry/zero fabricated and no 100-station truncation. | Fixed; actual A and incomplete-survey HTML/Excel regression |
| R12 P1 | Professional Excel returned success after swallowed section errors, dumped/truncated BHA/metadata in cells, mixed reports' survey/bulk rows, omitted sections and left claimed Raw Data empty. | Fail explicitly on query errors; enforce context; structured BHA/chemical tables, typed NULL/date/zero cells, report-scoped rows, additional operational sheets, full chunked raw/audit lineage. Remove invented company/approval labels; literal Excel formula-like text remains text. | Fixed tested paths; failure/scope/40,000-character lineage regression and actual A 28-sheet export |
| R13 P2 | Shared CSV export logs a write failure without visible feedback or return contract. | Return path on success, None on cancel, False plus error dialog/log on failure. | Fixed; real file/cancel/directory-write-failure protocol test |
| R14 P1 | Edit BHA length to malformed text; permissive float conversion silently changes it to NULL. | Existing normalizer's explicit error result is respected before persistence. | Fixed; valid previous BHA survives invalid edit |
| R15 P0 | Supply one well ID with another well's report ID to a Downhole saver; independent FKs do not validate the pair. | BHA/equipment/formation services verify the owning report in their transaction before updates. | Fixed in these services; three scoped regressions |
| R16 P1 | Calculate totals with missing weight/hours, or check service with no date: old code implied zero totals or “All equipment up to date.” | BHA delegates to existing engine and marks missing weight unknown; hours remain unknown when incomplete; invalid input explicit; missing service dates remain REVIEW_REQUIRED. Blank new equipment/formation rows no longer invent dates/serials/geology. | Fixed; totals/controller-missing-input and service-date tests |
| R17 P3 | Downhole always claimed Auto-save ON independent of settings; optional DrillPipe notice used fatal-looking red. | Truthful setting-dependent wording and neutral optional-reference styling. Vendor-reference absence is not suppressed. | Source/UI declarations corrected; appearance NV |
| R18 P1 | Global Save All previously enumerated every saver without dirty/no-change semantics. | Common per-section snapshots/context/load/save boundaries and honest dispositions implemented; 22 new DB/protocol tests pass. Schematic/supplementary Procedure and other legacy domain lifecycle limits remain (section 0). | **PARTIAL / OPEN — not application-wide accepted** |
| R19 P1 | Legacy named configuration maps cannot be losslessly edited by the current list saver. | Alternative C: named read-only inspection; UI/service/repository/import replacement guards; lossless JSON/Excel archive; 26 new preservation tests pass. See report-scoped/unscoped boundary in section 0. | **Read-only software path verified; editable migration unsupported; native NV** |

No claim is made that all remaining GUI or authorization defects have been found. In particular, R15 is not certification of every generic ORM parent-context mutation.

## 5. Executed workflows and integrity

### Production first run and ordinary setup

The standalone tool created a fresh Production DB, authenticated the generated admin, rejected wrong-password and unknown-account attempts, closed the engine and authenticated again without bootstrap settings. It then created **Production Acceptance Test**, **TEST-WELL-001**, a section and a dated report with bilingual text. A well edit persisted; invalid date input left the previous date intact.

Native first-run dialog, password entry, modal cancellation, logout/relogin and browser-like navigation are **NOT VERIFIED**. Startup never reached these widgets.

### Persistence/CRUD

- Production service workflow plus **46 mapped entity types** exercised synthetic schema create, edit, read, new-engine reopen and delete. Every probe completed. Per-entity results are in `production.json → schema_crud`.
- These 46 are **mechanical schema/API probes**, not realistic drilling-engineering/approval tests. Generated required fields are explicitly QA values, not additional Golden workbooks. Users/system audit records were not synthesized by the probe. History-table CRUD does not certify an approval workflow.
- An additional isolated Production graph exercised Company/Project/Well/Section create, explicit name edits, new-engine reopen and child-first deletion (`parent-crud.json`). This does not certify parent deletion with every possible dependent graph.
- Operational import, selected edits, BHA button save/cancel/delete and source-aware table roundtrips provide stronger evidence for the relevant modules.
- Golden A report deletion removed the 23-model import snapshot's report-scoped rows. The imported well was deleted; the independent manual well survived. Successful schema probes also deleted their rows.
- Before and after deletion: SQLite `integrity_check = ok`, **zero FK violations**, **zero report/well mismatches in every mapped table carrying both keys**. No orphan condition was observed in the tested graph. This is not exhaustive concurrency/cascade testing of every possible graph.

### Save All and failures

The real Production run saved Mud, BHA and Formation through the shared coordinator and verified edits after a fresh engine reopen. It also recorded injected invalid/system outcomes and an empty callback list. Existing follow-up regressions exercise independent section failure and successful-save retention. Pending-state regressions prove that a stale empty editor cannot erase a stored BHA.

Transactions remain **per supplied domain service**, not one transaction across all tabs. Partial success is reported, not rolled back or labeled total success. Pure callback fault injections are not native Save All clicks. All-loaded dirty/no-change behavior is not solved (R18); every individual editor's invalid/cancel behavior is not certified.

### Offline recovery/security

A fresh **real reset CLI** sequence tested cancel, missing-bootstrap preflight with byte preservation, secure reset, authentication after reset without bootstrap env, backup restoration and authentication, and an unrelated target remaining unchanged. Logs contain no generated password. The original recovery probe inadvertently kept backup SQLite connections open; reset refused rather than proceeding. The probe was corrected to close both handles; no security policy was weakened.

The existing unsafe-credential guard is retained. Missing bootstrap, unsafe stored credentials, invalid configuration and optional accounts are also covered by the rerun credential tests. Reset still requires all application instances closed; it is not a race-free cross-process maintenance protocol. Windows file-handle behavior remains unverified.

## 6. Golden A and review audit

Actual file: `08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx`, unmodified; SHA-256 in `production.json`. The tool rehashes it after the workflow. **Golden B: NOT AVAILABLE / NOT VERIFIED**. Synthetic schema/input variations are not a second real workbook.

Results: **101 import operations, 0 failed; 64 retained ReviewItems; 65 persisted rows across the 23-model snapshot**. Reopen and same-source replay compare equal. Explicit edits survive reopen. Existing lifecycle tests additionally rerun clean-source replay separately from edits.

`review-classification.csv` classifies every current review into the requested six classes. Scalar source cells were reread from the actual workbook, rather than assuming every review meant absence:

| Classification | Count | Interpretation |
|---|---:|---|
| Expected source absence | 27 | Optional blank/dash/N.C fields; not replaced with measurements |
| Valid user review | 37 | 24 unresolved chemical roles; 3 missing survey azimuths; 4 time/continuation rows; 2 incomplete lookahead rows; 1 BOP type; 1 combined Oil/Water value; 2 projected coordinate strings needing CRS/context |
| Unsupported source feature | 0 | None of these 64 classified here; not a claim of universal importer support |
| Importer defect | 0 | No unresolved importer defect established among these current 64 |
| Mapping defect | 0 | No unresolved mapping defect established among these current 64 |
| System error | 0 | No unexpected system failure in the final Production import |

The old 65th phantom formula/whitespace review was already repaired before this iteration; it was not reintroduced or suppressed to improve the count. Review reasons that merely name a template cell are augmented in this audit with the original value, type of ambiguity and corrective action.

Important engineering fidelity checks:
- Database mud density remains **PCF**: actual A's stored MW is **71 pcf**, not 71 ppg. The existing PCF-domain conversion was inspected and preserved. Calculators declaring ppg have separate input contracts.
- Unknown chemical roles remain unknown; no new product identities/catalog roles were guessed. The explicit `received = 2` acceptance edit did not recalculate or replace measured closing stock or other chemical rows.
- Missing composition is not normalized to 100%. The combined Oil/Water source value is not assigned to a component without review.
- Three actual A survey stations retain missing azimuth; calculated geometry remains unavailable. No north/zero azimuth is invented.
- Named BHA component/order/dimension/provenance fields survive persistence; derived cumulative values are not written over measured source merely to populate a view.

## 7. Engineering acceptance

**121 engineering tests passed** in a separately traced run. `engineering-executed.json` maps **81 actually executed public functions/methods** to test node IDs; it is execution evidence, not an exhaustive boundary-coverage percentage. Additional direct exercises cover **50 valid/missing-input cases**, with independent checks for kill MW, mixed mud density, kick height/zero/negative gain and trajectory closure. Supplemental inputs follow actual function signatures, not inferred UI labels.

| Calculator family | Executed evidence | Limit / status |
|---|---|---|
| Torque & Drag / weight card / casing landing | Soft-string tests; supplemental component/card/landing calls | Johancsik screening/PARTIAL; no stiffness/dynamic certification; vendor benchmark unavailable |
| Kick tolerance | Ground truth/invalid/missing tests and bridge | Input units/geometry required; no replacement of engineering constraints |
| Trip margin | Engine tests + bridge direct valid/missing | Swab/formation context retained |
| Kick volume / kill MW / MAASP / formation pressure | Supplemental valid/missing, zero and negative gain; engine tests | 10 bbl / 0.05 bbl/ft = 200 ft checked; no inferred kick for zero gain |
| Casing | Burst/collapse/combined/tensile/triaxial/evaluate tests | Within declared casing-model assumptions; not signed design approval |
| Cement | Job volumes/hydrostatic tests; displacement/TOC direct calls | ft/in/bbl inputs explicit; empty Plan is not a cement job |
| Trajectory / closure / anti-collision | Minimum curvature tests, closure direct call, clearance tests | Missing directional stations excluded from geometry; anti-collision screening is not a survey-uncertainty study |
| MSE | Teale ground truth/validation + bridge direct calls | WOB lbf, torque ft·lbf, ROP ft/hr, diameter in; zero ROP invalid |
| Mud volume balance / mixing / dilution / weight-up | Tests plus supplemental mix/dilution/balance | Missing inputs stay missing; no composition completion |
| Bit/section performance | Run/d-exponent/cost-per-foot tests; daily-params and rollup direct calls | Native section performance interaction not verified |
| Fishing/stuck pipe | Backoff tests; adjusted weight/free point/stretch/jar/overshot calls | Explicit legacy screening approximations, not field certification |
| Hydraulics / PV-YP / ECD / nozzles | Core and extended tests | Native UI units, controls and navigation blocked |
| Calculator Bridge / extended helpers | Traced tests and supplemental facade calls | Not every UI button nor every function's entire boundary space exhausted |

`TrajectoryCalculator.calculate([])` explicitly raises `MissingInputError`; this is a documented API validation exception, not an unexplained application crash. Supplemental probe mistakes (incorrect keyword/component aliases) were corrected without changing calculator signatures or formulas. **No engineering algorithm or legitimate validation was weakened.** Optional welleng/vendor comparisons and actual drilling-engineer approval remain unverified.

## 8. Reporting and visualization

Final service run:
- DDR/EOWR/NPT/Cost: actual **HTML and XLSX** files generated and reopened; EOWR works without a drilling plan and with NULL survey geometry.
- Plan without plan data: returns False/no output, an expected unavailable-input state. After explicit plan/activity creation: HTML and XLSX generated.
- Professional Excel: **28 sheets**, including 34 chemical rows, 9 BHA components, 3 source survey rows, POB, equipment, lookahead, BOP, formation/downhole collections and chunked raw/audit data. Query failures do not return success. Raw-lineage reconstruction beyond Excel's single-cell size was regression-tested.
- CSV: real UTF-8 file generation, cancel and failed destination tested through the shared method with a file-dialog protocol. Actual native dialog/Excel desktop viewing not performed.
- Missing values remain blank/unknown in repaired paths; dates/numbers remain typed. Bilingual content/file paths exercised. **Visual pagination, Persian shaping, fonts and all spreadsheet application behavior are NOT VERIFIED**.
- Actual DDR/EOWR/NPT/Cost PDF calls returned False and produced no files because Qt could not load `libGL`; see `pdf-attempts.json`. Other native PDF routes likewise not certified. Word/other peripheral export routes were not exercised; no Word success is claimed.
- Existing shared 3D Matplotlib function rendered empty, insufficient Golden A and valid manual survey states with Agg. Reusing the **same axes** through valid → empty → incomplete → valid produced line counts **1 → 0 → 0 → 1**. This verifies the draw boundary clears stale lines, not native 2D/3D navigation or Windows graphics.

## 9. Runtime message and exception register

| Observed message / event | Classification | Resolution / disposition |
|---|---|---|
| Downhole `NoneType.startswith` / pending refresh | Real software defect | R01/R05 fixed and regressed; no native replay available |
| EOWR `No active plan` despite actual reports | Real logic defect | R11 removed impossible predicate |
| EOWR `unsupported format string ... NoneType` | Real nullable-data defect | R11 fixed; A output rerun |
| EOWR Excel dictionary has no `__table__` | Real type-contract defect | R11 accepts both dictionaries and ORM rows |
| Silent professional-export section exception | Real error-reporting/data-completeness defect | R12 explicit False/error, no false successful partial workbook |
| Malformed collections / wrong report-well / invalid dates or BHA text | Validation failure | Explicit rejection; previous stored values not cleared |
| Failed parent load injected in regression | Injected recoverable fault | Remains pending, traced; save blocked |
| Invalid/system callback injections | Test fault, not real source defect | INVALID_SOURCE/SYSTEM_ERROR, independent success retained |
| CSV failed destination / injected unavailable query | Expected I/O/fault test | Explicit failure, not successful export |
| Missing bootstrap during CLI reset | Expected secure refusal | Preflight retains target bytes; actionable message |
| Reset attempt with backup connections still open | Probe resource-lifecycle mistake / safety refusal | Handles explicitly closed; secure recovery rerun passed |
| `libGL.so.1` at `run.py` and PDF renderers | Environment blocker | Real attempts failed before native UI; apt recovery unsuccessful |
| Debian package fetch failures / packages unavailable | Environment/network dependency | Not an application defect; no libraries faked |
| Optional DrillPipe vendor reference unavailable | Optional resource | Existing independent calculators remain available; neutral notice, browse/path remediation retained |
| openpyxl unsupported data-validation extension | Dependency warning | Input workbook not saved/changed; retained warning. Not proof imported Excel validation widgets survive export |
| Existing >3000-line file warning | Maintainability warning | `database.py` / W13 still large; no unrelated rewrite |
| Missing-input calculator result/exception | Expected validation | Preserved; not fabricated numeric output |
| Initial audit probe key/date/alias/partial-geometry mistakes | Audit harness errors | Corrected to actual APIs/contracts; not patched into permissive application behavior |

The **final Production service run has no ERROR or WARNING lines** in its application runtime log. The openpyxl warning is separately present on stderr. This does not mean all possible app logs were observed: native startup never reached operational tabs.

## 10. Automated and runtime verification

| Final run | Passed | Failed/errors | Skipped | Warnings |
|---|---:|---:|---:|---:|
| New acceptance regressions | **33** | 0 | 0 | 0 |
| Affected subsystems | **343** | 0 | 2 | 5 |
| Entire collected suite | **738** | 0 | **6** | 15 |
| Engineering trace run | **121** | 0 | 0 | 0 |

Full suite: 744 test cases, 134.24 seconds. The correct opt-in variable **`DRILLMASTER_TEST_DDR_XLSX`** was set to the actual workbook. An earlier run used an incorrect variable and skipped that opt-in test; it was superseded, not presented as the final result.

Six final skips: actual DDR PDF fixture, real MinerU runtime/input, native nozzle boundary, Windows bundle, native core import sweep and circular-import sweep. Fourteen openpyxl warnings plus the large-file warning account for the 15 warnings.

Compilation, new-file Ruff F checks, targeted F821 checks and `git diff --check` passed. No tests were weakened/deleted. New protocol tests explicitly disclose that they do not instantiate Qt widgets.

Evidence/reproduction: `evidence/real-user-acceptance/commands.txt`, XML/text logs, Production JSON, review CSV, source inventory, engineering traces and recovery evidence. Databases and generated report workbooks remain outside Git in ignored `build/`; no real/generated plaintext credential was committed.

## 11. Required gates

PASS applies only where the gate is genuinely established at its stated scope. A missing native/Windows requirement is not converted into PASS by a service test.

| Gate | Status | Reason |
|---|---|---|
| Startup | **BLOCKED** | Actual `run.py` fails importing Qt/libGL |
| Authentication | **BLOCKED** | Production service/CLI passes; wizard/login/logout native sequence not reached |
| Database | **PASS** | Fresh schema, 46 schema lifecycles, reopen and observed integrity checks pass |
| Well lifecycle | **BLOCKED** | Service create/edit/delete/reopen passes; native CRUD/cancel/selection unverified |
| DDR lifecycle | **BLOCKED** | Service import/edit/delete/replay passes; complete native workflow unverified |
| Import | **BLOCKED** | Actual A service gate passes; native wizard, PDF and second actual workbook not verified |
| Save All | **FAIL** | Confirmed pending-context data loss fixed, but global dirty/no-change requirement R18 remains |
| Operational tabs | **FAIL** | Native coverage blocked; R19 editing unsupported but read-only preservation tested |
| Engineering | **BLOCKED** | Automated/direct contracts pass within scope; native inputs/results and field validation unverified |
| Reporting | **BLOCKED** | HTML/Excel repaired/executed; PDF/native visual/other format acceptance incomplete |
| Visualization | **BLOCKED** | Agg boundary passes; native 2D/3D interaction/platform unverified |
| Persistence | **PASS** | Tested service edits/typed NULLs/reopen/replay/cascades and integrity verified; not all GUI paths |
| Recovery | **PASS** | Isolated Production offline CLI preflight/reset/backup restore verified; Windows/concurrency limit explicit |
| Security | **BLOCKED** | Credential guard/reset tests pass; full native role/action authorization audit not completed |
| Packaging | **BLOCKED** | No Windows/Python 3.12 installed artifact execution |

## 12. Handoff and next iteration

1. Provide a working native Qt runtime and the target Windows/Python 3.12 package; execute the module matrix as real widgets, including first-run/login/logout, keyboard/menu/button paths, modals, invalid/cancel, navigation and restart.
2. Close **R18** with an application-wide dirty/context/no-change policy, preserving successful independent saves and guarding read-only/no-op tabs. Test actual hidden/visible editors and timers, not only callback protocols.
3. Verify **R19 alternative C** natively and resolve unscoped historical discovery if required; editable migration remains a separate future capability and must never silently flatten source.
4. Verify PDF and other promised formats, bilingual layout, all native charts, peripheral knowledge/AI/reference routes and role-based authorization. Retain engineering screening limitations and obtain appropriate domain review.
5. Rerun focused/subsystem/full/real-runtime acceptance after those changes. A second real source workbook must be supplied or explicitly remain unavailable; do not fabricate Golden B.

**Final decision: NOT PRODUCTION ACCEPTED.** This is a committed remediation/verification iteration with precise remaining blockers, not a production certificate or a claim that the entire original mission is complete. The commit containing this report and its verified remote SHA are given in the final delivery message; the immutable baseline is recorded above.
