# M521–M600 canonical backlog

Start SHA `1ab35e1`. Product label: PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. M504–M520 stay
RESERVED (never completed). No owner decision P1–P19 is approved; `OWNER_APPROVALS` stays empty.

Columns: ID · origin · mission(s) · source · scope · dependencies · data · licence · owner gate · safety · status ·
acceptance · evidence. Status values: DONE (stated synthetic scope), PARTIAL, BLOCKED, OPEN, PACKAGE-ONLY.
The status column is updated at the end of the mission (M581–M600); see the integrated report for the final state.

| ID | Origin | Missions | Source | Scope | Depends | Data | Licence | Owner gate | Safety | Status | Acceptance | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B-01 Live baseline | M521 | M521 | git / gh | SHA, cleanliness, CI on start SHA | — | — | — | — | no destructive git | DONE | temp-index diff empty; CI green | m521-m600-evidence/m521_live_baseline.md |
| B-02 Forensic audit | M461–M520 report | M522–M524 | code at 1ab35e1 | claims vs code, crosswalk, CI addendum | B-01 | — | — | — | — | DONE | every claim checked | m522_m524_forensic_audit_crosswalk_ci.md |
| S-01 Erge record | M482 | M526–M527, M541–M545 | JPSE 128:128–139; SPE 167950-PA; BoreTHM (Apache-2.0, secondary) | citation correction; coefficients unchanged | — | — | Apache-2.0 (secondary) | — | no unverified formula promoted | DONE (record) / NOT VERIFIED (coefficients) | note names both papers; numbers unchanged | sources/M526_M527_ERGE_RECORD_CORRECTION.md; test_m541 |
| S-02 Open-ended surge sources | M479 | M528, M531–M535 | He 2016 (abstract), Mohammad & Belayneh 2023 (OA), METU 2016 (closed-end) | open-end equations | — | none shipped | MDPI OA (CC BY unconfirmed) | — | M420 not relabelled | BLOCKED | full open-end equations from a lawful source | sources/M528_OPEN_ENDED_SURGE_SOURCE_AUDIT.md |
| S-03 Eccentric HB / rotation sources | M480/M481 | M529 | Krishna 2025 (OA), Kelessidis 2011 (abstract), Torsvik 2026 (not found) | eccentric, rotation | — | none shipped | Springer OA | — | no concentric→eccentric extension | BLOCKED (eccentric, rotation) | verifiable closed form + independent data | sources/M529_ECCENTRIC_HB_AND_ROTATION_SOURCE_AUDIT.md |
| H-01 Exact HB concentric annulus | M480 (κ < 0.3) | M536–M540 | clean-room derivation; Fredrickson & Bird 1958, Hanks 1979 (method references) | laminar, concentric, 0.01 ≤ κ ≤ 0.99 | — | synthetic | own code | — | laminar only; Re_G ≥ Re1 refused | DONE (stated synthetic scope) | independent references; replay MATCH; mutants killed; MainWindow journey | M536_M540 spec; test_m538, test_m540; benchmark_m538 14/14; mutation_m521_m600 |
| C-01 Citation record v2 (U4) | U4 | M546–M550 | own schema | content SHA-256, page hash, passage id/offsets, verification state; v1 readable | U2 | synthetic | own | — | no fabricated hashes; traversal/symlink refused | see report | v1 still readable; v2 verified only from real bytes | schema v2, tests |
| E-01 EOWR consistency analyzer (U5) | U5 | M551–M555 | own rules | non-destructive checks, 5 statuses, lineage | M464–M468 | synthetic | own | — | no fabricated EOWR data; nothing modified | see report | every rule unit-tested; journey | analyzer, tests |
| D-01 Drill-off diagnostics | M475 | M556–M560 | Bloomfield & Steiger 1983 (LAD) | uniqueness / sensitivity / leverage diagnostics, more benchmarks | M475 | synthetic | own | E12 | never substitute surface WOB for downhole | see report | diagnostics reported, E12 unchanged | tests, benchmark |
| R-01 M129 | M129 | M561–M563 | CI history | instrumentation, reproduction, closure proposal | — | — | — | — | stays OPEN unless criterion met | see report | — | evidence |
| R-02 D88 timing | D88 | M564–M565 | CI durations | audit; safe optimisation only | — | — | — | D88 constraints | 60-min timeout, workflow unchanged, no coverage loss | see report | same tests/assertions/coverage | evidence |
| W-01 WITSML read-only pilot | roadmap | M566–M570 | Energistics WITSML (standard, licence to be checked) | read-only adapter design + synthetic mock | — | synthetic | to check | P-series (data import) | no real-time claim; no secrets; wrong-well refusal | see report | mock-server tests | design doc, tests |
| I-01 Integrity | M488 | M571–M575 | code | catalogue / replay / well isolation / security re-checks | H-01 | synthetic | — | — | — | see report | tests | tests |
| G-01 Governance | M483–M485 | M576–M580 | owner packages | E1c, E11, E12 packages; P1–P19 matrix | — | — | — | all P1–P19 | no approval granted | PACKAGE-ONLY | OWNER_APPROVALS empty | M196 update |
| F-01 Final verification | — | M581–M600 | — | regression, mutation, benchmarks, inventories, CI, catalogue, roadmap, report | all | — | — | — | — | see report | exact-SHA CI | integrated report |
