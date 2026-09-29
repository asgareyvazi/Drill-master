#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-019 (45 MEDIUM records, class B+C).

Phase 2, eleventh batch: the actual-vs-plan scalar comparator and its engine callers, the
cache TTL accessor, the shared table-widget default, the currency normalizer pair, the
trajectory/bridged-calculator truthiness sites, the mud-ledger closing helper, the two
engineering-ground-truth weighted-ROP assertions, the test seeders/teardowns that read a
fresh self-created database, the deterministic-snapshot test idiom (casing/cement/torque-
drag), and the seven session-lifecycle fixtures that open one discarded session on a
StaticPool in-memory engine.

No genuine defect was found in this batch: every flagged construct was read at its own site
in the hash-verified current tree, traced to its caller and consumer, and each one either
preserves the unknown/zero contract the repository already documents (optional_number /
None-propagating comparators, the finite-boundary _to_number, the upsert-identity `.one()`,
the seeded single-well `.first()`) or is a documented presentation/determinism default.
The record whose register symbol is null (INV34-009493, the DailyReport.forecast column)
is adjudicated through its import contract ("absent stays absent",
core/ddr_import_service.py:501-505).  Observations that are *not* defect claims are kept
in OBSERVATIONS; the section-24 question about core/ai_import_mapper.py is answered there
as well (the file has no `_to_float`; its only float() is a bounded confidence gate).
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-019"

VC, INT, DUP, DDD, DEF, INS = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                               "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT",
                               "INSUFFICIENT_EVIDENCE")

# Every batch-019 file is byte-identical to the tree its records were derived from (verified
# by source_sha256 before any comparison), so no provenance tree and no reconstruction is
# needed.  The mechanisms stay available (unchanged since batch-016).
RECHECK_AGAINST: dict[str, str] = {}
RECONSTRUCT: dict[str, tuple[str, str, tuple[int, ...]]] = {}

# The M34 fingerprint ledger is NOT tracked in the repository (11 MB; only its summary is),
# so the fingerprint gate runs ledger-free: expressions are derived from the register's own
# recorded line text and from the hash-verified tree's AST segments under the same
# path|kind|symbol|norm(expression)|ordinal contract.  When the ledger IS present locally it
# is used first, exactly as in batch-018.  The mode actually used is reported in
# staleness.fingerprint_proof.method.
FINGERPRINT_SOURCE = "docs/audits/m34-evidence/m34-ledger.json"
LEDGER_AVAILABLE = (ROOT / FINGERPRINT_SOURCE).is_file()


def dup(sibling: str, where: str, summary: str) -> tuple[str, str, None]:
    return (DUP,
            f"Second register record for {where}, already adjudicated under {sibling}: "
            f"{summary}",
            None)


def misfire(what: str) -> tuple[str, str, None]:
    """A rule mis-fire: the matched construct is not the semantic the rule family targets."""
    return (DUP,
            f"Rule mis-fire, not a behaviour to adjudicate: {what}",
            None)


# ----------------------------------------------------------------- shared contract fragments
_OPT_NUM = (
    "core/engineering/result.optional_number returns the number, None for a missing value and "
    "raises on a non-numeric one - unknown is carried, never converted to 0"
)
_AGG_ONE = (
    "a SQL aggregate without GROUP BY returns exactly one row, so `.one()` on it asserts the "
    "query ran, not a row count"
)
_TEST_LOCAL_DB = (
    "the fixture creates a fresh DatabaseManager with its own in-memory/static-pool engine "
    "inside the same test function, so the selection cannot see another test's data"
)
_SNAP_SERIAL = (
    "json.dumps(..., sort_keys=True, default=str) is a test-internal comparison, not the "
    "persistence path: sort_keys makes the equality order-independent and default=str only "
    "makes a non-JSON-native value representable so the equality check is possible; any value "
    "that changed between the two serializations would produce a different string and fail "
    "the assertion"
)
_STATIC_POOL_SESSION = (
    "`DatabaseManager.create_session` is `return self.Session()` (core/database.py:3452-3454); "
    "the fixture replaces `Session` with a sessionmaker bound to a StaticPool in-memory engine "
    "and discards the returned session without emitting any SQL, so no transaction is opened, "
    "the pool's single connection is shared with (not withheld from) the sessions the test "
    "actually uses, and the engine itself is per-test"
)


# ----------------------------------------------------------------- adjudications, register order
R: dict[str, tuple[str, str, str | None]] = {}


R["INV34-000052"] = (
    VC,
    "`def compare(metric, planned, actual, tolerance_pct=10.0)` (core/actual_vs_plan.py:28-44) "
    "is the documented backward-compatible scalar comparison ('used by existing operations "
    "tests').  The flagged default 10.0 is the *tolerance band* of the status verdict, not a "
    "value substituted for a missing measurement: `planned = optional_number(planned, "
    "\"planned\")` and `actual = optional_number(actual, \"actual\")` (" + _OPT_NUM + "), and "
    "the function returns `Variance(metric, planned, actual, None, None, \"unavailable\")` when "
    "either side is None (40-41) - unknown planned/actual propagates as status 'unavailable' "
    "with variance None, never as a zero-variance 'on-track'.  The zero/zero convention is "
    "explicit in the code comment ('nonzero / zero has a known delta but no finite percentage - "
    "never synthetic 100%', 42-43).  Consumers: tabs/w10_Planning_Widget.py:1727-1738 passes "
    "the default and explicitly branches on `result.variance is None` (grey render) before any "
    "numeric use; tests/test_operations.py:2, tests/test_m28_finance_safety_plan.py:8 and "
    "tests/test_m30_semantic_regressions.py:259 exercise the comparator including the "
    "unavailable path.  No caller treats a missing planned value as 0.",
    None,
)

R["INV34-000131"] = (
    VC,
    "`CacheEntry.remaining_ttl` returns `max(0.0, self.ttl - self.age)` "
    "(core/cache_manager.py:66-67).  The class's own expiry contract is one line above: "
    "`is_expired` is `(time.monotonic() - self.created_at) > self.ttl` (58-59), i.e. an entry "
    "older than its ttl legitimately exists in the dict until eviction.  For that state "
    "`ttl - age` is negative, and a negative 'remaining time' is a nonsensical countdown; the "
    "clamp reports the truthful 0.0 ('no TTL left'), which agrees with is_expired rather than "
    "inventing time.  This is a derived *time* accessor over monotonic clock deltas, not a "
    "measurement: no stored datum is clamped, and age/creation are never falsified.  The "
    "property currently has no in-repo caller (grep over core/, tabs/, dialogs/, tests/: only "
    "the definition), so there is also no consumer that could misread 0.0 as data.",
    None,
)

R["INV34-000204"] = (
    VC,
    "`min_height: int = 200` (core/common_widgets.py:30) is the minimum pixel height of the "
    "shared `CommonTableWidget` (used by `self._setup_ui(show_toolbar, alternating_colors, "
    "min_height)`, 34).  It is a Qt layout presentation default for the widget frame, not an "
    "operational quantity: it never reaches a model, a database column, an import boundary or "
    "an engineering result, and a caller that wants a different frame passes its own value "
    "(the keyword is part of the public constructor signature, 24-31).  UI presentation "
    "defaults are outside the unknown-vs-zero contract by construction.",
    None,
)

R["INV34-000239"] = (
    VC,
    "`normalize_currency` ends `return text or None` (core/cost_semantics.py:99) under the "
    "docstring 'Return an explicit currency code or None (unknown). An empty/blank currency is "
    "unknown, NOT silently USD (§9)' (88-90).  After `text = str(value).strip().upper()` (94) "
    "the only falsy value `text` can hold is \"\", i.e. the caller supplied a blank currency; "
    "`text or None` maps exactly that to None (unknown) and passes every non-empty code "
    "through, which is precisely the documented contract - the known-marker set above it "
    "(97) already filtered the explicit 'UNKNOWN'/'N/A' spellings so two unknown rows are "
    "never aggregated as proven.  Consumers enforce the unknown downstream: the "
    "`_canonicalize_cost_record` event listener stores the normalized value on every "
    "CostRecord insert/update (core/database.py:2558-2566), and report_engine.py:1758 gates "
    "the whole rate projection on `projection_currency is not None` - an unknown currency "
    "blocks the projection instead of fabricating a converted figure.",
    None,
)

R["INV34-001460"] = (
    VC,
    "`if b.hd:` (core/engineering/bridge.py:91) guards the closure-azimuth computation "
    "`closure_azi = round(math.degrees(math.atan2(b.east, b.north)) % 360, 3)` (92).  `b` is "
    "the second TrajectoryPoint returned by TrajectoryEngine.calculate, and `hd` is a derived "
    "non-negative float of that dataclass (`hd: float = 0.0`, core/engineering/core.py:90; "
    "computed as `hd = math.sqrt(north**2 + east**2)`, 289) - it can never be None, so the "
    "truthiness test is exactly `hd != 0`.  When hd == 0 the projected station sits on the "
    "survey origin axis and atan2(0, 0) would fabricate a 0° closure azimuth by IEEE "
    "convention, not by measurement; leaving `closure_azi = None` (90) preserves 'no closure "
    "direction is defined' for that degenerate geometry, which is the unknown-preserving "
    "choice.  The result object carries both the values and the None "
    "(values['closure_azimuth_deg'], 100-104), and the two documented consumers are the "
    "acceptance calculator scripts docs/audits/2026-09-08-ddr/evidence/real-user-acceptance/"
    "supplemental-calculators.py:35,54 which assert on the numeric fields of a non-degenerate "
    "pair.  Sibling guard in the same function: `if d_md > 0 and b.dls:` (94) is the same "
    "non-negative-derived-float pattern.",
    None,
)

R["INV34-001477"] = (
    VC,
    "`MudLedgerEngine.calculate_closing(opening, received, used, returned=0, adjusted=0)` "
    "(core/engineering/core.py:630-631) computes `opening + received + adjusted - used - "
    "returned` under the class contract 'Mud Chemical Ledger with Opening(day+1)=Closing(day) "
    "enforcement' (627) and `next_day_opening(closing)` chains the result into the next day "
    "(634).  The two flagged defaults are the additive identity of that formula: a ledger day "
    "with no returns and no adjustments closes to exactly the value the formula gives when "
    "those terms are absent, so 0 here is the *physical* 'nothing moved' quantity, not a "
    "substitute for an unknown - the volume fields of a mud ledger are quantities that are "
    "zero when nothing moved, and the repository's zero-semantics contract explicitly "
    "preserves such zeros (tests/test_inventory_zero_semantics.py asserts the same "
    "distinction for bulk movements).  Consumers: tests/test_p0_engineering_core.py:141-169 "
    "(MudLedgerEngineTests) pins next_day_opening/build_history, and "
    "core/repositories/logistics_repository.py imports the engine for ledger validation; no "
    "caller passes None-with-a-0-fallback through this path.",
    None,
)

R["INV34-001478"] = dup(
    "INV34-001477",
    "the identical `calculate_closing` signature default at core/engineering/core.py:630 "
    "(second register record, same file/line/symbol)",
    "the zero defaults are the additive identity of the mud-ledger closing formula, pinned by "
    "MudLedgerEngineTests and consumed through the logistics repository",
)

R["INV34-001482"] = (
    VC,
    "`vs_azimuth: float = 0.0` (core/engineering/core.py:338) is the reference azimuth the "
    "vertical-section projection is measured against, documented in the method's own "
    "docstring: 'VS is recomputed from the projected North/East and vs_azimuth (not copied "
    "from the last station)' (340-342).  0.0 is the north-referenced VS convention, not a "
    "substituted measurement, and the recomputation comment exists precisely so no stale "
    "planned VS is copied forward.  The AI tool registry records the same assumption "
    "explicitly ('VS azimuth 0 default', core/ai_tools.py:190) and the only other caller, "
    "tests/test_engineering_ground_truth.py:105, passes vs_azimuth=0 explicitly.  The value "
    "is a direction convention for a derived projection - it never replaces a missing "
    "planned/actual depth, hour or cost.",
    None,
)

R["INV34-001497"] = (
    VC,
    "`return hhp / bit_area if bit_area else 0` (core/engineering/core.py:415) closes "
    "`calculate_hsi`, whose precondition already excludes the falsy case: `if not "
    "flow_rate_gpm or not pressure_drop_psi or not bit_size_in: raise MissingInputError` "
    "(410-411), so bit_size_in != 0 on every path that reaches 413 and `bit_area = math.pi/4 "
    "* bit_size_in * bit_size_in` (413) is strictly positive (sign is squared away).  The "
    "`else 0` branch is therefore unreachable defensive code, and an unreachable branch is "
    "not a behaviour to adjudicate - the value actually returned is hhp / bit_area, with "
    "missing inputs refused loudly instead of rendered as 0 HSI.  The single production "
    "caller is the w3 report widget (tabs/w3_drilling_report.py calculate_hsi, whose inputs "
    "are QDoubleSpinBox values - finite floats by construction), and batch-002 already "
    "recorded that caller's log-and-leave-unset handling of engine failures.",
    None,
)

R["INV34-001502"] = misfire(
    "`if not (0 <= inc_f <= 180):` (core/engineering/core.py:168) is a chained range "
    "comparison over a *required* survey inclination, not a truthiness test: the value was "
    "raised as MissingInputError when missing (140-141), converted with a typed error "
    "(147-150) and already rejected when non-finite (`if not all(math.isfinite(value) for "
    "value in (md_f, inc_f, azi_f))`, 154-156) before this line.  The R-TRUTH-UNKNOWN family "
    "targets bare truthiness on a value whose optionality is unproven; here the range test "
    "itself is the validation that makes the engine refuse out-of-domain input "
    "(EngineeringError 'Inclination out of range [0,180]', 169).  Nothing about the construct "
    "matches the rule's semantic.",
)

R["INV34-001508"] = (
    VC,
    "`except (TypeError, ValueError): continue` inside `BitEngine.calculate_tfa` "
    "(core/engineering/core.py:398-402) skips a nozzle token that is not a number while "
    "summing pi/4*(n/32)^2.  The skip cannot fabricate a measurement and cannot lose one: a "
    "non-numeric token has no truthful area, the numeric subset is summed as-is, and the "
    "engine refuses the empty result (`if tfa == 0: raise EngineeringError(\"TFA calculated "
    "as 0\")`, 403-404) instead of returning a fabricated 0 in^2.  The production producers "
    "cannot emit non-numeric tokens in the first place: the w3 nozzle table builds "
    "`{'size_32nd': size_widget.value(), 'quantity': qty_widget.value()}` from "
    "QDoubleSpinBoxes (tabs/w3_drilling_report.py:695-707, finite floats by construction), "
    "the managers facade `DrillingManager.calculate_tfa` maps that data through and converts "
    "any engine failure to None with the documented 'not entered, not a measured 0' contract "
    "(core/managers.py:381-400), and the w13 calculator pre-filters `[s for s in nozzle_sizes "
    "if s > 0]` (tabs/w13_Engineering_Calculator.py:64).  The handler is typed (no bare "
    "except) and the remaining caller (core/ai_tools.py:192-197) reports "
    "MISSING_INPUT/success explicitly around the same engine.",
    "when a *mixed* list of parseable and non-parseable tokens reaches the engine the "
    "returned TFA silently covers the parseable subset; no in-repo producer can emit that "
    "input today (all three producers are numeric by construction), so this is recorded as "
    "an observation, not patched.",
)

R["INV34-006473"] = (
    VC,
    "`naive_footage, naive_hours = session.query(func.sum(...), func.sum(...)).filter(...)"
    ".one()` (tests/test_engineering_data_semantics.py:150-153) is the *deliberately wrong* "
    "half of a documentation test: the docstring states the hazard ('the naive SUM(footage)/"
    "SUM(hours) is wrong because SQL SUM skips the NULL footage while still counting that "
    "row's hours', 130-135) and the assertions encode it - naive 9.0909 marked 'WRONG value' "
    "(155-157) versus the per-row-paired 20.0 marked 'CORRECT value' (158-185).  " + _AGG_ONE +
    ".  The test would fail if the aggregate semantics changed (a NULL-footage row dropping "
    "out of the denominator would move naive_hours off 11.0).  " + _TEST_LOCAL_DB + ".",
    None,
)

R["INV34-006512"] = (
    VC,
    "`fetch_row` closes with `.one()` on BulkMaterials filtered by (well_id, report_date, "
    "material_name) (tests/test_inventory_zero_semantics.py:80-89).  The identity it asserts "
    "is the writer's own upsert key: `save_bulk_material` locates the existing row by exactly "
    "well_id + report_date + report_id IS NULL + unit + material_name before updating "
    "(core/database.py:7359-7390), so one save per (well, date, material) is the storage "
    "contract and `.one()` is its enforcement - a second row would raise MultipleResultsFound "
    "and fail the test, which is the load-bearing direction.  All three call sites "
    "(111, 129, 146) read back the single Barite row of a fresh per-test in-memory DB "
    "(" + _TEST_LOCAL_DB + ") to assert explicit-zero semantics (State A/B/C of the module).",
    None,
)

R["INV34-006536"] = (
    VC,
    "`assert conn.execute(DrillingParameters.__table__.select()).one().well_id == a` "
    "(tests/test_ownership_parent_edits.py:106) verifies that a rejected startup did NOT "
    "repair the corrupted ownership link: the test seeds exactly one DrillingParameters row "
    "pointing at well `a` (the corruption scenario of 87-99), reopens with a fresh "
    "DatabaseManager, asserts `not reopened.initialize()` and the 'ownership conflict' "
    "diagnostic (103-104), then reads the raw table.  The seeded table has exactly one row, "
    "so `.one()` doubles as a no-silent-repair check - if startup had deleted, re-parented or "
    "duplicated rows, `.one()` would raise and fail the test.  The context is a plain "
    "engine.connect() read of the same file the test created (tmp_path), not a shared "
    "database.",
    None,
)

R["INV34-006552"] = dup(
    "INV34-006553",
    "the same `session.query(Well).first()` selection at tests/test_p0_well_identity.py:95 "
    "(test_report_identity_unique; the sibling test_section_identity_depth_range at :78)",
    "a test-local selection of the Default Well that `DatabaseManager.initialize()` seeds "
    "outside production before the test creates its own section/report on it",
)

R["INV34-006553"] = (
    VC,
    "`well = session.query(Well).first()` (tests/test_p0_well_identity.py:78, repeated at 95) "
    "runs immediately after `self.db.initialize()` in setUp (16-24) on a brand-new per-test "
    "SQLite file: `initialize()` calls `create_default_data()`, which - outside production "
    "environments, which tests are - seeds Company 'Default Company', Project 'Default "
    "Project' and Well 'Default Well' (core/database.py:3342-3430), and no other well exists "
    "in that database at this point.  `.first()` is therefore a deterministic selection of "
    "the single seeded well whose id the test then uses to create its own Section/Report "
    "(81-99); it is not a scoping shortcut over shared data, and tearDown closes the DB and "
    "removes the tmpdir (26-33).",
    None,
)

R["INV34-006594"] = dup(
    "INV34-006596",
    "the same `.first()`-after-atomic-save read-back at tests/test_real_oeoc_golden.py:696 "
    "(CasingReport; sibling CementReport at :701)",
    "the single row-table row written by save_imported_multi_tab_data_atomic for the seeded "
    "report, read back to verify the golden canonical JSON persisted verbatim",
)

R["INV34-006595"] = dup(
    "INV34-006596",
    "the same `.first()`-after-atomic-save read-back at tests/test_real_oeoc_golden.py:701 "
    "(CementReport)",
    "the single row-table row written by save_imported_multi_tab_data_atomic for the seeded "
    "report, read back to verify the golden materials JSON persisted verbatim",
)

R["INV34-006596"] = (
    VC,
    "`de = session.query(DownholeEquipment).filter_by(report_id=report_id).first()` "
    "(tests/test_real_oeoc_golden.py:691; CasingReport at 696, CementReport at 701) reads "
    "back the row-table row that `db.save_imported_multi_tab_data_atomic(well_id, report_id, "
    "dict(canonical))` (688) just wrote for the report the test itself seeded via "
    "_seed_well_report (687).  The atomic writer creates exactly one row-table row per "
    "report, so filter_by(report_id) + .first() is the deterministic read of the data this "
    "test wrote, and the assertion is load-bearing in both directions: a missing row would "
    "crash on `de.equipment_data_json` (None has no attribute) and a duplicated one would "
    "make the golden-content assertions on equipment_data_json[0]/casing[0]/materials[0] "
    "(692-704) test an arbitrary row.  " + _TEST_LOCAL_DB + ".",
    None,
)

R["INV34-006663"] = (
    VC,
    "`seed_well` opens `project = session.query(Project).first()` "
    "(tests/test_wellbore_discriminator_import.py:75; identical helper in "
    "tests/test_wellbore_schema_v3.py:80) after that module's `memory_manager()` fixture has "
    "created exactly one Company and one Project on a fresh StaticPool in-memory engine "
    "(49-68).  The selection is the deterministic single project of the test's own database, "
    "and the well it inserts (76-79) is the subject the suite's discriminator/scope "
    "assertions run against; the module docstring of the schema_v3 twin states the fixture "
    "mirrors tests/test_well_centric_acceptance.memory_manager so both suites build identical "
    "fixtures (51-55).  " + _TEST_LOCAL_DB + ".",
    None,
)

R["INV34-006707"] = dup(
    "INV34-006663",
    "the identical seed_well `session.query(Project).first()` at "
    "tests/test_wellbore_schema_v3.py:80",
    "the single Project of the fixture's fresh in-memory database, seeded by the same "
    "memory_manager idiom the module documents as a deliberate mirror of the acceptance "
    "fixture",
)

R["INV34-006837"] = dup(
    "INV34-000239",
    "the identical `return text or None` at core/cost_semantics.py:99 (second register "
    "record for normalize_currency, R-DEF-UNKNOWN/or-constant beside R-DEF-UNKNOWN/or-empty)",
    "blank input is the only falsy value after strip().upper(), so `text or None` implements "
    "the docstring's 'empty/blank currency is unknown, NOT silently USD' and every real code "
    "passes through",
)

R["INV34-007448"] = (
    VC,
    "`_to_number` (core/engineering/drill_pipe.py:106-122) is the repository's "
    "finite-boundary parser, and its record anchors the docstring that states the contract: "
    "'Parse a finite float, or None when the value is not a clean number... this does NOT "
    "judge the engineering domain (0/negative pass here); domain validity (OD>0 etc.) is "
    "enforced separately so we can distinguish not-a-number from a number outside the "
    "physical domain' (107-111).  The implementation matches it exactly: missing -> None via "
    "_is_missing, bool -> None ('never a measurement'), float() with typed failure -> None, "
    "`if not math.isfinite(number): return None` for NaN/inf/1e400 (117-121).  Consumers "
    "honour the None: `_to_inches` propagates it (128-131) and the component parser at 330 "
    "skips non-numeric raws, so an unparseable cell never becomes a 0-inch pipe segment.  "
    "This is the same boundary the batch-017 contract established for coerce_model_values, "
    "implemented correctly here.",
    None,
)

R["INV34-008502"] = dup(
    "INV34-006473",
    "the second line of the same naive-aggregate statement at "
    "tests/test_engineering_data_semantics.py:153 (the `.filter(...).one()` tail)",
    "the deliberately-wrong naive SUM/SUM of the weighted-ROP documentation test, whose "
    "'WRONG value' assertion is the hazard the test exists to record",
)

R["INV34-008508"] = dup(
    "INV34-006512",
    "the `.one()` tail of the same fetch_row statement at "
    "tests/test_inventory_zero_semantics.py:87",
    "the upsert-identity read of the single Barite row, enforcing the writer's "
    "(well_id, report_date, report_id IS NULL, unit, material_name) key",
)

R["INV34-009000"] = (
    VC,
    "`allocate_npt_cost(actual_cost, npt_hours, total_hours)` "
    "(core/cost_semantics.py:65-85) implements, and its docstring states, the "
    "unknown-preserving contract: 'Returns None (unknown) unless stored actual cost AND a "
    "positive total_hours exist - the same contract used by the report engine. No synthetic "
    "rig-day rate is ever introduced here' (68-71).  The body matches: None when "
    "actual_cost/total_hours/npt_hours is missing (79), None when total_hours <= 0 (81-82), "
    "EngineeringError when npt_hours leaves [0, total_hours] (83-84), and a "
    "require_number-wrapped proportional allocation otherwise.  The plan/actual direction is "
    "never inverted - the function only divides *stored actual* cost across *recorded* NPT "
    "time.  Consumers: report_engine.py:1425-1431 applies it only for the whole-well window "
    "('Whole-well costs have no proven attribution to a requested date window. Do not "
    "allocate the entire well's cost to a subset of logs', 1423-1424) and tabs/"
    "w12_Analysis.py:2281 surfaces the same None-as-unknown value.",
    None,
)

R["INV34-009493"] = (
    VC,
    "`forecast = Column(Text)` (core/db_models.py:209) is the DailyReport operation-forecast "
    "free-text field, not a numeric planned value: the canonical schema declares it text with "
    "an empty default and no measurement semantics (core/canonical_schema.py:171), and the "
    "DDR import boundary states the contract in code: '-> DailyReport.forecast (nullable; "
    "absent stays absent)' with the write guarded by `if dr.get(\"forecast\") in (None, \"\")` "
    "(core/ddr_import_service.py:501-505) - a report whose source page has no forecast keeps "
    "NULL instead of an empty-string stand-in, and no reader coerces it to a number.  The "
    "register stores no symbol for this record (a class-body column line), so its scope is "
    "the enclosing DailyReport model (191-213), read via AST; the neighbouring depth/rop/wob "
    "columns carry their own numeric-default records in other rule families and are not part "
    "of this flag.",
    None,
)

R["INV34-009587"] = (
    VC,
    "`self.baseline = deepcopy(self.reader())` (core/editor_state.py:22) establishes the "
    "edit baseline the module docstring defines: 'A baseline is established at editor "
    "creation/load, never at first Save All. Readers must describe persisted input, "
    "including raw invalid text, not selection or derived displays' (1-4).  The deepcopy is "
    "what makes the comparison in `dirty` meaningful - the baseline is an independent "
    "snapshot of the loaded persisted state (including its invalid raw text), so later "
    "reader() mutations cannot alias it - and `checkpoint()` re-runs it only at load and "
    "after a successful save (36-37).  No plan/actual value is involved: this is an edit "
    "session's own before-image, never coerced, never zero-filled.",
    None,
)

R["INV34-009588"] = (
    VC,
    "`return not self.read_only() and self.reader() != self.baseline` "
    "(core/editor_state.py:27) is the dirty test against the baseline established at 22 "
    "(same mechanism, adjudicated separately above).  It is an equality test over the "
    "reader's persisted-input snapshot - raw invalid text included, per the module "
    "docstring - so 'unchanged' means byte-equal to what was loaded and any user edit "
    "(including typing then un-typing invalid text) is detected; read_only gates the whole "
    "test.  save() consults it and re-checkpoints only after a successful save (29-37), so "
    "the baseline always denotes the last persisted state.  Nothing is defaulted or coerced "
    "in this comparison.",
    None,
)

R["INV34-010368"] = (
    VC,
    "`second = json.dumps(recalculate_from_snapshot(snap).values, sort_keys=True, "
    "default=str)` (tests/test_casing_persistence.py:139-140) is the second half of the "
    "determinism check batch-018 already adjudicated from its first half under INV34-010367: "
    "`first` (135-136) and `second` (139-140) serialize two recalculations of the same "
    "snapshot taken before and after five unrelated engine calls, and the test asserts "
    "`first == second` plus `INPUTS == before` (141-142).  " + _SNAP_SERIAL + "  No "
    "production data is serialized here - the persistence path for these runs is "
    "CasingCalculationRepository with its own converter "
    "(core/repositories/casing_repository.py), exactly as batch-018 recorded.",
    None,
)

R["INV34-010382"] = (
    VC,
    "`first = json.dumps(recalculate_from_snapshot(snap).values, sort_keys=True, default=str)` "
    "(tests/test_cement_persistence.py:145-146) opens the cement twin of the casing "
    "determinism test: `second` at 150-151 closes it and the test asserts `first == second` "
    "plus `INPUTS == before` (152-153) after five unrelated CementEngine.job_volumes calls "
    "(147-149).  " + _SNAP_SERIAL + "  The persistence path for cement jobs is the cement "
    "repository's own converter, not this comparison.",
    None,
)

R["INV34-010383"] = dup(
    "INV34-010382",
    "the second serialization of the same determinism check at "
    "tests/test_cement_persistence.py:150",
    "the closing half of the first/second comparison whose equality assertion is the "
    "determinism claim itself",
)

R["INV34-010506"] = (
    VC,
    "`json_str = json.dumps(report_dict, default=str, ensure_ascii=False)` "
    "(tests/test_ddr_regression.py:189) is the assertion target of "
    "`test_full_report_json_serializable` ('Full report must be JSON serializable', 173): "
    "the dict assembles the DDR report's counts, confidence distribution and canonical_json "
    "(180-188) and the test fails the moment dumps raises on any non-JSON-native value.  "
    "`default=str` is part of the *contract under test* - the export boundary must render "
    "non-native values rather than crash - and `len(json_str) > 100` (190) additionally "
    "asserts real content was produced.  This is a test of the serialization boundary, not "
    "the boundary itself; the production canonical JSON is produced by the DDR service with "
    "its own writer.",
    None,
)

R["INV34-010614"] = (
    VC,
    "`m.create_session()` (tests/test_import_to_selection_m25.py:37) is the last line of the "
    "module's `db()` fixture: after replacing engine/Session with a StaticPool in-memory "
    "binding and create_all (31-36), the fixture opens one session and returns the manager "
    "without keeping the handle.  " + _STATIC_POOL_SESSION + ".  The identical fixture idiom "
    "appears in tests/test_report_scope_metadata_m25.py:42, tests/test_w12_milestones_m25."
    "py:36, tests/test_w12_scope_leakage_m25.py:39, tests/test_w12_wellbore_scope.py:46, "
    "tests/test_wellbore_identity_conflict_m25.py:34 and tests/test_wellbore_scope_display."
    "py:54, and every test in these modules obtains its own sessions via "
    "db.create_session()/session_scope() for the actual work.  The Persian docstring on "
    "create_session ('use session_scope so tracking works') is about *production callers "
    "keeping* the session; a fixture warm-up that discards the handle has no work to track.",
    None,
)

R["INV34-011007"] = (
    VC,
    "`self.tmpdir = tempfile.mkdtemp()` (tests/test_p0_well_identity.py:17) is the secure "
    "temp-directory API (0700, unique name) holding the per-test SQLite file at "
    "self.db_path (18-20); tearDown closes the DatabaseManager and removes the tree with "
    "`shutil.rmtree(self.tmpdir, ignore_errors=True)` (26-33), so the artifact is cleaned on "
    "success and on failure alike.  The rule family's hazards - a world-readable temp file "
    "carrying secrets, or a temp file left behind - do not apply: the payload is a throwaway "
    "test database with seeded demo users, and cleanup is unconditional.",
    None,
)

R["INV34-011155"] = dup(
    "INV34-010614",
    "the identical discarded fixture session at tests/test_report_scope_metadata_m25.py:42",
    "the same db() fixture idiom: one SQL-less session opened on the fixture's own "
    "StaticPool engine and dropped, with per-test isolation",
)

R["INV34-011242"] = (
    VC,
    "`frozen = json.dumps(snap, sort_keys=True)` (tests/test_torque_drag_persistence."
    "py:127) freezes the engine-input snapshot so line 138 can assert `json.dumps(snap, "
    "sort_keys=True) == frozen` after five unrelated TorqueDragEngine.calculate calls - the "
    "register's own contract quote for this record is the test's comment: 'must give a "
    "byte-identical numeric result, and the engine must not mutate' (116-119).  Here "
    "json.dumps carries *no* default=str because build_snapshot output is JSON-native by "
    "construction, and the frozen-string equality IS the mutation check: any mutation of the "
    "snapshot (a recalculated field, a sorted-in-place survey) changes the string and fails "
    "the test.  The sibling assertions at 129-137 pin the byte-identical recomputation.  "
    "This is the strongest form of the family: the serialization exists to detect "
    "non-determinism, and weakening it would be the defect.",
    None,
)

R["INV34-011243"] = dup(
    "INV34-011242",
    "the `first = json.dumps(recalculate_from_snapshot(snap).values, ...)` line of the same "
    "test at tests/test_torque_drag_persistence.py:129",
    "one half of the byte-identical recomputation comparison whose frozen-snapshot anchor "
    "and quoted contract are recorded under INV34-011242",
)

R["INV34-011244"] = dup(
    "INV34-011242",
    "the `second = json.dumps(recalculate_from_snapshot(snap).values, ...)` line of the "
    "same test at tests/test_torque_drag_persistence.py:134",
    "the other half of the byte-identical recomputation comparison asserted at 137",
)

R["INV34-011245"] = dup(
    "INV34-011242",
    "the re-serialization assertion `assert json.dumps(snap, sort_keys=True) == frozen` at "
    "tests/test_torque_drag_persistence.py:138",
    "the mutation detector itself: the frozen string from line 127 compared against the "
    "snapshot after five unrelated engine calls",
)

R["INV34-011270"] = dup(
    "INV34-010614",
    "the identical discarded fixture session at tests/test_w12_milestones_m25.py:36",
    "the same db() fixture idiom: one SQL-less session opened on the fixture's own "
    "StaticPool engine and dropped, with per-test isolation",
)

R["INV34-011280"] = dup(
    "INV34-010614",
    "the identical discarded fixture session at tests/test_w12_scope_leakage_m25.py:39",
    "the same db() fixture idiom: one SQL-less session opened on the fixture's own "
    "StaticPool engine and dropped, with per-test isolation",
)

R["INV34-011306"] = dup(
    "INV34-010614",
    "the identical discarded fixture session at tests/test_w12_wellbore_scope.py:46",
    "the same db() fixture idiom: one SQL-less session opened on the fixture's own "
    "StaticPool engine and dropped, with per-test isolation",
)

R["INV34-011415"] = dup(
    "INV34-010614",
    "the identical discarded fixture session at tests/test_wellbore_identity_conflict_m25."
    "py:34",
    "the same db() fixture idiom: one SQL-less session opened on the fixture's own "
    "StaticPool engine and dropped, with per-test isolation",
)

R["INV34-011489"] = dup(
    "INV34-010614",
    "the identical discarded fixture session at tests/test_wellbore_scope_display.py:54",
    "the same db() fixture idiom: one SQL-less session opened on the fixture's own "
    "StaticPool engine and dropped, with per-test isolation",
)


# ----------------------------------------------------------------- observations (not defects)
NEW_FINDINGS: list[dict] = []

OBSERVATIONS: list[dict] = [
    {"record": "INV34-001508", "site": "core/engineering/core.py:398-404",
     "observation": ("`calculate_tfa` skips non-numeric nozzle tokens and sums the parseable "
                     "subset, refusing only the all-invalid case.  All three in-repo "
                     "producers are numeric by construction (QDoubleSpinBox values in w3, "
                     "the >0 pre-filter in w13, the managers facade), so the mixed-input "
                     "case is unreachable today; if a future producer can emit heterogeneous "
                     "tokens, decide explicitly whether the engine should refuse instead of "
                     "partially summing.  Recorded, not patched.")},
    {"record": "mission section 24 (ai_import_mapper)", "site": "core/ai_import_mapper.py:145-155",
     "observation": ("the non-finite `_to_float` question from the previous session's sweep "
                     "does not exist in this file: there is no `_to_float` in "
                     "core/ai_import_mapper.py, and its only float() is the proposal "
                     "confidence gate (`confidence = float(proposal.get(\"confidence\", 0))`, "
                     "bounded by `0 <= confidence <= 1` at 155, which rejects NaN and both "
                     "infinities).  No measurement value flows through a coercion here, so "
                     "nothing to patch; recorded so the question is closed with evidence "
                     "rather than silence.")},
    {"record": "fingerprint gate provenance", "site": "docs/audits/m34-evidence/m34-ledger.json",
     "observation": ("the 11 MB M34 fingerprint ledger is not tracked in the repository "
                     "(only its summary is committed), so batch-018's committed "
                     "fingerprint_proof numbers were produced against a file a fresh clone "
                     "does not have.  This batch's gate therefore derives fingerprints "
                     "ledger-free from the register's own recorded line text and the "
                     "hash-verified tree's AST segments under the same "
                     "path|kind|symbol|norm(expression)|ordinal contract, and uses the "
                     "ledger first when it is present locally.  If future batches need the "
                     "ledger's stored patterns, the ledger must either be tracked or its "
                     "patterns exported into the tracked summary - a tooling decision, "
                     "recorded here.")},
    {"record": "INV34-006552 / INV34-006553", "site": "tests/test_p0_well_identity.py:16-24",
     "observation": ("these tests depend on `DatabaseManager.initialize()` seeding a Default "
                     "Well outside production environments (create_default_data, "
                     "core/database.py:3342-3430).  That is today's contract and it holds in "
                     "every environment CI runs; if the demo seeding is ever made "
                     "production-optional in a way that reaches tests, these selections "
                     "should be replaced by explicit seeding in setUp rather than relying on "
                     "the default-data path.  Recorded, not patched.")},
]


# ----------------------------------------------------------------- helpers (018 architecture)
def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def m34_norm(text: str) -> str:
    """The M33/M34 'whitespace-collapsed single-line form' used by the fingerprint contract."""
    return re.sub(r"\s+", " ", text or "").strip()


def git_blob(rev: str, path: str) -> bytes:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git show {rev}:{path} failed: {out.stderr.decode()[:200]}")
    return out.stdout


def reconstruct_tree(path: str, entry: tuple[str, str, tuple[int, ...]]) -> bytes:
    """Rebuild the register's tree for `path` by reverse-applying the named hunks of a commit."""
    base, commit, hunk_ids = entry
    diff = subprocess.run(["git", "diff", base, commit, "--", path], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode("utf-8", "replace")
    parts = re.split(r"(?m)^(@@[^\n]*@@[^\n]*\n)", diff)
    header, hunks = parts[0], [(parts[i], parts[i + 1]) for i in range(1, len(parts), 2)]
    patch = header + "".join(hunks[i][0] + hunks[i][1] for i in hunk_ids)
    work = Path(tempfile.mkdtemp(prefix="m36-p6-019-"))
    target = work / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(git_blob(commit, path))
    patch_file = work / "reverse.patch"
    patch_file.write_text(patch, encoding="utf-8")
    run = subprocess.run(["git", "apply", "--reverse", "-p1", str(patch_file)], cwd=work,
                         capture_output=True)
    if run.returncode != 0:
        raise SystemExit(f"reconstruction of {path} failed: {run.stderr.decode()[:300]}")
    data = target.read_bytes()
    shutil.rmtree(work, ignore_errors=True)
    return data


_TREES: dict[tuple[str, str], tuple[list[str], bytes, str]] = {}


def provenance_tree(path: str, declared_sha: str) -> tuple[list[str], bytes, str]:
    """The tree the register's line numbers for `path` belong to, *proven* by its sha256."""
    key = (path, declared_sha)
    if key in _TREES:
        return _TREES[key]
    current = (ROOT / path).read_bytes()
    if hashlib.sha256(current).hexdigest() == declared_sha:
        result = (current.decode("utf-8", "replace").splitlines(), current,
                  "current tree: sha256(file) == the record's source_sha256")
    elif path in RECHECK_AGAINST:
        commit = RECHECK_AGAINST[path]
        data = git_blob(f"{commit}^", path)
        result = (data.decode("utf-8", "replace").splitlines(), data,
                  f"provenance tree = {commit}^ (the line numbers of this file moved in "
                  f"{commit}); sha256 == the record's source_sha256")
    elif path in RECONSTRUCT:
        data = reconstruct_tree(path, RECONSTRUCT[path])
        base, commit, hunk_ids = RECONSTRUCT[path]
        result = (data.decode("utf-8", "replace").splitlines(), data,
                  f"provenance tree = {commit} with hunk(s) {list(hunk_ids)} of "
                  f"`git diff {base} {commit} -- {path}` reversed; sha256 == the record's "
                  f"source_sha256")
    else:
        raise SystemExit(f"{path}: no provenance tree known for sha256 {declared_sha[:16]}...")
    if hashlib.sha256(result[1]).hexdigest() != declared_sha:
        raise SystemExit(f"{path}: provenance tree sha256 "
                         f"{hashlib.sha256(result[1]).hexdigest()[:16]}... != register's "
                         f"{declared_sha[:16]}...")
    _TREES[key] = result
    return result


_AST_CACHE: dict[str, object] = {}


def _parsed(source: str):
    key = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if key not in _AST_CACHE:
        _AST_CACHE[key] = ast.parse(source)
    return _AST_CACHE[key]


def symbol_body(source: str, symbol: str) -> tuple[int, int]:
    """Line range of the symbol named by a dotted path (owner-aware, unchanged since batch-009)."""
    tree = _parsed(source)
    parts = [p for p in (symbol or "").split(".") if p]
    if not parts:
        raise SystemExit(f"empty symbol {symbol!r}")
    index: dict[str, tuple[int, int]] = {}

    def visit(node, prefix):
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + [child.name]
                index[".".join(qualified)] = (child.lineno, child.end_lineno)
                visit(child, qualified)

    visit(tree, [])
    found = index.get(".".join(parts))
    if found is None:
        candidates = [n for n in ast.walk(tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.name == parts[-1]]
        if len(candidates) != 1:
            raise SystemExit(f"symbol {symbol!r} not resolvable ({len(candidates)} candidates)")
        found = (candidates[0].lineno, candidates[0].end_lineno)
    return found


def record_scope(source: str, symbol: str, line: int) -> tuple[int, int]:
    """Owner-aware scope for one record.

    A record the register leaves without a symbol (this batch's DailyReport column line,
    INV34-009493) is scoped to the enclosing class found by AST at the recorded line - never
    a nearest-line window.
    """
    if (symbol or "").strip():
        return symbol_body(source, symbol)
    tree = _parsed(source)
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.lineno <= line <= (node.end_lineno or node.lineno):
            if best is None or node.lineno >= best.lineno:
                best = node
    if best is None:
        return 1, len(source.splitlines())
    return best.lineno, best.end_lineno


def scope_symbol_forms(source: str, line: int) -> list[str]:
    """The qualified names of the classes/functions enclosing `line`, innermost first."""
    tree = _parsed(source)
    forms: list[str] = []

    def walk(node, prefix):
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + [child.name]
                if child.lineno <= line <= (child.end_lineno or child.lineno):
                    forms.append(".".join(qualified))
                    forms.append(child.name)
                walk(child, qualified)

    walk(tree, [])
    return forms


def ast_segment_forms(source: str, line: int, limit: int = 60) -> list[str]:
    """Normalized source segments of the AST nodes containing `line`, smallest span first."""
    tree = _parsed(source)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not hasattr(node, "lineno"):
            continue
        if not (node.lineno <= line <= (node.end_lineno or node.lineno)):
            continue
        segment = ast.get_source_segment(source, node)
        if not segment or len(segment) > 4000:
            continue
        normalized = m34_norm(segment)
        if normalized and normalized not in [f[1] for f in found]:
            found.append(((node.end_lineno or node.lineno) - node.lineno, normalized))
    found.sort(key=lambda item: (item[0], len(item[1])))
    return [text for _, text in found[:limit]]


def line_map(previous: list[str], current: list[str]) -> dict[int, int]:
    matcher = difflib.SequenceMatcher(None, previous, current, autojunk=False)
    mapping: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset + 1] = j1 + offset + 1
    return mapping


def text_matches(recorded: str, actual: str) -> bool:
    """Register text vs source text (register stores line.strip()[:160])."""
    expected, candidate = (recorded or "").strip(), (actual or "").strip()
    if len(expected) >= 160:
        return candidate[:len(expected)] == expected
    return candidate == expected


def fingerprint_proof(record: dict, m34: dict, tree_source: str) -> tuple[str, str] | str | None:
    """Re-derive the record's context_fingerprint from its identity (content, not lines).

    Contract: fingerprint = sha256("path|kind|symbol|norm(expression)|ordinal")
    (tools/m34/common.py).  Symbol forms: the symbol's last dotted component, the qualified
    symbol, the enclosing class/symbol found by AST for a symbol-less record, and - for the
    M32/M33-era symbol-less identities - the empty component itself.  Expression forms: the
    M34 ledger's `pattern` when the tracked ledger is present locally, the register's own
    recorded line text (whitespace-collapsed), and the statement's AST segments recovered
    from the hash-verified tree (the M34 sweep truncates its stored pattern to 200
    characters, so a multi-line statement can only reproduce from its own segments).
    Returns (symbol form, expression form) or None when no expression source exists at all.
    """
    symbol = record.get("symbol") or ""
    line = record["line"]
    forms: list[tuple[str, str]] = []
    for candidate in (symbol.split(".")[-1], symbol):
        if candidate and all(candidate != existing for _, existing in forms):
            forms.append(("short" if candidate == symbol.split(".")[-1] else "qualified",
                          candidate))
    for candidate in scope_symbol_forms(tree_source, line):
        if all(candidate != existing for _, existing in forms):
            forms.append((f"enclosing-scope:{candidate}", candidate))
    if not symbol and all("" != existing for _, existing in forms):
        forms.append(("empty-symbol", ""))

    expressions: list[tuple[str, str]] = []
    row = m34.get(record["id"]) if m34 else None
    if row and row.get("pattern"):
        expressions.append(("m34-pattern", m34_norm(row["pattern"])))
    recorded = m34_norm(record.get("current_source_line") or "")
    if recorded:
        expressions.append(("recorded-line", recorded))
    for segment in ast_segment_forms(tree_source, line):
        if all(segment != existing for _, existing in expressions):
            expressions.append(("ast-segment", segment))
    if not expressions:
        return None
    for expression_form, expression in expressions:
        for form, candidate in forms:
            payload = "|".join([record["file"], row.get("kind") if row else record.get("kind") or "",
                                candidate, expression, "0"])
            if hashlib.sha256(payload.encode("utf-8")).hexdigest() == record["context_fingerprint"]:
                return (form, expression_form)
    return "MISMATCH"


def check(batch: list[dict]) -> tuple[list[tuple[str, str, int, int, str]], dict]:
    problems: list[str] = []
    reanchored: list[tuple[str, str, int, int, str]] = []
    current_cache: dict[str, list[str]] = {}
    current_src: dict[str, str] = {}
    tree_src: dict[tuple[str, str], str] = {}
    maps: dict[tuple[str, str], dict[int, int]] = {}
    m34: dict[str, dict] = {}
    if LEDGER_AVAILABLE:
        ledger = json.loads((ROOT / FINGERPRINT_SOURCE).read_text(encoding="utf-8"))
        for row in list(ledger.get("carried_records", [])) + list(ledger.get("new_records", [])):
            m34[row["id"]] = row
    stats = {"fingerprints_checked": 0, "fingerprints_verified": 0,
             "fingerprints_without_evidence": [], "fingerprints_by_form": {},
             "fingerprints_by_expression_form": {},
             "fingerprints_not_reproduced_but_hash_anchored": [], "trees": {},
             "ledger_mode": "m34-ledger patterns used first" if LEDGER_AVAILABLE
             else "ledger-free: recorded-line + AST-segment expression forms (the 11 MB M34 "
                  "ledger is not tracked in the repository)"}

    for record in batch:
        path, line, expected = record["file"], record["line"], record.get("current_source_line")
        declared = record.get("source_sha256") or ""
        tree_lines, tree_bytes, provenance = provenance_tree(path, declared)
        stats["trees"].setdefault(path, provenance)
        source_key = (path, declared)
        if source_key not in tree_src:
            tree_src[source_key] = tree_bytes.decode("utf-8", "replace")
        if path not in current_src:
            src = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            current_src[path] = src
            current_cache[path] = src.splitlines()
        lines = current_cache[path]
        current_is_tree = hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == declared
        start, end = record_scope(current_src[path], record.get("symbol", ""), line)
        if current_is_tree:
            fstart, fend = start, end
        else:
            fstart, fend = record_scope(tree_src[source_key], record.get("symbol", ""), line)

        proof = fingerprint_proof(record, m34, tree_src[source_key])
        if proof is None:
            stats["fingerprints_without_evidence"].append(record["id"])
        else:
            stats["fingerprints_checked"] += 1
            stats["fingerprints_verified"] += int(proof != "MISMATCH")
            if proof == "MISMATCH":
                form = "MISMATCH"
            else:
                form, expression_form = proof
                stats["fingerprints_by_expression_form"][expression_form] = \
                    stats["fingerprints_by_expression_form"].get(expression_form, 0) + 1
            stats["fingerprints_by_form"][form] = stats["fingerprints_by_form"].get(form, 0) + 1

        hash_anchored = 0 < line <= len(tree_lines) \
            and text_matches(expected, tree_lines[line - 1]) and fstart <= line <= fend
        if proof == "MISMATCH":
            if hash_anchored:
                stats["fingerprints_not_reproduced_but_hash_anchored"].append(record["id"])
            else:
                problems.append(f"{record['id']}: context_fingerprint does not reproduce from "
                                f"its identity (any symbol form, any expression form) and the "
                                f"record is not hash-anchored")
                continue
        if proof is None and not current_is_tree:
            problems.append(f"{record['id']}: no fingerprint evidence and the file is not the "
                            f"recorded tree - refusing to adjudicate by line number alone")
            continue

        if 0 < line <= len(lines) and text_matches(expected, lines[line - 1]) \
                and start <= line <= end:
            continue

        if not (0 < line <= len(tree_lines)) or not text_matches(expected, tree_lines[line - 1]):
            got = tree_lines[line - 1].strip() if 0 < line <= len(tree_lines) else "<beyond EOF>"
            problems.append(f"{record['id']}: {path}:{line} is {got[:60]!r} in the provenance "
                            f"tree, register recorded {expected[:60]!r}")
            continue

        map_key = (path, declared)
        if map_key not in maps:
            maps[map_key] = line_map(tree_lines, lines)
        new_line = maps[map_key].get(line)
        if new_line is None or not text_matches(expected, lines[new_line - 1]) \
                or not (start <= new_line <= end):
            problems.append(f"{record['id']}: re-anchor {path}:{line} -> {new_line} failed "
                            f"(symbol {record.get('symbol')!r} spans {start}-{end})")
            continue
        reanchored.append((record["id"], path, line, new_line, provenance))

    if problems:
        print("STALE / UNVERIFIED EVIDENCE - not applying:")
        for problem in problems:
            print("  ", problem)
        raise SystemExit(2)
    return reanchored, stats


def record_head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode().strip()


def main() -> int:
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    batch = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(batch) != len(R):
        print(f"batch has {len(batch)} records, adjudications: {len(R)}")
        print("missing:", sorted({r["id"] for r in batch} - set(R)))
        print("extra:", sorted(set(R) - {r["id"] for r in batch}))
        return 1

    reanchored, stats = check(batch)

    counts: dict[str, int] = {}
    for record in batch:
        classification = R[record["id"]][0]
        counts[classification] = counts.get(classification, 0) + 1
    classes: dict[str, int] = {}
    for record in batch:
        classes[record["p6_class"]] = classes.get(record["p6_class"], 0) + 1

    items = [{
        "id": record["id"], "file": record["file"], "line": record["line"],
        "symbol": record.get("symbol"), "rule": record.get("rule"), "kind": record.get("kind"),
        "register_line_text": record.get("current_source_line"),
        "classification": R[record["id"]][0], "evidence": R[record["id"]][1],
        "remaining_question": R[record["id"]][2],
        "defect": R[record["id"]][0] == DEF,
        "test": None, "commit": None,
    } for record in batch]

    by_file: dict[str, int] = {}
    for item in items:
        by_file[item["file"]] = by_file.get(item["file"], 0) + 1

    # sibling populations, recomputed from the register (not hardcoded)
    rule_totals: dict[str, int] = {}
    for r in register["records"]:
        rule_totals[r["rule"]] = rule_totals.get(r["rule"], 0) + 1
    open_by_rule: dict[str, int] = {}
    for r in register["records"]:
        if r["classification"] == "OPEN":
            open_by_rule[r["rule"]] = open_by_rule.get(r["rule"], 0) + 1

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": ("phase-2 classes B+C (persistence/identity surfaces + core semantics): "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))
                  + " - the actual-vs-plan scalar comparator and its engine callers, the cache "
                    "TTL accessor, the shared table-widget default, the currency normalizer "
                    "pair, the trajectory/bridged-calculator truthiness sites, the mud-ledger "
                    "closing helper, the two engineering-ground-truth weighted-ROP "
                    "assertions, the test seeders/teardowns on fresh self-created databases, "
                    "the deterministic-snapshot test idiom (casing/cement/torque-drag) and "
                    "the seven discarded-fixture-session records"),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "records_by_file": dict(sorted(by_file.items())),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [],
        "new_findings": NEW_FINDINGS,
        "observations": OBSERVATIONS,
        "sibling_search": {
            "target": ("the batch's own families as populations: the numeric parameter "
                       "default, the `or` container/constant default, the bare truthiness "
                       "test, the typed skip-continue handler, the `.one()`/`.first()` "
                       "selection in tests, the snapshot-serialize comparison, the "
                       "session-lifecycle fixture, and the plan/baseline columns"),
            "method": ("populations recomputed from the register at run time (rule_totals / "
                       "open_by_rule below), and every flagged construct read at its own "
                       "site with its consumer traced; the two R-SEL-UNPROVEN multi-record "
                       "statements, the or-constant/or-empty pair on normalize_currency, "
                       "the calculate_closing pair and the four torque-drag serializations "
                       "are cross-linked as DUPLICATE records to their anchor so no site is "
                       "adjudicated twice under different evidence"),
            "counts": {
                "register_records_total": len(register["records"]),
                "rule_totals": rule_totals,
                "open_by_rule_before_this_batch": open_by_rule,
            },
            "findings": [
                {"site": "core/actual_vs_plan.compare + tolerance default",
                 "status": ("optional_number/None propagation keeps an unknown planned or "
                            "actual as status 'unavailable' with variance None; the w10 "
                            "consumer branches on None before any numeric use")},
                {"site": "core/engineering numeric defaults (calculate_closing, "
                         "project_ahead vs_azimuth)",
                 "status": ("both defaults are physical identity elements (nothing moved / "
                            "north-referenced VS convention), pinned by "
                            "MudLedgerEngineTests and the ground-truth test")},
                {"site": "core/engineering finite boundary",
                 "status": ("drill_pipe._to_number implements the batch-017 finite-boundary "
                            "contract exactly (missing/bool/non-finite -> None); "
                            "TrajectoryEngine._validate_surveys rejects non-finite surveys "
                            "before its range test")},
                {"site": "test selections (.one()/.first())",
                 "status": ("every selection is over a database the test itself created in "
                            "the same function - the seeded single row, the upsert-identity "
                            "row, the aggregate's contractual single row, or the "
                            "initialize()-seeded Default Well - and each is load-bearing in "
                            "the failing direction")},
                {"site": "deterministic-snapshot test idiom (8 records)",
                 "status": ("json.dumps with sort_keys/default=str is the comparison "
                            "mechanism the tests assert with, not a persistence path; the "
                            "torque-drag frozen-snapshot variant is the mutation detector "
                            "itself")},
            ],
        },
        "tests": ("no production code was changed in this batch, so no new regression was "
                  "written and no mutation validation applies; the batch script ran with the "
                  "provenance and fingerprint gates active (see `staleness`) - all 45 "
                  "records were hash-anchored and re-identified against the current tree "
                  "before any classification was written"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "tools/m36/p6_batch_019.py",
                           "core/actual_vs_plan.py", "core/cache_manager.py",
                           "core/common_widgets.py", "core/cost_semantics.py",
                           "core/db_models.py", "core/editor_state.py",
                           "core/engineering/bridge.py", "core/engineering/core.py",
                           "core/engineering/drill_pipe.py",
                           "tests/test_casing_persistence.py",
                           "tests/test_cement_persistence.py",
                           "tests/test_ddr_regression.py",
                           "tests/test_engineering_data_semantics.py",
                           "tests/test_import_to_selection_m25.py",
                           "tests/test_inventory_zero_semantics.py",
                           "tests/test_ownership_parent_edits.py",
                           "tests/test_p0_well_identity.py",
                           "tests/test_real_oeoc_golden.py",
                           "tests/test_report_scope_metadata_m25.py",
                           "tests/test_torque_drag_persistence.py",
                           "tests/test_w12_milestones_m25.py",
                           "tests/test_w12_scope_leakage_m25.py",
                           "tests/test_w12_wellbore_scope.py",
                           "tests/test_wellbore_discriminator_import.py",
                           "tests/test_wellbore_identity_conflict_m25.py",
                           "tests/test_wellbore_schema_v3.py",
                           "tests/test_wellbore_scope_display.py"],
        "staleness": {
            "checked": len(batch), "stale": len(reanchored), "re_anchored": len(reanchored),
            "method": ("every record's declared source_sha256 selects the tree its line "
                       "number belongs to: for this batch every one of the 16 files is "
                       "byte-identical to the recorded tree (sha256(file) == "
                       "source_sha256), so all 45 records are anchored in the current tree "
                       "with no re-anchoring and no reconstruction.  The recorded text must "
                       "match at the recorded line inside the symbol's AST range (for the "
                       "one record the register leaves without a symbol - the "
                       "DailyReport.forecast column line - the scope is the enclosing class "
                       "found by AST).  In addition, every record's context fingerprint was "
                       "re-derived under the path|kind|symbol|norm(expression)|ordinal "
                       "contract (tools/m34/common.py), so the 'same site' claim rests on "
                       "content, not on line arithmetic."),
            "re_anchored_items": [
                {"id": i, "file": p, "register_line": a, "current_line": b, "tree": prov}
                for i, p, a, b, prov in reanchored],
            "provenance_trees": stats["trees"],
            "fingerprint_proof": {
                "checked": stats["fingerprints_checked"],
                "verified": stats["fingerprints_verified"],
                "records_without_a_reproducible_fingerprint": stats["fingerprints_without_evidence"],
                "records_without_a_reproducing_fingerprint_but_hash_anchored":
                    stats["fingerprints_not_reproduced_but_hash_anchored"],
                "symbol_forms_that_reproduced": stats["fingerprints_by_form"],
                "expression_forms_that_reproduced": stats["fingerprints_by_expression_form"],
                "method": stats["ledger_mode"] + ("  fingerprint = "
                          "sha256(\"path|kind|symbol|norm(expression)|ordinal\"); four "
                          "symbol forms are tried (the symbol's last component, the "
                          "qualified symbol, the enclosing AST scope for the symbol-less "
                          "column record, and the empty component for the M32/M33-era "
                          "symbol-less identity) and the expression forms are the M34 "
                          "ledger's pattern when the ledger is present locally, the "
                          "register's own recorded line text, and the statement's AST "
                          "segments from the hash-verified tree.")},
        },
        "method": ("all 45 records were read at their own sites in the hash-verified current "
                   "tree and the flagged construct was traced to its consumer before "
                   "classification: the actual-vs-plan comparator and its w10/tests "
                   "consumers, the cache TTL accessor and its expiry contract, the table "
                   "widget's layout default, the currency normalizer against the ORM "
                   "canonicalization listener and the projection gate, the bridge/trajectory "
                   "truthiness sites against the derived TrajectoryPoint fields and the "
                   "finite guard above them, the TFA typed-skip against all three numeric "
                   "producers and the refuse-on-empty guard, the mud-ledger identity "
                   "defaults against the ledger tests, the weighted-ROP documentation test "
                   "against its own WRONG/CORRECT assertions, the test selections against "
                   "the fixtures that create exactly the data they select, the "
                   "determinism/snapshot serializations against their frozen-string "
                   "contracts, and the seven fixture sessions against "
                   "DatabaseManager.create_session and the StaticPool sharing semantics.  "
                   "The deciding contract is quoted in `evidence` for every record; no line "
                   "of production or test code was changed."),
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"{BATCH}: {len(items)} records, {payload['sites']} sites, re-anchored "
          f"{len(reanchored)}, defects fixed {len(payload['defects_fixed'])}, fingerprints "
          f"{stats['fingerprints_verified']}/{stats['fingerprints_checked']} "
          f"({stats['ledger_mode']})")
    print("by classification:", payload["by_classification"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
