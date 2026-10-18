# M42.13 — REL-13 same-SHA resolution, Windows lifecycle forensics, exact-tip CI reconciliation, controlled Windows-test readiness

**Report date:** 2026-10-18 (mission opened 2026-10-17). **Repository:** `asgareyvazi/Drill-master`, fixed branch `arena/72010272-drill-master`. Canonical current status remains [`PRODUCTION_READINESS.md`](../../PRODUCTION_READINESS.md); this file is the dated record and is the only place where run IDs and counts for this mission are written down.

Status labels have the meanings given in the mission: `PASS`, `FAIL`, `NOT_RUN`, `NOT_VERIFIED`, `UNKNOWN`, `BLOCKED_BY_PERMISSION`, `UNSIGNED`. Nothing in this report is release approval.

---

## 1. Verdict

| Question | Answer |
| --- | --- |
| Publication | **CHANGES PUBLISHED** — three commits are on `origin/arena/72010272-drill-master`, plus the commit that adds this report |
| Do all internal gates pass on the exact verified tip `fa92145b69b332240ffb6b34fad17bd02ff3c834`? | **Yes.** `SOURCE_GATE_GREEN_ON_EXACT_TIP` (Source release gate run 117, `39124603637`, Python 3.11/3.12/3.13 all success) and `WINDOWS_GATE_GREEN_ON_EXACT_TIP` (Windows release validation run 63, `39124603564`, all 11 steps success, `lifecycle=PASS`) |
| REL-13 | **`REL-13_CLOSED_FOR_STATED_CONDITION`** — closed on the limb *"the instability is explained"*; no protection relaxed (§4) |
| Signing | **`SIGNING_UNSIGNED`** — unchanged; no signing evidence exists |
| Controlled Windows test | **`CONTROLLED_WINDOWS_TEST_HANDOFF_BLOCKED`** on Arena's side, but only on byte verification: the artifact blob host is unreachable from the automation. A tester can unblock it in step 1 of §10 (`OWNER_ACTION_REQUIRED`) |
| External acceptance (signing, independent byte verification of the candidate, owner decisions, clean-machine and field acceptance) | **Open / `NOT_RUN`** — unchanged by this mission |
| Workspace | **`CLEAN_AND_PUBLISHED`** once this report commit is pushed: clean working tree, all 10 temporary refs deleted, all temporary worktrees removed |

**Headline finding.** The intermittent Windows lifecycle failure tracked as REL-13 since 2026-10-11 was **not** an external agent on the runner. It was a check-then-use race inside the gate's own post-launch listing: the `except FileNotFoundError` meant for a refused uninstaller launch also wrapped the settle loop, and that loop's `snapshot()` raced the uninstaller's deletion of the install tree. As a result the gate reported a launched, successful uninstall as a refused launch. Fixed in `1720b19` without relaxing anything; the race was then observed directly on the runner in a run that passed.

---

## 2. SHAs, base, commits

| Item | Value |
| --- | --- |
| Starting SHA (mission start) | `279a52fbfed89813162b16691183ecdff3fb77c4` |
| Verified code/record tip | `fa92145b69b332240ffb6b34fad17bd02ff3c834` |
| Final branch tip | the commit that adds this file (a child of `fa92145`, which adds only this file). Its exact-SHA runs are read from the live GitHub record and listed in the delivery message, following the M41 report convention. **A revision of this file requires a new exact-SHA run.** |
| Base before | `4336ea357fc1ae28ccca228cdf7873697cc4cd84` (`arena/01a0ec23-drill-master`) |
| Base after | `4336ea357fc1ae28ccca228cdf7873697cc4cd84`, unchanged; `merge-base` = base; `drill-Master` untouched at `e3fa42a3257e981d9bdf9d012c97919e3352a53a` |

**Commits (oldest first):**

| SHA | Kind | Summary |
| --- | --- | --- |
| `a64a2420d495209014b0b64ebdd393a5b1c07090` | evidence-only telemetry + records | Same-SHA re-run of `9f7f47f` recorded; read-only process lineage, Defender channel window, log first lines, the raising frame of the launch exception, and a checkpoint timeline. Verdict-neutral, which a test enforces |
| `1720b192274aec0458a38021ee9b7f0bce71bf8e` | **functional fix** (evidence-backed) | `snapshot()` absorbs only *absence* between listing and `stat`. Post-launch errors become `UninstallObservationError` (not an `OSError`; still a FAIL; never retried). Adds the evidence-only `uninstall_observation` and an Actions notice. 6 new tests |
| `fa92145b69b332240ffb6b34fad17bd02ff3c834` | records | REL-13 closed for its stated condition with the history preserved; checkpoint JSON appended (60+/0−); present-tense summary updated; guards tightened |
| *(this file)* | report | dated mission report |

Recovery note: at the start of the final working session the sandbox came back from a snapshot with the local branch ref at `4336ea3` and the working tree byte-identical to the pushed tip `a64a242`. `git diff origin/arena/72010272-drill-master` showed nothing. The ref was moved with a non-destructive mixed reset to the remote tip. No work was lost, nothing was force-pushed, and the scratch directory and venv (both outside snapshot persistence) were rebuilt.

---

## 3. Exact-SHA CI table

All rows were read back from `GET /repos/asgareyvazi/Drill-master/actions/runs` and `/runs/<id>/jobs|artifacts`. Every row's `head_sha` equals the SHA it is cited for. "Old incidence" rows run the **unfixed** lifecycle code.

| workflow | run ID | attempt | head_sha | conclusion | relevant step | artifact ID | interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Windows | 38522527259 (#39) | 1 | `9f7f47f06c90f6bb9787a52dc5af241756428bdc` | failure | lifecycle → `silent_uninstall FAIL` | — | original REL-13 incidence; untouched (still attempt 1; rerun endpoints `403`, `BLOCKED_BY_PERMISSION`) |
| Windows | 39007139449 (#43) | 1 | `2891f0f87bdb1100b503c052399dea993e048a66` | failure | lifecycle | — | old incidence |
| Windows | 39008646413 (#45) | 1 | `5b60268e5aed170d6a8827cb9299bac59708b3b0` | failure | lifecycle | — | old incidence |
| Windows | 39009214340 (#46) | 1 | `890c96be3b1a15527ce405596ba070e9b5bd9d7c` | failure | lifecycle | — | old incidence |
| Windows | 39009869902 (#47) | 1 | `46d27cfc36f2553dbe38b92a3c28ef9816b42ec1` | failure | lifecycle | — | old incidence |
| Windows | 39011107012 (#49) | 1 | `d1a7f9ebb4e2b1d02a681cab7bdb5def4fabad97` | failure | lifecycle | — | old incidence |
| Windows | 39011696219 (#50) | 1 | `279a52fbfed89813162b16691183ecdff3fb77c4` | failure | lifecycle | — | old incidence (mission start SHA) |
| Windows | 39014435340 (#51) | 1 | `9f7f47f06c90f6bb9787a52dc5af241756428bdc` | **success** | all 11 steps | 12094367942 | same-SHA re-run via temp ref; `signing=UNKNOWN`/`tests=767/770` prove the old tree ran |
| Source | 39014435392 (#105) | 1 | `9f7f47f…` | success | 3.11/3.12/3.13 | — | companion |
| Windows | 39016542280 (#52) | 1 | `a64a2420d495209014b0b64ebdd393a5b1c07090` | failure | lifecycle | 12095232521 | **the instrumented run**: published `raised=pathlib.py:840 in stat` (§5) |
| Source | 39016542279 (#106) | 1 | `a64a242…` | success | all | — | — |
| Windows | 39016546849 (#53) | 1 | `2891f0f…` | failure | lifecycle | 12094862341 | same-SHA re-run; identical signature again |
| Windows | 39016547536 (#54) | 1 | `5b60268…` | **success** | all | 12095735246 | same-SHA re-run green |
| Windows | 39016548783 (#55) | 1 | `890c96b…` | failure | lifecycle | 12094853771 | same-SHA re-run; identical signature again |
| Windows | 39016549649 (#56) | 1 | `46d27cf…` | **success** | all | 12095740228 | same-SHA re-run green |
| Windows | 39016551144 (#57) | 1 | `d1a7f9e…` | **success** | all | 12094882688 | same-SHA re-run green |
| Windows | 39016551983 (#58) | 1 | `279a52f…` | failure | lifecycle | 12094714735 | same-SHA re-run; identical signature again |
| Source | 39016546824…39016551985 (#107–#112) | 1 | the six SHAs above, respectively | success ×6 | all | — | companions |
| Windows | 39123732874 (#59) | 1 | `1720b192274aec0458a38021ee9b7f0bce71bf8e` | **success** | lifecycle PASS; `settle_polls=2 vanished=0` | 12135780957 | fix, branch push |
| Windows | 39123733676 (#60) | 1 | `1720b19…` | **success** | `settle_polls=2 vanished=0` | 12134623971 | fix, repeat ref 1 |
| Windows | 39123734819 (#61) | 1 | `1720b19…` | **success** | `settle_polls=2 vanished=0` | 12135721087 | fix, repeat ref 2 |
| Windows | 39123735919 (#62) | 1 | `1720b19…` | **success** | `settle_polls=2` **`vanished_while_listing=1`** | 12135656132 | **the race observed on the runner, in a run the old code would have failed** |
| Source | 39123732877, 39123733636, 39123734813, 39123735952 (#113–#116) | 1 | `1720b19…` | success ×4 | all | — | — |
| **Windows** | **39124603564 (#63)** | 1 | **`fa92145b69b332240ffb6b34fad17bd02ff3c834`** | **success** | all 11 steps; `lifecycle=PASS`; `tests=793/796`; `settle_polls=3 vanished=0` | **12136310366** | **`WINDOWS_GATE_GREEN_ON_EXACT_TIP`** |
| **Source** | **39124603637 (#117)** | 1 | **`fa92145…`** | **success** | 3.11, 3.12, 3.13 | — | **`SOURCE_GATE_GREEN_ON_EXACT_TIP`** |

Tally on the Windows workflow: unfixed code, runs 39–58: **11 failed, 9 passed**. Fixed code, runs 59–63: **5 passed, 0 failed**. If the unfixed failure rate (~55%) still applied, five consecutive passes would have about a 1.8% chance (0.45⁵). That supports the explanation; it is not the reason the row was closed.

Rerun/dispatch boundary (`BLOCKED_BY_PERMISSION`, unchanged): `POST /actions/runs/38522527259/rerun` and `/rerun-failed-jobs` and `POST /actions/workflows/windows-release-gate.yml/dispatches` → `403 Resource not accessible by integration` for the automation credential. Each was called once in this mission and not repeated. Same-SHA repeats were therefore produced by pushing the exact SHA to a temporary ref (no new commit; `head_sha` equality checked per run); all 10 temporary refs are deleted.

---

## 4. REL-13 — status and verbatim condition

**`REL-13_CLOSED_FOR_STATED_CONDITION`.** The register's condition, verbatim: *"a step that fails after the recorded retry while an earlier run of byte-identical code passed is an environment condition on the runner, not a packaging pass: it stays open until the same SHA is re-run green or the instability is explained; the protections must not be relaxed to obtain green"*.

- **Limb used:** *the instability is explained.* The row was not closed on a successor pass, on a rerun attempt, on a permission error, or on "no process found". The same-SHA greens (`9f7f47f`, `5b60268`, `46d27cf`, `d1a7f9e`) are recorded as such, and the three SHAs that failed again (`2891f0f`, `890c96b`, `279a52f`) are kept as failures, discharged by the explanation rather than by a pass.
- **Protections not relaxed:** the one bounded settle-and-retry for a genuine refusal, no relaunch once the uninstaller is gone, exit code 0, `{app}` must list empty after the settle, `install_files_removed`, `user_data_preserved`, and work-root deletion are all unchanged. A gate-contract guard pins this.
- **Reopens if:** a refused-launch shape recurs on the fixed code.
- **Where it is recorded:** the REL-13 row's status now begins `CLOSED for the stated condition *the instability is explained*`, followed by `History:` and the complete text that kept it `OPEN`, unchanged. A dated addendum carries the evidence and an explicit correction of the 2026-10-17 `890c96b` sentence *"no in-repository code path launches one there"* (that sentence was wrong and is kept as written). In the checkpoint JSON, `m42_13_followup.resolution_after_the_instrumented_run` is appended and the 2026-10-17 `causal_status: UNRESOLVED_INSUFFICIENT_TELEMETRY` is kept.

---

## 5. Forensic evidence, causal conclusion, confidence, unknowns

**Evidence chain:**

1. **Observed raising frame (run 52, `a64a242`).** The M42.13 attribution published `raised=pathlib.py:840 in stat`. The same run's manifest reports `python=3.12.10`. In CPython `v3.12.10` (`Lib/pathlib.py`, fetched from `python/cpython` at that tag), line 840 is `return os.stat(self, follow_symlinks=follow_symlinks)` inside `Path.stat`. **`Popen` did not raise.** The per-attempt record still read `launch=FileNotFoundError (errno=2,winerror=2)`, which is exactly the misattribution.
2. **Only one statement fits.** The `except FileNotFoundError` around `_uninstall()` enclosed its settle loop and final listing. On 3.12.10, `rglob` swallows `OSError` from `scandir` (`_select_from … except OSError: pass`; `Path.walk` ignores errors by default), `Path.is_file()` returns `False` for a missing path, `Path.exists()` ignores `ENOENT`, and `_bounded_tail` returns a state instead of raising. So inside that block the only call that can raise `FileNotFoundError` from `pathlib.py` is `snapshot()`'s `path.stat()` after `path.is_file()` returned `True`.
3. **Precondition seen on the runner.** Inno Setup's first-phase uninstaller hands off to a second-phase copy and returns while that copy is still deleting. Every fixed-code run reports `settle_polls=2` or `3`: the first listing after the launch returned still saw files.
4. **The race observed directly.** Run 62 (`1720b19`) reported `vanished_while_listing=1`: an entry was listed, confirmed as a file, and deleted before its size was read. That is the exact interval, in a run that passed and that the unfixed code would have failed.
5. **Reproduction in-repository.** A test deletes each listed entry inside `is_file()` once the uninstaller has been launched. Against the unfixed module (worktree at `a64a242`) this publishes, verbatim, *"unins000.exe was listed before launch and no launch completed; attempt 1: refused (…); settle: the uninstaller is gone (dir=present entries=0 root=present unins=absent uninslog=present)"*. Run 52 published *"attempt 1: refused (dir=present entries=0 root=present unins=absent launch=FileNotFoundError (errno=2,winerror=2) uninslog=present); settle: the uninstaller is gone (dir=present entries=0 root=present unins=absent uninslog=pr…"*. Five of the six new tests fail on the unfixed module and all six pass on the fix.
6. **It explains the whole history.** Every occurrence since 2026-10-11 showed an emptied tree, a deleted uninstaller and a written uninstall log, which is what a *successful* uninstall leaves. It also explains why the failure moved between SHAs and between runs of the same SHA: it is a timing race between two processes.

**Causal conclusion:** the gate's settle-loop listing raced the uninstaller's deletion, and the resulting `FileNotFoundError` reached the refused-launch handler. Classification: `EXPLAINED_GATE_LISTING_RACE`. Earlier hypotheses (antivirus quarantine, external interference, scheduled cleanup) are not supported. The `procs=ok/1` and `defender=ok` probe results in run 52 are consistent with this: nothing outside the gate's own uninstaller was involved.

**Confidence: high.** The frame was observed, the interpreter source was read, the code path is unique, the race was reproduced deterministically and observed on the runner, and the fixed code passed 5/5.

**Unknowns, stated rather than absorbed:**
- The `call_chain` field (the frames above `pathlib.py`) was clipped from the 1,345-character annotation. The job-log and artifact blob hosts (`productionresultssa*.blob.core.windows.net`) are outside this sandbox's network allowlist, so the caller frame is established from code and interpreter source, not read.
- Inno Setup's uninstall log beyond its first line was not read, for the same reason.
- Five green runs are a sample, not a rate. The `Uninstall observation` notice keeps the race visible on future runs.

---

## 6. Artifact integrity and selection

| candidate SHA | source gate | Windows gate | lifecycle status | digest verification | signature state | suitable for controlled smoke test? | limitations |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **`fa92145b69b332240ffb6b34fad17bd02ff3c834`** (artifact `12136310366`, `drillmaster-windows-fa92145…`, 321,722,453 B, expires 2026-11-17T11:54:16Z, GitHub digest `sha256:8391f63bd5927ba89a30b6eb45b62a6e480eaa01ac5351cce895882a5c4259b2`) | success (#117) | success (#63) | `PASS` on the runner | **`NOT_VERIFIED` by Arena.** The blob host is unreachable, so no bytes were downloaded. Published values to check: installer `DrillMaster-1.0.0-Setup.exe` 83,270,432 B `sha256=1ddabf57bc2e26b3a3ff039466bd05706803292136d5c4bde786854e2933d73b`; portable ZIP 119,941,400 B `sha256=50303d397f3b396942312831a86052136d845112ad852be3ec1aa29a2a9dfb74` | `UNSIGNED` (installer and inner `DrillMaster.exe` `NotSigned`; ZIP `NOT_APPLICABLE`) | **Yes, after the tester's own digest check**, as an unsigned build on a disposable machine only | unsigned (SmartScreen warning expected); bytes unverified by Arena; the build is not reproducible byte-for-byte across runs (installer sizes differ by run), so only the bytes of *this* artifact are covered by its digests |
| `1720b192274aec0458a38021ee9b7f0bce71bf8e` (artifacts `12135780957`, `12134623971`, `12135721087`, `12135656132`) | success ×4 | success ×4 | `PASS` ×4 | `NOT_VERIFIED` | `UNSIGNED` | superseded by `fa92145` (identical code; records-only delta) | same as above |
| REL-04 historical `MATCH` (artifact `11696022238`, run `38122859040`) | — | — | — | `ARTIFACT_BYTES_MATCH_FOR_SPECIFIC_ARTIFACT`, for **those bytes only**, by the external reviewer (M42.12). Arena did not download or verify them | `UNSIGNED` | no: older code, before this fix | does not extend to any other artifact |

---

## 7. Tests: commands, results, failure classification

Runner: `/home/user/.venv/bin/python` 3.11.2, pytest 9.1.1, `requirements-lock.txt` installed (PySide6 6.8.1.1), `ruff==0.16.6`. The repository's `addopts = "-q"` means an extra `-q` suppresses the summary line, so the counts below come from runs without it.

| Command | Result |
| --- | --- |
| `pytest tests/test_windows_release_evidence.py tests/test_windows_release_gate_contract.py tests/test_release_documentation_truth.py tests/test_acceptance_report.py tests/test_junit_report.py tests/test_m36_p6_accounting.py -p no:cacheprovider` on `fa92145` content | **413 passed, 0 failed** |
| The 6 new race tests against the unfixed module (`a64a242` worktree) | **5 failed, 1 passed** (the genuine-refusal test passes on both, by design) |
| Same 6 on the fix | **6 passed** |
| Mutation: REL-13 row closed "because a later run passed" | guard **fails** as intended ("a closed row has to name the limb of its condition it was closed on"); file restored |
| Full suite on tip `fa92145`: `pytest tests/ <18 --ignore> -p no:cacheprovider --tb=no` | **2230 passed, 63 failed, 45 skipped** (326.6 s) |
| Same command on mission-start baseline `279a52f` (temporary worktree) | **2209 passed, 63 failed, 45 skipped** |
| Failure-set difference tip vs baseline (`comm` both directions) | **0 new, 0 fixed**; +21 passed = the tests M42.13 added |
| `ruff check --select E722,F821 packaging/ tests/` | All checks passed |
| `verify_release.verify_lint()` | lint debt 5343 ≤ ceiling 5375 (unchanged) |
| `pip check` | No broken requirements |
| Windows regression suite in CI on `fa92145` | 793/796 passed (3 explicit platform skips) |

**Failure classification (63 failed + 18 uncollectable modules):** **environment, pre-existing.** All 63 failures were re-run with `--tb=long`, and every one traces to `ImportError: libGL.so.1: cannot open shared object file`: Qt cannot load in this headless sandbox. The 18 modules that cannot be collected fail on the same import. The installed-wheel smoke in `test_release_boundary_imports.py` is in the same class and fails identically on the baseline. **Regressions: 0. Inconclusive: 0.** No corpus test exists in this repository, so none is reported. The Windows CI suite, which has a working Qt, is the authoritative run for these modules.

`verify_release.py --expected-sha` cannot complete in this sandbox: it stops at pytest collection on the same 18 `libGL` modules after passing its git, dependency, version and lint stages. This is recorded as an environment limit, not a pass.

---

## 8. What was changed and what was deliberately not changed

- **Changed (functional, evidence-backed):** `snapshot()` absence handling, and the separation of post-launch errors from launch refusals. Evidence: §5.
- **Changed (evidence-only):** `diagnostics.uninstall_observation` and one `::notice title=Uninstall observation::` line, printed only when `GITHUB_ACTIONS=true` and after the verdict is fixed. A test checks the exit code is identical with and without it.
- **Guards:** one gate-contract guard that pinned the literal text of the emptiness check was re-anchored to the new form, with two additional assertions (the separation exists, and the observation error is not an `OSError`). The M42.13 guard that pinned `OPEN` now permits `CLOSED` only with the recorded explanation, the named limb, the verbatim condition and the preserved history. A new guard pins the resolution's evidence. **No assertion was weakened.**
- **Not changed:** the workflow file, thresholds, retry policy, packaging, the installer script, signing behaviour, and every protection listed in §4.
- **Not changed (records):** every earlier REL-13 sentence, the 2026-10-17 `causal_status`, the M42.7 paragraph (a dated note was added after it), and REL-04's independent-review provenance.

---

## 9. Remaining external prerequisites and owner actions (`OWNER_ACTION_REQUIRED`)

1. **Trusted code signing** — certificate procurement and CI secret provisioning by the repository owner. Until then every artifact is `UNSIGNED`.
2. **Byte verification of the candidate** — by the tester, in step 1 of §10. Arena could not reach the blob host.
3. **Controlled Windows smoke test** on a clean, disposable Windows 10/11 x64 machine (§10). `NOT_RUN`.
4. **Owner decisions A–D** in `PRODUCTION_READINESS.md` — unchanged, open.
5. **Field / real-world acceptance** (real DDR PDF, production database, operator/business acceptance) — `NOT_RUN`, unchanged.
6. **Monitoring:** on future Windows runs, read the `Uninstall observation` notice. A refused-launch shape on the fixed code reopens REL-13.
7. **Maintenance (not a blocker):** the runner warns that `actions/checkout@v4`, `actions/setup-python@v5` and `actions/upload-artifact@v4` target Node.js 20 and are being forced onto Node.js 24. No change was made without a decision.
8. **Optional:** a repository administrator may re-run run `38522527259` itself. It is no longer needed for REL-13.

---

## 10. Controlled Windows smoke-test handoff

**State:** `CONTROLLED_WINDOWS_TEST_HANDOFF_BLOCKED` on the Arena side only because the bytes are unverified. It becomes `CONTROLLED_WINDOWS_TEST_CANDIDATE_VERIFIED` **for these bytes** if step 1 matches.

**Candidate:** SHA `fa92145b69b332240ffb6b34fad17bd02ff3c834`; Windows run 63 (`39124603564`); artifact `12136310366` (`drillmaster-windows-fa92145b69b332240ffb6b34fad17bd02ff3c834`); available until 2026-11-17.

1. **Verify before running anything.** Download the artifact ZIP from the run page and check `Get-FileHash -Algorithm SHA256` = `8391f63bd5927ba89a30b6eb45b62a6e480eaa01ac5351cce895882a5c4259b2`. Extract it, then check `DrillMaster-1.0.0-Setup.exe` = `1ddabf57bc2e26b3a3ff039466bd05706803292136d5c4bde786854e2933d73b` (83,270,432 B) and `DrillMaster-1.0.0-windows-x64.zip` = `50303d397f3b396942312831a86052136d845112ad852be3ec1aa29a2a9dfb74` (119,941,400 B). **Any mismatch: stop and report.**
2. Use a disposable VM or clean machine with no production data. Expect a SmartScreen "unknown publisher" warning, because the build is `UNSIGNED`.
3. Install (interactive, or `/SILENT /DIR=<path> /LOG=<path>`), launch, confirm the main window and version 1.0.0, create one test well, then close the application.
4. Uninstall from *Apps & features*. Confirm `{app}` is empty afterwards and that the user-data folder is preserved.
5. Report pass/fail per step, with the install/uninstall logs and any error text, to the repository owner. The result is field evidence; it is not CI evidence and it is not release approval.

---

## 11. Scorecard (10 areas, 0–10 each)

| # | Area | Score | Basis |
| --- | --- | --- | --- |
| 1 | REL-13 root cause and closure | 9 | frame observed, mechanism reproduced and seen on the runner; caller frame inferred, not read |
| 2 | Lifecycle fix quality and tests | 9 | narrow, no relaxation, 6 discriminating tests, mutation-checked guard |
| 3 | Exact-tip CI reconciliation | 10 | both gates green on `fa92145` with full SHA equality |
| 4 | Same-SHA re-run evidence | 8 | 7 incidences re-run; original run 39 itself not re-runnable (`403`) |
| 5 | Record integrity and history preservation | 9 | append-only, verbatim condition kept, explicit correction |
| 6 | Local test evidence | 6 | 2230 pass, 0 regressions, but Qt/UI modules cannot run here |
| 7 | Artifact byte integrity | 2 | candidate bytes `NOT_VERIFIED`; only REL-04's older external `MATCH` |
| 8 | Code signing | 0 | `UNSIGNED` |
| 9 | Controlled / clean-machine Windows acceptance | 2 | handoff ready; `NOT_RUN` |
| 10 | Owner decisions and field acceptance | 1 | open / `NOT_RUN` |
| | **Total** | **56 / 100** | 9+9+10+8+9+6+2+0+2+1 = 56 |

The repository-side work (areas 1–6) scores 51/60. The external areas (7–10) score 5/40 and dominate what remains. **This is not release approval.**
