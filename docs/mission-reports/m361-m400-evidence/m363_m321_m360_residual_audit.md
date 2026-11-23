# M363 — M321–M360 residual audit, phase by phase

Audited on 2026-11-23 against the tree at `3ca8b80`, before any M361–M400 change. Each phase is checked against
eight kinds of evidence: code, UI path, persistence, provenance, tests, mutation, benchmark and the SHA that carries
the work. The source of each claim is the M321–M360 closure report and its evidence files. Each claim was then
re-checked in the code with `grep` (UI references, test files, mutation catalogues).

Severity: **high** means a wrong or misleading engineering answer is possible; **medium** means a qualification or
traceability gap; **low** means documentation or tooling.

## 1. Phases that delivered something

| Phase | Claimed | Code / UI / persistence / provenance | Tests / mutation / benchmark | Unfinished work and responsible files | Root cause | Severity | Depends on | Exit criterion | M361–M400 action |
|---|---|---|---|---|---|---|---|---|---|
| M321 | DONE | baseline doc | – | none | – | – | – | – | – |
| M322 | DONE (A-1…A-9) | register | – | none open | – | – | – | – | – |
| M323 | DONE | `core/cement_job_reconciliation.py`, `core/architecture_diff.py` | `test_m323_m328_*`; mutated (M327) | none | – | – | – | – | – |
| M324 | DONE, decision with owner | `m324_pyside_upgrade_decision.md` | CI eval `45144294084` 10/10 | §102 says "6.8.5 is commercial-only" and §7 says "does not exist publicly". Both are imprecise: a 6.8.5 open-source **source** tarball exists; there are **no PyPI wheels** | wording written from the PyPI JSON only | low (misleading claim) | – | corrected record | **M364 addendum + M378** |
| M325 | NOT EXECUTED | – | – | pin raise | owner gate | – | owner approval | owner decision recorded | M378 / M385 (stays BLOCKED) |
| M326 | D63 BLOCKED, D74 PARTIAL | `core/qt_lifetime.py`, probes | `test_d74_*`, D63 probe | D63: windows retained by design on 6.8.1.1. D74: closed windows retained (cause 1) | Qt 6.8.1.1 PYSIDE-2201 not fixed in the pinned version | medium | M325 | pin ≥ 6.8.2 + release probe on Windows | M376 (stays BLOCKED) |
| M327 | DONE (121 mutants, 119 killed, 2 equivalent) | `tools/quality/mutation_m321_m360.py` | run on `6ace038` | `core/calculation_clone_contract.py` (M303/M304 identity) is in **no** catalogue; the run predates `246e7bf` (only a probe changed) | catalogue scope was the M321–M360 modules | medium | – | identity code mutated | **M389** (new catalogue includes M365 identity) |
| M328 | DONE | `core/history_replay.py` ← `core/calculation_history.py` ← History tab | `test_m323_m328_*`; mutated | none for M314/M317/M318. W13 page cases (M126) have their own verify path | – | – | – | – | M366 adds an M366 adapter |
| M329 | DONE | `core/architecture_diff.py`, `tabs/well_architecture_panel.py` | 3 test files; mutated | none | – | – | – | – | – |
| M331 | DONE | yield-unit registry in `core/cement_job_reconciliation.py` | parametrised tests | mass yield units refused (by design) | – | – | – | – | – |
| M333 | DONE | `core/report_sections.py` (no direct UI import: reached through report provenance) | RS-* killed | the UI path is indirect; there is no UI test that opens a manifest | – | low | – | – | M395 E2E |
| M334 | DONE | `core/citation_record.py`, `tabs/knowledge_assistant.py` | CR-*, KA-* killed | none | – | – | – | – | – |
| M349 | DONE, 44 / 44 | `tools/quality/benchmark_m349.py` | `--check` | covers bit hydraulics (M314), cement volumes, T&D. It does **not** cover circulating-system losses, ECD, survey/minimum curvature, anti-collision, casing, MSE, kill sheet | scope was the M314–M318 surfaces | medium | – | independent benchmark per domain | **M396** |
| M352 | DONE (ratchet) | `tools/quality/prepush_guard_m352.py` | – | proves a Linux-font ratchet, not Windows width | no Windows UI runner | low | – | – | stays as stated |
| M360 | DONE | closure report | – | phases without deliverable listed (§2) | – | low | – | – | this audit |

## 2. Phases with no deliverable

M330, M332, M335–M348, M350, M351 and M353–M359 produced nothing. The closure report says so and claims none
of them as done. Their titles are not recorded anywhere in the repository; the M321–M360 directive text was never
committed. This audit therefore cannot name each one, and does not invent names. The M361–M400 directive
re-issues the engineering-completion scope explicitly. Each domain is mapped to its new phase here:

| Gap kept open by M321–M360 (from the M320 roadmap and the M320 capability rows) | Responsible files | Root cause | Severity | M361–M400 phase | Exit criterion |
|---|---|---|---|---|---|
| D87: equal-timestamp / NULL-timestamp clone and archive identity | `core/calculation_workbench.py`, `core/calculation_clone_contract.py` | identity rested on `created_at` only | medium | M365 | fingerprint pin + tests for equal / NULL timestamp + legacy rule + residual |
| Hydraulics workflow: budget, pump limits, sensitivity, plan vs actual | `tabs/w13_Engineering_Calculator.py`, `core/hydraulics_engine.py`, `core/w13_hydraulics.py` | W13 computed one operating point only | medium | M366 | service + UI + persistence + replay + independent tests |
| T&D benchmark wells, buckling / side force reporting | `core/engineering/engines/torque_drag.py` | M349 covered two geometries | medium | M367 | independent benchmark wells in M396 |
| Survey / directional completeness (VS, closure, DLS, tie-in, export) | `core/engineering/engines/trajectory.py`, `core/survey_revisions.py` | no independent closed-form benchmark | medium | M368 | M396 benchmark |
| Anti-collision labelling (centreline only) | `core/engineering/engines/anti_collision.py` | – | low | M369 | label audit |
| Mud / hole cleaning, casing beyond the 5C3 subset, MSE / bit / BHA, kill sheet | engines | owner gates P8, P11, P12, P18 | medium | M370–M373 | catalogue rows with gates |
| W12 Analysis KPI structural definitions | `tabs/w12_Analysis.py` | M285 specs cover the dashboard only | medium | M374 | KPI spec rows |
| 35-step MainWindow journey | `tests/` | the M139 journey has 30 steps | low | M375 | journey test |
| D51 / M266 / D88 run-state vocabulary | CI docs | – | low | M377 | record |

## 3. Defect status carried into M361

| ID | State at `3ca8b80` | Action |
|---|---|---|
| D87 | PARTIALLY RESOLVED (equal-timestamp case open; NULL created_at refused) | M365 |
| D63 | BLOCKED BY OWNER DECISION (pin) | stays |
| D74 | PARTIALLY QUALIFIED | stays |
| D51 | explained for the M324 probe (missing `core.qt_gc`); the M266 event is unexplained and under the M309 monitor | M377 record |
| D88 | Source 3.12 leg can hit the 60-min limit (coverage); a TIMEOUT is not a FAILURE and not a SUCCESS | M377 record |
| D89–D92, A-1…A-9 | FIXED | – |
