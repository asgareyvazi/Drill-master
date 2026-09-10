# DrillMaster — Zero-Semantics Implementation Report (2026-09-10)

Implementation phase for the two data-integrity violations identified by the
2026-09-10 forensic re-audit: schematic fabrication and inventory
zero≠missing. The repository was re-verified from scratch before any change;
nothing from the previous session report was assumed.

---

## A. Repository identity

| Item | Value |
| --- | --- |
| Branch | `arena/01a085e0-drill-master` |
| Baseline commit (HEAD at phase start) | `7936a59` — "Fix P0 defects, add well-centric acceptance, CI, and 2026-09-09 forensic audits" |
| Did `7936a59` exist? | **Yes on the remote** (`refs/heads/arena/01a085e0-drill-master`), **not in the fresh local clone** (session reset had dropped local commits). It was fetched from the remote and the local branch fast-forwarded onto it; the working tree matched that commit exactly (0 tracked diffs), so nothing was overwritten or reset. |
| Did `7054da3` (local-only CI-workflow commit) exist? | **No — lost** with the session reset. Its sole file, `.github/workflows/ci.yml`, survived on disk (untracked) and is byte-identical to the lost commit's content. |
| CI workflow tracked locally? | No — untracked; pushing it still requires the GitHub App `workflows` permission (remote rejected it on 2026-09-10 with `refusing to allow a GitHub App to create or update workflow .github/workflows/ci.yml without workflows permission`). |
| Working tree at phase start | Clean except the untracked `.github/workflows/ci.yml`. |
| Environment | Python 3.11.2, PySide6 6.8.1.1, pytest 9.1.1, ruff 0.16.6 (venv and Qt stubs rebuilt this session via `tools/qt_headless_env.sh`). |
| Final commit | This phase's single implementation commit (message: "Fix schematic no-fabrication and inventory zero semantics"); SHA reported in the session summary after committing. |

## B. Baseline (measured before any change)

| Measure | Value |
| --- | --- |
| Collected | 816 |
| Passed | 812 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 4 (DDR XLSX/PDF opt-ins, MinerU opt-in, Windows bundle opt-in — all deliberate) |
| XFailed / XPassed | 0 / 0 |
| E722 (bare except) | 0 |
| F821 (undefined name) | 0 |
| Ruff project-config debt | 5489 findings (= `.github/ruff-debt-ceiling.txt`) |

## C. Schematic root cause

### Fabricated fields discovered (all in the ACTIVE auto-generate path:
`tabs/w3b_wellbore_schematic_tab.py` `_generate_auto`/`auto_generate` →
`core/wellbore_schematic_engine.py` `SchematicAutoBuilder.build_from_well`)

| Field | Default source | Coercion bug |
| --- | --- | --- |
| Total depth | `well.get("target_depth", 3000) or 3000` | missing **and explicit 0** → 3000 m |
| GL (ground level) | `well.get("gle_msl", 10) or 10` | missing **and explicit 0** → 10 m |
| KB (RTE) | `well.get("rte_msl", 15) or 15` | missing **and explicit 0** → 15 m |
| Casing program | `_add_default_casings` fabricated a full 4-string program (20"/13⅜"/9⅝"/7" at TD fractions) whenever no casing report existed | — |
| Casing shoe depth | `c.get("to", ...) or 500` | missing shoe → 500 m |
| Casing wall thickness | `id_ if id_ > 0 else od * 0.9` | unknown ID invented from OD |
| Casing metallurgy | `grade="L-80"`, `connection="BTC"` | invented grade/connection |
| Cement | `cement_bottom_m=to_d, show_cement=True` | cement-to-shoe asserted for every casing |
| Formation base | `f.get("base", ...) or 100` | missing base → 100 m |
| Formation lithology | `f.get("Lithology", "Shale")` | unknown lithology → "Shale" |
| Completion geometry | `od_inch 4.5`, `length_m 2.0`, label `"Tubing"` defaults | invented completion equipment |
| Model defaults | `WellboreSchematic(total_depth_m=3000.0, gle_msl_m=10.0, kb_msl_m=15.0, tubing_od_inch=3.5, tubing_bottom_m=2800.0)` | fabrication baked into the dataclass; `WellboreSchematic()` for a missing well carried all of it |
| Tab UI | `td_spin.setValue(3000)` + `on_well_changed`'s `or 3000` | input pre-filled with a fake TD |
| Latent parser bug | `float(c.get("od", c.get("size", 0)) or 0)` on string sizes like `'13 3/8"'` | ValueError inside a broad `except` silently dropped ALL casings — so the fabricated default program fired even when real casing data existed |

### Why it violated the architecture
"Unknown must remain unknown": the generator manufactured engineering facts
(absent → plausible-looking numbers) and destroyed explicit zeros through
truthiness coercion, and those values were persisted through the tab's save
payload (`elements_json`) as if they were source data. The 2026-09-09
acceptance table had cited a *trajectory* test as no-fabrication evidence — a
misattribution corrected by the re-audit.

### What changed
- `WellboreSchematic` scalar fields are now `Optional[float] = None`
  (None = absent; 0.0 = explicit zero; value = fact). Tubing defaults
  (3.5"/2800 m) removed.
- `build_from_well` reads source values verbatim via a strict `_to_float`
  (None stays None; 0 stays 0.0; numeric strings parsed).
- `_add_default_casings` **deleted** — a well without casing data yields a
  schematic without casings.
- Casing rows: string sizes parsed properly (`13 3/8"` → 13.375, `9-5/8"` →
  9.625 — the formats the importers actually store); rows missing top or shoe
  depth are skipped, never completed; unknown ID stays `None` (rendered
  solid); metallurgy only from source; no cement asserted. Unclassifiable
  string labels map to a new generic `ElementType.CASING` (neutral gray)
  instead of silently becoming "Surface".
- Formations: rows without top/base skipped; unknown lithology stays `""`.
- Completion: no depth in source → no item; no 4.5"/2.0m/"Tubing" defaults.
- Renderer is None-safe: neutral canvas scale for unknown TD (view geometry
  only), no open-hole/bit/tubing/Xmas-tree/safety-valve/gas-lift drawing when
  the underlying fact is unknown, depth ruler spans only data that actually
  exists when TD is missing.
- Tab: `td_spin` starts at 0 (unset), `on_well_changed` displays TD exactly as
  reported, empty-well auto-generate reports "No source data available —
  schematic is empty (no invented values)", None-crash guards on quick-add
  and the completion dialog, unknown ID displays "—" and can be cleared back
  to unknown.

### Why the fix does not fabricate data
Every value in a generated schematic now traces to a source cell/row; absence
is represented as `None`/empty and **persists as JSON `null`** (verified by
`test_unknown_td_persists_as_null`). Rendering fallbacks are pure view
geometry (canvas scale 0.3 px/m, symbol sizes) that are never persisted and
never displayed as values.

## D. Inventory root cause

The `BulkMaterials` column was nullable, but a **client-side ORM default
`default=0.0` coerced explicit `None` to 0.0 at INSERT** (verified
empirically: `BulkMaterials(initial_stock=None)` persisted as 0.0), so the
database physically could not represent "missing". That client-side default
is not part of the DDL (emitted schema stays `FLOAT` nullable — verified via
`CreateTable` compile), so removing it is **not a schema migration** and no
database changes are required. `received`/`used` keep their 0.0 defaults
(movement-absent = 0 is the established daily-report convention, distinct
from the opening trichotomy).

### 1. Ledger carry-forward (`core/mud_ledger.py`)
- Old: `if mat in last_closing and opening == 0: if received == 0 and used == 0: opening = last_closing` — an explicit zero opening (no movement) was treated as missing and **replaced by the previous closing**; a missing opening *with* movements got no carry at all (stayed 0).
- New: carry-forward fires **only when `opening is None`** (genuinely missing), regardless of movements; unknown openings propagate to unknown closings (`LedgerEntry.closing_stock` is `None`); `validate()` makes no stock judgment on unknown rows.
- Tests: `TestLedgerCarryForward` (three-state day sequence: 100→80, missing→carried 80→50, explicit 0 stays 0; unknown propagation; validate tolerance).

### 2. Save path (`DatabaseManager.save_bulk_material`)
- Old: `initial_stock = float(get("initial_stock", 0.0) or 0.0)` (missing → 0.0) then `if carry_forward (default True) ... initial_stock = previous.current_stock` — **overwrote even an explicitly supplied nonzero opening**.
- New: explicit value (incl. 0.0) is preserved exactly; carry-forward applies **only** when the opening is missing and only if the previous closing is itself known; closing stays `None` when the opening is unknown (insert and update branches).
- Tests: `TestSavePathExplicitZero`, `TestSavePathMissing`, `TestSavePathNonzero` (7 persisted-state tests).

### 3. Import normalization (`core/profile_import_engine.py`)
- Old: `"initial_stock": initial or 0.0` (and the same in the sheet-table path) — missing stock became 0.0 before persistence, with a derived closing computed from the fabricated opening.
- New: missing stock stays `None`; `current_stock` is `None` when the opening is unknown; movement-only rows keep their movements. Same fix applied to cement-additive `on_hand`. The atomic importer already had None-aware closing computation and a NOT NULL guard for BOP pressure; the extractor's `pressure or 0.0` (which fabricated 0-psi ratings and bypassed both guards) now passes the raw value so the review gate flags it and the save layer skips it.
- Tests: `TestImportNormalization` (extraction preserves None/0; atomic import persists NULL and 0.0 distinctly).

### Additional same-class fix
The atomic importer **re-ADDed** bulk material rows on re-import without an
upsert (duplicate inventory state — mandate Input D). It now upserts by
`(report_id, material_name)`. Test: `TestRepeatedImport` (save path and
atomic path idempotency, values untransformed).

### Zero/Missing audit table (sweep results, §19)

| File | Field | Old behavior | Zero valid? | Action |
| --- | --- | --- | --- | --- |
| core/wellbore_schematic_engine.py | TD/GL/KB/water depth | `or 3000/10/15/0` | yes (GL/KB/water; TD 0 = ORM default) | **fixed** (verbatim read) |
| core/wellbore_schematic_engine.py | casing shoe/ID/grade/connection/cement | `or 500`, `od*0.9`, "L-80"/"BTC" | n/a (invented values) | **fixed** (skip/None/source-only) |
| core/wellbore_schematic_engine.py | formation base/lithology | `or 100`, "Shale" | n/a | **fixed** |
| core/wellbore_schematic_engine.py | completion od/length/label | 4.5/2.0/"Tubing" | n/a | **fixed** |
| tabs/w3b_wellbore_schematic_tab.py | TD input | pre-filled 3000, `or 3000` | yes | **fixed** (0 = unset input) |
| core/mud_ledger.py | opening | zero treated as missing | yes | **fixed** |
| core/database.py | initial/current stock | ORM default coerced None→0.0; carry overwrote explicit | yes | **fixed** (client default removed, carry gated) |
| core/database.py | bulk re-import | duplicate rows | n/a | **fixed** (upsert) |
| core/profile_import_engine.py | bulk initial/current, cement on_hand | `or 0.0` | yes | **fixed** (None preserved) |
| core/profile_import_engine.py | BOP working_pressure | `or 0.0` bypassed NOT NULL guard | no (0 psi invalid) | **fixed** (raw value; review gate + skip) |
| core/profile_import_engine.py | movements (received/used) | `or 0.0` | 0 = no movement (established convention) | **safe** (documented convention) |
| core/validators.py | bulk stock cross-check | `or 0` collapsed trichotomy | yes | **fixed** (None-aware) |
| tabs/w7_logistics_Widget.py | opening input/display | empty cell → 0.0; None crash | yes | **fixed** (empty→None; "—" display) |
| tabs/w10_Planning_Widget.py | plan material input/display | `or 0`; None crash | yes | **fixed** (empty/— → None; "—" display) |
| core/report_engine.py 588/763/766, operations_intelligence 48/49 | duration aggregates/exports | `or 0` | 0 h vs unknown | **deferred** (aggregation/export convention; no evidence of NULL durations in practice; changing alters export content) |
| core/report_engine.py 776/1713-1714/1733, operations_intelligence 92 | cost sums | `or 0` | 0 = no recorded cost | **safe** (sum of recorded values) |
| core/report_engine.py 1746 | max depth | `or 0`, guarded by `> 0` | yes | **safe** (guard prevents fabrication) |
| core/report_engine.py 2217-2219 | planned values in export | `or 0` | yes | **deferred** (PLAN export cells) |
| core/actual_vs_plan.py 29/118-119 | planned vs actual | `or 0` | yes | **deferred** (analysis display helper) |
| operations_intelligence 50/103-104 | depth/mw filters | `or 0` behind `is not None`/truthy filters | mw 0 physically invalid | **safe** |
| core/value_normalizer.py 243/284 | regex seconds | `or 0` | syntactic default | **safe** |
| profile_import_engine 338/344-345 | hours_worked, days-without-LTI, incidents | `or 0.0/0` | 0 days-without-LTI vs unknown | **deferred** (safety counters; UI-wide ripple; documented) |
| profile_import_engine 467 | BOP status "Operational" | hardcoded/model default | n/a (string) | **deferred** (model-level default; not a numeric engineering value) |
| tabs/w10 1289-1290/1517/1560-1561/2128-2137, w12 1290-1320 | chart series | `or 0` | yes | **safe** (display-only chart coordinates) |
| core/database.py 5735/5784 | totals | `or 0` | aggregation of knowns | **deferred** (summary display) |
| core/engineering/core.py 662 | chemical ledger (duplicate module) | `or 0` | yes | **deferred** (dead module — zero production imports) |
| core/repositories/logistics_repository.py 19 | opening | `or 0` | yes | **deferred** (dead module — no production or test callers) |

## E. Zero/Missing semantic matrix

| Field / path | Missing | Explicit 0 | Nonzero | Correct after fix? |
| --- | --- | --- | --- | --- |
| Well TD → schematic | None | 0.0 (preserved; no bit/ruler/open-hole) | value | **yes** (test A/B/C) |
| Well GL/KB → schematic | None | 0.0 preserved (old: 10/15) | value | **yes** |
| Casing size (string `13 3/8"`) | row skipped | 0 → row skipped (invalid OD) | parsed inches | **yes** |
| Casing top/shoe | row skipped | 0.0 preserved | value | **yes** |
| Casing ID | None (solid draw) | 0.0 → treated as unknown¹ | value | **yes** |
| Formation top/base | row skipped | preserved; base<=top skipped | value | **yes** |
| Completion depth | no item | no item (position required) | value | **yes** |
| BulkMaterials.initial_stock (save) | NULL (or carried) | 0.0 (never carried) | value (never overwritten) | **yes** |
| BulkMaterials.current_stock | NULL | 0.0 | derived | **yes** |
| Ledger opening (read) | carried from previous closing when known | 0.0 (never carried) | value | **yes** |
| Ledger closing | None (propagates) | 0.0 | computed | **yes** |
| Import extraction (bulk/cement) | None | 0.0 | value | **yes** |
| BOP working_pressure (import) | None → review flag + row skipped | n/a (invalid) | value | **yes** |
| Persisted schematic total_depth | JSON `null` | 0.0 | value | **yes** |

¹ zero wall thickness is physically meaningless; the builder maps an explicit
0/negative ID to unknown (documented in code).

## F. Regression matrix

| Invariant | Test | Result |
| --- | --- | --- |
| No schematic fabrication (empty well) | `TestCaseAEmptyWell` (3 tests) | PASS |
| Explicit zero preserved (schematic) | `TestCaseBExplicitZero` (2 tests) | PASS |
| Missing remains missing (schematic) | `TestCaseCPartialSource` | PASS |
| Partial source safe | `TestCaseCPartialSource` + `TestSourceFidelity` (4 tests) | PASS |
| No default casing program | `TestCaseAEmptyWell.test_empty_well_produces_empty_schematic` | PASS |
| Existing schematic preserved (Case D) | `TestCaseDExistingSchematicPreserved` (2 tests) | PASS |
| Repeated generation deterministic | `TestDeterminismAndReImport.test_repeated_generation_is_deterministic` | PASS |
| Re-import creates no synthetic schematic data | `TestDeterminismAndReImport.test_reimport_does_not_create_synthetic_data` | PASS |
| Unknown-state rendering (real raster paint) | `TestRendererNoData` (subprocess render + scale test) | PASS |
| Inventory carry-forward safe (ledger) | `TestLedgerCarryForward` (3 tests) | PASS |
| Inventory save path preserves explicit zero / nonzero / missing | `TestSavePath*` (7 tests) | PASS |
| Import preserves zero / missing | `TestImportNormalization` (3 tests) | PASS |
| Re-import idempotent (no duplicates, no transformation) | `TestRepeatedImport` (2 tests) | PASS |
| Ledger entry representation trichotomy | `TestLedgerEntryRepresentation` | PASS |
| R18 | `test_r18_r19_save_preservation.py` (48 tests) | PASS |
| R19 | same file | PASS |
| Well-centric identity (rig ≠ identity) | `test_well_centric_acceptance.py` (9 tests, incl. scenario F rig-change both orders) | PASS |
| Import repairs / golden / phase-1 regressions | full suite | PASS |

Old-code proof: with the production changes stashed, the schematic suite
fails across Case A/B/C/D, source-fidelity, determinism and renderer classes,
and the inventory suite fails across explicit-zero, ledger, import and
re-import classes (multiple distinct failures observed in both stashed runs).

## G. Final test result (exact)

| Measure | Baseline | Final |
| --- | --- | --- |
| Collected | 816 | **848** |
| Passed | 812 | **844** |
| Failed | 0 | **0** |
| Errors | 0 | **0** |
| Skipped | 4 | **4** (same opt-ins) |
| XFailed | 0 | **0** |
| XPassed | 0 | **0** |
| E722 / F821 | 0 / 0 | **0 / 0** |
| Ruff debt | 5489 | **5489** (= ceiling; three transient findings introduced by the new tests were eliminated before commit) |

Duration ≈ 184 s. The +32 tests are exactly the two new suites
(16 schematic + 16 inventory). No existing test was weakened, deleted or
re-skipped. Test-quality audit: every new test exercises real production
code (builder, renderer, DatabaseManager, MudChemicalLedger, profile
extractor) against real in-memory SQLite or tmp-file databases and asserts
**persisted** state; none uses a stub or mock. The single process-isolation
case (raster render) runs the unmodified production renderer with real
QPainter/QPixmap in a subprocess because a prior suite test's
QCoreApplication singleton makes in-process QApplication construction
impossible — documented in TESTING.md and the test docstring.

## H. Remaining blockers (unchanged by this phase)

- **Wellbore/schema v3** — not started (explicitly out of scope this phase).
- **KPI canonicalization** — not started; duplicate formula sites remain.
- **Windows GUI** — NOT VERIFIED (plan: `VERIFICATION_PLANS.md` §1).
- **Installer/bundle** — NOT VERIFIED (plan §2).
- **MinerU/local-AI** — NOT VERIFIED (plan §3).
- **Remote CI execution** — NOT VERIFIED; additionally `.github/workflows/ci.yml` is still not on the remote branch (push blocked by missing `workflows` permission for the GitHub App token).
- **Deferred zero-semantics sites** — see the audit table in §D (safety counters, duration aggregates/exports, plan-export cells, totals, dead modules).

## I. Next recommended phase (not implemented now)

**Primary: CI operationalization (small, immediate, gates everything).**
Evidence: the workflow is written and locally verified line-by-line; the debt
ratchet reproduces exactly (5489 = ceiling); the only blocker is the missing
`workflows` permission and one push. One permission grant turns every
subsequent phase into remotely-gated work and finally converts the CI row
from BLOCKED to observed.

**Then: Wellbore/schema v3 foundation.**
Evidence: it is the largest documented architectural gap (no persistent
Wellbore entity; sidetrack-as-wellbore and workover modeling blocked on it),
and the zero-semantics work just completed is precisely the prerequisite the
audit chain demanded — v3's wellbores/sections would have inherited the
fabrication and zero-collapse bugs had they been built on the old builder and
inventory semantics. Proceed with the same contract-first style: invariants
explicit, unknown representable, explicit zero preserved, migration designed
before code.
