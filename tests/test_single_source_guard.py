"""Single-source-of-truth guards and canonical-delegation parity tests.

Guard (section 19 of the engineering audit):
  * legacy engineering constants (12031 / 1086.31 / 10863.1 / 1932) must not
    appear anywhere in application code;
  * canonical formula constants (10858 / 1714 / 1930 / 3.117 / 1029.4 /
    0.000243 / 0.000162 / 735294 / 96250000 / 65.44 / 2.67) may appear ONLY
    in core engines, the reference-tables display tab (w15) and tests —
    never in other tabs/dialogs;
  * no duplicated @staticmethod decorator stacks anywhere in tabs/dialogs/core.

Parity (W13 legacy facade → canonical engines):
  buoyancy factor, casing landing load, formation pressure, build/turn rate,
  fishing (free point, stretch, adjusted weight, jar range, overshot fit,
  back-off) and jet-velocity/TFA wrappers must reproduce the exact legacy
  numbers through their canonical engine delegates.
"""
import math
import os
import re
import glob

import pytest

from core.engineering.core import TrajectoryEngine
from core.engineering.engines.fishing import FishingEngine
from core.engineering.engines.torque_drag import TorqueDragEngine
from core.engineering.engines.well_control import WellControlEngine
from core.hydraulics_engine import AdvancedHydraulicsEngine

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Constants that must NEVER exist in code (stale / superseded).
LEGACY_CONSTANTS = ["12031", "1086.31", "10863.1", "1932", "24.5 *", "1086.3"]

# Canonical formula constants: allowed in core engines, the w15 reference
# display and tests only.
CANONICAL_CONSTANTS = ["10858", "1714", "1930", "3.117", "1029.4",
                       "0.000243", "0.000162", "735294", "96250000",
                       "65.44", "2.67"]

ALLOWED_DIRS = (
    os.path.join("core", ""),
    os.path.join("tests", ""),
)
ALLOWED_FILES = {"tabs/w15_Reference_Tables.py"}


def _app_py_files():
    for root in ("tabs", "dialogs", "core"):
        for path in glob.glob(os.path.join(REPO, root, "**", "*.py"),
                              recursive=True):
            if "__pycache__" in path:
                continue
            yield os.path.relpath(path, REPO)


class TestStaleFormulaGuard:
    @pytest.mark.parametrize("const", LEGACY_CONSTANTS)
    def test_legacy_constants_absent_from_app_code(self, const):
        for rel in _app_py_files():
            src = open(os.path.join(REPO, rel), encoding="utf-8").read()
            assert const not in src, f"{const} found in {rel}"

    @pytest.mark.parametrize("const", CANONICAL_CONSTANTS)
    def test_canonical_constants_only_in_canonical_locations(self, const):
        offenders = []
        for rel in _app_py_files():
            if rel.startswith(ALLOWED_DIRS) or rel in ALLOWED_FILES:
                continue
            src = open(os.path.join(REPO, rel), encoding="utf-8").read()
            if const in src:
                offenders.append(rel)
        assert not offenders, (
            f"canonical constant {const} duplicated in UI code: {offenders}")

    def test_no_stacked_staticmethod_decorators(self):
        pat = re.compile(r"@staticmethod\n\s*@staticmethod")
        for rel in _app_py_files():
            src = open(os.path.join(REPO, rel), encoding="utf-8").read()
            hits = list(pat.finditer(src))
            assert not hits, f"duplicated @staticmethod in {rel}"


def _load_w13_engine_class():
    src = open(os.path.join(REPO, "tabs", "w13_Engineering_Calculator.py"),
               encoding="utf-8").read()
    cs = src.index("class DrillingCalculationEngine:")
    ce = src.index("# ==================== UI TAB")
    ns = {}
    exec(compile(src[cs:ce], "<w13 engine class>", "exec"), ns)
    return ns["DrillingCalculationEngine"]


class TestW13DelegationParity:
    """W13 legacy facade methods must reproduce legacy numbers through the
    canonical engines (wrappers only — no local formulas)."""

    @classmethod
    def setup_class(cls):
        cls.E = _load_w13_engine_class()

    def test_buoyancy_factor_delegates_to_torque_drag(self):
        bf = self.E.calc_buoyancy_factor(90.0)          # pcf input
        expected = round(TorqueDragEngine.buoyancy_factor(90.0 / 7.48), 4)
        assert bf == expected == round(1 - 90.0 / 490.0, 4)
        assert bf == pytest.approx(0.8163, abs=1e-4)
        # no input → legacy 0 (no crash, no invented value)
        assert self.E.calc_buoyancy_factor(0.0) == 0.0

    def test_formation_pressure_delegates_to_well_control(self):
        r = self.E.calc_formation_pressure(mw_pcf=90.0, tvd_ft=8000.0,
                                           sidpp=250.0)
        eng = WellControlEngine.formation_pressure(
            mw_ppg=90.0 / 7.48, tvd_ft=8000.0, sidpp_psi=250.0)
        assert eng.success
        assert r["hydrostatic_psi"] == round(eng.values["hydrostatic_psi"], 0)
        assert r["formation_pressure_psi"] == round(
            eng.values["formation_pressure_psi"], 0)
        assert r["equivalent_mw_ppg"] == round(eng.values["equivalent_mw_ppg"], 2)
        assert r["equivalent_mw_pcf"] == round(
            eng.values["equivalent_mw_ppg"] * 7.48, 2)
        # legacy zero-field fallback when TVD is missing (no invented depth)
        zero = self.E.calc_formation_pressure(mw_pcf=90.0, tvd_ft=0.0, sidpp=0)
        assert zero["hydrostatic_psi"] == 0.0 and zero["pressure_gradient_psi_ft"] == 0.0

    def test_build_turn_rate_delegate_to_trajectory_engine(self):
        assert self.E.calc_build_rate(5, 15, 300) == round(
            TrajectoryEngine.calculate_build_rate(5, 15, 300), 2) == 1.0
        assert self.E.calc_turn_rate(60, 90, 300) == 3.0
        # wrap across 0°
        assert self.E.calc_turn_rate(350, 10, 100) == 6.0
        assert self.E.calc_build_rate(5, 15, 0) == 0.0
        assert self.E.calc_turn_rate(5, 15, 0) == 0.0

    def test_fishing_calculations_delegate(self):
        fp = self.E.calc_free_point(12, 19.5, 30000)
        assert fp == round(735294.0 * 12 * 19.5 / 30000, 1)
        assert self.E.calc_free_point(12, 19.5, 0) == 0.0
        ss = self.E.calc_string_stretch(5000, 12)
        assert ss == round(5000 / 96250000.0 * (65.44 - 1.44 * 12), 2)
        aw = self.E.calc_adjusted_weight(5.0, 4.276)
        assert aw == round(2.67 * (25.0 - 4.276 ** 2), 2)
        j = self.E.calc_jar_operating_range(150000, 0.8168, 40000)
        eng_jar = FishingEngine.jar_operating_range(150000, 0.8168, 40000)
        assert j == eng_jar.values
        f = self.E.calc_fish_neck_ot(4.75, 5.0)
        assert f["compatible"] is True and f["recommendation"] == "OK"
        bo = self.E.calc_backoff_depth(12, 19.5)
        assert bo == round(12 * 30e6 * (19.5 / 3.4) / (19.5 * 12), 1)
        assert self.E.calc_backoff_depth(12, 0) == 0.0

    def test_jet_velocity_uses_canonical_bitengine_tfa(self):
        from core.engineering.core import BitEngine
        v = self.E.calc_jet_velocity(400, [13, 13, 14])
        tfa = BitEngine.calculate_tfa([13, 13, 14])
        assert v == round(AdvancedHydraulicsEngine.calc_jet_velocity(400, tfa), 2)
        assert self.E.calc_jet_velocity(400, []) == 0.0

    def test_tfa_from_pressure_delegates(self):
        assert self.E.calc_tfa_from_pressure(400, 12, 707.3) == round(
            AdvancedHydraulicsEngine.calc_tfa_from_pressure_drop(400, 12, 707.3), 4)
        assert self.E.calc_tfa_from_pressure(400, 12, 0) == 0

    def test_landing_load_shape_unchanged(self):
        r = self.E.calc_casing_landing_load(47.0, 5000.0, 0.8163, 0.25)
        assert set(r) == {"air_weight_lbs", "buoyant_weight_lbs",
                          "friction_load_lbs", "hook_load_lbs"}
        assert r["air_weight_lbs"] == round(47.0 * 5000.0, 0)


class TestEngineContractParity:
    """New canonical methods used by the UI return standard EngineeringResult
    shapes with units and assumptions."""

    def test_formation_pressure_result_contract(self):
        r = WellControlEngine.formation_pressure(mw_ppg=12.0, tvd_ft=10000,
                                                 sidpp_psi=500)
        assert r.success
        assert r.value == pytest.approx(6740.0, abs=0.1)
        for key in ("hydrostatic_psi", "formation_pressure_psi",
                    "pressure_gradient_psi_ft", "equivalent_mw_ppg"):
            assert key in r.values
        assert r.unit == "psi"
        assert r.method and r.assumptions
        bad = WellControlEngine.formation_pressure(mw_ppg=10.0, tvd_ft=0)
        assert not bad.success and bad.error

    def test_fishing_result_contract(self):
        r = FishingEngine.free_point(12.0, 19.5, 30000.0)
        assert r.success and r.unit == "ft" and r.scope
        assert "SCREENING" in r.scope or "PARTIAL" in r.scope
        assert FishingEngine.SCOPE.startswith("PARTIAL")

    def test_torque_drag_buoyancy_contract(self):
        bf = TorqueDragEngine.buoyancy_factor(12.0)
        assert bf == pytest.approx(1 - 12.0 / 65.5, abs=1e-12)
        with pytest.raises(Exception):
            TorqueDragEngine.buoyancy_factor(80.0)  # mud ≥ steel

    def test_trajectory_rate_contract(self):
        assert TrajectoryEngine.calculate_build_rate(0, 30, 300) == 3.0
        assert TrajectoryEngine.calculate_turn_rate(0, 90, 300) == 9.0
        assert TrajectoryEngine.calculate_build_rate(0, 30, 0) == 0.0
