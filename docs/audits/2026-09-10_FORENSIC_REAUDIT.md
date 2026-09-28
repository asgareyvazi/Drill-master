# DrillMaster — Independent Forensic Re-Audit (2026-09-10)

This document is the final deliverable of an **independent re-audit** of the
2026-09-09 remediation session. It re-verified every material claim of that
session against the repository itself, re-ran the full test baseline, and
probed the previously-untested behaviors live. The 2026-09-09 documents under
`docs/audits/2026-09-09/` are treated as **claims to verify, never as ground
truth**.

Statuses: `VERIFIED` / `PARTIAL` / `FALSE` / `PASS` / `BLOCKED` / `NOT
VERIFIED` / `OUT OF SCOPE`.

---

## A. Repository identity

| Item | Measured value |
| --- | --- |
| Remote | `https://github.com/asgareyvazi/Drill-master.git` |
| Branch | `arena/01a085e0-drill-master` (session-fixed; all work on it) |
| HEAD at audit start | `b05ea76` — a **grafted** head (shallow-clone limitation: full upstream history is not present locally) |
| Claimed commit `ba9bb038` ("Fix P0 defects, add well-centric acceptance, CI, and 2026-09-09 forensic audits") | **DOES NOT EXIST** in this clone — `git cat-file -t ba9bb038` fails; no ref contains it. The prior session's "committed and tree clean" claim is therefore **FALSE** as stated. All of that session's output exists only as uncommitted working-tree changes. |
| Working tree at audit start | DIRTY: ~27 modified tracked files + untracked `.github/`, `docs/audits/2026-09-09/`, 4 test files, `tools/qt_headless_env.sh` |

Shallow-clone limitations (explicit): parent history beyond the graft point is
unverifiable from here; whether `ba9bb03` exists on the remote cannot be
checked (GitHub auth unavailable in this sandbox). What can be said with
certainty: **the commit is not part of this clone, and the audit baseline had
to be reproduced from the working tree, not from git history.** The recommit
closes that gap: the working tree was recommitted as two commits — the
remediation+audit commit (this report's own commit; it is the head of the
remote branch `arena/01a085e0-drill-master`) and the CI-workflow commit
(local-only tip, see §E Push row).

## B. Measured baseline (re-measured this session, from the working tree)

| Measure | Value |
| --- | --- |
| Python | 3.11.2 (CPython) |
| PySide6 / shiboken6 | 6.8.1.1 |
| SQLAlchemy | 2.0.36 |
| pandas / numpy | 2.2.3 / 2.1.3 |
| pytest | 9.1.1 |
| ruff | 0.16.6 |
| Qt headless mechanism | `QT_QPA_PLATFORM=offscreen` + no-op stub libs built by `tools/qt_headless_env.sh` (script re-reviewed: derives stub symbol sets from the installed Qt `.so` files via `readelf`/`nm`; version-script nodes `V_0.5.0` (xkb) / `LIBDBUS_1_3` (dbus) hardcoded; libGL/libEGL/libxkbcommon/libdbus stubs). Legitimate and reproducible — rebuilt this session. **Note:** stubs live at `/home/user/qt-libs/` (repo-external, non-persisted path); the correct env is `LD_LIBRARY_PATH=/home/user/qt-libs`. |
| Compile gates | `compileall core dialogs tabs tests` + `py_compile app.py run.py main_window.py verify_release.py` → exit 0 |
| Ruff defect gate | `--select E722,F821` over core dialogs tabs main_window.py app.py tests → **0 findings** |
| Ruff project config | **5489 findings** (F405 4382, F401 460, E702 327, E701 124, F403 92, E741 22, E712 10, F811 10, E703 1, F601 1, F402 1, E711 1) — ceiling `.github/ruff-debt-ceiling.txt` = 5489, exact CI ratchet command reproduced locally → 5489 ≤ 5489 |
| Full suite (final, this session) | **812 passed, 4 skipped, 0 failed, 178.53 s** (12 collected = 816) |
| Skips (each accounted) | 2× `test_ddr_acceptance` (opt-in env `DRILLMASTER_TEST_DDR_XLSX`/`_PDF` unset), 1× `test_mineru_real_integration` (`MINERU_INTEGRATION_INPUT` unset), 1× `test_packaging_smoke` (`DRILLMASTER_BUNDLE_DIR` unset — no Windows bundle). All four are deliberate opt-ins, not masked failures. |
| Baseline reproduction note | Prior session claimed "808 passed / 4 skipped" — **VERIFIED**: reproduced exactly at audit start (808/4/0, 195.90 s). Today's final count is 808 + 4 tests added by this re-audit (§C row 10, §E row F-scenario). |
| Interim anomaly, resolved | One mid-audit full run reported 800 passed / 16 skipped. Root cause: operator error — `LD_LIBRARY_PATH=/home/user/qt-libs/lib` (nonexistent) instead of `/home/user/qt-libs`; the GUI-capability probes correctly detected the unloadable Qt and skipped 12 GUI tests with explicit reasons. Re-run with the correct path → 812/4/0. No test converted a failure into a skip; the probes performed exactly as designed. |

## C. Prior-session claim → evidence → verdict

| # | Claim (2026-09-09 docs) | Evidence found this session | Verdict |
| --- | --- | --- | --- |
| 1 | Commit `ba9bb038` created; tree clean | Commit absent from clone; tree dirty with all claimed changes present as uncommitted files | **FALSE** (commit) / changes themselves real |
| 2 | Suite 808 passed / 4 skipped / 0 failed | Re-run: 808/4/0, 195.90 s; all 4 skips are opt-ins with explicit reasons | **VERIFIED** |
| 3 | E722=0, F821=0, debt 5489, compile gates | Re-measured identically (§B) | **VERIFIED** |
| 4 | Tuple-key cache fixes (`_extract_embeded_ddr_data` 43 sites, mud_chemicals 7, catalog 3) | `git show HEAD:` comparison + live extraction tests; root cause real (cache is `{row:{col:val}}`; flat-key branches were dead code) | **VERIFIED** |
| 5 | CodeResolver NameError fixed via lazy import + explicit-unavailable degradation | Live probe: RR→"Rig Contractor", F-MWD→"Directional Company", "---"→not-NPT/"" ; this re-audit additionally **narrowed the guard from `except Exception` to `except ImportError`** (a broken dialog module must propagate, not masquerade as "unavailable") + 2 regression tests | **VERIFIED** (and hardened) |
| 6 | DISPLAY→capability-probe skip conversion | No DISPLAY-based skips remain; probes import-and-load Qt, skip with explicit reason; broken `validate_rows` import fixed | **VERIFIED** |
| 7 | QAction lives in QtGui for PySide6 6.8 | Live probe confirms | **VERIFIED** |
| 8 | `ExcelImportDialog.__new__` fix; no `object.__new__` remains | 0 sites; live proof that real-shiboken classes raise TypeError on `object.__new__` while `cls.__new__` works | **VERIFIED** |
| 9 | ImportValidator unified | Single contract via subclass delegation; production imports `core.import_quality` only; no circular import | **VERIFIED** |
| 10 | Well-centric acceptance (rig≠identity, DDR continuity, sidetrack separation, variant names, hierarchy) | `tests/test_well_centric_acceptance.py` re-run green; **gap found and closed this session: rig CHANGE on the same well (scenario F) was untested** — added `TestRigChangePreservesWellIdentity` (2 tests): rig change does not fork well identity in either order; rig is a well-level attribute (last-write-wins), reports carry no rig column, `rig_day` sequence continues 1→2 | **VERIFIED** (F now covered) |
| 11 | Schematic: "PASS (R18 contract) … no-fabrication tests green (`test_real_3d_draw_boundary_and_no_data`)" | **MISATTRIBUTION + VIOLATION.** `test_real_3d_draw_boundary_and_no_data` covers *trajectory* 3D plotting (NO_DATA/INSUFFICIENT_DATA statuses), **not** the schematic auto-builder. The actual auto-generate path — `tabs/w3b_wellbore_schematic_tab.py` `_generate_auto` → `core/wellbore_schematic_engine.py:1422` `SchematicAutoBuilder.build_from_well` — **fabricates data**: TD default 3000 m, GLE 10 m, KB 15 m (and `or N` coercion converts explicit zero to the default); `_add_default_casings` (line 1581) invents a full 4-string casing program (20"/13⅜"/9⅝"/7" at TD fractions) when no casing data exists. Zero test coverage of `build_from_wall`/`SchematicAutoBuilder`. NOT fixed in this re-audit: `total_depth_m=3000.0` is the dataclass field default and the renderer depends on it (`None > 0` would raise), so a correct fix requires an explicit unknown-state design in the render engine — next-phase item (§F), not a tiny change. | **PARTIAL** — R18 save-contract PASS; auto-generate fabrication is a **standing violation** of "unknown must remain unknown" |
| 12 | Inventory: "PARTIAL — ledger math + NULL≠0 golden assertions green" | Ledger math green, but **zero≠missing is violated in the live ledger path** — three sites: (a) `core/mud_ledger.py:75-80`: explicit-zero opening + no movement is *overwritten* by previous closing ("carry_forward" heuristic); (b) `core/database.py:5646-5651` (save path): `carry_forward` defaults True and **unconditionally overwrites even an explicitly supplied nonzero `initial_stock`** with `previous.current_stock`; (c) `core/profile_import_engine.py:444,607` (`initial or 0.0`) + column default `initial_stock = Column(Float, default=0.0)` conflate "not reported" with "zero stock". `core/mud_ledger.py` has **zero test coverage**. Root cause is model-level (column cannot represent "not reported"), so remediation is a schema-semantics decision — next-phase item (§F). | **PARTIAL — with documented violations** (worse than the 09-09 doc implies) |
| 13 | Cost: "PARTIAL — Actual/Planned/Variance/AFE; Estimate/Forecast absent" | `core/report_engine.py:1695-1770` verified: rig-rate math runs **only** when the caller explicitly supplies rates (`rate_supplied`); otherwise totals come from stored `CostRecord.actual_cost`; derived figures labeled as rate rows in output. w16 variance from stored records only. No rig-rate-derived value persisted as actual. | **VERIFIED as stated (PARTIAL by scope)** |
| 14 | KPI: "BLOCKED — duplicate formula sites" | Re-confirmed sites: `core/operations_intelligence.py:79-80`, `core/report_engine.py:466,768-773`, `tabs/w12_Analysis.py:1223` (SQL AVG — a *different data source* than daily-ROP mean: definition-drift risk), `:1244`, `:1654`, `tabs/home_tab.py:468`. No canonical KPI registry exists; no new KPI tab added (constraint respected). Documented in `KPI_MATRIX.md` | **VERIFIED as stated (BLOCKED)** |
| 15 | BHA/Bit: "PASS — JSON-per-report pattern documented; run identity via import logic" | Re-confirmed: `save_bha_report` upserts by report_id first, else (well_id, bha_name); `save_bit_report` by report_id/id. Per-DDR JSON snapshots; run continuity reconstructable only by matching names/serials inside JSON — no run entity. Matches the documented daily-report-centric reality | **VERIFIED as stated (PARTIAL by design)** |
| 16 | Exception-handler remediation (40 E722 narrowed) | Diff-audit of all 6 added broad `except Exception` sites: 5 defensible (per-value contractor fallback with logging; session.close() in error path; connectivity probe → explicit "❌ Disconnected"; 2× rollback-then-close); 1 narrowed this session (row 5 above). Zero bare `except:` | **VERIFIED** (and hardened) |
| 17 | "No production imports of repositories/" | Re-grepped: zero production imports; repo classes test-only (6 test files) | **VERIFIED** |

## D. Architecture matrix (as measured, not as claimed)

| Dimension | Current state |
| --- | --- |
| Identity | Canonical = `wells.id` (36 FK references). `Well.code` globally unique; `Well.name` NOT unique. Rename via `save_well` updates in place — identity stable. No alias table; normalization at resolution time only. Rig is an attribute (well-level, last-write-wins), never an identity key — now regression-tested both orders. |
| Well resolution | TWO implementations: `DDRImportService._resolve_import_well` (authoritative; alias-tolerant, project-scoped) vs `WellRepository.resolve_identity` (exact-match, no normalization, **zero production callers** — test-only). Divergence documented; consolidation is next-phase. |
| Wellbore | No persistent entity — OUT OF SCOPE by decision (schema v3 migration required); not faked. |
| Import pipeline | `ExcelImportDialog(QDialog, DDRImportService)` — all `_save_*` helpers live in Qt-free `core/ddr_import_service.py`; acceptance tests drive the exact production class without Qt; extraction layer covered by golden tests against the real OEOC workbook. |
| BHA/Bit | Daily-report-centric JSON snapshots (§C row 15). |
| Inventory | `BulkMaterials` per-report rows + derived ledger; cannot represent "not reported" (§C row 12). |
| Cost | `CostRecord` planned/actual (+AFE fields), w16 UI; estimate path gated (§C row 13). |
| KPI | No canonical registry; duplicated formulas across operations_intelligence / report_engine / w12 / home_tab (§C row 14). |
| Schematic | `WellboreSchematic` render engine + R18 save contract OK; auto-builder fabricates on empty wells (§C row 11). |
| Schemas | `OperationalProcedure` = well_id FK + denormalized display text (acceptable, documented). |
| Minor display-level placeholders (not persisted data) | `tabs/home_tab.py` "Last Update: Today" placeholder and "👥 1 active (simulated)" users line — cosmetic, but should be wired to real data or labeled; recorded as low-priority. |

## E. Production gates

| Gate | Status | Evidence |
| --- | --- | --- |
| Test suite | **PASS** | 812 passed / 4 skipped / 0 failed / 178.53 s (this session, final) |
| Ruff defect gate (E722,F821) | **PASS** | 0 findings |
| Ruff debt ratchet | **PASS** | 5489 = ceiling (exact CI command reproduced) |
| Compile gates | **PASS** | exit 0 |
| Well identity & hierarchy | **PASS** | well-centric acceptance incl. new rig-change tests |
| R18/R19 save preservation | **PASS** | 48/48 green |
| Import atomicity/rollback | **PASS** | atomic import + partial-success diagnostics tests green |
| Zero≠missing (inventory ledger) | **BLOCKED — VIOLATION** | §C row 12 (three sites; schema semantics decision required) |
| Schematic no-fabrication (auto-generate) | **BLOCKED — VIOLATION** | §C row 11 (render-engine unknown-state design required) |
| Schematic R18 save contract | **PASS** | R18 suite |
| CI (remote) | **BLOCKED — local configuration verified, remote execution not independently verified** | `.github/workflows/ci.yml` verified locally line-by-line: matrix 3.10–3.13 matches `requires-python >=3.10,<3.14`; apt set (libgl1/libegl1/libxkbcommon0/libdbus-1-3/libfontconfig1) matches the empirically-derived stub set; `requirements-lock.txt` complete against actual third-party imports (PyYAML/Pygments present in venv but unused by project code); ratchet arithmetic reproduces 5489≤5489; pytest step sets `DRILLMASTER_ENV=test` (consumed by `app.py`). No remote run observed; additionally the workflow file itself has not yet reached the remote branch (see Push row). |
| Windows GUI | **NOT VERIFIED** | plan: `VERIFICATION_PLANS.md` §1 |
| Installer/bundle | **NOT VERIFIED** | plan: `VERIFICATION_PLANS.md` §2 |
| MinerU / local-AI | **NOT VERIFIED** | plan: `VERIFICATION_PLANS.md` §3 |
| Push to remote | **PARTIAL** | The remediation+audit commit (all code fixes, tests, docs, debt ceiling) **pushed** — remote branch `arena/01a085e0-drill-master` created. The CI-workflow commit (`.github/workflows/ci.yml` only, branch tip) **blocked**: remote rejects with `refusing to allow a GitHub App to create or update workflow .github/workflows/ci.yml without workflows permission`. Action for repo owner: grant the GitHub App `workflows` permission (or push the branch tip from a token that has it). Per policy, no credentials were requested. |

## F. Evidence-based next-phase recommendation (priority order)

1. **Schematic unknown-state design (highest data-integrity impact).** Make
   `WellboreSchematic.total_depth_m` / `gle_msl` / `kb_msl` explicitly
   nullable-or-status, teach the renderer a real `UNKNOWN` state, remove
   `_add_default_casings`, and gate auto-generate behind explicit "no data"
   UI messaging. Regression tests: empty-well auto-generate produces an
   explicit no-data state and persists nothing fabricated; explicit zeros are
   preserved (no `or` coercion). Until then, the w3b auto-generate button is
   the single known path that can write fabricated engineering data.
2. **Inventory zero≠missing + carry-forward semantics.** Decide the model:
   nullable `initial_stock` (None = not reported) or an explicit
   `opening_reported` flag; then fix `mud_ledger.py:75-80`,
   `database.py:5646-5651` (carry_forward must never overwrite an explicitly
   supplied opening), and the profile-engine `or 0.0` coercions; add the
   missing `mud_ledger` test coverage (currently zero).
3. **Wellbore schema v3** (already scheduled): wells → wellbores → sections →
   DDRs, with sidetrack as wellbore, per the 2026-09-09 audit §4.
4. **KPI canonicalization**: extract one formula module (mean-of-daily-ROP vs
   SQL-AVG-over-DrillingParameters must become one *defined* choice per KPI),
   then point w12/home/report_engine at it. Debt-ratchet the duplication away
   incrementally — no new KPI tab.
5. **First real CI run**: push, watch the Actions run, fix only what the run
   proves broken; lower the debt ceiling as debt is paid.
6. **Execute `VERIFICATION_PLANS.md`** (Windows GUI, installer, MinerU) on
   real targets; convert their NOT VERIFIED rows to PASS only with recorded
   evidence.
7. **Consolidate well-resolution**: either promote
   `WellRepository.resolve_identity` to the single implementation (adding
   normalization) or delete it from the test surface; two divergent resolvers
   is a standing drift risk.

---

*Audit method: every verdict above was re-derived this session from the
working tree, live probes, or a full suite run; no verdict was inherited from
the 2026-09-09 documents without independent evidence. The two new violations
(§C rows 11–12) were present in that session's output — its Schematic row
cited an unrelated test as no-fabrication evidence, which this re-audit
corrects.*
