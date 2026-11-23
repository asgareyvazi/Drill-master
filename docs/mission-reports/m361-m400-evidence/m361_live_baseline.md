# M361 — Live baseline, and M362 — workspace recovery

Read live on 2026-11-23 at 10:22 UTC, before any M361–M400 change. Commands and outputs are summarised. Nothing
here is inferred from the previous mission's report.

## 1. Repository state at the start of M361

| Item | Command | Result |
|---|---|---|
| Current branch | `git branch --show-current` | `arena/72010272-drill-master` |
| HEAD | `git rev-parse HEAD` | `3ca8b80e14e93299ded78feb0750a51a21abe99a` |
| Remote work branch | `git ls-remote origin refs/heads/arena/72010272-drill-master` | `3ca8b80e14e93299ded78feb0750a51a21abe99a` (equal to HEAD) |
| Ahead / behind | `git rev-list --left-right --count HEAD...origin/arena/72010272-drill-master` | `0 0` |
| Protected base branch | `git ls-remote origin refs/heads/drill-Master` | `e3fa42a3257e981d9bdf9d012c97919e3352a53a` (never written by this mission) |
| Worktrees | `git worktree list` | one: `/home/user/Drill-master` |
| Stashes | `git stash list` | none |
| Unstaged / staged diff | `git diff --stat`, `git diff --cached --stat` | empty / empty |
| Untracked files | `git ls-files --others --exclude-standard` | 0 |
| Ignored, present | `git status --ignored --short` | `.ruff_cache/`, `.venv` (a symlink to the sandbox virtual environment) |
| Last 30 commits | `git log --oneline -30` | top: `3ca8b80` docs (D51 explained), `246e7bf` probe `--qt-gc`, `90192f5`, `29620f4`, `82d1fff`, `067aa44`, `534e4f3`, `6ace038` … |

## 2. M362 — non-destructive workspace recovery

Nothing needed recovering: no stash, no second worktree, no untracked or modified file, and no divergence from
the remote. No `reset`, `clean`, `checkout --` or `restore` was run. The M321–M360 work is all on the remote at
`3ca8b80`. There was no stranded work.

## 3. CI reconciliation: two SHAs, kept separate

`3ca8b80` changes only documentation. A docs-only SHA is **not** reported as passed because its parent passed: each
SHA keeps its own runs.

### 3a. Product code `246e7bf` (last code change of M321–M360)

| Run | Workflow | Result |
|---|---|---|
| `45144294084` | PySide candidate evaluation | SUCCESS (10 / 10 jobs) |
| `45144294022` | Source (3.11 / 3.12 / 3.13) | SUCCESS on all three |
| `45144294116` | Windows release gate | SUCCESS |

### 3b. Docs-only `3ca8b80`

| Run | Workflow | Job | State when read |
|---|---|---|---|
| `45153601358` | Source | 3.11 / 3.12 / 3.13 | see §3c |
| `45153601362` | Windows release gate | windows-release | see §3c |

The runs were IN_PROGRESS at 10:22:49, 10:25:37 and 10:41:12 UTC. No push was made while they ran, because a push
to the branch cancels in-flight runs (M321–M360 lesson). The M361–M400 commits were held locally until both
finished.

### 3c. Final state of the `3ca8b80` runs

(filled in when the runs complete; see the integrated report §CI for the final table)
