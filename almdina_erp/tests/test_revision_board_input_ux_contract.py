from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
REVISION_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_revision_ux.js"
)
LIFECYCLE_UX = (
    ROOT / "public" / "js" / "door_cutting_order" / "core" / "order_lifecycle.js"
)
REVISION_SERVICE = ROOT / "almdina_erp" / "services" / "order_revision_service.py"
BOARD_TEXT_UX = ROOT / "public" / "js" / "door_cutting_order_board_text_ux.js"
FAST_SAVE_UX = ROOT / "public" / "js" / "door_cutting_order_fast_save_ux.js"
TEXT_BOARD_PLAN_UX = ROOT / "public" / "js" / "door_cutting_order_text_board_plan_ux.js"
API_PATH = ROOT / "almdina_erp" / "api.py"
DOCTYPE_JSON = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.json"
)


class TestRevisionReasonUxContract(unittest.TestCase):
    def test_revision_dialog_forwards_an_optional_reason(self) -> None:
        source = REVISION_UX.read_text(encoding="utf-8")
        self.assertIn('fieldname: "reason"', source)
        self.assertIn("reqd: 0", source)
        self.assertIn("سبب إنشاء نسخة التعديل (اختياري)", source)
        self.assertIn("function createRevision(frm, reason = \"\")", source)
        self.assertIn(
            "almdina_erp.almdina_erp.services.order_revision_service.create_order_revision",
            source,
        )
        self.assertIn('reason: String(reason || "").trim()', source)
        self.assertNotIn("اكتب سبب إعادة الطلب للتعديل", source)

    def test_return_to_draft_dialog_keeps_reason_optional(self) -> None:
        source = LIFECYCLE_UX.read_text(encoding="utf-8")
        self.assertIn("سبب إعادة الطلب للمسودة (اختياري)", source)
        self.assertIn("reqd: 0", source)
        self.assertIn(
            "order_revision_service.return_order_to_draft",
            source,
        )
        self.assertIn('reason: String(values.reason || "").trim()', source)
        self.assertIn("إعادة نفس الطلب إلى المسودة", source)
        self.assertNotIn("routeToResult: true", source.split("function returnToDraft", 1)[1].split(
            "function cancelOrder", 1
        )[0])
        self.assertNotIn("إنشاء نسخة", source.split("function returnToDraft", 1)[1].split(
            "function cancelOrder", 1
        )[0])

    def test_server_accepts_missing_reason_as_the_final_safety_boundary(self) -> None:
        lifecycle = (
            ROOT / "almdina_erp" / "services" / "order_lifecycle_service.py"
        ).read_text(encoding="utf-8")
        return_fn = lifecycle.split("def return_order_to_draft", 1)[1]
        self.assertIn('reason = str(reason or "").strip()', return_fn)
        self.assertNotIn("A revision reason is required.", return_fn)
        # Missing reason is filled with a default audit message — never rejected.
        self.assertNotIn("if not reason:", return_fn)

    def test_retired_buttons_are_removed_by_the_final_lifecycle_owner(self) -> None:
        source = LIFECYCLE_UX.read_text(encoding="utf-8")
        self.assertIn("const RETIRED_LABELS = Object.freeze([", source)
        self.assertIn("function removeRetiredLifecycleButtons(frm)", source)
        self.assertIn("RETIRED_LABELS.forEach", source)
        self.assertIn("function removeLifecycleButtons(frm)", source)
        self.assertIn('__("إعادة للمسودة")', source)
        self.assertIn('__("Cancel Order")', source)
        self.assertIn("removeRetiredLifecycleButtons(frm)", source)
        self.assertNotIn('document.addEventListener("click"', source)
        self.assertNotIn("stopImmediatePropagation", source)

    def test_document_context_replaces_the_global_active_form_guard(self) -> None:
        source = LIFECYCLE_UX.read_text(encoding="utf-8")
        self.assertIn("documentContext().capture(frm)", source)
        self.assertIn("documentContext().isCurrent(frm, identity)", source)
        self.assertIn("context.order_name !== frm.doc.name", source)
        self.assertNotIn("currentOrderRevisionForm", source)


class TestBoardInputSyncContract(unittest.TestCase):
    def test_visible_board_controls_are_the_source_of_truth(self) -> None:
        source = BOARD_TEXT_UX.read_text(encoding="utf-8")
        self.assertIn("function controlValue", source)
        self.assertIn("field.$input.val()", source)
        self.assertIn("async function syncInputs", source)
        self.assertIn("await frm.set_value(updates)", source)
        self.assertIn("before_save(frm) { return syncInputs(frm); }", source)
        self.assertIn("syncInputs,", source)

    def test_plan_actions_flush_board_controls_before_validation(self) -> None:
        cases = (
            (FAST_SAVE_UX, "if (!boardUX || !boardUX.canCalculatePlan(frm))"),
            (TEXT_BOARD_PLAN_UX, "if (!validatePlanInputs(frm)"),
        )
        for path, validation_token in cases:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                sync_index = source.index("await boardUX.syncInputs(frm)")
                validation_index = source.index(validation_token)
                self.assertLess(sync_index, validation_index)

    def test_doctype_uses_free_text_board_field_not_hidden_stock_item(self) -> None:
        payload = json.loads(DOCTYPE_JSON.read_text(encoding="utf-8"))
        fields = {field["fieldname"]: field for field in payload["fields"]}

        self.assertEqual(fields["board_description"]["fieldtype"], "Data")
        self.assertEqual(fields["board_description"].get("reqd"), 1)
        self.assertEqual(fields["board_item"].get("hidden"), 1)
        self.assertFalse(fields["board_item"].get("reqd", 0))


class TestTextBoardLivePreviewRegression(unittest.TestCase):
    @staticmethod
    def _load_api(preview, stored):
        fake_frappe = types.ModuleType("frappe")
        fake_utils = types.ModuleType("frappe.utils")
        fake_utils.flt = lambda value=0: float(value or 0)
        fake_utils.cint = lambda value=0: int(float(value or 0))

        fake_frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
        fake_frappe.parse_json = json.loads
        fake_frappe.db = SimpleNamespace(
            exists=lambda *args, **kwargs: True,
            get_value=lambda *args, **kwargs: None,
        )

        def get_doc(*args, **kwargs):
            if len(args) == 1 and isinstance(args[0], dict):
                return preview
            return stored

        fake_frappe.get_doc = get_doc

        previous_frappe = sys.modules.get("frappe")
        previous_utils = sys.modules.get("frappe.utils")
        sys.modules["frappe"] = fake_frappe
        sys.modules["frappe.utils"] = fake_utils
        try:
            spec = importlib.util.spec_from_file_location(
                "_almdina_text_board_preview_regression",
                API_PATH,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load API module")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            if previous_frappe is None:
                sys.modules.pop("frappe", None)
            else:
                sys.modules["frappe"] = previous_frappe
            if previous_utils is None:
                sys.modules.pop("frappe.utils", None)
            else:
                sys.modules["frappe.utils"] = previous_utils

    def test_opening_an_existing_text_board_order_never_calls_item_loader(self) -> None:
        piece = SimpleNamespace(
            width_cm=60,
            length_cm=80,
            qty=1,
            piece_type="Regular",
            piece_no=0,
            area_m2=0,
            edge_meters=0,
            edge_rate_usd=0,
            edge_cost_usd=0,
            special_shape_status="Not Required",
            special_shape_estimated_unit_price_usd=0,
            special_shape_custom_unit_price_usd=0,
            special_shape_final_unit_price_usd=0,
            special_shape_price_status="Not Applicable",
            special_shape_price_note="",
            special_shape_price_approved_by="",
            special_shape_price_approved_on=None,
        )
        preview = SimpleNamespace(
            board_description="MDF أبيض 18 مم",
            board_item="",
            board_length_cm=244,
            board_width_cm=122,
            trim_margin_mm=5,
            pieces=[piece],
            packing_mode="Auto Pro",
            full_board_length_mm=0,
            full_board_width_mm=0,
            total_area_m2=0,
            total_edge_meters=0,
            required_boards=0,
            waste_area_m2=0,
            waste_percent=0,
            mdf_cost_usd=0,
            cutting_cost_usd=0,
            edge_cost_usd=0,
            total_cost_usd=0,
            special_shapes_baseline_cost_usd=0,
            special_shapes_estimated_total_usd=0,
            special_shapes_final_total_usd=0,
            customer_quote_total_usd=0,
            customer_quote_status="Automatic",
            packing_method="",
            packing_score="",
            engine_version="",
            cutting_plan_json="",
            system_plan_json="",
            custom_plan_json="",
            approved_plan_source="System",
            approved_plan=None,
        )
        stored = SimpleNamespace(check_permission=lambda permission: None)
        item_loader_called = False

        def forbidden_item_loader():
            nonlocal item_loader_called
            item_loader_called = True
            raise AssertionError("The hidden board_item loader must not run")

        def set_piece_numbers():
            piece.piece_no = 1

        def calculate_piece_rows():
            piece.area_m2 = 0.48
            preview.total_area_m2 = 0.48
            preview.total_edge_meters = 0
            preview.edge_cost_usd = 0

        def calculate_plan(settings, fingerprint):
            self.assertEqual(preview.board_item, preview.board_description)
            self.assertEqual(preview.full_board_length_mm, 2440)
            self.assertEqual(preview.full_board_width_mm, 1220)
            preview.required_boards = 1
            preview.total_cost_usd = 1
            preview.cutting_plan_json = '{"sheets":[{}]}'

        preview._load_board_snapshot = forbidden_item_loader
        preview._set_piece_numbers = set_piece_numbers
        preview._validate_special_shape_rows = lambda: None
        preview._calculate_piece_rows = calculate_piece_rows
        preview._get_settings = lambda: SimpleNamespace()
        preview._plan_input_fingerprint = lambda settings: "text-board-fingerprint"
        preview._calculate_cutting_plan = calculate_plan

        api = self._load_api(preview, stored)
        result = api.preview_door_cutting_order(
            {
                "doctype": "Door Cutting Order",
                "name": "DCO-2026-00001",
                "status": "Draft",
            }
        )

        self.assertFalse(item_loader_called)
        self.assertEqual(result["board_description"], "MDF أبيض 18 مم")
        self.assertEqual(result["full_board_length_mm"], 2440)
        self.assertEqual(result["full_board_width_mm"], 1220)
        self.assertEqual(result["required_boards"], 1)

    def test_preview_source_cannot_regress_to_hidden_item_validation(self) -> None:
        source = API_PATH.read_text(encoding="utf-8")
        self.assertIn("def _prepare_text_board_preview", source)
        self.assertIn("preview.board_item = description", source)
        self.assertNotIn("preview._load_board_snapshot()", source)
        self.assertNotIn('_("Board Item is required.")', source)


if __name__ == "__main__":
    unittest.main()
