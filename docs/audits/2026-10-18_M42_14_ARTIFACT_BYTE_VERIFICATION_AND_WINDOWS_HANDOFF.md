# M42.14 — Artifact byte verification, exact-tip reconciliation and controlled Windows-test handoff

- **Date:** 2026-10-18
- **Repository / branch:** `asgareyvazi/Drill-master`, `arena/72010272-drill-master`
- **Starting HEAD (local = remote):** `d9fecba057475c50a5204b031437c066dc1c5a38` (the M42.13 report commit)
- **Base branch `drill-Master`:** `e3fa42a3257e981d9bdf9d012c97919e3352a53a` before and after; not modified
- **This is not release approval.** No `RELEASE-APPROVED` state exists. Signing is `UNSIGNED`, owner decisions A–D stay open, field acceptance stays `NOT_RUN`.

## 1. Verdict

| label | scope |
|---|---|
| `ARTIFACT_BYTES_MATCH_FOR_SPECIFIC_ARTIFACT` | artifact `12135787858` (source `d9fecba057475c50a5204b031437c066dc1c5a38`) and artifact `12136310366` (source `fa92145b69b332240ffb6b34fad17bd02ff3c834`) — those two IDs only, computed **on a GitHub-hosted runner**, not in the Arena sandbox |
| `CONTROLLED_WINDOWS_TEST_CANDIDATE_VERIFIED` | artifact `12135787858`; handoff in §8 |
| `SOURCE_GATE_GREEN_ON_EXACT_TIP`, `WINDOWS_GATE_GREEN_ON_EXACT_TIP` | `42d29723f3df126179ab12a3e9f2aeaf50c56d20`, the last code-bearing commit (§3). The report commit that adds this file changes documentation only; its own runs are read back after it is pushed and are not claimed here |
| `REL-13_CLOSED_FOR_STATED_CONDITION` | unchanged from M42.13; the refused-launch shape did not recur (§5) |
| `SIGNING_UNSIGNED` | both installers and both `DrillMaster.exe`: no certificate table in the PE header, and `UNSIGNED/NotSigned` in the run's signing record |
| `OWNER_ACTION_REQUIRED` | §10 |

## 2. Why the bytes could now be read, and by whom

Every earlier attempt from this workspace to download an artifact failed the same way: `api.github.com` answers, but the redirect to the Azure blob host (`productionresultssa*.blob.core.windows.net`) is reset during the TLS handshake. M42.14 made **one** more attempt (artifact `12135787858`; exit 1, zero bytes, the same reset) and did not retry it.

GitHub's own runners can reach that host.
- **Mechanism:** a read-only workflow, `.github/workflows/artifact-byte-verification.yml`. It has `contents: read` and `actions: read` permissions, uses no secrets and hardcodes no IDs.
- **Download:** it reads `docs/audits/m42-14-evidence/artifact-candidates.json` and fetches each named artifact through `GET /repos/{owner}/{repo}/actions/artifacts/{id}/zip`, the route a tester's browser uses. The bytes are streamed to disk.
- **Verification:** `packaging/verify_artifact_bytes.py` checks the archive, and coreutils `sha256sum` hashes it a second time.
- **Safety:** nothing is executed, extracted or modified. The verifier's source is test-guarded against `subprocess`, `os.system`, `startfile`, `extractall` and file deletion or writes.
- **Status:** the workflow is not a release gate.

**Source of the expected values.** Every expected value comes from somewhere other than the archive under test:
- the artifact API's `size_in_bytes` and `digest` for the outer archive;
- each build job's `Windows release manifest` notice for the inner files.

They were committed in the candidates file before the download. Records inside the archive (`release-metadata.json`, `SHA256SUMS.txt`, the acceptance and signing reports) are only cross-checked against the hashes actually computed, never used as the expectation.

## 3. Runs, exact SHA (all `push`, attempt 1, branch `arena/72010272-drill-master`)

| workflow | # | run ID | head_sha | jobs | conclusion |
|---|---|---|---|---|---|
| Source release gate | 117 | 39124603637 | `fa92145b69b332240ffb6b34fad17bd02ff3c834` | 3.11 / 3.12 / 3.13 | success |
| Windows release validation | 63 | 39124603564 | `fa92145b…` | `windows-release` | success → artifact `12136310366` |
| Source release gate | 118 | 39125666192 | `d9fecba057475c50a5204b031437c066dc1c5a38` | 3.11 / 3.12 / 3.13 | success |
| Windows release validation | 64 | 39125666180 | `d9fecba0…` | `windows-release` (job 117670132544) | success → artifact `12135787858` |
| Source release gate | 119 | 39128927092 | `42d29723f3df126179ab12a3e9f2aeaf50c56d20` | 3.11 / 3.12 / 3.13 | success |
| Windows release validation | 65 | 39128927120 | `42d29723…` | `windows-release` (job 117679876342) | success → artifact `12136504650` (**not byte-verified**) |
| Artifact byte verification | 1 | 39128927168 | `42d29723…` | `verify` (job 117679876630) | success |

- **No relabelling:** the `fa92145` runs belong to `fa92145` and the `d9fecba` runs to `d9fecba`.
- **Code identity:** `git diff fa92145 d9fecba` adds only the M42.13 report. `git diff d9fecba 42d2972` adds only the verifier, its test, its workflow and the candidates file. No application, packaging or gate source changed after `fa92145`.
- **Retained builds:** run 65's own artifact (`12136504650`, 321670336 B, `sha256:e534a476…3515`) was not in the candidates file and is not covered by any byte claim. The three builds differ byte-for-byte, so the build is not reproducible and no claim of that is made.

## 4. Artifact table — expected vs observed

The observed column is the verifier's report as published in the job's notice annotations. `coreutils` is the independent `sha256sum` of the same file in the same job.

| artifact | item | expected (source) | observed on runner | coreutils | result |
|---|---|---|---|---|---|
| `12135787858` | outer archive | 321663699 B, `891873eeb1a8a76f57b72b11ecdcf9b316ed2f2d9b40e9445efb7cb001abed6f` (artifact API) | 321663699 B, `891873eeb1a8a76f57b72b11ecdcf9b316ed2f2d9b40e9445efb7cb001abed6f` | `891873ee…abed6f` | MATCH |
| | `DrillMaster-1.0.0-Setup.exe` | 83211695 B, `ff14393e50c7a348eb7876a0ef3fffe47de849210b7a3b530e0d52bca6f9f9e1` (run 64 manifest) | identical | — | MATCH |
| | `DrillMaster-1.0.0-windows-x64.zip` | 119941399 B, `0863b887604091998e3b580e84ca906e9aaa644a86aa54012c4f9353726ebd1f` (run 64 manifest) | identical | — | MATCH |
| `12136310366` | outer archive | 321722453 B, `8391f63bd5927ba89a30b6eb45b62a6e480eaa01ac5351cce895882a5c4259b2` (artifact API) | identical | `8391f63b…4259b2` | MATCH |
| | installer | 83270432 B, `1ddabf57bc2e26b3a3ff039466bd05706803292136d5c4bde786854e2933d73b` (run 63 manifest) | identical | — | MATCH |
| | portable ZIP | 119941400 B, `50303d397f3b396942312831a86052136d845112ad852be3ec1aa29a2a9dfb74` (run 63 manifest) | identical | — | MATCH |

Both artifacts passed all 16 checks:
1. `live_api_binding`: id, name, size, digest, run, source SHA and non-expiry, read live in the same job.
2. `archive_size` and `archive_sha256`.
3. `zip_crc`: every member.
4. `member_paths`: no absolute, drive-qualified, traversing, backslash, control-character, case-fold-duplicate, symlink or other special entries.
5. `member_layout`: every member is under `DrillMaster-release-<run>/`, `DrillMaster-M42-tests-<run>/` or `DrillMaster-build-transcript-<run>.txt`. This confirms the layout that M42.14 had inferred from the workflow; the verifier fails closed if it is wrong.
6. `required_members`: each mandatory file appears exactly once, at its expected path.
7. `installer_bytes` and `portable_zip_bytes`.
8. `sha256sums_binding`: exactly two rows, both matching.
9. `release_metadata_binding`: schema validator passes, the run's source SHA, the observed artifacts.
10. `acceptance_report_binding`: source SHA, both files, lifecycle `PASS`, `UNSIGNED`.
11. `signing_record_binding`.
12. `lifecycle_record`: `PASS`, with the installer hash verified before execution.
13. `installer_pe_signature` and `portable_exe_pe_signature`: certificate-table size 0. That means no embedded Authenticode signature, consistent with `UNSIGNED`. It is a header read, not a trust evaluation.

**What this result does and does not mean:**
- It shows that GitHub serves exactly the bytes its build job recorded, and that the archive is structurally safe and internally consistent.
- It is computed on GitHub's infrastructure, so it is not an independent verification outside GitHub, and it says nothing about the copy a particular tester downloads.
- The tester's own `Get-FileHash` of their file (§8, step 2) is the step that binds that copy.
- REL-04's literal procedure (operator's machine) therefore stays `NOT_RUN` for these two artifacts.
- The earlier REL-04 `MATCH` records stay scoped to their own artifacts and are unchanged. The new record is appended to the REL-04 row with this scope.

Per-check detail lines (member counts, the inner `DrillMaster.exe` hash) went to the job log and step summary. The log blob host is unreachable from this workspace, so this report cites only the summary notice and the step conclusion, whose exit code is non-zero on any failed check.

## 5. Lifecycle fix — adversarial review (P3, read-only; no gap found)

Reviewed `1720b19` (the REL-13 fix) against the M42.13 starting point `279a52f`.
- **The diff's 17 deleted lines are all re-expressions.** The `snapshot` signature gained `vanished=`, the settle loop moved inside the new `try`, `forensics` gained a `system` label, and the notes gained attribution. Every verdict-bearing change is an addition, and no guard was removed.
- **Only absence is absorbed.** `snapshot()` catches `FileNotFoundError` from `path.stat()` alone. Per CPython 3.12.10 `pathlib`, that is the only call in the listing that can raise for a vanished entry. Widening that clause to `OSError` (mutation run in M42.14) is caught by `test_snapshot_still_raises_for_a_file_that_exists_but_cannot_be_read`.
- **Launch failure stays distinct from observation failure.** The runner call sits outside the observation `try`. A `FileNotFoundError` from the launch still reaches the refused-launch branch (`test_a_genuinely_refused_launch_is_still_reported_as_one`). Any error after launch becomes `UninstallObservationError` → `silent_uninstall FAIL`, the uninstaller is not re-launched, and the message names the launch.
- **Retained:**
  - exit code 0 is required;
  - an empty install directory is still required, via the later `install_files_removed` listing;
  - user data must survive (`user_data_preserved`);
  - the isolated work root;
  - bounded retry, with the number of attempts and the boundary unchanged.
- **Diagnostics stay bounded and redacted.** The vanished-name sample holds at most 5 entries of at most 120 characters each. The notice prints only numbers and booleans. The uninstall log is still read through the bounded, root-checked `_tail` and redacted.
- **The tests still discriminate (re-run in M42.14 on a temporary worktree of `a64a242`, then removed).**
  - Of the 6 race tests, 5 fail on the old module and 1 passes.
  - The one that passes is the refused-launch regression guard, which must pass on both.
  - Precision added to the M42.13 statement ("5 of 6 fail on the old code"):
    - 4 of those 5 are behavioural failures.
    - `test_snapshot_still_raises_…` fails on the old code only because the old `snapshot` lacks the `vanished=` keyword. The old code also raised for an unreadable file, so its value is the over-absorption guard proven by the mutation above, not race discrimination.
  - On the fixed module, all 6 pass.
- **Field evidence on the fixed code:** `vanished_while_listing=1` with `status=PASS exit=0 emptied=True` was observed on Windows runs 62, 64 and now 65. The race path is exercised in production CI and handled. The refused-launch shape has not recurred, so REL-13 is not reopened.

## 6. Tests and baseline

| scope | result |
|---|---|
| `tests/test_verify_artifact_bytes.py` (new) | 27 passed. Each of 8 mutations to the verifier (traversal, CRC, special-file, duplicate-candidate, SHA256SUMS, metadata SHA, identity gate and PE-signature checks) turned at least one test red. The file was restored afterwards |
| `tests/test_windows_release_gate_contract.py` + new tests | 93 passed (after the doc edits) |
| Lifecycle race tests | 6/6 on the tip, 5/6 failing on `a64a242` (§5) |
| Ruff (repository config, `E4/E7/E9/F`) on the new Python files | clean. CI does not run ruff, and the repository-wide pre-existing findings are not this mission's |
| Full suite at `42d2972` | **2257 passed, 63 failed, 45 skipped, 18 collection errors** |
| Full suite baseline (`fa92145`, M42.13 log) | 2230 passed, 63 failed, 45 skipped |

- **Delta:** +27 passed, exactly the new file. The failure set is node-for-node identical, with 0 new and 0 gone. All are Qt subprocess smoke tests that cannot load `libGL.so.1` here.
- **The 18 collection errors** are 18 Qt view-model modules failing with `ImportError: libGL.so.1`. The **unmodified `d9fecba` checkout produces the same 18 errors in this sandbox** (2336 collected vs 2363 at the tip = +27), so they are environmental. The M42.13 log shows none. The sandbox's Python environment was rebuilt after a restore, and that difference is recorded here, not explained away.

## 7. Commits

| commit | content |
|---|---|
| `42d29723f3df126179ab12a3e9f2aeaf50c56d20` | verifier, its 27 tests, the read-only verification workflow, the candidates file |
| (this commit) | this report; `PRODUCTION_READINESS.md` checkpoint wording (no run counts); a new dated, scoped record appended to the REL-04 row in `packaging/WINDOWS_RELEASE_ACCEPTANCE.md` |

**No PowerShell helper was written, deliberately.** It became unnecessary once a runner could verify the bytes: the remaining tester step is one built-in cmdlet (`Get-FileHash`) against one published digest, and a script would be scope inflation. No checkpoint-JSON key was added either. M42.14 changes no register row's state, and M42.10–M42.12, which also did not, added none.

## 8. Controlled Windows-test handoff (artifact `12135787858`)

**What to test**

| field | value |
|---|---|
| run | Windows release validation #64, run `39125666180`, attempt 1 — <https://github.com/asgareyvazi/Drill-master/actions/runs/39125666180> |
| source SHA | `d9fecba057475c50a5204b031437c066dc1c5a38` (application code identical to `fa92145` and to the current tip) |
| gates on that SHA | Source #118 success (3.11/3.12/3.13), Windows #64 success |
| artifact | `drillmaster-windows-d9fecba057475c50a5204b031437c066dc1c5a38`, ID `12135787858`, expires 2026-11-17T12:11:02Z |
| outer ZIP | 321663699 bytes, SHA-256 `891873eeb1a8a76f57b72b11ecdcf9b316ed2f2d9b40e9445efb7cb001abed6f` |
| installer | `DrillMaster-1.0.0-Setup.exe`, 83211695 bytes, `ff14393e50c7a348eb7876a0ef3fffe47de849210b7a3b530e0d52bca6f9f9e1` |
| portable | `DrillMaster-1.0.0-windows-x64.zip`, 119941399 bytes, `0863b887604091998e3b580e84ca906e9aaa644a86aa54012c4f9353726ebd1f` |
| signing | **UNSIGNED.** Windows will show "Unknown publisher" |

**Where:** Windows Sandbox (Windows 10/11 Pro or Enterprise) or a disposable Windows 10/11 x64 VM with a snapshot.
- No production database, no real operator credentials and no confidential DDR files.
- Windows Sandbox discards everything on close, so collect logs (step 7) before closing it.

**Steps**
1. Download the artifact from the run page above (section *Artifacts*, signed in to GitHub). Use the browser, which keeps the ZIP intact. `gh run download` extracts the ZIP, which skips the outer check; if you used it, go straight to the inner checks in step 3.
2. Check the outer ZIP in PowerShell, on the host or inside the sandbox:
   ```powershell
   $p = "$HOME\Downloads\drillmaster-windows-d9fecba057475c50a5204b031437c066dc1c5a38.zip"
   (Get-Item -LiteralPath $p).Length -eq 321663699
   (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash -eq '891873eeb1a8a76f57b72b11ecdcf9b316ed2f2d9b40e9445efb7cb001abed6f'
   ```
   Both lines must print `True` (`-eq` ignores case).
3. Extract the ZIP, then check the two files you will use:
   ```powershell
   $d = "$HOME\Downloads\dm-test"; Expand-Archive -LiteralPath $p -DestinationPath $d
   $r = Join-Path $d 'DrillMaster-release-39125666180'
   (Get-FileHash (Join-Path $r 'DrillMaster-1.0.0-Setup.exe')).Hash -eq 'ff14393e50c7a348eb7876a0ef3fffe47de849210b7a3b530e0d52bca6f9f9e1'
   (Get-FileHash (Join-Path $r 'DrillMaster-1.0.0-windows-x64.zip')).Hash -eq '0863b887604091998e3b580e84ca906e9aaa644a86aa54012c4f9353726ebd1f'
   (Get-AuthenticodeSignature (Join-Path $r 'DrillMaster-1.0.0-Setup.exe')).Status   # expected: NotSigned
   ```
4. Install by running `DrillMaster-1.0.0-Setup.exe` (it asks for administrator rights; the default target is `C:\Program Files\DrillMaster`). SmartScreen may warn about an unrecognised app from an unknown publisher. That is expected for an unsigned build whose hash you just verified, and you may proceed through that prompt for this file only. Do not change SmartScreen or Defender settings.
5. **First-run checklist:**
   - **(a)** Record the Windows edition/build, the date, the source SHA and the installer hash.
   - **(b)** Launch the app and complete first-run credential setup with a new, throw-away test password. Never reuse a real one, and do not write it into any report.
   - **(c)** Sign in, close the app, reopen it and sign in again.
   - **(d)** Confirm data lives in `%LOCALAPPDATA%\DrillMaster` (`drillmaster.db`, `logs\`), not under `C:\Program Files\DrillMaster`.
   - **(e)** Create one clearly synthetic project/report.
   - **(f)** Uninstall through *Settings → Apps*, then confirm the program folder is gone and `%LOCALAPPDATA%\DrillMaster` is still there. Uninstall must not delete user data.
   - **(g)** Optionally, unzip the portable ZIP to a separate folder and launch `DrillMaster.exe` once.
6. Note every deviation in plain words, with the step number.
7. **Logs to send:**
   - `%LOCALAPPDATA%\DrillMaster\logs\drillmaster.log`;
   - if the installer misbehaved, an installer log from re-running `DrillMaster-1.0.0-Setup.exe /LOG="$HOME\Desktop\dm-setup.log"`;
   - a screenshot of any error.
   Before sending, open each text file and remove anything that looks like a password, token or personal path you do not want to share. **Do not send** `drillmaster.db`, `config\ai_settings.json` (it can hold API keys), backups or any credential.

**Stop immediately, without continuing to install or run, if:**
- any size or hash check prints `False`;
- `Get-AuthenticodeSignature` reports anything other than `NotSigned` (a signature from any publisher would contradict this build);
- Defender reports a detection or quarantines a file;
- the installer asks for anything unexpected (network credentials, extra components, a different install path you did not choose);
- the app writes its database under `Program Files`;
- uninstall removes `%LOCALAPPDATA%\DrillMaster`;
- anything asks for real/production credentials.

Report what you saw. Do not work around it.

**A passing smoke test is not approval.** It is evidence for REL-07 (clean-machine install) and part of REL-08. Signing (REL-02), the owner decisions and field acceptance (REL-09–REL-11) remain open whatever the result.

## 9. Scorecard (same ten areas as M42.13; baseline 56)

| # | area | M42.13 | M42.14 | reason |
|---|---|---|---|---|
| 1 | REL-13 root cause and closure | 9 | 9 | unchanged; one more fixed-code observation of the race path, handled |
| 2 | Lifecycle fix quality and tests | 9 | 9 | re-verified adversarially; no gap; one precision note on test 2 of 6 (§5) |
| 3 | Exact-tip CI reconciliation | 10 | 10 | exact-SHA table for three SHAs, no relabelling |
| 4 | Same-SHA rerun evidence | 8 | 8 | reruns still `403`; nothing new |
| 5 | Record integrity and history preservation | 9 | 9 | appended a scoped REL-04 record; earlier records untouched |
| 6 | Local test evidence | 6 | 6 | +27 mutation-checked tests, identical failure set; still environment-limited (libGL) |
| 7 | Artifact byte integrity | 2 | **7** | real bytes of two specific artifacts hashed twice and verified structurally and across all records on a hosted runner. Not 10, because this is not verification outside GitHub, no tester copy has been hashed yet, and builds are not reproducible |
| 8 | Code signing | 0 | 0 | `UNSIGNED` |
| 9 | Controlled/clean-machine Windows acceptance | 2 | 2 | a verified candidate and a handoff exist, but no test has been run; instructions earn no score |
| 10 | Owner decisions and field acceptance | 1 | 1 | open / `NOT_RUN` |
| | **total** | **56** | **61** | |

## 10. Can testing start now, and what the owner must do

**Yes. A controlled test of artifact `12135787858` can start now**, following §8. Its first required step is the tester's own `Get-FileHash`.

Owner items:
1. **Run the controlled smoke test (§8) and return the logs.** This is what can raise area 9.
2. **Code signing (Decision A / REL-02).** It needs a certificate or a hosted-signing service; nothing in this repository can supply one.
3. **Owner decisions A–D**, and field acceptance REL-09–REL-11.
4. **The Node 20 action deprecation:** `actions/checkout@v4` and `actions/setup-python@v5` are forced onto Node 24. Also, `ubuntu-latest` migrates to Ubuntu 26 from 2026-10-19, which affects the verification workflow only.
5. **Optional:** an admin rerun of the historical run `38522527259`; the API returns `403` to this session.

## 11. Workspace state

- No temporary refs or worktrees remain; the two temporary worktrees used in §5 and §6 were removed and pruned.
- Uncommitted work at the time of the final push: none. The post-push clean check (porcelain empty, `HEAD` = remote tip, base branch unchanged) is read back after this commit is pushed.
