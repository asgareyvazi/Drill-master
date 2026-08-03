# core/permissions.py
"""
Permission Manager - کنترل دسترسی نقش‌ها
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PermissionManager:
    """Singleton مدیریت دسترسی"""
    _instance = None
    _user = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def set_user(self, user_data: dict):
        self._user = user_data

    @property
    def user(self):
        return self._user

    @property
    def role(self):
        if not self._user:
            return "viewer"
        return self._user.get("role", "viewer")

    @property
    def username(self):
        if not self._user:
            return "unknown"
        return self._user.get("username", "unknown")

    @property
    def user_id(self):
        if not self._user:
            return None
        return self._user.get("id")

    def has_permission(self, permission: str) -> bool:
        if not self._user:
            return False
        if self.role == "admin":
            return True
        perms = self._user.get("permissions", {})
        if isinstance(perms, dict):
            return perms.get(permission, False)
        return False

    def can_create_well(self) -> bool:
        return self.has_permission("can_create_well")

    def can_delete_well(self) -> bool:
        return self.has_permission("can_delete_well")

    def can_edit_reports(self) -> bool:
        return self.has_permission("can_edit_reports")

    def can_approve_reports(self) -> bool:
        return self.has_permission("can_approve_reports")

    def can_manage_users(self) -> bool:
        return self.has_permission("can_manage_users")

    def can_export(self) -> bool:
        return self.has_permission("can_export")

    def can_import(self) -> bool:
        return self.has_permission("can_import")

    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_viewer(self) -> bool:
        return self.role == "viewer"


# Global instance
permissions = PermissionManager()