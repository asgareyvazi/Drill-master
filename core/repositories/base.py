"""Base Repository - abstracts session handling for domain repositories."""

from typing import List, Dict, Optional, Any
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with Unit of Work pattern."""

    def __init__(self, db_manager):
        self.db = db_manager

    @contextmanager
    def session(self):
        with self.db.session_scope() as s:
            yield s

    def save(self, model, data: dict) -> Optional[int]:
        """Generic save with column filtering."""
        valid = {c.name for c in model.__table__.columns}
        values = {k: v for k, v in (data or {}).items() if k in valid and k != "id"}
        with self.db.session_scope() as session:
            obj_id = data.get("id") if data and data.get("id") else None
            obj = session.get(model, obj_id) if obj_id else None
            if obj is None:
                obj = model(**values)
                session.add(obj)
                session.flush()
            else:
                for k, v in values.items():
                    setattr(obj, k, v)
                session.flush()
            return obj.id

    def get_by_id(self, model, obj_id: int) -> Optional[Dict]:
        with self.db.session_scope() as session:
            obj = session.get(model, obj_id)
            if not obj:
                return None
            return {c.name: getattr(obj, c.name) for c in model.__table__.columns}

    def get_list(self, model, filters: Dict = None, limit: Optional[int] = None) -> List[Dict]:
        with self.db.session_scope() as session:
            query = session.query(model)
            for k, v in (filters or {}).items():
                if hasattr(model, k):
                    query = query.filter(getattr(model, k) == v)
            if limit:
                query = query.limit(int(limit))
            return [{c.name: getattr(r, c.name) for c in model.__table__.columns} for r in query.all()]

    def delete(self, model, obj_id: int) -> bool:
        with self.db.session_scope() as session:
            obj = session.get(model, obj_id)
            if not obj:
                return False
            session.delete(obj)
            return True
