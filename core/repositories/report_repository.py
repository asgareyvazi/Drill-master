"""Report, TimeLog, Survey, BHA, Bit repositories."""

from .base import BaseRepository
from core.database import DailyReport, TimeLog24H, TimeLogMorning, SurveyPoint, BHAReport, BitReport
from core.import_quality import TimeLogValidator
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ReportRepository(BaseRepository):
    def get_by_identity(self, well_id: int, section_id: int, report_date) -> Optional[Dict]:
        with self.db.session_scope() as session:
            r = session.query(DailyReport).filter_by(well_id=well_id, section_id=section_id, report_date=report_date).first()
            if not r:
                return None
            return {c.name: getattr(r, c.name) for c in DailyReport.__table__.columns}

    def save_atomic(self, data: Dict, time_logs_24h: List[Dict] = None, time_logs_morning: List[Dict] = None) -> Dict:
        """Atomic save of report + time logs in one transaction."""
        # Validate time logs before save
        if time_logs_24h:
            report = TimeLogValidator.validate_logs(time_logs_24h, sheet="TimeLog24H")
            if report.errors:
                raise ValueError(f"TimeLog validation failed: {[e.message for e in report.errors]}")

        with self.db.session_scope() as session:
            report_id = data.get("id")
            if report_id:
                report_obj = session.get(DailyReport, report_id)
                if not report_obj:
                    raise ValueError(f"Report {report_id} not found")
                valid_keys = {c.name for c in DailyReport.__table__.columns}
                for k, v in data.items():
                    if k != "id" and k in valid_keys:
                        setattr(report_obj, k, v)
            else:
                valid_keys = {c.name for c in DailyReport.__table__.columns}
                filtered = {k: v for k, v in data.items() if k in valid_keys and k != "id"}
                report_obj = DailyReport(**filtered)
                session.add(report_obj)
                session.flush()
                report_id = report_obj.id

            # Time logs 24h - delete previous and insert new atomically
            if time_logs_24h is not None:
                session.query(TimeLog24H).filter(TimeLog24H.report_id == report_id).delete()
                for log in time_logs_24h:
                    if not isinstance(log, dict):
                        continue
                    if log.get("time_from") in (None, "") or log.get("time_to") in (None, ""):
                        continue  # skip separators
                    valid_keys = {c.name for c in TimeLog24H.__table__.columns}
                    filtered = {k: v for k, v in log.items() if k in valid_keys and k != "id"}
                    filtered["report_id"] = report_id
                    session.add(TimeLog24H(**filtered))

            if time_logs_morning is not None:
                session.query(TimeLogMorning).filter(TimeLogMorning.report_id == report_id).delete()
                for log in time_logs_morning:
                    if not isinstance(log, dict):
                        continue
                    if log.get("time_from") in (None, "") or log.get("time_to") in (None, ""):
                        continue
                    valid_keys = {c.name for c in TimeLogMorning.__table__.columns}
                    filtered = {k: v for k, v in log.items() if k in valid_keys and k != "id"}
                    filtered["report_id"] = report_id
                    session.add(TimeLogMorning(**filtered))

            session.flush()
            return {"id": report_id, "report_number": report_obj.report_number, "report_date": report_obj.report_date}


class SurveyRepository(BaseRepository):
    def save_points(self, points: List[Dict]) -> int:
        with self.db.session_scope() as session:
            saved = 0
            for p in points:
                if not isinstance(p, dict) or p.get("md") in (None, ""):
                    continue
                valid_keys = {c.name for c in SurveyPoint.__table__.columns}
                filtered = {k: v for k, v in p.items() if k in valid_keys and k != "id"}
                session.add(SurveyPoint(**filtered))
                saved += 1
            session.flush()
            return saved


class BHARepository(BaseRepository):
    def save(self, well_id: int, data: Dict) -> int:
        with self.db.session_scope() as session:
            report_id = data.get("report_id")
            if report_id:
                existing = session.query(BHAReport).filter(BHAReport.report_id == report_id).first()
                if existing:
                    existing.bha_name = data.get("bha_name", existing.bha_name)
                    existing.bha_data_json = data.get("bha_data", existing.bha_data_json)
                    session.flush()
                    return existing.id
            # create new
            obj = BHAReport(
                well_id=well_id,
                report_id=report_id,
                bha_name=data.get("bha_name", "Unnamed BHA"),
                bha_data_json=data.get("bha_data", {}),
            )
            session.add(obj)
            session.flush()
            return obj.id


class BitRepository(BaseRepository):
    def save(self, well_id: int, data: Dict) -> int:
        import json
        with self.db.session_scope() as session:
            report_id = data.get("report_id")
            bit_json = data.get("bit_records_json")
            if isinstance(bit_json, (dict, list)):
                bit_json = json.dumps(bit_json, ensure_ascii=False)
            if report_id:
                existing = session.query(BitReport).filter(BitReport.report_id == report_id).first()
                if existing:
                    existing.bit_records_json = bit_json or existing.bit_records_json
                    session.flush()
                    return existing.id
            obj = BitReport(
                well_id=well_id,
                report_id=report_id,
                report_date=data.get("report_date"),
                report_name=data.get("report_name", "Imported Bit"),
                bit_records_json=bit_json or "[]",
            )
            session.add(obj)
            session.flush()
            return obj.id
