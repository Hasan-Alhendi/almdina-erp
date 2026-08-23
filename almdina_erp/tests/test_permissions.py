from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_matrix_repository import (
    FrappePermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


EDITOR_ROLE = "Almdina Arbitrary Editor Test"
READER_ROLE = "Almdina Arbitrary Reader Test"
EMPTY_ROLE = "Almdina Arbitrary Empty Test"
EDITOR_USER = "almdina.arbitrary.editor@example.com"
READER_USER = "almdina.arbitrary.reader@example.com"
EMPTY_USER = "almdina.arbitrary.empty@example.com"


class TestAlmdinaPermissions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        sync_permission_types()
        for role in (EDITOR_ROLE, READER_ROLE, EMPTY_ROLE):
            cls._ensure_role(role)
        cls._ensure_user(EDITOR_USER, EDITOR_ROLE)
        cls._ensure_user(READER_USER, READER_ROLE)
        cls._ensure_user(EMPTY_USER, EMPTY_ROLE)

        repository = FrappePermissionMatrixRepository()
        repository.save_role_state(
            EDITOR_ROLE,
            {
                Capability.VIEW_ORDERS: True,
                Capability.CREATE_ORDER: True,
                Capability.EDIT_ORDER: True,
            },
        )
        repository.save_role_state(
            READER_ROLE,
            {Capability.VIEW_ORDERS: True},
        )
        repository.save_role_state(EMPTY_ROLE, {})
        frappe.clear_cache()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        for user in (EDITOR_USER, READER_USER, EMPTY_USER):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in (EDITOR_ROLE, READER_ROLE, EMPTY_ROLE):
            frappe.db.delete("Custom DocPerm", {"role": role})
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDownClass()

    @classmethod
    def _ensure_role(cls, role: str) -> None:
        if not frappe.db.exists("Role", role):
            frappe.get_doc(
                {"doctype": "Role", "role_name": role, "desk_access": 1}
            ).insert(ignore_permissions=True)

    @classmethod
    def _ensure_user(cls, email: str, role: str) -> None:
        if frappe.db.exists("User", email):
            user = frappe.get_doc("User", email)
        else:
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": role,
                    "enabled": 1,
                    "send_welcome_email": 0,
                    "user_type": "System User",
                }
            ).insert(ignore_permissions=True)
        existing_roles = {row.role for row in (user.roles or [])}
        if role not in existing_roles:
            user.append("roles", {"role": role})
            user.save(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_arbitrary_role_matrix_drives_door_cutting_order_access(self):
        expected = {
            EDITOR_USER: {"read": True, "create": True, "write": True},
            READER_USER: {"read": True, "create": False, "write": False},
            EMPTY_USER: {"read": False, "create": False, "write": False},
        }
        for user, rights in expected.items():
            for permission_type, allowed in rights.items():
                actual = bool(
                    frappe.has_permission(
                        "Door Cutting Order",
                        ptype=permission_type,
                        user=user,
                    )
                )
                self.assertEqual(
                    actual,
                    allowed,
                    f"{user} {permission_type}: expected {allowed}, got {actual}",
                )

    def test_cost_permlevel_has_no_fixed_role_grants(self):
        meta = frappe.get_meta("Door Cutting Order")
        cost_fields = {
            "board_rate_usd",
            "cutting_cost_per_board_usd",
            "mdf_cost_usd",
            "cutting_cost_usd",
            "edge_cost_usd",
            "total_cost_usd",
            "special_shapes_baseline_cost_usd",
            "special_shapes_estimated_total_usd",
            "special_shapes_final_total_usd",
            "customer_quote_total_usd",
            "customer_quote_status",
            "material_variance_cost_usd",
            "internal_loss_cost_usd",
            "actual_cost_usd",
        }
        for fieldname in cost_fields:
            field = meta.get_field(fieldname)
            self.assertIsNotNone(field, fieldname)
            self.assertEqual(field.permlevel, 1, fieldname)

        level_one_roles = {
            permission.role
            for permission in meta.permissions
            if int(permission.permlevel or 0) == 1 and permission.read
        }
        self.assertEqual(level_one_roles, set())

    def test_order_editor_does_not_implicitly_receive_factory_settings(self):
        from almdina_erp.almdina_erp.services.production_settings_service import (
            get_production_settings,
        )

        frappe.set_user(EDITOR_USER)
        with self.assertRaises(frappe.PermissionError):
            get_production_settings()

    def test_sensitive_replacement_approval_rejects_ungranted_role_before_lookup(self):
        from almdina_erp.almdina_erp.services.replacement_approval import approve_replacement

        frappe.set_user(EDITOR_USER)
        with self.assertRaises(frappe.PermissionError):
            approve_replacement("NON-EXISTENT")
