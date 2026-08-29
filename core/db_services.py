"""Database Services — domain-specific operations extracted from DatabaseManager.

These are standalone functions that accept a DatabaseManager instance.
They can be called from DatabaseManager methods or directly.

This enables incremental extraction without breaking the existing API.
"""

import json
import logging
from datetime import datetime, date, time, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ==================== Procedure Services ====================

def save_procedure(db, data: dict) -> int:
    """Save or update an operational procedure."""
    from core.db_models import OperationalProcedure
    session = db.create_session()
    try:
        if data.get('id'):
            proc = session.query(OperationalProcedure).filter(
                OperationalProcedure.id == data['id']
            ).first()
            if proc:
                for key, value in data.items():
                    if key != 'id' and hasattr(proc, key):
                        setattr(proc, key, value)
                proc.updated_at = _now_utc()
        else:
            proc = OperationalProcedure(**{
                k: v for k, v in data.items()
                if hasattr(OperationalProcedure, k)
            })
            session.add(proc)

        session.flush()
        proc_id = proc.id
        session.commit()
        return proc_id
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving procedure: {e}")
        return None
    finally:
        session.close()


def get_procedures_by_well(db, well_id: int) -> list:
    """Get all procedures for a well."""
    from core.db_models import OperationalProcedure
    session = db.create_session()
    try:
        procs = session.query(OperationalProcedure).filter(
            OperationalProcedure.well_id == well_id
        ).order_by(OperationalProcedure.created_at.desc()).all()

        return [{
            "id": p.id, "title": p.title, "procedure_type": p.procedure_type,
            "revision": p.revision, "revision_date": p.revision_date,
            "status": p.status, "prepared_by": p.prepared_by,
            "approved_by": p.approved_by, "created_at": p.created_at,
        } for p in procs]
    except Exception as e:
        logger.error(f"Error getting procedures: {e}")
        return []
    finally:
        session.close()


def get_procedure_by_id(db, proc_id: int) -> dict:
    """Get a single procedure with all fields."""
    from core.db_models import OperationalProcedure
    session = db.create_session()
    try:
        p = session.query(OperationalProcedure).filter(
            OperationalProcedure.id == proc_id
        ).first()
        if not p:
            return None
        return {
            "id": p.id, "well_id": p.well_id, "section_id": p.section_id,
            "title": p.title, "procedure_type": p.procedure_type,
            "revision": p.revision, "revision_date": p.revision_date,
            "rig_name": p.rig_name, "well_name": p.well_name,
            "field_name": p.field_name, "status": p.status,
            "prepared_by": p.prepared_by, "checked_by": p.checked_by,
            "approved_by": p.approved_by, "objective": p.objective,
            "hse_focus": p.hse_focus, "general_notes": p.general_notes,
            "created_at": p.created_at,
        }
    except Exception as e:
        logger.error(f"Error getting procedure: {e}")
        return None
    finally:
        session.close()


def delete_procedure(db, proc_id: int) -> bool:
    from core.db_models import OperationalProcedure
    session = db.create_session()
    try:
        p = session.query(OperationalProcedure).filter(
            OperationalProcedure.id == proc_id
        ).first()
        if p:
            session.delete(p)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting procedure: {e}")
        return False
    finally:
        session.close()


def save_procedure_steps(db, proc_id: int, steps: list) -> bool:
    from core.db_models import ProcedureStep
    session = db.create_session()
    try:
        session.query(ProcedureStep).filter(
            ProcedureStep.procedure_id == proc_id
        ).delete()
        for i, step in enumerate(steps):
            s = ProcedureStep(
                procedure_id=proc_id, step_number=i + 1,
                activity_description=step.get('activity_description', ''),
                parallel_activities=step.get('parallel_activities', ''),
                caution_notes=step.get('caution_notes', ''),
                is_completed=step.get('is_completed', False),
                completed_by=step.get('completed_by', ''),
                remarks=step.get('remarks', ''),
            )
            session.add(s)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving steps: {e}")
        return False
    finally:
        session.close()


def get_procedure_steps(db, proc_id: int) -> list:
    from core.db_models import ProcedureStep
    session = db.create_session()
    try:
        steps = session.query(ProcedureStep).filter(
            ProcedureStep.procedure_id == proc_id
        ).order_by(ProcedureStep.step_number).all()
        return [{
            "id": s.id, "step_number": s.step_number,
            "activity_description": s.activity_description,
            "parallel_activities": s.parallel_activities,
            "caution_notes": s.caution_notes,
            "is_completed": s.is_completed, "completed_by": s.completed_by,
            "completed_at": s.completed_at, "remarks": s.remarks,
        } for s in steps]
    except Exception as e:
        logger.error(f"Error getting steps: {e}")
        return []
    finally:
        session.close()


def save_checklist_items(db, proc_id: int, items: list) -> bool:
    from core.db_models import ProcedureChecklist
    session = db.create_session()
    try:
        session.query(ProcedureChecklist).filter(
            ProcedureChecklist.procedure_id == proc_id
        ).delete()
        for i, item in enumerate(items):
            c = ProcedureChecklist(
                procedure_id=proc_id, category=item.get('category', ''),
                item_description=item.get('item_description', ''),
                responsible=item.get('responsible', ''),
                verified=item.get('verified', False),
                verified_by=item.get('verified_by', ''),
                not_applicable=item.get('not_applicable', False),
                remarks=item.get('remarks', ''), sort_order=i,
            )
            session.add(c)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving checklist: {e}")
        return False
    finally:
        session.close()


def get_checklist_items(db, proc_id: int) -> list:
    from core.db_models import ProcedureChecklist
    session = db.create_session()
    try:
        items = session.query(ProcedureChecklist).filter(
            ProcedureChecklist.procedure_id == proc_id
        ).order_by(ProcedureChecklist.sort_order).all()
        return [{
            "id": i.id, "category": i.category,
            "item_description": i.item_description,
            "responsible": i.responsible, "verified": i.verified,
            "verified_by": i.verified_by, "verified_at": i.verified_at,
            "not_applicable": i.not_applicable, "remarks": i.remarks,
        } for i in items]
    except Exception as e:
        logger.error(f"Error getting checklist: {e}")
        return []
    finally:
        session.close()


# ==================== Logistics Services ====================

def save_logistics_personnel(db, data: dict):
    from core.db_models import LogisticsPersonnel
    session = db.create_session()
    try:
        if data.get('id'):
            obj = session.query(LogisticsPersonnel).filter(LogisticsPersonnel.id == data['id']).first()
            if obj:
                for k, v in data.items():
                    if k != 'id' and hasattr(obj, k):
                        setattr(obj, k, v)
                obj.updated_at = _now_utc()
                session.commit()
                return obj.id
        valid = {c.name for c in LogisticsPersonnel.__table__.columns}
        filtered = {k: v for k, v in data.items() if k in valid and k != 'id'}
        obj = LogisticsPersonnel(**filtered)
        session.add(obj)
        session.flush()
        session.commit()
        return obj.id
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving logistics personnel: {e}")
        return None
    finally:
        session.close()


def get_logistics_personnel(db, well_id=None, section_id=None, report_id=None):
    from core.db_models import LogisticsPersonnel
    session = db.create_session()
    try:
        q = session.query(LogisticsPersonnel)
        if report_id:
            q = q.filter(LogisticsPersonnel.report_id == report_id)
        elif well_id:
            q = q.filter(LogisticsPersonnel.well_id == well_id)
        if section_id:
            q = q.filter(LogisticsPersonnel.section_id == section_id)
        return [{col.name: getattr(r, col.name) for col in LogisticsPersonnel.__table__.columns} for r in q.all()]
    except Exception as e:
        logger.error(f"Error getting logistics personnel: {e}")
        return []
    finally:
        session.close()


def delete_logistics_personnel(db, obj_id: int):
    from core.db_models import LogisticsPersonnel
    session = db.create_session()
    try:
        obj = session.query(LogisticsPersonnel).filter(LogisticsPersonnel.id == obj_id).first()
        if obj:
            session.delete(obj)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting logistics personnel: {e}")
        return False
    finally:
        session.close()


def save_service_company_pob(db, data: dict):
    from core.db_models import ServiceCompanyPOB
    session = db.create_session()
    try:
        if data.get('id'):
            obj = session.query(ServiceCompanyPOB).filter(ServiceCompanyPOB.id == data['id']).first()
            if obj:
                for k, v in data.items():
                    if k != 'id' and hasattr(obj, k):
                        setattr(obj, k, v)
                obj.updated_at = _now_utc()
                session.commit()
                return obj.id
        valid = {c.name for c in ServiceCompanyPOB.__table__.columns}
        filtered = {k: v for k, v in data.items() if k in valid and k != 'id'}
        obj = ServiceCompanyPOB(**filtered)
        session.add(obj)
        session.flush()
        session.commit()
        return obj.id
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving POB: {e}")
        return None
    finally:
        session.close()


def get_service_company_pob(db, well_id=None, section_id=None, report_id=None):
    from core.db_models import ServiceCompanyPOB
    session = db.create_session()
    try:
        q = session.query(ServiceCompanyPOB)
        if report_id:
            q = q.filter(ServiceCompanyPOB.report_id == report_id)
        elif well_id:
            q = q.filter(ServiceCompanyPOB.well_id == well_id)
        if section_id:
            q = q.filter(ServiceCompanyPOB.section_id == section_id)
        return [{col.name: getattr(r, col.name) for col in ServiceCompanyPOB.__table__.columns} for r in q.all()]
    except Exception as e:
        logger.error(f"Error getting POB: {e}")
        return []
    finally:
        session.close()


def calculate_total_pob(db, well_id=None, section_id=None, report_id=None):
    from core.db_models import ServiceCompanyPOB
    session = db.create_session()
    try:
        q = session.query(ServiceCompanyPOB)
        if report_id:
            q = q.filter(ServiceCompanyPOB.report_id == report_id)
        elif well_id:
            q = q.filter(ServiceCompanyPOB.well_id == well_id)
        if section_id:
            q = q.filter(ServiceCompanyPOB.section_id == section_id)
        return sum(p.personnel_count for p in q.all())
    except Exception as e:
        logger.error(f"Error calculating POB: {e}")
        return 0
    finally:
        session.close()


def delete_service_company_pob(db, pob_id: int):
    from core.db_models import ServiceCompanyPOB
    session = db.create_session()
    try:
        obj = session.query(ServiceCompanyPOB).filter(ServiceCompanyPOB.id == pob_id).first()
        if obj:
            session.delete(obj)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting POB: {e}")
        return False
    finally:
        session.close()
