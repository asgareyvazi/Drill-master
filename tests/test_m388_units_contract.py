"""M388: every unit a M361-M400 replay adapter can report has a declared replay tolerance (no silent fallback).

``core.history_replay`` compares stored and replayed results with an absolute tolerance chosen by unit; an unknown
unit falls back to the dimensionless 1e-9. This contract makes the M366 / M368 / M371 / M372 / M373 field units
explicit, checks every input carries a unit declaration, and that no new module mixes ppg into a pcf-based worksheet
(P8: the volumetric aid takes pcf and uses the exact 1/144 gradient, not a gallon divisor).
"""
from __future__ import annotations

import inspect

import pytest

from core import casing_axial_loads as cal
from core import history_replay as hr
from core import hydraulics_workflow as hw
from core import mse_drilloff as mdo
from core import well_control_volumetric as wcv
from tests.test_m371_casing_axial_loads import FULL
from tests.test_m372_mse_drilloff import PARAMS, STEPS
from tests.test_m373_volumetric_method import BASE


def _payload(module):
    if module is cal:
        return cal.case_payload(cal.evaluate(FULL))
    if module is mdo:
        return mdo.case_payload(mdo.evaluate(PARAMS, STEPS))
    return wcv.case_payload(wcv.evaluate(dict(BASE, pressure_rise_psi=150.0, rise_duration_h=0.5)))


def _results(module):
    return _payload(module)[1]


@pytest.mark.parametrize("module", [cal, mdo, wcv], ids=["m371", "m372", "m373"])
def test_every_result_unit_has_a_declared_tolerance_and_matches_the_payload(module):
    for key, entry in _results(module).items():
        unit = hr._unit_of(module.METHOD_ID, key)
        assert unit in hr.FIELD_TOLERANCES, (module.METHOD_ID, key, unit)
        declared = entry.get("unit") if isinstance(entry, dict) else None
        if declared and isinstance(entry.get("value"), (int, float)) and not isinstance(entry["value"], bool):
            assert unit == declared, (module.METHOD_ID, key, unit, declared)


def test_m366_and_m368_units_have_declared_tolerances():
    assert {unit for _field, unit in hw._POINT_FIELDS} <= set(hr.FIELD_TOLERANCES)
    assert hr._unit_of("m368.survey_plan_deviation", "closest_distance_m") in hr.FIELD_TOLERANCES


@pytest.mark.parametrize("module", [cal, mdo, wcv], ids=["m371", "m372", "m373"])
def test_every_input_declares_its_unit(module):
    for key, unit, _required in module.FIELDS:
        assert key in module.UNITS and isinstance(unit, str)
    assert all("unit" in entry for entry in _payload(module)[0].values())


def test_the_volumetric_aid_does_not_mix_ppg_into_its_pcf_inputs():
    source = inspect.getsource(wcv)
    assert "ppg" not in source.lower().replace("no gallon", "")
    assert wcv.PSI_PER_FT_PER_PCF == pytest.approx(1 / 144)
    assert wcv.UNITS["mud_density_pcf"] == "pcf"


def test_m416_m420_m423_m427_services_declare_input_units_and_result_tolerances():
    """M412 / M437: the M401-M460 services follow the same unit contract (inputs carry units; every stored result unit
    has a replay tolerance)."""
    from core import bit_dull_grade as dg
    from core import drilloff_fitted as df
    from core import hydraulics_hb_slot as hb
    from core import surge_swab as ss

    for module in (hb, ss, df):
        for key, unit, _required in module.FIELDS:
            assert module.UNITS[key] == unit
        for key, unit in module.RESULT_FIELDS:
            assert hr._unit_of(module.METHOD_ID, key) == unit and unit in hr.FIELD_TOLERANCES
    assert dg.UNITS["depth_out_m"] == "m" and hr._unit_of(dg.METHOD_ID, "footage_m") == "m"
    assert hb.PA_PER_PSI == pytest.approx(6894.757293168361, rel=1e-15)          # exact lbf / in^2
    assert ss.PSI_FT_PER_PPG == pytest.approx(12.0 / 231.0, rel=1e-12)          # 1 lb/gal over 12 in, 231 in^3/gal
