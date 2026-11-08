"""D60: W9 "Update Status" announced a saved status and saved nothing.

Found in the post-M140 lint review (an unused ``request_data`` in ``edit_material_request``). The dialog showed
"Status updated to …" while the database kept the old status. Now the status is written through
``save_material_request`` and the message reports the real outcome. Synthetic data only.
"""
from __future__ import annotations

import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QInputDialog  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from core.database import Base, Company, DatabaseManager, Project, Well  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def world(app):
    db = DatabaseManager()
    db.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(db.engine)
    db.Session = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)
    s = db.create_session()
    company = Company(name="SYN C", code="SC")
    s.add(company)
    s.flush()
    project = Project(name="SYN P", company_id=company.id)
    s.add(project)
    s.flush()
    wells = [Well(name="SYN-W1", project_id=project.id), Well(name="SYN-W2", project_id=project.id)]
    s.add_all(wells)
    s.commit()
    w1, w2 = wells[0].id, wells[1].id
    s.close()
    own = db.save_material_request({"well_id": w1, "request_date": date(2026, 5, 1), "requested_items": "SYN bits",
                                    "status": "Pending"})
    foreign = db.save_material_request({"well_id": w2, "request_date": date(2026, 5, 1),
                                        "requested_items": "SYN casing", "status": "Pending"})
    from tabs.w9_Services_Widget import MaterialHandlingTab
    tab = MaterialHandlingTab(db)
    tab.current_well_id, tab.current_report_id = w1, None
    tab.load_material_requests()
    messages = []
    tab.status_manager.show_success = lambda _src, text: messages.append(("success", text))
    tab.status_manager.show_error = lambda _src, text: messages.append(("error", text))
    yield {"db": db, "tab": tab, "own": own, "foreign": foreign, "w1": w1, "w2": w2, "messages": messages}
    tab.deleteLater()


def _status(db, well_id, request_id):
    return {r["id"]: r["status"] for r in db.get_material_requests(well_id=well_id)}[request_id]


def test_the_chosen_status_is_saved_shown_in_the_table_and_reported(world, monkeypatch):
    tab, db = world["tab"], world["db"]
    asked = []

    def choose(_parent, _title, _label, items, current, _editable):
        asked.append(items[current])
        return "Partially Received", True
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(choose))
    tab.requests_table.setCurrentCell(0, 0)
    tab.edit_material_request()
    assert asked == ["Pending"]                                   # the picker starts at the stored status
    assert _status(db, world["w1"], world["own"]) == "Partially Received"
    assert tab.requests_table.item(0, 8).text() == "Partially Received"
    assert world["messages"] == [("success", f"Request #{world['own']}: status updated to Partially Received")]
    tab.requests_table.setCurrentCell(0, 0)
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(choose))
    tab.edit_material_request()
    assert asked[-1] == "Partially Received"


def test_cancel_saves_nothing_and_says_nothing(world, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a: ("Closed", False)))
    world["tab"].requests_table.setCurrentCell(0, 0)
    world["tab"].edit_material_request()
    assert _status(world["db"], world["w1"], world["own"]) == "Pending" and world["messages"] == []


def test_a_failed_save_is_reported_as_not_updated(world, monkeypatch):
    monkeypatch.setattr(world["db"], "save_material_request", lambda data: None)
    assert world["tab"].update_material_request_status(world["own"], "Closed") is False
    assert world["messages"] == [("error", f"Request #{world['own']}: status was NOT updated")]
    assert _status(world["db"], world["w1"], world["own"]) == "Pending"


def test_a_request_of_another_well_is_refused(world):
    assert world["tab"].update_material_request_status(world["foreign"], "Closed") is False
    assert _status(world["db"], world["w2"], world["foreign"]) == "Pending"
    kind, text = world["messages"][-1]
    assert kind == "error" and "not a request of the selected well" in text


def test_without_a_selected_well_nothing_is_saved(world):
    tab = world["tab"]
    refused = []
    tab.show_well_selection_error = lambda: refused.append(True)
    tab.current_well_id = None
    assert tab.update_material_request_status(world["own"], "Closed") is False
    assert refused == [True] and world["messages"] == []
    assert _status(world["db"], world["w1"], world["own"]) == "Pending"
