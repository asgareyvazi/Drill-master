# M522–M524 — forensic audit of M461–M520, crosswalk and CI classification addendum

## M522 — claims of the M461–M520 report checked against the code at `1ab35e1`

| Claim (M461–M520 report) | Check | Result |
|---|---|---|
| 67 catalogue entries, 0 approved | `method_catalogue.catalogue()`; `tests/test_m112_dependency_audit.py` asserts 67 | CONFIRMED at `1ab35e1` (68 after M538, this mission) |
| `OWNER_APPROVALS` empty | `core/method_catalogue.py` | CONFIRMED |
| 5 SHA-checked declared-input services (`SERVICE_MODULES`) | `core/history_replay.py` | CONFIRMED (m416, m420, m423, m427, m475) |
| M416 κ ≥ 0.3, 0.1 ≤ n ≤ 1, criteria founargiotakis-2008 / erge-2015 | `core/hydraulics_hb_slot.py` (`KAPPA_MIN`, `N_RANGE`, `CRITERIA`) | CONFIRMED |
| Erge 2015 marked NOT VERIFIED | `UNVERIFIED_CRITERIA["erge-2015"]` | CONFIRMED; but its citation named only SPE 167950-PA. Corrected in M541 (both candidate papers named, attribution unresolved) |
| M420 closed-end only, open end NOT ASSESSED | `core/surge_swab.py` `PIPE_ENDS`, catalogue limits | CONFIRMED |
| M475 robust L1 drill-off, declared WOB basis never converted | `core/drilloff_robust.py` | CONFIRMED |
| Mutation M461–M520 55/55 | `tools/quality/mutation_m461_m520.py` defines 55 mutants | count CONFIRMED (re-run in M581–M600) |
| M479, M480–M481 BLOCKED | report | CONFIRMED as stated; M480/M481 partly unblocked in this mission (M538, concentric exact only) |
| M504–M520 reserved, not completed | report | CONFIRMED; still reserved |
| M129 OPEN, D88 active risk | report, CI history | CONFIRMED |

No M461–M520 claim was found to be false. One citation record (Erge) was incomplete.

## M523 — mission / commit / test crosswalk (M461–M520)

| Missions | Commit | Main tests |
|---|---|---|
| M461–M468 | `3b4c297` | test_m464, test_m467 (EOWR sections, MainWindow journey), benchmark_m468 |
| M469–M472 (U2) | `842c35c` | test_m469, test_m472 (citation passage, MainWindow journey) |
| M473–M474 (U3) | `20c05d0` | test_m473; mutation families M275/M276/M278/M279/M282/M283 39/39 |
| M475–M485 | `f7075a0` | test_m475_drilloff_robust, test_m482_erge_secondary_consistency; owner packages E1c/E11/E12 |
| M488–M492 | `44d3fb4` | test_m488_integration_consistency |
| M486–M503 | `46c471c` | full suite 6225/6229 (4 skipped), mutation 55/55 |
| M494 R4b, M482 follow-up | `750e3cd` | mutation_m261_m290 89 anchors |
| M494/M502 final | `1ab35e1` | CI green attempt 1 |
| M495–M503 | grouped in `46c471c`, `750e3cd`, `1ab35e1` | evidence in `docs/mission-reports/m461-m520-evidence/` |
| M504–M520 | — | RESERVED, never marked completed |

## M524 — CI classification addendum

* Final M461–M520 SHA `1ab35e1`: Source run 46125064146 GREEN at attempt 1 on 3.11 / 3.12-coverage / 3.13;
  Windows 46125064174 GREEN.
* Historical D88 risk stays ACTIVE: timeouts at 60 min occurred on `e9244e8` (3.12 attempt 1, 60m16s),
  `f7075a0` (3.13, 60m15s) and `46c471c` (3.13 attempt 1, 60m14s; attempt 2 42m48s). The 3.12 coverage job runs
  52–58 min, i.e. 3.5–14 % headroom. A green final run does not close D88; TIMEOUT ≠ SUCCESS and failed attempts
  remain on record.
