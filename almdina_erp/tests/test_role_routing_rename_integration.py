from __future__ import annotations

import json

import frappe
from frappe.tests.utils import FrappeTestCase


ROLE_ORIGINAL = "Almdina Routing Rename Original"
ROLE_RENAMED = "Almdina Routing Rename Updated"
ROLE_SECONDARY = "Almdina Routing Rename Secondary"
ROUTING_NAME = "Almdina Routing Role Rename Test"


class TestRoleRoutingRenameIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls._cleanup()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        cls._cleanup()
        frappe.clear_cache()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self._cleanup()

    def tearDown(self):
        frappe.set_user("Administrator")
        self._cleanup()
        frappe.clear_cache()
        super().tearDown()

    @classmethod
    def _cleanup(cls) -> None:
        if frappe.db.exists("Production Routing", ROUTING_NAME):
            frappe.delete_doc(
                "Production Routing",
                ROUTING_NAME,
                force=True,
                ignore_permissions=True,
            )
        roles = [ROLE_ORIGINAL, ROLE_RENAMED, ROLE_SECONDARY]
        frappe.db.delete("Almdina Role Audit", {"role_name": ["in", roles]})
        for role in roles:
            frappe.db.delete("Custom DocPerm", {"role": role})
            frappe.db.delete("DocPerm", {"role": role})
            metadata = frappe.db.get_value(
                "Almdina Role Metadata",
                {"role": role},
                "name",
            )
            if metadata:
                frappe.delete_doc(
                    "Almdina Role Metadata",
                    metadata,
                    force=True,
                    ignore_permissions=True,
                )
            if frappe.db.exists("Role", role):
                frappe.delete_doc(
                    "Role",
                    role,
                    force=True,
                    ignore_permissions=True,
                )

    def test_rename_updates_a_role_in_every_routing_snapshot_field(self) -> None:
        from almdina_erp.almdina_erp.services.role_management_service import (
            create_factory_role,
            delete_factory_role,
            get_role_details,
            update_factory_role,
        )

        create_factory_role({"name": ROLE_ORIGINAL})
        create_factory_role({"name": ROLE_SECONDARY})
        routing = frappe.get_doc(
            {
                "doctype": "Production Routing",
                "routing_name": ROUTING_NAME,
                "disabled": 0,
                "stages": [
                    {
                        "sequence": 10,
                        "stage_type": "ROLE-RENAME-TEST",
                        "department_label": "اختبار إعادة تسمية الدور",
                        # Keep the renamed role second: the legacy Link field
                        # alone cannot discover or update this reference.
                        "eligible_roles_json": json.dumps(
                            [ROLE_SECONDARY, ROLE_ORIGINAL],
                            ensure_ascii=False,
                        ),
                        "required": 1,
                        "auto_complete_if_not_applicable": 0,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        stage_name = str(routing.stages[0].name)

        before = get_role_details(ROLE_ORIGINAL)
        self.assertEqual(before["production_routing_references"], 1)
        with self.assertRaises(frappe.ValidationError):
            delete_factory_role(ROLE_ORIGINAL, 1)

        renamed = update_factory_role(
            ROLE_ORIGINAL,
            {"name": ROLE_RENAMED},
        )["role"]
        self.assertEqual(renamed["name"], ROLE_RENAMED)
        self.assertFalse(frappe.db.exists("Role", ROLE_ORIGINAL))

        snapshot = frappe.db.get_value(
            "Production Routing Stage",
            stage_name,
            [
                "eligible_roles_json",
                "eligible_roles_display",
                "operational_role",
            ],
            as_dict=True,
        )
        self.assertEqual(
            json.loads(snapshot.eligible_roles_json),
            [ROLE_SECONDARY, ROLE_RENAMED],
        )
        self.assertEqual(
            snapshot.eligible_roles_display,
            f"{ROLE_SECONDARY}، {ROLE_RENAMED}",
        )
        self.assertEqual(snapshot.operational_role, ROLE_SECONDARY)

        after = get_role_details(ROLE_RENAMED)
        self.assertEqual(after["production_routing_references"], 1)
        with self.assertRaises(frappe.ValidationError):
            delete_factory_role(ROLE_RENAMED, 1)


if __name__ == "__main__":
    import unittest

    unittest.main()
