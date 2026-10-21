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

---

# Part 3 — M43 final technical closure (2026-10-21)

Mission *DRILL-MASTER M43 — FINAL TECHNICAL CLOSURE PROGRAM*. Branch
`arena/72010272-drill-master`, from checkpoints code `b2ea8a8` / report
`49675d7`. Parts 1 and 2 are left as written; where this part supersedes a
statement there, it says so.

## A. Executive summary

**Final status: OWNER_GATED.** `RELEASE_READY` is excluded:
- the default branch still holds real operational data;
- history is not purged;
- Windows/operator acceptance, signing and the licence are open.

The build is **UNSIGNED**. No tag was created and no release binary was run.

**Real defects found and fixed in this mission.** Every fix has a test that
fails on the previous code; mutation checks are in §F.

| # | Area | Defect | Commit |
|---|---|---|---|
| 1 | import review (**data integrity**) | the import preview linked rows to payloads through a dict under `Qt.UserRole`, which PySide6 stores as a **copy**. Operator decisions and edits went to the copy, while confirm/apply read the canonical payloads: a review row could never be resolved, and an operator REJECT never reached the import boundary (reproduced on unmodified HEAD with one row) | `8ba64d9` |
| 2 | import review (UI) | the preview table was filled with sorting enabled: with N review rows only one showed its values | `8ba64d9` |
| 3 | audit | `delete_well` wrote no audit record; well/report saves audited after commit under `except: pass`. Now one transaction with rollback on audit failure | `047bf90` |
| 4 | audit | a mandatory audit FK to a user missing from the open database rolled back the business save; now `user_id NULL` plus the username | `98e0358` |
| 5 | import UI | a second click during an import started a second batch and dropped the first | `2f23d4a` |
| 6 | export | batch DDR files were all named `DDR__<date>` (the list had no `report_number`), so two reports on one date overwrote each other | `6ffb4f6` |
| 7 | export UI | 11 `processEvents()` calls re-entered the event loop; one failing engine aborted the whole batch | `6ffb4f6` |
| 8 | operations | `reset_database.py --help` went straight to the destructive "Type RESET" prompt | `c039f6b` |

**Main structural results:**
- unexplained silent handlers 157 → **83** (tabs 50 → 0, dialogs 18 → 0,
  `main_window` 6 → 0; remaining: core 81, `app.py` 2);
- Export Center in a worker thread with its own read-only connection;
- second `database.py` extraction;
- independent engineering golden tests;
- coverage floor 45.2 → 45.5 on three CI runs;
- documented-command validation matrix.

## B. Git evidence (§14.4)

| Item | Value |
|---|---|
| Session start | local ref reset by the sandbox to the fork point `4336ea3`; recovered non-destructively to the remote `49675d7` (fetch, temporary-index comparison, compare-and-swap `update-ref`, `fetch --unshallow`) |
| Second sandbox reset (during phase 6) | local ref again at `4336ea3`; the working tree differed from the pushed `b8d2031` in exactly the 6 intended uncommitted export files. Same recovery; nothing lost. The venv and the libGL stub were rebuilt |
| Commits | `047bf90` `e29b2da` `1388b5b` `98e0358` `2f23d4a` `48f988c` `842553d` `8ba64d9` `b8d2031` `6ffb4f6` `b56b4a5` `c039f6b` `1c2de6b` `53b4138`, plus the report commit |
| Final code tip | `53b41385087c319704455981e8ed59866eb3055a` (`git ls-remote` confirmed; exact-SHA CI green, §D) |
| Report tip | the commit that adds this part (docs only); its exact-SHA CI is recorded in the final hand-off, since a report cannot contain its own SHA |
| Banned operations | none: no reset --hard, clean -fdx, force-push, rebase, filter-repo or PR-ref change. The containment branch was **not** pushed (owner-gated) |
| End state | clean tree; local HEAD = remote (`git status`, `git ls-remote`) |

## C. Phase results

| Phase | Result | Status |
|---|---|---|
| 0 Baseline | git state recorded; prior claims re-measured (2870 passed / 4 skipped on the stub runtime) | VERIFIED |
| 1 Containment | isolated clone at `e3fa42a`: `59adcda`, tree `7f3c9ca4f68d24724123de5bcd1109aee671c3c2`, privacy-only diff, 0 findings, 0 of 18 protected blobs | build VERIFIED; push, PR and merge **OWNER_GATED** |
| 2 Audit | delete/save paths audited in the same transaction, rollback on failure, `log_audit` classified; 23 tests, 4 mutants | VERIFIED |
| 3 Import | populated-but-unused cells reported (sheet and location only, value-free, deterministic, outside the fingerprint); re-entrancy guard; preview decision defects (§A 1–2) | VERIFIED; extraction and persistence still run on the UI thread (§E) |
| 4 Structure | `get_actual_vs_plan` computation extracted (`core/database.py` 10,547 → 10,471); tabs/dialogs/`main_window` silent handlers 74 → 0; coverage floor raised with a multi-run margin | VERIFIED |
| 5 Engineering | independent goldens (§F); VME oracle; old casing method ID stays stable on saved runs | VERIFIED (screening scope only) |
| 6 UI | Export worker (§F); import-worker assessment (§E); `QUndoStack`, `tr()` and theme tokens: assessed, not implemented | export VERIFIED; rest NOT_RUN |
| 7 Docs | `docs/COMMAND_VALIDATION_MATRIX.md`: 128 commands in 22 files classified, safe ones run in a disposable clone; one defect found (§A 8) | VERIFIED |
| 8 CI | runners pinned (`ubuntu-24.04`, `ubuntu-26.04`, `windows-2022`); action SHAs verified against their tags, all `node24`; 3.11–3.13 matrix; exact-SHA gates in §D | VERIFIED |
| 9 Decisions | P3 now states that service filters do not stop direct SQLite access; new P9 (Tier-2 identifiers, counts only) | done |
| 10 Adversarial audit | §H | done |

**Correction to Part 2:** its "Main gap" for security and audit ("well/report
deletes not audited", "`log_audit` swallows errors") is superseded by
`047bf90`. Part 2's CI recommendation to pin `ubuntu-24.04` is also stale: the
workflows were already pinned.

## D. Exact-SHA CI (GitHub REST `actions/runs?head_sha=<full sha>`)

| SHA | Source release gate | Windows release validation | Coverage (3.12 leg) |
|---|---|---|---|
| `2f23d4af5bb197ebce7eff941d716b687feb8985` | `39561312736` ✓ | `39561312739` ✓ | 46.17% (33540/72649, 188 files) |
| `b8d20315bd9a31e15af42cb783bd64bee0155094` | `39563513622` ✓ | `39563513741` ✓ | 46.40% (33717/72663, 188 files) |
| `6ffb4f6c58a305ce0c584ec90272770cca22ad25` | `39571865489` ✓ | `39571865358` ✓ | 47.03% (34262/72848, 189 files) |
| **`53b41385087c319704455981e8ed59866eb3055a` (final code tip)** | `39574662578` ✓ (3.11 / 3.12 / 3.13) | `39574662698` ✓ (UNSIGNED artifact) | 47.02% (34263/72864, 189 files); floor 45.50% |

**Local gate in a disposable clone of `6ffb4f6`, stub runtime.**
`verify_release.py --expected-sha` returned rc 0: collected 2960, passed
2956, skipped 4, failed 0; wheel built; `PACKAGE_SMOKE_OK schema=6`.

The integration subset (`-m integration tests/test_ddr_acceptance.py`)
exits 0, but both tests **skip** because they need a real DDR. That
acceptance is **NOT_RUN** by privacy policy.

**Final tree full suite (stub runtime):** **2966 passed, 4 skipped, 0 failed**
(590 s).

`047bf90` and `e29b2da` were cancelled or red at the time and do not count. A
run counts only when its full head SHA equals the commit and it concluded
`success`.

## E. Honest open technical gaps

- **Import worker: NOT done.** Extraction and persistence still run on the UI
  thread, with a busy guard and atomic persistence (about 9 s for a
  20,000-row sheet). Doing it properly needs three things:
  1. extraction in a worker;
  2. the modal preview kept in the UI thread;
  3. persistence through a separate *writable* connection with the same audit
     and authorization semantics.

  The application's `StaticPool` engine shares one SQLite connection across
  threads, so writing from a worker on that connection is unsafe. That
  writable-connection design is the next step and was not started.
- **No cancel in the middle of persistence**, by design: persistence is a single
  atomic transaction. Cancel works before persistence and between export files.
- **Silent handlers in `core/`: 81** remain unexplained (the ceiling enforces
  that the number cannot grow).
- **UI:**
  - 11 `processEvents()` calls remain: import dialog 3, login 1, smart template
    1, schematic 1, `main_window` 2, `app.py` 3;
  - `setStyleSheet` 502;
  - no `QUndoStack` and no `tr()`; Persian/RTL is not localised.

  Undo is deliberately not faked for irreversible database mutations.
- **Engineering:**
  - stiff-string, pressure-area buoyancy and ISCWSA remain UNSUPPORTED;
  - casing is a pipe-body screening check, not full casing integrity;
  - `CasingEngine.METHOD` is engine-wide, so the r2 bump marks every pre-fix
    saved casing run `method_matches=False`, even when burst and collapse still
    match. This is accepted: verification covers the whole result.
- **Import formats:** CSV is conversion-only; WITSML and LAS are placeholders.
- **`money_audit`** creates SQLite `-wal`/`-shm` side files; amounts are still
  `Float` (P5).
- **`log_audit` caller classes:**
  - security: login (`app.py`), authorization denials;
  - mandatory: deletes, owned saves, import lineage, survey edits, safety
    reviews, account administration;
  - best-effort: the `main_window` import summary, `w2_Daily_Report`, the rest.

## F. Evidence (tests and mutation checks)

| Package | Tests | Mutants killed (clean bytecode cache each run) |
|---|---|---|
| Atomic audit (`047bf90`, `98e0358`) | `tests/test_audited_mutations.py` (23) | 4 |
| Unmapped-cell diagnostic (`e29b2da`) | `tests/test_import_unmapped_content.py` (7) | 3 |
| Import re-entrancy (`2f23d4a`) | `tests/test_import_dialog_reentrancy.py` (5) | 2 |
| Engineering goldens (`48f988c`) | `tests/test_engineering_independent_golden.py` (14): MCM on an exact 3-D circle, kill MW / ICP / FCP / MAASP from 231 in³/gal, kill-sheet volumes from π and 9702 in³/bbl, bit ΔP from SI Bernoulli with Cd 0.95, invalid inputs 0, −1, NaN, inf. Rounded field constants (0.052, 10858, 1930) are bounded explicitly | 6 (pipe capacity, ICP sign, no Cd, jet velocity, MCM tangential, kill without TVD) |
| VME oracle (`48f988c`) | `tests/test_casing_vme_independent.py` (9): Lamé 2×2 solve, cap force balance, √(3·J₂) over 6 cases, thin-wall limit, method-ID semantics | 3 (missing π, hoop pe term, VME factor) |
| Tab handlers (`842553d`) | buoyancy refusal path in `tests/test_single_source_guard.py` | 2 |
| Import preview (`8ba64d9`) | `tests/test_import_preview_bulk_decisions.py` (7, real offscreen widgets) | 4 (sort during fill, dict link, broad except, index fallback) |
| Export worker (`6ffb4f6`) | `tests/test_export_worker.py` (20): plan names and order, collisions, ok/failed/error/cancelled, privacy of errors, own read-only connection, restore gate, authorization state, **byte-equal output (timestamps masked) via the worker connection for EOWR, NPT, Cost and DDR**, widget duplicate guard, cancel, shutdown wait | 9 |
| Extraction (`b56b4a5`) | `tests/test_actual_vs_plan_summary.py` (6) plus 3 existing DB-level files | 2 |
| Reset CLI (`c039f6b`) | `tests/test_reset_database_cli.py` (4, subprocess) | 2 |

**Full suite (local, libGL *stub* runtime: stub evidence only; CI is
authoritative):** 2870 (baseline) → 2905 (`2f23d4a`) → 2936 (`b8d2031`) →
2956 (`6ffb4f6`) → **2966** (final tree) passed, 4 skipped, 0 failed, at each
checkpoint.

**Metrics (`b2ea8a8` → final):**

| Metric | Before | After |
|---|---|---|
| Ruff debt (gated population) / ceiling | 751 / 751 | **750 / 750** |
| `E722,F821` | 0 | 0 |
| Unexplained silent handlers (ceiling) | 161 at `b2ea8a8`; 157 at the mission start | **83** (core 81, `app.py` 2, rest 0) |
| `core/database.py` lines | 10,482 at `b2ea8a8`; 10,547 after the audit work | **10,471** |
| `processEvents()` calls | 22 | **11** |
| `setStyleSheet` | 502 | 502 |
| Coverage floor | 45.2% | **45.5%** (CI 45.63 / 46.17 / 46.40%) |
| Schema version | 6 | 6 (one read-model key added; no migration) |
| Privacy check, whole tree | 0 findings | 0 findings |

## G. Scorecard (13 areas, rubric-based)

Rubric:

| Score | Meaning |
|---|---|
| 0–2 | absent |
| 3–4 | partial |
| 5–6 | core with gaps |
| 7–8 | robust, with negative tests, CI and limits |
| 9 | strong operational evidence |
| 10 | mature, with acceptance |

**No area can score 9–10 while owner-gated risks remain.** The baseline is
the supplied input. The *target* is what the next work package can reach;
it is never used as evidence.

| Area | Baseline | Score | Target | Progress / evidence | Main risk | Next | Owner need |
|---|---|---|---|---|---|---|---|
| Engineering core | 8.0 | 8.0 | 8.0 | independent goldens, mutation-checked | no field validation | keep goldens green | field validation |
| Advanced engineering | 6.0 | 6.0 | 6.5 | VME oracle; method-ID semantics | stiff-string / pressure-area / ISCWSA unsupported | cited sources before any formula | — |
| Import | 7.0 | 7.0 | 7.5 | review-decision integrity defect fixed; unmapped-cell diagnostic; re-entrancy | UI-thread extraction and persistence; CSV, WITSML and LAS gaps | worker with a writable connection | — |
| DB | 5.0 | 5.5 | 6.0 | atomic audit; second extraction; worker read-only connection | 10.5k-line `database.py`; `Float` money | further extractions | P5, P7 |
| Security | 5.5 | 5.5 | 5.5 | reset-CLI hardening; authorization state carried to the worker | read policy undecided; direct file access | — | P3 |
| Audit | 7.0 | 7.5 | 8.0 | mandatory audits atomic with rollback tests; callers classified | best-effort callers remain | promote w2 if required | — |
| UI | 5.0 | 5.5 | 6.0 | export worker; preview defects fixed; re-entrancy | 11 `processEvents`, no `tr()`/undo | import worker | P6 |
| Tests | 8.5 | 8.5 | 8.5 | +9 test files, 37 mutants killed this mission | stub runtime locally | — | — |
| CI | 7.0 | 7.5 | 7.5 | pins verified (node24); multi-run coverage floor; exact-SHA gates | — | — | — |
| Code structure | 3.5 | 4.0 | 4.5 | extraction 2; Qt-free export module | very large files | extraction 3 | — |
| Error handling | 5.5 | 6.5 | 7.0 | UI layers at 0 unexplained silent handlers | core 81 | core groups | — |
| Docs | 4.0 | 5.0 | 5.5 | 128-command matrix; one defect found; stale claims corrected | historical records not re-run | — | P9 |
| Privacy | 2.0 | **2.0** | 2.0 until the owner acts | tree clean; packets ready | default branch **not contained**; history not purged | — | **P1, P2** |

## H. Adversarial audit (§13), answered

- **Containment narrow?** Yes: the scripted diff is privacy-only. **Is the
  default tree clean?** No; `drill-Master` = `e3fa42a` still holds the data.
- **Pushes:** every push was confirmed with `git ls-remote`. CI claims use full
  SHAs, concluded `success`; cancelled runs are excluded. Stub results are
  labelled as stub.
- **Gates:** none weakened or skipped; ceilings only went down (ruff 751 → 750;
  silent 157 → 83). The coverage floor was raised, not set equal to any single
  run, and no omit pattern was added.
- **Tests encoding defects?** None found this mission. No test was weakened.
  The preview tests failed on HEAD before the fix.
- **New thread safety:** the worker never shares the UI's connection. It uses
  `mode=ro`, so it cannot write; it is drained by the restore gate; and no ORM
  object crosses a thread.
- **Privacy:**
  - errors surface the exception type only (tested with a value-bearing
    message);
  - the P9 count was reported as numbers only;
  - no real data was used; the real-workbook acceptance command was
    deliberately not run.
- **No new formula.** The goldens are independent derivations from unit
  definitions. Rounded field constants are bounded, not hidden.
- **Mistakes of my own, caught before commit:**
  1. a first golden mutation run was invalidated by stale bytecode and a
     pattern that matched the wrong function; it was re-run with cleared
     caches and an exact-count anchor;
  2. a narrowed `except EngineeringError` would have raised `NameError` (no
     import in scope); a test now covers that path;
  3. an export test that could have been vacuous (an engine that legitimately
     returns false) now requires success for every engine except Plan.

## I. Weighted work-package inventory and progress estimate

Method:
- each package gets a weight (sum 100), set by risk and size before the
  scoring;
- completion is 1.0 for VERIFIED, 0.5 when the agent's part is verified but an
  owner step remains or half the scope is done, and otherwise the verified
  fraction of the listed scope;
- progress is Σ weight × completion.

The estimate describes this programme's scope, not product readiness.

| Package | Weight | Completion | Contribution | Basis |
|---|---|---|---|---|
| P0 baseline | 5 | 1.0 | 5.0 | recorded and re-measured |
| P1 containment | 15 | 0.5 | 7.5 | build verified; push, PR and merge are owner steps |
| P2 audit | 10 | 1.0 | 10.0 | 23 tests, 4 mutants |
| P3 import | 10 | 0.8 | 8.0 | diagnostic, re-entrancy, preview fix; worker not done |
| P4 structure | 10 | 0.7 | 7.0 | extraction, UI silent handlers 0, floor; core 81 open |
| P5 engineering | 10 | 0.9 | 9.0 | goldens and VME; stale-result semantics for casing only |
| P6 UI | 10 | 0.4 | 4.0 | export worker; import worker, `tr()`, theme and undo not done |
| P7 docs | 8 | 1.0 | 8.0 | matrix |
| P8 CI | 7 | 1.0 | 7.0 | pins, runners, exact-SHA gates (§D) |
| P9 packets | 5 | 1.0 | 5.0 | P3 and P9 |
| P10 adversarial | 5 | 1.0 | 5.0 | §H |
| Final report | 5 | 1.0 | 5.0 | this part |
| **Total** | **100** | | **80.5** | of which 7.5 points are blocked only by the owner |

## J. Owner actions and resume

**Owner actions (packets in `docs/decisions/OWNER_DECISION_PACKETS.md`):**
1. **P1 containment (urgent):**
   1. run `tools/privacy/contain_default_branch.sh` in a clone at `e3fa42a`;
   2. `git push origin HEAD:refs/heads/privacy/default-branch-containment`;
   3. `gh pr create --base drill-Master --head privacy/default-branch-containment`;
   4. review that the diff is privacy-only, then merge.
2. P2 purge plus GitHub Support (PR refs #1–#4); include P9 in `--replace-text`.
3. P3 read policy.
4. P6 Windows/operator acceptance.
5. P4 licence.
6. P8 signing.
7. P7 backup placement.
8. P5 money.

**Resume:**
- verify the branch with `git ls-remote`; after a sandbox reset, use the §B
  recovery, never `reset --hard`;
- environment: Part 2 §J; the libGL stub recipe is in Part 1 §I;
- run the gates before each push (Part 2 §J).

Next technical steps, in order:
1. import worker with a dedicated writable connection;
2. silent handlers in `core/` (81);
3. `database.py` extraction 3;
4. remaining `processEvents` (login, schematic, smart template);
5. `tr()` and theme tokens, one tab at a time.
