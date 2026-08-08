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
    def user(self): return self._user

    def _get(self, name=None, default=None):
        """Read user data safely from either a dict or a User object.

        ``name`` is optional for compatibility with older callers that used
        ``_get()`` as a request for the complete current user.
        """
        if name is None:
            return self._user if self._user is not None else default
        if self._user is None:
            return default
        if isinstance(self._user, dict):
            return self._user.get(name, default)
        return getattr(self._user, name, default)

    @property
    def role(self): return str(self._get("role", "viewer")).lower()
    @property
    def username(self): return self._get("username", "unknown")
    @property
    def user_id(self): return self._get("id")

    def has_permission(self, permission):
        if self._user is None: return False
        explicit = self._get("permissions", {})
        if isinstance(explicit, dict) and permission in explicit:
            return bool(explicit[permission])
        return permission in ROLE_PERMISSIONS.get(self.role, set()) or "*" in ROLE_PERMISSIONS.get(self.role, set())

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
