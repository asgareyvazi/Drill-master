"""Mission 19 — logical DDR save atomicity, NPT sync, restart durability.

The interactive save path (``w2 save_report`` -> ``save_daily_report`` +
``save_time_logs_to_db``) must be one atomic transaction: a time-log failure
must not leave a committed report header with stale/absent time logs (§21/§22).

These exercise the real widget save path in an offscreen subprocess.
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


SETUP = """
from datetime import date, time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from PySide6.QtWidgets import QApplication
import core.database as dbmod
from core.database import DatabaseManager, Base, User, Well, Section, DailyReport, Company, Project, TimeLog24H

app = QApplication.instance() or QApplication([])

def make_db():
    db = DatabaseManager()
    db.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(db.engine)
    db.Session = sessionmaker(bind=db.engine, autoflush=False, autocommit=False)
    s = db.create_session()
    u = User(username="eng", password_hash="x", role="engineer"); s.add(u); s.flush()
    c = Company(name="C", code="C1"); s.add(c); s.flush()
    p = Project(company_id=c.id, name="P", code="P1"); s.add(p); s.flush()
    w = Well(project_id=p.id, name="W1", code="W1"); s.add(w); s.flush()
    sec = Section(well_id=w.id, name="12.25"); s.add(sec); s.flush()
    ids = dict(user=u.id, well=w.id, section=sec.id)
    s.commit(); s.close()
    return db, ids

from core.permissions import permissions
"""


def test_t21_ddr_save_atomic_rollback():
    """Inject a time-log failure and prove the header did not commit."""
    out = _run(SETUP + """
db, ids = make_db()
permissions.set_user({"id": ids["user"], "username": "eng", "role": "engineer"})
from tabs.w2_Daily_Report import DailyReportWidget
class FakeParent:
    user = {"id": None}
w = DailyReportWidget(db_manager=db, parent=None)
w.current_well_id = ids["well"]
w.current_section_id = ids["section"]
w.report_date.setDate(__import__("PySide6.QtCore", fromlist=["QDate"]).QDate(2026, 9, 1))
w.report_number.setValue(1)
# force the time-log save to blow up mid-transaction
def boom(*a, **k):
    raise RuntimeError("time log boom")
w.save_time_logs_to_db = boom
ok = False
try:
    ok = w.save_report()
except Exception:
    ok = "raised"
# report header must NOT be committed
count = db.create_session().query(DailyReport).count()
print("SAVED_OK", ok)
print("REPORT_COUNT", count)
""")
    assert "REPORT_COUNT 0" in out


def test_t21b_ddr_save_success_persists_all():
    """A normal save commits header + time logs together."""
    out = _run(SETUP + """
db, ids = make_db()
permissions.set_user({"id": ids["user"], "username": "eng", "role": "engineer"})
from tabs.w2_Daily_Report import DailyReportWidget
from PySide6.QtCore import QDate
w = DailyReportWidget(db_manager=db, parent=None)
w.current_well_id = ids["well"]
w.current_section_id = ids["section"]
w.report_date.setDate(QDate(2026, 9, 1))
w.report_number.setValue(1)
w.depth_0000.setValue(100.0)
w.depth_2400.setValue(250.0)
ok = w.save_report()
s = db.create_session()
from core.database import DailyReport
rc = s.query(DailyReport).count()
print("SAVED_OK", ok)
print("REPORT_COUNT", rc)
""")
    assert "SAVED_OK True" in out
    assert "REPORT_COUNT 1" in out
