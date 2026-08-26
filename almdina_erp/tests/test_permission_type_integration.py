from __future__ import annotations

import unittest

import frappe

from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    Capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)


class TestPermissionTypeIntegration(unittest.TestCase):
    @staticmethod
    def _ensure_user(role_name: str, user_email: str) -> None:
        if not frappe.db.exists("Role", role_name):
            frappe.get_doc(
                {
                    "doctype": "Role",
                    "role_name": role_name,
                    "desk_access": 1,
                }
            ).insert(ignore_permissions=True)

        if frappe.db.exists("User", user_email):
            user = frappe.get_doc("User", user_email)
        else:
            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": user_email,
                    "first_name": "Dynamic Permission",
                    "enabled": 1,
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True)
        if role_name not in {row.role for row in (user.roles or [])}:
            user.append("roles", {"role": role_name})
            user.save(ignore_permissions=True)

    def _assert_arbitrary_role_grant(self, permission_type: str, suffix: str) -> None:
        role_name = f"Almdina Dynamic Permission {suffix}"
        user_email = f"almdina.dynamic.{suffix.lower()}@example.com"
        target_doctype = CAPABILITY_CATALOG[permission_type].applies_to
        self._ensure_user(role_name, user_email)

        frappe.db.delete(
            "Custom DocPerm",
            {"parent": target_doctype, "role": role_name},
        )
        frappe.get_doc(
            {
                "doctype": "Custom DocPerm",
                "parent": target_doctype,
                "parenttype": "DocType",
                "parentfield": "permissions",
                "role": role_name,
                "permlevel": 0,
                "read": 1,
                permission_type: 1,
            }
        ).insert(ignore_permissions=True)
        frappe.clear_cache(user=user_email)
        frappe.clear_cache(doctype=target_doctype)

        try:
            self.assertTrue(
                frappe.has_permission(
                    target_doctype,
                    ptype=permission_type,
                    user=user_email,
                )
            )
        finally:
            frappe.db.delete(
                "Custom DocPerm",
                {"parent": target_doctype, "role": role_name},
            )
            frappe.clear_cache(user=user_email)
            frappe.clear_cache(doctype=target_doctype)

    def test_business_permission_types_are_installed_without_role_grants(self) -> None:
        capabilities = (
            Capability.CREATE_ORDER_REVISION,
            Capability.SUBMIT_ORDER,
            Capability.APPROVE_ORDER,
            Capability.CANCEL_ORDER,
            Capability.RETURN_ORDER_TO_DRAFT,
            Capability.DISPATCH_ORDER,
            Capability.START_ASSIGNED_STAGE,
            Capability.HANDOFF_ASSIGNED_STAGE,
            Capability.REVERT_DEPARTMENT,
            Capability.MARK_DELIVERED,
            Capability.REASSIGN_WORKER,
            Capability.VIEW_SHOP_FLOOR_HISTORY,
            Capability.RECALCULATE_PLAN,
            Capability.EXPORT_DXF,
            Capability.UPLOAD_DXF,
            Capability.REPLACE_DXF,
            Capability.APPROVE_DXF,
            Capability.VIEW_COSTS,
            Capability.EDIT_COST_SETTINGS,
            Capability.EDIT_SPECIAL_PRICE,
            Capability.APPROVE_SPECIAL_PRICE,
            Capability.PRINT_CUSTOMER_INVOICE,
            Capability.PRINT_INTERNAL_COST_REPORT,
        )
        for permission_type in capabilities:
            with self.subTest(permission_type=permission_type):
                target_doctype = CAPABILITY_CATALOG[permission_type].applies_to
                self.assertTrue(
                    frappe.db.exists(
                        "Permission Type",
                        {
                            "perm_type": permission_type,
                            "doc_type": target_doctype,
                        },
                    )
                )
                self.assertTrue(frappe.get_meta("DocPerm").has_field(permission_type))
                self.assertTrue(
                    frappe.get_meta("Custom DocPerm").has_field(permission_type)
                )
                self.assertEqual(
                    frappe.db.count(
                        "Custom DocPerm",
                        filters={
                            "parent": target_doctype,
                            permission_type: 1,
                        },
                    ),
                    0,
                )

    def test_administrator_can_grant_approval_to_an_arbitrary_role(self) -> None:
        self._assert_arbitrary_role_grant(Capability.APPROVE_DXF, "Approval")

    def test_administrator_can_grant_internal_report_printing_to_any_role(self) -> None:
        self._assert_arbitrary_role_grant(
            Capability.PRINT_INTERNAL_COST_REPORT,
            "InternalReport",
        )

    def test_administrator_can_grant_lifecycle_actions_to_any_role(self) -> None:
        self._assert_arbitrary_role_grant(Capability.SUBMIT_ORDER, "SubmitOrder")
        self._assert_arbitrary_role_grant(Capability.APPROVE_ORDER, "ApproveOrder")
        self._assert_arbitrary_role_grant(Capability.CANCEL_ORDER, "CancelOrder")
        self._assert_arbitrary_role_grant(
            Capability.RETURN_ORDER_TO_DRAFT,
            "ReturnOrder",
        )

    def test_administrator_can_grant_production_actions_to_any_role(self) -> None:
        grants = (
            (Capability.DISPATCH_ORDER, "DispatchOrder"),
            (Capability.START_ASSIGNED_STAGE, "StartStage"),
            (Capability.HANDOFF_ASSIGNED_STAGE, "HandoffStage"),
            (Capability.REVERT_DEPARTMENT, "RevertDepartment"),
            (Capability.MARK_DELIVERED, "MarkDelivered"),
            (Capability.REASSIGN_WORKER, "ReassignWorker"),
        )
        for permission_type, suffix in grants:
            with self.subTest(permission_type=permission_type):
                self._assert_arbitrary_role_grant(permission_type, suffix)

    def test_permission_type_sync_repairs_existing_custom_field_metadata(self) -> None:
        custom_field = frappe.db.get_value(
            "Custom Field",
            {
                "dt": "Custom DocPerm",
                "fieldname": Capability.UPLOAD_DXF,
            },
            ["name", "depends_on"],
            as_dict=True,
        )
        self.assertIsNotNone(custom_field)
        original_depends_on = custom_field.depends_on
        try:
            frappe.db.set_value(
                "Custom Field",
                custom_field.name,
                "depends_on",
                "eval:false",
                update_modified=False,
            )
            sync_permission_types()
            repaired = frappe.db.get_value(
                "Custom Field",
                custom_field.name,
                "depends_on",
            )
            self.assertNotEqual(repaired, "eval:false")
            self.assertIn("Cutting Plan", repaired or "")
            self.assertNotIn("Door Cutting Order", repaired or "")
        finally:
            frappe.db.set_value(
                "Custom Field",
                custom_field.name,
                "depends_on",
                original_depends_on,
                update_modified=False,
            )
            frappe.clear_cache(doctype="Custom DocPerm")

    def test_permission_type_sync_is_idempotent(self) -> None:
        before = frappe.db.count("Permission Type")
        sync_permission_types()
        sync_permission_types()
        self.assertEqual(frappe.db.count("Permission Type"), before)


if __name__ == "__main__":
    unittest.main()
