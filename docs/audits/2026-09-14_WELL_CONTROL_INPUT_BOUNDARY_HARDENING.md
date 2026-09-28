# Well Control Input-Boundary Hardening + Reproducibility Readiness

**Date:** 2026-09-14
**Branch:** `arena/01a085e0-drill-master`
**Baseline commit:** `d0c00f3` (Cement = 3rd persistent calculation)
**Scope:** Mission 7 — make the Well Control **kill sheet** boundary honest,
canonical, deterministic and snapshot-ready **without changing any formula**,
then decide persistence.

**Outcome: B — readiness achieved, persistence deliberately deferred.**
This is an explicit, mission-sanctioned outcome (not a failure). The primary goal
(an honest, canonical, deterministic, snapshot-ready boundary) is DONE. A DB table
was **not** added, because doing so purely "to show progress" is forbidden and the
kill-sheet result is semantically divergent from the three already-persisted
single-engine calculations.

---

## A. Repository identity (mission §3)

The stale-ref trap recurred as expected: the local checkout started at the
branch-point `b05ea76` with Mission-6 work appearing "uncommitted". Recovery
followed the proven procedure — `git fetch origin arena/01a085e0-drill-master`
by name → `FETCH_HEAD = d0c00f3`; verified `b05ea76` is an ancestor of `d0c00f3`,
there are **no unique local commits**, every tracked file is byte-identical to
`d0c00f3`, and the only untracked file is the pre-existing
`.github/workflows/ci.yml` (left untouched). Then `git reset FETCH_HEAD` (mixed).
No work was lost. HEAD is `d0c00f3`, working tree clean.

## B. The three completed calculations remain intact (mission §4)

T&D, Casing and Cement persistence + verification test suites all pass
unchanged. No engine was touched by this mission; no refactor was applied to
those calcs for "visual consistency".

## C. Well Control architecture, reconstructed repo-wide (mission §5)

* **Engine** `core/engineering/engines/well_control.py` — `WellControlEngine`,
  `METHOD = "IWCF / IADC well-control manuals; Bourgoyne et al."`, constant
  `PSI_PER_PPG_FT = 0.052`. All classmethods, canonical-unit, no silent
  engineering defaults, returning `EngineeringResult`:
  `kill_mw(original_mw_ppg, sidpp_psi, tvd_ft)`,
  `maasp(max_allowable_mw_ppg, current_mw_ppg, shoe_tvd_ft, leak_off_psi)`,
  `kick_tolerance(...)`, `kick_volume(...)`, `eaton_fracture_gradient`,
  `influx_type`.
* **Handlers** — 12 `_wc_*` methods in `tabs/w13_Engineering_Calculator.py`.
  Most sub-tabs (`_wc_calc_kt`, `_wc_calc_trip_margin`, `_wc_calc_eaton`,
  `_wc_calc_influx_type`, `_wc_calc_hp`) call the engine **directly with
  canonical units** and are already clean single-engine boundaries.
* **The kill sheet** (`_wc_calc_kill`) was the ONLY dishonest boundary and is the
  subject of this mission.

## D. Input-boundary forensics — the kill sheet (mission §6/§7/§8)

`_wc_calc_kill` was doing FOUR things that a snapshot-ready boundary must not
bury inside a Qt widget method:

| Category | What the handler did (pre-mission) | Engine home? |
|---|---|---|
| **Unit conversion** | `m → ft (×3.28084)`, `pcf → ppg (÷7.48)`, `frac psi/ft → max-allowable MW (÷0.052)`, pipe length `m → ft` | none — inline |
| **Volume aggregation** | iterate mutable `self.wc_pipes`, string cap `id²/1029.4 × L`, annular cap `(csg_id² − od²)/1029.4 × L` (simplified: last casing ID for whole string) | `AdvancedHydraulicsEngine` capacity fns, but composition inline |
| **Derived pressures/strokes** | ICP = `SCR + SIDPP`; FCP = `SCR × KillMW / MW`; strokes = `volume / pump_output` | **none — no engine defines ICP/FCP/strokes** |
| **Choke schedule** | linear ICP→FCP over a fixed 10 intervals | none — inline |

Only `kill_mw`, `maasp`, `kick_volume` were real engine calls. **The real input
boundary was therefore the handler, not the engine.**

### Input contract entering the computation (from the invocation signatures)

| Canonical engine/compute input | Caller source (widget) | Raw UI unit | Transformation | Canonical unit |
|---|---|---|---|---|
| `tvd_ft` | `wc_tvd` | m | ×3.28084 | ft |
| `md_ft` | `wc_md` | m | ×3.28084 | ft |
| `shoe_tvd_ft` | `wc_shoe_tvd` | m | ×3.28084 | ft |
| `hole_size_in` | `wc_hole_size` | in | — | in |
| `casing_id_in` | `wc_last_csg_id` | in | — | in |
| `mw_ppg` | `wc_mw` | pcf | ÷7.48 | ppg |
| `frac_gradient_psi_ft` | `wc_frac` | psi/ft | — (÷0.052 only inside MAASP call) | psi/ft |
| `sidpp_psi`,`sicp_psi` | `wc_sidpp`,`wc_sicp` | psi | — | psi |
| `pit_gain_bbl` | `wc_pit_gain` | bbl | — | bbl |
| `scr1_psi`,`scr1_spm`,`scr2_*` | `wc_scr*` | psi / spm | — | psi / spm |
| `pump_output_bbl_stk` | `wc_pump_output` | bbl/stk | — | bbl/stk |
| pipe `od_in`/`id_in` | `wc_pipes[*]` (AddPipeDialog) | in | — | in |
| pipe `length_ft` | `wc_pipes[*]` | m | ×3.28084 | ft |

### Hidden inputs / hidden state (mission §7)

* Constants: `3.28084`, `7.48`, `0.052`, capacity divisor `1029.4`, fixed
  `intervals = 10`, kick-type label map, default `last_pipe_od = 5`.
* Mutable state: `self.wc_pipes` (a live list mutated by add/edit/remove).
* Reference tables: **none** — the pipe program is manual entry via
  `AddPipeDialog`; there is no catalog/preset behind the kill sheet.

## E. Unit-conversion single owner (mission §9)

All raw→canonical conversion is now performed **exactly once** in
`build_canonical_kill_sheet_inputs()` inside
`core/engineering/well_control_kill_sheet.py`. The factors
(`FT_PER_M`, `PCF_PER_PPG`, `PSI_PER_PPG_FT`) are frozen module constants copied
verbatim from the handler. A test (`test_unit_conversion_single_owner`) proves no
double or missing conversion. **No numerical value changed for cleanliness.**

## F. What was built (mission §11/§14/§18-21)

New Qt-free module `core/engineering/well_control_kill_sheet.py`:

* `PipeSegment` — frozen canonical pipe record (in / ft).
* `WellControlKillSheetInputs` — frozen, Qt-free, canonical-unit input object
  (NOT a `GenericCalculationInputs`); tuple of pipes; `as_dict`/`from_dict`
  round-trip; a `display` mapping that echoes the original UI-unit numbers for
  faithful rendering but is consumed by no formula.
* `build_canonical_kill_sheet_inputs(**raw_ui)` — single unit-conversion owner.
* `KillSheetResult` — complete, serializable composite result, with members
  classified CORRECTNESS (kill weights, ICP/FCP/MAASP, volumes, strokes, kick
  geometry, choke schedule) vs DIAGNOSTIC (`warnings`, `engine_method`). ASCII
  rendering stays UI-only in the handler.
* `compute_kill_sheet(inp)` — the relocated composite computation, **byte-for-byte
  identical arithmetic** to the original handler (proven by regression), returning
  a `KillSheetResult` with explicit failure classification
  (`INPUT_INVALID` / `ENGINE_FAILED`).

The handler `_wc_calc_kill` now only (1) reads widgets, (2) calls the builder,
(3) calls `compute_kill_sheet`, (4) renders the unchanged ASCII kill sheet. It
caches `self._wc_last_kill_inputs` / `self._wc_last_kill_result` so a future Save
action has a clean snapshot to persist.

### Preserved (deliberately NOT "fixed") behavior

* The **simplified annulus** (whole string uses the last casing ID) is preserved
  verbatim — changing it would change results, which the mission forbids.
* Ordering is preserved: `kill_mw` runs before the handler's positive-MW guard,
  so `MW ≤ 0` fails at the engine (`ENGINE_FAILED`). A missing fracture gradient
  legitimately fails at MAASP rather than fabricating a value. Both are honest,
  documented, and covered by tests.

## G. Determinism, immutability, verification (mission §16/§17)

* Deterministic across repeated and interleaved runs (same inputs →
  byte-identical `as_dict()`); proven.
* Inputs are frozen (dataclass `frozen=True`, tuple of frozen pipes) and not
  aliased to the source `wc_pipes` list; proven by mutation test.
* Round-trip `as_dict`/`from_dict` reconstructs inputs 1:1 and recomputes
  identically; proven.

## H. Tests (mission §18/§51-55)

New `tests/test_well_control_kill_sheet.py` (11 tests, all Qt-free):
independent-oracle numerical regression (4 cases, actual engine outputs),
single-owner unit-conversion, determinism (repeated + interleaved), input
immutability + non-aliasing, serialization round-trip, and two honest
failure-semantics cases. A Qt subprocess smoke test confirms `_wc_calc_kill`
still renders the full kill sheet end-to-end.

**Full suite: 1160 passed, 4 skipped** (was 1149 passed / 4 skipped; +11 new,
zero regressions).

## I. Snapshot-readiness checklist (mission §27/§28)

| Gate | Status |
|---|---|
| Explicit boundary | ✅ `WellControlKillSheetInputs` |
| All inputs captured | ✅ incl. immutable pipe program |
| Canonical units | ✅ single owner, ft/in/ppg/psi/psi·ft⁻¹/bbl |
| Deterministic | ✅ repeated + interleaved |
| Complete result | ✅ `KillSheetResult` whole result serializable |
| Reconstructable w/o UI / mutable pipe list / globals | ✅ round-trip proven |
| Hidden deps understood | ✅ constants + label map + no catalog |
| Reference semantics understood | ✅ pipe program = MANUAL entry, no catalog/preset |

The kill sheet **is** snapshot-ready.

## J. Persistence decision (mission §27-49) — Outcome B, deferred

Persistence is **not** implemented this mission. Reasons, per the mission's own
gates:

1. **Do not add a DB table just to show progress** — the primary deliverable
   (an honest, canonical, deterministic, snapshot-ready boundary) stands on its
   own and is complete.
2. **Semantic divergence from the three persisted calcs.** T&D / Casing / Cement
   each persist a *single* `EngineeringResult` from *one* engine call. The kill
   sheet is a **composite**: three engine calls plus relocated handler
   engineering, yielding a bespoke `KillSheetResult` (nested string/annular
   detail lists + a choke schedule). The default posture is VERIFICATION-ONLY
   and no generic repository/snapshot/history-UI/reference-catalog abstraction is
   justified without proven semantic identity — which is absent here. The
   reference-diversity evidence already argues AGAINST a generic reference layer
   (DrillPipe = authoritative, Casing = preset, Cement = direct, WC = manual /
   mixed).
3. **A future Calc#4 slice, if approved, is now cheap and safe** precisely
   because the readiness work is done: it would add a *concrete*
   `well_control_persistence.py` (snapshot = `WellControlKillSheetInputs.as_dict`
   + engine `method` + schema version), `well_control_repository.py`,
   `WellControlKillSheetRecord`, a read-only `WellControlHistoryDialog`, and W13
   Save/History wiring — mirroring the cement slice but with its own concrete
   classes, whole-result (`KillSheetResult`) verification via the existing shared
   `deep_numeric_diff`, and mandatory cross-process reconstruction. No new
   dependency, no Alembic (`_apply_safe_schema_upgrades` already auto-creates new
   `Base` tables via `CREATE TABLE IF NOT EXISTS`).

## K. Ranked next-step candidates (mission §47 — not implemented)

1. **Well Control kill sheet → Calc#4** (highest value: kill sheets are exactly
   the well-control artifact operators want historically; now snapshot-ready).
2. The clean single-engine WC sub-tabs (kick tolerance, trip margin) — already
   canonical, would be trivial `EngineeringResult` persists if grouped with #1.
3. Hydraulics (ECD / pressure-loss) — a separate boundary audit first.

## L. No unrelated cleanup, no new dependencies (mission §48/§49)

No dead-code deletion, no dependency added, no refactor beyond the kill-sheet
boundary. `.github/workflows/ci.yml` left untouched.

## M. Conclusion

The Well Control kill-sheet input boundary is now honest, canonical,
deterministic, immutable and snapshot-ready, with the sole unit-conversion owner
centralized and every formula preserved byte-for-byte (regression-proven).
Persistence is deferred as a deliberate, justified Outcome B; a concrete Calc#4
slice can be built on this foundation whenever approved.
