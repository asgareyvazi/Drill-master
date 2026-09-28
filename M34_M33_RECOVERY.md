# M34 — Mission 33 Recovery Report

**Question this document answers:** what did Mission 33 actually change, test, claim, verify, invalidate — and what of it remains in the repository today?

**Method.** Nothing below is taken from an M33 narrative. Every statement is re-derived from the filesystem
(`git status`, file hashes, source reads), from the M33 artifacts that still exist, and from executions run in
this mission. Where M33's own narrative and the repository disagree, the repository wins and the disagreement
is recorded as a finding.

* Mission 34, branch `arena/01a0c945-drill-master`, HEAD `c28bbef37cbac9de7abcfa693e7e21f678fa74ab`.
* Recovery inputs: `docs/audits/m33-evidence/` (18 files), M33 root deliverables, `git status`, file sha256.
* Generated: 2026-09-27.

---

## 1. Status of Mission 33

> **M33 — PARTIAL, with two falsified claims.**

M33 did real work that survives (three code fixes, two test files, a full evidence directory, a coherent
ledger), and it also made claims that the repository does not support (§5). It never committed anything,
so nothing of M33 exists in git history: its entire output is uncommitted worktree state.

| Question | Answer (re-derived) |
|---|---|
| Did M33 run? | Yes. Its 24 evidence files and 6 root deliverables exist, and its ledger decomposes exactly into its own claimed origins (§3). |
| Did M33 commit? | **No.** `git log` HEAD is still `c28bbef…`; `git status` shows 0 staged files; the reflog contains only branch creation and a checkout. |
| Did M33 change code? | Yes — three production files, verified byte-identical to M33's recorded post-fix hashes (§2). |
| Did M33 add tests? | Yes — `tests/test_casing_absent_load_semantics.py`, `tests/test_casing_absent_load_widget_smoke.py`, still present and passing. |
| Is M33's tooling recoverable? | **No.** `/home/user/m33-tools/*`, `/tmp/mutate*.py` and `/tmp/m33-*` are gone (sandbox re-provisioning). Only repository contents survived. |
| Are M33's numbers reproducible with M33's own tooling? | **No** — the tooling is gone. They were re-derived independently in M34 (§3, §4). |
| Is M33's verdict still correct? | Yes, and it must be strengthened: M34 found a packaging blocker M33's narrative implicitly reported as passing (§5.2). |

---

## 2. What M33 changed — and whether it is still intact

Evidence: `m34-fix-reverification.json`; the pre-image of each file comes from `git show HEAD:<path>` because
M33 recorded each file's pre-fix hash as equal to HEAD.

| File | M33 pre-fix hash | M33 post-fix hash | Current file | Intact? |
|---|---|---|---|---|
| `core/data_quality.py` | `9ebc926f31d99e2b…` | `0151a92768ec15d1…` | `0151a92768ec15d1…` | **yes** — byte-identical |
| `core/engineering/engines/casing.py` | `caec140b33dc6488…` | `17eb484b1a095712…` | `17eb484b1a095712…` | **yes** — byte-identical |
| `tabs/w3_drilling_report.py` | `fd6eca6ceac06977…` | `e2764c18e9756705…` | `e2764c18e9756705…` | **yes** — byte-identical |

M34 re-verified each of the three by contract probes against the current source *and* by running the
regression test the fix claims (13/13 fixes across M32 and M33: VERIFIED — see `m34-fix-reverification.json`):

* **casing** — `fax_supplied`/`pi_supplied` separate "not supplied" from "supplied as 0"; `fyax_psi`,
  `axial_stress_psi`, `internal_pressure_psi` are `None` when the load was absent; absence emits explicit
  warnings; `axial_tension_supplied`/`internal_pressure_supplied` are part of the reported values. Five
  semantic tests plus one offscreen widget smoke test cover it, and two M34 mutants against this contract were
  killed (`M34-M-CASING-FABRICATE`, `M34-M-CASING-ZERONONE`).
* **data_quality** — `24h time coverage` counts entries whose `duration is None` first and reports
  `value=None`, `status="unknown"` instead of computing a subtotal. Two tests cover both branches, and the
  `unrecorded = 0` mutant is killed (`M34-M-NONETOZERO`).
* **w3_drilling_report** — derived-value displays get an explicit domain maximum and a sentinel minimum
  (`"Not computed"`), `collect_data` reads `None` for an untouched field, and `_set_calc` raises the maximum
  rather than silently truncating a real value. M34 reproduced the underlying Qt behaviour independently
  (`QDoubleSpinBox` defaults to maximum **99.99**; `setValue(150)` returns 99.99) and killed both the
  "restore the clamp" mutant and the "drop the documented maximum" mutant.

---

## 3. What M33 claimed — and what the repository says

M33's ledger was recovered intact and is internally consistent: its 8 934 records decompose exactly into the
origins it declared (`M32-LEDGER` 8 570 + `M32-LEDGER-ABSENT` 96 + `M33-NEW` 266 + `M33-FORENSICS` 2 = 8 934).
That ledger was used by M34 as the carry-forward population — not as truth, as *prior disposition evidence*:

| M33 claimed | M34 re-derived | Verdict |
|---|---|---|
| 8 934 ledger items (VC 3 712 / UR 2 837 / INT 2 264 / DF 51 / RW 49 / EXAC 17 / EI 4) | same ledger recovered; 8 933 carried at SAME-FILE-HASH + 1 record without a line | **CONFIRMED as an artifact**, not re-verified item by item in M33's own frame (fingerprints unrecoverable, §4) |
| 2 837 items under review | 2 837 inherited; M34 re-adjudicated all of them with new fact sources → **756 → VERIFIED-CORRECT, 578 → INTENTIONAL-BY-DESIGN, 1 503 still open, 0 re-classified as evidence-incomplete** | **PARTLY REFUTED as a floor**: 1 334 of M33's "open" items were decidable from facts M33's rules never consulted |
| 24 mutants killed | harness gone; M34 designed 16 mutants from the same fix contracts → **15 killed + 1 documented equivalent survivor** (including two M33 never had: restore the Qt clamp, remove the ownership guard) | **NOT REPRODUCIBLE from M33's own record**, independently re-established |
| Full suite green | M34 ran the suite on the actual final tree: **1 814 passed / 0 failed / 0 errors / 4 skipped, 309.9 s, exit 0** | **CONFIRMED** (M33's number was 1 818 collected; M34 collected 1 818 and ran 1 814 with 4 external-opt-in skips) |
| "the two previously-untracked modules `core/operational_time.py`, `core/safety_semantics.py` **are tracked** in that commit" (commit `a9d7dede…`) | `git ls-files --error-unmatch` fails for both files **today**; `git cat-file -e a9d7dede…^{commit}` → **UNRESOLVED**; `dc5939c8…` (M33's "built_from_tree") → **UNRESOLVED**; no commit exists on the reflog | **FALSIFIED** — see §5 |
| Outside-checkout wheel smoke exit 0 | the wheel built from the *actual tracked population* installs, then aborts: `ModuleNotFoundError: No module named 'core.operational_time'` | **FALSIFIED for the repository state** — see §5 |

---

## 4. What could not be recovered (and what that costs)

| Lost | Consequence | M34 response |
|---|---|---|
| `/home/user/m33-tools/*` (sweeper, adjudicator, rule tables) | M33's numbers cannot be regenerated by M33's own code; a reader cannot re-run M33 | M34 rebuilt the toolchain **inside the repository** (`tools/m34/`) so this cannot recur |
| `/tmp/mutate33.py` | the mutation harness cannot be re-executed; only its result table survived | M34 wrote `tools/m34/mutate34.py` in-repo and re-derived the mutation set from contracts |
| `/tmp/m33-commit1-tree`, `/tmp/m33-wheel`, `/tmp/m33-*` artifacts | M33's wheel, its exported commit-1 tree and its SHA evidence are gone; the SHAs do not resolve | M34 rebuilt both stages in-repo; the tracked-only wheel failure is reproduced in `m34-wheel-and-clean-env.json` |
| M33's per-item fingerprint derivation | M34 calibration attempts (line / inline / statement / unparsed / except-body variants) reproduced at most **8.3 %** of M33 fingerprints over untouched records (best single variant 4.8 %) | **abandoned deliberately** — the mismatch is recorded as a finding, and M34 carries records by `(path, family, line, normative text) + source sha256` instead |

---

## 5. Claims falsified, and the two that matter

### 5.1 M33's commit-1 SHA does not exist

`M33_RELEASE_CERTIFICATION.md` and `m33-wheel-and-clean-env.json` cite commit `a9d7dede612b9c5c86de8eea5555a969811cc77a`
and tree `dc5939c80aa8a1a75e9f2a074b196fcacbf3b7f9` as the exported commit-1 tree that carried the two
previously-untracked modules. In this repository **both are UNRESOLVED**
(`git cat-file -e <sha>^{commit}` fails) and can never be inspected again. The reflog shows no commit was ever
created on this branch. A staging-area state that was never committed, or a session that no longer exists,
cannot support a certification claim: **an unreachable SHA is not the same source.**

### 5.2 The tracked population cannot produce a runnable wheel (proven, blocking)

M34 built the wheel from the population a release actually contains — `git ls-files` — and then installed and
started it outside the checkout (the repository's own gate, `verify_release.verify_wheel`):

```
$ python -m build --wheel            # from the tracked-only copy
drillmaster-1.0.0-py3-none-any.whl  1 036 029 bytes  sha256 5d5211600372ced4…
$ python <target>/app.py --package-smoke     # cwd=/tmp, checkout absent from sys.path
  File ".../tabs/w10_Planning_Widget.py", line 19, in <module>
    from core.operational_time import summarize_time_logs
ModuleNotFoundError: No module named 'core.operational_time'
```

`core/operational_time.py` and `core/safety_semantics.py` are **untracked** while tracked production modules
import them (`core/actual_vs_plan.py`, `core/database.py`, `core/ddr_pdf_export.py`, `core/report_engine.py`,
`core/operations_intelligence.py`, `tabs/w10_Planning_Widget.py`, …). Any release artefact built from the
repository as it stands cannot start. This is a **repository blocker**, not an environment limit, and it is
cleared by one action: add the two files (and their tests) to the Commit-1 population.

---

## 6. What remains open from M33, now measured in M34's frame

* **1 503** items M33 left under review are still under review, and **387** hits M34's own sweep found are open
  as well — **1 894** in total (`m34-closure-invariants.json`), of which **475 are HIGH**.
* Each open item names the fact that is missing (`R-TRUTH-UNKNOWN` 523 — the subject's type is not declared,
  bound, documented or provable from its callers; `R-DEF-UNKNOWN` 342 — the default's consumer path is
  unclassified; `R-PLAN-OTHER` 184; `R-TRUTH-NUMERIC` 102; `R-EXC-PASS` 98; …). No open item was closed on
  pattern alone.
* M33's four `EVIDENCE-INCOMPLETE` records are carried unchanged (they are rule errors, and the rule that
  raised them has since been fixed, but re-running them is part of the open register rather than a silent
  rewrite) — listed verbatim in `m34-reconciliation.json`.
* M33's 51 defect-fixed records, 49 removed-with-evidence records and 25 external records are carried with
  their evidence intact.

**Bottom line.** M33 produced a real, internally consistent audit and three verified code fixes; its harness
and its commit/wheel evidence did not survive; its certification verdict ("NOT RELEASE-CERTIFIABLE") stands;
two of its specific claims — a resolving commit and a working tracked-only wheel — are false for this
repository, and the second one is a release blocker that M34 proved by execution.
