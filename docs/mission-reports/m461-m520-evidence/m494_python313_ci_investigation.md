# M494 / M487 follow-up: the Python 3.13 CI timeouts (D88)

**PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

The workflow, the 60 min job timeout and the matrix are **unchanged** (D88). Nothing in this file changes CI, and a
TIMEOUT is never counted as a SUCCESS. Every failed or cancelled attempt is kept in the run history.

## 1. What happened in CI

The `source (3.13)` job of the Source release gate, all on `ubuntu-24.04` (GitHub API job timestamps):

| Commit | Run / attempt | 3.11 | 3.12 (coverage) | 3.13 |
|---|---|---|---|---|
| `246e7bf` | `45144294022` / 1 | 41m49s SUCCESS | 55m42s SUCCESS | 42m07s SUCCESS |
| `c2f6eaf` | `45163844874` / 1 | 41m22s SUCCESS | 55m55s SUCCESS | 43m00s SUCCESS |
| `ed68380` | `45345379551` / 1 | 45m23s SUCCESS | 58m35s SUCCESS | 47m27s SUCCESS |
| `e9244e8` | `45353234275` / 1 | 45m03s SUCCESS | **cancelled at 60 min (TIMEOUT)** | 53m53s SUCCESS |
| `e9244e8` | `45353234275` / 2 (re-run of the failed job only) | (attempt 1) | 56m19s SUCCESS | (attempt 1) |
| `e561072` | `45401906446` / 1 | 42m31s SUCCESS | 56m38s SUCCESS | 42m44s SUCCESS |
| `f7075a0` | `45578429792` / 1 | 40m11s SUCCESS | 54m50s SUCCESS | **cancelled at 60 min (TIMEOUT)** |
| `46c471c` | `45588540843` / 1 | 43m46s SUCCESS | 57m13s SUCCESS | **cancelled at 60 min (TIMEOUT)** |
| `46c471c` | `45588540843` / **2** (re-run of the failed job only) | (attempt 1) | (attempt 1) | **42m48s SUCCESS** |

Attempt 2 of `45588540843` was started with `gh run rerun 45588540843 --failed`. It re-ran only the 3.13 job, on the
same commit, same workflow and same lock, and that job succeeded in 42m48s (07:07:48–07:50:36 UTC, 2026-11-28). The
run now reports `conclusion: success` at `run_attempt: 2`. **Attempt 1 stays in the history as a TIMEOUT**, and this
report counts it as one.

The 3.13 job's step timings for attempt 2 show set-up, checkout, Qt libraries and the locked install finishing in
under one minute. The rest is the single "Verify exact source, dependencies, tests and wheel" step, which runs the
whole suite in one pytest process (`verify_release.py`).

## 2. Local reproduction on Python 3.13

Python 3.13 could not be installed through `uv python install` (TLS to the release-asset host fails in this sandbox).
A **diagnostic-only** interpreter was used instead. It is not part of the product, the lock or CI:

- python-build-standalone CPython **3.13.18** (trimmed), taken from the npm package `@rowstile/cli-linux-x64`, version 0.1.0-beta.5;
- the trimmed build lacks the stdlib `venv` and `ensurepip` packages (needed by `python -m build`), so those two were
  added from `python/cpython` tag `v3.13.18` (`Lib/venv`, `Lib/ensurepip`);
- a venv built with `uv venv`, holding `requirements-lock.txt` (sha256 `697124ea…edcfadd`) plus pytest 9.1.1,
  ruff 0.16.6, build 1.6.1, coverage 7.16.2 and pip (the CI tool versions).

**Full suite, sharded runner, 8 shards** (`m494_full_suite_py313_46c471c_dirty.txt`). The tree was `46c471c` plus the
uncommitted R4b / Erge changes that were then committed unchanged as `750e3cd`, so the run is the `750e3cd` tree:

- **6264 collected; 6258 passed; 0 failed; 4 skipped (NOT RUN); 2 errors.** Summed shard wall time 2789 s.
- The **2 errors** are both in `tests/test_release_boundary_imports.py`, and both come from the environment, not the
  code: `python -m build` failed with "No module named 'venv'" because the trimmed interpreter lacked the module.
  After `venv`/`ensurepip` were added (and pip, which CI's setup-python provides), that file passes **3/3** on 3.13.
- Taking that re-run into account: **6260 passed, 4 skipped, 0 failed** on Python 3.13.18.

**Per-file comparison** with the 3.11 profile at `44d3fb4` (`m487_suite_profile.md`): summed test time is 2701 s on
3.13 against 2608 s on 3.11 (+3.6 %, with 35 more tests). No file is pathologically slower. The largest top-25
differences are `test_m173_scalar_correction` (46.5 s against 40.8 s), `test_m215_scalar_correction_adversarial`
(94.9 s against 86.4 s) and `test_m300_m301_value_lineage` (71.5 s against 65.7 s). The M461–M485 test files take
1–14 s each on 3.13 (`test_m464` 14 s, `test_m467` 13 s, `test_m320d` 10 s, `test_m472` 8 s, `test_m475` 8 s).

## 3. Assessment

- **No 3.13-specific code regression was found.** The same commit (`46c471c`) passed 3.13 in 42m48s on re-run; the
  local 3.13 suite is green apart from the environment errors explained above; no M461–M485 test file is slow.
- The two 3.13 timeouts are therefore **intermittent**, like the earlier 3.12 timeout at `e9244e8` (attempt 1
  cancelled at 60 min, attempt 2 SUCCESS in 56m19s): either runner variance or an intermittent stall that the
  available evidence cannot identify. The job logs are not downloadable from this sandbox, and the only annotation is
  "exceeded the maximum execution time of 1h0m0s". No hang annotation was produced, so no single test passed the
  900 s watchdog (`TEST_HANG_SECONDS`).
- The D74 window leak (a closed `MainWindow`, about 9,700 widgets, stays alive in the single CI process) also
  applies to the two new journey tests (`test_m467`, `test_m472`). It is the same pre-existing pattern as
  `test_m375_main_window_journey` and every other module that reuses the `test_m70_selection_audit.window` fixture,
  and it behaves the same on 3.11 and 3.13. It is a contributor to memory growth in the single CI process, not a
  demonstrated cause of the timeouts. Per D74 / M237 the windows are not force-destroyed, because doing so crashed
  the garbage collector.
- **D88 stays an active risk.** 3.12 with coverage runs at 55–59 min against the 60 min limit, and 3.13 has now
  exceeded the limit twice. The remedy (split, shard or a longer timeout) is an owner decision (D88 / R2) and is not
  taken here. No safe optimisation was identified that would cut minutes without losing coverage, so none was made.
