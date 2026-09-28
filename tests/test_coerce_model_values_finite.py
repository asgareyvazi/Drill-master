"""P6 batch 017 (INV34-001111 / INV34-006908) — a non-finite number is unknown, not data.

`DatabaseManager.coerce_model_values` is the persistence boundary used by
`save_well`, the safety/BOP save paths and the DDR import service.  Before the
fix it only rejected *non-parsable* strings: `float()` accepts `'nan'`, `'inf'`,
`'-inf'` and `'1e400'`, so those values were written into authoritative numeric
columns.  SQLite round-trips `inf` unchanged and silently converts `nan` to
NULL, i.e. a meaningless number could be stored as a measurement.

The repository's canonical numeric persistence helpers all reject non-finite
values (`core/engineering/*_persistence.py`: ``number if math.isfinite(number)
else None``, `core/engineering/result.py`, `core/engineering/drill_pipe.py` with
the explicit comment "NaN / inf / 1e400 overflow"), as do
`core/value_normalizer.py`, the in-module helper `_number_value`
(`core/database.py`) and the waste-volume aggregation in
`tabs/w8_Safety_Widget.py` ("Invalid waste volume").  These tests pin that
contract at the database boundary: non-finite input becomes NULL (unknown),
an explicit zero stays zero, and text columns are never coerced.
"""

import math

import pytest

from core.database import Company, DatabaseManager, Project, Well


@pytest.mark.parametrize(
    "raw", ["nan", "NaN", "inf", "-inf", "INF", "Infinity", "1e400", "-1e400"]
)
def test_non_finite_strings_become_unknown(raw):
    out = DatabaseManager.coerce_model_values(Well, {"target_depth": raw})
    assert out["target_depth"] is None


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), float("-inf"), 1e400])
def test_non_finite_floats_become_unknown(raw):
    out = DatabaseManager.coerce_model_values(Well, {"target_depth": raw})
    assert out["target_depth"] is None


def test_finite_values_and_explicit_zero_survive():
    out = DatabaseManager.coerce_model_values(
        Well,
        {
            "target_depth": "0",
            "water_depth": " 12,5 ",
            "elevation": "1e3",
            "gle_msl": 0.0,
            "rte_msl": 7,
        },
    )
    assert out["target_depth"] == 0.0  # explicit zero, not NULL
    assert out["water_depth"] == 125.0  # comma decimal still parses
    assert out["elevation"] == 1000.0
    assert out["gle_msl"] == 0.0
    assert out["rte_msl"] == 7


def test_placeholders_and_text_columns_are_unchanged():
    out = DatabaseManager.coerce_model_values(
        Well, {"elevation": "-", "name": "nan", "code": "inf"}
    )
    assert out["elevation"] is None
    assert out["name"] == "nan"  # a text column is not a number
    assert out["code"] == "inf"


def test_save_well_persists_non_finite_input_as_null(tmp_path):
    db = DatabaseManager()
    db.db_path = str(tmp_path / "nonfinite.db")
    assert db.initialize()
    try:
        with db.session_scope() as session:
            company = Company(name="Finite Co", code="FIN")
            session.add(company)
            session.flush()
            project = Project(name="Finite Project", code="FIN-P", company_id=company.id)
            session.add(project)
            session.flush()
            project_id = project.id

        assert db.save_well({"project_id": project_id, "name": "Inf Well", "target_depth": "inf"})
        assert db.save_well(
            {"project_id": project_id, "name": "Finite Well", "target_depth": "1234.5"}
        )

        with db.session_scope() as session:
            assert session.query(Well).filter_by(name="Inf Well").one().target_depth is None
            assert (
                session.query(Well).filter_by(name="Finite Well").one().target_depth == 1234.5
            )
            for well in session.query(Well).all():
                assert well.target_depth is None or math.isfinite(well.target_depth)
    finally:
        db.close()
