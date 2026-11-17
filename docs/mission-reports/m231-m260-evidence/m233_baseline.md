# M233 – Repository and environment baseline (before substantive M231–M260 changes)

Recorded 2026-11-16/17 in the Arena sandbox. Commands: `git rev-parse`, `git status --short --untracked-files=all`,
`git ls-remote origin`, `git stash list`, `git worktree list --porcelain`, `git branch -a`, `git tag`,
`gh api repos/asgareyvazi/Drill-master/branches/<branch>`.

## Arrival state (fifth sandbox reset)

- The checkout had been re-cloned: reflog `clone: from https://github.com/asgareyvazi/Drill-master.git` then
  `checkout: moving from drill-Master to arena/72010272-drill-master`; HEAD = graft base
  `4336ea357fc1ae28ccca228cdf7873697cc4cd84`; `.venv`, the Qt stub libraries and the git-ignored `htmlcov/` were gone.
- The unpushed report commit `0d824e4` **did not exist** (`git cat-file -t 0d824e4` → not a valid object).
- The tracked work tree held the files of `2764071` plus **20 untracked files** = exactly the content of `0d824e4`
  (the M201–M230 report, 509 lines, no placeholders; `full_suite_2764071_local_nocov.log.txt`;
  `load_samples_2764071_local_nocov.txt`; `mutation_final_2764071/` 16 result files, all `complete=True`, totals
  1086 / 1082 killed / 3 survived / 1 equivalent / 0 invalid, and `progress_2764071.txt`).
- Recovery without discarding anything: `git fetch`; `git update-ref refs/heads/arena/72010272-drill-master
  2764071… 4336ea3…` (compare-and-swap); `git read-tree HEAD`; `git branch --set-upstream-to`.

## M231 delivery

- `git push origin arena/72010272-drill-master` (fast-forward `2764071..eaa003f`) succeeded with the sandbox's
  configured GitHub integration (no credential typed, printed or stored; remote URL unchanged).
- Independent verification: `git ls-remote origin arena/72010272-drill-master` →
  `eaa003f2e94d1637116958f00218eb490cd7d973`; REST `branches/arena/72010272-drill-master` → same SHA, parent
  `27640711eb086496fe961e73c2908768d44de8b8`; `git merge-base --is-ancestor 2764071 eaa003f` → true.

## Baseline after M231

| Item | Value |
|---|---|
| Branch | `arena/72010272-drill-master` (the only branch written) |
| Local HEAD = remote | `eaa003f2e94d1637116958f00218eb490cd7d973` |
| Commits between them | none |
| Work tree | clean (`git status --short --untracked-files=all` empty) before the M232 edits |
| Stash / worktrees / tags | 0 / 1 (`/home/user/Drill-master`, no detached HEAD) / 0 |
| Local branches | `arena/72010272-drill-master`, `drill-Master` (clone default, untouched) |
| `drill-Master` | `e3fa42a3257e981d9bdf9d012c97919e3352a53a` (unchanged; its confidential content never opened) |
| Other `arena/*` heads | `02dd3e1…`, `c7e7697…`, `ad7ea0d…`, `b05ea76…`, `c28bbef…`, `7f0186e…`, `4336ea3…` (unchanged) |
| Generated / temp | `/tmp/qtenv.sh` (copy of `tools/qt_headless_env.sh` with the venv path); `/home/user/.venv` 1.1 GB; `/home/user/qt-libs` 88 KB (stub libraries); nothing generated inside the repository |

## Environment

| Item | Value |
|---|---|
| OS | Linux 6.1.158+, 2 CPUs, 3939 MiB RAM, no swap |
| Python | 3.11.2 (`/home/user/.venv`, rebuilt from `requirements-lock.txt`) |
| Qt | PySide6 6.8.1.1, `QT_QPA_PLATFORM=offscreen`, stub libGL / libEGL / libxkbcommon / libdbus from `tools/qt_headless_env.sh` |
| Tools | pytest 9.1.1, ruff 0.16.6, build 1.6.1, coverage 7.16.2 (the CI pins) |
| Test env | `DRILLMASTER_ENV=test`; `verify_release.py` per-test watchdog `TEST_HANG_SECONDS=900`; the M95 test's own child budget 300 s |

## CI definitions (as configured, not changed)

| Workflow | Trigger | Runner | Job limit | Notes |
|---|---|---|---|---|
| `ci.yml` "Source release gate" | push, pull_request, dispatch; cancel-in-progress per ref | ubuntu-24.04 | **60 min** | matrix 3.11 / 3.12 / 3.13; 3.12 runs `verify_release.py --coverage`; floor `.github/coverage-floor.json` 45.5 % |
| `windows-release-gate.yml` | push etc. | windows-2022 | 60 min | Python 3.12, PyInstaller + Inno, M52 stress ×5, UNSIGNED |
| `artifact-byte-verification.yml` | see file (not a mandatory gate) | ubuntu-26.04 | 30 min | verifies published Windows artifacts |

Lint ceiling `.github/ruff-debt-ceiling.txt` = 0. The three limits that must not be traded against each other: the
60-minute CI job limit, the 300 s M95 child budget (D74), the 900 s per-test watchdog (D51 diagnostics).
