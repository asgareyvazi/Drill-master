"""P6 follow-up regression: a non-finite source number is unknown, never a measurement.

The batch-017 defect fix (INV34-001111, ``DatabaseManager.coerce_model_values``)
established the repository-wide boundary contract: a value that does not parse
to a finite number is unknown — ``'nan'``, ``'inf'``, ``'-inf'`` and the
overflowing ``'1e400'`` are not measurements, and neither is an already-float
``nan``/``inf``.

``ProfileImportEngine._to_float`` and the schematic engine's ``_to_float`` read
imported spreadsheet/JSON cells and still accepted every spelling ``float()``
accepts, so a ``nan`` inclination passed the "required input is present" review
gate and an ``inf`` MD passed ``md >= 0``: a fabricated survey station could be
extracted from a meaningless cell, and fabricated casing geometry (od, depths)
from a persisted ``casing_json`` written by the import path.

The fix routes both helpers through the same finite check. An explicit finite
0 stays 0.0 and unparseable text stays missing, exactly as before; only the
non-finite spellings change from a fake number to unknown (None).

The schematic tests run REAL production code (``SchematicAutoBuilder`` over an
isolated in-memory SQLite database, ``DatabaseManager.save_casing_report``) —
the same pattern as ``tests/test_schematic_no_fabrication.py``. No mocks.
"""

import json
import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base, DatabaseManager
from core.profile_import_engine import ProfileImportEngine
from core.wellbore_schematic_engine import SchematicAutoBuilder


# --------------------------------------------------------------------------
# Profile import boundary
# --------------------------------------------------------------------------

def test_profile_to_float_rejects_nonfinite_spellings():
    engine = ProfileImportEngine(None)
    for value in ("nan", "NaN", "inf", "-inf", "Infinity", "1e400", float("nan"),
                  float("inf"), float("-inf")):
        assert engine._to_float(value) is None, (
            f"a non-finite value ({value!r}) is unknown, not a measurement")
    # unchanged contract: real numbers and explicit zeros parse, junk stays None
    assert engine._to_float("12.5") == 12.5
    assert engine._to_float(0) == 0.0
    assert engine._to_float("N/A") is None
    assert engine._to_float(None) is None


def _survey_engine(rows):
    engine = ProfileImportEngine(None)
    engine.cell_cache = {"Surveys": rows}
    return engine


def test_nan_inclination_is_reviewed_not_extracted_as_a_measurement():
    rows = {1: {1: "MD", 3: "INC", 4: "AZI"},
            2: {1: 1500.0, 3: "nan", 4: 90.0}}
    result = _survey_engine(rows)._extract_multi_tab_sheets(["Surveys"])

    assert result["surveys"] == [], "nan inclination is not a measurement"
    assert any(item["row"] == 2 and "inc" in item["missing"]
               for item in result["survey_review"]), \
        "the row is preserved as a review record instead"


def test_overflowing_md_is_not_a_survey_station():
    rows = {1: {1: "MD", 3: "INC", 4: "AZI"},
            2: {1: "1e400", 3: 12.0, 4: 45.0}}
    result = _survey_engine(rows)._extract_multi_tab_sheets(["Surveys"])

    # An unknown MD has no anchor: the row is skipped entirely (there is no
    # MD to report a review record against), and no station is fabricated.
    assert result["surveys"] == [], "an overflowing MD is not a survey station"


def test_finite_md_with_overflowing_tvd_stays_unknown_tvd():
    rows = {1: {1: "MD", 3: "INC", 4: "AZI", 5: "TVD"},
            2: {1: 1500.0, 3: 12.0, 4: 45.0, 5: "inf"}}
    result = _survey_engine(rows)._extract_multi_tab_sheets(["Surveys"])

    assert len(result["surveys"]) == 1, "the station itself is real"
    assert result["surveys"][0]["md"] == 1500.0
    assert "tvd" not in result["surveys"][0], \
        "an overflowing TVD is unknown, not a fabricated depth"


# --------------------------------------------------------------------------
# Schematic boundary: real DB, real builder
# --------------------------------------------------------------------------

@pytest.fixture
def manager():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(
        bind=manager.engine, autoflush=False, autocommit=False)
    session = manager.create_session()
    try:
        company = _quick(session, "company")
        project = _quick(session, "project", company)
        well = _quick(session, "well", project)
        manager._test_well_id = well
        return manager
    finally:
        session.close()


def _quick(session, kind, parent=None):
    from core.database import Company, Project, Well
    if kind == "company":
        record = Company(name="OEOC", code="OEOC")
        session.add(record)
        session.flush()
        return record.id
    if kind == "project":
        record = Project(name="Bid Boland", code="BB", company_id=parent)
        session.add(record)
        session.flush()
        return record.id
    record = Well(name="A-001", code="A-001", project_id=parent,
                  target_depth=3000.0)
    session.add(record)
    session.commit()
    return record.id


def _casing(manager, rows):
    manager.save_casing_report({
        "well_id": manager._test_well_id,
        "report_date": date(2024, 10, 1),
        "casing_type": "Surface",
        "casing_json": json.dumps(rows),
    })
    return SchematicAutoBuilder(manager).build_from_well(manager._test_well_id)


def test_schematic_skips_component_with_nonfinite_od(manager):
    # A nan od previously passed the `od is None or od <= 0` guard and a
    # fabricated casing element entered the schematic.
    schematic = _casing(manager, [
        {"od": "nan", "from": 0, "to": 500, "type": "Surface"},
        {"od": 13.375, "from": 0, "to": 500, "type": "Surface"},
    ])
    assert len(schematic.casings) == 1, "only the finite casing is built"
    assert schematic.casings[0].od_inch == 13.375


def test_schematic_skips_component_with_nonfinite_depths(manager):
    for row in ({"od": 13.375, "from": "nan", "to": 500, "type": "Surface"},
                {"od": 13.375, "from": 0, "to": "inf", "type": "Surface"},
                {"od": 13.375, "from": "1e400", "to": 500, "type": "Surface"}):
        schematic = _casing(manager, [row])
        assert schematic.casings == [], \
            f"a non-finite depth ({row}) must not fabricate schematic geometry"
