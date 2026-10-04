from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.capability_frappe_map import (
    capability_frappe_map,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
    Capability,
)


class TestFrappeNativePermissionCapabilityMap(unittest.TestCase):
    def test_every_catalog_capability_has_frappe_map_entry(self) -> None:
        mapped = {entry.capability for entry in capability_frappe_map()}
        self.assertEqual(mapped, set(ALL_CAPABILITIES))
        self.assertEqual(len(mapped), len(CAPABILITY_CATALOG))

    def test_customer_and_edge_view_are_custom_columns(self) -> None:
        """Native read stays technical; business view uses a dedicated column."""

        customers = CAPABILITY_CATALOG[Capability.VIEW_CUSTOMERS]
        edges = CAPABILITY_CATALOG[Capability.VIEW_EDGE_BANDING_TYPES]
        self.assertTrue(customers.custom)
        self.assertEqual(customers.permission_type, Capability.VIEW_CUSTOMERS)
        self.assertTrue(edges.custom)
        self.assertEqual(edges.permission_type, Capability.VIEW_EDGE_BANDING_TYPES)

    def test_map_keeps_standard_crud_where_semantics_match(self) -> None:
        by_key = {entry.capability: entry for entry in capability_frappe_map()}
        self.assertTrue(by_key[Capability.VIEW_ORDERS].standard)
        self.assertEqual(by_key[Capability.VIEW_ORDERS].permission_type, "read")
        self.assertTrue(by_key[Capability.CREATE_ORDER].standard)
        self.assertEqual(by_key[Capability.CREATE_ORDER].permission_type, "create")
        self.assertTrue(by_key[Capability.EDIT_ORDER].standard)
        self.assertEqual(by_key[Capability.EDIT_ORDER].permission_type, "write")
        self.assertFalse(by_key[Capability.DISPATCH_ORDER].standard)
        self.assertFalse(by_key[Capability.VIEW_COSTS].standard)
        self.assertIn("permlevel", by_key[Capability.VIEW_COSTS].contextual_rules)
        self.assertIn(
            "assignment",
            by_key[Capability.START_ASSIGNED_STAGE].contextual_rules,
        )


class TestCustomDocPermCapabilityReaderArchitecture(unittest.TestCase):
    def test_reader_never_uses_has_permission_as_capability_authority(self) -> None:
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[1]
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "custom_docperm_capability_reader.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Custom DocPerm", source)
        self.assertIn("PROTECTED_SYSTEM_ROLES", source)
        self.assertIn("normalize_business_capability_state", source)
        self.assertNotIn("has_permission(", source)
        self.assertNotIn("check_permission(", source)
        self.assertNotIn("Almdina Role Capability State", source)
        self.assertNotIn("capabilities_json", source)


if __name__ == "__main__":
    unittest.main()
