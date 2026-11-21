"""M285: every dashboard KPI carries the seven-field definition and the card shows all of it.

Seven fields: definition, unit, window, scope, source, method and missing-data behaviour, plus the counting rule
that keeps a figure from counting one record twice.  Expected numbers come from the documented SYNTHETIC
fixture (tests/synthetic_operations.py), as in tests/test_operations_dashboard.py.
"""
from __future__ import annotations

import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.operations_dashboard import (  # noqa: E402
    KPI_DEFINITIONS, KPI_GROUPS, KPI_SOURCES, KPI_SPECS, SPEC_FIELDS, build_snapshot,
)
from synthetic_operations import build_synthetic_operations, make_file_database  # noqa: E402

END = date(2026, 1, 15)


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    db = make_file_database(tmp_path_factory.mktemp("m285") / "syn.db")
    build_synthetic_operations(db, end_date=END)
    snap = build_snapshot(db, today=END)
    db.engine.dispose()
    return snap


def test_every_kpi_has_a_complete_specification():
    grouped = {key for _title, keys in KPI_GROUPS for key in keys}
    assert set(KPI_DEFINITIONS) == set(KPI_SOURCES) == set(KPI_SPECS) == grouped
    for key, spec in KPI_SPECS.items():
        assert set(spec) == set(SPEC_FIELDS), key
        for field in SPEC_FIELDS:
            assert isinstance(spec[field], str) and len(spec[field].strip()) >= 4, (key, field)
        assert KPI_SOURCES[key].strip(), key


def test_every_built_kpi_carries_its_specification(snapshot):
    for key, kpi in snapshot.kpis.items():
        assert kpi.spec == KPI_SPECS[key], key


def test_single_well_figures_say_so_and_estimates_are_labelled():
    for key in ("cost_per_metre", "npt_cost"):
        assert KPI_SPECS[key]["scope"] == "single well only"
    assert KPI_SPECS["npt_cost"]["method"].startswith("ESTIMATE")
    assert "never a mean of per-row ROPs" in KPI_SPECS["rop_window"]["counting"]
    assert "not well-scoped" in KPI_SPECS["imports_window"]["scope"]


def test_status_groups_count_each_well_once(snapshot):
    """Counting rule 'one status group per well': the groups partition the well list (fixture: 2 + 2 + 1 = 5)."""
    k = snapshot.kpis
    assert k["wells_active"].value + k["wells_planning"].value + k["wells_completed"].value == k["wells_total"].value


def test_npt_share_uses_the_same_rows_as_npt_hours(snapshot):
    """Counting rule: numerator and denominator from the same 24-h rows (fixture: 5.5 h NPT of 6 x 24 h)."""
    k = snapshot.kpis
    assert k["npt_window"].value == pytest.approx(5.5)
    assert k["npt_share"].value == pytest.approx(100 * k["npt_window"].value / (6 * 24.0))


def test_the_kpi_card_tooltip_shows_all_seven_fields(snapshot):
    from PySide6.QtWidgets import QApplication

    from tabs.dashboard_widgets import KpiCard

    app = QApplication.instance() or QApplication([])
    card = KpiCard()
    try:
        kpi = snapshot.kpis["rop_window"]
        card.set_kpi(kpi)
        tip = card.toolTip()
        assert kpi.definition in tip
        for label in ("Unit:", "Source:", "Window:", "Scope:", "Method:", "If data is missing:", "Counting:"):
            assert label in tip, label
        assert KPI_SPECS["rop_window"]["method"] in tip
    finally:
        card.deleteLater()
        del app
