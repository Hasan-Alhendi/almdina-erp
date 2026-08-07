from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "almdina_erp" / "infrastructure" / "frappe"
REGISTRY = INFRA / "managed_role_registry.py"
ROLE_REPOSITORY = INFRA / "role_repository.py"
PERMISSION_REPOSITORY = INFRA / "permission_matrix_repository.py"
WORKFORCE_REPOSITORY = INFRA / "workforce_repository.py"
PERMISSION_SYNC = INFRA / "permission_type_sync.py"


class TestManagedRoleRegistryArchitecture(unittest.TestCase):
    def test_registry_is_the_single_owner_of_metadata_doctype_constant(self) -> None:
        registry = REGISTRY.read_text(encoding="utf-8")
        self.assertIn('ROLE_METADATA_DOCTYPE = "Almdina Role Metadata"', registry)
        self.assertIn("managed_role_metadata", registry)
        self.assertIn("managed_role_names", registry)
        self.assertIn("is_managed_role", registry)

    def test_role_permission_workforce_and_sync_boundaries_use_registry(self) -> None:
        for path in (
            ROLE_REPOSITORY,
            PERMISSION_REPOSITORY,
            WORKFORCE_REPOSITORY,
            PERMISSION_SYNC,
        ):
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("managed_role_registry", source)
                self.assertIn("managed_role_names", source)

    def test_permission_console_cannot_manage_generic_frappe_roles(self) -> None:
        source = PERMISSION_REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("outside the Almdina managed-role registry", source)
        self.assertIn("PROTECTED_ROLES = PROTECTED_ROLE_NAMES", source)
        self.assertIn('filters={"name": ["in", managed]}', source)

    def test_role_console_lists_only_registered_roles(self) -> None:
        source = ROLE_REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("managed_role_names().difference(PROTECTED_ROLE_NAMES)", source)
        self.assertIn("outside the Almdina managed-role registry", source)
        self.assertIn("_ensure_metadata", source)

    def test_workforce_assignments_preserve_non_managed_technical_roles(self) -> None:
        source = WORKFORCE_REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("managed = self.managed_role_names()", source)
        self.assertIn("if row.role not in managed", source)
        self.assertIn('"Desk User"', source)

    def test_runtime_registry_has_no_historical_business_role_names(self) -> None:
        source = REGISTRY.read_text(encoding="utf-8")
        for role in (
            "Order Entry",
            "Production Manager",
            "Cutting Operator",
            "Edge Operator",
            "عامل رسم",
            "عامل CNC",
            "عامل تقشيط",
        ):
            self.assertNotIn(role, source)


if __name__ == "__main__":
    unittest.main()
