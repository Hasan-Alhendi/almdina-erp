from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


TEST_USERS = {
    "Order Entry": "almdina.order.entry@example.com",
    "Cutting Operator": "almdina.cutting@example.com",
    "Edge Operator": "almdina.edge@example.com",
    "Production Manager": "almdina.production.manager@example.com",
    "Stock Manager": "almdina.stock.manager@example.com",
    "Accounts Management": "almdina.accounts@example.com",
}


class TestAlmdinaPermissions(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for role, email in TEST_USERS.items():
            cls._ensure_user(email, role)

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
                }
            ).insert(ignore_permissions=True)
        existing_roles = {row.role for row in (user.roles or [])}
        if role not in existing_roles:
            user.append("roles", {"role": role})
            user.save(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_door_cutting_order_role_matrix(self):
        expected = {
            "Order Entry": {"read": True, "create": True, "write": True},
            "Cutting Operator": {"read": True, "create": False, "write": False},
            "Edge Operator": {"read": True, "create": False, "write": False},
            "Production Manager": {"read": True, "create": True, "write": True},
            "Stock Manager": {"read": True, "create": False, "write": False},
            "Accounts Management": {"read": True, "create": False, "write": False},
        }
        for role, rights in expected.items():
            user = TEST_USERS[role]
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
                    f"{role} {permission_type}: expected {allowed}, got {actual}",
                )

    def test_worker_roles_do_not_receive_cost_permlevel(self):
        meta = frappe.get_meta("Door Cutting Order")
        cost_fields = {
            "board_rate_usd",
            "cutting_cost_per_board_usd",
            "mdf_cost_usd",
            "cutting_cost_usd",
            "edge_cost_usd",
            "total_cost_usd",
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
        self.assertNotIn("Cutting Operator", level_one_roles)
        self.assertNotIn("Edge Operator", level_one_roles)

    def test_stock_settings_service_rejects_order_entry(self):
        from almdina_erp.almdina_erp.services.settings_access_service import get_stock_settings

        frappe.set_user(TEST_USERS["Order Entry"])
        with self.assertRaises(frappe.PermissionError):
            get_stock_settings()

    def test_stock_settings_service_allows_stock_manager(self):
        from almdina_erp.almdina_erp.services.settings_access_service import get_stock_settings

        frappe.set_user(TEST_USERS["Stock Manager"])
        result = get_stock_settings()
        self.assertIn("stock_consumption_point", result)
        self.assertTrue(result["can_edit"])

    def test_production_settings_service_rejects_stock_manager(self):
        from almdina_erp.almdina_erp.services.production_settings_service import get_production_settings

        frappe.set_user(TEST_USERS["Stock Manager"])
        with self.assertRaises(frappe.PermissionError):
            get_production_settings()

    def test_production_settings_service_allows_production_manager(self):
        from almdina_erp.almdina_erp.services.production_settings_service import get_production_settings

        frappe.set_user(TEST_USERS["Production Manager"])
        result = get_production_settings()
        self.assertIn("default_production_routing", result)
        self.assertIn("packing_options", result)

    def test_sensitive_replacement_approval_rejects_order_entry_before_lookup(self):
        from almdina_erp.almdina_erp.services.replacement_approval import approve_replacement

        frappe.set_user(TEST_USERS["Order Entry"])
        with self.assertRaises(frappe.PermissionError):
            approve_replacement("NON-EXISTENT")

    def test_actual_consumption_reversal_rejects_order_entry_before_lookup(self):
        from almdina_erp.almdina_erp.services.actual_consumption_reversal import reverse_actual_consumption

        frappe.set_user(TEST_USERS["Order Entry"])
        with self.assertRaises(frappe.PermissionError):
            reverse_actual_consumption("NON-EXISTENT", "test")
