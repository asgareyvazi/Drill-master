# M35 — FINAL REPORT (release-certification recovery)

> **Historical Mission 35 record.** Its Git identity and verdicts describe the recorded M35 session, not the current branch. Current release status: [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

Continuation of the M35 mission on `arena/01a0c945-drill-master`. Everything below was re-derived
from the actual repository in this session; no earlier report was trusted where the repository could
be checked directly. Sections follow the mandated recovery-report outline (§20).

---

## 20.1 Ground truth (captured before any change, §1)

```text
git branch --show-current   -> arena/01a0c945-drill-master
git rev-parse HEAD          -> c28bbef37cbac9de7abcfa693e7e21f678fa74ab
git status --porcelain -uall-> 89 M   /  281 ??  /  2 A  /  0 D
git diff --stat             -> 89 files changed, 3332 insertions(+), 1910 deletions(-)
git diff --cached --stat    -> core/operational_time.py 41+, core/safety_semantics.py 14+
git log --oneline --decorate --graph -n 20
                            -> * c28bbef (grafted, HEAD -> arena/01a0c945-drill-master)
                                 M27: release-candidate integrity certification
```

Upstream: none. Remote `origin https://github.com/asgareyvazi/Drill-master.git`. Shallow clone: the
object database holds exactly `c28bbef` and `02053eb`. **LOCAL-ONLY BRANCH — NOT SYNCHRONIZED TO
GITHUB** (remote has 6 branches; `arena/01a085e0-drill-master` = `c28bbef`; the target branch
returns 404). Nothing was reset, cleaned, stashed, discarded or deleted at any point; M34's evidence
corpus is byte-identical to a pre-session backup.

## 20.2 P1 packaging investigation — the exact two files (§2)

| File | Exists | Git tracked | Tracked wheel (before) | Full wheel (before) | Imported | Runtime-required | Generated | Duplicate |
|---|---|---|---|---|---|---|---|---|
| `core/operational_time.py` | yes (1 651 B, sha256 `8e12b6bb8f0f88e2060f37cd6e617ca754086cfa28aeb29ec6a0c1093b1ef4c6`) | **no** → staged → committed | **no** | yes | yes (9 import sites) | yes (`app:main` closure, 142 modules) | no | no (single `def summarize_time_logs`) |
| `core/safety_semantics.py` | yes (624 B, sha256 `19ae3cc15bc00ba9547c013f52e927a8f9cfcb5761c01e3bbf131212971b0a15`) | **no** → staged → committed | **no** | yes | yes (1 import site) | yes | no | no (single `def safety_kpis`) |

Import sites (production): `core/report_engine.py:16,1747`, `core/ddr_pdf_export.py:8`,
`core/operations_intelligence.py:13`, `core/actual_vs_plan.py:155`, `core/database.py:4420`,
`tabs/w10_Planning_Widget.py:19`, `tabs/w12_Analysis.py:1385,1537` — plus
`core/operations_intelligence.py:128` for `safety_kpis`.

## 20.3 Root cause (§5)

**The two files were never tracked, and never committed.** Proof, in order:

```text
git log --all --full-history -- core/operational_time.py    -> 0 commits
git log --all --full-history -- core/safety_semantics.py    -> 0 commits
git rev-list --all --objects | grep -E "operational_time|safety_semantics" -> (no object)
git fsck --full --no-reflogs                                -> dangling blobs do NOT include
                                                              their blob hashes (never staged before)
pyproject.toml   -> no rule mentions either module; no exclude list; MANIFEST.in does not exist
```

The build backend is setuptools (`Generator: setuptools (84.0.0)`, `Wheel-Version: 1.0`,
`Root-Is-Purelib: true`). setuptools packages what is present in the build source; a build whose
source is the tracked population therefore contained 127 `core/*.py` files and neither module, while
a build over the full worktree contained 129. The delta is exactly those two files, and the wheel
sizes differ by 1 252 B (1 036 029 → 1 037 281) — i.e. the compressed size of the two modules.

Not the cause (each checked and excluded): package discovery (both wheels contain the namespace
directories), namespace configuration, `MANIFEST`/include-exclude rules, package-data settings,
generation (no generator, build script or doc reference exists), source-root placement, sdist/wheel
inconsistency (both artifacts behaved identically), build isolation (reproduced with the same
result), and any development-only path leaking into the tree.

## 20.4 Namespace-package conclusion (§3)

The absence of `core/__init__.py`, `dialogs/__init__.py`, `tabs/__init__.py` and `ui/__init__.py` is
**intentional and correct** here — PEP 420 implicit namespace packages:

* `packages.find include = ["core*", "dialogs*", "tabs*", "config*", "ui*", "templates*"]`, plus
  `py-modules = ["app", "main_window", "run"]`; no namespace overrides.
* `…dist-info/top_level.txt` → `app, config, core, dialogs, main_window, run, tabs, templates, ui`
  (all nine tops, including the four `__init__`-less directories).
* The wheel ships 129 `core/*.py` files although `core/__init__.py` is absent; subpackages that do
  ship `__init__.py` (`core/api`, `core/engineering`, `config`, `config/company_templates`) are
  packaged as regular packages.
* Installed resolution confirms a namespace package: `core.__path__ ==
  ['…/site-packages/core']` with `namespace_package: true` and no `core.__file__`.

**No `__init__.py` was added, and none is required.** The missing modules were a *tracking* defect,
not a discovery defect.

## 20.5 Fix (§6 — three separate questions per file)

| File | Q1 in Git repository? | Q2 in distribution? | Q3 runtime import? | Root cause class |
|---|---|---|---|---|
| `core/operational_time.py` | **YES** | **YES** | **YES** (imported by production code on the release path) | accidentally untracked required production module |
| `core/safety_semantics.py` | **YES** | **YES** | **YES** (imported by operations intelligence) | accidentally untracked required production module |

Files changed: `core/operational_time.py` and `core/safety_semantics.py` (added to the index,
content byte-identical to the worktree), and `tests/test_release_boundary_imports.py` (new
release-boundary regression). No production behaviour changed, no file moved, no shim, placeholder
or duplicate added.

## 20.6 Artifact proof (§10)

| Build | Source | core/*.py | Required modules present | Startup |
|---|---|---|---|---|
| **Before** — tracked population | `git ls-files` export (506 files) | 127 | **no** | **FAIL** `ModuleNotFoundError: No module named 'core.operational_time'` (exit 1, reproduced in a fresh venv from `/tmp/m35/dist-tracked`) |
| **Before** — full worktree | worktree copy | 129 | yes | exit 0 (control) |
| **After** — tracked population | `git ls-files` export (including the two modules) | 129 | yes | exit 0 |
| **After** — **committed tree** | `git archive HEAD` at `09b5b5b4…` | 129 | yes | **exit 0** |

The committed-tree artifact is 1 037 281 B, ships no `tests/` or `docs/`, and resolves every module
from the install directory. Wheel bytes differ between rebuilds because wheels embed build
timestamps; the module population is identical (175 Python modules).

## 20.7 Clean install (§11)

`python -m venv` (fresh) → `pip install -r requirements-lock.txt` (26/26, `pip check`:
"No broken requirements found.") → `pip install --no-deps <artifact>` → run from `/tmp/m35/run`
with `env -i PATH=/usr/bin:/bin HOME=… LD_LIBRARY_PATH=/tmp/qtstub QT_QPA_PLATFORM=offscreen
DRILLMASTER_AI_IMPORT=0`. Checkout not on `sys.path`, no editable install, no `PYTHONPATH`, no
previous DrillMaster installation. Verified for the worktree-population wheel, the sdist, and the
committed-tree wheel.

## 20.8 Runtime startup (§11–§13) — exact result

```text
exit code: 0
stderr   : (empty apart from stub-library notes)
traceback: none
historical failure: ModuleNotFoundError occurrences = 0

app.__file__                       -> /tmp/m35/venv-head2/lib/python3.11/site-packages/app.py
core.__path__                      -> ['/tmp/m35/venv-head2/lib/python3.11/site-packages/core']
core.operational_time.__file__     -> …/site-packages/core/operational_time.py
core.safety_semantics.__file__     -> …/site-packages/core/safety_semantics.py
core.database.bootstrap_password_for_role -> resolves via core.credential_policy
repo entries on sys.path           -> [] (none)
```

## 20.9 Regression test (§12)

`tests/test_release_boundary_imports.py` (3 tests, 237 lines) — it exercises the real release
boundary, not an in-repo import:

1. `test_runtime_import_closure_is_tracked` — walks the AST import closure of `app:main` (142
   modules) and fails if any required module is not in `git ls-files`.
2. `test_wheel_from_tracked_population_starts` — copies the tracked population, builds the wheel,
   asserts every required module is inside the archive, installs it into an isolated `--target`
   directory and runs `app.main() --package-smoke` from a directory that is not the checkout, with
   the checkout absent from `sys.path`.
3. `test_release_population_has_no_cache_or_evidence_artifacts` — release hygiene of the archive.

**Failure it kills** (mutation-validated, then fully restored): `git rm --cached
core/operational_time.py` → 2 of 3 tests fail with
`these modules are required by the release entry point but are NOT tracked`;
the same for `core/safety_semantics.py`. Both modules were restored with byte-identical hashes
(worktree == index).

## 20.10 Semantic inventory (§14–§16) — actual current counts

| Metric | Value |
|---|---|
| TOTAL records | **11 554** (8 934 carried + 2 620 new) — arithmetic re-derived independently |
| VERIFIED-CORRECT | 7 333 |
| INTENTIONAL-BY-DESIGN | 2 880 |
| DEFECT-FIXED / EXTERNAL-ACCEPTANCE-ONLY / REMOVED-WITH-EVIDENCE | 51 / 17 / 49 |
| OPEN before M35 review | 1 224 (`UNDER-REVIEW`; EI = 0) |
| Reviewed individually this mission | 14 sites covering 29 ledger items |
| Closed with quoted contracts | **25** (15 INTENTIONAL, 10 VERIFIED-CORRECT) |
| **OPEN now** | **1 199** — 346 HIGH, 853 MEDIUM |
| CRITICAL | **0** |
| Stale-evidence records | **0** |
| Independent re-sweep | 5 802 recorded hits reproduced exactly, **0 lost**, +34 from M35's own test file |

Method: independent re-derivation (`tools/m35/verify_inventory.py`), then per-item register
(`m35-open-item-register.json`: file, symbol, line, fingerprint, source hash, question, missing
fact, why it matters, evidence target, classification, confidence) and contract-based adjudication
(`m35-contract-adjudications-final.json`: the quoted contract for every closure). No clustering, no
pattern adjudication, no mass classification — which is why 1 199 items remain open rather than
being declared domain decisions.

Two examined items stay open with named questions:

* `tabs/w5_Equipment_Widget.py:771/772` — the file's own comment calls the permission gate
  authoritative ("Read-only roles must never mutate equipment/inventory … Gate Q") while the handler
  passes silently if the control itself fails (fail-open). Security-owner decision: fail-closed or
  report-and-continue. Canonical pattern elsewhere in the codebase is a direct module-level import.
* `core/database.py:4223/4224` — an unparseable `report_date` string is passed through towards a
  `Date` column; reachability from the import path is not established. Decision: reject at the
  persistence boundary?

## 20.11 Remaining blockers (§20.11)

1. **1 199 open semantic records (346 HIGH, 0 CRITICAL)** — individually unadjudicated; the method
   and yield are demonstrated (29 → 25 closed).
2. **Two decision items** above (security gate, report-date parse).
3. **Pre-existing audit corpus untracked** — 231 `docs/` paths, 18 tool files, 19 root audit
   reports from M27–M34 (including 5 evidence JSONs > 5 MB). Enumerated per file with reasons in
   `docs/audits/m35-evidence/m35-commit-manifest.json`; deliberately not committed by this mission.
4. **External boundary NOT-RUN**: Windows runtime, native Qt, real MinerU, production-document
   acceptance (headless stub Qt only).
5. **Branch is local-only** — nothing pushed (mission forbids remote changes).

## 20.12 Git persistence (§18–§19)

```text
Repository path : /home/user/Drill-master
Branch          : arena/01a0c945-drill-master
HEAD before     : c28bbef37cbac9de7abcfa693e7e21f678fa74ab
HEAD after      : recorded in the commit ledger (below) and `git log -1`

IMPLEMENTATION COMMIT A : 02dfc5c5b8f7dade0a592ea182b250ed32da0419
  fix(packaging): make required runtime modules part of the distributable artifact
  core/operational_time.py, core/safety_semantics.py, tests/test_release_boundary_imports.py

RELEASE-TREE COMMIT B   : 09b5b5b47c6a81e0c4fc7e46400159e83d5fdcf8
  chore(release): bring the committed tree in line with the tested release population
  101 files (89 modified tracked + 11 untracked regression tests + .github/workflows/ci.yml)
  Reason: an artifact built from the pre-B committed tree failed with
  ImportError: cannot import name 'bootstrap_password_for_role' from 'core.database'

AUDIT COMMIT C          : 42b8503c8e7d1541557ac2550d7e5ade5aaf5d9f
  docs(audit): M35 recovery record, evidence and tooling (17 files)
COMMIT LEDGER           : docs/audits/m35-evidence/m35-commit-ledger.json (all SHAs)
```

Files intentionally uncommitted: the M27–M34 audit corpus listed above (pre-existing, not this
mission's work). `git status` after the commits therefore still shows a large untracked population —
that is pre-existing audit material, not M35 changes; M35's own files are all committed.

## 20.13 Resume point

```text
NEXT RESUME POINT:
P-number:  P6 (semantic adjudication) — packaging P0–P5, P7 and persistence are closed
exact unfinished task:
    adjudicate the 346 open HIGH inventory records in batches against quoted source contracts,
    exactly as demonstrated this session (29 items reviewed → 25 closed). Start with
    `docs/audits/m35-evidence/m35-open-item-register.json`, filter priority=HIGH, and record each
    closure in a contract-adjudication file with the quoted contract; unresolved items keep their
    question. Then resolve the two decision items (w5 fail-open gate, report_date parse) with the
    domain/security owner.
repository HEAD: see `git log -1` (three M35 commits already made: packaging fix, release-tree
    alignment, audit record)
known modified files: none owned by M35 (working tree changes were committed; remaining dirt is the
    pre-existing M27–M34 audit corpus, all untracked and enumerated in the commit manifest)
known untracked files: 231 docs/ paths, 18 tools/ files, 19 root audit reports (pre-existing)
tests already passed:
    tests/test_release_boundary_imports.py (3/3, mutation-validated)
    full suite 1821 tests → 1817 passed, 4 skipped, 0 failed (334 s) on this exact population
    re-run after the commits: see docs/audits/m35-evidence/ (junit)
tests still required:
    none for the packaging/release axis; the semantic axis needs per-item adjudication work, not
    new tests, except for whatever falls out of the two open decisions (each fix needs a killing
    regression, per the mission rules)
```

---

### Command index (reproducible)

```bash
# artifact from the committed tree, clean env, real startup
mkdir -p /tmp/x && git archive HEAD | tar -x -C /tmp/x
(cd /tmp/x && python -m build --wheel --outdir /tmp/dist)
python -m venv /tmp/venv && /tmp/venv/bin/pip install -r requirements-lock.txt
/tmp/venv/bin/pip install --no-deps /tmp/dist/*.whl
cd /tmp && env -i PATH=/usr/bin:/bin HOME=/tmp LD_LIBRARY_PATH=/tmp/qtstub \
  QT_QPA_PLATFORM=offscreen DRILLMASTER_AI_IMPORT=0 /tmp/venv/bin/drillmaster --package-smoke ; echo $?  # 0

# the same boundary as a test
python -m pytest tests/test_release_boundary_imports.py -q

# inventory re-derivation and the open-item register
python tools/m35/verify_inventory.py
python tools/m35/open_register.py
```
