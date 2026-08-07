from __future__ import annotations

import uuid

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import sync_permission_types


ADMIN_ROLE = "Almdina Permission Console Admin Test"
TARGET_ROLE = "Almdina Permission Console Target Test"
PRESERVED_ROLE = "Almdina Permission Baseline Test"
ADMIN_USER = "almdina.permission.console.admin@example.com"
TARGET_USER = "almdina.permission.console.target@example.com"
PRESERVED_USER = "almdina.permission.baseline@example.com"


class TestPermissionManagementIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        sync_permission_types()
        for role in (ADMIN_ROLE, TARGET_ROLE, PRESERVED_ROLE):
            cls._ensure_role(role)
            cls._ensure_managed_role(role)
        cls._ensure_user(ADMIN_USER, ADMIN_ROLE)
        cls._ensure_user(TARGET_USER, TARGET_ROLE)
        cls._ensure_user(PRESERVED_USER, PRESERVED_ROLE)
        cls._replace_role_permissions(
            ADMIN_ROLE,
            "Almdina ERP Settings",
            {"read": 1, Capability.MANAGE_PERMISSIONS: 1},
        )
        frappe.clear_cache(user=ADMIN_USER)
        frappe.clear_cache(doctype="Almdina ERP Settings")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        managed_roles = [ADMIN_ROLE, TARGET_ROLE, PRESERVED_ROLE]
        frappe.db.delete("Almdina Permission Audit", {"role": ["in", managed_roles]})
        frappe.db.delete("Almdina Role Metadata", {"role": ["in", managed_roles]})
        for role in managed_roles:
            frappe.db.delete("Custom DocPerm", {"role": role})
            frappe.db.delete("DocPerm", {"role": role})
        for user in (ADMIN_USER, TARGET_USER, PRESERVED_USER):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in managed_roles:
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDownClass()

    @classmethod
    def _ensure_role(cls, role: str) -> None:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

    @classmethod
    def _ensure_managed_role(cls, role: str) -> None:
        if frappe.db.exists("Almdina Role Metadata", {"role": role}):
            return
        frappe.get_doc(
            {
                "doctype": "Almdina Role Metadata",
                "role": role,
                "role_uid": str(uuid.uuid4()),
                "description": "Permission integration managed role",
                "managed_by_almdina": 1,
            }
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
        if role not in {row.role for row in (user.roles or [])}:
            user.append("roles", {"role": role})
            user.save(ignore_permissions=True)

    @classmethod
    def _replace_role_permissions(cls, role: str, doctype: str, values: dict[str, int]) -> None:
        frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0})
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role,
                "permlevel": 0,
                **values,
            }
        ).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.delete("Almdina Permission Audit", {"role": TARGET_ROLE})
        frappe.db.delete("Custom DocPerm", {"role": TARGET_ROLE})
        frappe.clear_cache(user=TARGET_USER)
        for doctype in (
            "Door Cutting Order",
            "Replacement Piece",
            "Almdina ERP Settings",
            "Production Routing",
            "Customer",
            "Edge Banding Type",
        ):
            frappe.clear_cache(doctype=doctype)
        super().tearDown()

    def test_managed_role_can_receive_drawing_and_factory_capabilities(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            get_permission_console,
            update_role_permissions,
        )

        frappe.set_user(ADMIN_USER)
        console = get_permission_console()
        self.assertTrue(any(row["name"] == TARGET_ROLE for row in console["roles"]))
        self.assertTrue(console["catalog"])

        result = update_role_permissions(
            TARGET_ROLE,
            {
                Capability.VIEW_ORDERS: True,
                Capability.VIEW_DRAWING_WORKSPACE: True,
                Capability.APPROVE_DXF: True,
                Capability.VIEW_FACTORY_SETTINGS: True,
                Capability.EDIT_FACTORY_CUTTING_DEFAULTS: True,
                Capability.EDIT_FACTORY_COST_DEFAULTS: True,
                Capability.VIEW_PRODUCTION_ROUTINGS: True,
                Capability.EDIT_FACTORY_PRODUCTION_CONTROLS: True,
            },
        )
        self.assertTrue(result["changed"])
        for capability in (
            Capability.VIEW_ORDERS,
            Capability.VIEW_DRAWING_WORKSPACE,
            Capability.APPROVE_DXF,
            Capability.VIEW_FACTORY_SETTINGS,
            Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
            Capability.EDIT_FACTORY_COST_DEFAULTS,
            Capability.VIEW_PRODUCTION_ROUTINGS,
            Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
        ):
            self.assertTrue(result["capabilities"][capability], capability)

        order_permission = frappe.db.get_value(
            "Custom DocPerm",
            {"parent": "Door Cutting Order", "role": TARGET_ROLE, "permlevel": 0},
            ["read", Capability.APPROVE_DXF],
            as_dict=True,
        )
        settings_permission = frappe.db.get_value(
            "Custom DocPerm",
            {"parent": "Almdina ERP Settings", "role": TARGET_ROLE, "permlevel": 0},
            [
                "read",
                "write",
                Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
                Capability.EDIT_FACTORY_COST_DEFAULTS,
                Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
            ],
            as_dict=True,
        )
        self.assertEqual(int(order_permission.read), 1)
        self.assertEqual(int(order_permission.get(Capability.APPROVE_DXF)), 1)
        self.assertEqual(int(settings_permission.read), 1)
        self.assertEqual(int(settings_permission.write), 0)
        for capability in (
            Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
            Capability.EDIT_FACTORY_COST_DEFAULTS,
            Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
        ):
            self.assertEqual(int(settings_permission.get(capability)), 1)

        frappe.clear_cache(user=TARGET_USER)
        self.assertTrue(
            frappe.has_permission(
                "Door Cutting Order",
                ptype=Capability.APPROVE_DXF,
                user=TARGET_USER,
            )
        )
        self.assertTrue(
            frappe.has_permission(
                "Almdina ERP Settings",
                ptype=Capability.EDIT_FACTORY_COST_DEFAULTS,
                user=TARGET_USER,
            )
        )
        self.assertFalse(
            frappe.has_permission("Almdina ERP Settings", ptype="write", user=TARGET_USER)
        )
        self.assertEqual(frappe.db.count("Almdina Permission Audit", {"role": TARGET_ROLE}), 1)

    def test_incomplete_role_matrix_is_rejected_without_hidden_grants(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import update_role_permissions

        frappe.set_user(ADMIN_USER)
        with self.assertRaises(frappe.ValidationError):
            update_role_permissions(TARGET_ROLE, {Capability.APPROVE_DXF: True})
        self.assertEqual(frappe.db.count("Almdina Permission Audit", {"role": TARGET_ROLE}), 0)

    def test_complete_order_surface_projects_native_and_field_permissions(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import update_role_permissions

        frappe.set_user(ADMIN_USER)
        result = update_role_permissions(
            TARGET_ROLE,
            {
                Capability.VIEW_ORDERS: True,
                Capability.CREATE_ORDER: True,
                Capability.EDIT_ORDER: True,
                Capability.VIEW_CUSTOMERS: True,
                Capability.VIEW_EDGE_BANDING_TYPES: True,
                Capability.VIEW_COSTS: True,
                Capability.VIEW_CUTTING_PLAN: True,
                Capability.RECALCULATE_PLAN: True,
            },
        )
        for capability in (
            Capability.VIEW_ORDERS,
            Capability.CREATE_ORDER,
            Capability.EDIT_ORDER,
            Capability.VIEW_CUSTOMERS,
            Capability.VIEW_EDGE_BANDING_TYPES,
            Capability.VIEW_COSTS,
            Capability.VIEW_CUTTING_PLAN,
            Capability.RECALCULATE_PLAN,
        ):
            self.assertTrue(result["capabilities"][capability], capability)

        for doctype in ("Customer", "Edge Banding Type"):
            permission = frappe.db.get_value(
                "Custom DocPerm",
                {"parent": doctype, "role": TARGET_ROLE, "permlevel": 0},
                ["read", "select"],
                as_dict=True,
            )
            self.assertEqual(int(permission.read), 1, doctype)
            self.assertEqual(int(permission.select), 1, doctype)

        field_permission = frappe.db.get_value(
            "Custom DocPerm",
            {"parent": "Door Cutting Order", "role": TARGET_ROLE, "permlevel": 1},
            ["read", "write"],
            as_dict=True,
        )
        self.assertEqual(int(field_permission.read), 1)
        self.assertEqual(int(field_permission.write), 0)

        frappe.clear_cache(user=TARGET_USER)
        for permission_type in (
            "read",
            "create",
            "write",
            Capability.VIEW_COSTS,
            Capability.VIEW_CUTTING_PLAN,
            Capability.RECALCULATE_PLAN,
        ):
            self.assertTrue(
                frappe.has_permission("Door Cutting Order", ptype=permission_type, user=TARGET_USER),
                permission_type,
            )

        permitted_fields = frappe.get_meta("Door Cutting Order").get_permitted_fieldnames(user=TARGET_USER)
        self.assertIn("board_rate_usd", permitted_fields)
        self.assertIn("total_cost_usd", permitted_fields)

    def test_cost_edit_grant_projects_write_and_noop_save_repairs_it(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import update_role_permissions

        frappe.set_user(ADMIN_USER)
        result = update_role_permissions(
            TARGET_ROLE,
            {
                Capability.VIEW_ORDERS: True,
                Capability.CREATE_ORDER: True,
                Capability.EDIT_ORDER: True,
                Capability.VIEW_CUSTOMERS: True,
                Capability.VIEW_EDGE_BANDING_TYPES: True,
                Capability.VIEW_COSTS: True,
                Capability.EDIT_COST_SETTINGS: True,
            },
        )
        filters = {"parent": "Door Cutting Order", "role": TARGET_ROLE, "permlevel": 1}
        permission_name = frappe.db.get_value("Custom DocPerm", filters)
        frappe.db.set_value("Custom DocPerm", permission_name, "write", 0)
        frappe.clear_cache(doctype="Door Cutting Order")
        repaired = update_role_permissions(TARGET_ROLE, result["capabilities"])
        self.assertFalse(repaired["changed"])
        field_permission = frappe.db.get_value("Custom DocPerm", filters, ["read", "write"], as_dict=True)
        self.assertEqual(int(field_permission.read), 1)
        self.assertEqual(int(field_permission.write), 1)

    def test_partial_custom_matrix_preserves_unedited_standard_role_access(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.delete("Custom DocPerm", {"role": PRESERVED_ROLE})
        frappe.db.delete("DocPerm", {"role": PRESERVED_ROLE})
        frappe.get_doc(
            {
                "doctype": "DocPerm",
                "parent": "Door Cutting Order",
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": PRESERVED_ROLE,
                "permlevel": 0,
                "read": 1,
                "report": 1,
                "print": 1,
            }
        ).insert(ignore_permissions=True)
        sync_permission_types()
        frappe.clear_cache(user=PRESERVED_USER)
        copied = frappe.db.get_value(
            "Custom DocPerm",
            {"parent": "Door Cutting Order", "role": PRESERVED_ROLE},
            ["read", "report", "print"],
            as_dict=True,
        )
        self.assertEqual(int(copied.read), 1)
        self.assertEqual(int(copied.report), 1)
        self.assertEqual(int(copied.print), 1)
        self.assertTrue(frappe.has_permission("Door Cutting Order", ptype="read", user=PRESERVED_USER))

    def test_control_center_and_financial_report_grants_are_explicit(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import update_role_permissions
        from almdina_erp.almdina_erp.services.report_permission_service import current_report_access

        frappe.set_user(ADMIN_USER)
        result = update_role_permissions(
            TARGET_ROLE,
            {
                Capability.VIEW_ORDERS: True,
                Capability.VIEW_REPLACEMENTS: True,
                Capability.APPROVE_REPLACEMENT: True,
                Capability.EDIT_REPLACEMENT_COST: True,
                Capability.VIEW_OPERATIONAL_REPORTS: True,
                Capability.VIEW_COSTS: True,
                Capability.VIEW_FINANCIAL_REPORTS: True,
            },
        )
        capabilities = result["capabilities"]
        for capability in (
            Capability.VIEW_REPLACEMENTS,
            Capability.APPROVE_REPLACEMENT,
            Capability.EDIT_REPLACEMENT_COST,
            Capability.VIEW_OPERATIONAL_REPORTS,
            Capability.VIEW_COSTS,
            Capability.VIEW_FINANCIAL_REPORTS,
            Capability.VIEW_ORDERS,
        ):
            self.assertTrue(capabilities[capability], capability)

        frappe.clear_cache(user=TARGET_USER)
        frappe.set_user(TARGET_USER)
        access = current_report_access()
        self.assertTrue(access.operational)
        self.assertTrue(access.financial)

    def test_self_lockout_requires_explicit_confirmation(self) -> None:
        from almdina_erp.almdina_erp.services.permission_management_service import (
            preview_role_permissions,
            update_role_permissions,
        )

        frappe.set_user(ADMIN_USER)
        preview = preview_role_permissions(ADMIN_ROLE, {Capability.VIEW_FACTORY_SETTINGS: True})
        self.assertTrue(preview["requires_self_lockout_confirmation"])
        with self.assertRaises(frappe.PermissionError):
            update_role_permissions(ADMIN_ROLE, {Capability.VIEW_FACTORY_SETTINGS: True})

    def test_factory_settings_are_capability_managed(self) -> None:
        from almdina_erp.almdina_erp.services.production_settings_service import get_production_settings

        frappe.set_user(ADMIN_USER)
        # Grant the minimum explicit read capability without changing permission-admin access.
        from almdina_erp.almdina_erp.services.permission_management_service import update_role_permissions
        update_role_permissions(
            ADMIN_ROLE,
            {
                Capability.MANAGE_PERMISSIONS: True,
                Capability.VIEW_FACTORY_SETTINGS: True,
            },
        )
        settings = get_production_settings()
        self.assertIn("default_production_routing", settings)
        self.assertIn("packing_options", settings)

        frappe.set_user(TARGET_USER)
        with self.assertRaises(frappe.PermissionError):
            get_production_settings()


if __name__ == "__main__":
    import unittest

    unittest.main()
