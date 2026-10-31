# M51 — Product integrity closure: off-thread Analysis, fresh knowledge corpus, false-answer fixes, cross-lingual evaluation, query refinement, verifier, GC watchdog

Branch `arena/72010272-drill-master`, base `2dab8b12f2fb1a447cf3026eddf08185298ecda7`
(the M50 report tip; M50 code tip `e48495c`). Status values: PASS / FAIL /
PARTIAL / BLOCKED / NOT RUN. All data is synthetic (`tests/m48_synthetic.py`,
`tests/m49_knowledge_fixtures.py`, `tests/m50_knowledge_fixtures.py`,
`tests/m51_knowledge_fixtures.py`: wells `SYN-*`, documents `SYN-KG-07`,
`SYN-KH-08`, `SYN-KJ-09`, `SYN-KM-10` …). No real DDR, real document, real well
or real money value was opened or reproduced. **No language model or embedding
model was installed, downloaded or run** (installing Ollama or pulling a model
needs explicit owner authorisation): semantic retrieval and real generation are
**NOT RUN**, and every retrieval improvement below is lexical (glossary,
normalisation, weighting, hard constraints) — none of it is semantic. No EXE,
installer or release bundle was built by this mission (the Windows CI runner
builds its own). The application stays **UNSIGNED**. Nothing here is release
approval, Windows desktop acceptance, field validation, semantic qualification
or a model-quality claim.

## A. Summary

| § | Item | Status | Evidence |
|---|---|---|---|
| 2 | Start audit (remote = local `2dab8b1`, clean, 0/0, 3663 tests collected) | PASS | J.1 |
| 3 | Every DB read, aggregation and non-Qt calculation of an Analysis cycle on a worker with its own read-only connection; plain-Python results; GUI only paints | PASS | B |
| 3 | Event-loop responsiveness of the whole cycle | **PARTIAL**: largest GUI gap 103 / 113 / 157 ms median at 1k / 4k / 16k rows (synchronous: 236 / 443 / 1301 ms); the remaining gap is Qt painting (NPT chart 76 ms at 16k) | B.3 |
| 4 | Corpus signature and snapshot read on the worker; same-length edit, review status, delete+reimport with reused ids, link changes, cancel, interrupted rebuild | PASS | C |
| 5 | Forensic baseline before edits; general fixes (identity hard constraint, partial-overlap veto, FA/AR injection patterns) | PASS | D |
| 6 | New EN+FA corpus, 114 labelled questions (57 dev / 57 held-out) committed before tuning; held-out run once on the unchanged baseline and once on the frozen SHA | PASS | E |
| 6 | Held-out: 0 scope / fabricated / unapproved / unsupported-number violations; 0 false answers on unanswerable; cross-lingual improved vs. frozen baseline | PASS (51/57 all-checks; 6 held-out questions still fail a check, not inspected) | E.3 |
| 6 | Latency of the assistant | **regressed**: held-out median 9.4 → 41.1 ms (same-machine dev 10.0 → 34.1 ms) | E.3 |
| 7 | Query refinement UI (scope, found / missing terms, related sources, semantic unavailable, editable suggested terms, disabled without suggestions, scope preserved, RTL/LTR) | PASS (Qt offscreen) | F |
| 8 | Verifier: other well, edited after retrieval, deleted / reimported reused id, escaping and bidi (plus the M50 cases); dimensions separate, never "semantic" | PASS (synthetic adversarial tests) | G |
| 9 | GC audit, watchdog (detects worker collections, heals re-enabled automatic GC), mixed soak | PASS (Linux offscreen, not Windows desktop) | H |
| 9 | Repeated real 3D/Analysis lifecycle step in the Windows gate (3 isolated repetitions, original order, no skips) | **PARTIAL**: green in 4/4 completed Windows runs (12/12 repetitions); determinism and closure of the M50 intermittent native crash are not proven | H.3 |
| 10 | Mutation M51 (29 mutants) | PASS: 29/29 killed on `46bc7bc` (first run 26/29: three test gaps found and closed, I.2) | I.2 |
| 10 | Mutation M48 / M49 / M50 re-runs | **PARTIAL**: M48 44/44, M49 38/38 (`63e8043`), M50 53/55 (`dbf8d50`) — the first re-runs found 6 old mutants no longer killed (M51 reached their contracts through other paths); 4 closed by new tests, 2 survive with analysis (not declared equivalent); one OOM "kill" replaced by an explicit failure after a harness fix | I.2 |
| 10 | Full suite (same 4 skips only) | PASS: 3762 passed, 4 skipped, 0 failed of 3766 collected on `63e8043`; the one test file changed afterwards (`dbf8d50`) re-run: 27 passed | I.1 |
| 12 | CI on the exact code tip `dbf8d50` | PASS: Source 41181840781 and Windows 41181840890 success; coverage 58.83% (floor 45.50%) | J.2 |

### A.2 Acceptance matrix (§14)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | No DB read, aggregation or non-Qt calculation of an Analysis cycle on the GUI thread (file DB), whole pipeline not only the digest | PASS (GUI-thread SQL counted in every selection path; AN mutants) | B.1, B.2 |
| 2 | Worker owns its session; only immutable plain-Python results cross threads | PASS (asserted recursively) | B.1 |
| 3 | Canonical service, row/wellbore scope, KPI semantics, M48/M49 states, Refresh, auto timer, in-memory DB, cancel/dispose preserved | PASS (golden parity; M48/M49/M50 suites) | B.2, B.3, I |
| 4 | Read error explicit, never cached, never "No data", retryable | PASS | B.2 |
| 5 | Concurrent edit → bounded restart / Updating | PASS | B.1 stage 7, B.2 |
| 6 | Benchmark 1k/4k/16k, real flow, temp file SQLite, median/P95/max/gap per stage, golden KPIs unchanged | PASS (measured) | B.3 |
| 7 | Event loop responsive during the whole cycle | **PARTIAL** (103–157 ms median gap left: Qt painting; no latency target claimed) | B.3 |
| 8 | Corpus signature and snapshot on a worker; loading; read error ≠ no documents; coherent snapshot; no redundant read | PASS | C |
| 9 | Same-length edit, review status, delete+reimport reused ids, link changes, cancel, interrupted rebuild | PASS | C |
| 10 | Forensic baseline before edits | PASS | D |
| 11 | General false-answer fixes (identity hard constraint, conflict / partial overlap refused, no id special cases); refusal rate measured | PASS | D, E.3 |
| 12 | FA/AR injection detected by general patterns; flagged text visible, never quoted; procedures not flagged | PASS | D, E.3 |
| 13 | ≥100 new labelled EN+FA questions, dev / held-out, committed before tuning; baseline on both; held-out aggregates only; frozen SHA; held-out run once | PASS (114; frozen `52adc99`; held-out spent) | E.1 |
| 14 | Held-out: 0 scope / fabricated / unapproved / unsupported-number violations; 0 false answers on unanswerable; cross-lingual improved vs. frozen baseline | PASS | E.3 |
| 15 | M49 40 + M50 86 regression sets unchanged | PASS (126/126) | E.4 |
| 16 | Lexical only, never claimed semantic | PASS | E.2 |
| 17 | Query refinement UI (scope kept, editable, disabled without suggestions, stale cleared, current signature, RTL/LTR) | PASS (Qt offscreen) | F |
| 18 | Verifier cases, dimensions separate, failed draft separate, escaping / bidi | PASS | G |
| 19 | GC audit; soak reclaimed with 0 worker collections | PASS (Linux offscreen) | H.1, H.2 |
| 20 | Repeated Windows lifecycle step: real view, isolated repetitions, original order, no skip / suppression; deterministic | **PARTIAL** (4/4 green runs; determinism not provable from 4 runs) | H.3 |
| 21 | §10 mutants (sync reads, generation guards, stale source, wrong well, partial answer, Persian injection quoted, scope-broadening suggestions, unverified citation, worker GC, late worker on disposed view) | PASS (29/29) | I.2 |
| 22 | M48 / M49 / M50 mutation re-runs | **PARTIAL** (44/44, 38/38, 53/55; 2 survivors analysed, not declared equivalent) | I.2 |
| 23 | Full suite, the same 4 skips only | PASS | I.1 |
| 24 | §11 gates (privacy, exception, ruff, coverage, lint), no debt raise, no dependency, no formula change, no passage logging | PASS | I.3 |
| 25 | §12 Git checklist; CI on code tip and report tip | PASS for code tip (J.2); report tip in the final reply | J |
| 26 | Semantic retrieval / real generation | NOT RUN (owner authorisation) | K |

## B. §3 Analysis: the whole cycle off the GUI thread

### B.1 Execution map (file database; `tabs/w12_Analysis.py`)

| # | Stage | Thread | Implementation |
|---|---|---|---|
| 1 | Selection (well / wellbore / section / report, deselect, Refresh, auto tick) | GUI | bumps `_generation`, clears the cache; `update_all_data()` cancels a cycle of another generation (`_cancel_revision` bumps `_rev_seq`) and starts one snapshot; an auto tick for the same generation joins the running one |
| 2 | Pre-read revision | worker | `AnalysisSnapshotWorker` computes `ev.data_revision` through `worker_database` (own read-only engine, M47 ownership) |
| 3 | DB snapshot | worker | every reader of the cycle (KPIs, time-depth, NPT, performance, today, recent, milestones, plan variance, intelligence, bores, data quality, evidence, analytics inputs) against a frozen scope (`_FrozenScope`: reader methods only, no widget access) |
| 4 | Canonical service | worker | `OperationsIntelligenceService` and the canonical engines unchanged; a memo service returns independent copies |
| 5 | Derived KPIs | worker | the same canonical functions; values returned as plain Python (no ORM row, session or QObject crosses threads; asserted recursively) |
| 6 | Qt update | GUI | `_paint_snapshot` → `_paint_for_revision` from the prefetched values only; a value the snapshot did not carry requests one more snapshot instead of reading |
| 7 | Post-read revision | worker | the M50 verify revision after the paint; a mismatch (concurrent edit) reads a new snapshot (bounded restart) — never a synchronous repaint |
| 8 | Status | GUI | "🟢 Updated" only when both revisions are equal; "🟡 Updating…" while a worker runs; a read error is explicit, never cached, never "No data", and Retry works |

In-memory databases (tests only; one shared connection) stay synchronous.
Generation and sequence tickets guard every delivery; the page joins its
worker on close (`cleanup` → `_cancel_revision(wait_ms=5000)`). Every current
scope change also cancels the running cycle (which bumps the sequence), so the
generation check is **defence in depth**; scenarios that change the generation
without a cancel exercise it directly (M51 child and, since `63e8043`, the M50
child).

Remaining GUI-thread work: Qt painting of the delivered values. Not moved (and
disclosed): the knowledge panel's `link_service.well_choices` read that fills
the well combo.

### B.2 Tests (`tests/test_m51_analysis_snapshot.py`, 28 tests: 13 scenarios of the real `AnalysisWidget` on a temp FILE database in one subprocess, Qt offscreen Linux; 15 in-process contract tests)

No GUI-thread SQL in any cycle or selection path (well A→B, well→bore→ST1→whole
well, section, report, every analytics view and evidence metric, deselect;
positive control: the synchronous path is seen) and **no worker statement
through the GUI's engine**; plain-Python payload read on a worker; snapshot
paint equals synchronous paint; reader error explicit and retryable; analytics
input error explicit; DB edit while the worker reads → detected and reloaded;
Refresh during a snapshot supersedes it; auto tick during a snapshot starts no
second one; rapid scope changes paint only the final scope; a scope change
without a cancel never paints the old snapshot; view change during a snapshot
gets one more cycle; close while a reader runs joins the worker; the worker
scope proxy fails closed. The UI child's stderr is bounded (8 MB; a healthy run
writes ~6 KB): runaway output fails the run at once (see I.2).

### B.3 Measured (`tools/quality/analysis_responsiveness_m51.py`, real flow, temp file SQLite, n = 15 per size, ms; evidence `m51-evidence/analysis_bench_46bc7bc.json`)

Linux 6.1, 2 CPUs, Python 3.11.2, PySide6 6.8.1.1 offscreen (rebuilt sandbox,
section J.3). `max_gap` = largest gap between 5 ms GUI-timer ticks (the longest
time the event loop could not run). Golden parity (painted values of the
snapshot path = synchronous path) held in every cycle at every size.

| Stage (snapshot path), median / P95 / max | 1 024 rows | 4 096 rows | 16 384 rows |
|---|---|---|---|
| revision (worker) | 25.2 / 34.0 / 34.2 | 43.5 / 59.3 / 65.2 | 119.6 / 165.2 / 199.3 |
| DB read: SQL execute (worker) | 5.9 / 20.6 / 29.7 | 7.0 / 13.7 / 21.1 | 12.0 / 31.1 / 40.2 |
| calculation: materialisation + canonical services (worker) | 118.4 / 143.2 / 153.3 | 243.8 / 272.4 / 299.3 | 783.3 / 880.8 / 900.4 |
| chart prep + widget updates (GUI) | 96.3 / 110.2 / 110.7 | 106.4 / 116.9 / 120.1 | 152.0 / 167.2 / 173.9 |
| paint: one offscreen render (GUI) | 28.5 / 39.5 / 50.8 | 32.7 / 40.2 / 46.1 | 29.6 / 39.8 / 52.3 |
| verify revision (worker) | 53.3 / 92.0 / 155.6 | 75.6 / 117.2 / 187.7 | 139.4 / 164.8 / 171.0 |
| total (Refresh → Updated) | 324.2 / 379.2 / 447.5 | 502.2 / 582.3 / 594.2 | 1244.1 / 1357.3 / 1393.7 |
| **largest event-loop gap** | **102.5 / 130.5 / 163.7** | **112.9 / 124.4 / 125.5** | **157.4 / 203.7 / 260.5** |
| synchronous path (pre-M51): total | 208.3 / 223.1 / 231.6 | 415.3 / 466.3 / 537.0 | 1269.0 / 1369.2 / 1458.7 |
| synchronous path: largest gap | 236.5 / 251.5 / 258.7 | 443.0 / 499.7 / 573.9 | 1300.7 / 1392.5 / 1483.8 |

Largest GUI paint steps at 16k (median): NPT chart 75.7, milestones 27.9,
analytics 20.6, time-depth 11.4 ms. The worker path takes longer in total at
1k/4k (thread hand-off and the extra verify read) but the event loop is blocked
2.3× / 3.9× / 8.3× less. No latency target is claimed.

## C. §4 Knowledge corpus off the GUI thread, never stale (`7c5a611`)

* `KnowledgeAssistantPanel`: on file databases the Ask, library-change check
  and semantic-build workers read the corpus signature **and** snapshot on their
  own read-only connection in **one** SQLite read transaction; the GUI thread
  runs no corpus SQL. In-memory databases stay synchronous.
* Signature: a digest of every approved page's text (sha256, computed on the
  worker), review status, position, document name and the link scope. A
  same-length edit or a review-status change gives a new signature (pre-M51
  code kept the signature and **cited a page that was no longer approved**).
  A DB trigger was rejected (schema change for a cache key).
* Read error ≠ "no documents"; cancel shows nothing; scope never broadened; the
  question and scope are kept.
* Tests (`tests/test_m51_knowledge_corpus.py`, 10): reads on a worker with its
  own connection; **same-length text edit → the next query never returns the old
  passage**; review status removes / restores a page; delete + reimport reusing
  ids with same-length text; link create / change / remove reach the next answer
  without broadening; read error explicit and retryable; cancel; only a real
  change invalidates; semantic build reads on its worker; snapshot and
  signature describe one database state. Interrupted rebuild: the signature is
  re-read for every query, so an index built for an older signature is replaced
  (`K-signature-change-keeps-index` mutant killed).

## D. §5 False answers (`f491ee9` forensic baseline, `6460608` fixes)

Forensic baseline recorded **before any edit** (`m51-evidence/forensics_baseline_7c5a611.json`:
terms, ids, scores, coverage, constraints, decision, reason):

| Id | Kind | Baseline decision | Cause found |
|---|---|---|---|
| N55 | wrong well | answered (false) | coverage inflated by the well-code tokens |
| N59 | partial overlap | answered (false) | a question word absent from the scope did not block |
| N64 | Persian injection | answered (false), quoted | Persian instruction not detected |
| N27 / N82 / N84 | cross-lingual | refused (miss) | glossary gaps |
| N45 | conflict | refused (miss) | "hole" vs "section" |
| N57 | partial overlap | refused (miss) | power / hp |
| N71 | paraphrased quantity | refused (miss) | time / depth quantity type |

General fixes (no question-id special cases; `RETRIEVAL_VERSION = 4`):
explicit well identity is a **hard constraint** at document level (text, file
name, confirmed link) — a passage naming only another well fails even inside a
document about both; the well code alone never makes a passage sufficient
(topic-only sufficiency); a question word found nowhere in scope vetoes an
answer (partial overlap → refusal), an aspect word does not; numbers are never
inherited between sentences; FA/AR instruction patterns (rules ignored,
answer-only, reveal secrets, "you are now", no sources, run commands, delete
files) with ordinary procedures (`دستورالعمل … اجرا کنید`, "ignore the previous
readings") explicitly not flagged; a flagged sentence stays visible as evidence
and is never quoted. After the fixes all nine are correct in the M50 set
(126/126, E.4; that set guided M50/M51 work and is not blind).

Refusal rate is measured with every result (E.3): held-out 0.333 → 0.351,
dev 0.456 → 0.263; refused answerable questions held-out 9 → 6, dev 14 → 0.

## E. §6 Cross-lingual evaluation

### E.1 Protocol

`tests/m51_gold_questions.py` (57 dev / 57 held-out) and the corpus were
committed in `91a069d` **before tuning**. The unchanged baseline (`91a069d`) was
run once on held-out (aggregates only) and on dev. Only dev guided changes. The
final knowledge code was frozen at `52adc99` (knowledge code identical to
`074dc0a`; later commits change only tests, the GC comment and tools), and
held-out was run **once** from a clean detached worktree at that SHA. **The
M51 held-out set is now spent.** The tool prints no per-question rows for
held-out; the six held-out questions that still fail a check were not looked
at. M49 (40) and M50 (86) sets are kept unchanged as regression.

Categories (both splits): FA→EN, EN→FA, mixed, Arabic/Persian letters, three
digit systems, unit spellings, paraphrased duration / depth / pressure /
density / frequency, synonyms, reordering, multi-document conflict, wrong well
/ report / size, partial overlap, unanswerable, missing pages, empty scope,
injection EN/FA.

### E.2 Mechanisms (lexical only)

Glossary concepts (EN↔FA technical terms), normalisation (Arabic/Persian
letters, digits, unit spellings; `NORMALIZATION_VERSION` unchanged —
index-only rules not changed), abbreviation expansion, heading / file-name
context and heading siblings, the hard constraints of D. **Not semantic.**

### E.3 Results (evidence `m51-evidence/heldout_*`, `dev_*`)

| Metric | Held-out baseline `91a069d` | **Held-out final `52adc99`** | Dev baseline | Dev final |
|---|---|---|---|---|
| all checks | 41/57 | **51/57** | 40/57 | 57/57 |
| Recall@5 (answerable) | 0.8837 | **1.0** | 0.8571 | 1.0 |
| complete-evidence R@5 | 0.8837 | 1.0 | | |
| MRR | 0.8004 | **0.9438** | 0.7321 | 0.9762 |
| top-1 doc/page | 0.7442 | **0.907** | 0.6667 | 0.9524 |
| answered rate (answerable) | 0.7907 | 0.8605 | 0.6667 | |
| refusal rate | 0.3333 | 0.3509 | 0.4561 | 0.2632 |
| refused answerable | 9 | 6 | 14 | 0 |
| refusal precision / recall | 0.5263 / 0.7143 | 0.70 / 1.0 | | |
| **false answers on unanswerable** | 4 | **0** | 3 | 0 |
| scope violations / fabricated ids / unapproved leaks / unsupported numbers / citation-check failures / identity / open errors | 0 | **0** | 0 | 0 |
| number-unit confusions / wrong-size false answers | 0 / 0 | 0 / 0 | | |
| procedures flagged as injection | 0 | 0 | | 0 |
| latency median / max (ms) | 9.36 / 24.89 | **41.06 / 89.6** | 10.04 / 33.53 (re-run, same machine) | 34.13 / 103.93 |
| peak RSS (MB) | 69.7 | 79.4 | 79.2 (re-run) | 70.1 |

Cross-lingual (held-out, n / R@5 / answered / all checks):

| Direction | Baseline | **Final** |
|---|---|---|
| FA→EN | 7 / 0.714 / 0.286 / 2 | 7 / **1.0 / 0.857 / 6** |
| EN→FA | 6 / 0.5 / 0.667 / 2 | 6 / **1.0** / 0.667 / **4** |
| mixed | 3 / 1.0 / 1.0 / 3 | 3 / 1.0 / 1.0 / 3 |

By language (held-out all checks): en 29/38 → 33/38, fa 9/15 → 14/15, ar 0/1
→ 1/1, mixed 3/3 → 3/3.

Disclosed: **latency regressed** (same-machine dev median 10.0 → 34.1 ms; the
added identity, coverage and glossary work), still well under a second. Peak
RSS differs by ±10 MB between repeated runs of the same code (79.2 vs 70.1 MB
for baseline / final on dev, 69.7 vs 79.4 on held-out) and is reported as
measured. `excluded_value_in_closest_passages` rose 6 → 9 (held-out): it counts
**refusals** whose closest passages (shown, marked insufficient, M49 design)
contain a forbidden value — the former false answers are now refusals that
show the related passage; no answer contains a forbidden value.

### E.4 Regression sets (`tools/quality/knowledge_eval_m50.py --split all`, code `e75afbd`, knowledge code = `52adc99`)

M49 40/40, M50 dev 43/43, M50 held-out (spent in M50, not blind) 43/43 —
126/126, R@5 1.0, 0 false answers, 0 scope violations, 0 unsupported numbers;
cross-lingual and mixed 16/16 (`m51-evidence/m50_all_final_e75afbd.json`).

## F. §7 Query refinement (`074dc0a`)

On "insufficient evidence" the panel shows the scope, found and missing terms,
related-but-insufficient sources, "semantic retrieval unavailable", and
glossary suggestions taken **only from the selected scope**. "Search with
suggested technical terms" uses an editable term field, is disabled without
suggestions, keeps the scope, replaces the blocking word (numbers, codes and
unrelated words kept), clears the stale result before the new search, reads
the current corpus signature, and Retry repeats the refined question. Effective
terms appear in diagnostics. Persian suggestions render right-to-left, English
left-to-right, escaped. Tests: `tests/test_m51_query_refinement.py` (11,
including refining every refused non-blind dev question: scope kept, no
unanswerable question answered). Dev probe at `074dc0a`: of 13 refused M51 dev
questions 3 got suggestions, 0 became answered, 0 false answers (M50 sets: 19 /
2 / 0 / 0) — the feature makes the refusal actionable; it does not by itself
raise recall.

## G. §8 Verifier (`da73f1b`)

Dimensions stay separate and none is called semantic ("Citation checks
passed" / "Not semantically verified"). New: `entities_match` (a draft naming
another well than its cited source fails, citing both wells does not launder
the wrong one; no code → not applicable), `sources_current` (passage edited
after retrieval, or document deleted and reimported with reused ids and
same-length text → fails), code digits are not quantities. Case → test:

| Case | Test |
|---|---|
| same number for two quantities; number without the relationship | `test_m50_verifier.py::test_adversarial_draft_fails_exactly_the_named_dimension` (quantity_relationship), `test_same_number_other_quantity_keeps_number_and_unit_dimensions_passing` |
| different units; unsupported conversion | same parametrisation (`units_match`, `numbers_in_cited_source`) |
| uncited sentence; fake label | same parametrisation (`claims_cited`, `citations_resolve`) |
| conflicting revisions | `test_conflict_must_be_disclosed`, `test_draft_hiding_one_side_of_a_conflict_is_not_used` |
| other well | `test_m51_verifier.py` (3 tests) |
| edited after retrieval | `test_a_source_edited_after_retrieval_fails_sources_current` |
| deleted / reimported reused id | `test_a_deleted_and_reimported_document_reusing_ids_fails_sources_current` |
| failed draft separate; escaping and bidi | `test_failed_draft_is_kept_apart_and_the_extractive_answer_stays`, `test_answer_and_failed_draft_are_escaped_and_take_the_direction_of_their_first_strong_letter` |

## H. §9 GC and Windows lifecycle (`52adc99`)

### H.1 Audit

`core/qt_gc.py` (M50): automatic cyclic collection off, collection from a
GUI-thread `QTimer` with the interpreter's thresholds — the fix for a captured
deadlock (worker-thread collection freeing Qt wrappers). Risks of disabling
automatic GC, evaluated: cycles live up to one interval longer; no collection
while the GUI thread is blocked; an explicit `gc.collect()` on a worker (ours or
a library's) and a library re-enabling automatic GC are not prevented by the
policy. `app.py` installs the policy before `initialize()` (source-contract
test). `trajectory_3d_view` / `trajectory_3d`: the M50 disposal (canvas closed
and deleted on the GUI thread, no Qt wrapper left for the collector) is kept;
Analysis timers stop and workers are joined on close; deferred deletes run on
the GUI thread. The fix was not reverted.

### H.2 Watchdog and soak

A `gc.callbacks` hook only increments counters for collections that start off
the GUI thread (no logging, lock or Qt call inside the collector); each timer
tick re-disables automatic collection if anything enabled it; `stats()` exposes
both. Soak (`tests/test_m51_gc_soak.py`, subprocess, Linux offscreen — **not
Windows desktop**): 6 interleaved rounds of real 3D view open/dispose, Analysis
refreshes with workers and knowledge queries: every collection on the GUI
thread, **0 on workers**, 1200/1200 worker-built cycles reclaimed, 0 views
alive, `gc.garbage` empty; positive controls (a worker collection and a
re-enabled GC) are detected and healed.

### H.3 Windows gate

New step "Repeated 3D and Analysis lifecycle (M51, isolated repetitions)" in
`.github/workflows/windows-release-gate.yml`: the real modules
(`test_trajectory_3d.py`, `test_trajectory_3d_lifecycle_m46.py`,
`test_m50_analysis_async.py`, `test_m50_trajectory_3d_disposal.py`,
`test_m51_gc_soak.py`) in the regression order, 3 repetitions, each a new
interpreter with its own data root; nothing skipped, deselected or suppressed;
any failing or dying repetition fails the gate.

| Commit | Windows run | Repeated step |
|---|---|---|
| `52adc99` | 40687205040 success | success (2026-10-28 12:32:38 → 12:34:53Z) |
| `e75afbd`, `e34382e` | cancelled by the next push | — |
| `46bc7bc` | 41174674523 success | success (2026-10-31 06:09:37 → 06:12:14Z) |
| `63e8043` | 41178473156 success | success (2026-10-31 07:06:38 → 07:09:45Z) |
| `dbf8d50` | 41181840890 success | success (2026-10-31 07:57:18 → 08:00:06Z) |

**PARTIAL**: green runs show the step works; they do not prove that the M50
intermittent native crash is gone (it was intermittent before the fix too).

## I. Tests, mutation, gates

### I.1 Full suite

Run in two halves (Qt offscreen, Linux), tree `63e8043`:

| Half | Result |
|---|---|
| 1 (133 files) | 2072 passed, 2 skipped |
| 2 (133 files) | 1688 passed, 2 skipped, 2 errors → after installing the CI-pinned `build==1.6.1` into the rebuilt venv (J.3), `tests/test_release_boundary_imports.py` 3 passed |
| **Total** | **3762 passed, 4 skipped, 0 failed** of 3766 collected |

The two errors were the wheel-building fixture of
`test_release_boundary_imports.py` (`No module named build`): the venv rebuilt
after the sandbox reset lacked the PyPA `build` package that CI installs
(`.github/workflows/ci.yml`, `build==1.6.1`); no code or test was changed for it.

Skips (the same four as M50): `test_ddr_acceptance.py:33` ×2 (real DDR is
opt-in), `test_mineru_real_integration.py:26`, `test_packaging_smoke.py:218`.

Collection 3663 (start) → 3761 (`46bc7bc`) → **3766**: +98 M51 tests, +1 M49
parameter (`pump liner size for pump 7351`), +2 M50 retrieval tests (code-only
file-name question, sufficiency tier over every gold question), +2 M50 Analysis
scenarios. No test was removed or skipped; no assertion was weakened.

`dbf8d50` changes only how `tests/test_m50_analysis_async.py` runs its child
(I.2); that file was re-run after the change: 27 passed.

### I.2 Mutation (fresh runs)

M51 (`tools/quality/mutation_m51.py`, 29 mutants on the M46 engine; every
snippet verified exactly-once):

* First complete run (tree `e34382e` + tests at that SHA): **26/29**. Survivors —
  real test gaps, not declared equivalent:
  `AN-snapshot-generation-guard-removed` (the generation check sits behind the
  sequence check; every current scope change also cancels via
  `_request_snapshot`, so no test reached it), `AN-snapshot-uses-gui-engine`
  (the probe only watched GUI-thread statements), `K-persian-ignore-rules-unflagged`
  (the only test sentence was also caught by the "only write …" pattern).
  Closed in `46bc7bc` by new assertions / scenario / sentences; mutants unchanged
  (re-run of the three: `m51_only_fix3.json`).
* Final complete run on `46bc7bc`: **29/29 killed**, 0 survived, 0 declared
  equivalent (baseline 94 passed).
* Before the fix to the test harness, `AN-cycle-read-on-gui-thread` caused
  unbounded synchronous recursion; the UI child logged ~3.8 MB/s of tracebacks
  that the parent buffered in memory until the 900 s timeout (~3 GB on a
  3.9 GB machine — the likely cause of a sandbox reset during M51). `ad0b4d7`
  bounds the child's stderr (8 MB → kill and **fail**); the mutant is now killed
  in ~7 s by an explicit failure, not by a timeout.

Mutant groups: AN 6 (GUI-thread reads ×2, generation guard, late worker after
dispose, GUI engine, read error as No data); K corpus 4; K answers 6 (wrong
well, partial overlap, code-only sufficiency, Persian injection unflagged,
flagged sentence quoted, procedure flagged); Q 6 (suggestions from all scopes,
refined search broadens scope, blocking word kept, numbers replaced, stale
result kept, Retry drops refinement); V 4 (other well, edited source, snapshot
not checked, code digits as numbers); G 3 (collected on worker, watchdog blind,
re-enable not healed).

Ported, same meaning (the M51 code moved the original text): M49
`K-stale-corpus-signature` (`(audit, link_digest, content)` → `(link_digest,)`),
`A-absence-unchecked` (`absent_topic +` → `list(terms) +`); M50
`R-absent-ignores-context` (`covered = set()`), `R-version-not-bumped` (4 → 3),
`A-sentence-inherits-any-size` (same expression on its own line),
`D-diagnostics-unescaped` (snippet widened by the docstring line for
uniqueness). Not added: `V-reimported-id-accepted` (the text-sha check also
catches it — defence in depth, not equivalence) and `_refine_base` / scope-check
mutants (layered defences make them survive; recorded, not hidden).

Old sets, re-run on the M51 code (fresh runs; never reused):

| Set | First re-run | Final run | Notes |
|---|---|---|---|
| M48 (44) | 44/44 (tree `46bc7bc`) | 44/44 (no M48 test or contract changed afterwards) | — |
| M49 (38) | 37/38 (tree `46bc7bc`) | **38/38** (`63e8043`) | `R-identifier-weight-removed` survived: the M51 absent-word veto refuses unknown *words* first, so both test questions no longer needed the weight. Numbers are exempt from that veto, so an unknown number is where only the weight refuses; `pump liner size for pump 7351` added to the existing test |
| M50 (55) | 50/55 (tree `46bc7bc`) | 53/55 (`63e8043`, `N-synchronous-fingerprint` ended by OOM, see below) → **53/55** (`dbf8d50`, every kill an exit-1 test failure) | see below |

M50 first re-run survivors and what was done:

* `N-generation-guard-removed` (same line as the M51 AN mutant) and
  `N-worker-not-retained`: since M51 the first revision of a cycle runs in the
  snapshot worker and every scope change cancels through `_request_snapshot`,
  so the M50 scenarios no longer reached the generation check or the
  verify-phase `RevisionWorker` retention. Two scenarios added to
  `tests/m50_analysis_child.py` (existing scenarios unchanged): a generation
  change without cancel, and the page destroyed while the verify worker is
  blocked. **Killed.**
* `R-sufficiency-rerank-removed`: observable in 41 of 183 non-held-out
  questions (an answering passage ranked below insufficient ones), but the one
  synthetic test no longer forced the order. Added the tier invariant over every
  M49 and M50 gold question (≥ 10 mixed-tier results asserted). **Killed.**
* `R-file-name-context-dropped`, `R-absent-ignores-context`: **SURVIVED, not
  declared equivalent.** Since M51, `chunk_context` appends the file-name and
  heading tokens to every passage and identity is checked at document level, so
  the M50 contract (Q19 answered; the message never claims a code missing that
  the file name states) holds through another path; a differential probe over
  183 non-held-out questions plus 8 code-only questions found no change in state,
  evidence or missing terms. The only observable effect: for N16 / N19 the
  mutant quotes **one unrelated sentence fewer** from the same page (e.g. the
  cement-top sentence for a MAASP question). A test that kills them would pin
  that imprecision, and the knowledge code is frozen after the held-out run, so
  it is recorded as an open finding (K) instead. A behavioural test (a question
  that is only a code stated by the file name never reports it missing) was
  added anyway.

**Harness defect found by the old-suite runs.** In both complete M50 runs on
the M51 code, `N-synchronous-fingerprint` was counted KILLED with exit −9. The
kernel log shows the OOM killer ended the pytest process (3.2 GB anonymous RSS):
under the mutant the synchronous path recurses (`RecursionError`) and the M50
UI child floods tracebacks, which `tests/test_m50_analysis_async.py` buffered
without limit (`subprocess.run(capture_output=True)`) — the same mechanism as
M51 `AN-cycle` before `ad0b4d7`. The child was **orphaned** and kept running
(two such processes, 38 and 70 min old, were found during the full suite and
stopped). A kill by the OOM killer is not an assertion, so `dbf8d50` gives the
M50 harness the same bounded drain as the M51 one (8 MB stderr → kill and
fail; the child is also killed on timeout; a healthy child writes ~8 KB; no
assertion changed). Re-run alone: the mutant now fails with an explicit
"runaway errors" failure in ~6 s, exit 1, no orphan (`m50_only_syncfp.json`).
The complete M50 set was then re-run on `dbf8d50` (table above, final column).

**Process incident.** During one earlier run a test file was edited while the
mutation engine was running. The engine copies the working tree once at start
(`_copy_worktree`), so that run tested exactly the pre-edit tree; the edited
state was covered by later runs. The final runs in the table were started on a
clean, committed tree and nothing was edited while they ran.

Evidence: `m51-evidence/mutation_*.json`, `m50_only_*.json`, `m49_only_*.json`.

### I.3 Gates

| Gate | Result |
|---|---|
| Lint debt (`verify_release.verify_lint`) | 727 = ceiling 727 (unchanged, no new debt) |
| Silent-exception ceiling (`tools/quality/exception_scan.py --check`) | pass |
| Privacy (`tools/privacy/privacy_check.py`) | 0 findings (1166 files) at every commit |
| Coverage (CI leg, branch+line) | 58.83% on `46bc7bc`, `63e8043` and `dbf8d50` (M50: 58.73%); floor 45.50% unchanged, no new omit pattern |
| `git diff --check`, ruff on changed files | clean |

No passage, question or password is logged (M49 log test still passes); no
network, cache in user data, synthetic data only; no new dependency (the
rebuilt system libraries are sandbox-only, J.3); no formula change.

## J. Git and CI

### J.1 State

Start (read-only audit): remote = local = `2dab8b1`, clean, 0 ahead / 0
behind, one worktree, 3663 tests collected. No checkout of, commit to, push to
or merge into `drill-Master` or `main`; no force-push, reset, rebase, tag,
signing, release or repository-setting change. Every package was pushed on its
own and confirmed with `git ls-remote`.

| Commit | Package |
|---|---|
| `9f68056` | feat(analysis): every Analysis read and calculation on a snapshot worker |
| `795c964` | test(analysis): per-stage responsiveness benchmark on a file database |
| `7c5a611` | fix(knowledge): corpus read on a worker, same-length edit detection |
| `f491ee9` | test(knowledge): forensic baseline before any fix |
| `91a069d` | test(knowledge): M51 corpus and 114 labelled questions, before tuning |
| `6460608` | fix(knowledge): identity hard constraint, partial-overlap veto, FA/AR injection |
| `da73f1b` | fix(knowledge): verifier identity and source currency |
| `074dc0a` | feat(knowledge): in-scope query refinement |
| `52adc99` | feat(gc): watchdog, soak, repeated Windows lifecycle step — **held-out freeze** |
| `e75afbd` | test(quality): M51 mutation set, six ported M49/M50 mutants |
| `ad0b4d7` | test(m51): bounded stderr for the M51 Analysis child |
| `e34382e` | docs(m51): held-out final, dev and M50 regression evidence |
| `46bc7bc` | test(m51): three mutation gaps closed |
| `63e8043` | test: four M49/M50 contracts pinned (old-suite re-run) |
| `dbf8d50` | test: bounded stderr for the M50 Analysis child — **code tip** |
| report tip | docs(m51): this report, evidence, index row |

End state: J.4.

### J.2 CI (exact SHAs)

| SHA | Kind | Source release gate | Windows release validation |
|---|---|---|---|
| `52adc9929304d56284fad345e133eaab73bc1168` | code (held-out freeze) | 40687205064 success | 40687205040 success |
| `46bc7bcad8420a12749946211f31f6b13cbaf520` | tests | 41174674492 success | 41174674523 success |
| `63e8043398fd1d168fa04b5cbd3067eafe6ffa5a` | tests | 41178473204 success | 41178473156 success |
| **`dbf8d506bfd40ae97b1d366d8649c380449453dc`** | **code tip** (tests) | **41181840781 success** | **41181840890 success** |
| report tip | docs | see J.4 | see J.4 |

Intermediate SHAs: `e75afbd` and `e34382e` — both workflows cancelled by the
next push; `ad0b4d7` (pushed together with `e34382e`) has no runs. No claim is
made for them.

### J.3 Environment and sandbox reset

During the mutation run the sandbox was reset (likely out of memory, I.2).
Git was recovered non-destructively (fetch, temporary index comparison,
compare-and-swap `update-ref`); one unpushed local commit was lost and its
content — still in the working tree — was re-committed as `e75afbd`. The work
data directory was lost; the committed evidence was intact, and the benchmark,
dev runs and mutation runs above were re-run after the reset. The Python venv
was rebuilt from `requirements-lock.txt` (the CI-pinned `build==1.6.1` was
added only when the full suite showed it missing, I.1). The sandbox OS image had lost the
system libraries PySide6 needs and package mirrors were blocked, so they were
built from pinned upstream source tags into a directory outside the repository
(test environment only, never shipped): libglvnd `v1.7.0` (`libEGL`,
`libOpenGL`, `libGLdispatch`), libxkbcommon `xkbcommon-1.7.0`, dbus
`dbus-1.14.10` (libdbus) with expat `R_2_6_4`, byacc `t20241231` (build tool).
`libGL.so.1` is a **minimal test library** that depends on libglvnd's
`libOpenGL` and provides the 21 GLX entry points the Qt libraries link,
each reporting "GLX unavailable" (as libglvnd does with no vendor); offscreen
raster Qt never calls them. All results here are Qt **offscreen** on Linux.

### J.4 End state

After the report commit: local = remote (`git ls-remote`), working tree clean,
0 ahead / 0 behind, no untracked file, no unpushed commit, one worktree. The
report commit's SHA and its CI result are given in the mission's final reply
(a report cannot contain its own SHA).

## K. BLOCKED / NOT RUN / PARTIAL

| Item | Status | Reason |
|---|---|---|
| Event-loop gap of the Analysis cycle | PARTIAL | 103–157 ms median remains (Qt painting) |
| Windows lifecycle closure | PARTIAL | see H.3 |
| Semantic retrieval, real generation | NOT RUN | no local model (owner authorisation required) |
| Semantic-enabled screenshot | NOT RUN | same |
| Windows desktop / field acceptance, release | NOT RUN (owner-gated) | |
| Assistant latency | regressed, disclosed | E.3 |
| Knowledge panel well-combo read | open | `link_service.well_choices` still on the GUI thread |
| Answer precision with a file-name well code | open finding | for N16 / N19 the answer also quotes one unrelated sentence from the same page (I.2, M50 survivors); knowledge code frozen after the held-out run |
| M50 mutants `R-file-name-context-dropped`, `R-absent-ignores-context` | SURVIVED (not equivalent) | I.2 |

## L. Owner decisions

Installing Ollama / pulling a model (needed for semantic retrieval and real
generation); branch protection; release, signing and tag; Windows desktop and
field acceptance.
