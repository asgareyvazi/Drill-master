# M52 — Product completion, engineering capability expansion, open-source integration

Status words: PASS / FAIL / PARTIAL / BLOCKED / NOT RUN. Release state: **UNSIGNED, NOT RELEASE-APPROVED**. No tag, no
release, no installer or EXE was built by this mission (the Windows CI gate builds its own bundle as before). All data in
tests, benchmarks and screenshots is synthetic. "Offscreen" means Qt `QT_QPA_PLATFORM=offscreen` on Linux; it is not
Windows desktop testing.

## 1. Identity, SHAs and CI

| Item | Value |
|---|---|
| Repository / branch | `asgareyvazi/Drill-master` / `arena/72010272-drill-master` |
| Baseline (M51 report, CI green) | `4affb7d5f0bd5134d809cabfb729733b15a668fa` (code `dbf8d506bfd40ae97b1d366d8649c380449453dc`) |
| Final code tip | `36a847a753b86e946a57e5dc720986eb0a10638d` |
| CI on the final code tip | **PASS** — Source release gate [41213500302](https://github.com/asgareyvazi/Drill-master/actions/runs/41213500302) (jobs source 3.11 / 3.12 / 3.13 success, 15:09:36–15:33:23 UTC) and Windows release validation [41213500374](https://github.com/asgareyvazi/Drill-master/actions/runs/41213500374) (job windows-release success, 15:09:38–15:42:02 UTC; Windows tests 1790/1794, 4 skipped; M51 lifecycle PASS; M52 stress PASS), 2026-10-31, `head_sha` equal to the full code SHA |
| Report commit | the commit that adds this file (its CI is reported in the final hand-over, not here: a file cannot name its own SHA) |

M52 commits (oldest first): `ef3a291` KA scope worker + QThread release · `404e175` sentence support · `3905cb7` Analysis
staged payloads + GC · `2e37f6c` trajectory comparison · `77d0ab4` balanced plug · `eac9063` DDR manual edit · `0f28418`
mutants · `906fde5` register · `c317dce` PDF report split · `f8ca619` Windows stress harness + M52 tests on Windows ·
`410b74c` NPT tint / disabled-confirm fix · `a439fe3` screenshot script · `396b57d` mutants (split, tint) · `6ec1603` fixes for the CI failure on `396b57d` (§20) and re-anchored / added mutants (§21) · `36a847a` harness:
breadcrumb after a progress dot, per-repetition annotations (§8).

## 2. Summary

* **Analysis GUI stalls (2.1): PASS on Linux offscreen.** Chart preparation, thinning and rendering moved to the snapshot
  worker as immutable payloads; the GUI thread applies one view per event-loop turn. Max GUI gap P95 ≤ 43.3 ms and
  max ≤ 56.7 ms at 1k–64k rows (targets 50 / 100 ms), golden parity kept. Windows timing NOT RUN (no Windows desktop).
* **KA scope lists (2.2): PASS.** Read on a worker with its own read-only connection; error ≠ empty; late results dropped.
* **N16/N19 sentence support (2.3): PASS** on the regression sets (no held-out claim: the M51 held-out set is spent).
* **M50 survivors (2.4): PASS** — both killed by a new test; a third M50 mutant that the 2.3 change left unobserved is
  killed by another new test (§7).
* **Windows native crash (2.5): PARTIAL.** A real native-abort mechanism (QThread destroyed while running) was reproduced
  6/6 on the baseline and fixed; a fresh-process stress harness with crash evidence now runs in the Windows gate. The
  intermittent 3D/Analysis crash itself was not reproduced, so no root-cause claim is made.
* **Engineering:** plan-vs-actual and offset-well **trajectory comparison** (SCREENING, NOT APPROVED) and a **balanced
  cement plug** calculator (SCREENING), both with saved, versioned, never-overwritten records.
* **DDR:** time-log reorder, a fixed Remove Row defect, report navigation, a fixed NPT-tint style defect (manual side);
  **multi-report PDF split** before review with blocked mixed import (import side).
* **Open source:** all 50 repositories reviewed in isolation and registered; two method re-implementations, no code
  copied, no new dependency.

## 3. Starting audit (read-only, before any edit)

* Sandbox reset found: shallow `.git` at `4336ea3`. Recovered non-destructively (`fetch --unshallow`, temporary-index
  comparison against `4affb7d` = 0 differences, compare-and-swap `update-ref`). HEAD = remote = `4affb7d`, clean, no stash,
  one worktree. `drill-Master` remote tip untouched; `main` does not exist on the remote.
* Environment rebuilt from `requirements-lock.txt` + CI pins; Qt system libraries built from pinned upstream tags outside
  the repository. `pytest --co`: 3766 tests in 266 files (= M51 final).
* Open items mapped source → behaviour → cause → reproduction → coverage → fix → acceptance (10 rows): Analysis paint on
  the GUI thread; KA pickers reading SQL on the GUI thread with read errors shown as empty lists; sentence relevance from
  file-name context; the two M50 survivors; the Windows lifecycle crash; anti-collision comparing two wells at the same MD;
  no comparison/clearance UI; no balanced plug / NPT cost; PDF fallback bound to one form's labels with no report split;
  no time-log reorder or report navigation.

## 4. Performance — Analysis (2.1)

Profile at 16k rows (M51 code): NPT 75.7 ms, milestones 27.9, analytics 20.6, time-depth 11.4 ms medians on the GUI thread.

Design (`core/analysis_payloads.py`, `tabs/analysis_views.py`, `tabs/w12_Analysis.py`):
* the snapshot worker builds immutable payloads (formatted rows, min-max thinned series, Agg-rendered pie and milestone
  images) cached by revision / scope / settings; no QObject crosses threads;
* min-max thinning is **visual only**: spikes and NPT points are kept; KPIs, exports and the database use the full data;
* the GUI thread applies one view per event-loop turn with generation and cancel checks (`RowsTableView` model view,
  `ChartImageView`); a scope change cancels a paint in progress;
* GC: bounded hold while the snapshot worker runs, a boundary collection when the hold is taken, the start-up heap frozen
  (`core/qt_gc.py`, `app.py`); export/worker engines cached per file with per-view `OptionEngine` (statements compiled once).

Measured with the real flow on a temporary file SQLite (no mocking), Linux offscreen, 2 CPUs, timer 5 ms, 20 cycles per
scenario. BEFORE = M51 code measured by `tools/quality/analysis_responsiveness_m51.py` (no warm-up field recorded); AFTER =
`tools/quality/analysis_responsiveness_m52.py`, 3 warm-up cycles. Evidence: `m52-evidence/analysis_before_m51code.json`,
`m52-evidence/analysis_after_m52.json`.

Max GUI gap, ms (median / P95 / max):

| Rows | BEFORE (M51 code) | AFTER refresh | AFTER changed data |
|---|---|---|---|
| 1,024 | 115.7 / 133.3 / 135.2 | 30.4 / 37.0 / 38.4 | 32.2 / 36.2 / 46.7 |
| 4,096 | 125.3 / 153.6 / 170.0 | 33.3 / 43.3 / 56.7 | 29.3 / 33.6 / 36.5 |
| 16,384 | 185.2 / 261.1 / 319.7 | 29.8 / 38.7 / 42.6 | 30.2 / 41.1 / 41.2 |
| 65,536 | 390.1 / 642.6 / 1374.0 | 30.0 / 35.8 / 38.5 | 34.0 / 42.7 / 46.3 |

AFTER detail (refresh, medians): total wall 365.9 / 575.5 / 1326.5 / 4262.5 ms (background time, the GUI stays
responsive; BEFORE 355.9 / 557.9 / 1515.3 / 5440.8 ms); prep 73.5 / 76.4 / 86.6 / 123.0 ms (worker); largest single GUI
stage 20.3 / 21.7 / 21.5 / 20.4 ms; render 25.8 / 29.1 / 25.1 / 24.8 ms; GUI-thread GC max ≤ 8.0 ms; payloads built on
the GUI thread during measured cycles: **0** at every size; painted values equal to the synchronous path: **True** at
every size; peak RSS 276.4 / 296.3 / 350.8 / 563.8 MB. The old synchronous path measured in the same run blocks the GUI
for 265.8 / 502.1 / 1335.1 / 4702.4 ms (median).

Iterations that did not work are recorded in §19 (memory/GC). Not measured: Windows desktop timing; slower or loaded CPUs.

## 5. KA scope lists off the GUI thread (2.2)

`ScopeChoicesWorker` reads the well / report / document pickers on its own read-only connection (file DB) and returns
plain dicts; a token guard drops late results; a read error shows "could not be read — Retry", distinct from "no wells";
asking is refused while the list is loading or unreadable; a library refresh keeps the chosen well. Linkage semantics
unchanged. Regression test fails if SQL runs on the GUI thread (`tests/test_m52_scope_choices.py`, 9 collected).

## 6. KA quality — sentence-level support (2.3)

Cause: a well code stated only in the file name (document identity) made an unrelated sentence on a relevant page
quotable. Rule now: identity makes a passage *eligible*, never a sentence an *answer*. A quoted sentence must state a
topical question term itself (own words, or the noun of an asked quantity shown by its unit; the page heading only when
no sentence does, and only for a sentence with a value), must not name another entity of the asked family, and a sentence
stating only part of what the best one states is not quoted beside it. Identity-only matches no longer fall back to the
first sentence and get an honest note. `ANSWER_VERSION` 3. Document, page, passage, sentence, numeric, well and freshness
checks stay separate; wrong-well and partial constraints were not weakened.

Adversarial tests (`tests/test_m52_sentence_support.py`, 17 collected): file-name-only identity, unrelated sentence on a relevant
page, similar well IDs, same-page conflict, partial overlap, a sentence about another casing size competing for a quote slot (§7). Regression sets: M49+M50 126/126 (R@5 1.0, MRR 0.9895), M51
dev 57/57; quoted sentences 197 → 175 (22 off-topic quotes removed, none added). Lexical retrieval only; nothing here is a
semantic or model-quality claim. Remaining weakness: N14 still quotes the table-of-contents sentence and N30 a partially
related sentence (§23).

## 7. M50 survivors (2.4)

`R-file-name-context-dropped` and `R-absent-ignores-context` reproduced with `--only`, then **killed** by the code-only
file-name identity test added with §6. Before that test existed both survived (30 passed with each mutant applied); after it, both are killed.

A third M50 mutant, `A-sentence-inherits-any-size`, **survived** the fresh M50 run on `396b57d` (it was killed in M51). Cause:
the new own-support gate of §6 repeats the size rule, so the M50 gold question no longer observes the ranking stage the
mutant changes. It is **not** equivalent: with a second page in the corpus the mutated code quotes "The LOT at the 13-3/8 in
shoe gave 1.65 sg EMW." for a 9-5/8 in question, because the other-size sentence then outranks a sentence that names no
size for the second quote slot. New test `test_a_sentence_about_another_size_never_takes_a_quote_slot` (3 questions, own
synthetic corpus) pins it; like the R-* pair it is re-run in `tools/quality/mutation_m52.py` with the M52 tests and stays a
survivor of `tools/quality/mutation_m50.py`, whose test list is M50's (§21).

## 8. Windows native crash (2.5) — PARTIAL

Evidence collected:
1. **Reproduced native abort, fixed.** Result slots called `deleteLater()` on a QThread still inside `run()`; Qt aborts
   with "QThread: Destroyed while thread is still running" (Linux rc 134 = SIGABRT; on Windows an `abort()` ends the
   process natively). Reproduced 6/6 on the M51 baseline (KA status, KA semantic, MinerU batch slots) by
   `tests/m52_thread_release_child.py`; fixed in `core/async_workers.release_when_finished` (checks `isFinished`,
   idempotent) and the three slots; a scan of all `deleteLater` sites found no other QThread result-slot site.
   This is a real native-crash mechanism; whether it was *the* intermittent 3D/Analysis crash is **not proven**.
2. **ChartImageView abort fixed** (Analysis view replaced while a paint referenced it) during 2.1.
3. **Stress harness** `tools/quality/lifecycle_stress_m52.py` (stdlib only), run by a new Windows gate step after the
   unchanged M51 3-repetition step: 5 fresh interpreters over the real 3D / Analysis / worker / GC modules (M51's five plus
   the M52 analysis, thread-release, GC-schedule, worker-engine and comparison-UI modules); per repetition: classified exit
   code (NTSTATUS such as 0xC0000005 never folded into "test failure"), last test started (breadcrumb), faulthandler stack,
   `faulthandler_timeout` hang dump, processes left alive after exit (Windows Job Object, POSIX process group — recorded,
   killed, and failing the step), peak working set, and new Windows Error Reporting minidumps (LocalDumps configured by
   the step). Any crash, failure, hang, leftover or dump fails the gate. Its own tests (21 collected) cause a real native
   crash (Windows: a NULL read, 0xC0000005; POSIX: SIGSEGV), a C runtime `raise(SIGABRT)`, a leftover child and a hang in
   synthetic modules and check that each is caught; a SIMULATED banner test covers both exit-code readings on every OS.
4. **What the first Windows CI run of the harness taught (run 41205652395 on `396b57d`, FAIL).** Two harness defects, both
   fixed in `6ec1603`: (a) the synthetic modules live in `%TEMP%` on another drive than the checkout, and pytest then names
   a test `::test_ok` (no file part) — the harness now takes `rootdir`; (b) `faulthandler._sigsegv()` is a C runtime
   `raise()`: after faulthandler re-raises, the MSVC default action ends the process with **exit code 3**, the code pytest
   uses for an internal error, and the harness called it "pytest: internal error". A logged faulthandler fatal error now
   makes a repetition a native crash whatever its exit code, and code 3 is labelled as possibly a C runtime
   `abort()`/`raise()` exit. Consequence for 2.5: on Windows an exit code of 3 alone must not be read as a pytest problem.
   A third defect was found locally afterwards (fixed in `36a847a`): with `pytest -q` the next breadcrumb follows the
   previous test's progress dot on the same line, and the parser read only line starts, so a crash in a multi-test
   module would have been blamed on an earlier test (`packaging/junit_report.py` already searched the whole line). The
   real crash fixture now runs a passing test first. Since `36a847a` the step also prints one annotation per repetition
   (exit class, JUnit totals, peak memory, leftovers, dumps, last test), which the checks API exposes.
5. Results: **Windows (CI run 41213500374 on `36a847a`, GitHub-hosted Windows Server runner, Python 3.12.10): PASS.** 5 fresh interpreters over the 10 lifecycle modules, 118 tests each: every repetition exit 0 (no native crash), 0 failures / 0 errors / 0 skipped, 0 processes left running (Job Object check ran), 0 new WER minidumps (LocalDumps configured), 132.6–136.1 s per repetition, step 15:27:23–15:38:45 UTC. The earlier run on `6ec1603` (41209512075) also passed this step; the first one, on `396b57d`, never reached it (§8 item 4). **Linux offscreen (this sandbox, `36a847a`, 2 repetitions, same 10 modules): PASS** — exit 0 twice, 118 tests each, 0 failures, 0 leftovers, peak RSS 419.1 / 418.5 MB, 118.9 / 119.9 s (dumps not configured on Linux; evidence `m52-evidence/lifecycle_stress_linux_36a847a.json`). This is CI evidence on a hosted runner, not Windows desktop or field acceptance, and it did not reproduce the original intermittent crash.

Not done: a long multi-hour soak on Windows (no Windows machine; CI time-boxed at 60 min); a reproduction of the original
crash. 2.5 stays **PARTIAL** until a crash is captured with its dump and explained.

## 9. Engineering — trajectory comparison (Groups A / Part 4)

`core/trajectory_compare.py` + `tabs/trajectory_compare_panel.py` ("Compare / clearance" tab of the trajectory viewer):
* plan vs actual: deviation as high / right / along in the plan normal plane, on exact minimum-curvature arcs;
* offset well: continuous closest approach — both trajectories as exact minimum-curvature arcs, every sampled local minimum
  refined by golden-section search (no nearest-station heuristic); separation on one vertical datum;
* well-to-well needs both wellheads, both datums and a user-confirmed common projected CRS in metres, otherwise
  **NOT ASSESSED** with every reason; ~180° doglegs refused;
* plan import CSV / TXT / XLSX with an explicit m / ft unit;
* computed on a worker with a stale-result guard; results saved as **new** `TrajectoryCalculation` records (never updated);
  CSV export headed with the label;
* label everywhere: `SCREENING - centre-to-centre, no ISCWSA uncertainty, NOT APPROVED`; `METHOD_VERSION`
  "M52 centre-to-centre screening v1".

References (independent of the implementation): analytic arcs, parallel / crossing lines, a U-path whose true minimum
(45 m at MD 200+50π) lies between stations (kills the sample-only mutant). Tests: 20 engine + 9 UI (collected). `AntiCollisionEngine`
(same-MD comparison) is untouched and documented as a limitation; no ISCWSA claim.

## 10. Engineering — balanced cement plug (Group D)

`CementEngine.balanced_plug` (SCREENING, `BALANCED_PLUG_VERSION` "M52 balanced plug v1"): equal column heights inside and
outside the pipe; spacer behind = ahead × Cp/Ca; displacement with optional under-displacement (warning); plug top after
pulling the pipe (gauge hole); sacks rounded up and only with a yield. Capacities π/4·(D/12)²/5.6146 bbl/ft. Invalid
geometry, negative volumes and non-positive displacement are refused with the reason; missing inputs are missing, never 0.
W13 "Balanced Plug" tab; each run saved as a new cement-history record that reconstructs and verifies from its snapshot.
Method credited to cement-calc (MIT); independent implementation with hand references (8.75 in hole, 3.5 / 2.764 in pipe,
500 ft plug at 9000 ft, 20 % excess, 10 bbl spacer → 44.626 bbl slurry, 237 sacks at 1.06 ft³/sk, displacement 60.867 bbl).
Tests: 16 collected (hand references, balance identities, invalid/missing inputs, persistence, W13 tab in a subprocess). NPT cost: NOT implemented (§23). Well-control calculators: not added (owner item).

## 11. DDR — manual entry and editing (Group B / Part 4)

`tabs/w2_Daily_Report.py`:
* Move Up / Move Down on both time-log tables: row *states* are swapped (times including raw invalid text, phase, codes,
  status, NPT, contractor, description, combo editability); each row keeps its own widgets and handlers; invalid times stay
  NOT ASSESSED;
* **defect fixed — Remove Row:** rows below a removed row kept handlers bound to their old index, so editing a time
  recalculated another row; states now shift up and the last row is removed;
* **defect fixed — combo editability** was not restored on a swap;
* **defect fixed — load order:** time logs loaded without ORDER BY; now id order, which is the saved on-screen order;
* Previous / Next report of the well (date, number, id) with an unsaved-edit confirmation; a list read error is reported,
  not shown as empty;
* **defect fixed — NPT tint (pre-existing at `dbf8d50`, found from the M52 screenshot):** ticking NPT replaced every cell
  stylesheet and unticking cleared it, so descriptions lost their font size / border / transparency and an invalid time
  lost its warning colour. The tint is now layered on each widget's own style; the invalid-time warning outranks it.

Tests: 12 collected (`tests/test_m52_ddr_manual_edit.py`). Existing CRUD for NPT, parameters, mud, bit/BHA/casing/survey is unchanged
(no new forms; §23).

## 12. DDR — PDF import and review: multi-report split (Group B)

`core/ddr_pdf_split.py` (`SPLIT_VERSION` "M52 DDR PDF report split v1") and `dialogs/excel_import_dialog.py`:
* each page classified text / no text layer (< 40 non-space characters; scanned pages are flagged, **OCR is not run**);
* header fields from the first 25 lines with generic labels (report number, report date, well); dates in ISO, D/M/Y, D-Mon-Y
  and Mon D, Y; day/month order is **never guessed** (04/03/2026 is "ambiguous", kept as written);
* grouping: a header page that agrees on every shared field continues the report (repeated headers); headerless pages are
  continuation pages; pages before the first header belong to no report;
* explained duplicates (same number + date), conflicts (one number, two dates), possible duplicates (same date, no number);
  a different well name is a suggestion only; confidence high / medium / low with reasons;
* the split is computed before extraction for every PDF in a batch; the preview shows a "PDF report split" table (pages,
  number, date, well, confidence, warnings); **a multi-report PDF cannot be confirmed as one report** (button disabled and
  `_confirm` guarded); "Save one PDF per report…" writes `<stem>_report-N_p<a-b>.pdf` files without overwriting; nothing is
  saved to the database by the split; a PDF that fails extraction still reports that it holds several reports; an
  unreadable PDF is an explicit NOT ASSESSED state, never an empty split.

Tests (`tests/test_m52_ddr_pdf_split.py`, 26 collected): text, scanned, fully scanned, multi-page with repeated
header, multi-report, continuation, missing headers / leading pages, duplicates, conflict, ambiguous / impossible dates,
wrong well, missing well, damaged PDF, no-overwrite writing, preview table and block, batch loop hand-over, failed-import
message. **Status: PARTIAL for the full "profile-based ingestion workspace"** — profiles, region selection, table
continuation across pages, field correction and confirmed-only persistence beyond the existing review were not built.
Found and not fixed (pre-existing): the PDF-native fallback requires ruled tables and reads a table's header row as data,
so text-only DDR PDFs fail at "open" and some ruled ones at "meaningful data" (§23).

## 13. Data contracts and provenance (Part 5)

| Calculation | Units | CRS / datum | Sign / convention | Version | Validity / errors | Record |
|---|---|---|---|---|---|---|
| Trajectory comparison | m (plan in m or ft, explicit) | user-confirmed common projected CRS; one vertical datum (RTE-MSL) | high/right/along in the plan normal plane | `METHOD_VERSION` | NOT ASSESSED with reasons; ~180° refused | new `TrajectoryCalculation` per save |
| Balanced plug | in, ft, bbl, ft³/sk | n/a (gauge hole) | volumes ≥ 0 | `BALANCED_PLUG_VERSION` | refused with reason; missing ≠ 0 | new cement-history record, verifiable |
| PDF split | pages 1-based | n/a | n/a | `SPLIT_VERSION` | `PdfSplitError` → NOT ASSESSED | not persisted (review aid) |
| Analysis payloads | as source | n/a | thinning visual only | `PAYLOAD_VERSION` 1 | stale payload dropped by generation | none (display) |
| KA answer | n/a | n/a | n/a | `ANSWER_VERSION` 3 | separate check dimensions | existing |

No old result is overwritten by any M52 path.

## 14. Screenshots

Real widgets, synthetic data, offscreen Linux (`tools/screenshots/capture_m52.py`, one fresh interpreter per image;
emoji glyphs render as boxes because the offscreen font set has no emoji font). Pinned in `tools/privacy/policy.json`.

* `m52-screenshots/m52_trajectory_offset_screening.png` — offset well, CRS confirmed: closest approach 10.0 m, SCREENING label.
* `m52-screenshots/m52_trajectory_not_assessed_crs.png` — CRS not confirmed: NOT ASSESSED and the reason; save disabled.
* `m52-screenshots/m52_balanced_plug_screening.png` — W13 balanced plug result with formula, assumptions and source.
* `m52-screenshots/m52_ddr_pdf_split_preview.png` — synthetic 5-page PDF, 3 reports; ambiguous date not read; Confirm Import blocked.
* `m52-screenshots/m52_ddr_time_log_reorder.png` — NPT record moved up; styles intact.

Two defects were found from these images and fixed before capture: the blocked Confirm button still looked enabled
(stylesheet overrode the disabled look) and the NPT tint defect of §11.

## 15. Open-source register (Part 3 / 7)

`docs/engineering/OPEN_SOURCE_ADOPTION_REGISTER.md`: all 50 URLs, each downloaded as a tarball at a recorded SHA into an
isolated directory outside the repository and reviewed read-only (licence file, dependencies, tests, Windows/offline
support, data redistributability, numerics). No upstream code executed or installed.

| Classification | Count |
|---|---|
| ADOPT | 0 |
| ADAPT | 0 |
| REUSE ALGORITHM | 2 (welleng → trajectory comparison ideas; cement-calc → balanced plug) |
| INSPIRE ONLY | 39 |
| OWNER REVIEW REQUIRED | 2 (pwptemp, torque_drag — LGPL-3.0) |
| REJECT | 7 |

Correction made while writing this report: the register first said PyMuPDF "remains absent"; it is a pre-existing locked
dependency (1.24.14, AGPL) — fixed in the register.

## 16. Licences and notices

No upstream code copied. `THIRD_PARTY_NOTICES.md` credits the cement-calc (MIT) formula set and welleng (Apache-2.0)
method ideas. GPL (ejbo2001), CC BY-NC (nmamzada), LGPL (pro-well-plan) and no-licence repositories: nothing taken.
DDR_UTAH_FORGE (MIT): ideas only, no FORGE-specific rules. welleng: no cloud API, no ISCWSA model adopted.

## 17. Dependencies

M52 adds **no** runtime or development dependency; `pyproject.toml` and `requirements-lock.txt` (the dependency inventory)
are unchanged. The stress harness and screenshot script are stdlib + existing packages. PyMuPDF (already locked) is used by
the PDF split as by the existing PDF import. A YAML parser was installed only into a temporary directory outside the
environment to validate the workflow syntax.

## 18. Migrations and data safety

No schema change (`core/database.py` untouched); old databases open unchanged. No money or rounding change (2.675 rule
untouched). Benchmarks, tests and screenshots use temporary synthetic databases only. The PDF split writes new files only,
never overwriting, and never writes to the database.

## 19. Memory and GC

* Garbage per 4 Analysis refreshes at 1k rows: 121,631 → 44,080 objects; GUI-thread gen0 collections 80 → 4–7 ms, gen1
  98.5 → 16.1 ms; GUI GC max P95 ≤ 9.9 ms in the final benchmark.
* About 294 SQLAlchemy subquery-proxy `Column` objects remain as garbage per refresh (not removed).
* Peak RSS of the benchmark process 276.4–563.8 MB (1k–64k rows).
* Dead ends recorded: frequent gen0 collections, unbounded hold deferral, a shared compiled cache, a plain shared engine,
  explicit gen1/gen2 collections without the heap freeze (each made gaps worse or moved them).
* Windows peak working set per repetition is recorded by the stress harness (Windows CI `36a847a`: peak working set 220.3, 221.0, 220.4, 221.0, 220.6 MB for repetitions 1–5 — flat, no growth across repetitions).

## 20. Tests and gates

Full suite (Linux offscreen, run in two halves): **PASS** on `36a847a` (2026-10-31 15:59–16:17 UTC, 278 test files split into two halves of 139, lists regenerated for this run): half 1 2177 passed, 2 skipped; half 2 1766 passed, 2 skipped — **3943 passed, 4 skipped, 0 failed**. The 4 skips are the expected ones: `test_ddr_acceptance.py:33` ×2 (real DDR files are opt-in), `test_mineru_real_integration.py:26` (no MinerU installation), `test_packaging_smoke.py:218` (no Windows bundle on Linux). Count check: CI on `396b57d` collected 3939; +8 tests since (sentence support +3, lifecycle stress +5) = 3947 = 3943 + 4. Windows CI on `36a847a` ran its regression selection: 1790 / 1794 (4 skipped).

M52 adds 180 collected tests in 12 files (analysis payloads 28, balanced plug 16, DDR manual edit 12, PDF split 26, GC schedule 10, lifecycle stress 21, scope choices 9, sentence support 17, thread release 7, trajectory comparison 20 + UI 9, worker engine 5).

**CI failure on `396b57d` (FAIL, fixed in `6ec1603`).** Source gate 41205652442 (3.11/3.12/3.13): 3934 passed, 4 skipped,
1 failed — `test_model_registry::test_every_live_registry_with_mappers_is_the_authoritative_one`, `ReferenceError: weakly-
referenced object no longer exists`. Reproduced locally (M52 test files + that test), bisected to
`test_m52_ddr_pdf_split.py`, and to its one test that drives the real import pipeline. Cause: PyMuPDF 1.24.14 keeps the
last table-finder `TextPage` in the module global `pymupdf.table.TEXTPAGE`; its `parent` is a weak proxy to a page whose
document is closed. The registry test scanned `gc.get_objects()` with `isinstance()`, which reads `__class__` and raises
on a dead proxy. **Pre-existing**: on the M51 code (`dbf8d50`, extracted with `git archive`), the M51
`extract_tables()` leaves the same dead proxy (it survives `gc.collect()`) and the same scan raises; it never surfaced
because the pre-existing PDF-table tests sort after `test_model_registry`. Fix: the scan uses `type()` (a proxy is never a
registry; a stray second registry is still found — checked with a dead proxy in the heap). PyMuPDF's private global is
not touched. Windows run 41205652395 failed on the harness defects of §8.

New / changed contracts and why counts changed: M51's source test moved to the staged `_paint_steps`; the 3D viewer's tab
list now has 4 tabs (comparison); the M52 analysis child has 12 scenarios; `test_m52_gc_schedule` order dependence fixed;
freeze-garbage, reorder/navigation tests added; mutation snippets re-anchored after edits.

Gates on the final code: ruff on changed files — no new findings (pre-existing: activity_mapper W293, w13 14, w2 4); lint
debt 727 = ceiling 727; exception scan rc 0 (one intentional handler annotated `# silent-ok`); privacy check 0 findings;
coverage gate runs in CI (floor 45.50, unchanged). Windows CI now runs all 12 M52 test modules
(`tests/test_windows_release_gate_contract.py` requires them).

## 21. Mutation

Fresh runs on the final code (`36a847a753b86e946a57e5dc720986eb0a10638d`, 2026-10-31 15:09–15:59 UTC, Linux offscreen, one tool at a time), no reused results:

| Tool | Mutants | Killed | Survived (non-equivalent) | Declared equivalent | Invalid | Seconds | Evidence |
|---|---|---|---|---|---|---|---|
| `mutation_m52.py` | 70 | 69 | 0 | 1 | 0 | 468 | `m52-evidence/mutation_m52_36a847a.json` |
| `mutation_m51.py` | 29 | 29 | 0 | 0 | 0 | 377 | `m52-evidence/mutation_m51_36a847a.json` |
| `mutation_m50.py` | 55 | 52 | 3 (see below) | 0 | 0 | 768 | `m52-evidence/mutation_m50_36a847a.json` |
| `mutation_m49.py` | 38 | 38 | 0 | 0 | 0 | 154 | `m52-evidence/mutation_m49_36a847a.json` |
| `mutation_m48.py` | 44 | 44 | 0 | 0 | 0 | 1212 | `m52-evidence/mutation_m48_36a847a.json` |

The three `mutation_m50.py` survivors are `R-file-name-context-dropped`, `R-absent-ignores-context` and
`A-sentence-inherits-any-size`. That tool runs M50's own test list; all three are re-run in `mutation_m52.py` with the
M52 tests and are **killed** there (§7). Earlier runs, kept as history and not counted: on `396b57d` M50 had 3 survivors and
2 INVALID, M48 1 INVALID (re-anchored since); on `6ec1603` M52 68/67+1, M51 29/29, M50 52+3, M49 38/38, M48 44/44.

M52 mutants cover: Analysis staged paint and scope cancellation, payload thinning, GC hold/boundary, trajectory arc /
closest approach / CRS gate, plug formulae and persistence, DDR reorder / remove / navigation / load order, NPT tint, PDF
split rules, preview block, batch hand-over and failure message, and the stress harness (rootdir, logged fatal error, hang
dump not promoted, orphans fail, signal is native, breadcrumb after a progress dot, annotation escaping); the M50 mutants `R-file-name-context-dropped`,
`R-absent-ignores-context` and `A-sentence-inherits-any-size` are re-run with the M52 tests (§7).

Re-anchored, not removed (the M52 staged paint moved the code; same statements, same mutation): M48 `B-forced-backend`
(w12 no longer imports Matplotlib at module level — the inserted backend switch now goes into its import block), M50
`N-verify-skipped` and `N-error-shown-as-updated` (moved into `_snapshot_painted`). On `396b57d` these three were INVALID
(snippet not found), which the engine reports instead of counting them. Declared equivalents with reasons:
`W12-staged-paint-ignores-scope` (all six scope bump sites cancel synchronously; pinned by the scenario
`section_change_mid_paint_cancels_the_old_paint`); an `order_by` removal was **not** added as a mutant because SQLite returns
rowid order without it (equivalent under SQLite).

## 22. Git and CI

State before the report commit (code tip `36a847a`, pushed, `git ls-remote` equal): branch `arena/72010272-drill-master`, 0 ahead / 0 behind its upstream, no stash, one worktree, `git diff --check` clean; the uncommitted files were exactly this report, its evidence and screenshot folders, the register, the README index row and the five screenshot pins in `tools/privacy/policy.json`. The full `status --porcelain=v2 --branch`, `log`, `branch -vv`, `worktree list`, `stash list` and `ls-remote` after the report commit are quoted in the final hand-over.

## 23. Limitations, PARTIAL, BLOCKED, NOT RUN

* 2.5 Windows native crash: **PARTIAL** (§8).
* DDR profile/region ingestion workspace: **PARTIAL** (§12); OCR NOT RUN (no local OCR engine used; scanned pages flagged).
* Pre-existing PDF-native fallback limits (needs ruled tables; header row read as data): found, NOT fixed.
* Import pipeline (including the PDF parse and split) runs on the GUI thread, as the existing architecture does.
* `AntiCollisionEngine` (same-MD comparison) untouched; comparison is centre-to-centre only; no ISCWSA uncertainty.
* NPT cost: NOT implemented. Well-control calculators: not added.
* KA: N14 quotes a table-of-contents sentence; N30 a partially related sentence. Semantic retrieval / local model: NOT RUN
  (no model installed; none downloaded).
* Group E (thermal / stability) and Group F ML: NOT RUN (no defensible data; nothing labelled as an estimate was added).
* Benchmarks: Linux offscreen, 2 CPUs; Windows desktop timing NOT RUN.
* ~294 garbage `Column` objects per Analysis refresh remain.
* Windows CI is GitHub-hosted runner execution, not Windows desktop or field acceptance.
* DDR time log: a row whose invalid time is corrected loses its NPT tint until NPT is toggled again (pre-existing, seen
  while fixing the tint style defect; not changed). A "24:00" end time is displayed as such on purpose (`is_2400`).
* Tests: `tests/conftest.py` points `DATA_DIR` (and the database / backup paths) at a temporary directory for every run,
  so no test can touch a real data folder; ad-hoc scripts must set the same variables.
* PyMuPDF keeps its last table-finder `TextPage` alive in a module global after extraction (§20); harmless to the app,
  but any heap scan must not use `isinstance()` on arbitrary objects.

## 24. Owner decisions

Ollama / local model and embedding models; branch protection; any GPL / LGPL / CC-NC code (pwptemp, torque_drag,
ejbo2001, nmamzada); welleng ISCWSA error models (would need scipy / pyproj and reference validation); PyMuPDF AGPL licence
(pre-existing) and OCR engines; well-control (kill-sheet) calculators; release, tag and signing; Windows desktop and field
acceptance.

## 25. Acceptance matrix (Definition of Done)

| Requirement | Status | Evidence |
|---|---|---|
| Part 2.1 Analysis stalls | PASS (Linux offscreen) | §4 |
| Part 2.2 KA worker | PASS | §5 |
| Part 2.3 sentence support | PASS (regression sets) | §6 |
| Part 2.4 survivors | PASS | §7 |
| Part 2.5 Windows crash root cause | PARTIAL | §8 |
| Register of all 50 URLs | PASS | §15 |
| ≥ 1 substantial trajectory / engineering capability | PASS (comparison + plug) | §9, §10 |
| DDR entry/edit + import/review improvement | PASS (edit, split); workspace PARTIAL | §11, §12 |
| Referenced calculators | PASS (plug; hand references) | §10 |
| Offline, no new dependency | PASS | §17 |
| M44–M51 intact | PASS — M48–M51 mutation suites fully killed on the final code (M50's three survivors killed by M52 tests), M51 lifecycle and full suite pass | §20, §21 |
| Full tests (same 4 skips) | PASS — 3943 passed, same 4 skips, 0 failed (Linux offscreen); CI Source 3.11/3.12/3.13 and Windows green | §20 |
| Mutation with survivors explained | PASS — 0 unexplained survivors; 1 declared equivalent with reasoning; 3 re-anchored, none removed | §21 |
| CI green on code SHA and report SHA | PASS on the code SHA `36a847a` (41213500302, 41213500374); the report SHA's runs are given in the hand-over (a file cannot name its own commit) | §1, §22 |
| Clean workspace, local = remote | PASS at the code tip; after the report commit see the hand-over | §22 |
| No release / EXE / tag / model | PASS | — |
