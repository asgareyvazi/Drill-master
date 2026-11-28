#!/usr/bin/env python3
"""Repeatable mutation run for M261-M290 (M270): the seven R-1 modules that no earlier catalogue mutated.

R-1 (M241/M262): anti-collision screening, bit performance, fishing, the trajectory contract wrapper, the well
control engine, and the mud-volume and casing persistence snapshots carried engineering claims that no mutant
had ever touched.  Each mutant introduces ONE realistic defect (a wrong sign, a dropped validity gate, unknown
read as zero, a mislabelled field, a broken reconstruction) in a scratch copy of the working tree and must be
KILLED by the listed tests.  Engine: ``tools/quality/mutation_m46.py``.  Run it on a green, COMMITTED tree;
an anchor that does not match exactly once is INVALID, never killed, and ``--only`` never gives complete=True.

Usage::

    python tools/quality/mutation_m261_m290.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.  IDs are stable: a mutant is never renamed; a retired one is removed and reported.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

AC = "core/engineering/engines/anti_collision.py"
BP = "core/engineering/engines/bit_performance.py"
FI = "core/engineering/engines/fishing.py"
TR = "core/engineering/engines/trajectory.py"
WC = "core/engineering/engines/well_control.py"
MV = "core/engineering/mud_volume_persistence.py"
CP = "core/engineering/casing_persistence.py"
QL = "core/qt_lifetime.py"
MGR = "core/managers.py"
MW = "main_window.py"
KD = "core/operations_dashboard.py"
KW = "tabs/dashboard_widgets.py"
WBM = "core/calculation_workbench.py"
CH = "core/calculation_history.py"
HT = "tabs/calculation_history_tab.py"
VS = "core/ddr_value_states.py"
VSD = "dialogs/ddr_value_states_dialog.py"
IL = "core/import_value_lineage.py"
ILD = "dialogs/import_review_dialog.py"

T270 = "tests/test_m270_r1_engine_contracts.py"          # added in M270 for the R-1 contracts
TAC = ["tests/test_anti_collision_engine.py", T270]
TBP = ["tests/test_weighted_rop.py", "tests/test_w3_bit_revolution_unknown_inputs.py",
       "tests/test_engineering_ground_truth.py", "tests/test_engineering_completion.py", T270]
TFI = ["tests/test_engineering_completion.py", "tests/test_m90_engine_qualification.py",
       "tests/test_engineering_non_finite_contract.py", "tests/test_w13_fishing_result_ui.py", T270]
TTR = ["tests/test_well_trajectory.py", "tests/test_engineering_independent_golden.py", T270]
TWC = ["tests/test_well_control_icp_fcp_consolidation.py", "tests/test_p0_engineering_core.py",
       "tests/test_engineering_ground_truth.py", "tests/test_engineering_independent_golden.py",
       "tests/test_well_control_kill_sheet.py", T270]
TMV = ["tests/test_mud_volume_persistence.py", "tests/test_mud_volume_cross_process.py", T270]
TKP = ["tests/test_m285_kpi_specifications.py", "tests/test_operations_dashboard.py", "tests/test_m53_dashboard.py"]
TWB = ["tests/test_m286_workbench_clone_archive.py"]
TVS = ["tests/test_m272_ddr_value_states.py"]
TIL = ["tests/test_m273_import_value_lineage.py"]
TAZ = ["tests/test_m286_m272_authorization.py"]
TLC = ["tests/test_m265_window_routes.py"]                # M268: window lifecycle (Qt, real MainWindow)
TCP = ["tests/test_casing_persistence.py", "tests/test_casing_absent_load_semantics.py",
       "tests/test_casing_cross_process.py", T270]

MUTANTS = [
    # ------------------------------------------------------------------ anti-collision screening (no ISCWSA)
    Mutant("AC-negative-md-accepted", AC,
           "            if values[\"md\"] < 0:\n",
           "            if values[\"md\"] < -1e300:\n", TAC,
           "a negative measured depth is accepted as a survey station"),
    Mutant("AC-non-increasing-md-accepted", AC,
           "            if previous_md is not None and values[\"md\"] <= previous_md:\n",
           "            if previous_md is not None and values[\"md\"] < previous_md:\n", TAC,
           "a repeated MD (zero-length interval) is accepted and later divides by a zero span"),
    Mutant("AC-negative-sigma-accepted", AC,
           "                    if sigma < 0:\n",
           "                    if sigma < -1e300:\n", TAC,
           "a negative 1-sigma uncertainty is accepted"),
    Mutant("AC-sigma-added-linearly", AC,
           "            axis: math.sqrt(reference[f\"sigma_{axis}\"] ** 2 + offset[f\"sigma_{axis}\"] ** 2)\n",
           "            axis: reference[f\"sigma_{axis}\"] + offset[f\"sigma_{axis}\"]\n", TAC,
           "the two wells' 1-sigma values are added linearly instead of root-sum-square"),
    Mutant("AC-partial-sigma-used", AC,
           "        if not all(f\"sigma_{axis}\" in reference and f\"sigma_{axis}\" in offset "
           "for axis in AntiCollisionEngine._SIGMA_AXES):\n",
           "        if not any(f\"sigma_{axis}\" in reference and f\"sigma_{axis}\" in offset "
           "for axis in AntiCollisionEngine._SIGMA_AXES):\n", TAC,
           "a separation factor is computed when only some uncertainty axes were supplied"),
    Mutant("AC-one-radius-gives-clearance", AC,
           "        if \"wellbore_radius\" in reference and \"wellbore_radius\" in offset:\n",
           "        if \"wellbore_radius\" in reference or \"wellbore_radius\" in offset:\n", TAC,
           "clearance is computed when only one well's radius is known"),
    Mutant("AC-clearance-adds-radii", AC,
           "            clearance = distance - radii\n",
           "            clearance = distance + radii\n", TAC,
           "clearance adds the wellbore radii to the centreline distance instead of subtracting them"),
    Mutant("AC-vertical-separation-dropped", AC,
           "        distance = math.sqrt(dn * dn + de * de + dtvd * dtvd)\n",
           "        distance = math.sqrt(dn * dn + de * de)\n", TAC,
           "the 3D separation ignores the vertical component (lateral distance reported as 3D)"),
    Mutant("AC-no-overlap-accepted", AC,
           "        if end < start:\n",
           "        if end < start - 1e300:\n", TAC,
           "two trajectories with no common MD interval are screened anyway"),
    Mutant("AC-threshold-zero-accepted", AC,
           "            if threshold is not None and threshold <= 0:\n",
           "            if threshold is not None and threshold < 0:\n", TAC,
           "a zero collision threshold is accepted (every station is then 'clear')"),
    Mutant("AC-threshold-touch-not-alert", AC,
           "                    if margin <= 0:\n",
           "                    if margin < 0:\n", TAC,
           "a station exactly at the collision threshold is not reported as an event"),
    Mutant("AC-claims-iscwsa", AC,
           "                    \"iscwsa_compliant\": False,\n",
           "                    \"iscwsa_compliant\": True,\n", TAC,
           "the screening result claims ISCWSA compliance (P19 is not approved)"),
    # ------------------------------------------------------------------ bit performance
    Mutant("BP-revolutions-uses-max-rpm", BP,
           "            average_rpm = (low + high) / 2.0\n",
           "            average_rpm = high\n", TBP,
           "bit revolutions use the maximum RPM instead of the mean of min and max"),
    Mutant("BP-revolutions-max-below-min-accepted", BP,
           "            if high < low:\n",
           "            if high < low - 1e300:\n", TBP,
           "an RPM maximum below the minimum is accepted"),
    Mutant("BP-weighted-rop-zero-when-undefined", BP,
           "        if valid == 0 or total_hours <= 0:\n            return ok(\n                None,\n",
           "        if valid == 0 or total_hours <= 0:\n            return ok(\n                0.0,\n", TBP,
           "weighted ROP with no valid pairs reports 0 m/hr instead of undefined"),
    Mutant("BP-weighted-rop-excluded-rows-hidden", BP,
           "        excluded = considered - valid\n",
           "        excluded = 0\n", TBP,
           "rows dropped from weighted ROP (incomplete or invalid pairs) are no longer counted or warned about"),
    Mutant("BP-dexp-wob-in-klbf", BP,
           "            denominator = math.log10((12.0 * wob) / (1000000.0 * d))\n",
           "            denominator = math.log10((12.0 * wob) / (1000.0 * d))\n", TBP,
           "the d-exponent denominator uses the klbf constant with WOB given in lbf"),
    Mutant("BP-cost-rig-day-not-hourly", BP,
           "            rig_hour = rig_day / 24.0\n",
           "            rig_hour = rig_day\n", TBP,
           "cost per foot multiplies trip hours by the daily rig rate"),
    Mutant("BP-cost-rotating-hours-ignored", BP,
           "                total_cost = rig_hour * (trip + rot) + bit\n",
           "                total_cost = rig_hour * trip + bit\n", TBP,
           "the full-cycle cost per foot ignores the supplied rotating hours"),
    # ------------------------------------------------------------------ fishing (screening only)
    Mutant("FI-weight-id-not-subtracted", FI,
           "            w = STEEL_WEIGHT_CONST * (od ** 2 - id_ ** 2)\n",
           "            w = STEEL_WEIGHT_CONST * od ** 2\n", TFI,
           "plain-end weight ignores the bore"),
    Mutant("FI-weight-id-ge-od-accepted", FI,
           "            if id_ >= od:\n",
           "            if id_ > od:\n", TFI,
           "an ID equal to the OD (zero wall) yields a zero-weight pipe instead of a refusal"),
    Mutant("FI-free-point-zero-pull-accepted", FI,
           "            if pull <= 0:\n                raise EngineeringError(\"pull_lbf must be > 0 (stretch under pull)\")\n",
           "            if pull < 0:\n                raise EngineeringError(\"pull_lbf must be > 0 (stretch under pull)\")\n", TFI,
           "a zero differential pull is accepted (division by zero / infinite free point)"),
    Mutant("FI-free-point-inverted", FI,
           "            fp = FREE_POINT_CONST * dl * w / pull\n",
           "            fp = FREE_POINT_CONST * dl * pull / w\n", TFI,
           "free point swaps pipe weight and pull"),
    Mutant("FI-stretch-buoyancy-sign", FI,
           "            stretch = length ** 2 * (STRETCH_A - STRETCH_B * mw) / STRETCH_DENOM\n",
           "            stretch = length ** 2 * (STRETCH_A + STRETCH_B * mw) / STRETCH_DENOM\n", TFI,
           "heavier mud increases the free-hanging stretch"),
    Mutant("FI-stretch-linear-in-length", FI,
           "            stretch = length ** 2 * (STRETCH_A - STRETCH_B * mw) / STRETCH_DENOM\n",
           "            stretch = length * (STRETCH_A - STRETCH_B * mw) / STRETCH_DENOM\n", TFI,
           "the D81 defect: stretch under own weight taken as linear in length"),
    Mutant("FI-jar-up-subtracts-overpull", FI,
           "            up = buoyed + op\n",
           "            up = buoyed - op\n", TFI,
           "the upward jar force subtracts the overpull"),
    Mutant("FI-overshot-zero-clearance-ok", FI,
           "            compatible = 0.0 < clearance < 0.5\n",
           "            compatible = 0.0 <= clearance < 0.5\n", TFI,
           "an overshot with no clearance over the fish is reported compatible"),
    # ------------------------------------------------------------------ trajectory contract wrapper
    Mutant("TR-vs-azimuth-not-passed", TR,
           "        points = TrajectoryEngine.calculate(surveys, vs_azimuth=vs_azimuth, dls_unit=dls_unit)\n",
           "        points = TrajectoryEngine.calculate(surveys, vs_azimuth=0.0, dls_unit=dls_unit)\n", TTR,
           "the vertical-section azimuth chosen by the user is dropped (VS always toward north)"),
    Mutant("TR-dls-unit-not-passed", TR,
           "        points = TrajectoryEngine.calculate(surveys, vs_azimuth=vs_azimuth, dls_unit=dls_unit)\n",
           "        points = TrajectoryEngine.calculate(surveys, vs_azimuth=vs_azimuth)\n", TTR,
           "a deg/100ft request silently returns deg/30m dogleg severity"),
    Mutant("TR-north-east-swapped", TR,
           "                \"north\": p.north,\n                \"east\": p.east,\n",
           "                \"north\": p.east,\n                \"east\": p.north,\n", TTR,
           "northing and easting are exchanged in the wrapper output"),
    Mutant("TR-hd-reports-vs", TR,
           "                \"hd\": p.hd,\n",
           "                \"hd\": p.vs,\n", TTR,
           "horizontal displacement is reported as the vertical section"),
    # ------------------------------------------------------------------ well control engine
    Mutant("WC-kill-mw-sidpp-subtracted", WC,
           "        return mw + sidpp / (PSI_PER_PPG_FT * tvd)\n",
           "        return mw - sidpp / (PSI_PER_PPG_FT * tvd)\n", TWC,
           "kill mud weight subtracts the SIDPP increment"),
    Mutant("WC-kill-mw-zero-tvd-accepted", WC,
           "        if tvd <= 0:\n            raise EngineeringError(\"TVD must be > 0\")\n"
           "        return mw + sidpp",
           "        if tvd < 0:\n            raise EngineeringError(\"TVD must be > 0\")\n"
           "        return mw + sidpp", TWC,
           "a zero TVD is accepted (division by zero)"),
    Mutant("WC-fcp-ratio-inverted", WC,
           "        return spr * (kmw / mw)\n",
           "        return spr * (mw / kmw)\n", TWC,
           "final circulating pressure scales the slow-rate pressure by MW/KMW"),
    Mutant("WC-icp-sidpp-dropped", WC,
           "        return spr + sidpp\n",
           "        return spr\n", TWC,
           "initial circulating pressure omits the SIDPP"),
    Mutant("WC-maasp-negative-allowed", WC,
           "        if frac < mw:\n",
           "        if frac < mw - 1e300:\n", TWC,
           "a fracture EMW below the current mud weight yields a negative MAASP instead of a refusal"),
    Mutant("WC-lot-ignores-mud-head", WC,
           "            return current_mw_ppg + pressure / (PSI_PER_PPG_FT * shoe_tvd_ft)\n",
           "            return pressure / (PSI_PER_PPG_FT * shoe_tvd_ft)\n", TWC,
           "a LOT surface pressure is converted to frac EMW without the mud hydrostatic already acting"),
    Mutant("WC-trip-margin-sign", WC,
           "            tm_ppg = mw - form_emw\n",
           "            tm_ppg = form_emw - mw\n", TWC,
           "trip margin is reported as pore EMW minus mud weight (overbalance shown as underbalance)"),
    # ------------------------------------------------------------------ M285: KPI specifications
    Mutant("KP-spec-not-attached", KD,
           "                   as_of if as_of is not None else latest, note, drilldown, KPI_SPECS[key])\n",
           "                   as_of if as_of is not None else latest, note, drilldown, None)\n", TKP,
           "built KPIs no longer carry their specification (the card shows no window, scope, method or rule)"),
    Mutant("KP-npt-cost-not-labelled-estimate", KD,
           "                     method=\"ESTIMATE: all actual cost of the well x NPT hours / all logged hours\",\n",
           "                     method=\"all actual cost of the well x NPT hours / all logged hours\",\n", TKP,
           "the allocated NPT cost is no longer labelled as an estimate"),
    Mutant("KP-cost-per-metre-scope-widened", KD,
           "    \"cost_per_metre\": dict(window=\"all dates\", scope=\"single well only\",\n",
           "    \"cost_per_metre\": dict(window=\"all dates\", scope=_SCOPE,\n", TKP,
           "cost per metre claims the multi-well filter scope although it is computed for one well only"),
    Mutant("KP-tooltip-drops-spec", KW,
           "        spec = getattr(kpi, \"spec\", None) or {}\n",
           "        spec = {}\n", TKP,
           "the KPI card tooltip omits window, scope, method, missing behaviour and counting rule"),
    # ------------------------------------------------------------------ M272: DDR value states
    Mutant("VS-missing-state-with-value", VS,
           "    if state in MISSING_STATES and value is not None:\n",
           "    if False:\n", TVS,
           "UNKNOWN / N/A / NOT_REPORTED is accepted for a field that holds a number"),
    Mutant("VS-zero-accepts-nonzero", VS,
           "    if state == ZERO and number != 0:\n",
           "    if False:\n", TVS,
           "ZERO is accepted for a non-zero (or empty) field"),
    Mutant("VS-reported-accepts-zero", VS,
           "    if state == REPORTED and (number is None or number == 0):\n",
           "    if state == REPORTED and number is None:\n", TVS,
           "a stored 0 is recorded as REPORTED instead of ZERO"),
    Mutant("VS-calculated-without-method", VS,
           "        if not str(method or \"\").strip():\n",
           "        if False:\n", TVS,
           "a CALCULATED value is accepted without its method"),
    Mutant("VS-first-event-wins", VS,
           "        latest[row.field] = row                            # ordered by id: the last event wins\n",
           "        latest.setdefault(row.field, row)\n", TVS,
           "the first recorded state decides; a correction is never shown"),
    Mutant("VS-inconsistency-hidden", VS,
           "        out[field] = {\"label\": label, \"value\": value, \"state\": INCONSISTENT if why else row.state,\n",
           "        out[field] = {\"label\": label, \"value\": value, \"state\": row.state,\n", TVS,
           "a value edited after its state was recorded still shows the old state"),
    Mutant("VS-non-finite-accepted", VS,
           "    if not math.isfinite(number):\n        raise ValueStateError(f\"{raw!r} is not a finite number\")\n",
           "    if False:\n        raise ValueStateError(f\"{raw!r} is not a finite number\")\n", TVS,
           "typed NaN / infinity becomes a REPORTED value"),
    Mutant("VS-blank-is-zero", VS,
           "    \"\": NOT_REPORTED, \"nr\": NOT_REPORTED,",
           "    \"\": ZERO, \"nr\": NOT_REPORTED,", TVS,
           "a blank field is read as a real zero"),
    Mutant("VS-not-audited", VS,
           "        db._add_mandatory_audit(session, AUDIT_ACTION, \"daily_reports\", report_id, FIELDS[field],\n",
           "        (lambda *_a: None)(session, AUDIT_ACTION, \"daily_reports\", report_id, FIELDS[field],\n", TVS,
           "a value state is recorded without an audit record"),
    Mutant("VS-dialog-rerecords-implicit", VSD,
           "            if state != before or (state == vs.CALCULATED and method != (entry[\"method\"] or \"\")):\n",
           "            if True:\n", TVS,
           "saving the dialog records every implicit state as if the operator had chosen it"),
    Mutant("VS-unreadable-stored-is-empty", VS,
           "    number = _number(value)\n    if number is None:\n        return INCONSISTENT\n",
           "    number = _number(value)\n    if number is None:\n        return NOT_REPORTED\n", TVS,
           "a stored value that is not a finite number is called NOT_REPORTED (empty)"),
    Mutant("VS-comma-accepted", VS,
           "    if \",\" in raw:                                        # \"1,5\" (decimal comma) vs \"1,500\" (thousands): refuse\n",
           "    raw = raw.replace(\",\", \"\")\n    if False:\n", TVS,
           "a decimal comma is read as a thousands separator (1,5 becomes 15)"),
    Mutant("VS-workspace-ignores-inconsistent", "core/data_quality_workspace.py",
           "                            for entry in value_states.states_in(session, report.id).values() if not entry[\"consistent\"]]\n",
           "                            for entry in value_states.states_in(session, report.id).values() if False]\n", TVS,
           "the data-quality workspace does not list an inconsistent value state"),
    Mutant("VS-report-delete-blocked", "core/database.py",
           "    DELETED_AFTER_REPORT = True\n",
           "    DELETED_AFTER_REPORT = False\n", TAZ,
           "a report with value states can no longer be deleted (the sweep runs before the report is gone)"),
    Mutant("AZ-value-state-policy-missing", "core/authorization.py",
           "    \"ddr_value_states\": TablePolicy(write=(NOBODY,), delete=(DELETE_REPORTS, DELETE_WELL), insert=(EDIT,)),\n",
           "", TAZ,
           "no policy: an editor cannot record a value state and a report deleter cannot delete the report"),
    Mutant("AZ-archive-mark-updatable", "core/authorization.py",
           "    \"calculation_archive_marks\": TablePolicy(write=(NOBODY,), delete=(DELETE_WELL,), insert=(EDIT,)),\n",
           "    \"calculation_archive_marks\": TablePolicy(write=(EDIT,), delete=(DELETE_WELL,), insert=(EDIT,)),\n", TAZ,
           "archive marks become editable by report editors"),
    # ------------------------------------------------------------------ M273: import value lineage
    # M494 (R4b): the IL-* and WB-* anchors below were re-anchored to the current code (M300 moved the check into
    # ``_check``; M303 moved the clone input check into ``core/calculation_clone_contract.py``). Same defects.
    Mutant("IL-changed-since-hidden", IL,
           "    if _same_value(stored_now, expected):\n        note = ",
           "    if True:\n        note = ", TIL + ["tests/test_m300_m301_value_lineage.py"],
           "a value changed after acceptance is still reported as matching"),
    Mutant("IL-first-correction-expected", IL,
           "        expected, basis = corrections[-1].get(\"new\"), \"the latest correction\"\n",
           "        expected, basis = corrections[0].get(\"new\"), \"the latest correction\"\n",
           TIL + ["tests/test_m300_m301_value_lineage.py"],
           "after a re-correction the first, superseded value is expected"),
    Mutant("IL-open-item-checked", IL,
           "    if item.state != accepted_state:\n        return NOT_APPLICABLE",
           "    if False:\n        return NOT_APPLICABLE", TIL + ["tests/test_m300_m301_value_lineage.py"],
           "a reopened (undecided) item is checked as if its old correction were accepted"),
    Mutant("IL-foreign-well-allowed", IL,
           "        if item is None or item.well_id != well_id:\n",
           "        if item is None:\n", TIL,
           "another well's review item is shown"),
    Mutant("IL-dialog-drops-lineage", ILD,
           "        lines.append(self.lineage_line(item))               # M273: the five stages and the stored-now check\n",
           "        pass\n", TIL,
           "the review dialog no longer shows the lineage line"),
    # ------------------------------------------------------------------ M286: workbench clone / archive / restore
    Mutant("WB-archive-without-reason", WBM,
           "    if not reason:\n        raise WorkbenchError(f\"A reason is required to {action.lower()} a calculation record.\")",
           "    if False:\n        raise WorkbenchError(f\"A reason is required to {action.lower()} a calculation record.\")", TWB,
           "a record is archived or restored without a reason"),
    Mutant("WB-double-archive-accepted", WBM,
           "        if action == ARCHIVE and current == ARCHIVED:\n",
           "        if False:\n", TWB,
           "an archived record is archived again (a second, meaningless event)"),
    Mutant("WB-first-mark-wins", WBM,
           "        latest[key] = action                             # ordered by id: the last mark wins\n",
           "        latest.setdefault(key, action)\n", TWB,
           "the first mark decides the state, so a restored record stays hidden"),
    Mutant("WB-reused-id-inherits-archive", WBM,
           "        if key not in born or born[key] != snapshot:     # deleted, or a reused id with another timestamp\n",
           "        if key not in born:\n", TWB,
           "a new record that reuses a deleted record's id inherits its archive mark"),
    Mutant("WB-archive-not-audited", WBM,
           "        db._add_mandatory_audit(session, f\"CALCULATION_{action}\", entry.table, entry.record_id,\n",
           "        (lambda *_a: None)(session, f\"CALCULATION_{action}\", entry.table, entry.record_id,\n", TWB,
           "archive / restore writes no audit record"),
    Mutant("WB-archived-not-hidden", CH,
           "    if hidden:\n        query = query.filter(~model.id.in_(sorted(hidden)))\n",
           "    if False:\n        query = query.filter(~model.id.in_(sorted(hidden)))\n", TWB,
           "archived records stay in the default workbench list"),
    Mutant("WB-ui-shows-archived-by-default", HT,
           "                           \"include_archived\": self.show_archived.isChecked()}\n",
           "                           \"include_archived\": True}\n", TWB,
           "the workbench ignores 'Show archived' and always lists archived records"),
    Mutant("WB-clone-claims-verified", WBM,
           "                     \"verification_status\": CLONE_STATUS, \"method_changed\": False})\n",
           "                     \"verification_status\": \"MATCH\", \"method_changed\": False})\n", TWB,
           "a copied (not recalculated) clone is linked as a verified MATCH"),
    Mutant("WB-clone-empty-inputs-accepted", "core/calculation_clone_contract.py",
           "    if not isinstance(entry.inputs, dict) or not entry.inputs:\n",
           "    if not isinstance(entry.inputs, dict):\n", TWB + ["tests/test_m303_m306_clone_contract_and_bulk.py"],
           "a record without readable inputs is passed on to be cloned"),
    Mutant("WB-recalc-confirmation-overwritten", HT,
           "        self.refresh()                     # M286 (D83): before the message, which refresh used to overwrite\n"
           "        self.status.setText(f\"Stored recalculation as case #{case['id']}; the original record is unchanged.\")\n",
           "        self.status.setText(f\"Stored recalculation as case #{case['id']}; the original record is unchanged.\")\n"
           "        self.refresh()\n", TWB,
           "D83: the stored-recalculation confirmation is replaced by the row count"),
    # ------------------------------------------------------------------ M268: window lifecycle cleanup (D74)
    Mutant("LC-close-keeps-selection-routes", MW,
           "        self._closed_route_count = disconnect_window_routes(self)\n",
           "        self._closed_route_count = len(routes_of(self))\n", TLC,
           "an accepted close leaves every SelectionManager route connected (stale updates to a closed window)"),
    Mutant("LC-status-bar-keeps-closed-window", MW,
           "        self.status_manager.unregister_main_window(self)\n",
           "", TLC,
           "the status-bar singleton still points at a window after its accepted close"),
    Mutant("LC-unregister-detaches-any-window", MGR,
           "        if self._main_window is main_window:\n            self._main_window_ref = None\n",
           "        self._main_window_ref = None\n", TLC,
           "closing one window detaches the status bar from another, still open window"),
    Mutant("LC-status-bar-holds-window-strongly", MGR,
           "        self._main_window_ref = weak_or_strong(main_window)\n",
           "        self._main_window_ref = (lambda window=main_window: window)\n", TLC,
           "the process-wide status-bar singleton keeps the last registered window alive"),
    Mutant("LC-duplicate-route-accepted", QL,
           "                raise ValueError(\"route already connected\")\n",
           "                pass\n", TLC,
           "connecting the same route twice is accepted (a reopened owner receives every update twice)"),
    Mutant("LC-registry-holds-its-owner", QL,
           "            return weakref.WeakMethod(slot)\n",
           "            return _Strong(slot)\n", TLC,
           "the route registry keeps its owner's bound methods strongly (owner becomes cyclic garbage: D63 path)"),
    Mutant("LC-child-routes-not-disconnected", QL,
           "    owners = [window, *window.findChildren(QObject)]\n",
           "    owners = [window]\n", TLC,
           "the window's tabs keep their SelectionManager routes after the accepted close"),
    # ------------------------------------------------------------------ mud volume persistence (snapshot)
    Mutant("MV-snapshot-missing-as-zero", MV,
           "        params[key] = _clean_number(inputs.get(key))\n",
           "        params[key] = _clean_number(inputs.get(key)) or 0.0\n", TMV,
           "an unknown active volume is frozen as 0 bbl in the historical snapshot"),
    Mutant("MV-active-volume-defaulted", MV,
           "            args[key] = val  # required — pass through (None → MISSING_INPUT)\n",
           "            args[key] = 0.0 if val is None else val\n", TMV,
           "re-running a snapshot without an active volume computes a balance from 0 bbl"),
    Mutant("MV-nan-frozen", MV,
           "    return number if math.isfinite(number) else None\n",
           "    return number\n", TMV,
           "a NaN / infinite volume is frozen into the snapshot instead of unknown"),
    Mutant("MV-summary-drops-net-change", MV,
           "    \"net_change_bbl\",\n)\n",
           ")\n", TMV,
           "the net-change headline is no longer stored with the record"),
    # ------------------------------------------------------------------ casing persistence (snapshot)
    Mutant("CP-snapshot-missing-load-as-zero", CP,
           "        params[key] = _clean_number(inputs.get(key))\n",
           "        params[key] = _clean_number(inputs.get(key)) or 0.0\n", TCP,
           "an absent load (not entered) is frozen as 0 psi / 0 lbf in the historical snapshot"),
    Mutant("CP-reconstruct-missing-as-zero", CP,
           "        args[key] = params.get(key)\n",
           "        args[key] = params.get(key) or 0.0\n", TCP,
           "re-running a stored snapshot turns an absent load into an explicit zero load"),
    Mutant("CP-grade-dropped", CP,
           "        params[key] = str(val) if val not in (None, \"\") else \"\"\n",
           "        params[key] = \"\"\n", TCP,
           "the casing grade label is not frozen into the snapshot"),
    Mutant("CP-source-provenance-dropped", CP,
           "    if source:\n        snapshot[\"source\"]",
           "    if False:\n        snapshot[\"source\"]", TCP,
           "the M89 architecture provenance of the inputs is not stored"),
    Mutant("CP-summary-drops-collapse", CP,
           "    \"collapse_rating_psi\",\n",
           "", TCP,
           "the collapse rating is not stored as a headline result"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
