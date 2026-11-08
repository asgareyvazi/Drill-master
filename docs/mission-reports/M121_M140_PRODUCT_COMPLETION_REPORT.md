# M121–M140 Product Completion Report

Statuses: PASS / PARTIAL / OPEN / BLOCKED / NOT IMPLEMENTED / NOT RUN / OWNER REVIEW REQUIRED.
Product label: **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED**. No result here is a standards
qualification, a field acceptance or a release. Windows CI is not Windows desktop acceptance. Offscreen Qt runs
are labelled as such. All data used is SYNTHETIC.

Allowed description of the product state: *Integrated drilling engineering product candidate — implemented and
qualified within the documented technical scope; Windows desktop acceptance, field acceptance, legal approvals and
release authorization remain open.*

The single live register, including the single defect register (D1–D56; D19–D22 are a numbering gap), is
[`docs/engineering/PRODUCT_CAPABILITY_MATRIX.md`](../engineering/PRODUCT_CAPABILITY_MATRIX.md), section
"M121–M140". This report summarises it and carries the evidence; it does not compete with it.

## A. Git

| Item | Value |
|---|---|
| Branch | `arena/72010272-drill-master` only; upstream `origin/arena/72010272-drill-master` |
| Start | report commit `27e3bc2` of M101–M120 (code `c7b6ac1`); both green on Source and Windows CI |
| **Final code SHA** | **`443a1e310afa15405cb36097afcb7daa93225726`** (every code change of the programme; the final full suite, the complete mutation run and the final CI ran on this tree) |
| Report commit | adds this file, the final register rows and the mutation evidence, and carries the D57 fix of the mutation harness (`tools/quality/mutation_m121_m140.py`; not imported by any test or CI job) — product code and tests are identical to the final code SHA. Its SHA and CI are in the final reply, because a file cannot contain its own commit SHA |
| `drill-Master` | untouched: `e3fa42a3257e981d9bdf9d012c97919e3352a53a` before and after (`git ls-remote`) |
| Not done (by instruction) | no `main` branch, no force-push, no history rewrite, no merge, no tag, no release, no EXE/installer publication, no signing, no settings / protection / ruleset change |

The git command set required by the brief (`status --porcelain=v2 --branch`, `status --short`,
`branch --show-current`, `branch -vv`, `rev-parse HEAD`, `rev-parse --abbrev-ref --symbolic-full-name @{u}`,
`remote -v`, `ls-remote`, `stash list`, `worktree list --porcelain`, `diff --check`, `log --oneline --decorate -30`)
was run at the start, before each checkpoint and at the end; its output at handoff is quoted in the final reply.

**Sandbox resets.** The sandbox was reset during the programme (most recently during M140, which killed a running
full suite). Each time the local branch ref went back to the sandbox base and the venv, the Qt support libraries
(libglvnd, libxkbcommon, dbus, expat, a GLX stub `libGL.so.1`) and scratch space were lost. Recovery used only
`git fetch` plus a compare-and-swap `git update-ref` to the verified remote tip and `git read-tree HEAD`; there was
no `reset --hard` and no force-push. The working tree survived each time; no pushed commit was lost. The suite that
was killed was re-run in full after recovery.

Phase checkpoints (CI on that exact SHA; "no run" = GitHub ran only the pushed tip):

| Phase | Commit | Source release gate | Windows release validation |
|---|---|---|---|
| M122 (D28) | `4878476` | ❌ 41831032682 (3.13 load-test precondition) | ✅ 41831032644 |
| M122 follow-up | `bffe3c3` | no run (pushed with `b820552`) | no run |
| M123 (D6) | `b820552` | cancelled 41846566897 (superseded) — not a pass | ✅ 41846566842 |
| M124 (D7, D38) | `f790f40` | ❌ 41934748855 (D40, found by CI) | ✅ 41934748871 |
| D40 | `33e7511` | no run (pushed with `56d5f6c`) | no run |
| M125 + M126 | `56d5f6c` | ✅ 42120776989 | ✅ 42120776954 |
| M127 | `82071b2` | ❌ 42126938336 (D46, 3.12) | ✅ 42126938432 |
| M128 | `45291cd` | ✅ 42132964518 | ✅ 42132964488 |
| M129–M131 | `7b13a1c` | ❌ 42357828918 (D46 reopened) | ✅ 42357829059 |
| M132 | `600b2f0` | ❌ 42371267520 (D51 hang) | ✅ 42371267514 |
| M133 + M134 | `75b2d38` | ❌ 42375856374 (D52) | ✅ 42375856411 |
| M135 | `f620564` | ❌ 42381281727 (D52) | ✅ 42381281820 |
| M136 | `76059dd` | ❌ 42387631121 (D52) | ✅ 42387631127 |
| D52 + D53 + M137 | `00ddbe6` | ❌ 42460255134 — 3.11 ✅ (job 128667817522), 3.13 ✅ (128667817652), 3.12 ❌ (128667817789: 4973 passed / 1 failed — D46 load child; D52 did not recur) | ✅ 42460255146 |
| M138 + M139 + M140 (final code) | `443a1e310afa15405cb36097afcb7daa93225726` | ❌ 42465610612 — 3.11 ✅ (job 128684300945), 3.12 ❌ (128684301142), 3.13 ❌ (128684301121): each 5018 passed / 4 skipped / 1 failed — the same D46 load child | ✅ 42465610586 (job 128684301197) |

A red Source run was never treated as a pass: each one produced a defect row (D40, D46, D51, D52) and a fix or a
bounded-risk statement.

## B. Defect register (summary of the live register)

| Defect | Priority | State at the end of M140 | Evidence |
|---|---|---|---|
| D28 Knowledge Assistant worker lifecycle | P3 | **RESOLVED (M122)** — root cause reproduced deterministically (*check, then connect* on a retiring worker); connect-before-check ownership, no terminate, no timeout increase, no retry; late results rejected by generation tokens | `test_m122_assistant_worker_lifecycle.py` (16), load runs in a fresh interpreter |
| D6 MSE lineage | P1 | **PARTIAL stays** (by design): new records carry lineage v2 (well / wellbore / report / explicit MD with unit / inputs / method); legacy rows are labelled "LEGACY — LINEAGE UNKNOWN — NOT DEPTH-REPRODUCIBLE" and can only gain lineage through the audited repair (evidence, confirmer, before / after, reason) — never inferred | M123, `test_m123_mse_lineage.py` (16) |
| D7 Central selection identity | P1 | **RESOLVED (M124)**: W12 snapshots, trajectory comparison, Knowledge Assistant, OA and every context job use `core.selection_context` identity; local render tokens only for their own purpose | `test_m124_central_identity.py` (11) |
| D11 Depth datum / CRS | P2 | **PARTIAL stays (owner gate)**: explicit vertical shift only; CRS mismatch → NOT ASSESSED; no transformation | M105, M129, M132 |
| D38 Global pickers | P2 | resolved (M124) | |
| D39 Well Volumes annulus double count | P1 | resolved (M126) | |
| D40 Late Knowledge Assistant results after cleanup | P2 | resolved (M126; found by CI) | |
| D41 Hydraulics cell precision | P2 | resolved (M126) | |
| D42 Weight / T&D survey source | P2 | resolved for new runs (M127) | |
| D43 Choke Schedule | P2 | resolved (M128) | |
| D44 / D45 Comparison / Anti-Collision references | P1 | resolved (M129) | |
| D46 CI 3.12/3.13 load-test hang | P2 | **OPEN (reopened) — root cause UNKNOWN; now the Source gate blocker.** It failed the Source gate on `00ddbe6` (3.12) and on the final code `443a1e3` (3.12 and 3.13); 3.11 has never failed and it was not reproduced locally. The dumps show a worker inside a SQLite call (`KnowledgeIndex._build_fts` `executemany`; SQLAlchemy `fetchall`) and, at `00ddbe6`, the main thread blocked inside `processEvents()` with no Python frame above it. Bounded: the child watchdog ends the run inside the job timeout and names the threads. The D53 fix did not remove it. **Product risk stated:** the same pattern could stall the desktop when the Knowledge Assistant is cancelled under heavy CPU load (not observed outside this test) | M129, M132, M134, M140 |
| D47 Bit run cost comparison | P1 | resolved (M130) | |
| D48 Performance chart lines | P2 | resolved (M131) | |
| D49 Manager retention of disposed widgets | P1 | resolved (M132) | |
| D50 Child hang diagnostics | P2 | resolved (M132) | |
| D51 CI hang inside the release gate | P2 | **OPEN — root cause UNKNOWN, risk bounded** (watchdog ends the run inside the job timeout and names the frame) | M134 |
| D52 Deferred deletes in the test session | P3 | **RESOLVED (fix `00ddbe6`)** — the D52 symptom did not recur in CI on `00ddbe6` or `443a1e3` (all three Python versions) nor locally | `test_d52_deferred_deletes.py` |
| D53 Garbage collection off the GUI thread in tests | P2 | **RESOLVED (fix `00ddbe6`)** — no SIGSEGV in the local full suites (4974 / 4 at `00ddbe6`, 5019 / 4 at M140) or in CI; D46 is **not** claimed fixed by it | `test_d53_gui_thread_gc.py` (13), mutants 6/6 |
| D54 Package verification outside the folder | P2 | **resolved (M140)** | `test_m140_adversarial.py`, `ADV-verify-*` 3/3 |
| D55 LSRYP from inverted θ3 / θ6 | P2 | **resolved for new cases (M140)** by "M133 mud evaluation v2"; v1 replayed, never re-based | `ADV-lsryp-*`, `ADV-mud-*` 4/4 |
| D56 Service contracts accepting values the UI cannot produce | P3 | **resolved (M140)** | `ADV-currency/md/npt/trend-*` 4/4 |
| D57 Mutation harness: shadowed test list | P3 | **resolved (M140)** — a second `T122` (from `7b13a1c`) narrowed the 7 KA mutants to the load test; found by the complete run (6 survived); fixed; 9/9 KILLED on the corrected lists | `mutation_m140_t122_rerun.json` |
| D13 Licences | P2 | disclosure holds; decisions are owner gates (M137) | |
| D17 Coverage numerator labelling | P3 | process (holds) | |
| D1–D5, D8–D10, D12, D14–D16, D18, D23–D27, D29–D37 | — | **hold** — their regression tests ran in the final full suite; none reopened by the M140 adversarial audit | §F |

## C. Capability status (M121–M139)

| Phase | Capability | Status | Main evidence (tests are in `tests/`) |
|---|---|---|---|
| M121 | Forensic baseline, source-backed defect map | PASS | matrix "M121" |
| M122 | Knowledge Assistant worker lifecycle (D28): explicit states, keep-until-finished ownership, stress cases (cancel before / during / before emit / after queueing, scope change, supersede, close, shutdown, repeated cycles, delayed scheduling, out-of-order completions) | PASS | `test_m122_assistant_worker_lifecycle.py` |
| M123 | MSE lineage v2, audited repair, legacy label, OA lineage classes, D33 deletion policy verified | PASS (D6 PARTIAL by design) | `test_m123_mse_lineage.py`; MSE mutants |
| M124 | Central selection identity in every background consumer; global pickers | PASS | `test_m124_central_identity.py`; CTX mutants |
| M125 | 27 W13 leaves classified from the product (§D) | PASS | `test_m125_w13_classification.py`; CLS mutants |
| M126 | Well Volumes (component tables, no invented dimensions) and Hydraulics contracts (component losses, bit ΔP, ECD only when valid) | PASS | `test_m126_volumes_hydraulics.py`; WV / HY mutants |
| M127 | Weight on a pinned survey revision with soft-string Johancsik; Casing Strength API TR 5C3 pipe-body subset with per-field provenance and a pinned architecture revision; no yield from a grade | PASS | `test_m127_weight_casing.py`; WT / CS mutants |
| M128 | Drill-pipe pressure schedule WORKSHEET (Choke Schedule); Kill Sheet stays TRAINING AID | PASS | `test_m128_dp_schedule.py`; DP mutants |
| M129 | Multi-Survey → immutable survey revisions; anti-collision centre-to-centre SCREENING, no SF, CRS / datum mismatch → NOT ASSESSED | PASS | `test_m129_surveys_anticollision.py`; AC / MS mutants |
| M130 | Bit run workbench: lifecycle, DDR linkage, incomplete runs visible, SCENARIO cost per length with explicit currency, comparison, History, CSV | PASS | `test_m130_bit_runs.py`; BR mutants |
| M131 | Drilling-parameter trends: time or depth axis (never mixed), no interpolation, missing / invalid listed, MSE discrete | PASS | `test_m131_parameter_trends.py`; TR mutants |
| M132 | Revision-aware 3D layers (survey / plan / targets / architecture), legend, scope labels, no overlay across frames | PASS | `test_m132_trajectory_layers.py`; TL mutants |
| M133 | Mud evaluation (LAB / ASSUMED / DERIVED / UNKNOWN), History, navigation, no HB claim; v2 since M140 (D55) | PASS | `test_m133_mud_engineering.py`; MUD mutants |
| M134 | NPT event reconciliation: provenance, UNCERTAIN groups, decisions with evidence and audit, no double counting, drill-down | PASS | `test_m134_npt_reconciliation.py`; NPT mutants |
| M135 | End-of-well package with manifest, SHA-256, audit record, verification; "Approved By" ≠ approval; Qt PDF boundary | PASS (D54 hardened in M140) | `test_m135_well_package.py`; WPK mutants |
| M136 | Security honesty and hardening: append-only audit triggers, owner-only files, session lock, Security Status; HMAC / DPAPI / SQLCipher design only | PASS (owner gates open) | `test_m136_security_hardening.py`; SEC 25 KILLED + 1 EQUIVALENT (proof in the register) |
| M137 | Dependency / licence / packaging reconciliation; PyMuPDF isolation proposal (design only) | PASS (owner gates open) | `test_m137_dependency_reconciliation.py`; DEP / SMK mutants |
| M138 | Panel states, Retry, empty / no-well / error explanations, RTL / LTR, chart axes; measured offscreen only | PASS (not Windows evidence) | `test_m138_ux_states.py`; `m140-evidence/ux_m138.json`; UXM 11/11 |
| M139 | 30-step journey through the real `MainWindow` | PASS (offscreen) | `test_m139_end_to_end_journey.py`; JRN 3/3 + W11 1/1 |

## D. The 27 W13 leaves (M125 audit; registry "M129 calculator contracts v7")

Every leaf is classified by what it really is; a WORKSHEET or SCREENING result is never presented as an approval.
Classes: CONTRACT (saved case, re-run with the recorded method version), SCREENING CONTRACT (saved and re-run, but
the method is a screening subset), WORKSHEET (structured capture of a defined calculation, no engineering claim),
TRAINING AID, REFERENCE-ONLY, NOT_SUPPORTED (not a W13 case; the reason is shown and Save is disabled).

| # | Leaf | Class | Evidence / note |
|---|---|---|---|
| 1 | Quick Calc | CONTRACT | M107/M125 registry; save → History → re-run MATCH |
| 2 | Bit Hydraulics | CONTRACT | MSE output stored as a case (no depth claimed; M123) |
| 3 | TFA | CONTRACT | M125 |
| 4 | HP FP | CONTRACT | M125 |
| 5 | OWR | CONTRACT | M125 |
| 6 | Build/Turn | CONTRACT | M125 |
| 7 | Weight/Dilution/Mix | CONTRACT | D26 corrected formula; text input re-run (M107) |
| 8 | Mud Lab | CONTRACT | M107 |
| 9 | Well Volumes | CONTRACT | M126: pump / string / casing tables with component ids, no invented dimensions |
| 10 | Buoyancy | SCREENING CONTRACT | BF = 1 − (pcf/7.48)/65.5 (7.48 vs 7.48052 owner gate); M139 journey steps 13–16 |
| 11 | Kick Tolerance | SCREENING CONTRACT | M107 |
| 12 | Pore Press FG | SCREENING CONTRACT | M107 |
| 13 | Stuck Pipe | SCREENING CONTRACT | unrecorded inputs never 0 (M107) |
| 14 | Fishing | SCREENING CONTRACT | M107 |
| 15 | Rheology | SCREENING CONTRACT | M107 |
| 16 | Nozzle Optimization | SCREENING CONTRACT | zero fall-backs rejected (M107) |
| 17 | Hydraulics | SCREENING CONTRACT | M126: component losses, bit ΔP, annular / pipe / total; ECD only when valid; without a survey NOT ASSESSED |
| 18 | Weight | SCREENING CONTRACT | M127: pinned survey revision, soft-string Johancsik through `TorqueDragEngine` |
| 19 | Casing Strength | SCREENING CONTRACT | M127: API TR 5C3 pipe-body subset, per-field provenance, pinned architecture revision, no yield from a grade |
| 20 | Cement Volume | WORKSHEET | M109 |
| 21 | Balanced Plug | WORKSHEET | M107 |
| 22 | Mud Volume Balance | WORKSHEET | M107 |
| 23 | Choke Schedule | WORKSHEET | M128 drill-pipe pressure schedule v1 (ICP → FCP, Wait and Weight) |
| 24 | Kill Sheet | TRAINING AID | owner gate; no procedure added (M128) |
| 25 | DP Database | REFERENCE-ONLY | M125 |
| 26 | Multi-Survey | NOT_SUPPORTED as a W13 case | M129: recorded as an immutable survey revision (`RECORDED_ELSEWHERE`) |
| 27 | Anti-Collision | NOT_SUPPORTED as a W13 case | M129: trajectory comparison record, "SCREENING — NO ISCWSA UNCERTAINTY — NO SEPARATION FACTOR — NOT APPROVED (centre-to-centre)"; CRS / datum mismatch → NOT ASSESSED |

Totals: CONTRACT 9, SCREENING CONTRACT 10, WORKSHEET 4, TRAINING AID 1, REFERENCE-ONLY 1, NOT_SUPPORTED 2 = 27.

## E. Methods and independent evidence (versioned; no constant changed globally)

| Method | Version | Golden / independent check |
|---|---|---|
| MSE lineage | `LINEAGE_VERSION = 2` (M123) | MD only when entered (m / ft, > 0, finite), only with the wellbore; same-well checks |
| Well volumes | "M126 well volumes v1" | closed-form string and annulus volumes of the synthetic 3000 m well (rel 1e-12); lag = annulus / 10 bbl/min |
| Hydraulics | M126 contract | bit ΔP = Q²·MW/(10858·TFA²), HHP = ΔP·Q/1714, ECD = MW + ΣΔPann/(0.052·TVD); turbulent / laminar Bingham rows at 420 / 126 gpm; velocity Q/(2.448·D²) |
| Weight card and T&D | "M127 weight card and soft-string T&D v1" | vertical: pickup = slack-off = buoyed weight, torque 0; straight 30° hole F = Σ w_b ΔL (cos I ± μ sin I), T = Σ μ w_b ΔL sin I · OD/24 |
| Casing strength | M127 (API TR 5C3 pipe-body subset) | Barlow burst 0.875·2·Yp·t/D; pipe-body yield Yp·π/4·(D² − d²) |
| Drill-pipe schedule | "M128 drill-pipe pressure schedule v1" | linear ICP → FCP in equal stroke steps, exact rows |
| Comparison | "M129 centre-to-centre screening v2" (v1 replay) | hash-verified revisions, grid north, RKB / RT / MSL datum, no transformation |
| Bit run cost | "M130 bit run cost per length v1" | 300.00 and 347.06 USD/m by hand; M140: 160.00 NOK/m |
| Parameter trends | "M131 drilling-parameter trends v1" | markers and recorded min–max bars only |
| 3D layers | "M132 revision-aware 3D layers v1" | MD 750 → TVD 747.15, E 32.54 |
| Mud evaluation | "M133 mud evaluation v2" (v1 replay) | PV 20 / YP 10 → θ600 50, θ300 30, n 0.7365378, K 154.8235; 75 pcf → 10.026041 ppg; θ3 5 / θ6 7 → LSRYP 3; θ3 > θ6 → NOT ASSESSED (v2) |
| NPT reconciliation | "M134 NPT event reconciliation v1" | 10.0 h certain + 4.5–6.5 h uncertain |
| End-of-well package | "M135 end-of-well package v1" | SHA-256 per file, manifest SHA in the audit log; COMPLETE = no FAILED part |
| Dependency audit | "M137 dependency audit v2" | 26 pins, 0 FAIL |
| Panel states | "M138 panel states v1" | evidence JSON, LTR and RTL |

7.48 vs 7.48052 stays an owner gate: Buoyancy keeps its versioned 7.48; the mud evaluation uses the central
`MudProperties.mw_ppg` (7.48052) — both are labelled, neither was changed globally.

## F. Quality and CI

All figures are for the final code SHA `443a1e310afa15405cb36097afcb7daa93225726` unless a row says otherwise.

**Full suite (local, offscreen Qt, Linux, Python 3.11.2, PySide6 6.8.1.1; NOT Windows desktop):**

| collected | passed | skipped | failed | errors | xfailed | xpassed | deselected | runtime |
|---|---|---|---|---|---|---|---|---|
| 5023 | 5019 | 4 | 0 | 0 | 0 | 0 | 0 | 1990 s (33:10) |

The 4 skips are the four opt-in tests (`test_ddr_acceptance.py` ×2, `test_mineru_real_integration.py`,
`test_packaging_smoke.py`). They did **not** pass. No skip, xfail or exclusion was added.

Count history in this programme (new tests only; nothing removed): 4707 (M120) → … → 4877 (M132) → 4905 (M134)
→ 4920 (M135) → 4944 (M136) → 4978 (D52 + D53 + M137) → 5023 (M138 +10, M139 +1, M140 +34).

**Mutation.** All 289 mutants of `tools/quality/mutation_m121_m140.py` were run on the final code tree in one complete run (`complete=True`, 2352 s): **282 KILLED, 6 SURVIVED, 1 declared EQUIVALENT, 0 INVALID** (`m140-evidence/mutation_m121_m140_complete.json`). The 6 survivors were all KA (D28 lifecycle) mutants and exposed **D57**, a harness defect: a second `T122` assignment added at `7b13a1c` had narrowed their test list to the load test alone. After the fix (in the report commit; the script is not imported by any test or CI job), the 9 mutants on the corrected lists were re-run: **9/9 KILLED** (`mutation_m140_t122_rerun.json`). Final: **288 KILLED + 1 EQUIVALENT of 289, 0 survived, 0 invalid**; product code identical between the runs. The EQUIVALENT mutant (`SEC-empty-password-unlocks`) carries its proof in the script and the register (three independent layers refuse an empty password; the two stronger variants are killed). Phase runs kept as evidence: M138/M139 15/15 (`mutation_m138_m139.json`), M140 adversarial 14/14 (`mutation_m140_adversarial.json`), M127–M129 rerun 41/41.

**Coverage (local, Python 3.11.2, branch coverage, `pyproject.toml` settings; not the CI 3.12 measurement, which was not produced — see below):** **69.95 %** (71238 / 101841), floor 45.50, target ≥ 65 met; programme-start baseline as recorded in the M121 brief 67.78 % (65304 / 96344). The coverage run was a second complete local suite: 5019 passed / 4 skipped / 0 failed (2498 s).

**Gates at the final code SHA:** lint 726 (ceiling 727; no finding in an added or modified file); exception gate
rc 0; privacy 0 findings; schema compatibility 26/26 (old `0822a28`, new `443a1e3`); dependency audit 26 pins, 0 FAIL; constant / engine
inventories and the journey index current.

**CI on the exact final code SHA:**

| Workflow | Run | Jobs | Result |
|---|---|---|---|
| Source release gate | 42465610612 | 3.11 128684300945 ✅; 3.12 128684301142 ❌; 3.13 128684301121 ❌ | **FAILURE** — 5018 passed / 4 skipped / 1 failed on 3.12 and 3.13; the failure is D46 (`test_cancel_under_cpu_load_releases_every_worker`: the fresh-interpreter load child hit its 600 s watchdog). Warnings unchanged: 3.11 39 / 12 groups, 3.12 and 3.13 102 / 13 groups |
| Windows release validation | 42465610586 | windows-release 128684301197 ✅ | success (bundle build and smoke; not desktop acceptance) |

**This is not a passing Source gate and is not reported as one.** Coverage is measured by the 3.12 leg only after its pytest stage passes, so CI produced no coverage figure for the final code; the local figure above is labelled as local. The report commit's own CI is a second sample of identical product and test code; its result is quoted in the final reply.

## G. Owner register (open decisions; none taken by automation)

| Gate | State | Where it shows |
|---|---|---|
| Windows interactive desktop acceptance | OPEN | Windows CI builds and smoke-tests the bundle; no interactive acceptance was performed |
| Field acceptance | OPEN | no field data used (synthetic only) |
| ISCWSA error models / `welleng` | OPEN | anti-collision stays centre-to-centre screening without SF |
| pwptemp / torque_drag (LGPL-3.0) | OPEN | not bundled (`BUNDLE_EXCLUDED`, spec excludes, smoke rejects) |
| PyMuPDF (AGPL-3.0), mandatory and pre-existing | OPEN | notices state that shipping licence texts does not by itself meet AGPL obligations; isolation proposal `core/pdf_backend.py` (design only) |
| Qt for Python (LGPL-3.0) | OPEN | one-folder bundle keeps the Qt libraries replaceable; obligations need owner confirmation |
| OCR / RapidOCR / onnxruntime and bundled models | OPEN | not bundled; models need owner review |
| AI / ML models, weights, GPU, cloud LLM | OPEN | none bundled or called |
| MinerU (custom licence) | OPEN | not bundled |
| qtribbon (licence unknown) | OPEN | excluded from the bundle (M137 fixed the missing exclusion) |
| Kill Sheet as TRAINING AID | OPEN | unchanged |
| 7.48 vs 7.48052 gal/ft³ | OPEN | versioned methods; no global constant change |
| Money / currency | OPEN | explicit currency per scenario (M130), never mixed or converted |
| CRS transformation | OPEN | none performed; mismatch → NOT ASSESSED (D11 PARTIAL) |
| Database encryption / external integrity key (HMAC, DPAPI, SQLCipher) | OPEN | design only (M136); Security Status says NOT PROVIDED |
| Idle-lock policy | OPEN | `DRILLMASTER_SESSION_IDLE_MINUTES` off by default (M136) |
| Method approvals | OPEN | every result carries its method label; nothing is "approved" by the software ("Approved By" ≠ approval, M135) |
| Release, signing, tags, publication | OPEN | none done |

## H. Conclusion

*Integrated drilling engineering product candidate — implemented and qualified within the documented technical
scope; Windows desktop acceptance, field acceptance, legal approvals and release authorization remain open.*
**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

**Qualification is not complete on CI:** the Source release gate on the final code SHA failed on Python 3.12 and 3.13 with one failure each (D46, open, root cause unknown); Python 3.11, the Windows release validation, the local full suite (5019 passed / 4 opt-in skips / 0 failed), the complete mutation run and every static gate pass. This report does not turn that red run into a pass; closing D46 (or an owner decision about it) is a precondition of any release decision.

Residual risks carried forward (each in the register):
- **D46 — the final code's Source gate is red because of it** (3.12 and 3.13: 1 failure of 5023 each; 3.11 green); root cause UNKNOWN, bounded by the child watchdog; a possible desktop stall when cancelling the Knowledge Assistant under heavy load is stated as a product risk. D51 — CI hang, root cause UNKNOWN, bounded by the watchdog.
- D6 and D11 PARTIAL by design — legacy MSE rows cannot gain lineage without audited evidence; no CRS transformation without an owner decision.
- The `trg_mse_lineage_repair_nodelete_v1` and audit triggers can be dropped by anyone with write access to the database file; the external-key chain is design only.
- The local test environment needs a GLX stub `libGL.so.1` (offscreen platform; GLX never called) — CI uses the distribution libraries.
- `TableManager` retention noted in M132; lint debt 726 under the 727 ceiling; broad exception handlers 680 → 682 and silent 188 → 191 over the programme, each silent handler explained (gate rc 0).
- The M135 cancelled-build `.partial` folder is removed on discard; a process killed mid-build can leave one (named `.partial`, never verified).
- M136 limits (no encryption, file permissions POSIX-only, Windows ACL NOT PROVIDED); the M137 bundle licence evidence is verified only by the Windows release job.
- M138 timings come from offscreen Linux on a 2-CPU sandbox, not from a Windows desktop.
