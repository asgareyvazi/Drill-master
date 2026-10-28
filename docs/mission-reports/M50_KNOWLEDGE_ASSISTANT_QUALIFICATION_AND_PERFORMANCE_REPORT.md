# M50 — Knowledge Assistant qualification, local-model readiness, evidence verification, retrieval quality and responsive Analysis

Branch `arena/72010272-drill-master`, base `740a162b3c6e29cd2074b2083023fa3955fe087e`
(the M49 report tip; M49 code tip `8cd52a0`). Status values: PASS / FAIL /
PARTIAL / BLOCKED / NOT RUN. All data is synthetic (`tests/m48_synthetic.py`,
`tests/m49_knowledge_fixtures.py`, `tests/m50_knowledge_fixtures.py`: wells
`SYN-*`, documents `SYN-KA-01 …`, `SYN-KE-05 …`, `SYN-INJECTION …`). No real DDR,
real document, real well or real money value was opened or reproduced. **No
language model or embedding model was installed, downloaded or run** (Ollama is
absent from the sandbox, and installing it or pulling a model needs explicit
owner authorisation). No EXE, installer or release bundle was built by this
mission (the Windows CI runner builds its own). The application stays
**UNSIGNED**. Nothing here is release approval, Windows desktop acceptance,
field validation, semantic qualification or a model-quality claim.

## A. Summary

| § | Item | Status | Evidence |
|---|---|---|---|
| 2 | Start audit (remote, branch, baselines 3540/0/4, mutation M49 38/38, M48 44/44) | PASS | G.1 |
| 3 | Analysis data revision computed off the GUI thread, same digest, M47 connection ownership, generation/sequence guards, concurrent-edit detection, disposal | PASS | B |
| 3 | Whole Analysis update cycle responsive | **PARTIAL**: load/paint still runs on the GUI thread (752 ms median at 16 k rows) | B.3 |
| 4 | Q09/Q16/Q19 fixed by general mechanisms; 86 new gold questions (dev 43 / held-out 43) | PASS | C |
| 4 | Targets: 0 out-of-scope, 0 fabricated ids, recall > 37/40, no unsupported numbers | PASS | C |
| 4 | Target: 0 false answers on unanswerable questions | **PARTIAL**: dev 0, held-out 4 (official) / 3 (post-hoc) | C.3 |
| 5 | Verifier: 7 separate dimensions; "Citation checks passed" / "Not semantically verified"; failed draft kept apart; exact page/span navigation | PASS (adversarial synthetic tests) | D |
| 6 | Real `OllamaAdapter` generation and real embeddings | **BLOCKED / NOT RUN** (no local model) | E |
| 6 | UI states for every model/index condition; "ready" never inferred from the server alone | PASS (Qt offscreen) | E |
| 7 | Licence table per model; legacy AI importer audit | PASS (importer had 3 real defects, fixed) | F |
| 8 | Windows 3D lifecycle crash | **PARTIAL**: a real Linux-reproduced defect fixed with a deterministic regression; Windows passed on both completed fix commits (`981a67f`, `e48495c`: 2/2), but a pre-fix commit also passed (intermittent), so Windows closure is not proven | G |
| 9 | Diagnostics panel; 7 screenshots of real states | PASS; semantic-enabled screenshot **NOT RUN**, failed-draft screenshot **BLOCKED** | H |
| 10 | Full suite on the code tip | PASS: 3659 passed, 0 failed, 4 skipped (the same 4) | I.1 |
| 10 | Mutation M50 / M49 / M48 | PASS: 55/55, 38/38, 44/44 | I.2 |
| 12 | CI on the exact code tip `e48495c` | PASS: Source 40670288118 and Windows 40670288104 success | J.2 |

## B. §3 Responsive Analysis

### B.1 Design

* `RevisionWorker` (`tabs/w12_Analysis.py`) computes `ev.data_revision` on its
  own thread through `worker_database` (its own read-only connection, M47
  bounded connections; never the GUI connection). The digest is unchanged (no
  weakened hash); the reader polls `cancelled` every 512 rows.
* Cycle: revision **before** → load/paint → revision **after**. "🟢 Updated"
  only when both revisions are equal; a concurrent write between them triggers
  a bounded reload; read errors are explicit and never cached.
* Each request carries a `(generation, sequence)` ticket. Well/bore/report
  change, deselect, refresh and disposal bump the generation; a late result
  from an older ticket is ignored. Workers are tracked and joined on close (no
  live thread after the tab closes).
* `core/qt_gc.py`: cyclic garbage collection runs only on the GUI thread. A
  real deadlock was captured when a collection on the worker thread freed Qt
  wrappers; soak 12/12 after the fix.
* In-memory databases (tests only, one shared connection) stay synchronous.

### B.2 Tests (`tests/test_m50_analysis_async.py`, 25 tests, real Analysis page on a temp FILE DB, Qt offscreen)

Currency-only change; `TimeLog24H.code` change; NPT reclassification with the
same duration; same row count and sum; delete + insert; well change mid-hash;
deselect mid-hash; late old result; DB error (not cached, retry works); tab
closed with an active worker; concurrent edit between the two revisions;
repeated changes; M49 parity of the digest; GC-policy tests.

### B.3 Measured responsiveness (`tools/quality/analysis_responsiveness_m50.py`, n = 15 per cell, median / max ms)

Largest gap of a 5 ms GUI-thread timer (the longest time the event loop could
not run). Post-hoc regeneration on `e48495c` (the earlier outputs were lost in
a sandbox reset); Linux, 2 CPUs, Python 3.11.2, Qt offscreen.

| Extra time-log rows | revision, sync (M49) | revision, async (M50) | revision wall time (async) | whole cycle, sync | whole cycle, async |
|---|---|---|---|---|---|
| 1 024 | 10.81 / 26.02 | 7.66 / 22.42 | 25.71 / 43.39 | 199.58 / 212.05 | 169.15 / 176.23 |
| 4 096 | 28.71 / 35.85 | 10.23 / 11.13 | 43.22 / 47.22 | 336.02 / 371.95 | 282.95 / 316.59 |
| 16 384 | 102.88 / 115.92 | 11.07 / **59.18** | 120.45 / 176.41 | 893.66 / 985.30 | 752.31 / 817.48 |

An earlier in-mission run at 16 k gave 112.1 / 133.1 → 11.2 / 25.4 (revision)
and 978 / 1104 → 811 / 902 (cycle). The 59 ms maximum above is a single
outlier of 15 in this run and is reported as measured. **The revision no longer
blocks the GUI; the load/paint steps still do (PARTIAL).** The page shows
"🟡 Updating…" while the worker runs (screenshot H.2).

## C. §4 Retrieval quality

### C.1 Gold set

`tests/m50_gold_questions.py`: the 40 M49 questions unchanged on the M49
corpus plus 86 new ones on a distractor corpus (EN, FA, mixed, Arabic/Persian
letters, Persian digits, units, decimals, abbreviations, paraphrased
quantities, reordering, scoped, conflict, wrong size, wrong well,
unanswerable, partial overlap, injection). Dev 43 / held-out 43; held-out
labels were committed in `7f2829b` **before** any M50 retrieval change and were
never used for tuning.

### C.2 Mechanisms (retrieval v3, `1ec2dca`, plus `7dc171a`)

* A well code stated in a page header or file name covers that page's chunks
  (whole code only; numbers and words are never inherited).
* "How long / often / deep / heavy" and named quantities require a passage
  showing that quantity (noun or unit); otherwise the score is capped below
  sufficiency, so the assistant refuses rather than quoting an unrelated value.
* Sufficient passages rank ahead of insufficient ones; "16 in section" is a
  size designation, not a conflicting value; conflicts are keyed by size.
* Glossary entries are kept only with dev or M49-failure evidence (3 removed).
* `7dc171a`: a sentence from a paragraph containing a detected instruction is
  never quoted (pre-existing since M49; found by the held-out run).
* Q09, Q16 and Q19 now pass. These are lexical/glossary/trigram fixes, **not
  semantic retrieval**.

### C.3 Results

Official runs (`1ec2dca`), baseline → final:

| Metric | M49 set (40) | Dev (43) | Held-out (43, single official run) |
|---|---|---|---|
| All checks | 37 → 40 | 20 → 41 | 20 → 35 |
| Recall@5 | 1.0 → 1.0 | 0.9412 → 0.9706 | 0.875 → 0.9375 |
| MRR | 0.9483 → 1.0 | 0.7696 → 0.9265 | 0.6859 → 0.8672 |
| Refusal precision / recall | 0.85 / 1.0 → 1.0 / 1.0 | 0.36 / 0.89 → 0.82 / 1.0 | 0.33 / 0.64 → 0.64 / 0.64 |
| False answers on unanswerable | 0 → 0 | 1 → 0 | 4 → 4 |

Every run: 0 wrong-size false answers, 0 number/unit confusions, 0 unsupported
numbers, 0 fabricated ids, 0 scope violations, 0 unapproved-page leaks.

**Post-hoc** on the code tip `e48495c` (held-out is spent; these are not
official): M49 40/40; dev 41/43; held-out 35/43, Recall@5 0.9062, MRR 0.8594,
refusal precision 0.6154 / recall 0.7273, 3 false answers; overall 116/126,
complete-evidence R@5 0.9579, top-1 doc/page 0.8947, citation-check failures 0,
latency median 7.2 ms / max 22.8 ms, peak RSS 70.9 MB. Identical to the
post-hoc run on `cb2d5e0`, so §6–§9 changed no retrieval result.

Per category (post-hoc `e48495c`; n, all checks, R@5, MRR, false answers):

| Category | n | All | R@5 | MRR | False ans. |
|---|---|---|---|---|---|
| abbreviation | 10 | 10/10 | 1.0 | 0.9 | 0 |
| arabic-letters | 5 | 5/5 | 1.0 | 1.0 | 0 |
| conflict | 3 | 2/3 | 1.0 | 1.0 | 0 |
| cross-lingual (FA question, EN text) | 8 | 4/8 | 0.5 | 0.5 | 0 |
| decimals | 5 | 5/5 | 1.0 | 0.9 | 0 |
| digits | 2 | 2/2 | 1.0 | 1.0 | 0 |
| exact | 6 | 6/6 | 1.0 | 0.9167 | 0 |
| injection | 7 | 6/7 | 1.0 | 1.0 | 1 |
| mixed / english / persian | 13 | 13/13 | 1.0 | 1.0 | 0 |
| number-unit / units | 8 | 8/8 | 1.0 | 1.0 | 0 |
| paraphrase / paraphrase-quantity | 11 | 10/11 | 1.0 | 1.0 | 0 |
| partial-overlap | 5 | 3/5 | 1.0 | 0.75 | 1 |
| reordering | 3 | 3/3 | 1.0 | 0.8333 | 0 |
| scoped / scoped-no-evidence | 15 | 15/15 | 1.0 | 1.0 | 0 |
| wrong-size | 6 | 6/6 | – | – | 0 |
| wrong-well | 4 | 3/4 | – | – | 1 |
| unanswerable / not-in-corpus / no-page / missing-page / empty-scope / unapproved | 12 | 12/12 | – | – | 0 |
| page / multi-doc / edited-page | 3 | 3/3 | 1.0 | 1.0 | 0 |

By language: EN 88/93 (R@5 1.0); FA 20/25 (R@5 0.7895); mixed 8/8.
Cross-lingual and mixed together: 12/16, R@5 0.75.

Failing questions (post-hoc): N27, N82, N84 (held-out) and N83 (dev), all
Persian questions over English text, cross-lingual recall miss → refusal; N45
(conflict question refused); N57 (partial overlap refused); N71 (dev,
Persian-digit paraphrase refused); and **3 false answers**: N55 (wrong well
answered), N59 (partial overlap answered) and **N64 (a Persian
injection-paragraph sentence quoted as an answer; quoted as data and never
executed, but it is a defect)**. None of these was patched after being seen on
held-out data (no tuning on held-out). N45 was answered in the official run
and refuses post-hoc after the `7dc171a`/§5 changes.

**Cross-lingual recall is the main gap. It needs real semantic retrieval
(BLOCKED, E) or new lexical work measured on dev.**

## D. §5 Verifier and citations

* `CitationCheck` records 7 separate dimensions instead of one boolean:
  `citations_resolve`, `claims_cited`, `numbers_in_cited_source`,
  `units_match`, `quantity_relationship` (**heuristic**: the number's quantity
  noun must appear near it in the cited passage), `sizes_match`,
  `conflicts_disclosed`. `semantic_verified` is always False. Labels:
  "Citation checks passed" and "Not semantically verified". `ANSWER_VERSION=2`.
* Adversarial tests (`tests/test_m50_verifier.py`, 23 tests): same number for
  a different quantity, wrong unit, wrong size, undisclosed conflict, bad
  conversion, a citation lacking the relationship, a missing citation, a
  nonexistent label, a citation not supporting the quantity. 91 gold answers,
  0 failing a dimension.
* A model draft that fails any dimension never replaces the extractive
  answer. It is shown apart, escaped, as "MODEL DRAFT NOT USED" with each
  failed dimension listed. Rendering is covered by offscreen tests; no real
  model produced a draft (E).
* Navigation (`tests/test_m50_citation_navigation.py`): citations carry the
  page text version; a changed or deleted page is refused; multiple passages
  per page and the same page number in different documents open the exact
  span.
* **Owner decision:** a same-length in-place edit of a page could keep the
  same text version; detecting it needs a content hash per page
  (`RETRIEVAL_VERSION` not bumped).

## E. §6 Real local model

| Item | Status | Detail |
|---|---|---|
| Real generation through `OllamaAdapter` | **BLOCKED / NOT RUN** | no model installed; candidates `qwen2.5:7b-instruct`, `qwen2.5:1.5b` (both Apache-2.0); installing needs owner authorisation |
| Real embeddings / semantic retrieval | **BLOCKED / NOT RUN** | candidates `bge-m3` (MIT, 1.2 GB in Ollama), `multilingual-e5-small` (MIT) |
| Real check against 127.0.0.1:11434 | PASS | ConnectionRefused → "Local model unavailable" with setup guidance |
| Extractive fallback works with no model | PASS | every screenshot in H |
| UI states | PASS (Qt offscreen) | server not running, model not installed, embedding not configured, index not built, index stale (fixed: a semantic index built for other documents was still labelled ready), lexical-only, generation ready/unavailable, remote rejected, timeout, cancelled, verification failed |
| Embedding reason when the server is down | fixed in `981a67f` | with `bge-m3` entered and no server, the label claimed "no local embedding model configured"; now "embedding model 'bge-m3' could not be checked - …" (found while reviewing screenshots; test + mutant) |

A fake LLM or stub server proves guards only, not quality.

## F. §7 Licences and the legacy AI importer

| Model (tag) | Weights licence | Commercial | Local (Ollama) | Size (sourced) | Status |
|---|---|---|---|---|---|
| `qwen2.5:7b-instruct` | Apache-2.0 | allowed | yes | not sourced | catalog entry, not measured |
| `qwen2.5:1.5b` | Apache-2.0 | allowed | yes | 986 MB | named in guidance only |
| `qwen2.5:0.5b` | Apache-2.0 | allowed | yes | 398 MB | not used |
| `qwen2.5:3b` | Qwen Research Licence | **non-commercial** | yes | 1.9 GB (Q4_K_M) | **removed** from catalog and guidance |
| `qwen2.5:72b` | not Apache-2.0 (Qwen licence; terms not re-checked) | restricted | yes | – | not used |
| `bge-m3` | MIT | allowed | yes | 1.2 GB | candidate embedder, not run |
| `multilingual-e5-small` | MIT | allowed | yes | 476 MB (f32) | candidate embedder, not run |
| Ollama runtime | MIT (code) | – | – | – | not installed |

Legacy importer (`core/ai_import_mapper.py`), defects found and fixed in
`3521f1a` (17 tests; 13 + 1 fail on the old code):
1. any endpoint was accepted, the environment proxy was followed and HTTP
   redirects were followed → now loopback only, no proxy, no redirects;
2. Ollama cloud models (`:cloud` tags, `remote_host`/`remote_model`) were
   listed and usable → now refused and never shown as local;
3. the catalog suggested `qwen2.5:3b` → removed; each catalog entry carries
   its licence (`config/ai_models.json`, `DEPLOYMENT.md`).

## G. §8 Windows 3D lifecycle

* History: native crashes (access violation / stack overflow) at the first Qt
  work of a new 3D view after earlier 3D tests: runs 40168089020,
  40499433606, 40647262700 (`f93d06e`).
* Root-cause candidate (measured on Linux, **not Windows proof**): every
  disposed view left about 6–7 k objects in cyclic garbage (figure ↔ canvas,
  `canvas.draw_idle` → view, Matplotlib/pyparsing first-import frame cycles).
  A later automatic collection then freed Qt wrappers inside unrelated Qt work.
* Fix (`3521f1a`, `tabs/trajectory_3d_view.py`): cut the cycles on
  `destroyed`; one GUI-thread collection after Matplotlib's first import.
  Disposed views are now freed by reference counting.
* Regression (`tests/test_m50_trajectory_3d_disposal.py`, 6 tests, Qt
  offscreen): automatic GC disabled, the view disposed four ways plus a fresh
  interpreter for the first import. **6/6 fail without the fix** (checked
  twice: first via a one-time `git stash`, restored; then via a file copy on
  the final tree).
* `e48495c`: CI full-suite order showed the test counting **other tests'**
  widgets (queued `deleteLater()` events processed inside the measurement).
  The test now flushes deferred deletes and holds and excludes pre-existing
  wrappers; the assertion (`[]`) is unchanged and it still fails 6/6 without
  the fix.
* Windows CI: `cb2d5e0` (no fix) **success**; `3521f1a` (fix) cancelled by the
  next push (concurrency group); `981a67f` (fix) **success**; `e48495c` (fix)
  **success**. Because a pre-fix commit also passed, the crash is intermittent and
  **Windows closure is not proven**. Reruns and `workflow_dispatch` returned
  HTTP 403 from this sandbox, so repeats came only from pushes. No skip or
  suppression was added.

## H. §9 Diagnostics and screenshots

### H.1 Diagnostics panel (`tabs/knowledge_assistant.py`)

Under each answer: result, extractive vs generated (and "draft failed"),
retrieval methods that ran, semantic retrieval (used, or the reason), scope
with the number of eligible documents and reviewed pages, passages used (or
"closest passages examined" for refusals, with instruction-like passages
counted), validation (label plus ✓ / ✗ / – per dimension, or "not
applicable"), conflicts with source labels, refusal reason with missing terms,
local-model state. Fully HTML-escaped; never repeats passage text; cleared with
any stale result. 6 tests plus 4 mutants (stale kept, semantic claimed,
unescaped, number fragments listed).

### H.2 Screenshots (real `MainWindow`, temp synthetic DB, Qt offscreen on Linux, raster, stub GL, 1600×1250; `tools/screenshots/capture_m50.py`; pinned in `tools/privacy/policy.json`)

| File | Shows |
|---|---|
| `m50-screenshots/m50_lexical_answer_diagnostics.png` | extractive answer with full diagnostics |
| `m50-screenshots/m50_semantic_unavailable_reason.png` | semantic unavailable with the reason after a real model check |
| `m50-screenshots/m50_conflict_both_values.png` | conflict: 1.08 sg [S1] vs 1.05 sg [S2] |
| `m50-screenshots/m50_refusal_insufficient_evidence.png` | wrong-size refusal, no validation claimed |
| `m50-screenshots/m50_model_unavailable.png` | real check, connection refused; extractive answer kept; injection passage flagged |
| `m50-screenshots/m50_scope_changed_mid_request.png` | scope changed while the worker ran; late result dropped (asserted by the script) |
| `m50-screenshots/m50_analysis_updating_responsive.png` | "🟡 Updating…" grabbed while the revision worker was running (asserted) |
| semantic retrieval **enabled** | **NOT RUN**: needs a real embedding model; never faked |
| number/unit **failed draft** | **BLOCKED**: only a real model produces a draft; a scripted draft would fake "model generated"; rendering covered by offscreen tests |

## I. Tests, mutation, coverage, gates

### I.1 Full suite on the code tree of `e48495c`

`2016 passed, 2 skipped` + `1643 passed, 2 skipped` = **3659 passed, 0 failed,
4 skipped** (two halves, Linux, Python 3.11.2, PySide6 6.8.1.1 offscreen,
SQLite 3.40.1). Skips: `test_ddr_acceptance.py:33` ×2,
`test_mineru_real_integration.py:26`, `test_packaging_smoke.py:218` (the same
4 as M49). +119 tests = the 8 new M50 files (25 + 15 + 5 + 7 + 21 + 17 + 6 + 23).
Three M49 assertions were changed to the §5 contract (failed draft no longer
becomes the answer; the label is no longer "verified"); each change asserts
more than before. All M49 and M50 knowledge tests are in the Windows gate
(`tests/test_windows_release_gate_contract.py`).

### I.2 Mutation (fresh runs)

* **M50** (`tools/quality/mutation_m50.py`) on `981a67f`: **55 mutants, 55
  killed**, complete, 1114 s (baseline 195 passed). Covers: synchronous
  fingerprint, no guard, stale accept, currency/NPT ignored, scope filter
  dropped, unapproved page, fake citation, number/unit mismatch, stale semantic
  index, remote bypass, unverified shown as verified, late worker result,
  unsafe Qt order (3D disposal), diagnostics. The 4 W- (3D) mutants were re-run
  on `e48495c` against the hardened test: 4/4 killed. Equivalence: one mutant
  (`A-injection-quoted`) was found equivalent during the mission, then
  retargeted to a live snippet and killed (not declared equivalent).
  `mutation_m50.py` was edited during the earlier 40-mutant run; that run is
  superseded by the final complete run.
* **M49** on `981a67f`: 38/38, complete, 137 s.
* **M48** on `981a67f`: 44/44, complete, 1064 s (one snippet updated for the
  M50 status text: `E-status-hides-read-error`).

### I.3 Coverage, lint, gates

* CI product coverage (branch+line, 3.12 leg) on the code tip `e48495c`: **58.73 % (47505/80881, 206 files)**; M49: 58.53 %. Floor 45.50 % unchanged; no new exclusions.
* Lint debt 727 (ceiling 727 unchanged); ruff clean on changed files;
  exception gate passed; privacy gate 0 findings (1142 files) before each
  push; `git diff --check` clean.
* No new required dependency, no vector DB, no cache in Git; logs carry
  states and counts, never passages or whole questions.

## J. Git and CI

### J.1 State

| Item | Value |
|---|---|
| Branch | `arena/72010272-drill-master` |
| Base | `740a162b3c6e29cd2074b2083023fa3955fe087e` |
| Code commits | `741b473` §3, `7f2829b` gold freeze, `1ec2dca` retrieval v3, `7dc171a` injection paragraph, `f93d06e` gold gate, `cb2d5e0` §5, `3521f1a` §6–§8, `981a67f` §9 + screenshots, `e48495c` test isolation |
| **Code tip** | `e48495cd2843969e5e57d4ccdba2369586f581e8`, pushed, `git ls-remote` equal |
| Report commit | see the final reply (a report cannot contain its own SHA) |
| Force-push, history rewrite, merge, tag | none; `drill-Master` untouched at `e3fa42a` (unprotected, 0 rulesets, not changed) |

A sandbox reset mid-mission was recovered non-destructively (unshallow fetch,
temporary-index comparison, compare-and-swap `update-ref`); venv and Qt stub
libraries were regenerated; no work was lost; lost local result files were
regenerated post-hoc and are labelled as such.

### J.2 CI (exact SHAs)

| SHA | Source release gate | Windows release validation |
|---|---|---|
| `f93d06ef4f5379cdc85ab06bd2db7df921b2f7b9` | – | 40647262700 **failure** (3D native crash, G) |
| `cb2d5e0ad0ddecbbdc9e8a7f978db894a284a115` | 40648934821 success | 40648934759 success (no §8 fix) |
| `3521f1a3dc5e2528714ea8f2ba50383fca053955` | 40662124300 cancelled (superseded) | 40662124130 cancelled (superseded) |
| `981a67ff3d9863a49a768fc22db878b06db7e7fc` | 40663249338 **failure**: 1 test, the §8 disposal test counted other tests' widgets in full-suite order (3658 passed, 4 skipped); fixed in `e48495c` | 40663249667 success |
| **Code tip** `e48495cd2843969e5e57d4ccdba2369586f581e8` | **40670288118 success** (3.11, 3.12, 3.13; coverage 58.73 %, 47505/80881, 206 files, floor 45.50 %) | **40670288104 success** (job 122755018037): full regression suite incl. all M49/M50 tests and the 3D disposal tests, bundle + installer build, frozen smoke, silent install/run/uninstall PASS, installer **UNSIGNED** |

A CI runner is not Windows acceptance.

## K. BLOCKED / NOT RUN / PARTIAL

| Item | Status | Reason |
|---|---|---|
| Real generation, real embeddings, semantic retrieval quality | BLOCKED / NOT RUN | no local model; install needs owner authorisation |
| Semantic-enabled and failed-draft screenshots | NOT RUN / BLOCKED | same |
| Whole Analysis cycle off the GUI thread | PARTIAL | load/paint unchanged |
| 0 false answers on held-out | PARTIAL | N55, N59, N64 |
| Windows 3D crash closure | PARTIAL | intermittent; pre-fix commit also passed |
| Windows desktop, field, production use | NOT RUN | never claimed |

## L. Owner decisions

* Authorise (or not) installing Ollama and pulling specific weights (e.g.
  Apache-2.0 `qwen2.5:1.5b` / `qwen2.5:7b-instruct`, MIT `bge-m3`) so that
  §6 and cross-lingual retrieval can be measured.
* N55 (wrong well) and N59 (partial overlap): whether such questions should be
  refused (a policy, not tuned on held-out); N64 (Persian injection sentence
  quoted) needs a dev-measured detector change.
* Same-length in-place page edit detection (content hash per page).
* Branch protection for `drill-Master`; unchanged earlier items (PyMuPDF/OCR
  licences, signing, tag, Windows/field/production acceptance, money
  migration).
