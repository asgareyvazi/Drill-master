# CI Operationalization — Verification Phase (2026-09-11)

Narrow operational-verification phase. Objective: move the CI workflow from
"exists locally" to "installed remotely with an independently observable
GitHub Actions result." **No production-code changes intended** beyond the
CI workflow itself. Data-integrity work (schematic no-fabrication, inventory
zero semantics) was completed in the prior phase and is unchanged here.

## A. Repository identity

| Item | Value |
| --- | --- |
| Branch | `arena/01a085e0-drill-master` |
| HEAD (local) | workflow commit — "Add blocking CI workflow …" (single unpushed, blocked commit) |
| Doc commit | this audit (pushed; on the remote branch) |
| Zero-semantics commit | `5e92732` — "Fix schematic no-fabrication and inventory zero semantics" (recreation of the session-reset-lost `0bdf364`; identical tree; pushed) |
| Base | `7936a59` (remote branch head at session start) |
| Remote branch head | this audit's commit after this phase's push (was `7936a59`) |
| Working tree | clean (`git status` = nothing to commit; `git diff --check` clean) |
| `.github/workflows/ci.yml` | tracked locally in the workflow commit; **NOT on remote** (push blocked by missing `workflows` permission) |

Commit topology (blocking commit kept last so everything else reaches remote):
`7936a59` → `5e92732` (pushed) → this audit (pushed) → workflow commit (blocked, workflow file).

Session-reset note: local commits do not survive session resets (working
tree does). `0bdf364`/`7936a59` did not exist as local objects at session
start; `7936a59` was re-fetched from remote, HEAD realigned to it via
`git reset`, and the persisted working tree (identical to `0bdf364`) was
recommitted as `5e92732`. Verified byte-for-byte via the recorded file set.

## B. Local verification (executed)

| Metric | Value |
| --- | --- |
| Python | 3.11.2 (venv from `requirements-lock.txt` + pytest + ruff==0.16.6) |
| pytest | 9.1.1 |
| Ruff | 0.16.6 |
| Collected | 848 |
| Passed | 844 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 4 (all legitimate opt-ins — see below) |
| XFailed | 0 |
| XPassed | 0 |
| E722 | 0 |
| F821 | 0 |
| Lint debt | 5489 (== ceiling `.github/ruff-debt-ceiling.txt`) |
| Compile | `compileall core dialogs tabs tests` + `py_compile app.py run.py main_window.py verify_release.py` → OK |

Run command (headless):
`export QT_QPA_PLATFORM=offscreen LD_LIBRARY_PATH=/home/user/qt-libs && .venv/bin/python -m pytest -ra -p no:cacheprovider` (~151s).

The 4 skips (unchanged, opt-in only):
- `test_ddr_acceptance.py` — `DRILLMASTER_TEST_DDR_XLSX` unset
- `test_ddr_acceptance.py` — `DRILLMASTER_TEST_DDR_PDF` unset
- `test_mineru_real_integration.py` — `MINERU_INTEGRATION_INPUT` unset
- `test_packaging_smoke.py` — Windows bundle unavailable

## C. CI workflow audit

Workflow: `.github/workflows/ci.yml`, name `CI`.

- Triggers: `push` (branches `**`) and `pull_request`. Deterministic, blocking.
- Matrix: Python `3.10, 3.11, 3.12, 3.13` (`fail-fast: false`) — matches
  `pyproject.toml` `requires-python = ">=3.10,<3.14"` and the lock file
  header ("Reproducible runtime lock for Python 3.10-3.13").
- OS: `ubuntu-latest`.
- Qt libs: `libgl1 libegl1 libxkbcommon0 libdbus-1-3 libfontconfig1` via apt —
  the real system libraries PySide6 needs. Headless via `QT_QPA_PLATFORM=offscreen`
  (env, top-level). No test skips to mask GUI.
- Dependencies: `requirements-lock.txt` (pinned runtime) + `pytest` +
  `ruff==0.16.6` (tooling intentionally outside the lock).
- Compile: `compileall -q core dialogs tabs tests` + `py_compile` of entrypoints.
- Ruff defect gate (blocking): `--select E722,F821` over core/dialogs/tabs/
  main_window.py/app.py/tests — must be zero.
- Debt ratchet (blocking): `COUNT = ruff check --statistics core dialogs tabs
  tests | awk '{s+=$1} END {print s+0}'`; fails if `COUNT > $(cat
  .github/ruff-debt-ceiling.txt)` (== 5489). Ceiling may only shrink.
- Test: `python -m pytest -ra --tb=short` (full suite, offscreen).
- **No `continue-on-error`** anywhere. All required gates block.
- Security: added least-privilege `permissions: contents: read` at top level
  (this phase). No secrets used, no token printing, no PR-input interpolation
  into shell, no `write-all`.

| Gate | Local | Workflow configured | Remote observed |
| --- | --- | --- | --- |
| Python 3.10 | n/a (local 3.11) | yes | NOT OBSERVED |
| Python 3.11 | PASS | yes | NOT OBSERVED |
| Python 3.12 | n/a | yes | NOT OBSERVED |
| Python 3.13 | n/a | yes | NOT OBSERVED |
| Compile | PASS | yes | NOT OBSERVED |
| E722 | 0 | yes (blocking) | NOT OBSERVED |
| F821 | 0 | yes (blocking) | NOT OBSERVED |
| Debt ratchet | 5489 ≤ 5489 | yes (blocking) | NOT OBSERVED |
| Full pytest | 844/4/0/0 | yes | NOT OBSERVED |

## D. Remote Actions

**BLOCKED — no real GitHub Actions execution observed.**

- Authentication is valid this session (`gh auth status` → logged in as
  `arena-ai-coding-agent[bot]` via GH_TOKEN). Auth is NOT the blocker.
- Push of the workflow commit is rejected:
  `! [remote rejected] … (refusing to allow a GitHub App to create or update
  workflow .github/workflows/ci.yml without workflows permission)`.
- The non-workflow commit `5e92732` pushed successfully (remote branch head is
  now `5e92732`), isolating the blocker to the workflow file only.
- `gh run list` / `gh api …/actions/runs` show only GitHub's managed
  "Dependency Graph" workflow has ever run (total_count = 2, unrelated). Our
  `CI` workflow has never executed because `ci.yml` has never reached remote.

**Root cause: the GitHub App installation token lacks the `workflows` write
permission.** This is a permission grant the user must make in Arena's GitHub
connection; it cannot be resolved from inside the sandbox and no credential
may be requested or stored.

## E. Changes this phase

- `.github/workflows/ci.yml` — new (committed `1e36be3`; adds least-privilege
  `permissions: contents: read`; otherwise the workflow authored in the prior
  session, unchanged in its gates).
- `docs/audits/2026-09-11_CI_OPERATIONALIZATION.md` — this document.

No production code changed.

## F. Final gate

**BLOCKED** — the CI workflow is authored, locally validated (YAML parses;
matrix/deps/gates verified against repo metadata), and committed, but it could
not be installed on the remote and therefore produced no observable GitHub
Actions run. Local success is NOT CI PASS.

Distinct blocker classification:
- GitHub authentication: OK (not blocked).
- `workflows` write permission: **BLOCKED** — token cannot push `ci.yml`.

## G. Next phase

CI is not yet PASS. Recommendation: **resolve CI first** — the user grants the
`workflows` permission (or reconnects GitHub in Arena with that scope), after
which push `1e36be3`, then observe the first real Actions run across the 3.10–
3.13 matrix and record run ID / SHA / per-job results. Only once CI is
independently PASS should the **Wellbore / schema v3 foundation** phase begin.
