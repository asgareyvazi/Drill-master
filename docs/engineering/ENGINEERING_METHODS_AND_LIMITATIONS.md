# Engineering methods and limitations

Scope: the calculation and data-ingestion methods that DrillMaster exposes to users after M53–M55, with their version strings, units, assumptions and limits. The method and version strings below are quoted from the code (`METHOD`, `*_VERSION` constants). If this document and the code disagree, the code is authoritative and this document is out of date.

**Release status:** UNSIGNED and NOT RELEASE-APPROVED. None of the methods here has field, regulatory or third-party certification. Anything labelled SCREENING is a planning or check aid. It is not a design approval.

## General rules (all methods)

* No invented values. A missing input produces an explicit *unavailable* state. It never becomes a zero or a default.
* Units are never mixed silently. Survey depths are stored in metres. Feet are converted with exactly 0.3048, and only when the unit is known.
* Azimuth references (true or grid north) are recorded as stated and **never converted**. No CRS or convergence correction exists in the product.
* Currencies are never summed together. A mixed-currency scope reports `total_actual = None` and raises a `COST_CURRENCY` alert.
* Calculation results carry method, version, inputs and warnings. Saved records are append-only.

## Directional

| Method | Version / method string | Module |
|---|---|---|
| Minimum curvature (canonical) | `TrajectoryCalculator.calculate` | `core/engineering/engines/trajectory.py` |
| Survey file import | `M55 survey file import v1` | `core/survey_file_import.py` |
| Well plan designer | `M55 plan designer v1`, "Minimum curvature (canonical TrajectoryCalculator); constant-curvature arcs" | `core/well_plan_designer.py` |
| Plan vs actual, offset screening | `M52 centre-to-centre screening v1` | `core/trajectory_compare.py` |
| Legacy anti-collision screening | "Linear-interpolated 3D centerline separation screening" | `core/engineering/engines/anti_collision.py` |

**Survey import (M55)**
* Reads CSV, TXT, DAT (comma, semicolon, tab, pipe, or two or more spaces) and XLSX (with sheet selection).
* Header aliases cover MD, inclination and azimuth. The depth unit comes from the header (`MD (ft)`, `MD [m]`, …) or from the user. A missing unit, or a conflict between the header and the user's choice, **blocks the import**.
* Rows are validated by the canonical `core.survey_records.prepare_surveys`:
  * finite numbers;
  * inclination 0–180°;
  * MD strictly increasing.
* The importer also requires azimuth in [0, 360).
* Every rejected row is reported with its source row number and reason. If two rows claim the same MD and one of them is invalid, both are rejected; the importer does not pick one silently.
* Nothing is persisted. The accepted stations are only placed into the editable survey table.

**Plan designer (M55)**
* Segments are *hold* (length), *curve* (target inclination and azimuth at a DLS in deg/30 m) and *hold to TVD*.
* Curves are constant-curvature arcs. Stations are sampled by spherical interpolation of the tangent vector, then the canonical calculator integrates them, so the plan uses exactly the same MinCurv as surveys.
* Verification: an independent closed-form J-profile check gives R = 30/DLS(rad). For KOP 500 m, build to 30° at 3°/30 m and hold to TVD 1500 m:

  | Quantity | Value |
  |---|---|
  | End of build MD | 800 m |
  | End of build TVD | 786.4789 m |
  | End of build HD | 76.7618 m |
  | TD MD | 1623.9032 m |
  | HD | 488.7134 m |

  The designer reproduces these values (`tests/test_m55_directional.py`).
* A breach of the DLS limit is **warned, never clipped**.
* Target check (M62, `M72 plan designer v3`): the closest point on the **continuous minimum-curvature path**. Between stations the path is the circular arc p(θ) = p1 + R(sin θ·t1 + (1−cos θ)·n), R = L/β, n the unit normal towards t2 (straight line when β → 0); each interval is sampled and refined by golden section. The closest station is reported alongside. A target without a radius is never reported as hit. Validated against the planar closed form HD = R(1−cos θ), TVD = KOP + R sin θ, and the arc reproduces the canonical MinCurv station positions to 1e-6 m.
* Safeguards (M62): non-finite inputs, an antiparallel curve (dogleg ≈ 180°, undefined arc plane) and an impossible hold-to-TVD are explicit errors.
* Limitations:
  * no tangent-to-target solver;
  * no turn-rate-only segments;
  * no plan versioning model (see the capability matrix);
  * the output is a planning aid, not an approved plan. The CSV header says so.

**Plan vs actual and offsets (M52, reused by M55)**
* Uses the exact MinCurv arc and continuous closest approach.
* Reports high-side and right-side (HL/RL) deviation along the well.
* **SCREENING – centre-to-centre, no ISCWSA uncertainty, NOT APPROVED.** Separation factor and ellipse clearance are not computed, because no uncertainty data or validated error model exists.
* welleng ISCWSA error models remain owner-gated.

## Drilling engineering engines (pre-existing; audited in M53–M60, not changed)

| Engine | Method string | Label |
|---|---|---|
| Casing | API TR 5C3 pipe-body subset (Barlow + four-regime + fyax + VME; capped-end r2) | Subset only; connections, tri-axial design factors and ductile-rupture models are not implemented (see the module docstring) |
| Cement | Oilfield capacity (D²/1029.4) + stacked column hydrostatic; balanced plug `M52 balanced plug v1` | Balanced plug is SCREENING. No slurry data is invented |
| Torque & drag | Johancsik soft-string (SPE 11380) | SCREENING; no stiff-string model; no LGPL code used |
| MSE | Teale (1965) Mechanical Specific Energy | |
| Well control | IWCF / IADC well-control manuals; Bourgoyne et al. | Training and check aid; not a kill-sheet approval |
| Fishing | Legacy free-point/stretch chart approximations | SCREENING |
| Mud volume | Mass/volume balance; no hidden defaults | |
| Hydraulics | `core/hydraulics_engine.py` | Pre-existing; not re-validated in M53–M60 |

## Operations and dashboard (M53)

* The KPIs come from `core/operations_dashboard.build_snapshot`. Each KPI declares its definition, unit, source table and freshness (latest report date).
* Rates such as ROP, NPT % and cost per metre are computed only when the numerator and denominator are both known and positive. Otherwise the KPI is *unavailable*.
* Footage ignores negative depth progress.
* Alert thresholds:
  * `NPT_HIGH`: NPT share above 20 %;
  * `COST_OVER_AFE`: actual cost above the AFE in the same currency;
  * `COST_CURRENCY`: more than one currency in scope.

## DDR ingestion (M54)

| Component | Version | Behaviour |
|---|---|---|
| Generic PDF tables | `M54 generic PDF tables v1` | Detects scanned pages (no text layer) and reports them. Excludes headers and footers by page margin. Joins tables that continue over pages when their header repeats. Joins ruled headerless continuations. Merges wrapped cells. |
| OCR | — | Not available. No local OCR engine is installed, so scanned pages show "OCR unavailable" and are not guessed. |
| Report profiles | `M54 report profile v1` | Immutable, append-only versions holding operator, format, header aliases, column maps and units. The profile resolves the field. A unit in the column header beats the profile unit. Aliases may only target canonical fields (`core.canonical_schema.FIELD_SPECS`). |

Fields stored in profiles but **not yet applied** by the importer (PARTIAL): `date_formats`, `table_rules`, `continuation`, `confidence_threshold`.

Document-to-well matching is a suggestion only. Every imported value goes through the review workspace (source, page, original value, normalized value, unit, mapping, confidence, warning, decision) before it is saved.

## DDR profile rules (M61, `PROFILE_RULES_VERSION = 1`)

* Dates: the profile's `date_formats` are tried in order on textual date fields. Exactly one resulting calendar date is accepted (formats that agree are not ambiguous). No match, or two formats giving different dates, sets the value to empty and adds a review item quoting the original string and every reading. The day/month convention is never inferred. Without a profile the canonical parser is unchanged.
* Table rules: `stop_markers` ignore the marker row and every later row of that table; `skip_rows_containing` ignores matching rows; `skip_tables_containing` ignores a whole table. Matching is case-insensitive substring on the joined row (or table name and headers). Each ignored row or table is a review warning with the rule, profile key/version, value and page/row source.
* Continuation: when the profile disables it, tables on consecutive pages are never joined and no header-less carry-over is applied.
* Confidence threshold: acceptance-eligible ≥ threshold; review band [min(0.70, threshold), threshold); low below that. Values in a needs-review state are never bulk-accepted. Without a profile the historical 95 % / 70 % bands apply.

## Calculation history (M67)

* Read-only adapters; the source records are never changed. Recalculation uses each engine's own `recalculate_from_snapshot` on the frozen snapshot and the shared `classify_verification`; a method change is flagged, and a recalculation is stored only as a new `calculation_cases` row whose note names the original record and verification status.
* W13 cases (M63) capture what the calculator page shows; W13 calculators have no per-method version, which the case label states.

## Survey revisions, plan tie-in and target solver (M72)

- **Survey revisions** (`core/survey_revisions.py`, `SURVEY_REVISION_VERSION = "M72 survey revision v1"`):
  numbered per well, insert-only (storage trigger), stations stored canonically (MD m, angles deg) with the
  declared source unit (m or ft; ft = 0.3048 m exactly), azimuth reference (true/grid/magnetic, default true)
  and depth datum. A missing datum or an unknown unit or reference is refused; no azimuth or datum conversion is
  performed, and a replace/append/branch revision whose reference or datum differs from its parent is refused.
  Modes `initial`/`replace`/`append`/`branch` with `parent_id`; the SHA-256 of the canonical stations and the minimum-curvature result (`core.well_trajectory`) are stored with the revision.
- **Plan tie-in** (`PLAN_VERSION = "M72 plan designer v3"`): a plan may pin a survey revision station through
  `inputs.tie_in` (`survey_revision_id`, `survey_sha256`, MD/inc/azi/TVD/N/E). Saving checks that the revision
  belongs to the well (and wellbore), that its SHA-256 still matches and that the tie-in is one of its
  stations (1e-6). The designed path is offset so its first station sits at the tie-in TVD/N/E; VS is
  recomputed. An unavailable pin refuses to design; it never falls back to the surface. v2 plans verify as
  METHOD CHANGED with numerically identical stations.
- **Build-hold solver** (`SOLVER_VERSION = "M72 build-hold target solver v1"`), closed form, vertical tie-in
  only: R = 5400/(pi*DLS); V = target TVD - KOP TVD; H = horizontal offset; d = hypot(R - H, V);
  inclination = atan2(V, R - H) - acos(R/d); tangent = sqrt(d^2 - R^2); azimuth = atan2(dE, dN).
  Infeasible (with the reason, no plan) when d < R, V <= 0, inclination > max_inc, KOP above the tie-in,
  DLS <= 0, non-finite input or a non-vertical tie-in. Golden: KOP 500 m, 3 deg/30 m, target N -300 E 300
  TVD 1400 m gives 30.0 deg at 135.0 deg and TD 1623.903201 m (miss 3e-13 m).
- **Target checks in plan vs actual**: closest approach of the actual path to each 3D target
  (`trajectory_compare.closest_point`), distance and hit within the target radius; without a radius, hit is
  not judged. Labelled SCREENING; offsets are never fabricated.

## Calculator contracts and history statuses (M73)

- `core/calculator_contracts.py` (`CONTRACT_REGISTRY_VERSION = "M73 calculator contracts v1"`): stable ID,
  schema version, method ID/version, field IDs and canonical units bound to the W13 form labels. First
  contract: Volume > Quick Calc (`M73 pipe capacity v1`, capacity ID^2/1029.4 bbl/ft, displacement
  (OD^2 - ID^2)/1029.4 bbl/ft, reusing `AdvancedHydraulicsEngine`).
- Verification re-runs the current method: MATCH/DIFFERENT within the display rounding of each result
  (0.5 x 10^-decimals); results never stored are listed as not compared. Cases without a method version
  (before M73) or whose version is no longer available are NOT_REPRODUCIBLE; missing or rejected inputs give
  UNREADABLE.
- History shows three separate statuses (readable / comparable / reproducible with the reason) and a
  unit-safe numeric comparison: values in different units are listed as UNIT MISMATCH and never converted.
  Filters and paging (200 per page) run in the database; the text filter matches name and method.

## Well architecture (M74)

- `core/well_architecture.py` (`ARCHITECTURE_VERSION = "M74 well architecture v1"`): immutable numbered
  revisions of sections, casing, liners, tubing, shoes, formations, packers, cement (TOC) and accessories,
  tied to the wellbore and optionally a survey revision; SHA-256 checked on read. Unknown sizes stay unknown.
- Validation (errors refuse the save): known kind and a name; top < bottom; depths >= 0; ID < OD; OD below
  the hole size; liner top inside a larger string whose ID clears the liner OD; unique string names; shoe at
  its string bottom (0.01 m); cement within its string; non-overlapping formations; packer within tubing.
  Rules whose inputs are unknown are reported as warnings, not judged.
- The W3b schematic is generated from the stored records through the existing renderer.
- Cement annulus (WORKSHEET; nominal sizes, no caliper, no excess): TOC to cement bottom split at outer string
  boundaries; cased intervals use the outer string ID, open hole the recorded or entered hole size; an
  unknown size leaves that interval's volume empty (never zero). Capacity reuses
  `AdvancedHydraulicsEngine.calc_annular_capacity_bbl_ft`. Saved worksheets are calculation cases pinned to
  the architecture revision ID and SHA-256; they are NOT REPRODUCIBLE from History (no contract).

## Engine inventory, labels and specialist methods (M75, M76, M79)

- `docs/engineering/ENGINE_INVENTORY.md` is generated from the source (`tools/quality/engine_inventory.py`)
  and checked by a test. Formula mutants (bit pressure drop, HHP, jet velocity, capacities, Fann PV, Teale MSE)
  are in `tools/quality/mutation_m70_m76.py`.
- Casing remains the TR 5C3 pipe-body subset (no connection ratings, no triaxial design envelope); torque and
  drag remain Johancsik soft-string SCREENING; the kill sheet shows a TRAINING AID notice on its page.
- `core/specialist_methods.py`: a method may be implemented only when reference, licence, inputs/units,
  limits, independent benchmark and approval are all met. ISCWSA error model and the pwptemp temperature
  model are OWNER REVIEW REQUIRED (licence); stiff-string T&D is NOT IMPLEMENTED (no benchmark).
