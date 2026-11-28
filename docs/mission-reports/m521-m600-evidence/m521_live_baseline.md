# M521 — live baseline (preflight)

Branch `arena/72010272-drill-master`. Product label: PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.

## Start SHA and remote

| Item | Value |
|---|---|
| Expected start (M461–M520 final) | `1ab35e1bff2595e657d5a677d1ddca364699a05f` |
| `git ls-remote origin arena/72010272-drill-master` | `1ab35e1bff2595e657d5a677d1ddca364699a05f` |
| `git ls-remote origin drill-Master` (protected, never written) | `e3fa42a3257e981d9bdf9d012c97919e3352a53a` |
| Local HEAD after the reset described below | `1ab35e1bff2595e657d5a677d1ddca364699a05f` |

## Session start state and the non-destructive reset

The sandbox started with local HEAD at the session base `4336ea3` (the branch point of the Arena session) and a
work tree that showed many modified files relative to that base. Before touching anything the work tree was
compared byte-for-byte against `1ab35e1` with a temporary index:

```
GIT_INDEX_FILE=/tmp/cmpidx git read-tree 1ab35e1
GIT_INDEX_FILE=/tmp/cmpidx git add -A
GIT_INDEX_FILE=/tmp/cmpidx git diff --cached --stat 1ab35e1     # -> empty
```

The diff was empty: the work tree was exactly the remote tip, so no unknown local work existed. Only then was
`git reset -q --mixed origin/arena/72010272-drill-master` run (index/HEAD move only; no `--hard`, no clean, no
force-push). Afterwards:

```
$ git status --short --branch
## arena/72010272-drill-master...origin/arena/72010272-drill-master
$ git stash list            # (empty)
$ git worktree list --porcelain
worktree /home/user/Drill-master
HEAD 1ab35e1bff2595e657d5a677d1ddca364699a05f
branch refs/heads/arena/72010272-drill-master
```

## CI on the start SHA (exact SHA `1ab35e1`)

| Workflow | Run | Job | Conclusion | Duration |
|---|---|---|---|---|
| CI (Source) | 46125064146, attempt 1 | Python 3.11 | success | 43m15s |
| CI (Source) | 46125064146, attempt 1 | Python 3.12 (coverage) | success | 51m47s |
| CI (Source) | 46125064146, attempt 1 | Python 3.13 | success | 43m59s |
| Windows release gate | 46125064174 | windows build | success | 35m30s |

Read with `gh api repos/asgareyvazi/Drill-master/actions/runs/46125064146/jobs`.

## Environment rebuild

The virtual environment and `/tmp` do not survive a sandbox restart. Rebuilt in the background:
`python3 -m venv /home/user/.venv` + `pip install -r requirements-lock.txt` (lock sha256 `697124ea…edcfadd`,
PySide6 / Addons / Essentials / shiboken6 6.8.1.1 unchanged), pytest, ruff, build, coverage; Qt headless stubs
via `tools/qt_headless_env.sh` into `/home/user/qt-libs` (a temporary `.venv` symlink was used and removed). Exit 0.
Python 3.13 diagnostic environments were not rebuilt (not needed; CI covers 3.13).

Linux offscreen Qt is not desktop acceptance.
