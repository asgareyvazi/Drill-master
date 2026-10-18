# M42.15 — Release evidence hardening, Actions runtime migration, latest-candidate verification and Windows acceptance handoff

- **Date:** 2026-10-18
- **Repository / branch:** `asgareyvazi/Drill-master`, `arena/72010272-drill-master`
- **Starting SHA (local = remote, clean):** `015279354980dc84388b9dfc0dbc933103d857ea` (the M42.14 report commit)
- **Base branch `drill-Master`:** `e3fa42a3257e981d9bdf9d012c97919e3352a53a` before and after; not modified
- **The M42.14 report is unchanged.** This file appends to it.
- **This is not release approval.** No `RELEASE-APPROVED` state exists, signing is `UNSIGNED`, owner decisions are open, and field acceptance is `NOT_RUN`.

## 1. Verdict

| label | scope |
|---|---|
| `ARTIFACT_BYTES_MATCH_FOR_SPECIFIC_ARTIFACT` | artifacts `12135787858`, `12136310366`, `12137427788` and `12138339192`, each scoped to its own ID and SHA (§4). Computed on GitHub-hosted runners, not in the Arena sandbox and not on a tester's machine |
| `CONTROLLED_WINDOWS_TEST_CANDIDATE_VERIFIED` | artifact `12137427788`, built by Windows run #66 on the final M42.14 tip (§8) |
| `SOURCE_GATE_GREEN_ON_EXACT_TIP`, `WINDOWS_GATE_GREEN_ON_EXACT_TIP` | `3cb7b267933cfef4d0ebc8a510548c003a1d57c9`, the last code-bearing commit (§3). The commit that adds this report changes documentation only; its own runs are read back after it is pushed and are not claimed here |
| `REL-13_CLOSED_FOR_STATED_CONDITION` | unchanged. Runs 66–68 show `Uninstall observation: status=PASS exit=0`, and the refused-launch shape did not recur |
| `SIGNING_UNSIGNED` | every artifact. The run signing records read `UNSIGNED/NotSigned`, and the PE headers have no certificate table |
| `OWNER_ACTION_REQUIRED` | §9 |

## 2. Phase 0 — starting state

- **Workspace:** porcelain v2 was empty. The only ignored content was `__pycache__/` and `.ruff_cache/`. `git diff --check` was clean, with no stashes and no extra worktrees.
- **Refs:** `HEAD` = `origin/arena/72010272-drill-master` = `ls-remote` = `015279354980dc84388b9dfc0dbc933103d857ea`, and `drill-Master` = `e3fa42a3…`.
- **Recovery:** none was needed.

## 3. Phase 1 — exact-SHA run reconciliation (live API; all `push` on `arena/72010272-drill-master`, attempt 1)

Workflow numbers are not API IDs; both are given.

| workflow | # | API run ID | head_sha | jobs (conclusion, image) | artifact |
|---|---|---|---|---|---|
| Source release gate | 120 | 39129842559 | `015279354980dc84388b9dfc0dbc933103d857ea` | 3.11 / 3.12 / 3.13 success (`ubuntu-24.04`) | — |
| Windows release validation | 66 | 39129842579 | `015279354980…` | `windows-release` success (`windows-2022`), job 117682569907 | `12137427788` |
| Artifact byte verification | 2 | 39132444862 | `4b254ea99b59b36bd6fa9fc308996c56aa237f28` | `ubuntu-24.04` and `ubuntu-26.04` success | — |
| Source release gate | 121 | 39132444854 | `4b254ea9…` | 3 × success | — |
| Windows release validation | 67 | 39132444944 | `4b254ea9…` | success, job 117690192942 | `12138339192` |
| Artifact byte verification | 3 | 39133211183 | `3cb7b267933cfef4d0ebc8a510548c003a1d57c9` | `ubuntu-26.04` success, job 117692424545 | — |
| Source release gate | 122 | 39133211186 | `3cb7b267…` | 3 × success | — |
| Windows release validation | 68 | 39133211223 | `3cb7b267…` | success, job 117692424742 | `12138712308` (not byte-verified) |

**Reconciling the M42.14 record:**
- M42.14's committed table ends at runs #119/#65 on `42d2972`. That is correct, because it was written before the report commit existed.
- Runs #120 (Source) and #66 (Windows) are the gates on the report commit `0152793`, as the M42.14 hand-off said. Their live `head_sha` equals that SHA, both succeeded, and every job succeeded.
- **Packaged code:** `git diff 42d2972 0152793` is documentation only. Artifact `12137427788` therefore packages the same application, packaging and gate code as `42d2972`, `d9fecba` and `fa92145`.
- **Expiry:** every artifact in this report is unexpired. The earliest expires on 2026-11-17.

## 4. Phases 2–3 — verifier audit, hardening, and the artifacts verified

### 4.1 Adversarial audit findings

These are settled from the code and the build's own contract, not assumed.

| finding | evidence | action |
|---|---|---|
| **Run identity was unbound.** The verifier checked the artifact API's `workflow_run.id`/`head_sha`, but nothing proved the build *passed*. The candidate's `run_number`, `run_attempt` and `source_gate_run_id` were static JSON that certified themselves | M42.14 code had no run-record input | **Fixed.** `windows_run_binding` and `source_run_binding` check the live `GET /actions/runs/<id>` records: `completed`/`success`, the same full SHA, workflow path, branch (from the registry), run number and attempt. The workflow downloads those records live |
| **Signing-record binding was partial.** M42.14 checked the aggregate, the installer and exe digests, and the container digest only when present. It did not validate the schema or bind `source_sha` or `release_metadata_sha256`, and duplicate rows collapsed silently in a dict | `release_metadata.validate_signing_document` (schema `drillmaster-signing-status/v2`, required `source_sha`/`release_metadata_sha256`) and `acceptance_report.read_signing_evidence(binding=…)`, which binds manifest digest, source SHA, installer row and container rows and requires the bundled executable | **Fixed** by reusing the build's own consumer, so there is no second implementation, with a binding computed from the observed bytes. The fix also requires exactly one `DrillMaster.exe` row bound to the portable ZIP, hashing the executable it actually carries, with per-row status equal to the aggregate |
| **`signing_configured_in_build`** | derived from whether the build scripts reference `signtool` (`windows_release_evidence.py` line 1960). The contract allows `UNSIGNED` while configured, for example without credentials | **Not a defect.** Published as observed; it is not enforced as a contradiction (test pins this) |
| **Lifecycle binding was partial.** M42.14 checked `status` and `installer_hash_verified` only | `read_lifecycle_evidence` also requires non-empty steps, all `PASS`. The generator records `installer_sha256` as the digest of the installer it *executed* (line 660) | **Fixed:** the build's reader is used, and the executed-installer digest and filename must equal the shipped installer |
| **A signed claim could not be verified** but was accepted as a candidate state | the PE read can show only the presence or absence of a certificate table, not trust | **Fixed:** candidate schema accepts only `UNSIGNED`. A present table is reported as "present, trust not evaluated" |
| **The candidate entry was unvalidated.** A malformed entry crashed with `KeyError` | — | **Fixed:** `candidate_problems` runs before any byte is read. Registry errors exit 2, a verifier crash exits 3, and a failed check exits 1 |
| **CRC failure was not terminal.** Later checks could decompress damaged members | `bundle.open` on a corrupt deflate stream raises | **Fixed:** nothing runs after a failed `zip_crc` (test corrupts the installer itself) |
| **Archive safety items re-verified, no change needed:** streaming hash, early refusal on size/digest, path rules, case-fold duplicates, special file types, exactly-once members, `SHA256SUMS` rows (missing, extra, malformed and duplicate names via `len(sums) == len(parsed)`), and duplicate manifest rows (refused by `validate_document`; test added) | code read and tests | the claims stay as narrow as the code: structural checks are defence-in-depth behind the outer digest, not semantic allowlisting of the bundle's contents |

**Tests:** `tests/test_verify_artifact_bytes.py` went from 27 to 65.
- **Fixture:** it now builds records shaped like the build's real output (signing schema v2 with installer, container-bound exe and `NOT_APPLICABLE` ZIP rows; a lifecycle record with steps and the executed installer digest). The 27 M42.14 assertions are unchanged.
- **Mutation testing:** 12 mutations, each removing one new protection, were all caught: signing binding, lifecycle installer binding, run SHA, run conclusion, candidate schema, exe-row digest, exe-row count, CRC terminality, signed-candidate refusal and PE table. Two initially survived; both exposed an untested path, and both now have a test.
- **Also added:** a runtime test that the archive's bytes and mtime are unchanged and that no temporary file remains; a truncated-archive test; CLI exit-code tests; and a preservation test pinning the M42.14 candidates' digests.

### 4.2 Candidate registry

`docs/audits/m42-14-evidence/artifact-candidates.json` gained a `branch` field, an `m42_15_addition` note and two entries. The two M42.14 entries are byte-identical: the diff deletes no line of them.

Every new value was parsed programmatically, before any download, from:
- the live artifact API;
- the live Windows and Source run records;
- the build job's `Windows release manifest` notice.

### 4.3 Expected vs observed

The observed values come from the verifier's published notice. `sha256sum` was computed independently in the same job.

| artifact (run, source) | item | expected (source) | observed | sha256sum | result |
|---|---|---|---|---|---|
| `12137427788` (#66, `015279354980dc84388b9dfc0dbc933103d857ea`) | outer | 321675645 B, `e8365a0a21b107bf182ca41879b7a82516737731da07f88dadf0ae6a63f0d7e1` (API) | identical | identical | MATCH |
| | installer | 83224510 B, `a05a6aa2444a0b3cd9d1968d728977a168490dd12ef634ead34a0cf5e298a248` (manifest) | identical | — | MATCH |
| | portable ZIP | 119941400 B, `d89a57944b10439d7feb1e1b1552e941dd04a4f9c4bcad068551f19aa79c0b64` (manifest) | identical | — | MATCH |
| `12138339192` (#67, `4b254ea99b59b36bd6fa9fc308996c56aa237f28`) | outer | 321707829 B, `a50d505505811d002a6649f1b55e28a376ba10278145b3a373ea0056fb876af0` | identical | identical | MATCH |
| | installer | 83255842 B, `95af1eb998ff8b1de82d71cad8e043b454c82dc72f54d3bc324cb3efb869627b` | identical | — | MATCH |
| | portable ZIP | 119941400 B, `94fbb83ee038d414a51c9e9eefb3e93a8bc95ec0b74c6e5caab73d2695dfd3a0` | identical | — | MATCH |
| `12135787858` (#64, `d9fecba…`) | outer / installer / portable | as recorded in M42.14 | identical | identical | MATCH (re-verified with 18 checks) |
| `12136310366` (#63, `fa92145…`) | outer / installer / portable | as recorded in M42.14 | identical | identical | MATCH (re-verified with 18 checks) |

**Checks per artifact (18), all `PASS` in run 39133211183 (`ubuntu-26.04`):**
1. `live_api_binding`, `windows_run_binding`, `source_run_binding`.
2. `archive_size`, `archive_sha256`.
3. `zip_crc`, `member_paths`, `member_layout`, `required_members`.
4. `installer_bytes`, `installer_pe_signature`, `portable_zip_bytes`, `portable_exe_pe_signature`.
5. `sha256sums_binding`, `release_metadata_binding`, `acceptance_report_binding`, `signing_record_binding`, `lifecycle_record`.

In run 39132444862, the three then-registered artifacts passed the same 18 checks on both `ubuntu-24.04` and `ubuntu-26.04`. `12138339192` passing shows the verifier accepts output from `upload-artifact` v7.0.2; its default `archive: true` keeps the ZIP layout.

**Scope:** each match covers its artifact ID only. It shows that GitHub serves the bytes its build recorded, and that those bytes are structurally sound and consistent with every build record. It does **not** verify any tester's downloaded copy, it is not verification outside GitHub, and it makes no reproducibility claim: every build differs byte-for-byte.

## 5. Phase 4 — Actions runtime and runner-image migration

**Node runtime.**
- **Timeline:** per GitHub's changelog, runners have used Node 24 by default since 2026-06-16, and Node 20 was removed on 2026-09-23, with the opt-out gone.
- **Prior state:** every workflow referenced `actions/checkout@v4`, `actions/setup-python@v5` and (Windows gate) `actions/upload-artifact@v4`. The upstream `action.yml` at each of those tags still declares `node20`, which is why every run carried the "forced to run on Node.js 24" warning.
- **Upstream verification:** all values were read from the official repositories through the GitHub API. Each tag resolves to the pinned commit (`GET /repos/actions/<action>/commits/<tag>`).

| action | pinned commit | tag | `runs.using` | inputs used / defaults |
|---|---|---|---|---|
| actions/checkout | `3d3c42e5aac5ba805825da76410c181273ba90b1` | v7.0.1 | node24 | default inputs; `persist-credentials: false` added in the verification workflow only |
| actions/setup-python | `5fda3b95a4ea91299a34e894583c3862153e4b97` | v7.0.0 | node24 | `python-version`, `cache`, `cache-dependency-path` all still present. v7 removed only `pip-install`, which is unused |
| actions/upload-artifact | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` | v7.0.2 | node24 | `name`, `path`, `if-no-files-found`, `retention-days` present. `archive` defaults to `true` and `compression-level` to `6`, as in v4 |

- **Result:** the gates on `4b254ea` and `3cb7b26` succeeded with zero Node 20 warning annotations in all five jobs.
- **Guard:** a new test requires every `uses:` in every workflow to be a full commit SHA with its release tag in a comment.

**Runner image.**
- **The announcement:** per actions/runner-images#14748, the `ubuntu-latest` label moves to Ubuntu 26.04 between 2026-10-19 and 2026-11-19.
- **Evidence on both images:** the complete verifier ran on each.
  - `ubuntu-24.04` (image 20261012.334.1): Python 3.12.15, gh 2.102.0, GNU coreutils 9.4.
  - `ubuntu-26.04` (image 20261012.163.1): Python 3.12.15, gh 2.102.0, and **uutils 0.10.0** as `sha256sum`, a Rust reimplementation rather than GNU coreutils.

  Both produced identical hashes for every artifact, so on 26.04 the cross-check comes from a third, independent SHA-256 implementation.
- **Production choice:** the verification job now runs on the explicit `ubuntu-26.04` label. `ubuntu-24.04` is the documented, tested fallback. The Source gate (`ubuntu-24.04`) and the Windows gate (`windows-2022`) already pin explicit images and are unaffected by the label migration; they were not changed.

**Workflow robustness.** The verification workflow now:
- keeps `contents: read` / `actions: read` permissions, with no secrets and no `set -x`;
- downloads the live artifact, Windows run and Source run records per candidate;
- fails the job on any verifier exit other than 0 (including a crash, exit 3), on any download failure (an expired artifact fails here), or on a `sha256sum` that disagrees with the expected digest;
- deletes each downloaded archive after use;
- writes an evidence notice and a step summary;
- adds a `workflow_dispatch` path for re-checking the registered candidates (the dispatch API returns 403 to this session, so only the owner can use it);
- extends the push filter to the verifier's imported modules (`release_metadata.py`, `acceptance_report.py`) and its test.

Before pushing, the script was dry-run locally with a fake `gh` serving a synthetic artifact: one good candidate passed, and a bad one raised two errors with exit 1.

## 6. Phase 5 — tests

Interpreter: CPython 3.11.2, pytest 9.1.1, ruff 0.16.6 (sandbox).

| command | result |
|---|---|
| `python -m pytest tests/test_verify_artifact_bytes.py -p no:cacheprovider` | 65 passed; also passed on both runner images (in CI, Python 3.12.15) |
| `python -m pytest tests/test_windows_release_gate_contract.py tests/test_release_documentation_truth.py tests/test_verify_artifact_bytes.py` | all passed (after the doc edits) |
| `pytest` over the 13 release/acceptance/metadata/windows/signing/doc-truth test files | 575 passed, 15 failed (rc 1). **All 15 are members of the unchanged baseline failure set** (Qt subprocess smoke tests needing `libGL.so.1`) |
| full suite `pytest -p no:cacheprovider --tb=no -rfE --continue-on-collection-errors` | **2295 passed, 63 failed, 45 skipped, 18 collection errors** (rc 1) |
| M42.14 baseline | 2257 passed, 63 failed, 45 skipped, 18 errors |
| `ruff check` on the changed Python files (repository config) | clean |

- **Delta:** +38 passed, exactly the new verifier tests. The 63-failure set and the 18-error set are **node-for-node identical** to M42.14, with no new and no missing nodes.
- **Classification:** the 18 errors are Qt view-model modules failing to import `libGL.so.1`, and the 63 failures are the same libGL class.
- **Not green:** these results are not called green. No product code was changed for the headless environment, and the Windows CI suite remains the Windows platform evidence.

## 7. Lifecycle (REL-13) status

- **Observations:** run 66 recorded `vanished_while_listing=1`, and runs 67 and 68 recorded `=0`; all three show `status=PASS exit=0 emptied=True`.
- **Conclusion:** the race path occurs and is handled, and the refused-launch shape has not recurred. No lifecycle code changed in M42.15, and REL-13 stays closed for its stated condition.

## 8. Controlled Windows-test handoff — artifact `12137427788`

| field | value |
|---|---|
| run | Windows release validation #66, API run `39129842579`, attempt 1 — <https://github.com/asgareyvazi/Drill-master/actions/runs/39129842579> |
| source SHA | `015279354980dc84388b9dfc0dbc933103d857ea` (application and packaging code identical to `42d2972` / `d9fecba` / `fa92145`) |
| gates on that SHA | Source #120 (`39129842559`) success on 3.11/3.12/3.13; Windows #66 success |
| artifact | `drillmaster-windows-015279354980dc84388b9dfc0dbc933103d857ea`, ID `12137427788`, expires 2026-11-17T13:10:27Z |
| outer ZIP | 321675645 bytes, SHA-256 `e8365a0a21b107bf182ca41879b7a82516737731da07f88dadf0ae6a63f0d7e1` |
| installer | `DrillMaster-1.0.0-Setup.exe`, 83224510 bytes, `a05a6aa2444a0b3cd9d1968d728977a168490dd12ef634ead34a0cf5e298a248` |
| portable | `DrillMaster-1.0.0-windows-x64.zip`, 119941400 bytes, `d89a57944b10439d7feb1e1b1552e941dd04a4f9c4bcad068551f19aa79c0b64` |
| signing | **UNSIGNED.** Windows shows "Unknown publisher", and SmartScreen may warn |

If this artifact becomes unavailable before testing, `12135787858` (M42.14 handoff, verified again here) is the fallback; its values are in the M42.14 report §8.

**Environment:** Windows Sandbox or a disposable Windows 10/11 x64 VM with a snapshot.
- No production database, no real credentials and no confidential files.
- Collect logs before closing a Sandbox, because closing it discards everything.

**Steps (PowerShell)**
1. Download the artifact from the run page (section *Artifacts*, signed in) with the browser, so the ZIP stays intact.
2. Check the outer ZIP. **Both lines must print `True`; if either prints `False`, stop.**
   ```powershell
   $p = "$HOME\Downloads\drillmaster-windows-015279354980dc84388b9dfc0dbc933103d857ea.zip"
   (Get-Item -LiteralPath $p).Length -eq 321675645
   (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash -eq 'e8365a0a21b107bf182ca41879b7a82516737731da07f88dadf0ae6a63f0d7e1'
   ```
3. Extract it, then check the files you will use and the records that describe them, **before running anything**:
   ```powershell
   $d = "$HOME\Downloads\dm-test"; Expand-Archive -LiteralPath $p -DestinationPath $d
   $r = Join-Path $d 'DrillMaster-release-39129842579'
   (Get-FileHash -Algorithm SHA256 (Join-Path $r 'DrillMaster-1.0.0-Setup.exe')).Hash -eq 'a05a6aa2444a0b3cd9d1968d728977a168490dd12ef634ead34a0cf5e298a248'
   (Get-FileHash -Algorithm SHA256 (Join-Path $r 'DrillMaster-1.0.0-windows-x64.zip')).Hash -eq 'd89a57944b10439d7feb1e1b1552e941dd04a4f9c4bcad068551f19aa79c0b64'
   Get-Content (Join-Path $r 'SHA256SUMS.txt')          # exactly two lines, the two hashes above
   $m = Get-Content (Join-Path $r 'release-metadata.json') -Raw | ConvertFrom-Json
   $m.git_sha                                             # 015279354980dc84388b9dfc0dbc933103d857ea
   $m.artifacts | Format-Table filename, size_bytes, sha256
   (Get-AuthenticodeSignature (Join-Path $r 'DrillMaster-1.0.0-Setup.exe')).Status   # NotSigned
   ```
4. Install by running `DrillMaster-1.0.0-Setup.exe` (administrator rights; default `C:\Program Files\DrillMaster`). For this hash-verified file only, you may proceed through SmartScreen's unknown-publisher prompt. Do not change SmartScreen or Defender settings.
5. **First-run checklist:**
   - **(a)** Record the Windows edition/build, the date, the source SHA and the installer hash.
   - **(b)** Launch the app. Note any startup error or crash dialog.
   - **(c)** Complete first-run credential setup with a throw-away password. Never reuse a real one, and don't write it down in the report.
   - **(d)** Open each main tab once, then sign out and back in.
   - **(e)** Create one clearly synthetic project/report.
   - **(f)** Close the app through its normal exit, reopen it, and confirm the synthetic data is still there.
   - **(g)** Confirm data is in `%LOCALAPPDATA%\DrillMaster` (`drillmaster.db`, `logs\`), not under `Program Files`.
   - **(h)** Uninstall through *Settings → Apps*. Confirm the program folder is gone and `%LOCALAPPDATA%\DrillMaster` remains.
   - **(i)** Optionally, unzip the portable ZIP elsewhere and launch `DrillMaster.exe` once.
6. **Send back:**
   - the `True`/`False` output of steps 2–3;
   - `%LOCALAPPDATA%\DrillMaster\logs\drillmaster.log`;
   - an installer log if setup misbehaved (`DrillMaster-1.0.0-Setup.exe /LOG="$HOME\Desktop\dm-setup.log"`);
   - screenshots of any error;
   - one line per checklist item: pass, or what happened.

   Review text files before sending and remove anything resembling a password, token or private path. **Never send** `drillmaster.db`, `config\ai_settings.json` (it can hold API keys), backups, production data or credentials.

**Stop immediately, without installing or running further, if:**
- any check prints `False`;
- `SHA256SUMS.txt` or the metadata disagree with the hashes above;
- the signature status is anything other than `NotSigned`;
- Defender reports a detection;
- the app crashes or the installer asks for unexpected things;
- data is written under `Program Files`;
- uninstall deletes `%LOCALAPPDATA%\DrillMaster`.

Report what you saw; do not work around it.

**A passing smoke test is evidence for REL-07 and part of REL-08. It is not approval**, and it does not touch signing, the owner decisions or field acceptance.

## 9. Phase 8 — owner decisions and remaining prerequisites

| ID | current status | exact evidence / decision required | owner | effect while open |
|---|---|---|---|---|
| Downloaded-copy hash (REL-04 operator step) | `NOT_RUN` | the tester's step 2–3 output (`True` ×4) for artifact `12137427788`, returned | tester | no claim about the copy actually installed |
| REL-07 clean-machine install | `NOT_RUN` | §8 checklist executed and its results returned | field/QA owner | no clean-machine evidence |
| REL-08 upgrade/uninstall retention | `NOT_RUN` | install an earlier candidate first, then this one; uninstall; data retained | field/QA owner | upgrade path unproven |
| A / REL-02 code signing | `OWNER_DECISION`; `UNSIGNED` | an owner-controlled certificate or hosted signing service, secrets configured in CI by the owner, and a signing step in `build_windows.ps1`/`DrillMaster.iss` | product owner | SmartScreen/enterprise trust unaddressed; `signing_status` cannot become `PASS` |
| B | precondition met; owner acceptance outstanding | the owner records acceptance of the determinate signature-state attribution | product owner | stays formally open; blocks nothing in engineering |
| C / REL-05 reproducibility | `OWNER_DECISION` | decide whether byte-reproducible builds are required | product owner | claims stay "this run produced these bytes" (confirmed again: every build differs) |
| D / REL-06 POSIX permissions | `OWNER_DECISION` | a documented mode-bit policy for the portable ZIP | product owner | non-Windows extraction needs `chmod` |
| REL-09 / REL-10 / REL-11 | `NOT_RUN` | real DDR Excel, real PDF/MinerU, production database and field validation | business/technical and operations owners | no production, operator or field acceptance |
| REL-12 (`NEW-P6-007/-008/-015/-020/-023/-024`) | `OWNER_DECISION` | six P6 decisions recorded | product owner | carried unchanged |
| Admin rerun of run 38522527259 (optional) | `BLOCKED_BY_PERMISSION` for this session | an admin re-runs it | repository admin | historical only |

The engineering scope limits in `PRODUCTION_READINESS.md` are unchanged. No new development workstream was opened.

## 10. Commits

| commit | content |
|---|---|
| `4b254ea99b59b36bd6fa9fc308996c56aa237f28` | verifier hardening (run bindings, build-contract signing/lifecycle binding, candidate schema, CRC terminality, exit codes); tests 27 → 65; registry third candidate and `branch`; all workflow actions pinned to Node 24 commit SHAs; verification matrix on both images |
| `3cb7b267933cfef4d0ebc8a510548c003a1d57c9` | verification job on explicit `ubuntu-26.04`; registry fourth candidate |
| (this commit) | this report; `PRODUCTION_READINESS.md` checkpoint wording (no run counts); a dated M42.15 record appended to the REL-04 row |

## 11. Scorecard (same ten areas; M42.14 baseline 61)

| # | area | M42.14 | M42.15 | reason |
|---|---|---|---|---|
| 1 | REL-13 root cause and closure | 9 | 9 | unchanged; three more passing observations |
| 2 | Lifecycle fix quality and tests | 9 | 9 | unchanged code |
| 3 | Exact-tip CI reconciliation | 10 | 10 | run #120/#66 reconciled to `0152793` from live records |
| 4 | Same-SHA rerun evidence | 8 | 8 | reruns still 403 |
| 5 | Record integrity and history preservation | 9 | 9 | appends only; M42.14 entries pinned by a test |
| 6 | Local test evidence | 6 | 6 | +38 mutation-checked tests; failure set identical; still environment-limited |
| 7 | Artifact byte integrity | 7 | **8** | verifier now binds live run records and the build's own signing/lifecycle contracts. Four artifacts pass 18 checks on two images with three independent SHA-256 implementations. Not higher, because no tester's copy has been hashed, there is no verification outside GitHub, and builds are not reproducible |
| 8 | Code signing | 0 | 0 | `UNSIGNED` |
| 9 | Controlled/clean-machine Windows acceptance | 2 | 2 | handoff updated; no test conducted |
| 10 | Owner decisions and field acceptance | 1 | 1 | open / `NOT_RUN` |
| | **total** | **61** | **62** | |

**Where the remaining 38 points are:**
- area 8: 10, which needs an owner-procured certificate;
- area 9: 8, which needs a conducted clean-machine test;
- area 10: 9, which needs owner decisions and field acceptance;
- area 6: 4, which needs a Qt-capable test environment;
- area 7: 2, which needs the tester's copy hash plus a reproducibility decision;
- area 4: 2, which needs an admin rerun;
- areas 1, 2 and 5: 1 each, as residual margin.

Most of that remainder depends on external owner actions, so no completion date is given.

## 12. Workspace

- No temporary refs or worktrees were created in M42.15. The local dry-run used `/tmp` only, outside the repository.
- The post-push checks (porcelain empty, `HEAD` = `ls-remote` tip, base branch unchanged) are read back after this commit is pushed.

**The single clearest next owner action:** run §8 steps 2–3 on a downloaded copy of artifact `12137427788` and return the four `True` lines. Then, in a disposable VM or Windows Sandbox, complete the step 5 checklist.
