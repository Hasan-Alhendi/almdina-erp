from __future__ import annotations

import json
from collections.abc import Mapping

import frappe
from frappe.handler import execute_cmd
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.custom_docperm_capability_reader import (
    CustomDocPermCapabilityReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    cost_settings_edit_allowed,
)


class TestSpecialCostPermissionRuntimeIntegration(FrappeTestCase):
    """Prove grant/revoke behavior through real roles, DocPerms, records and RPC."""

    @staticmethod
    def _insert(doctype: str, values: Mapping[str, object]) -> None:
        columns = list(values)
        names = ", ".join(f"`{column}`" for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        frappe.db.sql(
            f"INSERT INTO `tab{doctype}` ({names}) VALUES ({placeholders})",
            tuple(values[column] for column in columns),
        )

    @staticmethod
    def _create_role(role: str) -> None:
        frappe.get_doc(
            {"doctype": "Role", "role_name": role, "desk_access": 1}
        ).insert(ignore_permissions=True)

    @staticmethod
    def _create_user(email: str, role: str) -> None:
        frappe.get_doc(
            {
                "doctype": "User",
                "email": email,
                "first_name": role,
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "System User",
                "roles": [{"role": role}],
            }
        ).insert(ignore_permissions=True)

    @staticmethod
    def _grant(role: str, *, edit_cost_settings: bool) -> None:
        ProjectedPermissionMatrixRepository().save_role_state(
            role,
            {
                Capability.VIEW_ORDERS: True,
                Capability.VIEW_COSTS: True,
                Capability.EDIT_COST_SETTINGS: edit_cost_settings,
            },
        )

    @staticmethod
    def _refresh_permissions(user: str) -> None:
        frappe.clear_cache(user=user)
        frappe.clear_cache(doctype="Door Cutting Order")
        frappe.clear_cache(doctype="Cutting Plan")
        frappe.local.almdina_matrix_capabilities = {}

    @staticmethod
    def _execute_rpc(method: str) -> dict:
        """Dispatch through Frappe's real RPC handler with a real POST request."""

        previous_request = getattr(frappe.local, "request", None)
        frappe.local.request = Request(EnvironBuilder(method="POST").get_environ())
        try:
            return execute_cmd(method)
        finally:
            frappe.local.request = previous_request

    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        sync_permission_types()
        token = frappe.generate_hash(length=12)
        self.role_one = f"Cost-Role-{token}"
        self.role_two = f"Cost-Role-{frappe.generate_hash(length=12)}"
        self.user_one = f"cost-{token}@example.test"
        self.user_two = f"cost-{frappe.generate_hash(length=12)}@example.test"
        self.order_name = f"TEST-SPECIAL-COST-{token}"
        self.piece_name = f"TEST-SPECIAL-ROW-{token}"
        self.plan_name = f"TEST-SPECIAL-PLAN-{token}"
        now = now_datetime()
        common = {
            "owner": "Administrator",
            "creation": now,
            "modified": now,
            "modified_by": "Administrator",
            "docstatus": 0,
            "idx": 0,
        }
        self._insert(
            "Door Cutting Order",
            {
                "name": self.order_name,
                **common,
                "status": "Draft",
                "revision": 1,
                "revision_state": "Current",
                "board_description": "Integration fixture",
                "board_rate_usd": 10,
                "cutting_cost_per_board_usd": 1,
                "mdf_cost_usd": 10,
                "cutting_cost_usd": 1,
                "total_cost_usd": 11,
            },
        )
        self._insert(
            "Door Cutting Order Detail",
            {
                "name": self.piece_name,
                **common,
                "parent": self.order_name,
                "parenttype": "Door Cutting Order",
                "parentfield": "pieces",
                "idx": 1,
                "piece_no": 1,
                "piece_type": "Special",
                "qty": 1,
                "width_cm": 40,
                "length_cm": 80,
                "area_m2": 0.32,
                "edge_cost_usd": 2,
                "special_shape_price_status": "Estimated",
                "special_shape_custom_unit_price_usd": 0,
            },
        )
        self._insert(
            "Cutting Plan",
            {
                "name": self.plan_name,
                **common,
                "door_cutting_order": self.order_name,
                "plan_kind": "Order",
                "revision": 1,
                "status": "Draft",
                "source_type": "System",
                "snapshot_json": json.dumps(
                    {
                        "physical_execution_contract": 1,
                        "sheets": [
                            {
                                "sheet_no": 1,
                                "resource_kind": "FULL_BOARD",
                                "pieces": [
                                    {
                                        "piece_instance_id": "piece:1",
                                        "source_piece_no": 1,
                                        "resource_kind": "FULL_BOARD",
                                    }
                                ],
                            }
                        ],
                    }
                ),
                "required_boards": 1,
                "cost_snapshot_version": 1,
                "board_rate_usd": 10,
                "cutting_cost_per_board_usd": 1,
                "mdf_cost_usd": 10,
                "cutting_cost_usd": 1,
                "edge_cost_usd": 0,
                "total_cost_usd": 11,
                "offcut_price_usd": 0,
            },
        )
        self._create_role(self.role_one)
        self._create_role(self.role_two)
        self._create_user(self.user_one, self.role_one)
        self._create_user(self.user_two, self.role_two)
        self._grant(self.role_one, edit_cost_settings=True)
        self._grant(self.role_two, edit_cost_settings=False)
        self._refresh_permissions(self.user_one)
        self._refresh_permissions(self.user_two)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.delete("Door Cutting Order Detail", {"parent": self.order_name})
        frappe.db.delete("Cutting Plan", {"door_cutting_order": self.order_name})
        frappe.db.delete("Door Cutting Order", {"name": self.order_name})
        for role in (self.role_one, self.role_two):
            frappe.db.delete("Custom DocPerm", {"role": role})
            frappe.db.delete("DocPerm", {"role": role})
            frappe.db.delete("Almdina Role Capability State", {"role": role})
        for user in (self.user_one, self.user_two):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in (self.role_one, self.role_two):
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    def _save_special_price(
        self,
        user: str,
        price: float,
        *,
        cost_settings: dict[str, float] | None = None,
    ) -> dict:
        frappe.set_user(user)
        order = frappe.get_doc("Door Cutting Order", self.order_name)
        self.assertTrue(frappe.has_permission(order, "read", user=user))
        frappe.local.form_dict = frappe._dict(
            order_name=self.order_name,
            cost_settings=cost_settings,
            special_prices=[
                {
                    "piece_name": self.piece_name,
                    "unit_price_usd": price,
                    "note": "real role integration",
                }
            ],
            expected_modified=str(order.modified),
        )
        return self._execute_rpc(
            "almdina_erp.almdina_erp.services.cost_permission_service.save_cost_workspace"
        )

    def test_real_random_role_grant_revoke_and_second_role_use_same_policy(self) -> None:
        reader = CustomDocPermCapabilityReader()
        first_state = reader.role_capabilities(self.role_one)
        self.assertTrue(first_state[Capability.EDIT_COST_SETTINGS])
        self.assertFalse(first_state[Capability.APPROVE_SPECIAL_PRICE])
        self.assertFalse(first_state[Capability.EDIT_SPECIAL_PRICE])
        self.assertTrue(
            cost_settings_edit_allowed(
                frappe.get_doc("Door Cutting Order", self.order_name),
                user=self.user_one,
            )
        )

        for stage in ("Draft", "Pending Review", "Arbitrary Production Label", "Delivered"):
            frappe.db.set_value(
                "Door Cutting Order", self.order_name, "status", stage, update_modified=False
            )
            self.assertTrue(
                cost_settings_edit_allowed(
                    frappe.get_doc("Door Cutting Order", self.order_name),
                    user=self.user_one,
                ),
                f"Stage label {stage!r} must not define Cost Settings authority",
            )
        frappe.db.set_value(
            "Door Cutting Order", self.order_name, "status", "Cancelled", update_modified=False
        )
        self.assertFalse(
            cost_settings_edit_allowed(
                frappe.get_doc("Door Cutting Order", self.order_name),
                user=self.user_one,
            ),
            "Cancelled documents remain blocked by the common Cost Settings policy",
        )
        frappe.db.set_value(
            "Door Cutting Order", self.order_name, "status", "Draft", update_modified=False
        )
        frappe.db.set_value(
            "Door Cutting Order",
            self.order_name,
            "revision_state",
            "Superseded",
            update_modified=False,
        )
        self.assertFalse(
            cost_settings_edit_allowed(
                frappe.get_doc("Door Cutting Order", self.order_name),
                user=self.user_one,
            )
        )
        frappe.db.set_value(
            "Door Cutting Order", self.order_name, "revision_state", "Current", update_modified=False
        )
        frappe.db.set_value(
            "Door Cutting Order", self.order_name, "docstatus", 1, update_modified=False
        )
        self.assertFalse(
            cost_settings_edit_allowed(
                frappe.get_doc("Door Cutting Order", self.order_name),
                user=self.user_one,
            ),
            "Submitted docstatus remains blocked by the common Cost Settings policy",
        )
        frappe.db.set_value(
            "Door Cutting Order", self.order_name, "docstatus", 0, update_modified=False
        )

        renamed_role = f"Renamed-{frappe.generate_hash(length=12)}"
        frappe.rename_doc("Role", self.role_one, renamed_role, force=True)
        self.role_one = renamed_role
        self._refresh_permissions(self.user_one)
        self.assertTrue(
            cost_settings_edit_allowed(
                frappe.get_doc("Door Cutting Order", self.order_name),
                user=self.user_one,
            ),
            "Changing a granted Role's name must not change its capability decision",
        )

        self._save_special_price(
            self.user_one,
            25,
            cost_settings={
                "board_rate_usd": 12,
                "cutting_cost_per_board_usd": 2,
                "offcut_price_usd": 0,
            },
        )
        self.assertEqual(
            frappe.db.get_value(
                "Door Cutting Order Detail",
                self.piece_name,
                "special_shape_custom_unit_price_usd",
            ),
            25,
        )
        self.assertEqual(
            frappe.db.get_value("Cutting Plan", self.plan_name, "board_rate_usd"),
            12,
            "Cost settings and Special price must persist through one RPC command",
        )

        for stage, price in (("Arbitrary Production Label", 26), ("Delivered", 27)):
            frappe.db.set_value(
                "Door Cutting Order", self.order_name, "status", stage, update_modified=False
            )
            self._save_special_price(self.user_one, price)
            self.assertEqual(
                frappe.db.get_value(
                    "Door Cutting Order Detail",
                    self.piece_name,
                    "special_shape_custom_unit_price_usd",
                ),
                price,
                f"Special pricing must follow the shared Cost decision at {stage}",
            )
        frappe.db.set_value(
            "Door Cutting Order", self.order_name, "status", "Draft", update_modified=False
        )

        order = frappe.get_doc("Door Cutting Order", self.order_name)
        frappe.local.form_dict = frappe._dict(
            order_name=self.order_name,
            cost_settings={
                "board_rate_usd": 18,
                "cutting_cost_per_board_usd": 4,
                "offcut_price_usd": 0,
            },
            special_prices=[
                {
                    "piece_name": "OUTSIDE-ORDER-ROW",
                    "unit_price_usd": 99,
                    "note": "must roll back both financial changes",
                }
            ],
            expected_modified=str(order.modified),
        )
        frappe.db.savepoint("special_cost_atomicity")
        with self.assertRaises(frappe.PermissionError):
            self._execute_rpc(
                "almdina_erp.almdina_erp.services.cost_permission_service.save_cost_workspace"
            )
        frappe.db.rollback(save_point="special_cost_atomicity")
        self.assertEqual(
            frappe.db.get_value("Cutting Plan", self.plan_name, "board_rate_usd"),
            12,
            "A failed combined RPC cannot leave a partial Cost Settings write",
        )
        self.assertEqual(
            frappe.db.get_value(
                "Door Cutting Order Detail",
                self.piece_name,
                "special_shape_custom_unit_price_usd",
            ),
            27,
            "A failed combined RPC cannot leave a partial Special price write",
        )

        self._grant(self.role_one, edit_cost_settings=False)
        self._refresh_permissions(self.user_one)
        self.assertFalse(
            reader.role_capabilities(self.role_one)[Capability.EDIT_COST_SETTINGS]
        )
        self.assertFalse(
            cost_settings_edit_allowed(
                frappe.get_doc("Door Cutting Order", self.order_name),
                user=self.user_one,
            )
        )
        frappe.set_user(self.user_one)
        order = frappe.get_doc("Door Cutting Order", self.order_name)
        frappe.local.form_dict = frappe._dict(
            order_name=self.order_name,
            special_prices=[
                {
                    "piece_name": self.piece_name,
                    "unit_price_usd": 30,
                    "note": "must be denied after revoke",
                }
            ],
            expected_modified=str(order.modified),
        )
        with self.assertRaises(frappe.PermissionError):
            self._execute_rpc(
                "almdina_erp.almdina_erp.services.cost_permission_service.save_cost_workspace"
            )
        self.assertEqual(
            frappe.db.get_value(
                "Door Cutting Order Detail",
                self.piece_name,
                "special_shape_custom_unit_price_usd",
            ),
            27,
        )

        self._grant(self.role_two, edit_cost_settings=True)
        self._refresh_permissions(self.user_two)
        second_state = reader.role_capabilities(self.role_two)
        self.assertTrue(second_state[Capability.EDIT_COST_SETTINGS])
        self.assertFalse(second_state[Capability.APPROVE_SPECIAL_PRICE])
        self.assertFalse(second_state[Capability.EDIT_SPECIAL_PRICE])
        self.assertTrue(
            cost_settings_edit_allowed(
                frappe.get_doc("Door Cutting Order", self.order_name),
                user=self.user_two,
            )
        )
        self._save_special_price(self.user_two, 35)
        self.assertEqual(
            frappe.db.get_value(
                "Door Cutting Order Detail",
                self.piece_name,
                "special_shape_custom_unit_price_usd",
            ),
            35,
        )


__all__ = ["TestSpecialCostPermissionRuntimeIntegration"]
