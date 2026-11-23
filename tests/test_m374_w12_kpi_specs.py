"""M374: every W12 Analysis KPI has the seven-field structural definition, shown in its card tooltip."""
from __future__ import annotations

from core import analysis_evidence as ev


def test_every_w12_kpi_has_all_seven_fields():
    assert set(ev.KPI_SPECS) == set(ev.KPI_DEFINITIONS)
    for key, (title, unit, definition) in ev.KPI_DEFINITIONS.items():
        spec = ev.KPI_SPECS[key]
        assert title and unit and definition, key
        assert set(spec) == set(ev.KPI_SPEC_FIELDS), key
        assert all(isinstance(spec[f], str) and len(spec[f]) >= 5 for f in ev.KPI_SPEC_FIELDS), key


def test_tooltip_carries_every_field_in_order():
    for key in ev.KPI_DEFINITIONS:
        tip = ev.kpi_tooltip(key).splitlines()
        assert tip[0].endswith(f"[{ev.KPI_DEFINITIONS[key][1]}]") and tip[1] == ev.KPI_DEFINITIONS[key][2]
        assert [line.split(":")[0] for line in tip[2:]] == [f.capitalize() for f in ev.KPI_SPEC_FIELDS], key


def test_scope_states_the_wellbore_rule_and_missing_is_never_zero_for_averages():
    for key in ("avg_rop", "avg_wob", "avg_rpm", "avg_torque", "weighted_rop"):
        assert "excluded" in ev.KPI_SPECS[key]["missing"], key
    assert all("unknown wellbore excluded" in s["scope"] for s in ev.KPI_SPECS.values())
