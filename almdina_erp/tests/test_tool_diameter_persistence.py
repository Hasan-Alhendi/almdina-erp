"""Layer tool diameters must survive save and be the values DXF export reads."""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.domain.cutting.liner_geometry import LinerPiece
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import generate_toolpath
from almdina_erp.almdina_erp.domain.cutting.tool_diameters import diameters_for_record
from almdina_erp.almdina_erp.services import cutting_plan_command_service as commands
from almdina_erp.almdina_erp.services.cutting_plan_workspace_query_service import (
    get_plan_workspace_snapshot,
)
from almdina_erp.almdina_erp.services.dxf_export_service import _with_tool_diameters
from almdina_erp.almdina_erp.services.plan_settings_edit_service import save_plan_settings


class TestToolDiameterPersistence(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.orders: list[str] = []

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self.orders:
            for plan in frappe.get_all(
                "Cutting Plan",
                filters={"door_cutting_order": name},
                pluck="name",
            ):
                frappe.db.delete("Cutting Plan", {"name": plan})
            frappe.db.delete("Door Cutting Order Detail", {"parent": name})
            frappe.db.delete("Door Cutting Order", {"name": name})
        super().tearDown()

    @staticmethod
    def _insert(doctype, values):
        now = now_datetime()
        values = dict(
            owner="Administrator",
            creation=now,
            modified=now,
            modified_by="Administrator",
            docstatus=0,
            idx=0,
        ) | values
        columns = ", ".join(f"`{field}`" for field in values)
        params = ", ".join(["%s"] * len(values))
        frappe.db.sql(
            f"INSERT INTO `tab{doctype}` ({columns}) VALUES ({params})",
            tuple(values.values()),
        )

    def _order(self):
        name = "TEST-TD-" + frappe.generate_hash(length=12)
        self.orders.append(name)
        self._insert(
            "Door Cutting Order",
            dict(
                name=name,
                status="Draft",
                revision=1,
                revision_state="Current",
                board_description="Tool diameter persistence",
                allow_piece_mirroring=1,
                board_width_cm=100,
                board_length_cm=100,
                full_board_width_mm=1000,
                full_board_length_mm=1000,
            ),
        )
        return frappe.get_doc("Door Cutting Order", name)

    def _seed(self, liner=3, handle=6, groove=5):
        order = self._order()
        commands.save_system_plan_settings(
            order,
            dict(
                packing_mode="Auto",
                cutting_machine_type="CNC Router",
                kerf_mm=3,
                trim_margin_mm=0,
                optimization_time_limit_sec=0.4,
            ),
        )
        commands.save_system_plan_settings(
            order,
            dict(
                liner_tool_diameter_mm=liner,
                handle_recess_tool_diameter_mm=handle,
                rear_groove_tool_diameter_mm=groove,
            ),
        )
        plan_name = self._system_draft_name(order)
        frappe.db.set_value(
            "Cutting Plan",
            plan_name,
            {
                "plan_needs_recalculation": 0,
                "snapshot_json": '{"sentinel":"layout"}',
            },
            update_modified=False,
        )
        frappe.clear_document_cache("Cutting Plan", plan_name)
        return order, plan_name

    def _system_draft_name(self, order):
        return frappe.get_all(
            "Cutting Plan",
            filters={
                "door_cutting_order": order.name,
                "source_type": "System",
                "status": "Draft",
            },
            pluck="name",
        )[0]

    def _stored(self, plan_name):
        frappe.clear_document_cache("Cutting Plan", plan_name)
        return frappe.db.get_value(
            "Cutting Plan",
            plan_name,
            [
                "name",
                "status",
                "source_type",
                "kerf_mm",
                "liner_tool_diameter_mm",
                "handle_recess_tool_diameter_mm",
                "rear_groove_tool_diameter_mm",
                "plan_needs_recalculation",
                "snapshot_json",
            ],
            as_dict=True,
        )

    def _workspace_settings(self, order, key):
        snapshot = get_plan_workspace_snapshot(order.name)
        row = (snapshot.get("plans") or {}).get(key) or {}
        return row.get("settings") or {}

    def _assert_saved(self, order, plan_name, *, liner, handle, groove):
        stored = self._stored(plan_name)
        self.assertEqual(flt(stored.liner_tool_diameter_mm), liner)
        self.assertEqual(flt(stored.handle_recess_tool_diameter_mm), handle)
        self.assertEqual(flt(stored.rear_groove_tool_diameter_mm), groove)
        self.assertEqual(flt(stored.kerf_mm), 3)
        self.assertEqual(int(stored.plan_needs_recalculation or 0), 0)
        self.assertEqual(stored.snapshot_json, '{"sentinel":"layout"}')
        reloaded = frappe.get_doc("Cutting Plan", plan_name)
        self.assertEqual(flt(reloaded.liner_tool_diameter_mm), liner)
        self.assertEqual(flt(reloaded.handle_recess_tool_diameter_mm), handle)
        self.assertEqual(flt(reloaded.rear_groove_tool_diameter_mm), groove)
        visible = self._workspace_settings(order, "system_draft")
        self.assertEqual(flt(visible.get("liner_tool_diameter_mm")), liner)
        self.assertEqual(flt(visible.get("handle_recess_tool_diameter_mm")), handle)
        self.assertEqual(flt(visible.get("rear_groove_tool_diameter_mm")), groove)
        refreshed = self._workspace_settings(order, "system_draft")
        self.assertEqual(flt(refreshed.get("liner_tool_diameter_mm")), liner)
        self.assertEqual(flt(refreshed.get("handle_recess_tool_diameter_mm")), handle)
        self.assertEqual(flt(refreshed.get("rear_groove_tool_diameter_mm")), groove)
        return reloaded

    def test_liner_diameter_persists_through_database_workspace_and_refresh(self):
        order, plan_name = self._seed()
        result = save_plan_settings(order.name, liner_tool_diameter_mm=4)
        self.assertIn("liner_tool_diameter_mm", result["changed_fields"])
        self.assertEqual(int(result["plan_needs_recalculation"]), 0)
        self.assertEqual(result["cutting_plan"], plan_name)
        self._assert_saved(order, plan_name, liner=4, handle=6, groove=5)

    def test_handle_recess_persists_when_the_plan_is_read_again(self):
        order, plan_name = self._seed()
        commands.save_system_plan_settings(
            order,
            dict(handle_recess_tool_diameter_mm=8),
        )
        frappe.clear_document_cache("Cutting Plan", plan_name)
        reopened = frappe.get_doc("Cutting Plan", plan_name)
        self.assertEqual(flt(reopened.handle_recess_tool_diameter_mm), 8)
        self.assertEqual(flt(reopened.liner_tool_diameter_mm), 3)
        self.assertEqual(flt(reopened.rear_groove_tool_diameter_mm), 5)
        self._assert_saved(order, plan_name, liner=3, handle=8, groove=5)

    def test_rear_groove_change_does_not_replace_the_other_bits(self):
        order, plan_name = self._seed()
        commands.save_system_plan_settings(
            order,
            dict(rear_groove_tool_diameter_mm=3),
        )
        self._assert_saved(order, plan_name, liner=3, handle=6, groove=3)

    def test_all_three_diameters_persist_in_one_save(self):
        order, plan_name = self._seed(liner=3, handle=6, groove=5)
        commands.save_system_plan_settings(
            order,
            dict(
                liner_tool_diameter_mm=4,
                handle_recess_tool_diameter_mm=8,
                rear_groove_tool_diameter_mm=3,
            ),
        )
        self._assert_saved(order, plan_name, liner=4, handle=8, groove=3)

    def _clone_plan(self, source_name, **overrides):
        row = frappe.db.get_value("Cutting Plan", source_name, "*", as_dict=True)
        values = {key: row[key] for key in row if key != "name"}
        values["name"] = "TD-CP-" + frappe.generate_hash(length=10)
        values.update(overrides)
        self._insert("Cutting Plan", values)
        return values["name"]

    def test_system_draft_save_does_not_rewrite_uploaded_or_approved_plans(self):
        order, plan_name = self._seed()
        approved_name = self._clone_plan(
            plan_name,
            status="Approved",
            source_type="System",
            revision=20,
            liner_tool_diameter_mm=3,
            handle_recess_tool_diameter_mm=6,
            rear_groove_tool_diameter_mm=5,
        )
        uploaded_name = self._clone_plan(
            plan_name,
            status="Draft",
            source_type="Uploaded DXF",
            revision=21,
            liner_tool_diameter_mm=9,
            handle_recess_tool_diameter_mm=9,
            rear_groove_tool_diameter_mm=9,
        )
        frappe.db.set_value(
            "Door Cutting Order",
            order.name,
            "approved_plan",
            approved_name,
            update_modified=False,
        )
        order.reload()
        result = commands.save_system_plan_settings(
            order,
            dict(
                liner_tool_diameter_mm=4,
                handle_recess_tool_diameter_mm=8,
                rear_groove_tool_diameter_mm=3,
            ),
        )
        self.assertEqual(result["cutting_plan"], plan_name)
        self._assert_saved(order, plan_name, liner=4, handle=8, groove=3)
        approved = self._stored(approved_name)
        uploaded = self._stored(uploaded_name)
        self.assertEqual(approved.status, "Approved")
        self.assertEqual(flt(approved.liner_tool_diameter_mm), 3)
        self.assertEqual(flt(approved.handle_recess_tool_diameter_mm), 6)
        self.assertEqual(flt(approved.rear_groove_tool_diameter_mm), 5)
        self.assertEqual(uploaded.source_type, "Uploaded DXF")
        self.assertEqual(flt(uploaded.liner_tool_diameter_mm), 9)
        self.assertEqual(flt(uploaded.handle_recess_tool_diameter_mm), 9)
        self.assertEqual(flt(uploaded.rear_groove_tool_diameter_mm), 9)
        approved_view = self._workspace_settings(order, "approved")
        uploaded_view = self._workspace_settings(order, "uploaded_draft")
        self.assertEqual(flt(approved_view.get("liner_tool_diameter_mm")), 3)
        self.assertEqual(flt(uploaded_view.get("liner_tool_diameter_mm")), 9)

    def test_dxf_export_uses_the_diameters_reread_after_save(self):
        order, plan_name = self._seed()
        commands.save_system_plan_settings(
            order,
            dict(
                liner_tool_diameter_mm=4,
                handle_recess_tool_diameter_mm=8,
                rear_groove_tool_diameter_mm=3,
            ),
        )
        frappe.clear_document_cache("Cutting Plan", plan_name)
        plan = frappe.get_doc("Cutting Plan", plan_name)
        exported = _with_tool_diameters({"sheets": [], "kerf_mm": 99}, plan)
        self.assertEqual(exported["liner_tool_diameter_mm"], 4)
        self.assertEqual(exported["handle_recess_tool_diameter_mm"], 8)
        self.assertEqual(exported["rear_groove_tool_diameter_mm"], 3)
        self.assertEqual(exported["kerf_mm"], 3)
        resolved = diameters_for_record(plan)
        piece = LinerPiece("Regular", 40, 80)
        liner = generate_toolpath(
            kind="liner",
            piece=piece,
            reference_side="edge_width_top",
            offset_cm=0,
            width_cm=1.8,
            start_cm=0,
            length_cm=40,
            cutter_diameter_mm=resolved["liner"],
        )
        inherited = generate_toolpath(
            kind="liner",
            piece=piece,
            reference_side="edge_width_top",
            offset_cm=0,
            width_cm=1.8,
            start_cm=0,
            length_cm=40,
            cutter_diameter_mm=resolved["kerf_mm"],
        )
        self.assertEqual(min(point[0] for point in liner), -2)
        self.assertNotEqual(
            [round(point[0], 3) for point in liner],
            [round(point[0], 3) for point in inherited],
        )

    def test_factory_default_does_not_replace_a_saved_plan_diameter(self):
        order, plan_name = self._seed()
        frappe.db.set_single_value(
            "Almdina ERP Settings",
            "default_liner_tool_diameter_mm",
            99,
        )
        frappe.clear_document_cache("Almdina ERP Settings", "Almdina ERP Settings")
        commands.save_system_plan_settings(
            order,
            dict(handle_recess_tool_diameter_mm=8),
        )
        stored = self._stored(plan_name)
        self.assertEqual(flt(stored.liner_tool_diameter_mm), 3)
        self.assertEqual(flt(stored.handle_recess_tool_diameter_mm), 8)
        self.assertEqual(flt(frappe.db.get_value(
            "Almdina ERP Settings",
            "Almdina ERP Settings",
            "default_liner_tool_diameter_mm",
        )), 99)
