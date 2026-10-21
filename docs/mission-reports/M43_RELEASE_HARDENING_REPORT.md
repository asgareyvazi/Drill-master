# M43 — Release hardening: repository audit, privacy remediation, DB operations UX

Mission: *Full repository audit, engineering hardening, privacy remediation and
release-readiness closure*. Branch `arena/72010272-drill-master`, starting at
the reference checkpoint `9060b08`. Date: 2026-10-20.

**Status: implemented-incompletely-verified — NOT release-ready.** Three work
packages were completed and pushed (privacy, backup settings/authorization,
missing DB failure tests + security documentation). Phases 4–8 and 10 were
not started in this session; Phases 9 and 11 were done only for the work
above. Licence, signing (builds stay **UNSIGNED**), Windows manual acceptance,
field validation, the history purge and the money migration (D1–D7) remain
open owner actions. Nothing here is a release approval.

## A. Executive summary

1. **The public default branch still serves the real daily drilling report.**
   `drill-Master` (tip `e3fa42a`, the branch GitHub shows) never received the
   M43 remediation: its current tree contains the real workbook (blob
   `b581f873…`) and 11 other blobs with protected content. Merging the
   remediation is an ordinary commit, not a rewrite, but agents may not touch
   `drill-Master` — **owner action #1, urgent.**
2. **Real equipment serial numbers had survived the first privacy pass**: as
   text in three DDR evidence JSONs, and as numeric cells in the shipped cell
   dump (`templates/OEOC_DDR_full_extraction.json`, packaged in every build)
   and in the "de-identified" test fixture. Fixed in `61f2b71`: redacted or
   overwritten with synthetic values by the existing sanitizer, digests added
   to the denylist, and a new `equipment-serial-number` rule (which caught 12
   further occurrences the old checker missed).
3. **A full-history inventory replaces the shallow estimate**: 17 protected
   blobs in 300 of 454 commits, on every branch and in PR refs #2–#4. The
   purge plan now covers zipped workbooks (where `--replace-text` cannot
   reach) and lists every blob ID to verify. Not executed (owner-gated).
4. **Authorization bypass closed**: *Settings > Database > Backup Database
   Now* let any signed-in role (including viewer) copy the whole database —
   every row, password hashes, audit log — to any folder, with no permission
   check, manifest or audit. It now runs the verified service (`28d7920`).
5. **Dead backup settings wired**: the dialog saved values nothing read and
   showed backups as *off* while they ran every 30 minutes. One resolver
   (environment > saved setting > default, validated, applied at next start,
   never deleting on change) now feeds the scheduler and the service.
6. **Missing failure tests added**: shutdown while a scheduled backup is in
   flight, and corrupt manifests (`ad67602`).

## B. Git evidence

| Item | Value |
|---|---|
| Start | HEAD found stale at `4336ea3` while the remote was at `9060b08a9a31d0bf26c186365b08e757aa9b63a3`; verified with a temporary index (0 modified, 0 untracked), restored with a compare-and-swap `update-ref` + `read-tree` (no reset) |
| Commits this session | `61f2b719bf6ced931550f6b84a3a130f3e8fd07c` privacy · `28d7920` backup settings + authorization · `ad676023ea1f970c33b045ac910150b4030f3e15` tests + security docs · this report (next commit) |
| Push verification | `git ls-remote origin refs/heads/arena/72010272-drill-master` returned `61f2b71…` and then `ad67602…` after the respective pushes |
| History operations | none: no force-push, reset, rebase or rewrite; `drill-Master` and other branches untouched. A read-only `fetch --unshallow` plus a fetch of all branches and PR refs (local audit refs, deleted afterwards) were used for the inventory |

## C. Exact-SHA CI (GitHub REST `actions/runs?head_sha=<full sha>`)

| SHA | Nature | Source release gate (3.11/3.12/3.13) | Windows release validation |
|---|---|---|---|
| `9060b08a9a31…` | reference, docs-only | 39384716176 success (jobs `118501706310`, `118501706266`, `118501705961`) | 39384716078 success |
| `90016027b065…` | last code-complete before this session | 39383249614 success | 39383249495 success |
| `61f2b719bf6c…` | privacy package | 39403546275 success (jobs `118563883210`, `118563882809`, `118563883208`) | 39403546169 success |
| `ad676023ea1f…` | settings + tests + docs (contains `28d7920`, which was pushed together with it and has no separate run) | 39405858710 success, attempt 1 (jobs 3.11 `118571494194`, 3.12 `118571493756`, 3.13 `118571494111`) | 39405858636 success, attempt 1 (job `118571494028`); annotation: manifest `sha=ad676023…`, installer `DrillMaster-1.0.0-Setup.exe` **UNSIGNED/NotSigned** |

The Windows job builds and tests an **UNSIGNED** installer; it is not Windows
acceptance. Green runs on documentation-only SHAs are not code evidence.

## D. Audit of the Phase E/F claims

| Claim (M43 DB report) | Re-check | Result |
|---|---|---|
| Suite 2529/64/45/18 at the code-complete state | full run at `9060b08` (same code), native environment | **reproduced exactly**: 2529 passed, 64 failed, 45 skipped, 18 errors; the 82 failures/errors are all libGL-import (sandbox has no libGL; CI does) |
| CI green at `90016027` and `9060b08` | REST API, exact SHA, jobs | **verified**; IDs in C |
| Windows installer UNSIGNED, 83,276,309 B | earlier manifest record | not re-downloaded this session; unchanged claim |
| "Interactive backups require `can_maintain_database`" | code audit of every `backup_to` caller | **incomplete**: true for *Tools*, false for the Settings button → fixed (A4) |
| Backup configuration documented as env-only | code audit of Settings | the dialog offered settings that did nothing → fixed (A5) |
| Phase 1 failure tests | test-by-test mapping (G) | 2 of 9 missing → added |

## E. Metrics (before = `9060b08`, after = `ad67602`)

| Metric | Before | After | Note |
|---|---|---|---|
| Full suite (native, no libGL) | 2529 / 64 / 45 / 18 | 2568 / 64 / 45 / 19 (at `28d7920`) | +39 passing tests; the extra error is the new Qt UI test file failing to import libGL (passes 9/9 with a stub, see I) |
| New tests after `28d7920` | — | +5 in `test_db_backup_service.py` (22 passed) | |
| Coverage, branch+line, product source (excl. tests/tools/packaging) | 44.24 % | not re-measured | `--cov=. --cov-branch` at `9060b08`; all measured files 60.85 %, `core/` 70.25 %; depressed by the libGL-only failures. **Correction (continuation, 2026-10-21):** `--cov=.` silently left out modules that no test imported; over all 186 tracked product files the value was 33.52 % locally (no libGL) at `aee2cc8` and 45.30 % on CI 3.12 at `ba08ff0`; now gated at a 45.20 % floor (part 2, §E) |
| Ruff debt (core dialogs tabs tests) / ceiling | 5342 / 5375 | 5342 / 5375 | ceiling not changed |
| F403 wildcard statements | 94 | 94 | Phase 4 not started |
| Exception handlers / broad / silent | 1031 / 629 / 192 | 1035 / 628 / 192 | new handlers log; ceiling not changed |
| Privacy check findings (tracked tree) | 0 (rules then) | 0 (with the new rule; 12 found and fixed on the way) | |
| Protected blobs reachable from this branch's tip | 5 | 0 | full-history scan |
| Protected blobs in the default branch's tip | 12 | 12 | owner action #1 |
| Schema version | 6 | 6 | no migration |
| `setStyleSheet` / non-test `processEvents` call sites | 502 / 22 | 502 / 22 | Phase 7 not started |
| Largest file `core/database.py` | 10,713 lines | 10,713 lines | Phase 4 not started |

## F. Scorecard (13 areas)

"Supplied" are the baseline numbers given with the mission (not facts).
"Verified" is assigned only where this session produced evidence; "—" means
not re-assessed. No target was assigned automatically.

| Area | Supplied | Verified | Evidence | Work this session | Gap | Next |
|---|---|---|---|---|---|---|
| Engineering core | 8.0 | — | none new | — | Phase 6 audit not run | audit MCM, kill sheet, T&D, hydraulics with golden tests |
| Advanced engineering | 6.0 | — | none new | — | stiff-string, buoyancy, von Mises unsupported | cite a reference + golden test, or document unsupported |
| Import | 7.0 | — | fixture consumers 312 passed | fixture re-sanitized, structure-equal | Phase 5 edge-case/fuzz tests | Phase 5 |
| Database | 5.0 | 7.0 | 38 + 5 service tests, 30 + 9 settings tests, mutation checks | settings wired, 2 failure tests | Windows manual acceptance, power loss not simulated, count-only retention, remote mounts undetectable | owner checklist (12 items) |
| Security | 5.5 | 6.5 | bypass found and closed, role tests | read-policy audit, trust boundary, SQLCipher assessment | no encryption, read policy undecided, UNSIGNED, no password-change UI | owner read-policy decision |
| Audit trail | 7.0 | — | backup/restore audit tests | — | not tamper-proof (documented) | — |
| UI | 5.0 | 5.0 | call-site counts unchanged | Settings backup controls | theme, QUndoStack, `tr()`, blocking work | Phase 7 |
| Tests | 8.5 | 8.0 | +53 tests (44 run natively; 9 Qt tests in stub env and CI), mutants killed, 0 regressions | — | product coverage 44 %, no CI coverage floor | coverage ratchet (Phase 4) |
| CI | 7.0 | 7.0 | exact-SHA green, pinned `ubuntu-24.04` | — | no coverage, UNSIGNED | signing inputs (owner) |
| Code structure | 3.5 | 3.5 | file sizes unchanged | one small extraction (`_create_backup_services`) | `database.py` 10.7k lines, 94 F403 | Phase 4 |
| Error handling | 5.5 | 5.5 | silent 192 unchanged | new handlers log | 192 silent handlers | Phase 4 |
| Documentation | 4.0 | 5.0 | DB operations, security model, privacy docs updated with evidence | 4 documents | README, ARCHITECTURE, DEPLOYMENT, USER_GUIDE etc. not reviewed | Phase 8 |
| Privacy | 2.0 | **3.0** — working-branch tree 8.0; public exposure 2.0 | tree scan 0 findings, 0 protected blobs at tip; default branch serves the workbook; history 300 commits | serials fixed, rule added, verified inventory, plan corrected | containment, purge, PR refs | owner actions 1–2 |

Privacy is capped by the public exposure: no 9/10 is possible while the
default branch and history contain the data.

## G. Work-package progress

| Phase | Status | Detail |
|---|---|---|
| 0 Recon/baseline | verified-complete | state, CI, suite, coverage, static metrics, privacy cross-check |
| 1 DB ops UX | implemented-incompletely-verified | settings resolver + validation + UI + startup wiring (tests, mutants); Phase 1 failure-test map: close during maintenance ✓ (UI test), writes during restore ✓, second instance ✓, scheduler shutdown mid-backup **added**, corrupt manifest **added**, journal/replace/recovery failures ✓, Windows exclusive access ✓ simulated only; power loss not simulated (documented); Windows manual run owner-gated |
| 2 Privacy | implemented-incompletely-verified | tree remediated on this branch; purge plan owner-gated; default branch containment owner-gated |
| 3 Security | implemented-incompletely-verified | bypass fixed; docs; lockout/throttle/permission suites pass in the full run; no new read policy (owner) |
| 4 Code health | not run | |
| 5 Imports | not run | |
| 6 Engineering | not run | |
| 7 UI | not run | |
| 8 Docs | not run (beyond the 4 documents above) | |
| 9 Gates | verified for this session's SHAs (C); Windows remains UNSIGNED; owner checklist written (`docs/DATABASE_OPERATIONS.md`) | |
| 10 Owner prep | partially: purge plan updated, SQLCipher assessment, read-policy decision framed | licence, D1–D7, signing inputs not touched |
| 11 Adversarial re-audit | only for this session's claims (D) | |

## H. Owner actions

1. **Containment (urgent, no rewrite):** bring the remediation onto
   `drill-Master` (PR from this branch, or a commit deleting the workbook and
   applying the redactions). See `docs/privacy/HISTORY_PURGE_PLAN.md` §0.
2. **History purge** per the plan (§3 dry-run, §4 backup, §5 including the
   blob substitution, §6 verification of all 17 blob IDs); ask GitHub Support
   to drop PR refs and caches; collaborators re-clone.
3. **Read policy:** decide whether reads need per-company/project isolation or
   role limits (e.g. costs for viewers). Nothing was invented.
4. **Windows acceptance:** the 12-item checklist in
   `docs/DATABASE_OPERATIONS.md` (install, SmartScreen, backup settings,
   manual backup + manifest, synthetic restore, second instance, corrupt
   backup, close after restore, audit, uninstall, languages + daily report and
   survey).
5. Licence, code signing, deployment choices, money migration D1–D7, and
   whether to scrub Tier-2 names in old audit reports.

## I. Resume instructions

* Branch `arena/72010272-drill-master`; tip after this report = the commit
  following `ad67602`. Verify with `git ls-remote` before working; if HEAD is
  stale, restore it with a temporary index check and a compare-and-swap
  `update-ref` (never `reset --hard`).
* Environment: `python3 -m venv .venv && .venv/bin/pip install -r
  requirements-lock.txt pytest==9.1.1 ruff==0.16.6 build==1.6.1 pyyaml
  pytest-cov hypothesis`. Full suite:
  `QT_QPA_PLATFORM=offscreen python -m pytest -p no:cacheprovider --tb=no -rfE --continue-on-collection-errors`.
* Sandboxes without libGL: Qt tests can be run against generated stub
  libraries (empty `libGL`/`libEGL` functions and version-scripted
  `libdbus-1`/`libxkbcommon` stubs built from `nm -D --undefined-only` of the
  PySide6 libraries, put on `LD_LIBRARY_PATH`). Results are
  **stub-environment** evidence only; CI with real libGL is authoritative.
* Next packages, in order: Phase 4 (wildcard imports in groups, silent
  handlers in critical paths, coverage floor), Phase 5, Phase 7, Phase 8,
  Phase 6, then the remaining owner preparation (licence/D1–D7 worksheets).
* Privacy analysis of the real workbook must stay in memory or under `/tmp`;
  print only counts, shapes or masked tokens.

---

# Part 2 — M43 continuation (2026-10-20 → 2026-10-21)

Mission *DRILL-MASTER M43 CONTINUATION*. Branch `arena/72010272-drill-master`,
from checkpoint `aee2cc8` to code tip `b2ea8a8`. Part 1 above is left as it was
written, except for one marked correction to the coverage row.

## A. Executive summary

**Status: IMPLEMENTED_NOT_FULLY_VERIFIED. NOT release-ready. UNSIGNED.**
17 commits were pushed. Exact-SHA CI is green on the final code tip `b2ea8a8`
(three Python legs plus the Windows gate).

The default branch is **NOT contained**:
- `drill-Master` = `e3fa42a` still holds the real DDR workbook and PDF;
- the containment branch is scripted and verified, but only the owner can push
  and merge it;
- history is not purged.

**Real defects found and fixed this mission.** Each fix has a test that fails on
the previous code.

| # | Area | Defect | Commit |
|---|---|---|---|
| 1 | well info | saving a well with validation warnings raised `NameError`, so the well was **not saved** (hidden by star imports) | `0c32170` |
| 2 | audit | company/project/section deletes committed first and then wrote the audit entry under `except: pass`; the audit is now in the same transaction | `42ab17f` |
| 3 | import | lookahead hours such as `12-14` were silently dropped, and `inf` aborted the whole atomic import | `42ab17f` |
| 4 | import (performance) | generic Excel table detection was O(rows × cells): a 20,000-row sheet took more than 600 s and now takes about 12.5 s; output byte-identical | `00a392d` |
| 5 | engineering | casing VME capped-end axial stress was understated by a factor of π; the old test copied the bug | `e9bcc5c` |
| 6 | data safety | after a restore, autosave resumed before the modal result message, so stale screens could be saved into the restored database | `ec12eb2` |

**Structural and gate work:**
- all 94 PySide6 wildcard imports replaced (ruff debt 5342 → 751);
- whole-product coverage floor added (45.20%, CI-measured);
- unexplained silent handlers 192 → 161, with zero in `core/database.py`;
- first `database.py` extraction;
- report archive index, decision packets, UI assessment.

## B. Git evidence

| Item | Value |
|---|---|
| Start | `aee2cc866fdbee0f80943f465169efd8006c2db6` (HEAD = remote) |
| Final code tip | `b2ea8a8de637a82a8223d9a694b1c95e8d73d68c`, confirmed with `git ls-remote` |
| Commits | `bd47fa6`, `14a927f`, `dba5276`, `8831bd9`, `0c32170`, `2f2a82b`, `4e7631b`, `ba08ff0`, `42ab17f`, `46b6af3`, `fc34a18`, `00a392d`, `5028c29`, `4146a3f`, `e9bcc5c`, `ec12eb2`, `b2ea8a8`, plus this report commit |
| Banned operations | none used: no reset --hard, force-push, rebase, filter-repo or PR-ref change |
| Incident | a sandbox restore left the local branch ref at the fork point `4336ea3` and made the clone shallow. Recovery: fetch; compare the full working tree against `fc34a18` through a temporary index (only 3 intended files differed); compare-and-swap `update-ref`; mixed reset of the index only; `fetch --unshallow`. No work was lost. |
| Worktrees | `/tmp/wt-*` disappeared with the sandbox reset; `git worktree list` shows only the main checkout |

## C. Privacy containment

| | Value |
|---|---|
| Before (default branch `e3fa42a`) | 849 files; 131 findings in 13 paths; 12 protected blobs in the tip; 18 protected blobs in history, including the second real DDR PDF |
| Containment tree (scripted, not pushed) | `7f3c9ca4f68d24724123de5bcd1109aee671c3c2`: 0 findings, 0 of 18 blobs, 245 passed / 1 skipped, 23 files, privacy-only diff |
| PR | **none**. This session can push only its own branch, and a PR of this 135-commit branch is out of scope. Status: OWNER_GATED (packet P1) |
| Current tree of this branch | `privacy_check.py`: 989 files, 0 findings |
| Default branch after (re-checked 2026-10-21) | unchanged at `e3fa42a`; still contains the real workbook and PDF. **NOT contained** |
| History | **not purged**. The plan is ready (`HISTORY_PURGE_PLAN.md`, a single filter-repo run plus a 9-step checklist); approvals are absent |

## D. Exact-SHA CI (GitHub REST `actions/runs?head_sha=<full sha>`, attempt 1)

| SHA | Source release gate | Jobs | Windows release validation | Coverage notice | Signing |
|---|---|---|---|---|---|
| `ba08ff0…` | `39415376572` ✓ | 3.11 `118603000175`, 3.12 `118603000198`, 3.13 `118602999908` ✓ | `39415376568` ✓ (job `118602997122`) | 45.30% over 186 files (32836/72479) | UNSIGNED/NotSigned |
| `fc34a18…` | `39416876147` ✓ | 3.11 `118607932896`, 3.12 `118607932702`, 3.13 `118607932989` ✓ | `39416876122` ✓ (job `118607932483`) | 45.38% over 187 files (32894/72486) | UNSIGNED/NotSigned |
| **`b2ea8a8de637a82a8223d9a694b1c95e8d73d68c`** (final code tip) | **`39549337521` ✓** | 3.11 `119054978375`, 3.12 `119054978079`, 3.13 `119054978369` ✓ | **`39549337524` ✓** (job `119054919286`; Python 3.12.10, PyInstaller 6.11.1, Inno 6.7.1) | **45.63% over 187 files (33085/72512); floor 45.20%** | **UNSIGNED/NotSigned** |

The runs for `5028c29` and `e9bcc5c` were cancelled by the next push and do not
count. `bd47fa6` was not checked individually; its content is included in the
green SHAs above. The report commit that follows `b2ea8a8` is documentation-only.

## E. Metrics (start = `aee2cc8`, end = `b2ea8a8`)

| Metric | Start | End | Note |
|---|---|---|---|
| Full suite, local | 2573 / 64 / 45 / 19 (no libGL; the 83 failures and errors are all libGL) | **2870 passed / 4 skipped / 0 failed / 0 errors** | end run uses the libGL **stub**: stub evidence only, not comparable 1:1 with the start; CI is authoritative |
| Coverage (branch+line, all tracked product files) | 33.52% local over 186 files (the old "44%" figure omitted unimported modules) | **CI 45.63% over 187 files**; floor **45.20%**, enforced on CI 3.12 | provenance in `.github/coverage-floor.json` |
| Ruff debt (core dialogs tabs tests) / ceiling | 5342 / 5375 | **751 / 751** | ceiling lowered 5375 → 5142 → 4197 → 751 |
| F403 wildcard imports | 94 | **0** | explicit names; `tests/test_explicit_import_contract.py` |
| Exception handlers / broad / silent | 1035 / 628 / 192 | 1035 / 627 / 186 | |
| Unexplained silent handlers (ceiling) | 192 (core 112) | **161 (core 81)** | `core/database.py` 15 → 0; ceiling file lowered |
| `core/database.py` lines | 10,713 | **10,482** | one extraction (`core/default_procedure_templates.py`) |
| Other large files | w13 5,918; smart_template 3,568; main_window 3,236; w12 3,216 | 5,923; 3,572; 3,254; 3,220 | explicit imports added lines |
| `setStyleSheet` / `processEvents` | 502 / 22 | 502 / 22 | assessed only (`docs/UI_MODERNIZATION_ASSESSMENT.md`) |
| Schema version | 6 | 6 | no migration |

## F. Feature evidence

| Feature or claim | Status | Evidence |
|---|---|---|
| Hierarchy delete is atomic with its audit record | VERIFIED | `tests/test_silent_handler_contracts.py`; fails on the old code |
| Lookahead hours preserved | VERIFIED | same file |
| Corrupt or zero-byte xlsx rejected (`BadZipFile`) | VERIFIED (probe) | `IMPORT_PIPELINE.md` M43 table |
| Generic table detection is linear | VERIFIED | `tests/test_semantic_table_detection_scaling.py`: cell-visit bound, 20,000-row case, 400-seed fuzz. Equivalence: 3,000 seeded grids (711 with tables) and byte-identical payloads on 3 synthetic workbooks |
| Unrecognised generic tables are reported | **gap** | cells stay only in `raw_ir`; recommended diagnostic in `IMPORT_PIPELINE.md` |
| CSV import | conversion-only | the route stops before persistence (documented) |
| WITSML / LAS | placeholders | `core/witsml_import.py` |
| Engineering non-finite inputs rejected or flagged | VERIFIED | `tests/test_engineering_non_finite_contract.py`: 42 entry points, 244 calls; mutant killed |
| Casing VME | IMPLEMENTED_NOT_FULLY_VERIFIED | corrected and tested by force balance; screening only; no external standard edition cited |
| Stiff-string, pressure-area buoyancy, ISCWSA | NOT SUPPORTED | `ENGINEERING_CAPABILITY_STATUS.md` |
| Restore not overwritten by autosave | VERIFIED (stub UI test) | `tests/test_db_maintenance_ui.py` |
| `money_audit` read-only | VERIFIED | database byte-identical; `-wal`/`-shm` side files noted |
| Workers instead of `processEvents`, `QUndoStack`, `tr()`, theme | NOT_RUN | plan in `docs/UI_MODERNIZATION_ASSESSMENT.md` |

## G. Scorecard (13 areas)

The supplied scores are inputs, not facts. There is no scoring rubric, so none
of them is verified, and **no new score or target score is assigned**.

| Area | Supplied | Supplied score verified? | Evidence this mission | Change | Main gap | Next |
|---|---|---|---|---|---|---|
| Engineering core | 8.0 | NOT VERIFIED | non-finite contract over 42 entry points | test only | none measured | keep the contract green |
| Advanced engineering | 6.0 | NOT VERIFIED | VME π defect fixed | fix | no stiff-string, pressure-area or ISCWSA | cited sources before any formula |
| Import | 7.0 | NOT VERIFIED | lookahead fix; O(n²) → linear; edge-case probes | fixes | unrecognised generic tables are not reported | "unmapped cells" diagnostic |
| DB | 5.0 | NOT VERIFIED | restore/autosave fix; atomic hierarchy audit; first extraction | fixes | `database.py` is still 10.5k lines | one extraction per commit |
| Security | 5.5 | NOT VERIFIED | audit atomicity | fix | read policy undecided; well/report deletes not audited | owner P3; audit those deletes |
| Audit | 7.0 | NOT VERIFIED | as above | fix | `log_audit` swallows errors | raise or record |
| UI | 5.0 | NOT VERIFIED | w1 save fix; assessment | fix + plan | 22 `processEvents`, no undo or `tr()` | workers, starting with w11 |
| Tests | 8.5 | NOT VERIFIED | +7 new test files; mutants killed | added | stub vs official runtime | CI is authoritative |
| CI | 7.0 | NOT VERIFIED | coverage floor gate | added | runners: Node 20 removed; `ubuntu-latest` moving to 26.04 | pin `ubuntu-24.04` (owner choice) |
| Code structure | 3.5 | NOT VERIFIED | F403 94 → 0; ruff debt 5342 → 751 | improved | large files | extractions |
| Error handling | 5.5 | NOT VERIFIED | unexplained silent 192 → 161 | improved | tabs 50, dialogs 18, main_window 10 | next groups |
| Docs | 4.0 | NOT VERIFIED | archive index; 0 broken links; claims corrected | improved | per-doc command validation is partial | continue |
| Privacy | 2.0 | NOT VERIFIED | tree clean; default branch **not** contained | none on `drill-Master` | containment and purge | owner P1, P2 |

## H. Progress by work package (inventory; no percentages)

| Phase | Package | Status |
|---|---|---|
| §2 | containment script, verification, purge-plan audit | done; push and merge OWNER_GATED |
| §4 | Phase 0 baseline | done (`M43_CONTINUATION_BASELINE.md`) |
| §5 | wildcards | done |
| §5 | coverage floor | done (raised to the CI value) |
| §5 | critical-path exception classification | done (core/db/security: 0 unexplained in `database.py`) |
| §5 | `database.py` split | started: 1 of N extractions. Models must stay in `core/database.py` per `tests/test_model_registry.py` |
| §5 | dead code | none removed (no proof gathered) |
| §6 | import audit and probes | partial: probes, the performance fix and fuzzing done; cancel, retry and duplicate paths not newly tested |
| §7 | engineering review | partial: non-finite contract, VME fix, unsupported list; golden values for MCM, kill sheet and hydraulics not re-derived |
| §8 | UI | restore/autosave fix done; theme, `tr()`, undo and workers NOT_RUN (planned) |
| §9 | docs | archive index, links, claims, decision packets done; full per-doc command validation not done |
| §10 | exact-SHA CI | done for `b2ea8a8` |
| §11 | decision packets | done (`docs/decisions/OWNER_DECISION_PACKETS.md`) |
| §12 | adversarial audit | done (below) |

**Adversarial audit (§12), answered:**
- Containment narrow? Yes, the scripted diff is privacy-only. Default tree
  clean? **No**, not until the owner merges.
- Pushes all confirmed with `ls-remote`. CI exact-SHA. Stub results labelled as
  such.
- Coverage denominator: every tracked product file, unimported ones at 0%.
- Gates: none weakened. Two tests were *strengthened* because they encoded
  defects (VME and restore), and the ruff and exception ceilings only went down.
- Backup safety improved (autosave). No authorization bypass added. Settings
  resolver unchanged. Silent handlers reduced with reasons. Import lineage
  preserved (byte-identical payloads). No new engineering formula without
  derivation. Docs: claims checked against code (CSV, WITSML/LAS, VME).
- I also caught one mistake of my own: a vacuous assertion in the new
  engineering test, where the field names always matched. It was rewritten and
  mutation-checked before commit.

## I. Owner actions

1. **P1 containment** (urgent): run `tools/privacy/contain_default_branch.sh`,
   push, open a PR to `drill-Master`, merge.
2. **P2 history purge** plus GitHub Support (PR refs #1–#4 and caches).
3. P3 read policy.
4. P6 Windows acceptance: the 12-item checklist and the installer procedure.
5. P4 licence.
6. P8 signing.
7. P7 backup deployment, on a separate disk.
8. P5 money D1–D7.
9. Tier-2 names in old reports.
10. Whether to pin CI runners to `ubuntu-24.04` before the `ubuntu-latest` →
    26.04 rollout (from 2026-10-19).

All packets: `docs/decisions/OWNER_DECISION_PACKETS.md`.

## J. Resume

- Verify `git ls-remote origin refs/heads/arena/72010272-drill-master`. If the
  local ref or clone was reset, repeat the §B recovery: temporary-index
  comparison, compare-and-swap `update-ref`, and `fetch --unshallow`. Never use
  `reset --hard`.
- Environment:
  `python3 -m venv .venv && .venv/bin/pip install -r requirements-lock.txt pytest==9.1.1 ruff==0.16.6 build==1.6.1 coverage==7.16.2 pyyaml pytest-cov hypothesis`.
  The libGL stub recipe is in part 1 §I. The stub needs version scripts for
  `LIBDBUS_1_3` and `V_0.5.0`.
- Gates before each push:
  - ruff population `core dialogs tabs tests` ≤ `.github/ruff-debt-ceiling.txt`;
  - `ruff check --select E722,F821 .`;
  - `tools/quality/exception_scan.py --check .github/exception-silent-ceiling.json`;
  - `tools/privacy/privacy_check.py`.
- Next, in order:
  1. Audit records for well and report deletes; make `log_audit` failures visible.
  2. An "unmapped populated cells" review diagnostic on the generic import path.
  3. The next `database.py` extraction (non-model code only).
  4. Workers for `w11_Export`, then the import dialog.
  5. Silent handlers in tabs (50).
  6. Optionally raise the coverage floor to just under 45.63%.
