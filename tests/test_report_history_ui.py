"""UI-level tests for the Daily Report history dialog and workflow controls.

Runs in an offscreen subprocess (never in the shared pytest interpreter — real
QWidget construction there aborts the process). Verifies the revision/approval
history dialog renders both streams with real rows and honest empty states.
"""
import os
import subprocess
import sys
import textwrap

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(child: str):
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = REPO
    env.setdefault("LD_LIBRARY_PATH", "/home/user/qt-libs")
    result = subprocess.run([sys.executable, "-c", textwrap.dedent(child)],
                            capture_output=True, text=True, cwd=REPO, env=env)
    assert result.returncode == 0, f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    return result.stdout


CHILD_SETUP = """
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from core.database import DatabaseManager, Base, User, Well, Section, DailyReport, Company, Project

def make_db():
    db = DatabaseManager()
    db.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(db.engine)
    db.Session = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)
    s = db.create_session()
    eng = User(username="eng", password_hash="x", role="engineer"); s.add(eng); s.flush()
    sup = User(username="sup", password_hash="x", role="supervisor"); s.add(sup); s.flush()
    c = Company(name="C", code="C1"); s.add(c); s.flush()
    p = Project(company_id=c.id, name="P", code="P1"); s.add(p); s.flush()
    w = Well(project_id=p.id, name="W1", code="W1"); s.add(w); s.flush()
    sec = Section(well_id=w.id, name="12.25"); s.add(sec); s.flush()
    r = DailyReport(well_id=w.id, section_id=sec.id, report_number=1, report_date=date(2026,9,1), status="Draft"); s.add(r); s.flush()
    ids = dict(eng=eng.id, sup=sup.id, report=r.id, well=w.id, section=sec.id)
    s.commit(); s.close()
    return db, ids

ENG = lambda pp: pp in {"can_edit_reports", "can_export"}
SUP = lambda pp: pp in {"can_edit_reports", "can_approve_reports", "can_export"}
"""


def test_history_dialog_populated():
    out = _run(CHILD_SETUP + """
from PySide6.QtWidgets import QApplication, QTableWidget
app = QApplication.instance() or QApplication([])
db, ids = make_db()
db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
db.transition_report(ids["report"], "reject", has_permission=SUP, user_id=ids["sup"], comment="fix depth")
db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
from dialogs.report_history_dialog import ReportHistoryDialog
dlg = ReportHistoryDialog(db, ids["report"])
tables = dlg.findChildren(QTableWidget)
rev_rows = tables[0].rowCount()
app_rows = tables[1].rowCount()
# 3 revisions, 3 approval actions
print("REV", rev_rows)
print("APP", app_rows)
# actor names resolved (not raw ids)
cell = tables[1].item(0, 3).text()
print("ACTOR", cell)
""")
    assert "REV 3" in out
    assert "APP 3" in out
    assert "ACTOR eng" in out or "ACTOR sup" in out


def test_history_dialog_empty_state():
    out = _run(CHILD_SETUP + """
from PySide6.QtWidgets import QApplication, QLabel
app = QApplication.instance() or QApplication([])
db, ids = make_db()
from dialogs.report_history_dialog import ReportHistoryDialog
dlg = ReportHistoryDialog(db, ids["report"])
labels = [l.text() for l in dlg.findChildren(QLabel)]
print("LABELS", labels)
""")
    assert "No revision history available." in out
    assert "No approval history available." in out
