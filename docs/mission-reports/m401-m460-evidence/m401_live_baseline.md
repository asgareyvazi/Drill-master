# M401 — Live repository and workspace baseline

Recorded 2026-11-24 10:21 UTC (sandbox clock), before any M401–M460 file change.

| Item | Value |
|---|---|
| Repository path | `/home/user/Drill-master` |
| Remote | `https://github.com/asgareyvazi/Drill-master.git` (`origin`) |
| Current branch | `arena/72010272-drill-master` |
| Local HEAD | `e9244e80364641315d1da31e62e055b9548d57dd` |
| `git ls-remote` Arena branch | `e9244e80364641315d1da31e62e055b9548d57dd` |
| `git ls-remote` `drill-Master` | `e3fa42a3257e981d9bdf9d012c97919e3352a53a` |
| Ahead / behind remote | 0 / 0 (not diverged); no remote commit newer than `e9244e8` |
| `git status --short --branch` | `## arena/72010272-drill-master...origin/arena/72010272-drill-master` — no staged, unstaged or untracked file |
| Stashes | 0 |
| Worktrees | 1 (`/home/user/Drill-master  e9244e8`) |
| Ignored entries | `.venv` (symlink to `/home/user/.venv`), `__pycache__/` trees, `.pytest_cache/`, `.ruff_cache/` — none is product or test source |
| Active processes able to modify the repository | none (process list: `envd`, kernel threads only) |

## Branch protection / rulesets

| Query | Result |
|---|---|
| `GET branches/drill-Master` `.protected` | `false` |
| `GET branches/drill-Master/protection` | HTTP 403 "Resource not accessible by integration" — **NOT CHECKED** (token scope) |
| `GET branches/arena%2F72010272-drill-master` `.protected` | `false` |
| `GET rulesets` | `[]` (no repository ruleset) |

`drill-Master` is protected by project policy only, not by a GitHub rule. The policy is honoured regardless.

## Source-tree identity of the M400 evidence

`git diff --name-only 41ea53e e9244e8` lists six documentation / evidence files only. Tree hashes are identical:

| Path | `41ea53e` | `e9244e8` |
|---|---|---|
| `core` | `d108d165…` | `d108d165…` |
| `dialogs` | `799d1f7b…` | `799d1f7b…` |
| `tabs` | `6573e99a…` | `6573e99a…` |
| `tests` | `8d0d1da5…` | `8d0d1da5…` |
| `tools` | `fc37c96a…` | `fc37c96a…` |
| `ui` | `f49fa6a0…` | `f49fa6a0…` |
| `packaging` | `60a0e423…` | `60a0e423…` |
| `.github` | `3cc1317b…` | `3cc1317b…` |

Therefore M389 run 3 (on `41ea53e`) and the eight-shard suite (on `ed68380`) apply to the `e9244e8` product / test tree.

## CI on `e9244e8` (all attempts, exact `head_sha` = `e9244e803646…`)

| Run | Attempt | Job | Status | Conclusion | Start → end |
|---|---|---|---|---|---|
| Source `45353234275` | 1 | source (3.11) | completed | success | 08:06:25 → 08:51:28 |
| Source `45353234275` | 1 | source (3.12) | completed | **cancelled — TIMEOUT** (annotation "exceeded the maximum execution time") | 08:06:25 → 09:06:41 |
| Source `45353234275` | 1 | source (3.13) | completed | success | 08:06:25 → 09:00:18 |
| Source `45353234275` | 2 (failed job re-run, timeout unchanged) | source (3.12) | completed | success | 09:07:14 → 10:03:33 (56m19s) |
| Windows `45353234306` | 1 | windows-release | completed | success | 08:06:25 → 08:36:12 |

The attempt-1 TIMEOUT is retained; it is not reclassified as success.
