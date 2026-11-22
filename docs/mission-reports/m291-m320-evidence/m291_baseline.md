# M291 – live repository and workspace baseline

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

## Sandbox state found at the start

The sandbox had been reset again (the eighth reset recorded).

* The local branch ref pointed at the original base commit `4336ea357fc1ae28ccca228cdf7873697cc4cd84`, and no upstream was configured.
* The working files were present, so `git status` showed hundreds of modified and untracked paths relative to that base.
* The virtual environment (`/home/user/.venv`) and the headless Qt stubs (`/home/user/qt-libs`) were gone.

## Non-destructive recovery

No reset, clean, checkout, force update or blind tree replacement was used.

1. `git fetch origin` brought in the remote branch `b6a6a338ddefae70dd7ddb16eb8ea17ebd209182`.
2. `4336ea3` was confirmed to be an ancestor of the remote HEAD.
3. The working tree was written to a **temporary** index (`GIT_INDEX_FILE` in `/tmp`, seeded from the remote tree, then `git add -A`) and hashed with `git write-tree`.
   * Working-tree tree: `f2715211d867fdbf01762f435d60487b1958de3f`.
   * Remote `b6a6a33^{tree}`: `f2715211d867fdbf01762f435d60487b1958de3f`.
   * Identical, so no file content differs from the pushed tree.
4. Only after this verification:
   * the branch ref was moved with `git update-ref` (with the expected old value `4336ea3`);
   * the index was loaded from the same verified tree;
   * the upstream was set.
   No file changed.

## Verified baseline

| Item | Value |
|---|---|
| Branch | `arena/72010272-drill-master` (the only authorized branch) |
| Local HEAD | `b6a6a338ddefae70dd7ddb16eb8ea17ebd209182` |
| Upstream / remote HEAD | `b6a6a338ddefae70dd7ddb16eb8ea17ebd209182` (verified by `git ls-remote`) |
| Product-code commit | `07a0f8bad16f5040402526f28adff396bde709d5` = parent of `b6a6a33` |
| `07a0f8b..b6a6a33` | 8 files, all under `docs/`; 0 product-source files |
| Commits on the branch since its base | 317 |
| Staged / unstaged / untracked | none / none / none after recovery (`git status --short` is empty) |
| Stashes | none |
| Worktrees | one (the checkout itself) |
| `drill-Master` | `e3fa42a3257e981d9bdf9d012c97919e3352a53a`. GitHub reports `protected=false` and no rulesets; the project policy still forbids writing to it. Not tested by a write. |
| Tags / releases | 0 tags |
| Confidential files | not opened. The base commit `4336ea3` still tracks the `08-DDR …xlsx` workbook; the branch tree no longer contains it (removed in an earlier mission), and it was neither restored nor read. |
| Python / Qt | Python 3.11.2, PySide6 6.8.1.1, Shiboken6 6.8.1.1 (venv rebuilt from `requirements-lock.txt` plus the CI tool pins `pytest==9.1.1`, `ruff==0.16.6`, `build==1.6.1`, `coverage==7.16.2`) |
| Headless Qt | stubs rebuilt by `tools/qt_headless_env.sh`; offscreen smoke test passed |
| `.venv` | symlink to `/home/user/.venv`, excluded through `.git/info/exclude` (not tracked) |
| CI workflows | `ci.yml` (Source release gate: 3.11, 3.12 with `--coverage`, 3.13; 60-minute job limit), `windows-release-gate.yml`, `artifact-byte-verification.yml` |
| Reports / evidence | `docs/mission-reports/`; the previous evidence is in `m261-m290-evidence/`; this mission's evidence is in `m291-m320-evidence/` |

## CI on the starting SHAs

| SHA | Workflow (run) | Legs |
|---|---|---|
| `07a0f8b` (code) | Source release gate (44900584036) | 3.11 ✅ 33 min; 3.13 ✅ 52 min; 3.12 coverage ❌ cancelled at 60 min on attempt 1 (job 136835435798) and attempt 2 (job 136853947627) |
| `07a0f8b` | Windows release validation (44900583984) | ✅ |
| `b6a6a33` (docs only) | Source release gate (44917777718) | 3.11 ✅ 36 min (job 136886981457); 3.12 coverage ✅ 47 min (job 136886981465); 3.13 ✅ 37 min (job 136886981222) |
| `b6a6a33` | Windows release validation (44917777732) | ✅ 36 min (job 136886981365) |

Coverage for job 136886981465 comes from its check-run annotation, read through the API in this mission: "product coverage (branch+line) 72.40% over 291 tracked files (78781/108811); floor 45.50%".

The test counts for that job are 5,677 passed, 4 skipped, 0 failed, and 2,720.94 s for pytest under coverage. They come from the job log as quoted in the mission brief. The sandbox cannot download job logs: they are served from a blob host outside the allowed network list. The counts match the local full run on `07a0f8b`, which was 5,677 passed and 4 skipped.
