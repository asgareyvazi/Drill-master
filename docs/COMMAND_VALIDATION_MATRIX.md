# Documented command validation matrix (M43 closure, phase 7)

Every shell command in a fenced block of a tracked Markdown file, except the
archived `docs/mission-reports/` and `docs/archive/` trees, was inventoried
with a reproducible extractor (fenced `bash`/`sh`/`powershell`/`console`/plain
blocks; lines starting with `python`, `py`, `pip`, `pytest`, `ruff`, `git`,
`gh`, `cd`, `pwsh`, `.\`, `bash`, `export`, `coverage`, `tools/`, `sqlite3`,
`$env`, `mkdir`, `source`): **128 commands in 22 files**.

Validation ran on 2026-10-21 in a disposable clone (`/tmp/docval`) of
`b8d2031`, with Python 3.11.2 on Linux and a disposable data directory
(`DRILLMASTER_ENV=test`, temp `DRILLMASTER_DATA_DIR`/`DB_PATH`/`LOG_DIR`).
No command touched a real database, a real workbook or a remote.

Status vocabulary: `VERIFIED` (ran, exit 0, output as documented) ·
`NOT_RUN` (deliberately not executed; reason given) · `UNSUPPORTED` (cannot
run on this platform; other evidence named) · `OWNER_GATED` · `HISTORICAL`
(point-in-time evidence record; not a current instruction).

## 1. Current instructions (43 commands)

| Source | Command | Status | Evidence |
|---|---|---|---|
| README.md:221, CONTRIBUTING.md:8 | `python -m venv .venv` | VERIFIED | environment rebuilt from scratch after a sandbox reset |
| README.md:224/226, CONTRIBUTING.md:10 | `pip install -r requirements-lock.txt pytest==9.1.1 ruff==0.16.6 build==1.6.1` | VERIFIED | rc 0; the full suite then ran on this environment |
| README.md:227, docs/LOCAL_AI_IMPORT.md:15 | `python -m app` / `python run.py` | NOT_RUN | starts the GUI; headless start-up is exercised by the test suite and the Windows CI smoke, not by this run |
| README.md:234 | `python verify_release.py --expected-sha "$(git rev-parse HEAD)"` | VERIFIED | see §3 |
| CONTRIBUTING.md:19 | `python verify_release.py --allow-dirty` | VERIFIED | same gate; `--help` rc 0 |
| TESTING.md:21, DEPLOYMENT.md:199 | `python verify_release.py` | VERIFIED | see §3 |
| TESTING.md:20, DEPLOYMENT.md:198 | `python -m pytest -ra` | VERIFIED | full suite (stub libGL; numbers in the M43 report) |
| README.md:235, TESTING.md:22, DEPLOYMENT.md:200 | `python -m compileall -q core dialogs tabs tests` | VERIFIED | rc 0 |
| README.md:236, TESTING.md:23, DEPLOYMENT.md:201 | `python -m py_compile app.py run.py main_window.py verify_release.py` | VERIFIED | rc 0 |
| TESTING.md:24, DEPLOYMENT.md:202 | `python -m pip wheel . --no-deps --wheel-dir dist` | VERIFIED | rc 0; `drillmaster-1.0.0-py3-none-any.whl` (written to a temp dir) |
| README.md:237, TESTING.md:25, DEPLOYMENT.md:203 | `git diff --check` | VERIFIED | rc 0 |
| TESTING.md:83 | `python -m pytest -q -m integration tests/test_ddr_acceptance.py` | NOT_RUN (content) | the command runs (rc 0), but both tests skip by design: they need a real DDR through `DRILLMASTER_TEST_DDR_XLSX` / `DRILLMASTER_TEST_DDR_PDF`, which privacy policy forbids here |
| TESTING.md:179 | `python tools/real_user_acceptance.py "<actual workbook>" --output …` | NOT_RUN | needs a real operational workbook; privacy policy forbids it. `--help` rc 0 |
| docs/DATABASE_PERFORMANCE.md:11 | `python tools/perf/db_workload.py --output perf_after_v6.json` | VERIFIED | rc 0; JSON written (43 KB); synthetic data |
| docs/DATABASE_PERFORMANCE.md:13 | `… --drop-secondary-indexes --output perf_after_v6_noidx.json` | VERIFIED | rc 0; JSON written (42 KB) |
| docs/privacy/PRIVACY_CHECK.md:9 | `python tools/privacy/privacy_check.py` | VERIFIED | 999 files, 0 findings |
| docs/privacy/PRIVACY_CHECK.md:10 | `python tools/privacy/privacy_check.py path/a path/b` | VERIFIED | 2 files, 0 findings |
| docs/privacy/PRIVACY_CHECK.md:41 | `python tools/privacy/privacy_check.py --digest "<name>"` | VERIFIED | with a synthetic word: prints a 64-hex digest only |
| DEPLOYMENT.md:254 | `py -3.12 reset_database.py` (inside the documented PowerShell block) | VERIFIED (cancel path) / UNSUPPORTED (`py` launcher) | `echo no \| python reset_database.py` → "Reset cancelled.", no file created. **Defect found:** `--help` was ignored and led straight to the destructive prompt; fixed (see §2) |
| README.md:55/72, DEPLOYMENT.md:38/63 | `.\packaging\build_windows.ps1 [-PortableOnly]` | UNSUPPORTED here | Windows only. Evidence: `windows-release-gate.yml` builds the installer on `windows-2022` for every pushed SHA (exact-SHA runs in the M43 report). CI is not acceptance |
| DEPLOYMENT.md:64 | `python packaging\package_smoke.py --bundle-dir … --run` | UNSUPPORTED here | Windows bundle; run by the Windows CI gate |
| docs/WINDOWS_ACCEPTANCE.md:26/29 | `py -3.12 --version`, `py -3.12 -m venv $Venv` | UNSUPPORTED here | Windows `py` launcher; owner acceptance procedure (packet P6) |
| packaging/WINDOWS_RELEASE_ACCEPTANCE.md:21–29 | `build_windows.ps1 …`, `windows_release_evidence.py lifecycle/signing`, `acceptance_report.py` | UNSUPPORTED here / OWNER_GATED | Windows acceptance and signing are owner decisions (P6, P8) |

## 2. Defect found by this validation

`reset_database.py` took no arguments, so `python reset_database.py --help`
(the usual way to learn what a tool does) printed the configured database
path and went straight to the "Type RESET" prompt of a tool that deletes all
data and users. The typed confirmation still protected the data, so nothing
was ever deleted, but the behaviour was a trap. The script now prints its
usage for `-h`/`--help` and refuses any other argument before it reads the
configuration (`tests/test_reset_database_cli.py`).

## 3. Commands that run the whole gate

`python verify_release.py --expected-sha "$(git rev-parse HEAD)"` ran in a
fresh disposable clone of `6ffb4f6c58a305ce0c584ec90272770cca22ad25`, with
the libGL **stub** (stub evidence; CI is authoritative):
- **rc 0**: lint passed;
- pytest: collected 2960, passed 2956, skipped 4, failed 0, errors 0;
- wheel built; `PACKAGE_SMOKE_OK schema=6 modules=16`.

The same gate runs on CI for every pushed SHA (M43 report, Part 3 §D).

## 4. Owner-gated plan (26 commands): `docs/privacy/HISTORY_PURGE_PLAN.md`

| Commands | Status | Note |
|---|---|---|
| fetch, `worktree add` at the default-branch tip, `contain_default_branch.sh`, `privacy_check.py --root` | VERIFIED earlier (phase 1, isolated clone) | resulting tree `7f3c9ca…` matched; 0 findings; 0 of 18 protected blobs |
| `git push origin HEAD:refs/heads/privacy/default-branch-containment` | OWNER_GATED | not pushed by this session |
| `git clone --mirror`, `git log --all -- <path>`, `git rev-list --objects --all`, `git cat-file -e <blob>` | NOT_RUN this phase (read-only) | read-only audit steps; the equivalent blob inventory was produced in phase 1 |
| `pip install git-filter-repo==2.47.0`, `git filter-repo …`, `git push --force --mirror origin`, `git gc --prune=now --aggressive` | OWNER_GATED — never run | history rewrite and force-push are banned for this session |
| post-purge `privacy_check.py` and `cat-file -e` leak loop | OWNER_GATED | only meaningful after the purge |

## 5. Historical evidence records (59 commands in 12 files)

`M30_RELEASE_CERTIFICATION.md` (1), `M33_EVIDENCE_INDEX.md` (8),
`M34_EVIDENCE_INDEX.md` (9), `M34_M33_RECOVERY.md` (2), `M35_FINAL_REPORT.md`
(6), `docs/audits/2026-09-08-ddr/REPORT.md` (2) and
`evidence/r18-r19/commands.md` (12), `docs/audits/2026-09-09/MASTER_FORENSIC_AUDIT.md`
(4), `docs/audits/2026-09-12_ENGINEERING_PERFORMANCE_COMPLETION_PASS.md` (6),
`docs/audits/2026-09-12_SCOPE_IDENTITY_ATTRIBUTION_PASS.md` (7),
`docs/audits/2026-09-23_M29_RELEASE_CLOSURE.md` (1),
`docs/audits/m36-evidence/M36_RECOVERY_AND_P6_REPORT.md` (1).

Status `HISTORICAL`: they document what was run at the time, against the
commits named in those records. They are not current instructions and were
not re-run; several reference files and real-workbook paths that the privacy
remediation removed. Anyone reproducing them must check out the commit the
record names.

## Reproduce

```bash
git clone <repo> /tmp/docval && cd /tmp/docval
export DRILLMASTER_ENV=test DRILLMASTER_DATA_DIR=/tmp/docval-run/data \
       DRILLMASTER_DB_PATH=/tmp/docval-run/data/x.db DRILLMASTER_LOG_DIR=/tmp/docval-run/logs
python -m compileall -q core dialogs tabs tests
python -m py_compile app.py run.py main_window.py verify_release.py
git diff --check
python -m pip wheel . --no-deps --wheel-dir /tmp/docval-dist
python tools/privacy/privacy_check.py
python tools/perf/db_workload.py --output /tmp/docval-run/perf.json
echo no | python reset_database.py      # must print "Reset cancelled."
python reset_database.py --help         # must print usage and exit 0
```
