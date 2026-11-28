# M556–M560 — drill-off: M475 audit, L1 diagnostics, downhole data dossier, benchmark extension

Status: SCREENING. M372, M423 v1 and M475 v1 (method IDs, versions, stored cases, replay) are unchanged. E12
(`BL-BIT-DEFAULTS`) is not touched: no bit-performance default or behaviour was changed.

## M556 — audit of `core/drilloff_robust.py` (M475 v1)

| Item | Finding |
|---|---|
| L1 exactness | for a fixed W* every triple of steps is solved (vertex property of the L1 LP); correct for p = 3 |
| breakpoint search | grid over [W_(2), W_(n-1)] + golden section; the better of the two is kept |
| ties | the first optimal triple in index order is returned; **non-uniqueness was not reported** → M557 diagnostics |
| identifiability | a flat sum-\|r\| curve (e.g. a straight line) still returns one breakpoint → M557 flat interval |
| leverage | LAD is not robust to WOB errors (stated in M475) but no per-step indicator existed → M557 hat values |
| outlier scale | MAD over off-vertex residuals, 3 s rule; s = 0 flags every non-zero residual (stated) |
| WOB basis | declared, frozen, hashed; surface never converted (correct) |
| bounds | 6–30 steps; RPM tolerance; duplicate WOB refused |

No defect requiring a new M475 version was found. The gaps are reporting gaps and were closed additively.

## M557 — `core/drilloff_diagnostics.py` (`M556 drill-off L1 diagnostics v1`)

Recomputed from a COMPUTED M475 result whenever it is shown. The diagnostics are not stored in the case and not
replay-compared, so history is not affected. They include tied optima at the fitted breakpoint (UNIQUE / NOT
UNIQUE), the flat interval (grid points within 1 % of the optimum sum |r|), leave-one-out breakpoints and decision
flips, and hat values with the 2p/n threshold. M475 `summary_lines` appends them, so the W13 robust drill-off
dialog shows them.

Warnings (wording only): surface WOB basis, breakpoint within one tested step of the search edge, fewer than three
steps beyond the breakpoint, flagged residuals, non-unique optimum, high-leverage steps, leave-one-out shift of more
than one tested WOB step, and leave-one-out decision flip.

## M558 — downhole data dossier

| Need | Status |
|---|---|
| a downhole-WOB drill-off data set with redistribution rights | **NOT AVAILABLE**: none found with a licence permitting inclusion; the user's 08-DDR files are confidential and were not opened |
| downhole WOB derivation (hook load, friction, drag) | **NOT IMPLEMENTED** by design (E6b); the method never derives downhole WOB from surface WOB |
| field validation of the founder estimate | **NONE**; the method stays SCREENING |
| what would unblock | a public or owner-licensed data set with downhole WOB (e.g. a near-bit sub), RPM and ROP per step, plus the test procedure; an owner decision on rights |

## M559 — benchmark extension

`tools/quality/benchmark_m559_drilloff_diagnostics.py`: the nine M478 cases are re-run with diagnostics
expectations, plus 4 construction cases (edge, two steps above, clean downhole, surface) and a hand-derived L1 tie.
The tie uses the hinge-design null vector (−1, 3, −3, 1) at x = 0..3 with breakpoint 1.5. Result: **14/14 PASS**.
Leverage is cross-checked against an independent QR projection.

Two expectations were corrected during construction; the engine was unchanged:

- D1 holds only two steps below the knee, so the "leave-one-out shift 0" argument does not apply.
- D2's knee is 3 klbf from the upper search edge, so the edge warning applies by construction.

## M560 — evidence

`tests/test_m556_drilloff_diagnostics.py` (11 tests, including the W13 dialog and the M475 payload/replay
unchanged) and mutants DD-* (8/8 killed after a test for the tie warning was added; DD-tie-hidden first SURVIVED).
