# M53–M60 DrillMaster integrated product completion report

Branch `arena/72010272-drill-master`. Baseline code `36a847a753b86e946a57e5dc720986eb0a10638d`, baseline report `39d86a778f3b86901c72c3ba3586c611c8eb624a`.

Release status: **UNSIGNED and NOT RELEASE-APPROVED.** There is no tag, installer, EXE or release bundle. Windows desktop, field and production acceptance remain owner items.

Test environment for every result below: Linux 6.1, 2 CPUs, Python 3.11.2, PySide6 6.8.1.1, **offscreen Qt** with a stub libGL ("Linux offscreen"), synthetic data only. This is **not** Windows desktop testing. Windows CI runs the same suite on a GitHub-hosted Windows runner.

## 1. Outcome by phase

| Phase | Priority | Result | Summary |
|---|---|---|---|
| M53 Dashboard | P0 | **COMPLETE** (light theme NOT IMPLEMENTED; ECD chart NOT IMPLEMENTED, no data field) | Professional dark English/LTR dashboard: 20 KPIs with definition, unit, source, freshness and drill-down; portfolio; charts only with data; real-survey trajectory preview; linked alerts; recent activity; consistent filters; stale-guarded worker; 5 screenshots |
| M54 DDR | P0 | **PARTIAL** | Complete: navigation, timeline, duplicate for review, time-log validation, versioned profiles, generic PDF tables (scanned detection, margins, multi-page/ruled continuation, wrapped cells), review detail panel, explicit "OCR unavailable". Partial: batch import; profile date formats, table rules, continuation and confidence threshold are stored but not applied |
| M55 Directional | P0 | **PARTIAL** (core workflow COMPLETE) | Complete: validated survey import wired into W6; plan designer (KOP/hold/build/drop/turn/hold-to-TVD, DLS limit, targets) on the canonical MinCurv, golden against closed form; designed plan → plan vs actual (HL/RL/along). Partial: no `WellPlan` versioned model, no DLS/inc/az-vs-MD plot set. Anti-collision stays SCREENING; ISCWSA OWNER REVIEW REQUIRED |
| M56 W13 workbench | P0 | **PARTIAL** | New: calculator search, favourites and recents over the live W13 tree. Existing: categories, engine records for 5 calculators, MSE history. Not implemented: case compare, input-set save/reopen, torque & drag improvement |
| M57 Architecture/casing/cement | P1 | **PARTIAL** (audit only) | Existing schematic, API TR 5C3 pipe-body subset casing engine, cement engine; no new linking |
| M58 Operational analytics | P1 | **PARTIAL** | ROP, NPT, cost per metre, AFE vs actual and deterministic alerts delivered through M53; ML NOT IMPLEMENTED (no dataset; owner-gated) |
| M59 Optional modules | P2 | **NOT IMPLEMENTED** | Optional; recorded in the matrix |
| M60 Integration | P0 | **PARTIAL** | Offline readiness complete (pre-existing gates); shared well context partial; unified calculation history NOT IMPLEMENTED |

The per-capability detail is in `docs/engineering/PRODUCT_CAPABILITY_MATRIX.md`.

## 2. What the user can now do

* **Home:** see the portfolio state at a glance. Every number traces to a definition and a source, and missing data is shown as Unavailable rather than zero. Click through to the well, report or tab behind any card, row or alert.
* **W2 daily report:** move between reports with a timeline or Previous/Next without losing edits. Duplicate a report into an unsaved draft for review. Overlapping time intervals are blocked at save.
* **DDR import:** choose a versioned operator/format profile. Read text PDFs with multi-page and ruled tables correctly, see scanned pages flagged with "OCR unavailable", and review every field with its full provenance before anything is written.
* **W6 survey import:** import CSV/TXT/DAT/XLSX surveys with an explicit depth unit and azimuth reference. Rejected rows are listed with reasons, and nothing is saved until Save.
* **Trajectory viewer → Plan designer:** design a J/S/turn plan with DLS-limit warnings and target checks, export it, and send it straight to plan-vs-actual comparison.
* **W13:** find any calculator by name or by the titles of the groups inside it, mark favourites and reopen recent calculators.

## 3. Defects found and fixed during the programme

| Defect | Cause | Fix | Evidence |
|---|---|---|---|
| Full suite hung forever in `test_m45_ui` (would show a spurious modal prompt to a user) | M54's unsaved-change guard counted the read-only related-documents table, refreshed after a link made in the Documents tab, as an edit | Display-only widgets opt out via `core/editor_bindings.exclude_from_editor_snapshot` (related documents, report timeline). This matches the module contract that navigation views are not pending saves | `test_display_panels_do_not_count_as_unsaved_edits_but_real_edits_do`; mutant `EB-display-panel-counted-as-edit` |
| Full suite **segmentation fault during garbage collection**, plus two M50 disposal failures | The first M55 viewer wiring stored a bound method of the viewer on the embedded designer (a Python reference cycle), so Qt wrappers were left to an arbitrary GC | Designed plans are handed over through the Qt signal `plan_ready`. The designer's button lambdas were replaced by bound slots, and the finder uses bound slots too | M50 disposal tests pass; `test_the_embedded_designer_holds_no_python_reference_to_the_viewer`; mutant `TV-callback-reference-cycle` |
| Survey importer lost source row numbers for canonical-validation issues | Read a non-existent `source` key | Reads `row` / `source_location.row` | `test_invalid_rows_are_rejected_with_their_source_row` |
| Exception-silent ceiling exceeded by 2 | Two deliberate fall-through handlers without justification | `# silent-ok:` reasons added; ceiling unchanged | exception gate rc=0 |

The suite hang and the GC segfault were caught before any push of the affected code. Neither reached a pushed commit.

## 4. Verification

All results are for the final code tree, `44f124bf1ab2d5c573b9875f19e0ff82ce5915cb` (Linux offscreen, synthetic data).

| Gate | Result | Detail |
|---|---|---|
| Full suite (`pytest tests/`) | **PASS** | 4041 passed, 1 failed, 4 skipped in 17 min. The one failure was a pre-existing time-of-check/time-of-use race in the M52 lifecycle-stress helper `_alive` (`/proc/<pid>/stat` vanished between `is_file()` and `read_text()`). Fixed in `087bd67` (read once, same meaning, no assertion changed); that file then passed 21/21 three times. The mutation-gap work, made after that run, added one test and strengthened two. Those files passed in a targeted run (57 passed) |
| Expected skips | 4 | `test_ddr_acceptance.py:33` ×2 (real DDR opt-in), `test_mineru_real_integration.py:26` (real MinerU opt-in), `test_packaging_smoke.py:218` (no Windows bundle) |
| Lint ratchet (ruff 0.16.6) | **PASS** | debt 727, ceiling 727 (unchanged). All new and changed files are ruff-clean |
| Exception-silent ceiling | **PASS** | rc=0; total 83 / core 81 / tabs 0, ceilings unchanged; two new deliberate handlers carry `# silent-ok:` reasons |
| Privacy gate | **PASS** | 1247 files scanned, 0 findings |
| Coverage floor (45.50) | via CI | Enforced by the Source gate's Python 3.12 leg (`verify_release.py --coverage`) on the exact SHA; see section 8 |
| Mutation (M53–M56) | **PASS** | 38/38 killed (section 5) |

Test count change: +82 tests over the M53 tip (3965 → 4047 collected). They come from the new M54 tests (workflow 17, PDF tables 12, profiles 22), the M55 directional tests (25), the M56 finder tests (6) and the regression tests named in section 3. No test was removed or skipped. Two existing expectations changed, each for a real product change:
* `test_trajectory_3d` now lists the new "Plan designer" tab; the assertion stays an exact list;
* `test_m52_lifecycle_stress._alive` no longer has the race.

## 5. Mutation testing

`tools/quality/mutation_m53_m56.py` (M46 engine; scratch copy; each snippet matches exactly once). Final complete run on `44f124b`: **mutants=38 killed=38 survived=0 declared_equivalent=0 invalid=0 complete=True** (baseline 114 passed). Evidence: `docs/mission-reports/m53-m60-evidence/mutation_m53_m56_44f124b.json`.

| Group | Mutants | Killed |
|---|---|---|
| M53 dashboard (OD/HT) | 8 | 8 |
| M54 W2 workflow | 6 | 6 |
| M54 PDF generic tables | 6 | 6 |
| M54 profiles and normalizer | 4 | 4 |
| M54 regression fix (EB) | 1 | 1 |
| M55 survey import and W6 | 5 | 5 |
| M55 designer, compare and viewer | 5 | 5 |
| M56 finder | 3 | 3 |

The first complete run killed 35/38. The three survivors were genuine test gaps, and the **tests** were strengthened; no mutant was changed:
* `OD-options-from-filtered-wells`: options were only checked under a company filter. Now also checked under a rig filter;
* `WP-target-radius-ignored`: no missed target was tested. Now a mirrored target and a target without a radius are tested;
* `CF-recents-unbounded`: the tree had 5 pages, fewer than the bound of 8. Now 15 distinct pages.

Declared equivalent and therefore excluded: removing the dashboard's own single-currency guard. `cost_semantics.summarize_costs` already returns `total_actual=None` for mixed currencies, so no observable change exists.

## 6. Open source and dependencies

No new survey, no copied upstream code, and no new runtime or development dependency. `pyproject.toml`, `requirements-lock.txt` and `THIRD_PARTY_NOTICES.md` are unchanged from the M52 baseline. Details are in `docs/engineering/OPEN_SOURCE_ADOPTION_REGISTER.md` (M53–M60 update). PyMuPDF AGPL-3.0 remains on the owner risk list.

## 7. Owner decisions still open

Local OCR engine, embedding or LLM models; GPL/LGPL/CC-NC code (pro-well-plan torque_drag, pwptemp); welleng ISCWSA error models and reference validation; PyMuPDF AGPL licence; well-control calculator approval; release, tag and signing; Windows desktop, field and production acceptance; branch protection; ML datasets and training.

## 8. Git and CI evidence

**Final code SHA:** `44f124bf1ab2d5c573b9875f19e0ff82ce5915cb`. Pushed; `git ls-remote origin refs/heads/arena/72010272-drill-master` returned exactly this SHA before the report commit. The report commit is the child commit that adds this file. Its SHA and CI are recorded in the final mission reply, because a file cannot contain its own commit SHA.

| Workflow | Run ID | Jobs (conclusion) | Head SHA | Conclusion | URL |
|---|---|---|---|---|---|
| Source release gate | 41285408077 | source (3.11) ✅, source (3.12, with coverage floor) ✅, source (3.13) ✅ | `44f124bf1ab2d5c573b9875f19e0ff82ce5915cb` | **success** | https://github.com/asgareyvazi/Drill-master/actions/runs/41285408077 |
| Windows release validation | 41285408177 | windows-release ✅ (job 124785572303) | `44f124bf1ab2d5c573b9875f19e0ff82ce5915cb` | **success** | https://github.com/asgareyvazi/Drill-master/actions/runs/41285408177 |

Coverage: the Python 3.12 leg runs `verify_release.py --coverage` and fails below `.github/coverage-floor.json` (45.50). It succeeded, so the floor is met on this SHA. The exact percentage is **NOT RETRIEVED**: the job-log storage host is not reachable from this sandbox.

Windows CI is GitHub-hosted automation, **not** Windows desktop acceptance.

**Earlier tips in this programme (honest record):**
* M53 `7e4e7f0867658da82aa6c47519dd18e2384e608b`: Source 41278445093 and Windows 41278445120 were both **cancelled** by the concurrency group when the next push arrived. No green run exists for that SHA; it is superseded by `44f124b`.
* M54 part 1 `bd385e7741ec083ca1de18c77c803c0cc5f2ee3d`: Windows 41279045793 **success**. Source 41279045740 was **cancelled after 25 minutes** (job `timeout-minutes`), because that SHA contained the W2 modal hang described in section 3. Fixed in `13b4af2`.

Commits of this programme (phase-level, conventional):

| SHA | Commit |
|---|---|
| `7e4e7f0` | feat(dashboard): M53 English/LTR operations dashboard with filters, KPIs, charts and well detail |
| `bd385e7` | feat(ddr): M54 report timeline, duplicate-for-review, time-log save validation, generic PDF tables |
| `13b4af2` | fix(ddr): display-only panels are not unsaved edits (M54 hang) |
| `087bd67` | test(quality): read /proc once in lifecycle stress helper (TOCTOU) |
| `bc2669b` | feat(ddr): M54 versioned report profiles and review detail panel |
| `93d12c2` | feat(directional): M55 survey import, plan designer, plan handover |
| `9a21292` | feat(w13): M56 calculator search, favourites and recents |
| `44f124b` | test(quality): M53-M56 mutation set; close three survivor gaps |

`git log --oneline -n 30` at the final code SHA:

```
44f124b test(quality): M53-M56 mutation set; close three survivor gaps
9a21292 feat(w13): M56 calculator search, favourites and recents
93d12c2 feat(directional): M55 survey import, plan designer, plan handover
bc2669b feat(ddr): M54 versioned report profiles and review detail panel
087bd67 test(quality): read /proc once in lifecycle stress helper (TOCTOU)
13b4af2 fix(ddr): display-only panels are not unsaved edits (M54 hang)
bd385e7 feat(ddr): M54 report timeline, duplicate-for-review, time-log save validation, generic PDF tables
7e4e7f0 feat(dashboard): M53 English/LTR operations dashboard with filters, KPIs, charts and well detail
39d86a7 docs(m52): mission report, OSS register update, evidence and screenshots
36a847a fix(harness): breadcrumb after a progress dot; per-repetition annotations
6ec1603 fix(test): windows harness ids/crash class, registry scan, re-anchor moved mutants
396b57d test(m52): mutants for the PDF report split and the NPT tint
a439fe3 chore(screenshots): M52 capture script (real widgets, synthetic data)
410b74c fix(ddr): keep cell styles under the NPT tint; blocked import looks disabled
f8ca619 ci(windows): M52 lifecycle stress harness and M52 tests on Windows
c317dce feat(import): split multi-report DDR PDFs before review (M52)
906fde5 docs(m52): open-source adoption register for the 50 reviewed repositories
0f28418 test(m52): mutants for analysis paint, GC, trajectory comparison, plug and DDR edits
eac9063 feat(ddr): reorder time-log rows, safe row removal, report navigation (M52)
77d0ab4 feat(cement): balanced cement plug calculator with saved, verifiable runs (M52)
2e37f6c feat(trajectory): plan vs actual and offset-well comparison screening (M52)
3905cb7 perf(analysis): staged off-thread chart payloads and GC scheduling (M52 2.1)
404e175 fix(knowledge): a quoted sentence needs its own support
ef3a291 fix(knowledge): read scope lists on a worker; release QThreads only after finished
4affb7d docs(m51): product integrity and knowledge quality report, evidence, index row
dbf8d50 test: bound the M50 Analysis child's stderr and kill it on timeout
63e8043 test: pin four M49/M50 contracts that the M51 code reached through other paths (mutation re-run)
46bc7bc test(m51): close three mutation gaps (worker engine, generation guard, Persian ignore-rules)
e34382e docs(m51): held-out final run at frozen 52adc99 (aggregates only), dev and M50 regression evidence
ad0b4d7 test(m51): bound the Analysis UI child's stderr; runaway output fails fast instead of exhausting RAM
```

No force-push, history rewrite, merge, tag, signing, release build or branch-protection change was made. Work stayed on `arena/72010272-drill-master` only.
