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


CHILD_SETUP_FULL = CHILD_SETUP + """
from datetime import time
from core.database import TimeLog24H, DrillingParameters, MudReport, SurveyPoint

def add_children(db, ids):
    s = db.create_session()
    rid = ids["report"]; w = ids["well"]
    s.add(TimeLog24H(report_id=rid, time_from=time(6,0), time_to=time(12,0), duration=6.0, main_phase="Drilling", is_npt=False, activity_description="drill ahead"))
    s.add(TimeLog24H(report_id=rid, time_from=time(0,0), time_to=time(6,0), duration=6.0, main_phase="Circulate", is_npt=True, activity_description="stuck pipe"))
    s.add(DrillingParameters(report_id=rid, well_id=w, report_date=date(2026,9,1), depth_in=100.0, depth_out=200.0))
    s.add(MudReport(report_id=rid, well_id=w, report_date=date(2026,9,1)))
    s.add(SurveyPoint(report_id=rid, well_id=w, md=150.0))
    s.commit(); s.close()
"""


def test_history_shows_structured_operational_content():
    """§27/§29 — the selected revision renders real child sections, not just JSON."""
    out = _run(CHILD_SETUP_FULL + """
from PySide6.QtWidgets import QApplication, QTreeWidget
app = QApplication.instance() or QApplication([])
db, ids = make_db()
add_children(db, ids)
db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
from dialogs.report_history_dialog import ReportHistoryDialog
dlg = ReportHistoryDialog(db, ids["report"])
trees = dlg.findChildren(QTreeWidget)
tree = trees[0]
# collect top-level section labels
labels = []
root = tree.invisibleRootItem()
for i in range(root.childCount()):
    labels.append(root.child(i).text(0))
print("SECTIONS", labels)
""")
    assert "Report Header" in out
    assert "Time Log (24h)" in out
    assert "Drilling Parameters" in out
    assert "Survey" in out


def test_history_no_live_data_leak():
    """§30 — after modifying current children, the old revision is unchanged."""
    out = _run(CHILD_SETUP_FULL + """
from PySide6.QtWidgets import QApplication, QTreeWidget
from core.database import TimeLog24H
app = QApplication.instance() or QApplication([])
db, ids = make_db()
add_children(db, ids)
db.transition_report(ids["report"], "submit", has_permission=ENG, user_id=ids["eng"])
# delete all current time logs after the snapshot was captured
s = db.create_session()
s.query(TimeLog24H).filter_by(report_id=ids["report"]).delete()
s.commit(); s.close()
from dialogs.report_history_dialog import ReportHistoryDialog
dlg = ReportHistoryDialog(db, ids["report"])
tree = dlg.findChildren(QTreeWidget)[0]
root = tree.invisibleRootItem()
tl = None
for i in range(root.childCount()):
    if root.child(i).text(0) == "Time Log (24h)":
        tl = root.child(i)
print("TL_PRESENT", tl is not None)
print("TL_ROWS", tl.childCount() if tl else 0)
""")
    assert "TL_PRESENT True" in out
    assert "TL_ROWS 2" in out  # historical revision still has the 2 rows
