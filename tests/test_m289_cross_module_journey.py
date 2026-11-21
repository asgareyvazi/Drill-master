"""M289: 13-step SYNTHETIC cross-module journey for the M269-M285 engineering modules.

One file database carries the whole journey: the documented synthetic operations world
(tests/synthetic_operations.py, SYN-DEV-01 with 6 daily reports and stored MWD surveys, metres). Each step uses the
output of an earlier step, and each step is checked against an independent hand calculation, not against the code's own
result. Where a desktop widget exists for the step, the real widget is used (KPI card).

Why no MainWindow here: the real-window journeys are M139, M169 and M229 (35 steps).
Every closed MainWindow stays alive by design (D63), at about 200 MB of anonymous RSS each (M267), and this
journey crosses the engines, the persistence layer and the workbench, which do not need a window.

SYNTHETIC: not real-world, desktop or field acceptance. Anti-collision is a screening method (no ISCWSA, P19).
The kill sheet and well control are TRAINING AIDs. Fishing is a legacy screening method.
"""
from __future__ import annotations

import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import calculation_history as ch  # noqa: E402
from core import report_provenance as rp  # noqa: E402
from core.engineering.calculation_verification import VERIFY_MATCH  # noqa: E402
from core.engineering.engines.anti_collision import AntiCollisionEngine as AC  # noqa: E402
from core.engineering.engines.bit_performance import BitPerformanceEngine as BP  # noqa: E402
from core.engineering.engines.casing import CasingEngine  # noqa: E402
from core.engineering.engines.fishing import FishingEngine as FI  # noqa: E402
from core.engineering.engines.mud_volume import MudVolumeEngine  # noqa: E402
from core.engineering.engines.trajectory import TrajectoryCalculator as TR  # noqa: E402
from core.engineering.engines.well_control import WellControlEngine as WC  # noqa: E402
from core.operations_dashboard import KPI_SPECS, build_snapshot  # noqa: E402
from core.repositories.casing_repository import CasingCalculationRepository  # noqa: E402
from core.repositories.mud_volume_repository import MudVolumeCalculationRepository  # noqa: E402
from synthetic_operations import build_synthetic_operations, make_file_database  # noqa: E402

END = date(2026, 1, 15)
FT_PER_M = 1.0 / 0.3048            # exact definition of the international foot


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    db = make_file_database(tmp_path_factory.mktemp("m289") / "journey.db")
    ids = build_synthetic_operations(db, end_date=END)
    yield db, ids
    db.engine.dispose()


def test_m289_thirteen_step_cross_module_journey(world):
    db, ids = world
    dev = ids["dev"]
    carried = {}

    # 1. Dashboard over the synthetic world: every KPI carries its M285 specification, and NPT share uses the same
    #    24-h rows as NPT hours (fixture: 3.5 + 2.0 h NPT in 6 x 24 h logged).
    snap = build_snapshot(db, today=END)
    assert all(kpi.spec == KPI_SPECS[key] for key, kpi in snap.kpis.items())
    assert snap.kpis["npt_window"].value == pytest.approx(5.5)
    assert snap.kpis["npt_share"].value == pytest.approx(100 * 5.5 / 144.0)

    # 2. The real KPI card shows the specification (window, scope, method, missing behaviour, counting rule).
    from PySide6.QtWidgets import QApplication

    from tabs.dashboard_widgets import KpiCard

    app = QApplication.instance() or QApplication([])
    card = KpiCard()
    try:
        card.set_kpi(snap.kpis["npt_share"])
        tip = card.toolTip()
        assert KPI_SPECS["npt_share"]["counting"] in tip and "If data is missing:" in tip
    finally:
        card.deleteLater()
        del app

    # 3. The stored MWD surveys of SYN-DEV-01 (metres) are composed the way the application composes them. Each
    #    report repeats its start station, and composition merges the duplicates. The stations then go through the
    #    minimum-curvature wrapper, whose last station is at the deepest MD; TVD never exceeds MD. The wrapper agrees
    #    with the composed trajectory.
    from core.well_trajectory import READY, compose_well_trajectory

    composed = compose_well_trajectory(db.load_survey_points(well_id=dev))
    assert composed.status == READY, [i.code for i in composed.issues]
    stations = [{"md": s.md, "inc": s.inc, "azi": s.azi} for s in composed.stations]
    assert stations[-1]["md"] == pytest.approx(1800.0)
    trajectory = TR.calculate(stations, vs_azimuth=0.0)
    last = trajectory[-1]
    assert 0 < last["tvd"] <= last["md"] + 1e-9
    assert last["tvd"] == pytest.approx(composed.stations[-1].tvd, abs=1e-6)
    #    The stored points are frozen as a survey revision (datum and azimuth reference are stated, not inferred;
    #    P10 governs real CRS/datum use). Its stored results agree with the trajectory above.
    from core import survey_revisions as sr

    revision = sr.snapshot_survey_points(db, dev, depth_datum="RKB", azimuth_reference="true",
                                         note="SYNTHETIC M289 journey")
    frozen = sr.get_revision(db, revision["id"])
    assert sr.verify_results(frozen)["status"] == "MATCH", sr.verify_results(frozen)
    assert frozen["integrity"] == "VERIFIED"
    assert frozen["results"][-1]["tvd"] == pytest.approx(last["tvd"], abs=1e-3)
    carried["md_m"], carried["tvd_m"] = last["md"], last["tvd"]

    # 4. Anti-collision screening against a twin of that trajectory offset 30 m east. With 1-sigma values of
    #    3 m and 4 m (east), the combined sigma is sqrt(9 + 16) = 5 m by root-sum-square, so SF = 30 / 5 = 6.
    def path(shift_east, sigma_east):
        return [dict(md=s["md"], tvd=s["tvd"], north=s["north"], east=s["east"] + shift_east,
                     sigma_north=0.0, sigma_east=sigma_east, sigma_tvd=0.0) for s in trajectory]
    screen = AC.screen_clearance(path(0.0, 3.0), path(30.0, 4.0))
    assert screen.success, screen.error
    closest = screen.values["closest_approach"]
    assert closest["centerline_distance"] == pytest.approx(30.0, abs=1e-6)
    assert closest["combined_sigma"] == pytest.approx(5.0)
    assert closest["separation_factor"] == pytest.approx(6.0)
    assert screen.metadata["iscwsa_compliant"] is False

    # 5. Mud volume balance, saved for the well, reloaded and re-run as MATCH: 500 + 40 - 12 = 528 bbl.
    mud_repo = MudVolumeCalculationRepository(db)
    mud_inputs = dict(active_volume_bbl=500.0, additions_bbl=40.0, losses_bbl=12.0)
    balance = MudVolumeEngine.balance(**mud_inputs)
    assert balance.success and balance.values["final_volume_bbl"] == pytest.approx(528.0)
    mud_id = mud_repo.save_run(inputs=mud_inputs, result_values=balance.values, method=MudVolumeEngine.METHOD,
                               label="SYN M289 balance", well_id=dev)
    assert mud_repo.get(mud_id).verify(current_method=MudVolumeEngine.METHOD).status == VERIFY_MATCH

    # 6. An unknown active volume is refused, never balanced from 0 bbl.
    assert not MudVolumeEngine.balance(active_volume_bbl=None, additions_bbl=40.0).success

    # 7. Casing rating with its architecture source, saved and re-run as MATCH.
    #    Barlow burst: 0.875 x 2 x 80,000 x 0.472 / 9.625 = 6,865.5 psi.
    casing_repo = CasingCalculationRepository(db)
    casing_inputs = dict(od_in=9.625, id_in=8.681, wall_in=0.472, yield_psi=80000.0, grade="SYN-80",
                         internal_pressure_psi=None, external_pressure_psi=None, axial_tension_lbf=None,
                         weight_ppf=None)
    rating = CasingEngine.evaluate(**casing_inputs)
    assert rating.success, rating.error
    assert rating.values["burst_rating_psi"] == pytest.approx(0.875 * 2 * 80000.0 * 0.472 / 9.625, rel=1e-3)
    casing_id = casing_repo.save_run(inputs=casing_inputs, result_values=rating.values, method=CasingEngine.METHOD,
                                     label="SYN M289 casing", well_id=dev, source={"journey": "M289 step 7"})
    saved_casing = casing_repo.get(casing_id)
    assert saved_casing.verify(current_method=CasingEngine.METHOD).status == VERIFY_MATCH
    assert saved_casing.input_parameters["internal_pressure_psi"] is None          # absent load stays absent

    # 8. Well control (TRAINING AID) at the TVD from step 3, in feet: kill MW = MW + SIDPP / (0.052 x TVD).
    tvd_ft = carried["tvd_m"] * FT_PER_M
    kill_mw = WC.calculate_kill_mw(10.0, 400.0, tvd_ft)
    assert kill_mw == pytest.approx(10.0 + 400.0 / (0.052 * tvd_ft))
    assert WC.calculate_fcp(800.0, kill_mw, 10.0) == pytest.approx(800.0 * kill_mw / 10.0)
    carried["kill_mw"] = kill_mw

    # 9. Fishing (screening): free-string stretch at the MD from step 3 in the kill mud from step 8. D81 form:
    #    L^2 x (65.44 - 1.44 x MW) / 96,250,000.
    md_ft = carried["md_m"] * FT_PER_M
    stretch = FI.string_stretch(md_ft, carried["kill_mw"])
    assert stretch.success
    assert stretch.value == pytest.approx(md_ft ** 2 * (65.44 - 1.44 * carried["kill_mw"]) / 96_250_000.0,
                                         abs=0.005)                    # the engine reports 0.01 in

    # 10. Bit performance: footage-weighted ROP over two synthetic runs is sum of footage / sum of hours
    #     (300 + 300) / (10 + 20) = 20 m/h, not the mean of the two runs' ROPs (30 + 15) / 2 = 22.5.
    rop = BP.weighted_rop([{"depth_in": 1200.0, "depth_out": 1500.0, "hours_on_bottom": 10.0},
                           {"depth_in": 1500.0, "depth_out": 1800.0, "hours_on_bottom": 20.0}])
    assert rop.success, rop.error
    assert rop.value == pytest.approx(20.0)

    # 11. Workbench: the well's calculation history lists both saved runs as readable and reproducible.
    entries = {(e.table, e.record_id): e for e in ch.load_history(db, well_id=dev)}
    mud_entry = entries[("mud_volume_calculations", mud_id)]
    casing_entry = entries[("casing_calculations", casing_id)]
    for entry in (mud_entry, casing_entry):
        status = ch.entry_status(entry)
        assert status["readable"] == "READABLE" and status["reproducible"] == "REPRODUCIBLE", status

    # 12. Re-running from the workbench with the current method gives MATCH, and nothing is written.
    before = ch.count_history(db, well_id=dev)
    for entry in (mud_entry, casing_entry):
        assert ch.recalculate_entry(entry, db)["status"] == VERIFY_MATCH
    assert ch.count_history(db, well_id=dev) == before

    # 13. The end-of-well report provenance names the well, all six daily reports and the stored survey revision,
    #     and it keeps the release label.
    prov = rp.build(db, "eowr", dev)
    assert "SYN-DEV-01" in prov["scope"]["well"]
    assert "6 daily report(s) in scope" in prov["sources"]
    assert any(line.startswith("Survey revision") and "none recorded" not in line for line in prov["revisions"])
    assert prov["label"] == "UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED"
