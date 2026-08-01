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


VIEWER_ROLE = "Almdina Settings Viewer Test"
CUTTING_ROLE = "Almdina Cutting Defaults Test"
ROUTING_ROLE = "Almdina Routing Manager Test"
EDGE_ROLE = "Almdina Edge Manager Test"
VIEWER_USER = "almdina.settings.viewer@example.com"
CUTTING_USER = "almdina.cutting.settings@example.com"
ROUTING_USER = "almdina.routing.manager@example.com"
EDGE_USER = "almdina.edge.manager@example.com"
ROUTING_NAME = "Almdina Integration Routing"
EDGE_NAME = "قشاط اختبار تكامل"


class TestFactoryMasterDataIntegration(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        sync_permission_types()
        for role in (VIEWER_ROLE, CUTTING_ROLE, ROUTING_ROLE, EDGE_ROLE):
            cls._ensure_role(role)
        cls._ensure_user(VIEWER_USER, VIEWER_ROLE)
        cls._ensure_user(CUTTING_USER, CUTTING_ROLE)
        cls._ensure_user(ROUTING_USER, ROUTING_ROLE)
        cls._ensure_user(EDGE_USER, EDGE_ROLE)

        repository = FrappePermissionMatrixRepository()
        repository.save_role_state(
            VIEWER_ROLE,
            {Capability.VIEW_FACTORY_SETTINGS: True},
        )
        repository.save_role_state(
            CUTTING_ROLE,
            {Capability.EDIT_FACTORY_CUTTING_DEFAULTS: True},
        )
        repository.save_role_state(
            ROUTING_ROLE,
            {
                Capability.CREATE_PRODUCTION_ROUTINGS: True,
                Capability.EDIT_PRODUCTION_ROUTINGS: True,
                Capability.DELETE_PRODUCTION_ROUTINGS: True,
            },
        )
        repository.save_role_state(
            EDGE_ROLE,
            {
                Capability.CREATE_EDGE_BANDING_TYPES: True,
                Capability.EDIT_EDGE_BANDING_TYPES: True,
                Capability.DELETE_EDGE_BANDING_TYPES: True,
            },
        )
        frappe.clear_cache()

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        cls._delete_test_records()
        frappe.db.delete(
            "Almdina Master Data Audit",
            {"changed_by": ["in", [VIEWER_USER, CUTTING_USER, ROUTING_USER, EDGE_USER]]},
        )
        for user in (VIEWER_USER, CUTTING_USER, ROUTING_USER, EDGE_USER):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in (VIEWER_ROLE, CUTTING_ROLE, ROUTING_ROLE, EDGE_ROLE):
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
                    "default_app": "almdina_erp",
                    "default_workspace": "Almdina Settings",
                }
            ).insert(ignore_permissions=True)
        roles = {row.role for row in (user.roles or [])}
        for required in ("Desk User", role):
            if required not in roles and frappe.db.exists("Role", required):
                user.append("roles", {"role": required})
        user.save(ignore_permissions=True)

    @classmethod
    def _delete_test_records(cls) -> None:
        settings = frappe.get_single("Almdina ERP Settings")
        if settings.default_production_routing == ROUTING_NAME:
            fallback = frappe.get_all(
                "Production Routing",
                filters={"name": ["!=", ROUTING_NAME], "disabled": 0},
                pluck="name",
                limit_page_length=1,
            )
            if fallback:
                settings.default_production_routing = fallback[0]
                settings.save(ignore_permissions=True)
        if frappe.db.exists("Production Routing", ROUTING_NAME):
            frappe.delete_doc("Production Routing", ROUTING_NAME, force=True, ignore_permissions=True)
        if frappe.db.exists("Edge Banding Type", EDGE_NAME):
            frappe.delete_doc("Edge Banding Type", EDGE_NAME, force=True, ignore_permissions=True)

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self._delete_test_records()
        frappe.db.delete(
            "Almdina Master Data Audit",
            {"target_name": ["in", [ROUTING_NAME, EDGE_NAME, "Almdina ERP Settings"]]},
        )
        self.original_settings = {
            "default_kerf_mm": frappe.db.get_single_value("Almdina ERP Settings", "default_kerf_mm"),
            "default_cutting_cost_per_board_usd": frappe.db.get_single_value(
                "Almdina ERP Settings", "default_cutting_cost_per_board_usd"
            ),
            "default_production_routing": frappe.db.get_single_value(
                "Almdina ERP Settings", "default_production_routing"
            ),
        }
        for user in (VIEWER_USER, CUTTING_USER, ROUTING_USER, EDGE_USER):
            frappe.clear_cache(user=user)
        frappe.clear_cache()

    def tearDown(self):
        frappe.set_user("Administrator")
        from almdina_erp.almdina_erp.services.production_settings_service import (
            update_production_settings,
        )

        restore = {
            "default_kerf_mm": self.original_settings["default_kerf_mm"],
            "default_cutting_cost_per_board_usd": self.original_settings[
                "default_cutting_cost_per_board_usd"
            ],
        }
        if self.original_settings["default_production_routing"]:
            restore["default_production_routing"] = self.original_settings[
                "default_production_routing"
            ]
        update_production_settings(restore)
        self._delete_test_records()
        frappe.db.delete(
            "Almdina Master Data Audit",
            {"target_name": ["in", [ROUTING_NAME, EDGE_NAME, "Almdina ERP Settings"]]},
        )
        frappe.clear_cache()
        super().tearDown()

    def test_settings_are_readable_but_updated_only_by_owned_section(self) -> None:
        from almdina_erp.almdina_erp.services.production_settings_service import (
            get_production_settings,
            update_production_settings,
        )

        frappe.set_user(VIEWER_USER)
        viewer = get_production_settings()
        self.assertFalse(viewer["permissions"]["sections"]["cutting"]["editable"])
        with self.assertRaises(frappe.PermissionError):
            update_production_settings({"default_kerf_mm": 4})

        frappe.set_user(CUTTING_USER)
        current = get_production_settings()
        next_kerf = float(current["default_kerf_mm"] or 0) + 0.25
        updated = update_production_settings({"default_kerf_mm": next_kerf})
        self.assertAlmostEqual(updated["default_kerf_mm"], next_kerf)
        with self.assertRaises(frappe.PermissionError):
            update_production_settings({"default_cutting_cost_per_board_usd": 99})

        audit = frappe.get_all(
            "Almdina Master Data Audit",
            filters={
                "target_doctype": "Almdina ERP Settings",
                "changed_by": CUTTING_USER,
            },
            fields=["action", "changed_fields"],
        )
        self.assertTrue(audit)
        self.assertTrue(
            any("default_kerf_mm" in (row.changed_fields or "") for row in audit)
        )

    def test_routing_crud_and_default_reference_delete_guard(self) -> None:
        from almdina_erp.almdina_erp.services.master_data_service import (
            delete_master_data_record,
            get_master_data_console,
            set_master_data_disabled,
        )
        from almdina_erp.almdina_erp.services.production_settings_service import (
            update_production_settings,
        )

        frappe.set_user(ROUTING_USER)
        routing = frappe.get_doc(
            {
                "doctype": "Production Routing",
                "routing_name": ROUTING_NAME,
                "disabled": 0,
                "stages": [
                    {
                        "doctype": "Production Routing Stage",
                        "sequence": 10,
                        "stage_type": "Cutting",
                        "required": 1,
                        "auto_complete_if_not_applicable": 0,
                    },
                    {
                        "doctype": "Production Routing Stage",
                        "sequence": 20,
                        "stage_type": "Edge Banding",
                        "required": 1,
                        "auto_complete_if_not_applicable": 1,
                    },
                ],
            }
        ).insert()
        self.assertEqual(routing.name, ROUTING_NAME)
        set_master_data_disabled("Production Routing", ROUTING_NAME, 1)
        self.assertEqual(
            frappe.db.get_value("Production Routing", ROUTING_NAME, "disabled"),
            1,
        )
        set_master_data_disabled("Production Routing", ROUTING_NAME, 0)

        console = get_master_data_console()
        self.assertTrue(
            any(row["name"] == ROUTING_NAME for row in console["routings"])
        )

        frappe.set_user("Administrator")
        update_production_settings({"default_production_routing": ROUTING_NAME})
        frappe.set_user(ROUTING_USER)
        with self.assertRaises(frappe.ValidationError):
            delete_master_data_record("Production Routing", ROUTING_NAME)

        frappe.set_user("Administrator")
        update_production_settings(
            {
                "default_production_routing": self.original_settings[
                    "default_production_routing"
                ]
            }
        )
        frappe.set_user(ROUTING_USER)
        deleted = delete_master_data_record("Production Routing", ROUTING_NAME)
        self.assertTrue(deleted["deleted"])
        self.assertFalse(frappe.db.exists("Production Routing", ROUTING_NAME))

    def test_edge_type_crud_is_independent_from_routing_permissions(self) -> None:
        from almdina_erp.almdina_erp.services.master_data_service import (
            delete_master_data_record,
            get_master_data_console,
            set_master_data_disabled,
        )

        frappe.set_user(EDGE_USER)
        edge = frappe.get_doc(
            {
                "doctype": "Edge Banding Type",
                "edge_type_name": EDGE_NAME,
                "english_name": "Integration Edge",
                "width_cm": 2,
                "thickness_mm": 1,
                "finish_type": "Regular",
                "application_method": "Machine",
                "rate_usd_per_meter": 1.5,
                "disabled": 0,
            }
        ).insert()
        self.assertEqual(edge.name, EDGE_NAME)
        set_master_data_disabled("Edge Banding Type", EDGE_NAME, 1)
        self.assertEqual(
            frappe.db.get_value("Edge Banding Type", EDGE_NAME, "disabled"),
            1,
        )
        console = get_master_data_console()
        self.assertEqual(console["routings"], [])
        self.assertTrue(any(row["name"] == EDGE_NAME for row in console["edge_types"]))
        delete_master_data_record("Edge Banding Type", EDGE_NAME)
        self.assertFalse(frappe.db.exists("Edge Banding Type", EDGE_NAME))

    def test_fixed_business_roles_receive_no_standard_master_data_grants(self) -> None:
        frappe.set_user("Administrator")
        for doctype in ("Production Routing", "Edge Banding Type"):
            for role in ("Production Manager", "System Manager", "Stock Manager", "Order Entry"):
                self.assertFalse(
                    frappe.db.exists(
                        "DocPerm",
                        {"parent": doctype, "role": role, "permlevel": 0},
                    )
                )


__all__ = ["TestFactoryMasterDataIntegration"]
