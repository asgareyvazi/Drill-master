> **HISTORICAL MISSION RECORD — Mission 30 checkpoint (2026-09-23).** Its inventory baseline (2232 occurrences) and its `NOT RELEASE-CERTIFIABLE — EVIDENCE INCOMPLETE` verdict describe the tree as it stood then; the numbers have since been re-adjudicated by Missions 31-33. Current state: 8932 occurrences, 3712 verified-correct, 2266 intentional-by-design, 47 defect-fixed, 49 removed-with-evidence, 2837 under-review, 4 evidence-incomplete — see [M33_SEMANTIC_AUDIT.md](M33_SEMANTIC_AUDIT.md). The body of this document is preserved unedited.

---

# M30 — release decision and 33 audit answers

**NOT RELEASE-CERTIFIABLE — EVIDENCE INCOMPLETE**

Date: 2026-09-23. Mission30 is **not complete**. Green tests do not close 2191 unread inventory occurrences, the additional reviewed-but-open occurrence, or the 69-domain audit. This is not an external-only rejection.

## Verified execution boundary

| Check | Observed result |
|---|---|
| Tested source | `e2eeb3539c5d9c468e73961824e9fe5229864a59` |
| Source tree | `e6e6982d8238917d877f1716a9c6f59eef5649c4` |
| Branch | `arena/01a0c945-drill-master` |
| Source gate | PASS, exit 0, clean worktree at invocation |
| Pytest | **1732 collected; 1729 passed; 3 skipped; 0 failed/errors/xfail/xpass/deselected; 20 warnings; 236.34 seconds** |
| Environment | Linux, Python 3.11.2; pytest 9.1.1; Ruff 0.16.6; build 1.6.1; locked runtime; offscreen Qt with explicitly declared dependency stubs |
| Compileall | PASS |
| Global E722/F821 | PASS; not equivalent to all lint clean |
| Scoped lint | **5336**, within budget 5375, Ruff exit 1; **NOT lint-clean** |
| All-root Ruff | **5547** diagnostic occurrences; separate scope from the ratchet |
| pip check / lock verification | PASS; no runtime dependency/lock changes introduced |
| Clean staged wheel | PASS; `drillmaster-1.0.0-py3-none-any.whl` built, installed in isolated target |
| Outside-checkout smoke | PASS: installed `app.py --package-smoke`, no checkout resource fallback |
| Negative controls | 14 inherited + 10 new detected; separate wheel omission detected by focused test and installed-wheel gate; all source hashes restored |
| Native Qt | EXTERNAL-BLOCKED: missing `libGL.so.1`; stubs are not native runtime evidence |
| Actual current-SHA CI | **UNAVAILABLE**: fresh final-source API query returned HTTP 401, not PASS |
| Windows EXE/installer | NOT-RUN |
| Real PDF/MinerU | Explicit opt-in attempt **EXTERNAL-BLOCKED**, pytest actually failed because MinerU was disabled/not detected |

Full log: [`docs/audits/m30-evidence/final-gate-e2eeb35.txt`](docs/audits/m30-evidence/final-gate-e2eeb35.txt). Later documentation-only commits are not silently substituted for this test SHA. The delivery HEAD is obtained from Git and the external publication-state artifact, avoiding a self-referential commit identifier inside a committed report.

### Reproduction

From the repository root, with the locked environment and the explicitly described local Qt stubs available:

```bash
QT_STUB_DIR=/home/user/qt-libs \
LD_LIBRARY_PATH=/home/user/qt-libs \
QT_QPA_PLATFORM=offscreen \
DRILLMASTER_TEST_DDR_XLSX='/home/user/Drill-master/08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx' \
.venv/bin/python verify_release.py \
  --expected-sha e2eeb3539c5d9c468e73961824e9fe5229864a59
```

Run that exact SHA command only on that source snapshot; on a later delivery commit use its actual SHA, do not bypass identity/clean-tree checks. For native Linux verification, install real Qt system libraries, omit the stub variables and rerun; a stubbed pass is not a native substitute. Windows, production DB and MinerU acceptance require their real environments/assets.

## 33 explicit answers

1. **What Git identity was audited?** Branch `arena/01a0c945-drill-master`; tested source HEAD and tree above. Base/patch comparison is `c28bbef37cbac9de7abcfa693e7e21f678fa74ab`. Source gate observed a clean tree. Documentation/evidence commits follow; final delivery HEAD/cleanliness must be read from the publication-state artifact, not a stale historical SHA.

2. **Were the old commits/tree/patch independently reconstructed?** The inherited files exactly reproduced M29's reported tree and 352 fingerprints; recovery is `964e922`, not fabricated `fb857d7` ancestry. The reconstructed binary patch has the recorded `f0ce2d...` hash and applies to the exact recovery tree. Original patch file is absent. `95dd631` and `c28bbef` are real local history; original `0bbcbd4`, `fb857d7`, `beaf963` are unavailable. Original committed implementation/certification and later inherited dirty repairs are not conflated.

3. **Is the remote updated / is CI green?** Initial GitHub reads/fetch/API succeeded. A later final-source CI API request failed with HTTP 401 Bad credentials. The earlier push was rejected because the GitHub App lacks **workflows** permission for `.github/workflows/ci.yml`; that rejection was a workflow permission issue, not an authentication error at that time. The later 401 is a separate current connection problem. No successful session-branch publication is claimed. After rejection, GitHub could resolve uploaded commit object `9d511cd`, but no session-branch ref existed: reachable object lookup is NOT a published branch. The last successful query for `9d511cd` returned no run; the final-source `e2eeb35` query is UNAVAILABLE because of HTTP 401. Reconnect GitHub in Arena before retrying publication/CI. Historical successful runs at another SHA do not count. An applicable patch is supplied instead; do not strip the workflow or change branches to bypass permission.

4. **What happened to branches?** `branches.json` records ancestry, unique commits and unique files. Four older remote session refs are ancestors, classified MERGED-SAFE-TO-DELETE but retained. Current local session and previous remote checkpoint ref are ACTIVE. Local/remote `drill-Master` are UNMERGED-REVIEW-REQUIRED: three unique commits and a real PDF asset. `origin/HEAD` is an alias, not another independent branch. No branch was deleted or switched.

5. **Were all 2232 substantive dispositions completed?** **No. 41 reviewed, 40 closed, 2191 unreviewed.** A/B/C/D/E/F/G = **12/16/2/9/1/0/2192**. G includes one actually reviewed unresolved item plus 2191 explicit queue placeholders. The JSON's 2232 rows are not 2232 semantic judgments. Original IDs collide 100 times; stable ordinals preserve every occurrence.

6. **Are critical/high repository areas still unreviewed?** Yes. Conservative queue priorities leave **1139 CRITICAL and 1053 HIGH unclosed occurrences**. These numbers are review priorities, not confirmed defect counts. Exhaustive repository integrity and certification remain blocked.

7. **Are model/schema/migration/write boundaries complete?** No. Existing fresh-schema, ownership, startup and transactional tests ran; selected DB writes were repaired. Every model field/default, migration, legacy upgrade, merge, bulk path, direct/raw SQL/import/restore route has not been individually closed. Historical 62-model/118-index or isolated-import counts are not reused as fresh M30 certification.

8. **Is well→bore→section→report ownership universally safe?** Selected ORM, parent-move, contradictory-section, two-well and ambiguous-candidate tests PASS. Search leakage and bulk well/unit identity were fixed. Whole-well versus bore aggregation, same-name UI selection and every bypass path remain partial; no universal PASS.

9. **Is scope attribution honest and wired?** Persisted coverage is separated from attributable proposals; malformed candidate chains rejected; preview remains read-only; detached result data tested. DataQualityService consumes coverage. No automatic production apply caller was found. Resolution intentionally converges across safe passes; it is not mislabeled one-pass fixed-point idempotence.

10. **Are historical snapshots immutable and reference data separate?** Specific nested input/output alias regressions and attribution serialization PASS. Existing persisted revision/MSE snapshots were exercised. No claim that every master reference, historical engineering input and derived result has been fully traced.

11. **Are NULL/zero/unknown/failed/not-run distinctions preserved repository-wide?** Not certified repository-wide. Selected financial, inventory, time, safety, retrieval and plan paths preserve them under the documented contracts. Absent stock movement intentionally means no movement; missing opening does not mean zero. Failed search and unavailable save no longer masquerade as successful emptiness/persistence.

12. **Was the expanded Plan/Actual matrix tested?** Yes, scalar and persisted: `(None,None)`, `(None,0)`, `(0,None)`, `(0,0)`, `(None,100)`, `(100,None)`, `(0,100)`, `(100,0)`, `(100,100)`, `(100,80)`, `(80,100)`. All corresponding tests ran. Finite-derived variance/percentage and abs(planned) annotation were repaired. All Forecast/Target pairings and every UI/report/export consumer remain unclosed.

13. **Does missing Safety mean zero incidents?** The dedicated missing/zero/incomplete/latest-record regressions and W8 subprocess tests PASS. Missing record is not accepted as a no-incidents assessment. This is not full Safety import/default/export certification.

14. **Is the complete financial pipeline certified?** No. Currency, nullable amounts, persisted actual versus labeled projection, finite derived values and selected dashboard/export paths were tested. Complete payroll, tax, insurance, maintenance, standby/moving, fuel, NPT allocation, CAPEX/revenue/payback/NPV/IRR input provenance and assumptions have not all been traced.

15. **Can mixed or unknown currencies become a single total?** Targeted canonical tests prevent that without FX. Explicit UNKNOWN/N/A/not-recorded markers now remain unknown, rather than authorizing totals. Per-currency grouping is retained; no project-currency imputation or invented conversion. Arbitrary external currency-label validity is not certified.

16. **Are economic formulas and projections field-validated?** No. No new model or invented economic assumptions were introduced. Existing engine tests ran; complete units, historical assumptions, revenue/payback/NPV/IRR model validation and external acceptance remain NOT-RUN to closure.

17. **Are time/NPT/logistics inputs trustworthy?** Invalid/bool durations and nonboolean NPT classification now remain unknown. Existing NPT report-scope/calendar tests ran. Full transport, personnel, standby/moving, time overlap and historical input audit remains partial.

18. **Are all engineering engines traced end-to-end?** No. MSE representability and shared numeric error contracts were repaired and tested. Registered-engine, persistence and cross-process tests ran. Trajectory, hydraulics, torque/drag, cement, fishing, well control, mud, bit, anti-collision and casing still require complete per-path input→validation→result→snapshot→UI/export semantic closure and appropriate engineering acceptance.

19. **Were real imports, duplicates and malformed input tested?** The provided real XLSX was used in the gate, including existing DDR review/persistence/lifecycle tests. Malformed stock writes and duplicate bulk identities have new rollback regressions. Every CSV/vendor/manual/PDF identity, NFC/case/unit/provenance and reimport path is not certified. A real PDF was recovered from the unmerged branch; it was not discarded or misrepresented as already parsed by MinerU.

20. **Is UI/HTML/PDF/Excel/JSON field parity complete?** No. Existing export regression and failure tests PASS for their fixtures, including exporter false-return controls. A complete field-level parity matrix was not delivered; native rendered PDF/Windows typography and every provider remain unverified.

21. **Are writes/backups/failures honest?** Demonstrated bulk rollback, live invalid output, no-provider saves, query failures and disappearing-source backup are fixed. Previous backups survive failure; a missing source is opened read-only and cannot be recreated as an empty success. All real ACL/readonly/locked-DB/power-loss/partial-write combinations are not closed.

22. **Was the full UI selection lifecycle exercised?** No manual native run. Relevant subprocess widget/selection tests PASS with explicit stubs. Every well/bore/section/report/parameter transition, stale refresh, same-name selection and persisted reopen is not covered by this checkpoint.

23. **Is AI production integration certified?** No. Retrieval is explicitly scoped keyword search with typed sources, no fabricated 0.75 probability. Failed/no-match/invalid-query differ. HistoricalDDRSearch is not active UI wiring; formation similarity remains a retained prototype. Real providers, Ollama/local models, credentials, online timeouts and offline acceptance have not all run. Deterministic engines remain the intended numerical authority, not an independently certified statement for every route.

24. **Did real MinerU pass?** No. The recovered 740,510-byte PDF has SHA-256 `6ce9b37e4e30c7800191598d9f9febebc12d4cf0ab5932c5d7f6ad1b789a226c`. Explicit PDF acceptance failed in 0.05s with `ENVIRONMENT-BLOCKED: MinerU is disabled or not detected`. Real executable, models and configuration are required. Mock/parser boundary tests are not a substitute for real PDF extraction/provenance acceptance.

25. **Did clean packaging and Windows installation pass?** Clean staged Linux wheel build/install/outside-checkout smoke PASS; missing UI package mutation is detected. Windows source build definitions exist, but actual EXE, installer, clean user profile, writable AppData, upgrades, DLL/plugins and real GUI are NOT-RUN. Structural fake bundle tests are not frozen-runtime acceptance.

26. **What are the exact test results and integrity limits?** 1732/1729/3, zero failures/errors/xfail/xpass/deselected, 20 warnings, 236.34s in the final source log. New regression module: 42 cases. Positive assertions include real SQLite/service behavior and isolated widgets, not assert-True integrations. All 1700+ tests have not been individually audited for no-ops, mocks, order dependence or every unreachable assertion.

27. **Did mutations really fail and restore?** Yes: 14 inherited + 10 new focused controls all exit 1 with expected failed tests and restored SHA-256. Separate wheel omission fails focused test and wheel verifier. JSON records and stdout are archived. This is selective test sensitivity, not exhaustive mutation coverage.

28. **Are the three skips justified individually?** See the table below. They are external opt-in acceptance tests, not passed integrations. The real PDF is available locally now, but MinerU is not; its explicit opt-in attempt is recorded as a failure/environment block. None is dismissed for inconvenience or expense.

29. **Were warnings classified?** Yes by observed occurrence family below; not all consumer consequences closed. The openpyxl unsupported-validation warning remains an explicit workbook-fidelity risk, not blanket harmless style. No native field-validation success is inferred from dependency warnings.

30. **Is lint clean / debt understood?** No. Scoped 5336 (baseline 5334), root 5547. Categories and each diagnostic location are archived, but individual semantic closure is incomplete. Wildcards, unused computations/imports and shadowing are not all called harmless. Critical E722/F821 PASS is much narrower than all-lint PASS.

31. **Are dependencies/security/resources fully coherent?** Lock verification, pip check, compile and installed-wheel checks PASS; runtime dependencies/lock untouched. Current scoped search is bounded and avoids lazy owner N+1; backup respects OS failure. Full optional-import graph, all paths/pickle/subprocess/credentials/logging/temp/handle/thread/memory/resource risks remain unreviewed. No exhaustive security/performance certificate.

32. **Are docs/dead code/history claims corrected?** Living current-evidence banners now point to M30 and distinguish current results from historical/unverified body claims. Historical audits remain preserved. Claim-by-claim verification of all documentation is incomplete. No module was deleted merely because it looked unused; unmerged PDF history and unwired APIs were retained. Scans and stale counts are not promoted into current facts.

33. **What is the final decision and blocker separation?** **NOT RELEASE-CERTIFIABLE — EVIDENCE INCOMPLETE.** Repository audit obligations remain; external acceptance is also missing; conditional maintenance debt is separate. Details below. This does not assert all repository bugs are repaired merely because the demonstrated ones and the gate are green.

## Three skips — independent classification

| Test | Gate status / reason | Local possibility and production impact |
|---|---|---|
| `test_real_ddr_pdf_mineru_common_ir_review_and_atomic_db` | OPTIONAL-SKIPPED in standard gate: PDF opt-in variable absent | PDF asset recovered; actual opt-in attempted and FAILED/EXTERNAL-BLOCKED for missing MinerU. Real parsing/common-IR/review/atomic DB acceptance still not established. |
| `test_real_mineru_parse_and_normalize` | OPTIONAL-SKIPPED: `MINERU_INTEGRATION_INPUT` absent | Requires real installed executable/models/config and an input file; dependency is optional, but this production integration cannot be declared accepted. |
| `test_real_windows_bundle_smoke_when_provided` | OPTIONAL-SKIPPED: Windows bundle unavailable | Real Windows build and clean-machine execution required. Linux wheel/fake bundle structural tests cannot substitute. |

## Twenty counted warnings, plus teardown output

- **14 openpyxl Data Validation extension warnings**: 1 DDR acceptance, 3 DDR follow-up lifecycle, 1 forensic DDR, 1 DDR regression, 3 Excel intelligence, 1 golden DDR, 1 real OEOC golden, 3 review-contract certification. Reading/extraction does not rewrite the original file; unsupported extension round-trip preservation is **not established**. Export/template fidelity consequences remain open, not waived as style.
- **2 SwigPyPacked + 2 SwigPyObject + 1 swigvarlink** dependency deprecations during core-dependency import. No failed computation was observed from these warnings; future binding compatibility needs dependency-owner attention. They are not native Qt/Windows proof.
- **1 large-file warning**: `main_window.py` 3062 lines, `core/database.py` 10374, W12 3215, W13 5398. Maintainability/reviewability risk, not itself a demonstrated functional failure. No broad rewrite was performed to silence it.
- One additional `swigvarlink` deprecation appears at interpreter teardown outside pytest's counted 20. It is retained in the raw log, not secretly added to or omitted from the pytest count.

## Lint classification, without semantic laundering

Scoped debt: F405 4471; E702 541; E701 124; F403 92; F841 42; E741 20; F401 19; F541 16; E712 8; F402 1; E711 1; E703 1. Total **5336**. Root count is separately 5547.

- F403/F405: namespace/architecture and potential correctness risk; symbols not all resolved individually.
- F841/F401: unused-value/import/re-export/side-effect candidates; not proof of removable or harmless code.
- F402/F811: shadowing/duplicate bindings need context. Inspected F402 is local `field` iteration in ImportValidator, not reassignment of module-level dataclass.field; inspected root F811 repeats the same SectionDataWidget import. These occurrences do not justify mass cleanup.
- E711/E712: SQLAlchemy comparison operators must not be blindly replaced with Python `is`/boolean expressions. The inspected diagnostics concern ORM expressions, including contractor NULL filtering and active/NPT flags.
- E701/E702/E703/E741/F541: diagnostic category is formatting/readability; that category is **not approval of the surrounding business logic**.

Individual diagnostic locations/categories are in compressed JSON. No security/complexity/architecture absence is inferred from Ruff's selected rules.

## Blocker buckets

### Repository audit / evidence blockers

2191 unreviewed occurrences; one reviewed legacy migration/provenance gap; 69 partial domains; incomplete financial/engineering/write-path/export-parity/UI/test/lint/doc/security/resource closure. Unsupported spreadsheet-validation round-trip consequences remain open. These are not relabeled external.

### External acceptance / publication blockers

Native Qt environment; real Windows EXE/installer/clean profile/upgrade; real MinerU executable/models/PDF acceptance; production legacy DB fixtures; real optional provider acceptance where supported; GitHub connection HTTP 401, App workflows permission and actual source/delivery-SHA CI execution. App permission must be repaired through the GitHub/Arena connection by an authorized user, not by supplying credentials in chat or bypassing the workflow.

### Conditional nonblocking maintenance

Investigated redundant import/local variable shadowing, layout diagnostics and dependency deprecations with no observed functional failure may be maintenance work. They do not make the **entire** lint/warning backlog nonblocking. Temporary-backup cleanup denied by the OS is a documented limitation requiring operator attention, never a successful backup claim.
