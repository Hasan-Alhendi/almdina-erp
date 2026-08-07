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
        if frappe.db.exists("Role", ROLE):
            frappe.delete_doc("Role", ROLE, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

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

        # Simulate the next authenticated request rather than relying on the
        # Administrator request-local role/capability caches used above.
        frappe.clear_cache(user=USER)
        for doctype in ("Door Cutting Order", "Cutting Plan", "Production Stage"):
            frappe.clear_cache(doctype=doctype)
        frappe.local.role_permissions = {}
        if hasattr(frappe.local, "almdina_matrix_capabilities"):
            del frappe.local.almdina_matrix_capabilities
        frappe.set_user(USER)

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
        self.assertTrue(frappe.has_permission("Door Cutting Order", Capability.UPLOAD_DXF, user=USER))

        # These two assertions reproduce the missing bridge in the old code:
        # the capability lived on Door Cutting Order while the actual records
        # had no native DocPerm row for arbitrary roles.
        self.assertTrue(frappe.has_permission("Cutting Plan", "read", user=USER))
        self.assertTrue(frappe.has_permission("Production Stage", "read", user=USER))
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


if __name__ == "__main__":
    import unittest

    unittest.main()
