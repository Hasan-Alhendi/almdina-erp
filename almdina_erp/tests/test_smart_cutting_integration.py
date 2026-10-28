"""Real Frappe persistence, permissions, exact preview and manufacturing checks."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import cutting_plan_capability_allowed
from almdina_erp.almdina_erp.infrastructure.frappe.projected_permission_matrix_repository import ProjectedPermissionMatrixRepository
from almdina_erp.almdina_erp.services import cutting_plan_command_service as commands
from almdina_erp.almdina_erp.services import cutting_plan_preview_service as previews
from almdina_erp.almdina_erp.services.cutting_plan_recalculation_job_service import _still_stale
from almdina_erp.tests.test_smart_cutting_manufacturing import CASES, rows_with_identity, import_saved_plan
from almdina_erp.tests.test_cutting_industrial_gaps import export_real_js


class TestSmartCuttingIntegration(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.orders = []
        self.users = []
        self.roles = []

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self.orders:
            for doctype in ("Cutting Plan Source", "Cutting Plan Piece"):
                for plan in frappe.get_all("Cutting Plan", filters={"door_cutting_order": name}, pluck="name"):
                    frappe.db.delete(doctype, {"parent": plan})
            frappe.db.delete("Cutting Plan", {"door_cutting_order": name})
            frappe.db.delete("Door Cutting Order Detail", {"parent": name})
            frappe.db.delete("Door Cutting Order", {"name": name})
        for role in self.roles:
            for doctype in ("Custom DocPerm", "DocPerm", "Almdina Role Capability State"):
                frappe.db.delete(doctype, {"role": role})
        for user in self.users:
            frappe.delete_doc("User", user, force=True, ignore_permissions=True)
        for role in self.roles:
            frappe.delete_doc("Role", role, force=True, ignore_permissions=True)
        frappe.clear_cache()
        super().tearDown()

    @staticmethod
    def _insert(doctype, values):
        now = now_datetime()
        values = dict(owner="Administrator", creation=now, modified=now,
                      modified_by="Administrator", docstatus=0, idx=0) | values
        columns = ", ".join(f"`{field}`" for field in values)
        params = ", ".join(["%s"] * len(values))
        frappe.db.sql(f"INSERT INTO `tab{doctype}` ({columns}) VALUES ({params})", tuple(values.values()))

    def _order(self, width=100, height=100, trim=0, rows=None):
        rows = rows_with_identity(rows or [dict(width_cm=40, length_cm=30, qty=2)])
        name = "TEST-SMART-" + frappe.generate_hash(length=12)
        self.orders.append(name)
        self._insert("Door Cutting Order", dict(name=name, status="Draft", revision=1,
            revision_state="Current", board_description="Smart test", allow_piece_mirroring=1,
            board_width_cm=width, board_length_cm=height,
            full_board_width_mm=width*10, full_board_length_mm=height*10))
        for i, row in enumerate(rows,1):
            self._insert("Door Cutting Order Detail", dict(row, name=f"{name}-{i}", parent=name,
                parenttype="Door Cutting Order", parentfield="pieces", idx=i, piece_no=i,
                piece_instance_id=f"smart:{i}", cut_width_cm=row["width_cm"], cut_length_cm=row["length_cm"]))
        order = frappe.get_doc("Door Cutting Order", name)
        commands.save_system_plan_settings(order, dict(packing_mode="Auto", cutting_machine_type="CNC Router",
            kerf_mm=3, trim_margin_mm=trim*10, optimization_time_limit_sec=.4))
        return order, rows

    def _plan(self, order):
        name = frappe.get_all("Cutting Plan", filters={"door_cutting_order": order.name,
            "source_type": "System", "status": "Draft"}, pluck="name")[0]
        return frappe.get_doc("Cutting Plan", name)

    def test_generate_save_reload_export_strict_import(self):
        for width, height, trim, rows in CASES:
            with self.subTest(width=width, height=height, kind=rows[0].get("piece_type")):
                order, rows = self._order(width, height, trim, rows)
                commands.recalculate_order_plan(order.name)
                plan = self._plan(order)
                snapshot = json.loads(plan.snapshot_json)
                self.assertEqual(plan.optimization_mode, "smart")
                self.assertEqual(plan.validation_status, "Valid")
                self.assertFalse(_still_stale(order))
                with TemporaryDirectory() as directory:
                    imported = import_saved_plan(snapshot, rows, export_real_js(snapshot, Path(directory)))
                self.assertEqual(sum(len(s["pieces"]) for s in imported["sheets"]), sum(r["qty"] for r in rows))

    def test_preview_keeps_database_unchanged_then_commits_exactly(self):
        order, _ = self._order()
        commands.recalculate_order_plan(order.name)
        plan = self._plan(order)
        before = plan.snapshot_json
        preview = previews.preview_cutting_plan(order.name, packing_mode="Auto Pro",
            cutting_machine_type="CNC Router", kerf_mm=3, trim_margin_mm=0, optimization_time_limit_sec=.4)
        self.assertEqual(self._plan(order).snapshot_json, before)
        self.assertEqual(preview["summary"]["settings"]["packing_mode"], "smart")
        with patch.object(previews, "calculate_system_plan", side_effect=AssertionError("optimizer during commit")):
            result = previews.commit_cutting_plan_preview(order.name, preview["preview_id"], preview["candidate_id"])
        self.assertTrue(result["exact_preview_commit"])
        self.assertEqual(json.loads(self._plan(order).snapshot_json), preview["plan"])

    def _preview(self, order):
        return previews.preview_cutting_plan(order.name,packing_mode="smart",cutting_machine_type="CNC Router",
            kerf_mm=3,trim_margin_mm=0,optimization_time_limit_sec=.6)

    def test_portfolio_selection_is_read_only_and_selected_cost_snapshot_is_exact(self):
        rows=[dict(width_cm=w,length_cm=h,qty=1,allow_rotation=1) for w,h in [(40,30),(30,20),(50,15),(18,45),(25,25)]]
        order,rows=self._order(rows=rows)
        commands.recalculate_order_plan(order.name)
        plan=self._plan(order)
        frappe.db.set_value('Cutting Plan',plan.name,dict(board_rate_usd=10,cutting_cost_per_board_usd=2))
        before=self._plan(order).snapshot_json
        preview=self._preview(order)
        self.assertGreaterEqual(len(preview['candidates']),2)
        self.assertLessEqual(len(preview['candidates']),5)
        self.assertTrue(all('snapshot' not in c for c in preview['candidates']))
        with patch.object(previews,'calculate_system_plan',side_effect=AssertionError('optimizer during selection or save')):
            for candidate in preview['candidates']:
                selected=previews.select_cutting_plan_candidate(order.name,preview['preview_id'],candidate['candidate_id'])
                self.assertEqual(self._plan(order).snapshot_json,before)
                with TemporaryDirectory() as directory:
                    imported=import_saved_plan(selected['plan'],rows,export_real_js(selected['plan'],Path(directory)))
                self.assertEqual(sum(len(sh['pieces']) for sh in imported['sheets']),len(rows))
            chosen=preview['candidates'][-1]['candidate_id']
            selected=previews.select_cutting_plan_candidate(order.name,preview['preview_id'],chosen)
            result=previews.commit_cutting_plan_preview(order.name,preview['preview_id'],chosen)
        saved=self._plan(order)
        self.assertEqual(result['committed_candidate_id'],chosen)
        self.assertEqual(json.loads(saved.snapshot_json),selected['plan'])
        self.assertEqual(saved.mdf_cost_usd,saved.required_boards*10)
        self.assertEqual(saved.cutting_cost_usd,saved.required_boards*2)
        with self.assertRaises(frappe.ValidationError):
            previews.commit_cutting_plan_preview(order.name,preview['preview_id'],chosen)

    def test_cancel_expiry_wrong_candidate_and_concurrent_edit_never_save(self):
        from dataclasses import replace
        from datetime import timedelta
        from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_preview_store import FrappeCuttingPlanPreviewStore
        order,_=self._order()
        commands.recalculate_order_plan(order.name)
        before=self._plan(order).snapshot_json
        preview=self._preview(order)
        with self.assertRaises(frappe.ValidationError):
            previews.commit_cutting_plan_preview(order.name,preview['preview_id'],'forged')
        self.assertIsNotNone(FrappeCuttingPlanPreviewStore().get(preview['preview_id']))
        previews.discard_cutting_plan_preview(order.name,preview['preview_id'])
        with self.assertRaises(frappe.ValidationError):
            previews.select_cutting_plan_candidate(order.name,preview['preview_id'],preview['candidate_id'])
        expired=self._preview(order)
        store=FrappeCuttingPlanPreviewStore()
        session=store.get(expired['preview_id'])
        store.put(replace(session,expires_at=str(now_datetime()-timedelta(seconds=1))))
        with self.assertRaises(frappe.ValidationError):
            previews.commit_cutting_plan_preview(order.name,expired['preview_id'],expired['candidate_id'])
        concurrent=self._preview(order)
        frappe.db.set_value('Cutting Plan',self._plan(order).name,'optimization_time_limit_sec',.7)
        with self.assertRaises(frappe.ValidationError):
            previews.commit_cutting_plan_preview(order.name,concurrent['preview_id'],concurrent['candidate_id'])
        self.assertEqual(self._plan(order).snapshot_json,before)

    def test_first_plan_is_only_created_when_selected_preview_is_saved(self):
        order,_=self._order()
        name=self._plan(order).name
        frappe.db.delete('Cutting Plan',{'name':name})
        preview=self._preview(order)
        self.assertTrue(preview['is_first_system'])
        self.assertFalse(frappe.db.exists('Cutting Plan',{'door_cutting_order':order.name}))
        previews.discard_cutting_plan_preview(order.name,preview['preview_id'])
        self.assertFalse(frappe.db.exists('Cutting Plan',{'door_cutting_order':order.name}))
        preview=self._preview(order)
        with patch.object(previews,'calculate_system_plan',side_effect=AssertionError('first save reran optimizer')):
            receipt=previews.commit_cutting_plan_preview(order.name,preview['preview_id'],preview['candidate_id'])
        self.assertEqual(receipt['committed_candidate_id'],preview['candidate_id'])
        self.assertEqual(json.loads(self._plan(order).snapshot_json),preview['plan'])

    def test_continuation_retains_the_best_and_invalidates_previous_token(self):
        order,_=self._order(rows=[dict(width_cm=40,length_cm=30,qty=2,allow_rotation=1)])
        first=self._preview(order)
        second=previews.continue_cutting_plan_search(order.name,first['preview_id'])
        self.assertLessEqual(tuple(second['plan']['industrial_rank']),tuple(first['plan']['industrial_rank']))
        self.assertEqual(second['search_round'],1)
        with self.assertRaises(frappe.ValidationError):
            previews.commit_cutting_plan_preview(order.name,first['preview_id'],first['candidate_id'])
        third=previews.continue_cutting_plan_search(order.name,second['preview_id'])
        self.assertFalse(third['can_continue'])
        with self.assertRaises(frappe.ValidationError):
            previews.continue_cutting_plan_search(order.name,third['preview_id'])

    def test_candidate_scope_fingerprint_and_stage_guards(self):
        from dataclasses import replace
        from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_preview_store import FrappeCuttingPlanPreviewStore
        order,_=self._order()
        other,_=self._order()
        preview=self._preview(order)
        store=FrappeCuttingPlanPreviewStore()
        session=store.get(preview['preview_id'])
        with self.assertRaises(frappe.PermissionError):
            previews.select_cutting_plan_candidate(other.name,preview['preview_id'],preview['candidate_id'])
        store.put(replace(session,user='someone-else@example.test'))
        with self.assertRaises(frappe.PermissionError):
            previews.commit_cutting_plan_preview(order.name,preview['preview_id'],preview['candidate_id'])
        store.put(replace(session,settings_fingerprint='tampered'))
        with self.assertRaises(frappe.ValidationError):
            previews.commit_cutting_plan_preview(order.name,preview['preview_id'],preview['candidate_id'])
        store.put(session)
        frappe.db.set_value('Door Cutting Order Detail',order.pieces[0].name,'cut_width_cm',39)
        with self.assertRaises(frappe.ValidationError):
            previews.select_cutting_plan_candidate(order.name,preview['preview_id'],preview['candidate_id'])
        # Lifecycle gate must run before a cached candidate is returned or saved.
        with patch.object(previews,'assert_plan_settings_edit_lifecycle',side_effect=frappe.PermissionError('stage locked')):
            for action,args in [(previews.select_cutting_plan_candidate,(preview['candidate_id'],)),
                                (previews.commit_cutting_plan_preview,(preview['candidate_id'],)),
                                (previews.continue_cutting_plan_search,()),
                                (previews.discard_cutting_plan_preview,())]:
                with self.assertRaises(frappe.PermissionError):
                    action(order.name,preview['preview_id'],*args)

    def test_recalculate_without_settings_edit_and_reject_physical_changes(self):
        order, _ = self._order()
        token = frappe.generate_hash(length=12)
        role, email = f"Smart-Recalc-{token}", f"smart-{token}@example.test"
        frappe.get_doc(dict(doctype="Role", role_name=role, desk_access=1)).insert()
        self.roles.append(role)
        frappe.get_doc(dict(doctype="User", email=email, first_name="Smart test", enabled=1,
            send_welcome_email=0, user_type="System User", roles=[dict(role=role)])).insert()
        self.users.append(email)
        ProjectedPermissionMatrixRepository().save_role_state(role, {
            Capability.VIEW_ORDERS: True, Capability.VIEW_ALL_ORDERS: True,
            Capability.VIEW_SYSTEM_CUTTING_PLAN: True, Capability.RECALCULATE_PLAN: True,
            Capability.EDIT_OPTIMIZER_SETTINGS: False,
        })
        frappe.clear_cache()
        frappe.local.almdina_matrix_capabilities = {}
        frappe.set_user(email)
        self.assertFalse(cutting_plan_capability_allowed(order, Capability.EDIT_OPTIMIZER_SETTINGS))
        result = commands.recalculate_order_plan(order.name, packing_mode="smart")
        self.assertEqual(result["packing_mode"], "smart")
        preview = previews.preview_cutting_plan(order.name,packing_mode='smart',cutting_machine_type='CNC Router',
            kerf_mm=3,trim_margin_mm=0,optimization_time_limit_sec=.4)
        self.assertNotIn('cost',preview['summary'])
        selected = previews.select_cutting_plan_candidate(order.name,preview['preview_id'],preview['candidate_id'])
        self.assertNotIn('cost',selected['summary'])
        previews.commit_cutting_plan_preview(order.name,preview['preview_id'],preview['candidate_id'])
        with self.assertRaises(frappe.PermissionError):
            previews.preview_cutting_plan(order.name,packing_mode='smart',cutting_machine_type='CNC Router',
                kerf_mm=0,trim_margin_mm=0,optimization_time_limit_sec=.4)
        with self.assertRaises(frappe.PermissionError):
            commands.recalculate_order_plan(order.name, kerf_mm=0)
