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
| Coverage, branch+line, product source (excl. tests/tools/packaging) | 44.24 % | not re-measured | `--cov=. --cov-branch` at `9060b08`; all measured files 60.85 %, `core/` 70.25 %; depressed by the libGL-only failures |
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
