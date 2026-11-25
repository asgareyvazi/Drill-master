# M461 — Live baseline and workspace inspection

Recorded 2026-11-25 07:38 UTC (sandbox clock), before any M461–M520 file change.

| Item | Value |
|---|---|
| Repository path | `/home/user/Drill-master` |
| Remote | `https://github.com/asgareyvazi/Drill-master.git` (`origin`) |
| Branch | `arena/72010272-drill-master` |
| `git ls-remote` Arena branch | `e5610729f9f3370341a8cb2a6fb8b7b28ec523f5`: has not advanced since `e561072` |
| `git ls-remote` `drill-Master` | `e3fa42a3257e981d9bdf9d012c97919e3352a53a` (unchanged) |
| Local HEAD at session start | `4336ea357fc1ae28ccca228cdf7873697cc4cd84` (see the next section) |
| Local HEAD after reconciliation | `e5610729f9f3370341a8cb2a6fb8b7b28ec523f5` |
| Unpushed local commits / remote commits not local | 0 / 0 |
| Stashes | 0 |
| Worktrees | 1 (`/home/user/Drill-master`) |
| Untracked / relevant ignored files | none, after reconciliation (only `__pycache__` trees) |

## Sandbox restore observed

The sandbox was restored from a workspace snapshot. The restored checkout had these properties:

- the working tree contained the files of `e561072`;
- the local `HEAD` and index pointed at the session base commit `4336ea3`;
- `git status` therefore listed about 1 160 apparent changes.

`4336ea3` is an ancestor of `e561072`. Reconciliation was `git reset --mixed origin/arena/72010272-drill-master`, which moves HEAD and the index only. After it, `git status --short --ignored` showed no staged, unstaged or untracked change, which shows that the working tree equals `e561072` exactly. No file was discarded, and nothing was force-pushed or rewritten.

The Python environment (`/home/user/.venv`) and the Qt stub libraries (`/home/user/qt-libs`) were not part of the snapshot. They were rebuilt as follows:

- Python 3.11.2;
- `pip install -r requirements-lock.txt` (lock sha256 `697124eaf6dc…edcfadd`, unchanged);
- the CI-pinned tools `pytest==9.1.1`, `ruff==0.16.6`, `build==1.6.1` and `coverage==7.16.2`;
- `tools/qt_headless_env.sh`.

PySide6 is 6.8.1.1 (pin unchanged).

## CI on the baseline

| Run | Workflow | head SHA | Conclusion |
|---|---|---|---|
| `45401906446` | Source release gate | `e561072` | success: 3.11 42m31s, 3.12 56m38s, 3.13 42m44s |
| `45401906533` | Windows release validation | `e561072` | success (30m09s) |
| `45384695412` | Source release gate | `1c5d0f7` | failure: 3.12 benchmark-table drift; 3.13 TIMEOUT (retained) |

The last successful CI belongs to the exact baseline SHA `e561072`.
