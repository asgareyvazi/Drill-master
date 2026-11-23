# M321 – live repository baseline and non-destructive recovery

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

The mission text uses two spellings for the evidence directory, `m321_m360_evidence` and `m321-m360-evidence`.
The evidence lives in `docs/mission-reports/m321-m360-evidence/`, following the existing `m291-m320-evidence`
convention.

## State found at the start (start of M321)

The sandbox had been reset for the **ninth** time.

| Check | Result |
|---|---|
| `git branch --show-current` | `arena/72010272-drill-master` |
| local HEAD | `4336ea357fc1…` (the original base, *grafted*/shallow); no upstream configured |
| `git log -n 20` | 1 commit visible (`4336ea3`), the shallow graft |
| `git status --short` | 174 modified/deleted tracked files plus many untracked files, all relative to `4336ea3` |
| `git diff --cached` | empty |
| `git stash list` | empty |
| `git worktree list` | one worktree (the checkout itself) |
| `git remote -v` | `origin https://github.com/asgareyvazi/Drill-master.git` (fetch and push) |
| `git ls-remote origin refs/heads/arena/72010272-drill-master` | **`6754e14dbbf12351728bd36c558a164a81e3bf1e`**, equal to the expected starting SHA |
| `git ls-remote origin refs/heads/drill-Master` | `e3fa42a3257e981d9bdf9d012c97919e3352a53a` (protected by project policy; never written) |
| tags | 0 |
| `.venv`, `/home/user/qt-libs` | missing (lost in the reset) |
| confidential `08-DDR …xlsx` | shows as `D` relative to the base. It is absent from the branch tree, was removed in an earlier mission, and was neither restored nor opened |

## Recovery (no reset, clean, checkout or force)

1. `git fetch origin arena/72010272-drill-master` and `git fetch --unshallow origin`.
2. `git merge-base --is-ancestor 4336ea3 6754e14`: confirmed.
3. A **temporary index** (`GIT_INDEX_FILE=/tmp/m321.idx`) was seeded with `git read-tree 6754e14`, followed by
   `git add -A` and `git write-tree`:
   * working-tree tree: `ca53c3ac5edf2f2d68e16255f53dd2bf339f1b0e`;
   * `6754e14^{tree}`: `ca53c3ac5edf2f2d68e16255f53dd2bf339f1b0e`.

   They are **identical**. No local file differs from the pushed tree, so no work could be lost.
4. Only after this check:
   * `git update-ref refs/heads/arena/72010272-drill-master 6754e14… 4336ea3…` (with the expected old value);
   * `git read-tree 6754e14` to load the real index;
   * the upstream was set.

   No file changed. `git status --short` is now empty and the branch is level with `origin`. The history has
   727 commits.
5. Environment:
   * `/home/user/.venv` was rebuilt from `requirements-lock.txt` plus the CI tool pins (`pytest==9.1.1`,
     `ruff==0.16.6`, `build==1.6.1`, `coverage==7.16.2`), giving Python 3.11.2 and PySide6 6.8.1.1;
   * `.venv` is a symlink, excluded through `.git/info/exclude`;
   * the headless Qt stubs were rebuilt with `tools/qt_headless_env.sh`, and the offscreen smoke test passed.

## CI on the starting SHA `6754e14` (read through the API)

| Workflow | Run | Jobs |
|---|---|---|
| Source release gate | 45005356374 | source (3.11) 137155650322 ✅, source (3.12) 137155650355 ✅ (coverage 72.88 %, 81,029 / 111,179), source (3.13) 137155650184 ✅ |
| Windows release validation | 45005356467 | windows-release 137155650615 ✅ |

## Conclusion

The live baseline equals the expected starting SHA. No unintended work existed, and nothing was discarded.
Product code was not modified during M321.
