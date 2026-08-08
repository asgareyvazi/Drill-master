"""Role-based permissions and a reusable method guard."""
import logging
from functools import wraps

logger = logging.getLogger(__name__)

ROLE_PERMISSIONS = {
    "admin": {"*"},
    "supervisor": {"can_create_well", "can_edit_reports", "can_approve_reports", "can_export", "can_import"},
    "engineer": {"can_create_well", "can_edit_reports", "can_export", "can_import"},
    "manager": {"can_create_well", "can_approve_reports", "can_export", "can_import"},
    "viewer": {"can_export"},
}


class PermissionManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._user = None
        return cls._instance

    def set_user(self, user_data):
        self._user = user_data

    @property
    def user(self):
        return self._user

    def _read_user_value(self, name=None, default=None):
        """Read a value from dict- or object-based user data.

        Deliberately not called ``_get``: older application versions used
        ``_get`` as a data attribute, which could shadow the method and cause
        ``'dict' object is not callable`` during startup.
        """
        if name is None:
            return self._user if self._user is not None else default
        if self._user is None:
            return default
        if isinstance(self._user, dict):
            return self._user.get(name, default)
        return getattr(self._user, name, default)

    @property
    def role(self):
        return str(self._read_user_value("role", "viewer")).lower()

    @property
    def username(self):
        return self._read_user_value("username", "unknown")

    @property
    def user_id(self):
        return self._read_user_value("id")

    def has_permission(self, permission):
        if self._user is None:
            return False
        explicit = self._read_user_value("permissions", {})
        if isinstance(explicit, dict) and permission in explicit:
            return bool(explicit[permission])
        role_permissions = ROLE_PERMISSIONS.get(self.role, set())
        return permission in role_permissions or "*" in role_permissions

    def can_create_well(self): return self.has_permission("can_create_well")
    def can_delete_well(self): return self.has_permission("can_delete_well")
    def can_edit_reports(self): return self.has_permission("can_edit_reports")
    def can_approve_reports(self): return self.has_permission("can_approve_reports")
    def can_manage_users(self): return self.has_permission("can_manage_users")
    def can_export(self): return self.has_permission("can_export")
    def can_import(self): return self.has_permission("can_import")
    def is_admin(self): return self.role == "admin"
    def is_viewer(self): return self.role == "viewer"


permissions = PermissionManager()


def require_permission(permission):
    """Guard a slot/method; returns False rather than crashing the UI."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            manager = getattr(args[0], "permissions", permissions) if args else permissions
            if not manager.has_permission(permission):
                logger.warning("Permission denied: %s (%s)", manager.username, permission)
                target = args[0] if args else None
                if hasattr(target, "show_warning"):
                    target.show_warning("You do not have permission for this action.")
                return False
            return func(*args, **kwargs)
        return wrapper
    return decorator
