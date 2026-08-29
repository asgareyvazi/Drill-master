"""P0: Permission Enforcement Tests"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.permissions import PermissionManager, ROLE_PERMISSIONS


class PermissionTests(unittest.TestCase):
    def test_viewer_read_only(self):
        pm = PermissionManager()
        pm.set_user({"id": 1, "username": "viewer", "role": "viewer", "permissions": {"can_export": True}})

        self.assertTrue(pm.is_viewer())
        self.assertFalse(pm.can_create_well())
        self.assertFalse(pm.can_delete_well())
        self.assertFalse(pm.can_delete_reports())
        self.assertFalse(pm.can_edit_reports())
        self.assertFalse(pm.can_import())
        self.assertFalse(pm.can_approve_reports())
        self.assertTrue(pm.can_export())

    def test_engineer_permissions(self):
        pm = PermissionManager()
        pm.set_user({"id": 2, "username": "engineer", "role": "engineer"})

        self.assertFalse(pm.is_viewer())
        self.assertTrue(pm.can_create_well())
        self.assertTrue(pm.can_edit_reports())
        self.assertTrue(pm.can_import())
        self.assertTrue(pm.can_export())
        self.assertFalse(pm.can_approve_reports())

    def test_admin_all(self):
        pm = PermissionManager()
        pm.set_user({"id": 3, "username": "admin", "role": "admin"})

        self.assertTrue(pm.is_admin())
        self.assertTrue(pm.has_permission("can_create_well"))
        self.assertTrue(pm.has_permission("can_delete_well"))
        self.assertTrue(pm.has_permission("can_delete_reports"))
        self.assertTrue(pm.has_permission("can_edit_reports"))
        self.assertTrue(pm.has_permission("can_import"))
        self.assertTrue(pm.has_permission("can_export"))
        self.assertTrue(pm.has_permission("can_approve_reports"))

    def test_supervisor(self):
        pm = PermissionManager()
        pm.set_user({"id": 4, "username": "supervisor", "role": "supervisor"})

        self.assertTrue(pm.can_approve_reports())
        self.assertTrue(pm.can_delete_reports())
        self.assertTrue(pm.can_edit_reports())

    def test_protected_operations_list(self):
        protected = ["Create", "Edit", "Save", "Delete", "Import", "Export", "Approve", "Reject", "Finalize"]
        permission_map = {
            "Create": "can_create_well",
            "Edit": "can_edit_reports",
            "Save": "can_edit_reports",
            "Delete": "can_delete_reports",
            "Import": "can_import",
            "Export": "can_export",
            "Approve": "can_approve_reports",
            "Reject": "can_approve_reports",
            "Finalize": "can_approve_reports",
        }
        for op in protected:
            self.assertIn(op, permission_map)


if __name__ == "__main__":
    unittest.main()
