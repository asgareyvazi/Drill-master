# M398 — owner-decision report

**Nothing in M361–M400 approves an owner decision.** The per-package state table is the "M400 status" section of
`docs/engineering/M196_OWNER_DECISION_PACKAGES.md`; this report lists what the owner is asked to decide next, in
priority order, and what each decision would unblock. `core/method_catalogue.OWNER_APPROVALS` is empty on the final
tree (tested by `test_m112_dependency_audit`: 62 entries, 0 approved).

| Priority | Package | Decision asked | Unblocks | Evidence |
|---|---|---|---|---|
| 1 | P2 PySide6 | raise the pin to 6.8.3 (or 6.8.2.1); all four packages together | D63 / D74 window release on the shipped pin (catalogue domain 2); M376 closed-window part | `m378_pyside_decision_record.md` |
| 2 | CI design (D88) | split or shard the 3.12 coverage leg, or record another decision; the 60 min limit was not raised | a margin on the final-SHA gate (`3ca8b80` timed out at 60 min) | `m361_live_baseline.md` §3c; M377 |
| 3 | P11 kill sheet | whether any well-control worksheet may leave TRAINING AID | catalogue domains 30–32 (M373 added) | M196 P11 |
| 4 | P19 ISCWSA | error-model source, table licence, benchmark wells | separation factor (domain 13) | M196 P19 |
| 5 | P12 / P18 | casing method set and a tubular rating source | triaxial envelope, connection ratings (domains 20, 21, 46) | M196 P12, P18 |
| 6 | P10 datum / CRS | whether conversions may be implemented and against which reference | M368 converts instead of refusing | M196 P10 |
| 7 | P3 LGPL | pwptemp / torque_drag | temperature model, stiff-string reference | M196 P3 |
| 8 | M386 pillow raise (made) | confirm or reverse pillow 12.3.0 → 13.0.0 | – (security fix already applied; same MIT-CMU licence; not a Qt package) | `m386_vuln_audit_before.json` (58 advisories), `m386_vuln_audit_after.json` (0) |
| – | P1, P4–P9, P13–P17 | unchanged since M196 | – | M196 |
