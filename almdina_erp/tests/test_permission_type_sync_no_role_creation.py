from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SYNC_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "permission_type_sync.py"
)
REGISTRY_MODULE = "almdina_erp.almdina_erp.infrastructure.frappe.managed_role_registry"


class _FakeDocument:
    def __init__(self, payload: dict[str, object], inserted: list[dict[str, object]]) -> None:
        self.payload = dict(payload)
        self.inserted = inserted

    def insert(self, ignore_permissions: bool = False):
        self.inserted.append(self.payload)
        return self


class _FakeDB:
    def exists(self, doctype: str, filters=None):
        if doctype in {
            "Permission Type",
            "Door Cutting Order",
            "Replacement Piece",
            "Almdina ERP Settings",
            "Production Routing",
            "Customer",
            "Edge Banding Type",
        }:
            return True
        if isinstance(filters, dict):
            return False
        return False


class TestPermissionTypeSyncNoRoleCreation(unittest.TestCase):
    def test_sync_creates_permission_types_but_never_roles(self) -> None:
        inserted: list[dict[str, object]] = []
        fake_frappe = types.ModuleType("frappe")
        fake_frappe.db = _FakeDB()
        fake_frappe.get_doc = lambda payload: _FakeDocument(payload, inserted)

        permissions_module = types.ModuleType("frappe.permissions")
        permissions_module.setup_custom_perms = lambda _doctype: None

        registry_module = types.ModuleType(REGISTRY_MODULE)
        registry_module.managed_role_names = lambda: frozenset()

        repository_module_name = (
            "almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository"
        )
        repository_module = types.ModuleType(repository_module_name)

        class _FakeRepository:
            def ensure_custom_permission_baseline(self, _doctypes):
                return None

        repository_module.FrappePermissionMatrixRepository = _FakeRepository

        with patch.dict(
            sys.modules,
            {
                "frappe": fake_frappe,
                "frappe.permissions": permissions_module,
                REGISTRY_MODULE: registry_module,
                repository_module_name: repository_module,
            },
        ):
            spec = importlib.util.spec_from_file_location(
                "_almdina_permission_type_sync_test",
                SYNC_PATH,
            )
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.sync_permission_types()

        self.assertTrue(inserted)
        self.assertTrue(all(row["doctype"] == "Permission Type" for row in inserted))
        self.assertFalse(any(row["doctype"] == "Role" for row in inserted))
        permission_types = {str(row["perm_type"]) for row in inserted}
        self.assertIn("submit_order", permission_types)
        self.assertIn("approve_dxf", permission_types)
        self.assertIn("dispatch_order", permission_types)
        self.assertIn("manage_permissions", permission_types)
        self.assertIn("view_users", permission_types)
        self.assertIn("assign_user_roles", permission_types)
        self.assertNotIn("assign_workforce_profile", permission_types)
        self.assertNotIn("manage_users", permission_types)
        self.assertNotIn("manage_factory_settings", permission_types)


if __name__ == "__main__":
    unittest.main()
