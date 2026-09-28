# M34 — Release Certification

**Mission 34 · branch `arena/01a0c945-drill-master` · HEAD `c28bbef37cbac9de7abcfa693e7e21f678fa74ab` · tree
`7e16996cdcc1bce4a79fed8823371c20c74eef15`.**

Everything below was executed in this mission against the tree as it exists now. Where a stage could not be run
(Windows, native Qt, real production documents), it is stated as NOT-RUN rather than inferred.

> ## Verdict: **NOT RELEASE-CERTIFIABLE**
> **Repository-verifiable semantic inventory not closed (1 224 OPEN, 371 HIGH, 0 CRITICAL), and the release
> artefact built from the tracked population cannot start (`ModuleNotFoundError: core.operational_time`).**
> The four external acceptance items additionally remain unexecuted.

---

## 1. Gates

| Gate | Requirement | Measured | State |
|---|---|---|---|
| Closure | inventory N == terminal ledger items | 11 554 vs 10 330 | **FAIL** |
| Closure | UNREVIEWED == 0 | 1 224 | **FAIL** |
| Closure | EVIDENCE-INCOMPLETE == 0 (repository-verifiable) | **0** | PASS |
| Blocker | CRITICAL unresolved == 0 | **0** | PASS |
| Blocker | HIGH unresolved == 0 | 371 | **FAIL** |
| Residual | any other unresolved defect found by this mission | tracked-only wheel aborts at start (PACKAGING DEFECT) | **FAIL** |

`m34-closure-invariants.json` carries these numbers with the rule that drives every open item.

---

## 2. Source and test state (Parts P, and the final candidate tree)

| Check | Result |
|---|---|
| `compileall` | clean (exit 0) |
| Collection | **1 818** tests collected |
| Full suite (`-ra`, JUnit) | **1 814 passed · 0 failed · 0 errors · 4 skipped · 309.9 s · exit 0** |
| The 4 skips | real DDR xlsx, real DDR PDF, real MinerU, Windows bundle — external inputs, named in the run, **not** counted as passes |
| `ruff --select E722,F821` | **0 defects** (bare `except`/undefined names clean) |
| Lint debt ratchet (`core dialogs tabs tests`) | **5 338** ≤ ceiling **5 375** — unchanged ceiling |
| Test-integrity audit | no vacuous asserts; every skip keyed to a stated external dependency; failed imports never converted to passes |

## 3. Fix integrity (Parts B, N, O)

| Stage | Result |
|---|---|
| M32 fixes 001–010 re-verified | **10/10 VERIFIED** — contract probe against current source + the fix's own regression test |
| M33 fixes re-verified | **3/3 VERIFIED** (casing absent-load semantics, data-quality unknown coverage, Qt clamp contract) |
| Hash reconciliation | 11 of 13 files byte-identical to their recorded post-fix hash; 2 differ **because M33 changed them** — recorded as `DIFFERS-FROM-RECORDED`, not explained away |
| Mutation controls | **16 mutants designed from the contracts → 15 KILLED, 1 documented equivalent survivor**; every touched file restored byte-identically; harness aborts on restore mismatch |
| Coverage of the required mutants | `None→0`, `zero→None`, restore-fabricated-measurement, remove-ownership-guard, restore-Qt-singleton (killed only with the cross-file oracle, which is stated), restore-99.99-clamp, drop-documented-maximum, restore-`duration or 0` (the equivalent survivor) |

## 4. Clean environment and lock (Part Q)

| Check | Result |
|---|---|
| Throwaway venv created | yes (`/tmp/m34-clean-venv`) |
| `pip install -r requirements-lock.txt` | **26/26 pins exact**, no mismatch |
| `pip check` | `No broken requirements found` |
| Runtime deps used by the suite | the same lock, installed in the verification venv |

## 5. Wheel (Parts Q/R) — the blocking finding

| Stage | Result |
|---|---|
| Wheel built from the **tracked** population (`git ls-files`, exactly what a release can contain) | `drillmaster-1.0.0-py3-none-any.whl`, 1 036 029 B, sha256 `5d5211600372ced4…` |
| Required packaging entries | all present (`app.py`, `main_window.py`, `core/database.py`, `ui/*`, `config/*`, `templates/*`); `tests/` **excluded** |
| Install outside the checkout | `pip install --no-deps --no-index --target` → OK |
| Start the installed entry point from `/tmp` | **ABORT**: `ModuleNotFoundError: No module named 'core.operational_time'` (`tabs/w10_Planning_Widget.py:19`) |
| Root cause | `core/operational_time.py` and `core/safety_semantics.py` are **untracked** while tracked modules import them (8+ import sites) |
| Verdict | **PACKAGING DEFECT — blocking.** M33 reported this stage as passing against a staging state whose cited commit `a9d7dede…` does not resolve in this repository (`M34_M33_RECOVERY.md` §5) |

## 6. Commit staging simulation (Part S)

The Commit-1 population was exported with `git archive HEAD` plus the proposed Commit-1 files — **no audit
record, report or analysis tool present** — and then exercised:

| Stage in the overlay | Result |
|---|---|
| Commit-1 files | 86 (production code, tests, packaging/config/CI — including `packaging/DrillMaster.spec`, `packaging/build_windows.ps1`, `packaging/package_smoke.py` — plus `core/operational_time.py` and `core/safety_semantics.py`) |
| `compileall` | clean |
| Collection | all test modules collect |
| Targeted tests (casing semantics, M31 scenarios, ownership, autosave) | pass |
| **Full suite inside the overlay** | **exit 0** — Commit 1 is behaviour-verified without Commit 2 |
| Import smoke of the previously-untracked consumers | `core.report_engine`, `core.ddr_pdf_export`, `core.operations_intelligence`, `core.actual_vs_plan`, `tabs.w10_Planning_Widget` → IMPORT-OK; `CasingEngine.evaluate` → SUCCESS |
| Import of any `docs/…` audit material from Commit-1 code | **none** (one *docstring citation* of a 2026-09-12 audit note exists in `core/database.py`; it is prose, not a dependency) |
| **Self-contained** | **true** |
| Commit 2 population | 269 files (audit records, evidence, reports, `tools/m34/`) — behaviour-neutral |
| Files needing a human decision | none remain unclassified: every changed path carries an explicit class and reason in `decisions[]`, and the two Windows build files are classified as packaging configuration in Commit 1 rather than left silent |

## 7. Repository state (Part X and cleanliness)

| Check | Result |
|---|---|
| Worktree | 89 modified tracked / 260 untracked / **0 deleted / 0 staged** |
| `git diff --check` | clean |
| Cache artifacts (`.pyc`, `__pycache__`, `.pytest_cache`, coverage, venvs) in the change set | **none** |
| Credential patterns (API keys, private keys, tokens, AWS/GitHub key shapes) | **no matches** |
| Mutant markers | present only in `tools/m34/` and `m34-mutation-controls.json` (the harness and its result); **zero** in production or test code |
| Documentation truth scan | 11 claims CURRENT-VERIFIED, 98 HISTORICAL, 15 to check against the final run, 45 status claims needing review, **36 SHAs that do not resolve locally → UNRESOLVED** |
| Remote | this branch is **absent** from the remote (404): `LOCAL-ONLY BRANCH — NOT SYNCHRONIZED TO GITHUB`. Nothing was pushed; no SHA was invented. |

## 8. External boundary — what is *not* certified

* Windows application, installer and PyInstaller bundle: **NOT-RUN** (no Windows runtime here) — state is
  `WINDOWS-REPOSITORY-READY / WINDOWS-RUNTIME-NOT-RUN`.
* Native Qt: the suite ran headless with symbol-complete **fail-loud** stubs; font metrics are unavailable
  (fontconfig stub), so **no native-Qt or pixel-geometry acceptance is claimed**.
* Real production documents (DDR xlsx/PDF, OEOC workbooks, MinerU): the acceptance inputs are absent — the four
  skips. **External skip ≠ production acceptance.**
* A wheel is not a Windows EXE and CI-workflow existence is not CI having passed: neither is claimed.

## 9. What would change the verdict

1. **Track the two modules** (`core/operational_time.py`, `core/safety_semantics.py`) and their tests, then
   rebuild the wheel and start it outside the checkout — the Commit-1 overlay already proves this population is
   sufficient (full suite green, all consumer imports OK, `CasingEngine` evaluates).
2. **Adjudicate the 1 224 open items from a domain decision**, per field: (a) can a legitimate `0`/falsy value
   exist for this subject (`R-TRUTH-NUMERIC` 88, `R-SPIN-ZERO` 26, `R-NUM-UNKNOWN` 45, `R-DEF-VALUE-PATH` 21,
   `R-DEF-RETURN-NUM` 52)? (b) may this swallowed failure be invisible to the operator
   (`R-EXC-PASS` 98, `R-PASS-EXC` 74, `R-EXC-SILENT-RETURN` 52, `R-EXC-CONTINUE` 35, `R-EXC-OTHER` 60,
   `R-PASS-OTHER` 23)? (c) what is the declared type/contract of these subjects (`R-TRUTH-UNKNOWN` 367,
   `R-DEF-UNKNOWN` 152, `R-PLAN-OTHER` 48, `R-SESSION-OTHER` 26, `R-SEL-UNPROVEN` 20,
   `R-SNAP-SERIAL-DEFAULT` 16, `R-RED-UNPROVEN` 14)? Every record names the file, the line and the missing fact.
3. Then re-run this certification on the frozen tree.

## 10. Verdict rationale (Part AI)

The mission allows exactly four states; `RELEASE-CERTIFIABLE` requires complete semantic closure, zero
repository critical/high items, coherent evidence and a reproducible current source. Here:

* closure is **incomplete** (1 224 open, 371 HIGH) — repository-verifiable work, not external acceptance;
* a **new blocking defect** was proven by execution (the tracked population cannot produce a startable artefact);
* the evidence is coherent (every number in this document is reproducible from `tools/m34/`), the suite is green,
  the lock is exact — and none of that is enough by the mission's own rules.

Because the blockers are repository-verifiable, the state is the not-certifiable family, and it is stated
exactly:

> **NOT RELEASE-CERTIFIABLE — repository-verifiable semantic inventory not closed (1 224 UNDER-REVIEW, 371 HIGH)
> and a proven packaging blocker (tracked-only wheel `ModuleNotFoundError: core.operational_time`), with the
> four external acceptance items additionally unexecuted.**
