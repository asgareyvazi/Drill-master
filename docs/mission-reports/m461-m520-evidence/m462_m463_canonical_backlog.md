# M462–M463 — Canonical M461–M520 backlog

This file is the single backlog for the M461–M520 delivery. It continues the M460 roadmap
(`docs/engineering/DRILLMASTER_ENGINEERING_ROADMAP_M460.md`).

The missing historical directives (M405 and others) were not requested and were not reconstructed. M430–M459 stay **NOT
DELIVERED**, as the M401–M460 report states. Mission numbers here are forward-only.

Every row's final status is given in the integrated report:
`docs/mission-reports/M461_M520_INTEGRATED_ENGINEERING_DELIVERY_REPORT.md`.

| Phase | Missions | Item | Source in the M460 roadmap | Owner gate |
|---|---|---|---|---|
| — | M461 | Live baseline, sandbox reconciliation, environment rebuild | — | none |
| A | M462–M463 | This backlog. U1/U2/U3 are recorded as the authorized open items | U1, U2, U3 | none |
| B | M464 | EOWR audit: six sections collected but NOT_RENDERED (bit, BHA, 24 h logs, morning logs, requests, equipment) | U1 | none |
| B | M465 | Render the six sections from stored rows. Covers period scope, chronology, units as stored, sources, and the NOT_RECORDED / QUERY_FAILED / NOT_RENDERED states | U1 | none |
| B | M466 | Same rows in HTML, PDF, Excel and CSV. Manifest v3; provenance states the requested period | U1 | none |
| B | M467 | Real MainWindow journey: W11 End-of-Well tab, whole well and period, well isolation | U1 | none |
| B | M468 | Mutation (`tools/quality/mutation_m461_m520.py`) and scale benchmark (`benchmark_m468_eowr.py`) | U1 | none |
| C | M469–M472 | Citation passage navigation. Covers the schema, a secure passage service, Documents-tab UI, and E2E plus security tests | U2 | none |
| D | M473–M474 | Recover the historical mutations M275, M276, M278, M279, M282 and M283 | U3 | none |
| E | M475–M478 | Robust drill-off v2 under a new method ID. Preserves M423 v1 and replay | E6b | none (no field validation claim) |
| E | M479 | Open-ended surge, only if a primary-source validation is available; otherwise a recorded blocker | E8b | data |
| E | M480–M481 | E1b HB extensions, only if validated | E1b | data |
| E | M482 | Erge 2015 coefficients checked against the primary source; otherwise marked NOT VERIFIED or disabled | Erge gap | source access |
| E | M483–M485 | Owner packages only, no behaviour change: E1c (fitting stays DISABLED), E11, E12 | E1c, E11, E12 | owner |
| F | M486 | M129 status re-check | M129 | — |
| F | M487 | D88 suite profiling. No workflow change; the 60-min timeout is kept | D88 | owner (P-D88) |
| F | M488–M493 | Consistency, well context, replay, security, E2E, Windows gate (static only) | — | Windows acceptance is owner/field |
| G | M494–M503 | Sharded suite, mutation, benchmarks, audits, M520 catalogue and roadmap, integrated report, exact-SHA CI, git audit | — | none |
| G | M504–M520 | Reserved. No work is claimed under these numbers | — | — |

Owner decisions that are not approved and stay in force: P1–P19, D88, P2, P3, P8, P10, P11, P12/P18, P13/P16/P17, P19, D63/D74.
