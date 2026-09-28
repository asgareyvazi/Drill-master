"""Regression: the well-plan Excel importer must keep unknown cells unknown.

``PlanImportReviewDialog._parse_data`` (dialogs/planning_dialog.py) feeds the
W10 plan-review staging path, whose whole purpose is to let the planner review
imported assumptions ("Staged for review ... Review phase/depth assumptions").

The parser used to coerce BOTH an absent cell and an unparseable cell into a
planned ``0`` for every numeric plan field (interval/depth/rop/hours/days/
total_days), which contradicts the plan-input trichotomy the same codebase
states elsewhere:

* ``dialogs/planning_dialog.py`` consumer: ``_import_from_excel`` guards with
  ``interval is not None and depth is not None`` / ``depth is not None and
  cum_depth is not None`` / ``if depth_to is not None`` - i.e. it was written
  for ``None`` to be possible;
* ``core/text_utils.fmt_num``: "``default`` used to be ``0.0``, which printed a
  missing (NULL) engineering value as an explicit zero ... genuine unknown stays
  unknown" - and ``_refresh_table`` renders these very fields with
  ``default=None`` ("—") and derives the plan total with
  ``core.cost_semantics.complete_total``, which returns None unless *every*
  duration is a number.

So a blank duration cell was counted as a 0-hour activity in a "complete" plan
total, and a blank depth cell silently defined the plan's depth range as 0 m.

The real parser method is exercised here on a plain state object carrying only
the attributes it reads (``col_map``, ``cell_cache``, ``data_start_spin``,
``max_row``); the method touches no Qt widget, so no Qt object is faked.
"""
from __future__ import annotations

import types

from core.cost_semantics import complete_total
from core.text_utils import fmt_num
from dialogs.planning_dialog import PlanImportReviewDialog


def _parse(rows, col_map):
    """Run the real `_parse_data` over a cell cache built from ``rows``.

    ``rows`` maps a 1-based row index to {column index: cell value}; row 1 is
    the data start.  A cell that is absent from the cache is an absent cell.
    """
    state = types.SimpleNamespace(
        col_map=col_map,
        cell_cache={(r, c): v for r, cells in rows.items() for c, v in cells.items()},
        data_start_spin=types.SimpleNamespace(value=lambda: 1),
        max_row=max(rows),
    )
    return PlanImportReviewDialog._parse_data(state)


COL_MAP = {"activity": 1, "iadc_code": 2, "interval": 3, "formation": 4,
           "depth": 5, "rop": 6, "hours": 7, "days": 8, "total_days": 9}


def test_absent_numeric_cell_stays_unknown_never_zero():
    data = _parse(
        {1: {1: "Drilling 8.5in hole", 2: "DRLG", 4: "Aghajari", 5: "1000"}},
        COL_MAP,
    )
    assert len(data) == 1
    row = data[0]
    # present values survive as numbers
    assert row["depth"] == 1000.0
    # absent numeric cells are unknown, not planned zeros
    for key in ("interval", "rop", "hours", "days", "total_days"):
        assert row[key] is None, key
    # absent text cells keep the empty-string encoding
    assert row["formation"] == "Aghajari"


def test_unparseable_numeric_cell_is_unknown_not_zero():
    data = _parse(
        {1: {1: "Drilling 8.5in hole", 3: "n/a", 5: "1000", 6: "N/A",
             7: "12.5", 8: "", 9: "2.0"}},
        COL_MAP,
    )
    row = data[0]
    assert row["depth"] == 1000.0
    assert row["rop"] is None           # unparseable text
    assert row["interval"] is None      # unparseable text
    assert row["days"] is None          # empty string
    assert row["hours"] == 12.5         # a real planned duration survives
    assert row["total_days"] == 2.0


def test_explicit_zero_is_preserved_as_a_planned_zero():
    data = _parse(
        {1: {1: "Reaming", 3: "0", 5: "0", 6: "0", 7: "0", 8: "0", 9: "0"}},
        COL_MAP,
    )
    row = data[0]
    for key in ("interval", "depth", "rop", "hours", "days", "total_days"):
        assert row[key] == 0.0, key


def test_unknown_duration_invalidates_the_plan_total_and_renders_as_dash():
    data = _parse(
        {1: {1: "Drilling 8.5in hole", 5: "1000", 7: "12.5"},
         2: {1: "Reaming to TD", 5: "1100"}},
        COL_MAP,
    )
    durations = [row["hours"] for row in data]
    assert durations == [12.5, None]
    # the review table's own contracts: "—" for the unknown row, and no
    # "complete" total while one duration is unknown
    assert fmt_num(durations[1], 1, default=None) == "—"
    assert complete_total(durations) is None
    assert complete_total([12.5, 5.0]) == 17.5


def test_rows_without_activity_are_still_skipped():
    # row 1 has no activity cell at all -> skipped; row 2's activity is shorter
    # than the parser's 5-character noise floor -> skipped; row 3 is kept.
    data = _parse({1: {5: "1000", 7: "5"}, 2: {1: "Trip"}, 3: {1: "Short"}}, COL_MAP)
    assert [row["activity"] for row in data] == ["Short"]
