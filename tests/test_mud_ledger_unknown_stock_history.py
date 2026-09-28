"""Mud-ledger history must survive an unknown stock (missing opening).

Defect proven here (core/mud_ledger.py, ``MudChemicalLedger.get_history``):

    stocks = [float(m.closing_stock) for m in mats_sorted]

``LedgerEntry.closing_stock`` is ``Optional[float]`` by contract - the module
states the trichotomy "None = opening not reported (missing) ... An unknown
opening propagates to an unknown closing (None) - it is never silently replaced
by 0" (core/mud_ledger.py:24-27) and ``validate()`` explicitly tolerates that
state ("Unknown opening/closing: no stock judgment is possible", 140-141).
``float(None)`` raised ``TypeError``, so the whole history call - and with it
the ``check_mud_ledger`` AI tool that also returns the entries and the alerts
from the same call (core/ai_tools.py:283-293) - failed as soon as ONE material
had one entry with an unreported opening, i.e. in a documented, normal data
state that the sibling method already handles on purpose.

The fix keeps the unknown unknown: the ``stock_trend`` series stays aligned
with ``dates`` (one sample per reported day) and carries ``None`` where the
closing is unknown, ``closing_stock``/``days_remaining`` are ``None`` rather
than a fabricated 0.0 ("stock exhausted today"), while an *explicit* zero stock
stays a real ``0.0`` fact.

Every test uses the real production code (``MudChemicalLedger``,
``AIToolRegistry.call_tool``) against an isolated in-memory database.

Regression discipline: this file fails on the pre-fix code (TypeError) and also
fails if the unknown is coerced to 0.0 instead of preserved.
"""

from datetime import date

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.ai_tools import AIToolRegistry
from core.database import (
    Base, DatabaseManager, BulkMaterials, Company, Project, Well, Section,
    DailyReport,
)
from core.mud_ledger import MudChemicalLedger


@pytest.fixture()
def env():
    manager = DatabaseManager()
    manager.engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(manager.engine)
    manager.Session = sessionmaker(
        bind=manager.engine, autoflush=False, autocommit=False
    )
    session = manager.create_session()
    try:
        company = Company(name="OEOC", code="OEOC")
        session.add(company)
        session.flush()
        project = Project(name="P", company_id=company.id)
        session.add(project)
        session.flush()
        well = Well(name="W-1", project_id=project.id)
        session.add(well)
        session.flush()
        section = Section(name="S", well_id=well.id)
        session.add(section)
        session.flush()
        report = DailyReport(well_id=well.id, section_id=section.id,
                             report_date=date(2024, 10, 1))
        session.add(report)
        session.commit()
        well_id = well.id
    finally:
        session.close()
    return manager, well_id


def _add_row(manager, well_id, d, initial, received, used):
    session = manager.create_session()
    try:
        session.add(BulkMaterials(
            well_id=well_id, report_date=d, material_name="Barite",
            unit="kg", initial_stock=initial, received=received, used=used,
            current_stock=(initial + received - used if initial is not None else None),
        ))
        session.commit()
    finally:
        session.close()


def test_history_keeps_unknown_stock_unknown(env):
    """Pre-fix this raised TypeError: float(None)."""
    manager, well_id = env
    # Day 1: opening not reported -> closing unknown (None by contract).
    # Day 2: opening known, so the day itself IS judged.
    _add_row(manager, well_id, date(2024, 10, 1), None, 0.0, 5.0)
    _add_row(manager, well_id, date(2024, 10, 2), 40.0, 0.0, 10.0)

    history = MudChemicalLedger(manager).get_history(well_id)
    entry = history["Barite"]

    # Unknown stays unknown - not 0.0, and the series is not silently shortened.
    assert entry["stock_trend"] == [None, 30.0]
    assert len(entry["stock_trend"]) == len(entry["dates"]) == 2
    assert entry["daily_usage_chart"] == [5.0, 10.0]
    # Opening of the first (unreported) day is still reported as unknown.
    assert entry["opening_stock"] is None

    # The last day IS known (30.0) - so the runway is real, not blanked out.
    assert entry["closing_stock"] == 30.0
    assert entry["consumption_rate"] == 7.5
    assert entry["days_remaining"] == 4.0


def test_history_unknown_last_stock_has_no_runway(env):
    """An unknown latest stock must not become a 0-day runway."""
    manager, well_id = env
    _add_row(manager, well_id, date(2024, 10, 1), None, 0.0, 5.0)
    _add_row(manager, well_id, date(2024, 10, 2), None, 0.0, 5.0)

    entry = MudChemicalLedger(manager).get_history(well_id)["Barite"]

    assert entry["stock_trend"] == [None, None]
    assert entry["closing_stock"] is None
    assert entry["days_remaining"] is None          # unknown, never 0.0
    assert entry["received_vs_used"] == {"total_received": 0.0, "total_used": 10.0}


def test_history_explicit_zero_stays_a_fact(env):
    """The other direction: an explicit zero stock is 0.0, not 'unknown'."""
    manager, well_id = env
    _add_row(manager, well_id, date(2024, 10, 1), 10.0, 0.0, 10.0)  # closing 0.0
    _add_row(manager, well_id, date(2024, 10, 2), None, 0.0, 0.0)   # unreported

    entry = MudChemicalLedger(manager).get_history(well_id)["Barite"]

    # Day 2 has no stored opening, so the documented carry-forward fills it
    # from the previous closing (0.0) - an explicit zero, not an unknown.
    assert entry["stock_trend"] == [0.0, 0.0]
    assert entry["closing_stock"] == 0.0
    # No consumption at all: the pre-existing "no consumption -> 0" rule stands
    # (changing it would be a separate product decision, not this fix).
    assert entry["days_remaining"] == 0


def test_ai_tool_check_mud_ledger_reports_entries_and_alerts(env):
    """The real caller path: a failed history call loses entries + alerts too."""
    manager, well_id = env
    _add_row(manager, well_id, date(2024, 10, 1), None, 0.0, 5.0)
    _add_row(manager, well_id, date(2024, 10, 2), 10.0, 0.0, 40.0)

    result = AIToolRegistry(manager).call_tool("check_mud_ledger", well_id=well_id)

    assert result["success"] is True, result
    assert len(result["entries"]) == 2
    # Day 1: nothing to carry forward -> unknown stays unknown. Day 2 has a
    # stored opening (10) and a real over-consumption (40) -> -30.0, which is
    # a declared fact and must stay visible (never smoothed to None/0).
    assert result["history"]["Barite"]["stock_trend"] == [None, -30.0]
    # The known row still raises its designed alert; the unknown row does not.
    assert "Unusual Consumption" in [a["type"] for a in result["alerts"]]


def test_check_continuity_ignores_unknown_stock(env):
    """Same class inside the module: comparing None to None raised TypeError."""
    manager, well_id = env
    _add_row(manager, well_id, date(2024, 10, 1), None, 0.0, 5.0)   # closing None
    _add_row(manager, well_id, date(2024, 10, 2), 10.0, 0.0, 0.0)
    _add_row(manager, well_id, date(2024, 10, 3), 10.0, 0.0, 0.0)

    issues = MudChemicalLedger(manager).check_continuity(well_id)

    # No stock judgment is possible for the unknown pair; the two known days
    # are continuous (10 -> 10), so nothing is reported at all.
    assert issues == []
