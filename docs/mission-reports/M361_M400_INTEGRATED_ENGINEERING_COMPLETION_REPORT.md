# M361–M400 — Integrated engineering completion report

**PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**
Branch `arena/72010272-drill-master`; `drill-Master` untouched (`e3fa42a3257e981d9bdf9d012c97919e3352a53a`).
Mission baseline `3ca8b80e14e93299ded78feb0750a51a21abe99a`. Evidence: `docs/mission-reports/m361-m400-evidence/`.
Everything below is synthetic (offscreen Qt on Linux, GitHub-hosted runners). Mutation results show the listed
tests detect the listed defects; they are not proof of correctness.

## 1. SHAs, CI, mutation, local suite

| Item | Value |
|---|---|
| Last tested SHA before the report | `ed683806e782d713568cf236f695107e61845ebc` (code `41ea53e` + mutation / acceptance evidence) |
| CI on `ed68380` | **SUCCESS.** Source `45345379551`: 3.11 SUCCESS (45m23s), 3.12 SUCCESS (58m35s — 1m25s under the 60 min limit, D88), 3.13 SUCCESS (47m27s); Windows `45345379462` SUCCESS (26m09s). Classified with `tools/quality/ci_run_states.py --github`; `head_sha` of both runs = `ed683806e782d713568cf236f695107e61845ebc` |
| CI on `8ceaeb7` (intermediate) | Source `45337895534` **FAILURE** on 3.11 / 3.12 / 3.13: one test, `test_m113_constant_inventory::test_the_committed_inventory_is_current` — the constant inventory was stale after the new M371 module (a gate listed as not yet run; fixed in `5d1f54a`). Windows `45337896230` SUCCESS. Not counted as green |
| CI on `c2f6eaf` | Source `45163844874` SUCCESS (3.12 took 55m55s); Windows `45163844864` SUCCESS |
| CI on `3ca8b80` (M321–M360 docs SHA) | Source `45153601358` **TIMEOUT** (3.12 hit the 60 min limit, D88); 3.11 / 3.13 SUCCESS; Windows `45153601362` SUCCESS — kept separate from the `246e7bf` product CI (Source and Windows SUCCESS) |
| Report SHA (this file) | its CI is given in the hand-over: a file cannot name the commit that contains it, and a docs-only SHA is not counted as passed because its parent passed |
| Mutation, final catalogue (M389) | **run 3 on `41ea53e`: 53 mutants, 53 KILLED, 0 SURVIVED, 0 EQUIVALENT, 0 INVALID, complete** (`m389_run3_41ea53e.txt` / `.json`) |
| Mutation history | run 1 on `35b44f1`: 23 mutants, 19 killed, 4 survived → killing tests in `c2f6eaf`; run 2 on `8181095`: 37/37 killed; M321–M360 regression on `35b44f1`: 121 mutants, 119 killed, 2 equivalent |
| Local full suite | `ed68380`: **8 / 8 shards exit 0, `EXIT=0`** (`tools/quality/run_suite_sharded.py --shards 8`, `/home/user/.venv/bin/python`; 2917 s total; `suite_final_sharded.txt`). The runner records each shard's exit code; it printed no pytest summary line, so per-test counts are taken from CI (6079 collected per leg on `8ceaeb7`). Earlier run on `8ceaeb7`: shards 3 and 7 exit 1 — `test_m112` (audit was stale while the tree changed), `test_m129` W13 anti-collision (passed when rerun alone; load / order sensitive), and `test_release_boundary_imports::test_wheel_from_tracked_population_starts` (run through the `Drill-master/.venv` symlink, which puts the repository path on `sys.path`; passed through `/home/user/.venv/bin/python`). All three passed on `ed68380` |
| Benchmarks (M396) | 31 independent cases, 0 outside tolerance (`m396_benchmarks.txt`) |
| Privacy check | 0 findings on the final tree |
| Inventories | `engine_inventory`, `dependency_audit` (62 catalogue entries, 0 approved), `constant_inventory`: all `--check` current |

## 2. What was built (product code, UI → service → engine → validation → persistence → provenance → history)

| Mission | Delivered | UI entry | Label |
|---|---|---|---|
| M365 | D87 clone identity: `D87fp1` content fingerprint on archive marks and clone links; VERIFIED / SOURCE_REPLACED / TIMESTAMP_ONLY | Calculation History | – |
| M366 | hydraulics pressure budget, pump limits, flow / nozzle sensitivities, plan vs actual, replay | W13 hydraulics › "Budget & sensitivity…" | SCREENING |
| M367 / M369 | D93 vertical-aware buckling v2 with replay pinning; geometric closest approach (D94) | W13 T&D, anti-collision | SCREENING |
| M368 | survey vs plan centreline deviation, targets HIT / MISS / NOT REACHED, refusals on frame / reference mismatch | 3D view › layers › "Plan vs actual…" | SCREENING |
| M370 | Robinson–Morgan CCI, ≤ 35° | M366 workflow | SCREENING |
| M371 | casing axial-load components (bending, temperature, ballooning), fibre stress, worn-wall burst / collapse | W13 casing › "📐 Axial loads & wear…" | SCREENING |
| M372 | drill-off test: founder point, per-step MSE, drilling efficiency CCS / MSE | W13 bit page › "📈 Drill-off test (founder)…" | SCREENING |
| M373 | volumetric method bleed schedule (stops at a declared casing limit) and gas-migration rate | W13 well control › "🫧 Volumetric method (TRAINING AID)…" | TRAINING AID (P11) |
| M374 | seven-field structured W12 KPI specs in the card tooltips | W12 Analysis | – |
| M375 | 35-step journey through the real MainWindow | – | test |
| M376 | Qt lifecycle tests for the new dialogs | – | test |
| M377 | CI run-state classifier (SUCCESS / SUPERSEDED / TIMEOUT / FAILURE / IN_PROGRESS) | developer tooling | – |
| M386 | lock vulnerability audit; **pillow 12.3.0 → 13.0.0** (58 published advisories → 0) | developer tooling | – |
| M387 | shared well context across the W13 workflows | – | test |
| M388 | replay tolerance for every reported unit (`in`, `ft/h`, `psi/bbl` added) | – | – |
| M392 | Help → Method catalogue +8 calculation-case services (62 entries, 0 approved); engine-inventory services section | Help → Method catalogue | – |

Every new service: declared inputs only (missing → NOT ASSESSED, zero is a value), inputs SHA-256 in the case,
replay adapter in `core/history_replay.py` (MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE), W13 UI test that
opens the dialog from the real tab, runs, saves and replays, hand-computed goldens, mutants in the catalogue.

## 3. Documents

* `docs/engineering/DRILLMASTER_COMPLETE_ENGINEERING_CAPABILITY_CATALOGUE_M400.md` — 48 domains, per-domain fields,
  strict labels, "PLANNED ENGINEERING CAPABILITIES — NOT YET IMPLEMENTED" (M393).
* `docs/engineering/DRILLMASTER_ENGINEERING_ROADMAP_M400.md` (M394; R-HYD-2 BoreTHM clean-room port is E1).
* M400 sections in `M241_CAPABILITY_INVENTORY.md`, `PRODUCT_CAPABILITY_MATRIX.md`, `ENGINE_INVENTORY.md`
  (generated), `ENGINEERING_METHODS_AND_LIMITATIONS.md`, `OPEN_SOURCE_ADOPTION_REGISTER.md`,
  `M196_OWNER_DECISION_PACKAGES.md` (M392).
* Evidence: `m361_live_baseline.md`, `m363_m321_m360_residual_audit.md`, `m378_pyside_decision_record.md`,
  `m379_oss_reaudit.md` (+ addendum: cement-calc is the M52 balanced plug, not M109), `oss_reaudit_m379.json`,
  `m386_vuln_audit_{before,after}.json`, `m389_run{1,2,3}_*.txt`, `m390_acceptance_matrix.md`, `m396_benchmarks.txt`,
  `m398_owner_decision_report.md`, `suite_final_sharded.txt`.

## 4. Owner-gated (BLOCKED BY OWNER DECISION — nothing approved)

P2 PySide pin (M378 recommends 6.8.3; pin stays 6.8.1.1) · D88 CI design (60 min limit not raised) · P11 kill
sheet (M373 stays TRAINING AID) · P19 ISCWSA · P12 / P18 casing methods and tubular data · P10 datum / CRS · P3
LGPL. Details: `m398_owner_decision_report.md`.

## 5. Disclosures and limitations

* M368: centreline only; a datum or azimuth-reference mismatch is refused, never converted.
* M370: CCI appears in the M366 summary lines only, not as its own case field.
* M371: pipe body only; no triaxial envelope, connection rating or casing buckling; E, α, ν declared; wear keeps the
  engine's 0.875 wall tolerance (conservative).
* M372: the founder rule is a stated slope-fraction rule, not a fitted line; constant-RPM tests only; no CCS
  correlation; surface WOB / torque.
* M373: single bubble, constant annular capacity, no gas law; lubricate-and-bleed NOT IMPLEMENTED; its gradient is
  pcf/144 (exact), so it does not touch P8; the kill sheet itself still uses its own conversion.
* M375: a hidden tab applies a well change only when shown, by design; the journey opens the tab first.
* M376: closed MainWindows are still retained on the shipped PySide 6.8.1.1 (D74 / D63) — owner-gated.
* M380–M384: no new external method was adopted; the BoreTHM Herschel-Bulkley / Colebrook port is roadmap only.
* M386: the pillow raise is the only dependency change; it is listed in M196 so the owner can reverse it.
* Local full suite: one pytest process exceeds the 4 GB sandbox (OOM at 76 %); the local run uses
  `tools/quality/run_suite_sharded.py` (sequential shards). CI keeps the single-process run.
* `test_m129` (W13 anti-collision) is load / order sensitive: it failed once inside a loaded shard and passed alone and on the final run.
* `test_release_boundary_imports` must be run through the real interpreter path (`/home/user/.venv/bin/python`); through the in-repo `.venv` symlink it fails by design (the probe forbids repository paths on `sys.path`).
* D88: the 3.12 CI leg runs 55–59 min against a 60 min limit; a TIMEOUT there is reported as TIMEOUT, never green.

## 6. M399 delivery audit

| Check | Result |
|---|---|
| Only branch written: `arena/72010272-drill-master`; fast-forward pushes; remote SHA verified with `git ls-remote` after each push | PASS |
| `drill-Master` unchanged (`e3fa42a`) | PASS |
| No `reset --hard`, `clean -fd`, force-push, history rewrite, branch deletion | PASS |
| Workspace clean at the end; no stranded work | PASS (checked with `git status`) |
| PySide6 pins unchanged | PASS |
| No owner decision marked approved | PASS |
| P8 untouched; kill sheet TRAINING AID; ISCWSA / SF not claimed | PASS |
| No LGPL code, no copied unlicensed code, no datasets, no proprietary ratings | PASS |
| Historical reports intact; corrections as addenda | PASS |
| No COMPLETE label; synthetic ≠ field acceptance | PASS |
| Real DDR, Windows desktop and field acceptance | NOT RUN |
