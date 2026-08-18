from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import granted_capabilities


ROLE = "Almdina Runtime Permission Flow Test"
USER = "almdina.runtime.permission.flow@example.com"


class TestRolePermissionRuntimeIntegration(FrappeTestCase):
    """Exercise the exact administrator flow used by the factory UI."""

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        if frappe.db.exists("User", USER):
            frappe.delete_doc("User", USER, force=True, ignore_permissions=True)
        frappe.db.delete("Almdina User Audit", {"target_user": USER})
        frappe.db.delete("Almdina Permission Audit", {"role": ROLE})
        frappe.db.delete("Custom DocPerm", {"role": ROLE})
        frappe.db.delete(
            "Custom DocPerm",
            {"parent": "Door Cutting Order", "role": "Desk User"},
        )
        if frappe.db.exists("Role", ROLE):
            frappe.delete_doc("Role", ROLE, force=True, ignore_permissions=True)
        frappe.get_doc({"doctype": "Role", "role_name": ROLE}).insert(ignore_permissions=True)
        frappe.clear_cache()

    def tearDown(self):
        frappe.set_user("Administrator")
        if frappe.db.exists("User", USER):
            frappe.delete_doc("User", USER, force=True, ignore_permissions=True)
        frappe.db.delete("Almdina User Audit", {"target_user": USER})
        frappe.db.delete("Almdina Permission Audit", {"role": ROLE})
        frappe.db.delete("Custom DocPerm", {"role": ROLE})
        frappe.db.delete(
            "Custom DocPerm",
            {"parent": "Door Cutting Order", "role": "Desk User"},
        )
        if frappe.db.exists("Role", ROLE):
            frappe.delete_doc("Role", ROLE, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    @staticmethod
    def _fresh_user_context() -> None:
        frappe.clear_cache(user=USER)
        for doctype in (
            "Door Cutting Order",
            "Cutting Plan",
            "Production Stage",
            "Replacement Piece",
        ):
            frappe.clear_cache(doctype=doctype)
        frappe.local.role_permissions = {}
        if hasattr(frappe.local, "almdina_matrix_capabilities"):
            del frappe.local.almdina_matrix_capabilities
        frappe.set_user(USER)

    def test_role_permissions_survive_workforce_assignment_and_fresh_user_context(self) -> None:
        from almdina_erp.almdina_erp.services.permission_context_service import get_permission_context
        from almdina_erp.almdina_erp.services.permission_management_service import update_role_permissions
        from almdina_erp.almdina_erp.services.workforce_service import create_workforce_user

        role = frappe.get_doc("Role", ROLE)
        self.assertEqual(int(role.desk_access or 0), 1)

        saved = update_role_permissions(
            ROLE,
            {
                Capability.CREATE_ORDER: True,
                Capability.EDIT_ORDER: True,
                Capability.VIEW_CUTTING_PLAN: True,
                Capability.VIEW_COSTS: True,
                Capability.UPLOAD_DXF: True,
                Capability.START_ASSIGNED_STAGE: True,
            },
        )
        for capability in (
            Capability.VIEW_ORDERS,
            Capability.CREATE_ORDER,
            Capability.EDIT_ORDER,
            Capability.VIEW_CUTTING_PLAN,
            Capability.VIEW_COSTS,
            Capability.UPLOAD_DXF,
            Capability.START_ASSIGNED_STAGE,
        ):
            self.assertTrue(saved["capabilities"][capability], capability)

        created = create_workforce_user(
            {
                "email": USER,
                "first_name": "Runtime",
                "last_name": "Permission",
                "language": "ar",
                "roles": [ROLE],
                "temporary_password": "SecureRuntime123!",
            }
        )["user"]
        self.assertEqual(created["roles"], [ROLE])
        self.assertEqual(frappe.db.get_value("User", USER, "user_type"), "System User")
        self.assertIn(ROLE, frappe.get_roles(USER))

        self._fresh_user_context()

        granted = granted_capabilities(USER)
        for capability in (
            Capability.VIEW_ORDERS,
            Capability.CREATE_ORDER,
            Capability.EDIT_ORDER,
            Capability.VIEW_CUTTING_PLAN,
            Capability.VIEW_COSTS,
            Capability.UPLOAD_DXF,
            Capability.START_ASSIGNED_STAGE,
        ):
            self.assertIn(capability, granted, capability)

        self.assertTrue(frappe.has_permission("Door Cutting Order", "read", user=USER))
        self.assertTrue(frappe.has_permission("Door Cutting Order", "create", user=USER))
        self.assertTrue(frappe.has_permission("Door Cutting Order", "write", user=USER))
        self.assertFalse(
            frappe.has_permission(
                "Door Cutting Order",
                Capability.UPLOAD_DXF,
                user=USER,
            )
        )
        self.assertFalse(frappe.has_permission("Door Cutting Order", "delete", user=USER))

        self.assertTrue(frappe.has_permission("Cutting Plan", "read", user=USER))
        self.assertTrue(frappe.has_permission("Production Stage", "read", user=USER))
        plan_permission = frappe.db.get_value(
            "Custom DocPerm",
            {"parent": "Cutting Plan", "role": ROLE, "permlevel": 0},
            ["read", Capability.UPLOAD_DXF],
            as_dict=True,
        )
        self.assertEqual(int(plan_permission.read), 1)
        self.assertEqual(int(plan_permission.get(Capability.UPLOAD_DXF)), 1)
        self.assertEqual(
            frappe.db.get_value(
                "Custom DocPerm",
                {"parent": "Cutting Plan", "role": ROLE, "permlevel": 1},
                "read",
            ),
            1,
        )

        context = get_permission_context()
        for capability in (
            Capability.VIEW_ORDERS,
            Capability.CREATE_ORDER,
            Capability.EDIT_ORDER,
            Capability.VIEW_CUTTING_PLAN,
            Capability.VIEW_COSTS,
            Capability.UPLOAD_DXF,
            Capability.START_ASSIGNED_STAGE,
        ):
            self.assertTrue(context["capabilities"][capability], capability)
        self.assertTrue(context["navigation"]["shared_shell"])
        self.assertIn("Almdina ERP", context["navigation"]["workspaces"])

    def test_empty_role_cannot_inherit_legacy_desk_user_permissions(self) -> None:
        from almdina_erp.almdina_erp.infrastructure.frappe.automatic_role_permission_cleanup import (
            revoke_automatic_role_business_grants,
        )
        from almdina_erp.almdina_erp.services.permission_context_service import get_permission_context
        from almdina_erp.almdina_erp.services.workforce_service import create_workforce_user

        # Reproduce an upgraded site's dangerous historical row. Desk User is an
        # automatic Frappe role, so every System User would inherit these rights.
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": "Door Cutting Order",
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": "Desk User",
                "permlevel": 0,
                "read": 1,
                "create": 1,
                "write": 1,
                "delete": 1,
                Capability.VIEW_COSTS: 1,
                Capability.VIEW_CUTTING_PLAN: 1,
            }
        ).insert(ignore_permissions=True)

        create_workforce_user(
            {
                "email": USER,
                "first_name": "Empty",
                "last_name": "Role",
                "language": "ar",
                "roles": [ROLE],
                "temporary_password": "SecureRuntime123!",
            }
        )
        self.assertIn("Desk User", frappe.get_roles(USER))

        # Runtime business capabilities already fail closed even before cleanup:
        # automatic native roles are no longer accepted as factory authority.
        self._fresh_user_context()
        self.assertEqual(granted_capabilities(USER), frozenset())
        context = get_permission_context()
        self.assertFalse(context["capabilities"][Capability.VIEW_ORDERS])
        self.assertFalse(context["capabilities"][Capability.CREATE_ORDER])
        self.assertFalse(context["capabilities"][Capability.EDIT_ORDER])
        self.assertFalse(context["capabilities"][Capability.VIEW_COSTS])
        self.assertFalse(context["capabilities"][Capability.VIEW_CUTTING_PLAN])

        # migrate/after_migrate executes this cleanup, removing the native row as
        # well so Frappe Desk metadata cannot show Add/Edit/Delete buttons.
        frappe.set_user("Administrator")
        revoke_automatic_role_business_grants()
        self.assertFalse(
            frappe.db.exists(
                "Custom DocPerm",
                {"parent": "Door Cutting Order", "role": "Desk User"},
            )
        )
        self.assertFalse(
            frappe.db.exists(
                "DocPerm",
                {"parent": "Door Cutting Order", "role": "Desk User"},
            )
        )

        self._fresh_user_context()
        for ptype in (
            "read",
            "create",
            "write",
            "delete",
            Capability.VIEW_COSTS,
            Capability.VIEW_CUTTING_PLAN,
        ):
            with self.subTest(ptype=ptype):
                self.assertFalse(
                    frappe.has_permission(
                        "Door Cutting Order",
                        ptype,
                        user=USER,
                    )
                )


if __name__ == "__main__":
    import unittest

    unittest.main()
