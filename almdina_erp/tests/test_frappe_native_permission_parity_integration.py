from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.application.security.legacy_permission_bootstrap import (
    legacy_role_state,
    legacy_roles,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.canonical_permission_state_repository import (
    CanonicalPermissionStateRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.custom_docperm_capability_reader import (
    CustomDocPermCapabilityReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.system_role_policy import (
    PROTECTED_SYSTEM_ROLES,
)
from almdina_erp.patches.v1_0.retire_canonical_permission_runtime import (
    execute as retire_canonical_permission_runtime,
)


ROLE = "Almdina Native Parity Role"
PERSONA_FIXTURES = (
    "Order Entry",
    "Production Manager",
    "Accounts Management",
    "Cutting Operator",
    "Edge Operator",
    "عامل رسم",
    "عامل شريون",
    "عامل CNC",
    "عامل تقشيط",
)


class TestFrappeNativePermissionParityIntegration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        sync_permission_types()
        if not frappe.db.exists("Role", ROLE):
            frappe.get_doc(
                {"doctype": "Role", "role_name": ROLE, "desk_access": 1}
            ).insert(ignore_permissions=True)
        frappe.db.delete("Custom DocPerm", {"role": ROLE})
        frappe.db.delete("Almdina Role Capability State", {"role": ROLE})

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Custom DocPerm", {"role": ROLE})
        frappe.db.delete("Almdina Role Capability State", {"role": ROLE})
        if frappe.db.exists("Role", ROLE):
            frappe.delete_doc("Role", ROLE, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    def _assert_docperm_round_trip(
        self, role: str, capabilities: dict[str, bool]
    ) -> None:
        """Assert save → CustomDocPermCapabilityReader round-trip.

        Both sides intentionally read Custom DocPerm after cutover. This is a
        persistence round-trip check, not legacy-vs-Frappe migration parity.
        """

        repository = ProjectedPermissionMatrixRepository()
        reader = CustomDocPermCapabilityReader()
        repository.save_role_state(role, capabilities)
        saved = repository.role_state(role)["capabilities"]
        projected = reader.role_capabilities(role)
        mismatched = sorted(
            key
            for key in sorted(saved)
            if bool(saved[key]) != bool(projected[key])
        )
        self.assertEqual(
            mismatched,
            [],
            f"DocPerm round-trip mismatch for {role}: {mismatched}",
        )

    def test_empty_role_is_deny_all_in_both_readers(self) -> None:
        self._assert_docperm_round_trip(ROLE, {})
        reader = CustomDocPermCapabilityReader()
        state = reader.role_capabilities(ROLE)
        self.assertFalse(any(state.values()))

    def test_order_entry_lookup_does_not_become_customer_view_capability(self) -> None:
        self._assert_docperm_round_trip(
            ROLE,
            {
                Capability.VIEW_ORDERS: True,
                Capability.CREATE_ORDER: True,
                Capability.EDIT_ORDER: True,
            },
        )
        repository = FrappePermissionMatrixRepository()
        state = repository.role_state(ROLE)["capabilities"]
        self.assertFalse(state[Capability.VIEW_CUSTOMERS])
        self.assertFalse(state[Capability.VIEW_EDGE_BANDING_TYPES])

        customer = frappe.db.get_value(
            "Custom DocPerm",
            {"parent": "Customer", "role": ROLE, "permlevel": 0},
            ["read", "select", Capability.VIEW_CUSTOMERS],
            as_dict=True,
        )
        self.assertIsNotNone(customer)
        self.assertEqual(int(customer.read), 1)
        self.assertEqual(int(customer.select), 1)
        self.assertEqual(int(customer.get(Capability.VIEW_CUSTOMERS) or 0), 0)

    def test_explicit_customer_view_writes_custom_column(self) -> None:
        self._assert_docperm_round_trip(
            ROLE,
            {
                Capability.VIEW_CUSTOMERS: True,
                Capability.CREATE_CUSTOMERS: True,
            },
        )
        row = frappe.db.get_value(
            "Custom DocPerm",
            {"parent": "Customer", "role": ROLE, "permlevel": 0},
            ["read", "create", Capability.VIEW_CUSTOMERS],
            as_dict=True,
        )
        self.assertEqual(int(row.get(Capability.VIEW_CUSTOMERS) or 0), 1)
        self.assertEqual(int(row.read), 1)
        self.assertEqual(int(row.create), 1)

    def test_cost_and_production_capabilities_parity(self) -> None:
        self._assert_docperm_round_trip(
            ROLE,
            {
                Capability.VIEW_ORDERS: True,
                Capability.VIEW_CUTTING_PLAN: True,
                Capability.VIEW_COSTS: True,
                Capability.EDIT_COST_SETTINGS: True,
                Capability.DISPATCH_ORDER: True,
                Capability.START_ASSIGNED_STAGE: True,
                Capability.HANDOFF_ASSIGNED_STAGE: True,
                Capability.MANAGE_PERMISSIONS: True,
            },
        )

    def test_legacy_persona_fixtures_project_with_docperm_round_trip(self) -> None:
        available = set(legacy_roles())
        repository = ProjectedPermissionMatrixRepository()
        reader = CustomDocPermCapabilityReader()
        for role in PERSONA_FIXTURES:
            if role not in available:
                continue
            if not frappe.db.exists("Role", role):
                frappe.get_doc(
                    {"doctype": "Role", "role_name": role, "desk_access": 1}
                ).insert(ignore_permissions=True)
            frappe.db.delete("Custom DocPerm", {"role": role})
            frappe.db.delete("Almdina Role Capability State", {"role": role})
            state = legacy_role_state(role)
            repository.save_role_state(role, state)
            saved = repository.role_state(role)["capabilities"]
            projected = reader.role_capabilities(role)
            mismatched = sorted(
                key
                for key in sorted(saved)
                if bool(saved[key]) != bool(projected[key])
            )
            self.assertEqual(
                mismatched, [], f"persona DocPerm round-trip failed for {role}"
            )

    def test_legacy_persona_expected_sets_migrate_into_docperm(self) -> None:
        """True migration parity: bootstrap expected sets → retire → DocPerm reader.

        Expected values come from legacy_permission_bootstrap, not from the
        DocPerm repository under test.
        """

        available = set(legacy_roles())
        canonical = CanonicalPermissionStateRepository()
        reader = CustomDocPermCapabilityReader()
        personas = [
            role
            for role in (
                "Order Entry",
                "Production Manager",
                "Accounts Management",
                "Cutting Operator",
                "Edge Operator",
                "عامل رسم",
            )
            if role in available
        ]
        for role in personas:
            if not frappe.db.exists("Role", role):
                frappe.get_doc(
                    {"doctype": "Role", "role_name": role, "desk_access": 1}
                ).insert(ignore_permissions=True)
            frappe.db.delete("Custom DocPerm", {"role": role})
            frappe.db.delete("Almdina Role Capability State", {"role": role})
            canonical.save(role, legacy_role_state(role))

        retire_canonical_permission_runtime()

        for role in personas:
            expected = legacy_role_state(role)
            actual = reader.role_capabilities(role)
            mismatched = sorted(
                key
                for key in sorted(expected)
                if bool(expected[key]) != bool(actual.get(key))
            )
            self.assertEqual(
                mismatched,
                [],
                f"legacy→DocPerm migration parity failed for {role}: {mismatched}",
            )

    def test_protected_roles_are_rejected_by_docperm_reader(self) -> None:
        reader = CustomDocPermCapabilityReader()
        for role in sorted(PROTECTED_SYSTEM_ROLES):
            with self.assertRaises(ValueError):
                reader.role_capabilities(role)

    def test_multi_role_union_ignores_system_manager(self) -> None:
        repository = ProjectedPermissionMatrixRepository()
        repository.save_role_state(
            ROLE,
            {Capability.VIEW_ORDERS: True, Capability.CREATE_ORDER: True},
        )
        reader = CustomDocPermCapabilityReader()
        granted = reader.granted_capabilities_for_roles(
            [ROLE, "System Manager", "Desk User"]
        )
        self.assertIn(Capability.VIEW_ORDERS, granted)
        self.assertIn(Capability.CREATE_ORDER, granted)
        self.assertNotIn(Capability.MANAGE_PERMISSIONS, granted)


__all__ = ["TestFrappeNativePermissionParityIntegration"]
