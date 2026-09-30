"""W3c section data must stay attached to the selected well and section."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

try:
    from PySide6.QtWidgets import QApplication  # noqa: F401
except ImportError as exc:  # pragma: no cover - host Qt runtime dependent
    pytest.skip(f"Qt runtime unavailable: {exc}", allow_module_level=True)


_CHILD = textwrap.dedent(
    """
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from datetime import date
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from core.database import Base, DatabaseManager, Company, Project, Well, Section

    db = DatabaseManager()
    db.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(db.engine)
    db.Session = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)
    session = db.create_session()
    company = Company(name="C", code="C"); session.add(company); session.flush()
    project = Project(name="P", company_id=company.id); session.add(project); session.flush()
    well = Well(name="W", code="W", project_id=project.id); session.add(well); session.flush()
    section_a = Section(well_id=well.id, name="Section A", depth_from=0, depth_to=1000)
    section_b = Section(well_id=well.id, name="Section B", depth_from=1000, depth_to=2000)
    empty_well = Well(name="W-empty", code="W-empty", project_id=project.id)
    session.add_all([section_a, section_b, empty_well]); session.commit()
    well_id, section_a_id, section_b_id, empty_well_id = well.id, section_a.id, section_b.id, empty_well.id
    session.close()

    # A real report in section A must not load into section B.
    db.save_cement_report({"well_id": well_id, "section_id": section_a_id,
                           "report_date": date(2026, 9, 1), "report_name": "A cement"})
    db.save_casing_report({"well_id": well_id, "section_id": section_a_id,
                           "report_date": date(2026, 9, 1), "report_name": "A casing"})

    from PySide6.QtWidgets import QApplication, QWidget
    app = QApplication.instance() or QApplication([])
    from tabs.w3c_section_data import SectionDataWidget
    parent = QWidget()
    widget = SectionDataWidget(db, parent=parent)
    assert widget._tabs_ready
    widget.current_well_id = well_id
    widget.current_section_id = section_a_id
    widget.cement_tab.current_well = well_id
    widget.casing_tab.current_well = well_id
    widget.cement_tab.load_data()
    widget.casing_tab.load_data()
    assert widget.cement_tab.report_name.text() == "A cement"
    assert widget.casing_tab.report_name.text() == "A casing"

    # A has data; B does not. Changing section must clear rather than leak A.
    widget.current_section_id = section_b_id
    widget.cement_tab.load_data()
    widget.casing_tab.load_data()
    assert widget.cement_tab.report_name.text() == ""
    assert widget.casing_tab.report_name.text() == ""

    # Saving now must attach the records to B, not create whole-well/null-section rows.
    widget.cement_tab.report_name.setText("B cement")
    widget.casing_tab.report_name.setText("B casing")
    assert widget.cement_tab.save_data()
    assert widget.casing_tab.save_data()
    cement_b = db.get_cement_report(section_id=section_b_id)
    casing_b = db.get_casing_report(section_id=section_b_id)
    assert cement_b and cement_b["report_name"] == "B cement"
    assert casing_b and casing_b["report_name"] == "B casing"
    assert cement_b["section_id"] == section_b_id and casing_b["section_id"] == section_b_id

    # A well switch drops the old section and every stale report/table value.
    widget.cement_tab.report_name.setText("Old form state")
    widget.casing_tab.report_name.setText("Old form state")
    widget.casing_tally_tab.tally_table.setRowCount(2)
    widget.casing_tally_tab.summary_text.setPlainText("Old tally")
    widget.bit_tab.bit_table.setRowCount(3)
    widget.on_well_changed(empty_well_id, {"name": "W-empty"})
    assert widget.current_section_id is None
    assert widget.cement_tab.report_name.text() == ""
    assert widget.casing_tab.report_name.text() == ""
    assert widget.casing_tally_tab.tally_table.rowCount() == 0
    assert widget.casing_tally_tab.summary_text.toPlainText() == ""
    assert widget.bit_tab.bit_table.rowCount() == 0
    widget.close()
    parent.close()
    app.processEvents()
    print("W3C_SECTION_SCOPE_OK")
    """
)


def test_w3c_section_load_save_and_well_switch_scope_in_isolated_qt_process():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-c", _CHILD], cwd=repo_root, env=env,
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0 or "W3C_SECTION_SCOPE_OK" not in result.stdout:
        pytest.fail(f"W3c section scope regression failed\n{result.stdout}\n{result.stderr}")
