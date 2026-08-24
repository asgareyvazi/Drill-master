"""Safety, BOP, Waste repositories."""

from .base import BaseRepository
from core.database import SafetyReport, BOPComponent, WasteRecord
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class SafetyRepository(BaseRepository):
    pass


class BOPRepository(BaseRepository):
    def check_due_tests(self, well_id: int, interval_days: int = 14) -> List[Dict]:
        """Configurable test interval, not hard-coded."""
        from datetime import date, timedelta
        with self.db.session_scope() as session:
            comps = session.query(BOPComponent).filter(BOPComponent.well_id == well_id).all()
            due = []
            today = date.today()
            for c in comps:
                if not c.last_test_date:
                    due.append({"id": c.id, "component": c.component_name, "reason": "No test history"})
                    continue
                next_due = c.last_test_date + timedelta(days=interval_days)
                if next_due <= today:
                    due.append(
                        {
                            "id": c.id,
                            "component": c.component_name,
                            "last_test": c.last_test_date,
                            "next_due": next_due,
                            "days_overdue": (today - next_due).days,
                        }
                    )
            return due
