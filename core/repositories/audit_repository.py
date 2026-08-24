"""Audit repository."""

from .base import BaseRepository
from core.database import AuditLog
from typing import List, Dict


class AuditRepository(BaseRepository):
    def log(self, action, entity_type="", entity_id=None, entity_name="", details="", user_id=None, username=""):
        from core.database import AuditLog
        from core.database import _now_utc
        with self.db.session_scope() as session:
            log = AuditLog(
                user_id=user_id,
                username=username,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_name=entity_name,
                details=details[:500] if details else "",
                timestamp=_now_utc(),
            )
            session.add(log)
