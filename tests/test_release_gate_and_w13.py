"""Release-gate, production-bootstrap, and headless W13 acceptance tests."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from core.database import DatabaseManager, User
from core.engineering.engines.casing import CasingEngine
from core.engineering.engines.cement import CementEngine
from core.engineering.engines.mud_volume import MudVolumeEngine
from core.engineering.engines.torque_drag import TorqueDragEngine
from core.engineering.engines.well_control import WellControlEngine
from core.hydraulics_engine import AdvancedHydraulicsEngine
from core.engineering.core import TrajectoryEngine

REPO = Path(__file__).resolve().parent.parent
W13 = REPO / "tabs" / "w13_Engineering_Calculator.py"


def _load_w13_engine_class():
    source = W13.read_text(encoding="utf-8")
    start = source.index("class DrillingCalculationEngine:")
    end = source.index("# ==================== UI TAB")
    namespace = {}
    exec(compile(source[start:end], "<w13 headless engine>", "exec"), namespace)
    return namespace["DrillingCalculationEngine"]


def _new_database_manager(tmp_path):
    manager = DatabaseManager()
    manager.db_path = str(tmp_path / "drillmaster.sqlite")
    return manager


class TestReleaseGate:
    def test_release_gate_collects_and_invokes_pytest(self):
        import verify_release

        calls = []
        responses = [
            subprocess.CompletedProcess(
                [], 0, stdout="tests/test_example.py: 3\n", stderr=""
            ),
            subprocess.CompletedProcess(
                [], 0, stdout="3 passed, 1 skipped in 0.01s\n", stderr=""
            ),
        ]

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return responses[len(calls) - 1]

        with patch.object(verify_release.subprocess, "run", side_effect=fake_run):
            assert verify_release.run_pytest() is True

        assert len(calls) == 2
        assert all(call[0][1:3] == ["-m", "pytest"] for call in calls)
        assert "--collect-only" in calls[0][0]
        assert "-ra" in calls[1][0]
        assert calls[0][1]["cwd"] == verify_release.ROOT

    def test_release_gate_fails_on_pytest_failure(self):
        import verify_release

        responses = [
            subprocess.CompletedProcess([], 0, stdout="tests/test_example.py: 1\n", stderr=""),
            subprocess.CompletedProcess([], 1, stdout="1 failed, 0 passed\n", stderr=""),
        ]
        with patch.object(verify_release.subprocess, "run", side_effect=responses):
            assert verify_release.run_pytest() is False

    def test_release_gate_does_not_use_unittest_discover(self):
        source = (REPO / "verify_release.py").read_text(encoding="utf-8")
        assert "-m pytest" not in source
        assert "unittest discover" not in source
        assert "pytest" in source
        assert "--collect-only" in source
        assert "unittest.TestCase" in (REPO / "tests" / "test_canonical_schema.py").read_text()


class TestProductionBootstrapCredentials:
    def _clear_password_environment(self, monkeypatch):
        for name in (
            "DRILLMASTER_ADMIN_PASSWORD",
            "DRILLMASTER_USER_PASSWORD",
            "DRILLMASTER_VIEWER_PASSWORD",
        ):
            monkeypatch.delenv(name, raising=False)

    def test_production_requires_explicit_bootstrap_credentials(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DRILLMASTER_ENV", "production")
        self._clear_password_environment(monkeypatch)

        manager = _new_database_manager(tmp_path)
        assert manager.initialize() is False
        assert manager.Session is not None
        session = manager.create_session()
        try:
            assert session.query(User).count() == 0
        finally:
            session.close()
            manager.close()

    def test_production_uses_configured_passwords_and_rejects_fixtures(
        self, tmp_path, monkeypatch, caplog
    ):
        monkeypatch.setenv("DRILLMASTER_ENV", "production")
        configured = {
            "DRILLMASTER_ADMIN_PASSWORD": "admin-production-only-9f3c",
            "DRILLMASTER_USER_PASSWORD": "engineer-production-only-4d7a",
            "DRILLMASTER_VIEWER_PASSWORD": "viewer-production-only-8b2e",
        }
        for name, value in configured.items():
            monkeypatch.setenv(name, value)

        manager = _new_database_manager(tmp_path)
        assert manager.initialize() is True
        try:
            assert manager.authenticate_user("admin", configured["DRILLMASTER_ADMIN_PASSWORD"])
            assert manager.authenticate_user("engineer", configured["DRILLMASTER_USER_PASSWORD"])
            assert manager.authenticate_user("viewer", configured["DRILLMASTER_VIEWER_PASSWORD"])
            assert manager.authenticate_user("admin", "admin123") is None
            assert "admin-production-only-9f3c" not in caplog.text
            assert "engineer-production-only-4d7a" not in caplog.text
            assert "viewer-production-only-8b2e" not in caplog.text
        finally:
            manager.close()

    def test_development_fixture_path_is_not_available_in_production(
        self, tmp_path, monkeypatch
    ):
        self._clear_password_environment(monkeypatch)
        monkeypatch.setenv("DRILLMASTER_ENV", "test")
        manager = _new_database_manager(tmp_path)
        assert manager.initialize() is True
        manager.close()

        monkeypatch.setenv("DRILLMASTER_ENV", "production")
        production_manager = _new_database_manager(tmp_path)
        assert production_manager.initialize() is False
        production_manager.close()


class TestW13HeadlessAcceptance:
    @classmethod
    def setup_class(cls):
        cls.W13 = _load_w13_engine_class()
        cls.source = W13.read_text(encoding="utf-8")

    def test_hydraulics_facade_matches_canonical_results(self):
        A = AdvancedHydraulicsEngine
        tfa = A.calc_tfa_from_pressure_drop(400.0, 12.0, 707.3)
        assert self.W13.calc_tfa_from_pressure(400.0, 12.0, 707.3) == round(tfa, 4)
        from core.engineering.core import BitEngine
        nozzle_tfa = BitEngine.calculate_tfa([13, 13, 14])
        assert self.W13.calc_jet_velocity(400.0, [13, 13, 14]) == round(
            A.calc_jet_velocity(400.0, nozzle_tfa), 2
        )
        assert self.W13.calc_pump_output(6.0, 12.0, 0.9) == A.calc_pump_output(6.0, 12.0, 0.9)

    def test_weight_drag_path_returns_canonical_result(self):
        result = TorqueDragEngine.calculate_weight_card(
            components=[{"length": 1000.0, "weight": 19.5}],
            mud_density_pcf=90.0,
            inclination_deg=30.0,
            top_drive_weight_klbf=10.0,
            friction_factor=0.2,
        )
        assert result.success, result.error
        assert "TorqueDragEngine.calculate_weight_card" in self.source
        assert "TorqueDragEngine.calculate(" in self.source[self.source.index("def _wt_run_td"):]
        assert result.values["pickup_lbs"] > result.values["hook_load_lbs"]
        assert result.values["slackoff_lbs"] < result.values["hook_load_lbs"]

    def test_casing_landing_facade_matches_canonical_result(self):
        canonical = TorqueDragEngine.casing_landing_load(47.0, 5000.0, 0.8163, 0.25)
        facade = self.W13.calc_casing_landing_load(47.0, 5000.0, 0.8163, 0.25)
        assert canonical.success, canonical.error
        assert facade["hook_load_lbs"] == round(canonical.values["hook_load_lbs"], 0)
        assert "TorqueDragEngine.casing_landing_load" in self.source

    def test_well_control_facade_matches_canonical_result(self):
        kwargs = {
            "mw_ppg": 14.5,
            "shoe_tvd_ft": 6000.0,
            "current_tvd_ft": 10000.0,
            "frac_mw_ppg": 16.0,
            "influx_gradient_psi_ft": 0.1,
            "annular_capacity_bbl_ft": 0.0459,
            "formation_emw_ppg": 15.0,
        }
        canonical = WellControlEngine.kick_tolerance(**kwargs)
        facade = self.W13.calc_kick_tolerance(
            16.0,
            14.5,
            10000.0,
            6000.0,
            None,
            influx_gradient_psi_ft=0.1,
            annular_capacity_bbl_ft=0.0459,
            formation_emw_ppg=15.0,
        )
        assert canonical.success, canonical.error
        assert facade == canonical.values

    def test_trajectory_facade_matches_canonical_results(self):
        assert self.W13.calc_build_rate(5.0, 15.0, 300.0) == round(
            TrajectoryEngine.calculate_build_rate(5.0, 15.0, 300.0), 2
        )
        assert self.W13.calc_turn_rate(350.0, 10.0, 100.0) == round(
            TrajectoryEngine.calculate_turn_rate(350.0, 10.0, 100.0), 2
        )

    def test_mud_volume_facade_matches_canonical_result(self):
        canonical = MudVolumeEngine.mix(85.0, 100.0, 95.0, 50.0)
        facade = self.W13.calc_mud_mixing(85.0, 100.0, 95.0, 50.0)
        assert canonical.success, canonical.error
        assert facade == {
            "final_mw_pcf": canonical.values["final_mw"],
            "total_volume_bbl": canonical.values["total_volume"],
        }

    def test_casing_and_cement_paths_use_canonical_engines(self):
        casing = CasingEngine.evaluate(
            od_in=9.625,
            id_in=8.681,
            wall_in=0.472,
            yield_psi=80000.0,
        )
        cement = CementEngine.job_volumes(12.25, 9.625, 1000.0, 0.0)
        assert casing.success, casing.error
        assert cement.success, cement.error
        casing_section = self.source[self.source.index("def _csg_calc_strength"):self.source.index("def _csg_calc_cement")]
        cement_section = self.source[self.source.index("def _csg_calc_cement"):self.source.index("def _csg_calc_landing")]
        assert "CasingEngine.evaluate(" in casing_section
        assert "CementEngine.job_volumes(" in cement_section
        assert casing.values["burst_rating_psi"] > 0
        assert cement.values["annular_volume_bbl"] > 0

    def test_lag_and_bottoms_up_paths_use_canonical_hydraulics(self):
        A = AdvancedHydraulicsEngine
        assert A.calc_lag_time(437.0, 630.0) == pytest.approx(437.0 / (630.0 / 42.0))
        assert A.calc_bottoms_up_strokes(437.0, 0.125) == pytest.approx(437.0 / 0.125)
        volume_section = self.source[self.source.index("def _vol_calculate"):self.source.index("def _wt_refresh_table")]
        assert "A.calc_lag_time(total_annular, total_gpm)" in volume_section
        assert "A.calc_bottoms_up_strokes(total_annular, total_output)" in volume_section
