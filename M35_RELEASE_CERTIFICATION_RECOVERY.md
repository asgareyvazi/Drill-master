# M35 — RELEASE-CERTIFICATION RECOVERY

> **Historical Mission 35 record.** Its Git identity and verdicts describe the recorded M35 session, not the current branch. Current release status: [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

Forensic first, implementation second. Every statement below was re-derived in this session; no M34
number was accepted because it appeared in a report. Where M34 is contradicted or narrowed, it is
said explicitly.

---

## A. Ground truth

| Fact | Value (re-derived this session) |
|---|---|
| Branch checked out | `arena/01a0c945-drill-master` |
| HEAD | `c28bbef37cbac9de7abcfa693e7e21f678fa74ab` (tree `7e16996cdcc1bce4a79fed8823371c20c74eef15`) |
| Upstream | **none configured** |
| Remote | `origin  https://github.com/asgareyvazi/Drill-master.git` |
| Synchronisation | **LOCAL-ONLY BRANCH — NOT SYNCHRONIZED TO GITHUB** (`gh api` re-query: 6 remote branches, `arena/01a085e0-drill-master` = `c28bbef`, target branch → 404) |
| Clone depth | shallow (object database holds exactly `c28bbef` + `02053eb`; `HEAD^` does not resolve) |
| Stashes | 0 |
| Worktree | 89 modified tracked, 280 untracked, **0 deleted** |
| Index | 2 staged (`A core/operational_time.py`, `A core/safety_semantics.py`) — population 371 paths at capture (372 with this mission's manifest file) |
| M33 SHA `a9d7dede…` | **ABSENT** (git object lookup; also absent: `dc5939c8…`, `964e922a…`, `beaf963…`, `fb857d7…`, `0bbcbd4…`, `716e8f…`) |
| Commits after `c28bbef` | none locally, none on the remote |
| M34 artefacts | **untracked** (present in the worktree, in no commit, in no remote branch) |

No reset / checkout / stash / clean / discard / restore / delete / history rewrite was performed.
`docs/audits/m34-evidence/` is byte-identical to a pre-session backup (verified with `diff -rq`).

## B. M34 claim verification

| M34 claim | Verdict | Evidence produced here |
|---|---|---|
| Distribution cannot start: required modules missing from the built artifact | **VERIFIED** | independent tracked-population wheel → `ModuleNotFoundError: core.operational_time` at `main_window.py:44 → tabs/w10_Planning_Widget.py:19`; `drillmaster --package-smoke` exit 1 from `/tmp/m35/run` with `env -i` |
| Exactly two modules differ between the tracked and full wheels | **VERIFIED** | wheel manifests differ by exactly `core/operational_time.py`, `core/safety_semantics.py` |
| The repository's own release gate fails on this tree | **VERIFIED** | `verify_release.verify_wheel()` → `False` before the fix, `True` after (package-smoke OK) |
| Ledger size and disposition arithmetic (11 554; 7 333/2 880/1 224/51/17/49; EI 0) | **VERIFIED** | independent recount of `carried_records` (8 934) + `new_records` (2 620) = 11 554; disposition recount identical to the declared map; **0** `EVIDENCE-INCOMPLETE` records |
| Fresh sweep of 5 802 hits (3 182 already covered + 2 620 new) | **VERIFIED** | independent re-implementation of the family table: 5 802 identical occurrences, **0 lost**, +34 new hits = M35's own regression file |
| "HIGH 371" | **PARTIALLY VERIFIED** | 371 is the **open** HIGH subset; the ledger contains 372 HIGH records (1 terminal) |
| No CRITICAL items | **VERIFIED** | 0 records with priority CRITICAL |
| Evidence freshness | **VERIFIED** | 0 stale `source_sha256` values, 0 referenced files missing across all 11 554 records |
| Full suite 1 814 passed / 4 skipped, 0 fail / 0 error | **VERIFIED** | M34 junit: tests 1 818, passed 1 814, skipped 4, 315.5 s |
| Commit-1 staging simulation 86 files, self-contained, 0 unclassified | **VERIFIED** | an independently written classifier reproduces M34's class for **every** overlapping path (0 differences) |
| M34 §3 "M32 fixes 10/10, M33 fixes 3/3 re-verified" | **NOT RE-CHECKED** | only the packaging/regression axis was re-run this mission; the per-fix contract probes were not re-executed (reported, not inherited) |
| M34 document-truth scan (11 CURRENT-VERIFIED / 98 HISTORICAL / 36 UNRESOLVED SHAs) | **NOT RE-CHECKED** | out of scope of the packaging-critical path; the numbers remain M34's, unverified |

M34's earlier statement that the wheel stages passed is contradicted by execution and was already
disclosed by M34 itself as the packaging defect; this mission reproduces the defect and closes it.

## C. Packaging root cause

* **Why the checkout works.** `core/` and `tabs/` are namespace packages without `__init__.py`;
  imports resolve against loose files on disk. Two of those files (`core/operational_time.py`,
  `core/safety_semantics.py`) were never added to the index, so any build whose source is the
  tracked population simply does not contain them.
* **Why the wheel fails.** `pyproject.toml` (setuptools) discovers packages with
  `packages.find include = core* dialogs* tabs* config* ui* templates*` and `py-modules = [app,
  main_window, run]`. Discovery is not the defect — the tracked wheel contains 127 `core/*.py`
  modules and the full wheel 129, i.e. namespace discovery works. The defect is that the *source
  population* lacked the two files. `drillmaster` → `app:main` → `main_window` →
  `tabs/w10_Planning_Widget.py:19` → `ModuleNotFoundError`.
* **Which modules, why required.** `core/operational_time.py` (`summarize_time_logs`) is imported by
  the report engine, DDR PDF export, operations intelligence, actual-vs-plan, database, planning and
  analysis tabs; `core/safety_semantics.py` (`safety_kpis`) by operations intelligence. Both are
  inside the static import closure of `app:main` (142 modules).
* **Fix chosen (minimal).** Track the two modules. No discovery change, no package re-structure, no
  `__init__.py` added, no shim, no placeholder. Verified: the wheel built from the tracked population
  now contains every required module and starts.

## D. Release artifact matrix

Generated by `tools/m35/release_matrix.py` → `docs/audits/m35-evidence/m35-release-artifact-matrix.json`
(wheel sha256 `3046bf4c…`, sdist sha256 `034ab175…`; 186 wheel entries / 343 sdist entries).

| Component | on disk | tracked | in sdist | in wheel | installed importable | runtime-required modules |
|---|---|---|---|---|---|---|
| `core/` | 129 | yes | 129 | 129 | yes | 99 |
| `dialogs/` | 20 | yes | 20 | 20 | yes | 20 |
| `tabs/` | 19 | yes | 19 | 19 | yes | 19 |
| `ui/` | 2 | yes | 2 | 2 | yes | 2 |
| `config/` | 2 | yes | 2 | 2 | yes | 0 |
| `templates/` | 0 (6 JSON) | yes | yes | yes | yes | 0 |
| `app.py` / `main_window.py` / `run.py` | 3 | yes | 3 | 3 | yes | 2 |
| `core/operational_time.py` | 1 | **yes (was no)** | **yes (was no)** | **yes (was no)** | **yes (was no)** | yes |
| `core/safety_semantics.py` | 1 | **yes (was no)** | **yes (was no)** | **yes (was no)** | **yes (was no)** | yes |

No package ships incompletely; no untracked shipped file remains; the wheel contains no `tests/`,
no `docs/`, no `__pycache__`.

Rebuild check: a wheel rebuilt from the current tracked population has the identical 175 Python
modules and contains both required modules; the archive hash differs from the recorded one only
because wheels embed build timestamps (content-identical, byte-different).

## E. Semantic inventory

| Metric | Value |
|---|---|
| TOTAL records | **11 554** (8 934 carried + 2 620 new) |
| VERIFIED-CORRECT | 7 333 |
| INTENTIONAL-BY-DESIGN | 2 880 |
| DEFECT-FIXED / EXTERNAL-ACCEPTANCE-ONLY / REMOVED-WITH-EVIDENCE | 51 / 17 / 49 |
| OPEN before this review | 1 224 (all `UNDER-REVIEW`; **EI = 0**) |
| Individually reviewed this mission | 14 sites covering **29** ledger items |
| Closed from that review | **25** — 15 INTENTIONAL-BY-DESIGN, 10 VERIFIED-CORRECT (0 closed without a quoted contract) |
| Still open from that review | **4** (2 sites, questions recorded) |
| **OPEN after this review** | **1 199** (346 HIGH, 853 MEDIUM) |
| CRITICAL | **0** |
| Stale-evidence records | **0** |

**Method.** The ledger was re-derived independently (`tools/m35/verify_inventory.py`, own scanner,
family table read verbatim for comparability): arithmetic, disposition map, freshness and sweep
coverage all reproduce. Every open item was then rehydrated against the current tree into a register
(`m35-open-item-register.json`) that states, per item: file, symbol, line, rule, priority, domain,
context fingerprint, source hash, question, missing fact, why it matters, where the answer lives,
classification and confidence. Nothing was clustered, pattern-matched, or closed because a
neighbour was closed. The 25 closures each quote the governing contract (inline comment, docstring,
schema comment, declared type/initialiser, callee return contract, or an in-block domain rule) — see
`m35-contract-adjudications-final.json`.

Two examined items remain open with named questions because the repository does not decide them:

1. `tabs/w5_Equipment_Widget.py:771/772` — the file's own comment calls the permission gate
   authoritative ("Read-only roles must never mutate equipment/inventory … Gate Q") while the
   handler silently continues if the control itself fails (fail-open). The canonical pattern
   elsewhere is a direct module-level import (16 sites, only 3 inside a `try`). **Security-owner
   decision:** fail-closed, or report-and-continue.
2. `core/database.py:4223/4224` — an unparseable `report_date` string is passed through to a `Date`
   column. **Decision:** reject/raise at the persistence boundary? Reachability from an unvalidated
   import path (`core/ddr_import_service.py:509`) is not established.

The remaining 1 199 are recorded as **OPEN / REQUIRES-DOMAIN-DECISION with a per-item question**;
they were **not** mass-classified as verified, and they are the primary reason for the verdict below.

### Domain and hygiene audits (E2)

* **Operational time (§12)** — `docs/audits/m35-evidence/m35-operational-time-audit.json`.
  Authoritative representation: **naive UTC for audit timestamps** (`core/database.py:17-19`
  `_now_utc()` — documented as UTC without tzinfo for SQLite), **`Date` columns for business dates**
  (`report_date`, `spud_date`, rig-move, start-hole), **hours for durations**. 49 `datetime.now()`
  sites are display-only (footer/export filenames/status); all 52 persistence assignments use
  `_now_utc()`. No tz-aware arithmetic exists, so DST cannot corrupt stored durations. The operational
  day is a local calendar day with `24:00` as a legal end-of-day value and explicit midnight-crossing
  duration handling (`core/time_utils.py`, `core/import_quality.py:434-447,621-625`).
  `summarize_time_logs` keeps absence distinct from zero through the installed artifact
  (`total_hours=None` with `known_hours=4.0`; recorded zero stays zero); `safety_kpis` keeps
  "absence is not safe" (`days_without_lti=None`, `total_lti=0.0`). **No semantic change warranted**;
  one convention inconsistency recorded, not changed (`core/data_quality.py:273` uses local-naive
  `isoformat()` inside a returned evidence payload that is not persisted).
* **Duplicates/dead code (§13)** — nothing was deleted. The mission's additions are one test file,
  four tool files and nine evidence files; no production module was modified, duplicated or
  superseded, and the production tree contains no import of `tools/` (0 matches).
* **Database/migrations (§18)** — no schema change in the candidate change set: the only tracked
  change is two *previously untracked* modules plus a test; no model, column, constraint or index is
  touched, so no migration is required and none was written. The app creates schema from
  `Base.metadata` with a `schema_version` table; the candidate commits add no DDL.
* **Security/hygiene (§19)** — 0 credential-shaped literals in the candidate files; the wheel ships
  no `docs/`, `tests/`, `__pycache__`, databases or logs; the audit/evidence corpus is outside
  `packages.find` and confirmed absent from both artifacts; the new test writes only into
  `tempfile` directories and leaves no repository artefacts.

## F. Changes made

| File | Change | Reason | Evidence | Regression |
|---|---|---|---|---|
| `core/operational_time.py` | added to the index (byte-identical to the worktree file, sha256 `8e12b6bb…`) | required at import time by the release entry point; absent from both commit trees, not generated, not ignored, no duplicate definition | `git ls-files` lists it; wheel/sdist/installed import all now contain it | `tests/test_release_boundary_imports.py` (fails when untracked) |
| `core/safety_semantics.py` | added to the index (sha256 `19ae3cc1…`) | same | same | same |
| `tests/test_release_boundary_imports.py` | new release-boundary regression (3 tests) | the release boundary was untested: the suite ran inside the checkout where loose files mask a missing index entry | builds the wheel from `git ls-files`, checks every required module against the archive, installs into an isolated target and starts `app.main() --package-smoke` from outside the checkout | mutation-validated: untracking either module fails 2/3 tests, then hashes restored byte-identically |

No production behaviour was changed. No file was deleted, renamed or moved. No `__init__.py` was
added. No placeholder, shim or duplicated code was introduced.

## G. Validation (exact commands, exit status)

| Layer | Command | Result |
|---|---|---|
| Focused | `pytest tests/test_release_boundary_imports.py -q` | **3 passed**, exit 0 |
| Mutation | `git rm --cached core/operational_time.py` → same test | **2 failed** (ModuleNotFoundError class reproduced), restore verified `8e12b6bb…` worktree == index; repeated for `safety_semantics.py` (`19ae3cc1…`) |
| Packaging | `python -m build --wheel --sdist` from the tracked population | wheel 1 037 281 B, sdist 1 198 622 B, exit 0 |
| Wheel inspection | `zipfile` listing + `entry_points.txt` | 186 entries, `console_scripts drillmaster = app:main`, no tests/docs |
| Clean install (wheel) | fresh venv (26/26 lock pins) + `pip install`; `env -i … drillmaster --package-smoke` from `/tmp/m35/run` | exit **0** |
| Clean install (sdist) | fresh venv + `pip install drillmaster-1.0.0.tar.gz`; same command | exit **0** |
| Import smoke (D) | 9 previously broken consumers imported from `site-packages` | exit 0; `summarize_time_logs` → `known_hours=4.0, total_hours=None`; `safety_kpis` → `days_without_lti=None, total_lti=0.0` |
| Entry points (E) | every declared console script + `python -m app` (checkout and installed) | exit 0 each |
| No repo-relative loads (F) | `any('Drill-master' in p for p in sys.path)` → False; `app.__file__` under the installed target | exit 0 |
| Repo gate | `verify_release.verify_wheel()` | **True** (was False) |
| Repo gate stages | `verify_repository` / `verify_dependencies` / `verify_resources` / `verify_version` / `verify_lint` | False (dirty worktree, by design) / True / True / True / True |
| Integration marker | `pytest -m integration -q` | **1 passed, 3 skipped, 1 817 deselected**, 16.4 s, exit 0 |
| Full suite | `pytest -ra -q --junitxml=…` | **1 821 tests, 1 817 passed, 4 skipped, 0 failed, 0 errors, 334.2 s** |
| Static | `python -m compileall` ; `ruff check --select E722,F821 .` ; `ruff check core dialogs tabs tests` | exit 0 ; All checks passed ; **5 338** debt ≤ ceiling **5 375** (no increase) |
| Independent inventory | `tools/m35/verify_inventory.py` | arithmetic identical, 0 stale hashes, re-sweep 5 802 + 34 new, 0 lost |

Skipped (classified): 2 real-DDR acceptance tests (unset input files), 1 real MinerU integration
(unset input), 1 Windows bundle test (no Windows bundle). These are environment-bound, not passes.

## H. Remaining blockers

1. **1 199 open semantic records (346 HIGH)** — each carries a question and an evidence target; the
   per-item method is demonstrated (29 items reviewed → 25 closed on quoted contracts), but the
   remaining items have not been adjudicated individually. They are open, not verified.
2. **Two decision items with named questions** (§E): the fail-open permission gate and the
   unparseable `report_date` pass-through.
3. **Worktree is not clean** — 89 modified tracked files and 280 untracked paths inherited from
   M25–M34, classified in the manifest but not committed; `verify_repository()` therefore reports
   False by design.
4. **External boundary unchanged**: Windows runtime, native Qt, real MinerU, production-document
   acceptance → NOT-RUN / NOT VERIFIED (headless stub Qt only).
5. **Branch is local-only** — nothing is on GitHub; pushing is out of scope for this mission.

## I. Commit readiness

**PACKAGING CLOSED AND COMMITTED; SEMANTIC INVENTORY STILL OPEN** (see M35_FINAL_REPORT.md).

This report was written before the continuation mission made Git persistence mandatory; the
continuation then committed the work (see below). The packaging blocker — the only release-critical
defect found — is fixed, independently verified and now committed. The semantic inventory is **not**
closed: 1 199 records remain open (346 HIGH, 0 CRITICAL). They stay OPEN rather than being declared
"domain decisions" because my own review showed unexamined items are often repo-decidable (25 of 29
examined items closed from quoted contracts), and a mass classification without evidence is
forbidden by the mission.

Commit candidate A (now committed as `02dfc5c5…`; manifest
`docs/audits/m35-evidence/m35-commit-manifest.json`):

| File | sha256 | Size |
|---|---|---|
| `core/operational_time.py` | `8e12b6bb8f0f88e2060f37cd6e617ca754086cfa28aeb29ec6a0c1093b1ef4c6` | 1 651 B |
| `core/safety_semantics.py` | `19ae3cc15bc00ba9547c013f52e927a8f9cfcb5761c01e3bbf131212971b0a15` | 624 B |
| `tests/test_release_boundary_imports.py` | `5cf7243846a61912d5d5cac5cead5aed77ea953c91e0843d9713e2fa523a8a56` | 10 564 B |

The remaining population paths are classified in the manifest: 84 behavioural files from earlier
missions (committed in commit B once the committed tree proved unable to start), 280 audit/evidence
paths (M35's own committed in commit C; the M27–M34 corpus deliberately left untracked), 5 evidence
JSONs > 5 MB flagged for a provenance decision. The independent classifier agrees with M34's staging
simulation on every overlapping path (0 differences).

**Smallest next mission** — finish the evidence pass:

1. Adjudicate the 346 open HIGH records in batches exactly as demonstrated (read the site, quote the
   contract, close INTENTIONAL/VERIFIED, otherwise record the question).
2. Obtain the two owner decisions in §E and either fix with a killing regression or record
   ACCEPTED-LIMITATION.

Commits were created (continuation mission §18, Git persistence mandatory) — no push, PR, merge or
remote change was made:

* `02dfc5c5b8f7dade0a592ea182b250ed32da0419` — fix(packaging): the two tracked modules + the
  release-boundary regression;
* `09b5b5b47c6a81e0c4fc7e46400159e83d5fdcf8` — chore(release): the committed tree realigned with the
  tested release population (an artifact from the pre-B committed tree failed with
  `ImportError: cannot import name 'bootstrap_password_for_role' from 'core.database'`);
* audit commit — this report, `M35_FINAL_REPORT.md`, `docs/audits/m35-evidence/`, `tools/m35/`;
  the exact SHA is in `docs/audits/m35-evidence/m35-commit-ledger.json`.

Verified after the commits: a wheel built from `git archive HEAD` contains both required modules
(129 `core/*.py`), installs into a fresh venv (26/26 lock pins) and starts
`drillmaster --package-smoke` from outside the checkout with **exit 0** and zero
`ModuleNotFoundError`/`ImportError`/`Traceback` lines. That closes the release-boundary objective;
the semantic inventory (§E) remains the open axis.
