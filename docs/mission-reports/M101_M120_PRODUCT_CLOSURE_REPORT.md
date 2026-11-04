# M101–M120 Product Closure Report

Statuses: PASS / PARTIAL / BLOCKED / NOT IMPLEMENTED / NOT RUN / OWNER REVIEW REQUIRED.
Product label: **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED**. No result here is a standards
qualification, a field acceptance or a release. Windows CI is not Windows desktop acceptance. Offscreen Qt runs
are labelled as such.

Allowed description of the product state: *Integrated drilling engineering product candidate — implemented and
qualified within the documented technical scope; Windows desktop acceptance, field acceptance, legal approvals and
release authorization remain open.*

The single live register, including the single defect register (D1–D35), is
[`docs/engineering/PRODUCT_CAPABILITY_MATRIX.md`](../engineering/PRODUCT_CAPABILITY_MATRIX.md), section
"M101–M120". This report summarises it and carries the evidence. It does not compete with it.

## A. Git

| Item | Value |
|---|---|
| Branch | `arena/72010272-drill-master` only; upstream `origin/arena/72010272-drill-master` |
| Start | code `c776e8cd863b88623df0a8719cf497fbede93d73`, report `e90843fd59608508bc0eb96bb573f7286c22c7ca` (M82–M100); the first programme commit `fc2daf2` has `e90843f` as its parent; 19 code/phase commits follow it |
| **Final code SHA** | **`c7b6ac194fc531995da5d4722254100dc2fbfab1`** (every code change of the programme; the M118 qualification and CI ran on it) |
| Report commit | the docs-only commit that adds this file; its SHA and CI are in the final reply, because a file cannot contain its own commit SHA |
| `drill-Master` | untouched: `e3fa42a3257e981d9bdf9d012c97919e3352a53a` before and after (`git ls-remote`) |
| Not done (by instruction) | no `main` branch, no force-push, no history rewrite, no merge, no tag, no release, no EXE/installer publication, no signing, no settings/protection/ruleset change |

The git command set required by the brief was run at the start and at the end: `status --porcelain=v2 --branch`,
`status --short`, `branch --show-current`, `branch -vv`, `rev-parse HEAD`,
`rev-parse --abbrev-ref --symbolic-full-name @{u}`, `remote -v`, `ls-remote`, `stash list`,
`worktree list --porcelain`, `diff --check`, `log --oneline --decorate -30`. Its actual output is quoted in the
final reply.

**Sandbox resets.** The sandbox was reset five times during the programme. Each time the local branch ref went back
to the sandbox's base and the venv, Qt libraries and scratch space were lost. Recovery used only
`git fetch` plus a compare-and-swap `git update-ref` to the verified remote tip; there was no `reset --hard` and no
force-push. No pushed commit was lost: every phase was pushed and confirmed with `git ls-remote` before the next one.

Phase checkpoints:

| Phase | Commit | CI on that exact SHA |
|---|---|---|
| M101 evidence reconciliation, defect register, M52 equivalent mutant killed, warning inventory | `fc2daf2238856fec27cf81164d34853847dcb27d` | Source ✅, Windows ✅ |
| M105 survey result integrity, explicit depth-datum shift, declared plan references | `74d679bc2e7a95f59d93a797ab5a38de00131646` | Source ✅, Windows ✅ |
| M102 full selection context, every tab subscribed, extended leak probes and six real leak fixes | `01f0b3e6821eba44b7d941a867afe7e406146c1e` | cancelled by the next push (not a pass) |
| M103 reusable context-bound background jobs; operational analysis off the GUI thread | `333313f58c1dc4381df26413a74a75093b372a4e` | Source **failed** (D23/D25, fixed in M104/M106), Windows ✅ |
| M104 operational analysis scope, MSE lineage, KPI register | `fe7ee662cbf8e0f0c92301352ebf083453f014e6` | Source **failed** (D25, fixed in M106), Windows ✅ |
| M106 multi-target and S-profile directional solver | `78f89d645ba34fca8ea17748cfc9aef6c1ce0632` | Source ✅, Windows ✅ |
| M107 every W13 calculator has a contract or an exact NOT_SUPPORTED reason; weight-up sack co… | `109607e61d7a6f923c4c4d1e77559f8503d62031` | Source cancelled (not a pass), Windows ✅ |
| M108 calculation history covers every source; trajectory records versioned and re-runnable; … | `4d918df7fdbf0c42c6ed1f702df0a15a8858b7c2` | Source ✅, Windows ✅ |
| M109 cement worksheet contract and re-run adapter | `485954cb79fc0876442e4e42f1cd2b256396a9f2` | Source ✅, Windows ✅ |
| M110 professional export revision, approval wording, provenance, D29 | `81754329297894a827a3b860a544c174ad064bca` | Source ✅, Windows ✅ |
| M111 isolated spawn DDR parser, DTO boundary, bounded shutdown | `b43febb45a95d308bcdefc3035cc0c291bd78d65` | Source ✅, Windows ✅ |
| M112 dependency and licence audit, catalogue evidence, owner decision packs; fix D30 | `2cf9a00df09bbcfa5fdc0ff65703d150ee92317f` | Source ✅, Windows ✅ |
| M113 unit-conversion constant inventory and versioning strategy (no value changed) | `faeb7a47c13cef0511934966b0b2a8fe928ed966` | cancelled (not a pass) |
| M114 document search follows the scope (D31) | `7c53dea7daaa9c3c337560daeead1272ba993c67` | cancelled (not a pass) |
| M115 measured start-up breakdown, RTL/LTR check on every tab, chart axis labels (D34) | `ea6d044169c8e5ebbbd2861178de693366ad234d` | cancelled (not a pass) |
| M116 survey results hash frozen (D32), explicit SQLite date adapters (D16), report delete ke… | `297851053c3e932ae20ed57599a36def5049d875` | cancelled (not a pass) |
| M117 user journeys A–Z through real widgets | `6d5c9db4bf27effc1ffa7f4c3963e0703666af9d` | cancelled (not a pass) |
| M119 second adversarial review - malformed stored records are UNREADABLE (D35), forgery limi… | `c5ea34983dd6fe99454d4ce86ecc7bd1b475a5b0` | Source **failed** on 3.12/3.13 (D36, D37), 3.11 ✅, Windows ✅ |
| M118 fix CI 3.12/3.13 legs - UX tool confirms its own close (D36), version-independent const… | `c7b6ac194fc531995da5d4722254100dc2fbfab1` | Source 3.11/3.12/3.13 ✅, Windows ✅ (**final code**) |

A run cancelled because a newer commit was pushed is **not** a pass. Only the final code and report SHAs carry the
CI result that this report relies on (§F).

## B. Phases

| Phase | Result | Main evidence (tests are in `tests/`) |
|---|---|---|
| M101 audit | PASS | Coverage reconciled: CI 3.12 62291/93969 is authoritative, and 62289 was the unlabelled local 3.11 figure (D17). The "no PyMuPDF" claim is scoped to the programme delta; PyMuPDF is a pre-existing mandatory AGPL dependency (owner gate, not removed). The m52 "equivalent" mutant was refuted and replaced by a stronger one. Warnings are inventoried in CI via `verify_release.report_warnings` (no suppression). Defect register D1–D14 |
| M102 selection context | PASS (D18) | `SelectionManager` context company → project → well → wellbore → section → report → date/period, where the model has the relation (there is no rig table; nothing invented); `context_changed` reaches all 21 tabs; leak probes beyond IDs |
| M103 async pattern | PASS (D3) | `core/context_jobs.py`: GUI snapshot → worker session → DTO → context token → stale/superseded rejection, loading/error/retry, cancel, bounded close. Tests: switch during a job, close during a job, newer job first |
| M104 operational analysis | PASS / PARTIAL (D5 resolved, D6 PARTIAL) | Additive MSE lineage (legacy unknown), scope-aware plan vs actual or NOT ASSESSED with a reason, NPT separate, KPI register (value, unit, scope, source, quality, reason) |
| M105 survey integrity | PASS (D1, D2, D15) | Full-field `verify_results` with tolerances and azimuth wrap, results hash v1 (legacy NOT RECORDED), fail-closed `verify_for_use` before tie-in, explicit datum shift as a new revision, plan reference declared; CRS out of scope (D11 PARTIAL) |
| M106 multi-segment solver | PASS (D10, D25) | Build/drop/hold/turn, S-profile, multiple targets, DLS and inclination limits, documented objective and convergence, structured infeasible codes, independent goldens; anti-collision stays SCREENING |
| M107 W13 calculators | PASS (D8, D26) | 18 contracts + 9 NOT_SUPPORTED with an exact reason = 27 (§D) |
| M108 calculation history | PASS (D14 for new records, D27) | Every source in history; `method_version` on new trajectory records, legacy NOT_REPRODUCIBLE; full-field unit-aware compare |
| M109 cement worksheet | PASS (D9; D35 found in M119) | Contract and re-run adapter (new linked `rerun_of` case), "WORKSHEET — NOT A CEMENT DESIGN APPROVAL", no yield inferred from grade |
| M110 export | PASS (D4, D29) | No hard-coded "Rev 0"; per-report provenance in batch workbooks; Mud Chemicals checked; "Approved By" is a recorded name, not an approval; HTML/PDF/Excel/CSV parity in RTL and LTR; PyMuPDF not used for generation |
| M111 isolated DDR parse | PASS (D12) | Spawn process, DTOs only, persistence in the parent, bounded shutdown, no orphans, identity checks, cancel never commits; no OCR |
| M112 dependency audit | PASS for disclosure (D13, D30) | 26 pins (22 permissive); `dependency_audit.json`; catalogue evidence per method (54 entries); 12 owner packs; no approval UI |
| M113 constant inventory | PASS (inventory) | pcf/ppg 7.48052 ×10, 7.48 ×11, 7.4805 ×1; ft³/bbl 5.6146 vs 5.615; versioning strategy; no global change (owner gate) |
| M114 document intelligence | PASS (D31) | Searches scoped to the documents of the selection, manual confirmation of links, page citations, no cross-well leak, offline, delete/reindex, honest "no text layer" |
| M115 UX | PASS (D34) | Measured start-up 1504 ms LTR / 1435 ms RTL offscreen (4 tabs ≈ 74% of `create_tabs`); lazy tabs NOT ADOPTED (measured, decision recorded); every tab checked in RTL and LTR; chart axes carry units and scope |
| M116 persistence | PASS (D16, D32, D33) | Fresh and legacy DBs, migrations, FK/cascade/SET NULL, immutability incl. ORM bulk update and raw SQL, authorization, rollback, concurrency, backup/restore, interrupted recovery |
| M117 journeys A–Z | PASS | 26/26 journeys through real widgets with synthetic data; `journey_index.py --check` |
| M118 qualification | PASS after the D36/D37 fixes: CI green on the exact SHA, coverage 67.78 %, 570 mutants (567 killed + 3 killed in m52) | §F |
| M119 adversarial review (committed before M118 so the qualification covers it) | PASS (D35 fixed) | D1–D14 re-attacked; test-assertion audit; the forgery limit of unkeyed hashes documented in `SECURITY_MODEL.md` §5 |
| M120 report | this file | §A–§H |

## C. Methods (versioned; no constant changed globally)

| Method | Version identifier | Golden / independent check |
|---|---|---|
| Survey minimum curvature and results verification | `M72 survey revision v1`; tolerances md/tvd/N/E/VS/HD 1e-6 m, inc/azi 1e-7°, DLS 1e-6 °/30 m; azimuth wraps | build-hold TD 1623.903201 m; J-profile VS 488.7133898 m |
| Survey results hash | `M105 survey results hash v1` (legacy NOT RECORDED); frozen by `SURVEY_GUARD_VERSION = 2` | tamper tests |
| Vertical depth-datum shift | `M105 vertical depth-datum shift v1` (explicit parameters, new revision) | −25 m shift |
| Azimuth reference transform | `M85 azimuth reference transform v1` (no online declination) | M85 tests |
| Multi-target / S-profile solver | `M106 multi-target / S-profile solver v1` (documented objective, no optimality claim) | S-profile 24.355° |
| W13 contracts | `M107 calculator contracts v3` (§D) | Teale MSE 127997.67 psi; bit ΔP 920.98 psi; nozzles [7, 7, 9], TFA 0.1371 in²; weight-up v2 500 bbl 80→90 pcf → 427.4 sacks |
| Cement annulus worksheet | `M89 cement annulus worksheet v1`; adapter re-run as a new linked case | M109 tests |
| Operational analysis | `M104 operational analysis v2` | M104 tests |
| Professional export | `M110 professional export template v1` | M110 parity tests |
| Report provenance | `M93 report provenance v1` | M93/M110 tests |
| Isolated parse | `ISOLATION_VERSION = 1` | M111 tests |
| Date adapters | `ADAPTER_VERSION = 1` (stored text unchanged) | M116 test |
| Anti-collision | `M52 centre-to-centre screening v1` — SCREENING, no separation factor without an uncertainty model | M52 tests |
| Unit constants | inventory only (M113); 7.48 vs 7.48052 is an owner decision | `constant_inventory.py --check` |

## D. The 27 W13 calculators (each listed)

Source: `core/calculator_contracts.py` (`CONTRACTS` 18, `NOT_SUPPORTED` 9). The leaves are enumerated from the real
W13 widget tree by `test_m107_w13_contracts.py::test_all_27_leaves_have_a_contract_or_an_exact_reason`; the contract set
and the NOT_SUPPORTED set are disjoint. A contracted calculator saves a case with semantic field IDs and units and
can be re-run from History. A NOT_SUPPORTED page still works on screen, but no reproducible case is claimed (DP Database is a reference
catalogue and computes nothing).
Inputs → results are field counts.

| # | Calculator | Status | Stable ID | Method version | Inputs → results | Limits / reason |
|---|---|---|---|---|---|---|
| 1 | Volume › Quick Calc | CONTRACT (schema v2) | `w13.volume.quick_calc` | M87 volume quick calc v2 | 6 → 6 | Nominal geometry; no tool joints, no washout. |
| 2 | Bit Hydraulics › Bit Hydraulics | CONTRACT (schema v1) | `w13.bit.hydraulics_page` | M87 bit hydraulics / MSE / cost per foot v1 | 12 → 8 | Nozzle program required for hydraulics; currency is not recorded (owner-gated money model). |
| 3 | Bit Hydraulics › TFA Calculator | CONTRACT (schema v1) | `w13.bit.tfa_from_dp` | M87 TFA from bit pressure drop v1 | 3 → 1 | — |
| 4 | Well Control › HP  FP | CONTRACT (schema v1) | `w13.well_control.hydrostatic_fp` | M87 hydrostatic and formation pressure v1 | 3 → 4 | — |
| 5 | CSG/CMT › Cement Volume | CONTRACT (schema v1) | `w13.cement.job_volumes` | M87 cement job volume worksheet v1 | 17 → 10 | WORKSHEET — NOT A CEMENT DESIGN APPROVAL: not laboratory cement design; yield and sacks are entered, never inferred from a class or grade; 0 in an optional field means omitted. |
| 6 | Mud › OWR | CONTRACT (schema v1) | `w13.mud.owr` | M87 oil-water ratio v1 | 2 → 2 | — |
| 7 | Directional › Build/Turn Rate | CONTRACT (schema v1) | `w13.directional.build_turn_dls` | M87 build/turn rate and dogleg severity v1 | 5 → 3 | — |
| 8 | CSG/CMT › Buoyancy | CONTRACT (schema v1) | `w13.casing.buoyancy_landing` | M107 buoyancy factor and casing landing load v1 | 4 → 4 | SCREENING: density ratio only, no pressure-area term. |
| 9 | CSG/CMT › Balanced Plug | CONTRACT (schema v1) | `w13.cement.balanced_plug` | M107 balanced plug volumetrics v1 | 9 → 7 | WORKSHEET - static volumetrics, not a placement simulation or a cement design approval. |
| 10 | Well Control › Kick Tolerance | CONTRACT (schema v1) | `w13.well_control.kick_tolerance` | M107 kick tolerance and trip margin v1 | 11 → 6 | SCREENING well-control aid; not an approved well-control calculation. |
| 11 | Well Control › Pore Press  FG | CONTRACT (schema v1) | `w13.well_control.pore_fg` | M107 Eaton FG / influx type / dc-exponent v1 | 13 → 6 | SCREENING; EMW uses 0.052 psi/ft per ppg; the influx category text is shown, not compared. |
| 12 | Stuck Pipe | CONTRACT (schema v1) | `w13.fishing.stuck_pipe` | M107 free point / stretch / adjusted weight v1 | 7 → 3 | SCREENING estimates; an unrecorded input is not assessed, never zero. |
| 13 | Mud › Weight/Dilution/Mix | CONTRACT (schema v1) | `w13.mud.weight_dilution_mix` | M107 weight-up v2 / dilution / mixing v1 | 12 → 7 | Ideal volume additivity; additive densities as listed in the calculator. |
| 14 | Mud › Volume Balance | CONTRACT (schema v1) | `w13.mud.volume_balance` | M107 mud volume balance v1 | 8 → 2 | — |
| 15 | Mud › Mud Lab | CONTRACT (schema v1) | `w13.mud.lab` | M107 mud lab (MBT, LSRYP, lime, slug, corrosion) v1 | 13 → 7 | The corrosion severity text is shown, not compared. |
| 16 | Fishing | CONTRACT (schema v1) | `w13.fishing.sizing` | M107 overshot fit / jar range / back-off v1 | 7 → 6 | SCREENING sizing rules. |
| 17 | Mud › Rheology | CONTRACT (schema v1) | `w13.mud.rheology` | M107 Fann rheology (Bingham / power law / HB estimate) v1 | 9 → 9 | SCREENING; θ200 and θ100 are recorded but not used by the method; not a full HB fit. |
| 18 | Bit Hydraulics › Nozzle Optimization | CONTRACT (schema v1) | `w13.bit.nozzle_optimization` | M107 two-point nozzle optimisation v1 | 10 → 15 | SCREENING; the parasitic-loss model is a single power law from two pump-test points. |
| 19 | Volume › Well Volumes | NOT_SUPPORTED | — | — | — | reads the pump, drill-string and casing tables (vol_pumps, vol_pipes, vol_casings), which are not captured; the case capture records form fields and result labels only |
| 20 | Hydraulics | NOT_SUPPORTED | — | — | — | reads the pump, drill-string, casing and nozzle tables of the page, which are not captured (the case capture records form fields and result labels only); hydraulics runs are only exported to CSV and are not stored, so they do not appear in Calc History |
| 21 | Weight | NOT_SUPPORTED | — | — | — | the drill-string components table (wt_pipes) is not captured and the torque-and-drag result reads the survey table of Directional › Multi-Survey (dd_surveys) on another page; torque-and-drag runs are saved with their snapshot and verified in Calc History |
| 22 | CSG/CMT › Casing Strength | NOT_SUPPORTED | — | — | — | inputs can be inherited from a casing architecture revision and the per-field provenance (entered / inherited / unknown) is not captured, so a case could not say where each value came from; casing runs are saved with provenance and verified in Calc History |
| 23 | Well Control › Kill Sheet | NOT_SUPPORTED | — | — | — | TRAINING AID (owner decision pending) and the drill-string geometry table (wc_pipes) is not captured; kill-sheet runs are saved in Calc History as TRAINING AID |
| 24 | Well Control › Choke Schedule | NOT_SUPPORTED | — | — | — | the output is a schedule table, which the case capture does not record, so no case can be saved from this page |
| 25 | Directional › Multi-Survey | NOT_SUPPORTED | — | — | — | the survey table (dd_surveys) is not captured (the case capture records form fields and result labels only); use Survey revisions (immutable, verified, method-versioned) |
| 26 | Directional › Anti-Collision | NOT_SUPPORTED | — | — | — | the reference and offset survey tables are not captured (the case capture records form fields and result labels only); SCREENING only, no ISCWSA uncertainty |
| 27 | DP Database | NOT_SUPPORTED | — | — | — | reference catalogue, not a calculator: nothing is computed, so there is nothing to re-run |

## E. History and provenance

History is insert-only: nothing overwrites a revision, a case or a history record (D27; immutability triggers
for revisions, M116). There are 11 sources (`calculation_history.COVERAGE`):

| Source | Table | Method version | Re-run | Compare |
|---|---|---|---|---|
| Torque & drag, Casing design, Cement volumes, MSE, Mud volume | engine snapshot tables | every record (engine method + snapshot schema) | engine snapshot re-run | full-field |
| Kill sheet | `well_control_kill_sheet_calculations` | every record | engine snapshot re-run (TRAINING AID) | full-field |
| Trajectory | `trajectory_calculations` | from M108 on; earlier rows "unversioned (legacy)", never given the current method | re-run of the stored stations; legacy NOT REPRODUCIBLE | full-field |
| Calculation case | `calculation_cases` | every case (W13_UNVERSIONED before M73) | contract re-run (18 calculators); the 9 NOT_SUPPORTED are NOT REPRODUCIBLE | full-field |
| Directional plan | `directional_plan_revisions` | every revision | plan re-design + result hash | full-field |
| Survey revision | `survey_revisions` | every revision | minimum curvature after the station and results SHA-256 checks | full-field |
| Well architecture | `well_architecture_revisions` | every revision (schema version) | validator after the SHA-256 check; cement worksheet re-run as a new `rerun_of` case (M109) | full-field |

Re-check outcomes are MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE. Since M119 (D35), any failure while
re-checking a malformed stored record is UNREADABLE with its reason; nothing is stored or changed. Compare outcomes
are SAME / DIFFERENT / CHANGED / ONLY A / ONLY B / UNIT MISMATCH; values in different units are never compared.

Provenance and lineage:
- **MSE lineage (M104):** `wellbore_id`, `report_id`, `input_source`, `lineage_version` for new runs; legacy stays
  unknown. A report delete keeps those runs and sets the report to unknown (D33, M116).
- **Reports (M93, M110):** per-report provenance (actual revision or "No report revision recorded", template
  version), also in multi-report workbooks.
- **Documents (M114):** page citations; links are confirmed manually; searches never leave the selection's
  documents.
- **Integrity:** survey station/results hashes, case input hashes and architecture component hashes are verified
  before use. They are unkeyed and tamper-evident only (`SECURITY_MODEL.md` §5).

## F. Quality

All figures are for the final code SHA `c7b6ac194fc531995da5d4722254100dc2fbfab1` unless a row says otherwise.

**Full suite (local, offscreen Qt, Linux, Python 3.11.2, SQLite 3.40.1, PySide6 6.8.1.1; NOT Windows desktop):**

| collected | passed | skipped | failed | errors | xfailed | xpassed | deselected | runtime | warnings |
|---|---|---|---|---|---|---|---|---|---|
| 4707 | 4703 | 4 | 0 | 0 | 0 | 0 | 0 | 1580 s | run with `-W ignore` locally; CI counts below |

The 4 skips are the four opt-in tests (`test_ddr_acceptance.py:33` ×2, `test_mineru_real_integration.py:26`,
`test_packaging_smoke.py:218`). They did **not** pass. No skip, xfail or exclusion was added.

Count history in this programme: 4559 (M106) → 4599 (M108) → 4622 (M110) → 4645 (M111) → 4654 (M112) → 4658
(M113) → 4668 (M114) → 4674 (M115, +6) → 4684 (M116, +10) → 4693 (M117, +9) → 4706 (M119, +13) → 4707 (M118
fix, +1). Each step is new tests only; nothing was removed.

**CI on the exact final code SHA:**

| Workflow | Run | Jobs | Result |
|---|---|---|---|
| Source release gate | 41807619126 | 3.11 `126498477822` (25 min), 3.12 + coverage `126498478559` (36 min), 3.13 `126498478015` (21 min) | **success** |
| Windows release validation | 41807618881 | — | **success** (CI, not desktop acceptance) |

A green Source job means `verify_release` saw failed = 0 and errors = 0, with the JUnit report validated against
the collected count. On success the count line is printed only to the job log, which this workspace cannot read.
The last annotated CI count is 4706 collected at `c5ea349`.

**Earlier CI failure, fixed:** at `c5ea349` the 3.12 and 3.13 legs failed (collected 4706, passed 4698, skipped 4,
failed 1, errors 3). D36 was the M115 measurement tool's ignored close, which left threads alive at exit. D37 was
the constant inventory's version-dependent f-string tokenization. Both are fixed in `c7b6ac1`, each with a killed
mutant. Intermediate runs cancelled by a newer push are listed as cancelled in §A and are not passes.

**Coverage (CI 3.12, branch + line):** 67.78 % (65304/96344, 243 tracked files). The aim of ≥ 65 % is met; the
floor stays 45.50 %. The M101 reconciliation stands: CI is authoritative, and local figures are labelled local
(D17).

**Warnings (CI, not suppressed):**

| Leg | Occurrences | Groups | Repository | Third-party |
|---|---|---|---|---|
| 3.11 | 39 | 12 | 4 | 35 |
| 3.12 | 102 | 13 | 67 | 35 |
| 3.13 | 102 | 13 | 67 | 35 |

The 3.12 figure was 859 at `c776e8c`; most of the drop is D16 (explicit SQLite date adapters, M116). The largest
remaining repository group is `core/report_snapshot.py:132` `datetime.utcnow()` (63, Python ≥ 3.12). Third-party
groups are openpyxl data-validation (16), matplotlib/pyparsing (12) and SWIG builtins (4). The 3.13-only
`re.split` positional `maxsplit` warning (9) was fixed. CI annotates only the 7 largest groups; the rest are in the
job log.

**Mutation (clean clone, exact SHA):**

| Suite | SHA | Mutants | Killed | Survived | Equivalent | Invalid |
|---|---|---|---|---|---|---|
| m46 | `c5ea349` | 29 | 29 | 0 | 0 | 0 |
| m47 | `c5ea349` | 26 | 26 | 0 | 0 | 0 |
| m48 | `c5ea349` | 44 | 44 | 0 | 0 | 0 |
| m49 | `c5ea349` | 38 | 38 | 0 | 0 | 0 |
| m50 | `c5ea349` | 55 | 52 | 3 (killed in m52) | 0 | 0 |
| m51 | `c5ea349` | 29 | 29 | 0 | 0 | 0 |
| m52 | `c5ea349` | 70 | 70 | 0 | 0 | 0 |
| m53_m56 | `c5ea349` | 38 | 38 | 0 | 0 | 0 |
| m61_m67 | `c5ea349` | 19 | 19 | 0 | 0 | 0 |
| m70_m76 | `c5ea349` | 18 | 18 | 0 | 0 | 0 |
| m83_m96 | `c5ea349` | 20 | 20 | 0 | 0 | 0 |
| m101_m120 | `c7b6ac1` | 184 | 184 | 0 | 0 | 0 |
| **Total** | | **570** | **567** | **3** | **0** | **0** |

- **m50 survivors:** the three run against M50's own test list and have been re-run in m52 (killed) since M52.
- **m101_m120 growth:** it grew from 0 to 184 in this programme, with mutants for every defect fix. The M52
  "equivalent" mutant was refuted in M101 and is now killed.
- **Why the c5ea349 results still hold:** none of the files mutated or tested by the eleven `c5ea349` suites
  changed in `c7b6ac1`, checked against every path in the result files.
- **Evidence:** `docs/mission-reports/m118-evidence/`.

**Gates at the final code SHA:**
- lint 727 (ceiling 727, not raised);
- `ruff --select E722,F821` clean, and ruff clean on new and modified files (the 13 findings in `core/database.py`
  are pre-existing);
- privacy 1348 files / 0 findings;
- dependency audit 26 pins / 0 FAIL;
- engine inventory, constant inventory v2 and journey index current;
- schema compatibility 26/26;
- mutation anchors 570 / 0 bad.

Goldens pass in the full suite (§C).

**Defects found and fixed in this programme:** D1–D5, D8–D10, D12, D14 (new records), D15, D16, D18, D23–D27,
D29–D37. D19–D22 were never assigned (numbering gap, M119). Open: D28 (timing under load; not observed in 5 full
suites and the m49 mutation baseline in M118, but neither reproduced nor fixed). Partial: D6, D7, D11. Owner-gated
decisions: D13.

## G. Owner register (open decisions; none taken by automation)

| Gate | State | Pack |
|---|---|---|
| Windows desktop acceptance | OWNER REVIEW REQUIRED (Windows CI is not desktop acceptance) | — |
| Field acceptance | OWNER REVIEW REQUIRED | — |
| ISCWSA error models / welleng | OWNER REVIEW REQUIRED; no separation factor without an uncertainty model | M112 pack |
| pwptemp, torque_drag (LGPL-3.0) | OWNER REVIEW REQUIRED; not installed | M112 pack |
| PyMuPDF (AGPL-3.0, pre-existing mandatory) | OWNER REVIEW REQUIRED; not removed or replaced | M112 pack |
| OCR / RapidOCR / onnxruntime | OWNER REVIEW REQUIRED; not installed | M112 pack |
| AI/ML models, weights, GPU | OWNER REVIEW REQUIRED; none bundled | M112 pack |
| MinerU (custom licence), qtribbon (unknown licence) | OWNER REVIEW REQUIRED | M112 audit |
| Kill sheet leaving TRAINING AID | OWNER REVIEW REQUIRED | M112 pack |
| 7.48 vs 7.48052 gal/ft³ | OWNER REVIEW REQUIRED; inventoried, not changed | M113 |
| Money / currency | OWNER REVIEW REQUIRED; no money migration | M112 pack |
| Hydraulics and method approvals | OWNER REVIEW REQUIRED; no approval UI | M112 pack |
| Datum / CRS scope | OWNER REVIEW REQUIRED; CRS not implemented | M112 pack |
| Integrity reference kept elsewhere / DB encryption | OWNER REVIEW REQUIRED (`SECURITY_MODEL.md` §5, §7) | — |
| Release, signing, tags, protection, history purge | OWNER REVIEW REQUIRED; nothing done | — |

## H. Status by category

| Category | Items |
|---|---|
| Implemented and qualified within the documented scope | M101–M119 capabilities marked PASS in the matrix; D1–D5, D8–D10, D12, D14 (new records), D15, D16, D18, D23–D27, D29–D35 resolved |
| PARTIAL (scope stated) | D6 MSE lineage (legacy runs unknown, MD not recorded); D7 (tab-local tokens remain in four views, all rejecting stale results); D11 datum/CRS (vertical shift only) |
| Open defects | D28 (m49 cancel test timing under load; see §F) |
| Recorded process items | D17 (local vs CI coverage figures; CI is authoritative) |
| SCREENING / WORKSHEET / TRAINING AID labels | anti-collision, torque & drag, casing design, MSE, buoyancy, kick tolerance, pore/FG, stuck pipe, fishing, rheology, nozzle optimisation (SCREENING); cement, mud volume, balanced plug (WORKSHEET); kill sheet (TRAINING AID) |
| NOT IMPLEMENTED (by scope) | CRS transformation, GIS, online declination, OCR, AI/ML models, separation factor, lazy tabs (measured, not adopted) |
| OWNER REVIEW REQUIRED | §G |
| Not done by instruction | release, tag, signing, installer/EXE publication, deployment, history purge, money migration, `main` branch, protection changes |

Product state: *Integrated drilling engineering product candidate — implemented and qualified within the documented
technical scope; Windows desktop acceptance, field acceptance, legal approvals and release authorization remain
open.* **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**
