# M49 — Offline Knowledge Assistant with page-level citations, hybrid retrieval, local-model adapter and analysis-cache correctness

Branch `arena/72010272-drill-master`, base `e83fb6ddd108078aa58fbc906031ccf9c5ed835e`
(the M48 report tip; M48 code tip `0b298b8`). Status values: PASS / FAIL / PARTIAL /
BLOCKED / NOT RUN. All data used in this mission is synthetic
(`tests/m49_knowledge_fixtures.py`: wells `SYN-*`, documents `SYN-KA-01 …`,
`SYN-KB-02 …`, `SYN-INJECTION …`). No real DDR, real document, real well or real
money value was opened, used or reproduced. No language model or embedding
model was installed, downloaded or run. No EXE, installer or release bundle was
built by this mission (the Windows CI runner builds its own, see G). The
application stays **UNSIGNED**. Nothing in this report is release approval,
Windows desktop acceptance or field validation.

## A. Summary

| Item | Status | Evidence |
|---|---|---|
| Start audit (Git, remote, baselines 3356/0/4, mutation 44/44, coverage 57.60 %) | PASS | G.1 |
| Deep pipeline audit (import → pages → review → links → search → answer) | PASS | B.1 |
| M48 cache P0: code-only, NPT-only, currency-only and count/sum-preserving edits change the fingerprint | PASS | B.4, F (group A) |
| Five mandatory cache tests (currency, NPT code, Refresh parity, no scope leak, read error never cached) | PASS (real Analysis page, Qt offscreen) | F.1 |
| Read cost of the new fingerprint measured | PASS (measured; a limitation remains, H) | B.4 |
| Knowledge Assistant inside Documents (ask FA/EN, scope, cited answer, open the page, clear on change, insufficient evidence) | PASS (Qt offscreen, Linux) | E |
| Hybrid retrieval: FTS5 + glossary + trigram, optional semantic, RRF k=60, scope before ranking, dedupe, provenance | PASS | B.2 |
| "Semantic retrieval unavailable" while keyword retrieval keeps working | PASS | E, screenshots |
| Decision matrix (SmartDocs-RAG, RAG Cookbook, Ollama, BGE-M3, lighter options) | PASS | C |
| Model adapter: loopback only, no keys, no downloads, timeout, cancel, model-missing state | PASS (stub server + real closed port) | B.3 |
| Real local generation / real embeddings | **BLOCKED / NOT RUN** (no model installed; model hosts unreachable from the sandbox) | I |
| Citations map to retrieved evidence; fabricated citations rejected | PASS | B.3, F (group C), mutants |
| Document text is untrusted (injection never executed or obeyed) | PASS (synthetic tests) | F (group C/E) |
| Storage: versioned chunker, no stale results after edit/delete/scope change, unapproved pages excluded, no index in Git | PASS | B.2, F (group B) |
| ≥ 6 real screenshots | PASS: 9 (Qt offscreen, Linux) | E.2 |
| Gold QA ≥ 30 FA/EN questions with real metrics | PASS: 40 questions; 37/40 all checks; 0 false answers | D |
| End-to-end workflow on a file DB with SQL oracles | PASS: 14/14 (Qt offscreen) | F.2 |
| Fresh M49 mutation tool | PASS: 38 mutants, 38 killed, complete | F.4 |
| M48 mutation re-run (no regression of M48 contracts) | PASS: 44/44 | F.4 |
| Full suite on the exact code tip | PASS: 3540 passed, 0 failed, 4 skipped | F.3 |
| CI on the exact code tip | PASS: Source 40501999949 and Windows 40501999951 success on `8cd52a0` | G.2 |
| Windows desktop acceptance | NOT RUN (never claimed) | I |

## B. Architecture

### B.1 Pipeline map (code-based audit)

| Stage | Implementation | Stored data / approval | UI callers | Limits found | What M49 adds |
|---|---|---|---|---|---|
| Import | `core/document_library.py` `import_reviewed` | `documents` (sha256 unique, `page_count` = source pages) | Documents → Import | — | nothing (reused) |
| Pages / review | `document_pages.review_status` ∈ extracted / approved / edited / rejected; a page rejected at review is **not stored** | edited text keeps its page id and is marked `edited` | review dialog | OCR text is never stored silently (M44) | only `extracted`, `approved`, `edited` pages are answerable |
| Links | `document_links` (well, optional report), user-confirmed | `linked_by`, `linked_at` | Library link dialog | names are never used to infer links | scope "well" / "daily report" uses **only** these rows |
| Search | M44 FTS search over pages | — | Library && Search | phrase-level, no ranking fusion; the M44 index could go stale after delete + re-import (fixed, `corpus_signature` includes the latest document audit id) | — |
| Retrieval | **new** `core/knowledge_retrieval.py` | in-memory FTS5 index rebuilt from a read-only snapshot; optional embedding cache file `<data dir>/knowledge_cache/` (gitignored) | Knowledge Assistant | — | hybrid ranked lists + RRF, scope filter before ranking |
| Answer | **new** `core/knowledge_answer.py` | nothing stored | Knowledge Assistant | — | extractive cited answer; model answer only when every citation and number verifies |
| Model | **new** `core/local_llm.py` | nothing stored | model box in the assistant | — | loopback-only Ollama client |

Distinct states (never collapsed into an empty answer): `no_documents`,
`invalid_query`, `no_evidence` (with what was found / not found, whether the
scope was limited, what was unavailable), `read_error`, `model_unavailable`
(extractive answer kept), `error`, `cancelled`, `stale`, `ready`.

### B.2 Retrieval

* Answerable = page status in {extracted, approved, edited}; the scope filter
  (all / well / daily report / document, from confirmed links only) is applied
  **before** ranking.
* Ranked lists: FTS5 over normalised text (`core/search_normalization.py`,
  Persian/Arabic letters, digits), a small glossary list, a character-trigram
  list; a semantic list only when a local embedding model is configured.
* Fusion: Reciprocal Rank Fusion, k = 60, documented and unit-tested; at most
  two passages per page; coverage of the question's informative terms below
  0.6 gives `no_evidence`; a size designation in the question (e.g. 17-1/2 in)
  that no passage contains caps coverage at 0.5 (`RETRIEVAL_VERSION = 2`).
* Chunks: `CHUNKER_VERSION = 1`, target 700 characters, each carrying
  `document_id`, filename, page number, stable page id, character span, text
  version (sha256 of chunker version + text), scope and review status.
* Freshness: `corpus_signature` = (normalisation, chunker, retrieval versions,
  every page's id/status/length/hash, the latest document audit id, a digest
  of links). Any edit, delete, re-import or link change rebuilds the index;
  the embedding cache is keyed by model + chunker version + chunk sha, so a
  model or dimension change never collides; a partially built semantic index
  is never reported ready (`mark_complete`).
* The embedding cache refuses to open any SQLite file that holds other tables
  (it can never write into the application DB).

### B.3 Answers and the model adapter

* Evidence, retrieved context and the generated answer are separate objects.
* Extractive answer (always available): `• «sentence» [S#]`, sentences taken
  verbatim from evidence; conflicting values from different documents are both
  shown with a conflict note.
* A model answer is accepted only if every sentence cites `[S#]` labels that
  exist, every number appears in the cited evidence, it is non-empty, contains
  no tool call and does not repeat instruction-like text; otherwise it is
  rejected (never marked grounded) and the extractive answer is shown.
* Instruction-like document text is flagged per page ("treated as document
  data only") and never executed or obeyed.
* Adapter (`core/local_llm.py`, stdlib only): URL must be `127.0.0.1`,
  `localhost` or `::1` and must resolve to loopback; no proxy, no redirects;
  cloud/remote models (`:cloud`, `remote_model`, `remote_host`) are refused in
  the model list and in every streamed chunk; NDJSON stream with a 180 s
  deadline and an 8000-character cap; `status()` never raises.
* **Windows fixes found by Windows CI (run 40486602573):**
  1. `cancel()` used to close the `http.client` response from the UI thread,
     which waited for the reader's buffer lock until the server sent more
     data (~10 s on Windows). Cancel now shuts down and closes only the
     detached OS socket handle and never waits for the worker.
  2. Windows retries the SYN to a closed loopback port (~2 s), so a short
     connect timeout said `timeout`; a loopback connection that is never
     accepted is now `not_running`, a listening-but-silent server stays
     `timeout`.

### B.4 M48 analysis-cache P0

`core/analysis_evidence.data_revision` (version 2) digests every column of
every in-scope row (blake2b-128, primary-key order, `repr` of each value) of
the nine tables the Analysis page reads: well, wellbores, sections, daily
reports, drilling parameters, mud, 24-h time logs, costs, safety. The M48
summary (counts, max ids, `updated_at`, sums) missed an NPT-code-only edit
(`TimeLog24H` has no `updated_at`), currency-only SQL edits, swapped values and
a delete + re-insert reusing the top rowid. No schema change; old databases
work unchanged.

Read cost (synthetic well, temporary file DB, Linux sandbox, 2 CPUs, median of
30, one call per Analysis update cycle):

| 24-h time-log rows of the well | M48 summary | M49 digest |
|---|---|---|
| 1 024 | 1.57 ms | 7.36 ms |
| 4 096 | 2.43 ms | 23.73 ms (max 55 ms) |
| 16 384 | 5.26 ms | 86.44 ms (max 125 ms) |

A raw-driver-row variant was prototyped (−38 % at 16 k rows) and not adopted:
the floor is SQLite reading every row, and it adds compiled literal SQL.
Moving the fingerprint off the GUI thread is the real fix and is left open (H).

## C. Libraries and models (decision matrix)

| Candidate | Code licence | Weights licence | FA/EN | Offline / Windows | Size / CPU | Value over FTS5 | Decision |
|---|---|---|---|---|---|---|---|
| SQLite FTS5 + normalisation + RRF (stdlib) | Python/SQLite (PSF / public domain) | — | FA/EN via normalisation | yes / yes | none added | baseline | **adopted** (core) |
| Ollama (`ollama/ollama`) | MIT | per model | per model | yes (local server; set `OLLAMA_NO_CLOUD=1`) / yes | user-installed | generation, embeddings | **optional**, loopback HTTP only, no Python dependency |
| BGE-M3 (`FlagOpen/FlagEmbedding`) | MIT | MIT | strong multilingual | yes / yes | 568 M params, 2.27 GB FP32; Ollama `bge-m3` 1.2 GB | semantic recall | documented option via Ollama; **NOT RUN** |
| multilingual-e5-small | MIT | MIT | 100 languages (lower quality on low-resource) | yes / yes | 118 M params, ~470 MB FP32 | lighter semantic option | documented option; **NOT RUN** |
| qwen2.5:1.5b (example answer model) | — | Apache-2.0 | multilingual | via Ollama | 986 MB (Ollama) | wording only; extractive answers work without it | named as the setup example |
| qwen2.5:3b | — | **Qwen Research Licence (non-commercial)** | multilingual | via Ollama | 1.9 GB | — | **not recommended**; was the first example in the guidance, replaced in `8cd52a0` |
| SmartDocs-Multilingual-Agentic-RAG | MIT (36 stars) | — | — | needs LangChain/LangGraph, OpenAI client, pgvector, Redis, presidio, ragas … | heavy | none for an offline desktop app | rejected |
| RAG-with-Python-Cookbook (`polzerdo55862`) | **no licence** | — | — | — | — | reference only; no code reused | rejected (licence) |
| sentence-transformers / fastembed / onnxruntime / llama-cpp-python | Apache-2.0 / Apache-2.0 / MIT / MIT | — | — | yes | large wheels | would add native dependencies | not added (no measured value over the optional Ollama path) |

Sources: GitHub repository metadata (`gh api`), Ollama `docs/api.md` at
v0.40.11, model cards (BAAI bge-m3, intfloat multilingual-e5-small), Ollama
library pages (bge-m3, qwen2.5). No weights, caches or indexes are in Git; no
dependency was added (`requirements*.txt` unchanged).

## D. Gold QA (40 synthetic questions, `tests/m49_gold_questions.py`)

Corpus: 9 documents, 14 stored pages, 26 chunks; 28 English, 9 Persian, 3
mixed questions; 29 answerable, 11 unanswerable. Measured by
`tools/quality/knowledge_eval_m49.py` on the final tree (Linux).

| Metric | Value |
|---|---|
| Recall@5 (hybrid) | 1.0 (complete-evidence recall@5 1.0) |
| MRR (hybrid) | 0.9483 (first correct rank: 26 × rank 1, 3 × rank 2) |
| Recall@5, lexical only | 1.0 |
| Recall@5, M44 library search on the same questions | 0 / 22 (phrase search; not built for questions) |
| State accuracy | 0.95 |
| Unanswerable correctly refused | 11 / 11; false answers 0 |
| Answer contains the expected value | 25 / 28 |
| Forbidden value absent | 10 / 10 |
| Conflicts detected | 2 / 2 |
| Injection pages flagged, instruction not followed | 2 / 2 |
| Scope violations / identity (doc, page) errors / open errors / unapproved leaks | 0 / 0 / 0 / 0 (99 evidence items) |
| Index build / answer latency | 6.9 ms / median 3.19 ms, max 6.9 ms |
| Peak RSS of the eval process | 69.3 MB (Linux; NOT MEASURED on Windows) |

By category (all checks passing): exact 3/3, paraphrase 3/4, Arabic letters
2/2, Persian 3/3, English 2/2, mixed 2/3, cross-lingual 1/2, scoped 6/6,
scoped no-evidence 1/1, empty scope 1/1, page 1/1, missing page 1/1, multi-doc
1/1, edited page 1/1, unapproved 1/1, not in corpus 4/4, wrong size 2/2,
injection 2/2.

Failures (reported, not tuned away): **Q09** (paraphrase "90 seconds": refused
although the page answers it), **Q16** (mixed FA/EN: "differential" missing
from the answer), **Q19** (cross-lingual: refused; the value is only in the
Persian page). These are honest misses of a lexical retriever without
embeddings. Before the size rule (`f0313d0`) Q39/Q40 gave **2 false answers**
(a different hole size's value); now refused.

Recall@5 is a weak discriminator on a 26-chunk corpus; the refusal and
false-answer metrics carry more information.

## E. UI

### E.1 Paths

Documents → **Knowledge Assistant** tab (next to "Library && Search"):
scope selector (All approved documents / Well / Daily report / Document),
question box, Ask / Cancel / Retry / Clear, "Write the answer with the local
model" (disabled until a local model checks ready), model box (server,
answer model, embedding model, Check model, Build semantic index), answer
pane, notes, evidence table (source, document, page, review, match, found
by, passage), **Open source in library** (or click `[S#]`) → switches to
Library && Search with the cited page and the exact span selected. States:
Searching / Retrieving / Generating / Ready / No evidence / Model unavailable
/ Error / Cancelled / Stale. A scope, target or question change clears the
answer; late worker results are dropped by a generation guard.

### E.2 Screenshots (real app, synthetic data, Qt offscreen on Linux, 1600×1150; `tools/screenshots/capture_m49.py`, pinned in `tools/privacy/policy.json`)

| File | Shows |
|---|---|
| `m49-screenshots/m49_assistant_no_documents.png` | empty library state |
| `m49-screenshots/m49_library_search_results.png` | library search "pump liner" → 2 pages |
| `m49-screenshots/m49_multi_source_answer.png` | answer citing S1 + S3 with the conflict note (1.25 vs 1.32 sg) |
| `m49-screenshots/m49_source_opened.png` | cited span of `mud program rev2` p1 selected in the library |
| `m49-screenshots/m49_model_unavailable.png` | real check, connection refused, setup guidance, extractive answer kept |
| `m49-screenshots/m49_insufficient_evidence.png` | refusal with found / not found / unavailable lines |
| `m49-screenshots/m49_persian_answer.png` | Persian question and right-to-left answer |
| `m49-screenshots/m49_injection_flagged.png` | answer Ready; S2 flagged as instruction-like, not obeyed |
| `m49-screenshots/m49_scope_well.png` | well scope: only the linked note is cited |

Emoji icons render as boxes (no emoji font in the sandbox). The status-bar
clock is part of every capture.

## F. Tests

### F.1 Groups and counts

Collected: baseline 3360 (3356 passed + 4 skipped) → **3544** (+184):

| File | Tests | Group |
|---|---|---|
| `tests/test_m49_cache_integrity.py` | 16 | A cache (core) |
| `tests/m48_ui_child.py` (+5 scenarios, collected by `test_m48_analysis_ui.py` 42 → 47) | 5 | A cache (real Analysis page): currency-only, NPT-code-only, Refresh parity, scope leak, read error never cached or shown as No data |
| `tests/test_m49_knowledge_retrieval.py` | 37 | B retrieval / storage |
| `tests/test_m49_knowledge_answer.py` | 48 | C answers / citations / injection |
| `tests/test_m49_knowledge_ui.py` | 23 | D UI (Qt offscreen) |
| `tests/test_m49_local_llm.py` | 50 | E adapter security / compatibility |
| `tests/test_m49_knowledge_gold.py` | 5 | gold set + POSIX-only import guard |

No existing test was removed, skipped or weakened; skips are the four
pre-existing opt-in ones (`test_ddr_acceptance.py:33` ×2,
`test_mineru_real_integration.py:26`, `test_packaging_smoke.py:218`). Stubs:
`tests/m49_fake_ollama.py` is a real loopback HTTP server standing in for
Ollama (external dependency only); it is **not** evidence of answer quality.

### F.2 End-to-end workflow (`tools/quality/workflow_m49.py`, 14/14 PASS)

Temporary file DB, real users (engineer imports, read-only viewer asks), real
Documents tab; every expectation read with an independent `sqlite3`
connection: every evidence passage equals the stored approved page text at
its span; every `[S#]` names a retrieved passage; both conflicting values
shown; opening a citation selects exactly the stored span; well scope cites
only linked documents; a rejected page is not stored and never evidence;
asking wrote nothing (schema + all 67 table row counts); states for Persian,
unknown identifier and unknown size; real closed-port model check disables
the model option and answers stay extractive; a deleted cited document is
never cited again; `PRAGMA integrity_check` ok; no cache in the repository.

### F.3 Full suite on the final code tree (`8cd52a0`)

`1856 passed, 2 skipped` + `1684 passed, 2 skipped` = **3540 passed, 0 failed,
4 skipped** (two foreground halves, Linux, Python 3.11.2, PySide6 6.8.1.1
offscreen, SQLite 3.40.1, pytest 9.1.1).

### F.4 Mutation

* **M49** (`tools/quality/mutation_m49.py`, fresh run on `8cd52a0`): **38
  mutants, 38 killed**, 0 equivalent, 0 invalid, 123 s. Covers scope filter
  dropped, approval ignored, wrong page id, fake citation accepted, stale
  index after a document change, remote host / proxy / cloud model allowed,
  error turned into "no evidence", injection ignored, stale scope result,
  NPT- and currency-only changes undetected, tool calls accepted, cancel
  closing the response / leaving the handle open, connect timeout misread.
  History: 27/33 → 34/35 → 35/35 → 37/38 → 38/38. The 37/38 survivor
  (`U-generation-guard-removed`) had been killed only through a race that the
  old blocking cancel created; a deterministic test now kills it 5/5.
* **M48** (`tools/quality/mutation_m48.py`, fresh run on `6fb8420`, whose
  analysis code is identical to `8cd52a0`): **44/44 killed**, baseline 206
  passed, 1001 s.

### F.5 Coverage, lint, gates

* CI product coverage (branch+line, 3.12 leg): 58.52 % (46948/80232) on
  `41e2485`; **58.53 % (46964/80243) on the code tip `8cd52a0`**. M48: 57.60 %. Floor
  45.50 % unchanged.
* Local focused coverage of the new modules from the M49 tests (Linux):
  `knowledge_answer` 95 %, `knowledge_retrieval` 96 %, `local_llm` 83 %,
  `tabs/knowledge_assistant.py` 83 %; 90 % overall.
* Lint debt 727 (ceiling 727 unchanged); ruff clean on changed files;
  exception gate passed with 9 new `# silent-ok: <reason>` markers and the
  ceiling unchanged; data-layer guard: 3 new allowlist entries (the in-memory
  FTS index and the separate embedding cache file) plus a guard that the
  cache refuses the application DB; `git diff --check` clean.

### Defects fixed along the way

M48 cache blind spots (B.4); M44 index stale after delete + re-import with a
reused page id; an "insufficient evidence" message that claimed terms were
absent when they were present; wrong-size answers (Q39/Q40); a read-only DB
path; a `sqlite3` context manager that committed but did not close its
connection; privacy-scanner hits on example URL strings; Windows-only
`resource` import (`5617c67`); Windows cancel blocking the UI thread and the
slow-refusal misclassification (`6fb8420`); research-only example model in the
setup guidance (`8cd52a0`).

## G. Git and CI

### G.1 State

| Item | Value |
|---|---|
| Branch | `arena/72010272-drill-master` (upstream `origin/arena/72010272-drill-master`) |
| Base | `e83fb6ddd108078aa58fbc906031ccf9c5ed835e`, 0/0 at start, clean |
| Code commits | `c0d663c` cache P0, `f0313d0` knowledge core, `41e2485` panel + gates, `5617c67` Windows `resource`, `5ef4b07` workflow, `6fb8420` Windows cancel/status, `8cd52a0` guidance model |
| **Code tip** | `8cd52a0fb79d14d50f99cf32d30b875e54a05b92`, pushed, `git ls-remote` equal |
| Report commit | see the final reply (a report cannot contain its own SHA) |
| Force-push, history rewrite, merge, tag | none; `drill-Master` and `main` untouched |
| Branch protection | `drill-Master` is unprotected with 0 rulesets (checked at start); not changed (owner decision) |

Two sandbox resets were recovered non-destructively (fetch, temporary-index
comparison showing the working tree byte-identical to the remote tip,
compare-and-swap `update-ref`); no work was lost.

### G.2 CI (exact SHAs)

| SHA | Source release gate | Windows release validation |
|---|---|---|
| `c0d663c6bf059a41750d9dd88cf734dfc097ddf9` | success | success |
| `f0313d003b3ada59c14fb6f16a92de77d048fe52` | 40478508102 **failure** (repo-wide exception and data-layer guards; fixed in `41e2485`) | 40478508104 success |
| `41e24854623c54f617e9c80f88fa537a1a888e9e` | 40483073772 success (coverage 58.52 %) | 40483073550 **failure**: collection error, module-level `import resource` in the eval tool (POSIX only); fixed in `5617c67` with a test that imports all M49 modules with POSIX-only modules blocked |
| `5617c67ebc25c5feaceaa3813b65965c08d1c3a2` | 40486251819 cancelled (superseded) | 40486251709 cancelled (superseded) |
| `5ef4b07317578d26a43187e4acb75852633578ad` | 40486602526 success | 40486602573 **failure**: two real adapter defects on Windows (cancel ~10 s, closed port → `timeout`); fixed in `6fb8420` |
| `6fb842040fc662d62aafc53bdbb703c3dc196992` | 40499433603 success | 40499433606 **failure**: native access violation in the **M46** test `test_trajectory_3d_lifecycle_m46.py::test_many_requests_in_one_event_cycle_draw_once_and_leave_no_timer`, which runs **before** every M48/M49 test file; same crash family as run 40168089020 (`780880f`, 2026-10-25, before M49) in `test_trajectory_3d.py`; classified pre-existing intermittent |
| **Code tip** `8cd52a0fb79d14d50f99cf32d30b875e54a05b92` | **40501999949 success** (3.11, 3.12, 3.13; coverage 58.53 %, 46964/80243, 205 files, floor 45.50 %) | **40501999951 success** (job 122181719890): full regression suite incl. all M49 tests, bundle + installer build, frozen smoke, silent install/run/uninstall PASS, installer **UNSIGNED** |

The early Windows death on `41e2485` produced no per-test annotation in the
job; a local reproduction of `packaging/junit_report.py --annotations` on a
collection error emits correct `::error` lines, so the cause is **NOT
DETERMINED** (job logs are on storage unreachable from the sandbox). Later
failures were annotated correctly. A CI runner is not Windows acceptance.

## H. Security, privacy and limitations

* No cloud API, key, telemetry or runtime download; the only network use is
  an optional HTTP client to a loopback address. Logs record states and
  counts, never full document text or questions. Synthetic data only; 9 PNGs
  pinned; privacy gate 0 findings on 1118 files before every push.
* **Limitations:**
  * the cache fingerprint costs ~5 µs per row on the GUI thread once per
    Analysis update cycle (86 ms at 16 k time-log rows, B.4);
  * the size-designation parser can produce false positives, which only make
    answers stricter (refusals), never looser;
  * identifier terms are weighted softly; two near-threshold refusals score
    coverage 0.57 / 0.59;
  * a yes/no question containing a wrong number is answered by quoting the
    real value, not with "no";
  * normalisation does not fold every spelling variant; Q09, Q16, Q19 miss;
  * Recall@5 is a weak discriminator on this corpus; M44 library search
    finds 0/22 question-form queries (it is a phrase search);
  * peak RSS is NOT MEASURED on Windows;
  * the currency-only UI scenario also passes on the M48 code (the core test
    fails there); Q37–Q40 were added late in the mission;
  * all UI evidence is Qt offscreen on Linux.
* `config/ai_models.json` and `DEPLOYMENT.md` (older AI-import feature, not
  M49) still name `qwen2.5:3b`, which is research-only; not changed (model
  licence choice is an owner decision).

## I. BLOCKED / NOT RUN

| Item | Status | Reason |
|---|---|---|
| Real local generation (any LLM) | BLOCKED / NOT RUN | no model installed; Ollama and model hosts unreachable from the sandbox; a real check against 127.0.0.1:11434 gives ConnectionRefused |
| Real embeddings / semantic retrieval quality | BLOCKED / NOT RUN | same |
| Answer quality of a real model | NOT RUN | the stub server proves guards only |
| Windows desktop use of the assistant | NOT RUN | CI runner only; never claimed |
| Field / production use | NOT RUN | — |

## J. Owner decisions

* Which local models (if any) to approve, by weights licence (e.g. Apache-2.0
  `qwen2.5:1.5b`, MIT `bge-m3`); whether to change the AI-import defaults
  that name `qwen2.5:3b`.
* Whether to move the analysis fingerprint off the GUI thread.
* Branch protection for `drill-Master` (unprotected, 0 rulesets).
* Unchanged from earlier missions: PyMuPDF (AGPL) / OCR licences, signing,
  release tag or approval, Windows / field / production acceptance, money
  migration.
