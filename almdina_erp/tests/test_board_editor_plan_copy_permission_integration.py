"""Board Editor plan copy must persist for a non-Administrator editor.

The employee has ``use_board_editor`` and the order visibility required to open
the source plan, and does not have optimizer, approval, export, or cost rights.
Create and snapshot save run through the real Cutting Plan permission hook.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import draft_key
from almdina_erp.almdina_erp.domain.cutting.plan_settings import normalize_plan_settings
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.board_editor_draft_store import (
    FrappeBoardEditorDraftStore,
)
from almdina_erp.almdina_erp.infrastructure.frappe.custom_docperm_capability_reader import (
    CustomDocPermCapabilityReader,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_context import (
    PLAN_COMMAND_FLAG,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_repository import (
    FrappeCuttingPlanCommandRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.permission_type_sync import (
    sync_permission_types,
)
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import (
    ProjectedPermissionMatrixRepository,
)
from almdina_erp.almdina_erp.services.board_editor_plan_create_service import (
    create_board_editor_plan_copy,
)
from almdina_erp.tests.test_board_editor_plan_materialize import (
    layout_rows,
    projection,
    projection_piece,
    source_snapshot,
)


_PIECES = [projection_piece("A", 1, 0, 0, 200, 200)]
_DERIVED_SNAPSHOT_KEYS = (
    "cut_path",
    "cut_paths",
    "overlays",
    "cutter_center_path",
    "cutter_center_paths",
    "toolpath",
    "toolpaths",
)


def _operational_source() -> dict:
    """Unit-test snapshots include stale overlays the real sanitizer rejects."""

    snapshot = source_snapshot(_PIECES)
    snapshot.pop("cut_path", None)
    for sheet in snapshot.get("sheets") or []:
        for key in _DERIVED_SNAPSHOT_KEYS:
            sheet.pop(key, None)
        for piece in sheet.get("pieces") or []:
            for key in _DERIVED_SNAPSHOT_KEYS:
                piece.pop(key, None)
    return snapshot


class TestBoardEditorPlanCopyPermissionIntegration(FrappeTestCase):
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
    def _grant(role: str, capabilities: Mapping[str, bool]) -> None:
        ProjectedPermissionMatrixRepository().save_role_state(role, dict(capabilities))

    @staticmethod
    def _refresh(user: str) -> None:
        frappe.clear_cache(user=user)
        frappe.clear_cache(doctype="Door Cutting Order")
        frappe.clear_cache(doctype="Cutting Plan")
        frappe.local.almdina_matrix_capabilities = {}

    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        sync_permission_types()
        token = frappe.generate_hash(length=10)
        self.editor_role = f"Board-Editor-{token}"
        self.viewer_role = f"Board-Viewer-{token}"
        self.scoped_role = f"Board-Scoped-{token}"
        self.editor = f"board-editor-{token}@example.test"
        self.viewer = f"board-viewer-{token}@example.test"
        self.scoped = f"board-scoped-{token}@example.test"
        self.visible = self._seed_order("VISIBLE", status="Draft", with_draft=True)
        self.admin_world = self._seed_order("ADMIN", status="Draft", with_draft=True)
        self.cancelled = self._seed_order("CANCELLED", status="Cancelled", with_draft=False)
        self.delivered = self._seed_order("DELIVERED", status="Delivered", with_draft=False)
        self._source_before = self._plan_row(self.visible["plan"])
        for role in (self.editor_role, self.viewer_role, self.scoped_role):
            self._create_role(role)
        self._create_user(self.editor, self.editor_role)
        self._create_user(self.viewer, self.viewer_role)
        self._create_user(self.scoped, self.scoped_role)
        self._grant(
            self.editor_role,
            {
                Capability.USE_BOARD_EDITOR: True,
                Capability.VIEW_ALL_ORDERS: True,
            },
        )
        self._grant(
            self.viewer_role,
            {
                Capability.VIEW_ALL_ORDERS: True,
                Capability.VIEW_CUTTING_PLAN: True,
                Capability.VIEW_SYSTEM_CUTTING_PLAN: True,
            },
        )
        self._grant(self.scoped_role, {Capability.USE_BOARD_EDITOR: True})
        for user in (self.editor, self.viewer, self.scoped):
            self._refresh(user)

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for world in (self.visible, self.admin_world, self.cancelled, self.delivered):
            frappe.db.delete("Board Editor Draft", {"door_cutting_order": world["order"]})
            frappe.db.delete("Cutting Plan", {"door_cutting_order": world["order"]})
            frappe.db.delete("Door Cutting Order Detail", {"parent": world["order"]})
            frappe.db.delete("Door Cutting Order", {"name": world["order"]})
        for role in (self.editor_role, self.viewer_role, self.scoped_role):
            frappe.db.delete("Custom DocPerm", {"role": role})
            frappe.db.delete("DocPerm", {"role": role})
            frappe.db.delete("Almdina Role Capability State", {"role": role})
        for user in (self.editor, self.viewer, self.scoped):
            if frappe.db.exists("User", user):
                frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in (self.editor_role, self.viewer_role, self.scoped_role):
            if frappe.db.exists("Role", role):
                frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    def _seed_order(self, suffix: str, *, status: str, with_draft: bool) -> dict[str, str]:
        token = frappe.generate_hash(length=8)
        order_name = f"TEST-BE-ORDER-{suffix}-{token}"
        plan_name = f"TEST-BE-PLAN-{suffix}-{token}"
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
                "name": order_name,
                **common,
                "status": status,
                "revision": 1,
                "revision_state": "Current",
                "board_description": "Board editor permission fixture",
                "board_width_cm": 122,
                "board_length_cm": 244,
            },
        )
        self._insert(
            "Door Cutting Order Detail",
            {
                "name": f"{order_name}-PIECE-1",
                **common,
                "parent": order_name,
                "parenttype": "Door Cutting Order",
                "parentfield": "pieces",
                "idx": 1,
                "piece_no": 1,
                "piece_instance_id": "A",
                "piece_type": "Regular",
                "qty": 1,
                "width_cm": 20,
                "length_cm": 20,
                "cut_width_cm": 20,
                "cut_length_cm": 20,
                "area_m2": 0.04,
                "allow_rotation": 1,
                "edge_cost_usd": 0,
            },
        )
        self._insert(
            "Cutting Plan",
            {
                "name": plan_name,
                **common,
                "door_cutting_order": order_name,
                "plan_kind": "Order",
                "revision": 1,
                "status": "Draft",
                "source_type": "System",
                "optimization_mode": "auto_pro",
                "machine_type": "CNC Router",
                "optimization_time_limit_sec": 10,
                "kerf_mm": 4,
                "trim_margin_mm": 5,
                "snapshot_json": json.dumps(_operational_source()),
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
        draft_name = ""
        if with_draft:
            draft = FrappeBoardEditorDraftStore().insert(
                {
                    "draft_key": draft_key(order_name, plan_name),
                    "door_cutting_order": order_name,
                    "source_plan": plan_name,
                    "source_input_fingerprint": "fp-1",
                    "source_content_revision": "rev-1",
                    "draft_version": 1,
                    "distribution_fingerprint": "stored",
                    "layout_json": layout_rows(_PIECES),
                }
            )
            draft_name = str(draft["name"])
        return {"order": order_name, "plan": plan_name, "draft": draft_name}

    def _plan_row(self, name: str) -> dict[str, object]:
        return frappe.db.get_value(
            "Cutting Plan",
            name,
            [
                "status",
                "source_type",
                "revision",
                "snapshot_json",
                "optimization_mode",
                "machine_type",
                "method_label",
                "approved_by",
                "based_on_plan",
            ],
            as_dict=True,
        )

    def _plan_count(self, order_name: str) -> int:
        return len(
            frappe.get_all(
                "Cutting Plan",
                filters={"door_cutting_order": order_name},
                pluck="name",
            )
        )

    def _copy(self, world: Mapping[str, str], request_id: str) -> dict:
        payload = {
            "plan": {
                "name": world["plan"],
                "content_revision_token": "rev-1",
                "input_fingerprint": "fp-1",
            },
            "projection": projection(_PIECES),
        }
        with patch(
            "almdina_erp.almdina_erp.services.board_editor_plan_create_service.get_board_editor_projection",
            return_value=payload,
        ):
            return create_board_editor_plan_copy(
                order_name=world["order"],
                plan_name=world["plan"],
                expected_draft_version=1,
                source_content_revision="rev-1",
                source_input_fingerprint="fp-1",
                create_request_id=request_id,
                draft_name=world["draft"],
            )

    def test_editor_grant_is_create_write_without_delete_or_optimizer(self) -> None:
        state = CustomDocPermCapabilityReader().role_capabilities(self.editor_role)
        self.assertTrue(state[Capability.USE_BOARD_EDITOR])
        self.assertTrue(state[Capability.VIEW_CUTTING_PLAN])
        self.assertTrue(state[Capability.VIEW_SYSTEM_CUTTING_PLAN])
        self.assertFalse(state[Capability.EDIT_OPTIMIZER_SETTINGS])
        self.assertFalse(state[Capability.RECALCULATE_PLAN])
        self.assertFalse(state[Capability.APPROVE_DXF])
        self.assertFalse(state[Capability.EXPORT_DXF])
        self.assertFalse(state[Capability.VIEW_COSTS])
        self.assertFalse(state[Capability.EDIT_COST_SETTINGS])

        rights = frappe.db.get_value(
            "Custom DocPerm",
            {
                "parent": "Cutting Plan",
                "role": self.editor_role,
                "permlevel": 0,
                "if_owner": 0,
            },
            ["read", "create", "write", "delete"],
            as_dict=True,
        )
        self.assertEqual(int(rights.read), 1)
        self.assertEqual(int(rights.create), 1)
        self.assertEqual(int(rights.write), 1)
        self.assertEqual(int(rights.delete), 0)
        cost_rights = frappe.db.get_value(
            "Custom DocPerm",
            {
                "parent": "Cutting Plan",
                "role": self.editor_role,
                "permlevel": 1,
                "if_owner": 0,
            },
            ["read", "write"],
            as_dict=True,
        )
        if cost_rights:
            self.assertEqual(int(cost_rights.read or 0), 0)
            self.assertEqual(int(cost_rights.write or 0), 0)

        frappe.set_user(self.editor)
        bare = frappe.new_doc("Cutting Plan")
        bare.door_cutting_order = self.visible["order"]
        self.assertFalse(frappe.has_permission(bare, "create", user=self.editor))
        self.assertFalse(frappe.has_permission(bare, "write", user=self.editor))
        self.assertFalse(frappe.has_permission(bare, "delete", user=self.editor))
        bare.flags[PLAN_COMMAND_FLAG] = Capability.USE_BOARD_EDITOR
        self.assertTrue(frappe.has_permission(bare, "create", user=self.editor))
        self.assertTrue(frappe.has_permission(bare, "write", user=self.editor))
        self.assertFalse(frappe.has_permission(bare, "delete", user=self.editor))

    def test_non_admin_editor_inserts_and_saves_a_draft_copy(self) -> None:
        frappe.set_user(self.editor)
        first = self._copy(self.visible, "req-editor-copy-1")
        self.assertTrue(first.get("ok"), first)
        self.assertFalse(first.get("idempotent"))
        self.assertEqual(first.get("status"), "Draft")
        self.assertEqual(first.get("source_type"), "Board Editor")
        self.assertFalse(first.get("approves_plan"))
        created_name = str(first["plan_name"])

        frappe.set_user(self.editor)
        second = self._copy(self.visible, "req-editor-copy-1")
        self.assertTrue(second.get("ok"), second)
        self.assertTrue(second.get("idempotent"))
        self.assertEqual(second.get("plan_name"), created_name)

        frappe.set_user("Administrator")
        self.assertEqual(self._plan_count(self.visible["order"]), 2)
        created = self._plan_row(created_name)
        self.assertEqual(created.status, "Draft")
        self.assertEqual(created.source_type, "Board Editor")
        self.assertEqual(created.based_on_plan, self.visible["plan"])
        self.assertEqual(int(created.revision), 2)
        self.assertFalse(created.approved_by)
        snapshot = json.loads(created.snapshot_json or "{}")
        self.assertTrue(snapshot.get("sheets"))
        self.assertEqual(snapshot.get("method_key"), "board_editor")
        self.assertEqual(self._plan_row(self.visible["plan"]), self._source_before)

        frappe.set_user(self.editor)
        existing = frappe.get_doc("Cutting Plan", created_name)
        existing.method_label = "Changed outside the board editor command"
        with self.assertRaises(frappe.PermissionError):
            existing.save()
        rogue = frappe.new_doc("Cutting Plan")
        rogue.plan_kind = "Order"
        rogue.door_cutting_order = self.visible["order"]
        rogue.source_type = "Board Editor"
        rogue.revision = 9
        rogue.status = "Draft"
        rogue.optimization_mode = "auto_pro"
        rogue.machine_type = "CNC Router"
        rogue.optimization_time_limit_sec = 10
        rogue.kerf_mm = 4
        rogue.trim_margin_mm = 5
        with self.assertRaises(frappe.PermissionError):
            rogue.insert()

        frappe.set_user("Administrator")
        reloaded = self._plan_row(created_name)
        self.assertNotEqual(reloaded.method_label, "Changed outside the board editor command")
        self.assertEqual(json.loads(reloaded.snapshot_json or "{}").get("method_key"), "board_editor")
        self.assertEqual(self._plan_count(self.visible["order"]), 2)

    def test_user_without_board_editor_cannot_copy_or_force_the_repository(self) -> None:
        frappe.set_user(self.viewer)
        with self.assertRaises(frappe.PermissionError):
            self._copy(self.visible, "req-viewer-denied")
        repository = FrappeCuttingPlanCommandRepository(Capability.USE_BOARD_EDITOR)
        with self.assertRaises(frappe.PermissionError):
            repository.create_draft(
                order_name=self.visible["order"],
                revision=3,
                status="Draft",
                source_type="Board Editor",
                based_on_plan=self.visible["plan"],
                settings=normalize_plan_settings(
                    optimization_mode="auto_pro",
                    machine_type="CNC Router",
                    optimization_time_limit_sec=10,
                    kerf_mm=4,
                    preferred_trim_mm=5,
                ),
            )
        frappe.set_user("Administrator")
        self.assertEqual(self._plan_count(self.visible["order"]), 1)

    def test_scoped_editor_cannot_copy_an_order_outside_assignment(self) -> None:
        order = frappe.get_doc("Door Cutting Order", self.visible["order"])
        frappe.set_user(self.scoped)
        self.assertFalse(frappe.has_permission(order, "read", user=self.scoped))
        with self.assertRaises(frappe.PermissionError):
            self._copy(self.visible, "req-scoped-denied")
        frappe.set_user("Administrator")
        self.assertEqual(self._plan_count(self.visible["order"]), 1)

    def test_locked_orders_are_not_copied(self) -> None:
        frappe.set_user(self.editor)
        for world, request_id in (
            (self.cancelled, "req-cancelled"),
            (self.delivered, "req-delivered"),
        ):
            with self.subTest(status=world["order"]):
                with self.assertRaises(frappe.PermissionError):
                    create_board_editor_plan_copy(
                        order_name=world["order"],
                        plan_name=world["plan"],
                        expected_draft_version=1,
                        source_content_revision="rev-1",
                        source_input_fingerprint="fp-1",
                        create_request_id=request_id,
                    )
        frappe.set_user("Administrator")
        self.assertEqual(self._plan_count(self.cancelled["order"]), 1)
        self.assertEqual(self._plan_count(self.delivered["order"]), 1)

    def test_administrator_copy_still_succeeds(self) -> None:
        frappe.set_user("Administrator")
        result = self._copy(self.admin_world, "req-administrator-copy")
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result.get("status"), "Draft")
        self.assertEqual(result.get("source_type"), "Board Editor")
        created = self._plan_row(str(result["plan_name"]))
        snapshot = json.loads(created.snapshot_json or "{}")
        self.assertEqual(created.status, "Draft")
        self.assertEqual(created.source_type, "Board Editor")
        self.assertTrue(snapshot.get("sheets"))
        self.assertEqual(snapshot.get("method_key"), "board_editor")
        self.assertEqual(self._plan_count(self.admin_world["order"]), 2)
