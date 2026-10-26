"""Phase 1: board mirroring policy is stored and bound, without moving pieces."""

from __future__ import annotations

import copy
import csv
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
    BoardGeometry,
    OptimizeOrderPlanCommand,
    OptimizerOptions,
    optimize_order_plan,
)
from almdina_erp.almdina_erp.domain.cutting.plan_fingerprint_contract import (
    validate_v4_baseline,
)
from almdina_erp.almdina_erp.domain.cutting.plan_freshness import (
    decide_approved_plan_freshness,
    decide_draft_plan_freshness,
)
from almdina_erp.almdina_erp.domain.orders.piece_mirroring import (
    ALLOWED,
    NOT_ALLOWED,
    PieceMirroringPolicyError,
    normalize_allow_piece_mirroring,
    piece_mirroring_allowed,
)
from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import (
    domain_cutting_engine,
)
from almdina_erp.almdina_erp.infrastructure.frappe import (
    cutting_plan_workspace as workspace,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders.board_input_adapter import (
    FrappeOrderBoardInputAdapter,
)
from almdina_erp.tests.test_plan_fingerprint_compatibility import golden_case


ROOT = Path(__file__).resolve().parents[1]
CUTTING = ROOT / "almdina_erp" / "domain" / "cutting"


class _BoardAccess:
    def board_dimensions(self) -> tuple[float, float]:
        return (280.0, 207.0)


def _order(**overrides):
    document = SimpleNamespace(
        board_description="MDF white 18 mm",
        board_length_cm=280,
        board_width_cm=207,
        allow_piece_mirroring=None,
    )
    for key, value in overrides.items():
        setattr(document, key, value)
    return document


class TestPieceMirroringPolicy(unittest.TestCase):
    def test_missing_and_blank_values_mean_mirroring_is_not_allowed(self) -> None:
        for value in (None, "", "   ", 0, False, "0", "false", "not_allowed"):
            with self.subTest(value=value):
                self.assertEqual(0, normalize_allow_piece_mirroring(value))
                self.assertFalse(piece_mirroring_allowed(value))

    def test_checkbox_toggles_between_zero_and_one(self) -> None:
        for value in (1, True, "1", "true", "allowed", "  Allowed  "):
            with self.subTest(value=value):
                self.assertEqual(1, normalize_allow_piece_mirroring(value))
                self.assertTrue(piece_mirroring_allowed(value))
        for value in ("yes", "no", 2, "نعم", "sideways"):
            with self.subTest(value=value):
                with self.assertRaises(PieceMirroringPolicyError):
                    normalize_allow_piece_mirroring(value)

    def test_save_keeps_the_choice_and_reopens_it(self) -> None:
        legacy = _order()
        del legacy.allow_piece_mirroring
        FrappeOrderBoardInputAdapter(legacy, _BoardAccess()).load_snapshot()
        self.assertEqual(0, legacy.allow_piece_mirroring)

        chosen = _order(allow_piece_mirroring=0)
        adapter = FrappeOrderBoardInputAdapter(chosen, _BoardAccess())
        adapter.load_snapshot()
        self.assertEqual(0, chosen.allow_piece_mirroring)

        chosen.allow_piece_mirroring = 1
        adapter.load_snapshot()
        self.assertEqual(1, chosen.allow_piece_mirroring)
        adapter.load_snapshot()
        self.assertEqual(1, chosen.allow_piece_mirroring)

        chosen.allow_piece_mirroring = True
        adapter.load_snapshot()
        self.assertEqual(1, chosen.allow_piece_mirroring)

        chosen.allow_piece_mirroring = "allowed"
        adapter.load_snapshot()
        self.assertEqual(1, chosen.allow_piece_mirroring)

        chosen.allow_piece_mirroring = 0
        adapter.load_snapshot()
        self.assertEqual(0, chosen.allow_piece_mirroring)

        invalid = _order(allow_piece_mirroring="yes")
        with self.assertRaises(ValueError):
            FrappeOrderBoardInputAdapter(invalid, _BoardAccess()).load_snapshot()

    def test_doctype_is_one_unchecked_checkbox(self) -> None:
        payload = json.loads(
            (ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json").read_text()
        )
        fields = {field["fieldname"]: field for field in payload["fields"]}
        field = fields["allow_piece_mirroring"]
        self.assertEqual("Check", field["fieldtype"])
        self.assertEqual("0", str(field["default"]))
        self.assertNotIn("options", field)
        self.assertEqual("Mirrorable", field["label"])
        self.assertNotIn("reqd", field)
        self.assertEqual(
            "allow_piece_mirroring",
            payload["field_order"][payload["field_order"].index("edge_color") + 1],
        )
        self.assertEqual(
            1,
            sum(1 for item in payload["fields"] if item.get("fieldname") == "allow_piece_mirroring"),
        )

    def test_visible_copy_is_yes_no_pills(self) -> None:
        with (ROOT / "translations" / "ar.csv").open(encoding="utf-8", newline="") as handle:
            catalog = {row[0]: row[1] for row in csv.reader(handle) if len(row) >= 2}
        self.assertEqual("قابل للانعكاس", catalog["Mirrorable"])
        self.assertEqual("نعم", catalog["Yes"])
        self.assertEqual("لا", catalog["No"])
        self.assertEqual(
            "إذن عكس الدرفات غير صالح.",
            catalog["Piece mirroring permission is invalid."],
        )
        css = (ROOT / "public" / "css" / "door_cutting_order_form_tab_layout.css").read_text(encoding="utf-8")
        self.assertIn("dco-piece-mirroring-option", css)
        self.assertIn("border-radius: 999px", css)
        self.assertNotIn("allow_piece_mirroring\"] select", css)
        source = (
            ROOT / "public" / "js" / "door_cutting_order" / "order_entry"
            / "door_cutting_order_piece_mirroring_ux.js"
        ).read_text(encoding="utf-8")
        self.assertIn('input.type = "radio"', source)
        self.assertIn('value: "1"', source)
        self.assertIn('value: "0"', source)
        self.assertIn('label: "Yes"', source)
        self.assertIn('label: "No"', source)
        self.assertIn("set_value(FIELDNAME, next)", source)
        self.assertNotIn("<select", source)
        defaults = (
            ROOT / "public" / "js" / "door_cutting_order" / "order_entry" / "door_cutting_order_defaults.js"
        ).read_text(encoding="utf-8")
        self.assertIn('allow_piece_mirroring: "Mirrorable"', defaults)


class TestPieceMirroringPlanBinding(unittest.TestCase):
    def test_historical_baseline_ignores_the_default_and_binds_an_allowed_change(self) -> None:
        _, order, plan = golden_case()
        historical = workspace.plan_input_fingerprint(order, plan, version=4)
        self.assertNotIn("allow_piece_mirroring", workspace.manufacturing_baseline_v4(order, plan)["board"])

        order.allow_piece_mirroring = NOT_ALLOWED
        self.assertEqual(historical, workspace.plan_input_fingerprint(order, plan, version=4))
        fresh = decide_approved_plan_freshness(
            status="Approved",
            stored_fingerprint=historical,
            expected_fingerprint=workspace.plan_input_fingerprint(order, plan, version=4),
        )
        self.assertFalse(fresh.should_invalidate)

        order.allow_piece_mirroring = ALLOWED
        allowed_baseline = workspace.manufacturing_baseline_v4(order, plan)
        self.assertIs(True, allowed_baseline["board"]["allow_piece_mirroring"])
        validate_v4_baseline(allowed_baseline)
        allowed = workspace.plan_input_fingerprint(order, plan, version=4)
        self.assertNotEqual(historical, allowed)
        self.assertTrue(decide_approved_plan_freshness(
            status="Approved",
            stored_fingerprint=historical,
            expected_fingerprint=allowed,
        ).should_invalidate)
        self.assertTrue(decide_draft_plan_freshness(
            status="Draft",
            stored_fingerprint=historical,
            expected_fingerprint=allowed,
            already_needs_recalculation=False,
        ).should_invalidate)

        order.allow_piece_mirroring = "sideways"
        with self.assertRaises(PieceMirroringPolicyError):
            workspace.manufacturing_baseline_v4(order, plan)

    def test_false_or_unknown_board_key_is_not_a_historical_baseline(self) -> None:
        _, order, plan = golden_case()
        baseline = workspace.manufacturing_baseline_v4(order, plan)
        denied = copy.deepcopy(baseline)
        denied["board"]["allow_piece_mirroring"] = False
        with self.assertRaises(Exception):
            validate_v4_baseline(denied)
        extra = copy.deepcopy(baseline)
        extra["board"]["grain_direction"] = "horizontal"
        with self.assertRaises(Exception):
            validate_v4_baseline(extra)

    def test_enabling_mirroring_cancels_approval_through_the_existing_rule(self) -> None:
        import frappe
        from almdina_erp.almdina_erp.domain.orders.plan_fingerprint import fingerprint_payload
        from almdina_erp.almdina_erp.services import cutting_plan_invalidation_service as service

        _, order, plan = golden_case()
        sheets = [{"pieces": []}]
        baseline = workspace.manufacturing_baseline_v4(order, plan)
        plan.input_fingerprint = fingerprint_payload(baseline)
        plan.snapshot_json = json.dumps({
            "input_fingerprint_contract": 4,
            "manufacturing_baseline": baseline,
            "sheets": sheets,
            "validation": {"is_valid": True},
            "saved_layout_sha256": fingerprint_payload({"sheets": sheets}),
        })
        plan.status = "Approved"
        order.approved_plan = plan.name
        previous = copy.deepcopy(order)
        order.allow_piece_mirroring = NOT_ALLOWED
        order.get_doc_before_save = lambda: previous
        with patch.object(frappe, "get_doc", return_value=plan, create=True), \
             patch.object(frappe.db, "exists", return_value=True, create=True), \
             patch.object(frappe.db, "set_value", side_effect=AssertionError("default policy cancelled approval"), create=True):
            self.assertIsNone(service.apply_stale_approved_plan_cancellation(order))
        self.assertEqual(plan.name, order.approved_plan)

        order.allow_piece_mirroring = ALLOWED
        writes = []
        with patch.object(frappe, "get_doc", return_value=plan, create=True), \
             patch.object(frappe.db, "exists", return_value=True, create=True), \
             patch.object(frappe.db, "set_value", side_effect=lambda *args, **kwargs: writes.append(args), create=True), \
             patch.object(frappe, "clear_document_cache", create=True), \
             patch.object(service, "_sync_drawing_dxf_status"):
            self.assertEqual(plan.name, service.apply_stale_approved_plan_cancellation(order))
        self.assertIsNone(order.approved_plan)
        self.assertTrue(any(len(call) >= 4 and call[2] == "status" for call in writes))


class _RecordingEngine:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def expand_pieces(self, rows):
        return domain_cutting_engine.expand_pieces(rows)

    def optimize(self, *args, **kwargs):
        self.calls.append(dict(kwargs))
        return domain_cutting_engine.optimize(*args, **kwargs)

    def validate(self, *args, **kwargs):
        return domain_cutting_engine.validate(*args, **kwargs)


class TestPieceMirroringDoesNotChangeCutting(unittest.TestCase):
    def test_flag_reaches_the_snapshot_without_changing_the_engine_or_layout(self) -> None:
        def command(allowed: bool) -> OptimizeOrderPlanCommand:
            return OptimizeOrderPlanCommand(
                engine_version="phase-1-mirroring",
                input_fingerprint="same-geometry",
                board=BoardGeometry(
                    full_width_cm=122,
                    full_length_cm=244,
                    trim_cm=0.5,
                    kerf_cm=0.3,
                ),
                optimizer=OptimizerOptions(
                    selected_mode="maxrects",
                    machine_type="Panel Saw",
                    time_limit_sec=2,
                    exact_piece_limit=40,
                    min_remnant_width_cm=0,
                    min_remnant_length_cm=0,
                    min_remnant_area_m2=0,
                ),
                piece_rows=(
                    {"id": 1, "width_cm": 40, "length_cm": 80, "qty": 1, "allow_rotation": 0, "piece_type": "Regular"},
                    {"id": 2, "width_cm": 30, "length_cm": 50, "qty": 1, "allow_rotation": 1, "piece_type": "Regular"},
                ),
                allow_piece_mirroring=allowed,
            )

        blocked_engine = _RecordingEngine()
        allowed_engine = _RecordingEngine()
        blocked = optimize_order_plan(command(False), engine=blocked_engine)
        allowed = optimize_order_plan(command(True), engine=allowed_engine)

        self.assertEqual(blocked.snapshot["sheets"], allowed.snapshot["sheets"])
        self.assertEqual(blocked.snapshot["method_key"], allowed.snapshot["method_key"])
        self.assertEqual(blocked.snapshot["kerf_cm"], allowed.snapshot["kerf_cm"])
        self.assertEqual(blocked.snapshot["trim_cm"], allowed.snapshot["trim_cm"])
        self.assertEqual(blocked.required_boards, allowed.required_boards)
        self.assertFalse(blocked.snapshot["allow_piece_mirroring"])
        self.assertTrue(allowed.snapshot["allow_piece_mirroring"])
        self.assertTrue(blocked.snapshot["validation"]["is_valid"])
        self.assertTrue(allowed.snapshot["validation"]["is_valid"])
        def _without_mirroring(call: dict) -> dict:
            item = dict(call)
            item.pop("mirroring_allowed", None)
            return item

        for engine in (blocked_engine, allowed_engine):
            self.assertTrue(engine.calls)
            for call in engine.calls:
                self.assertNotIn("allow_piece_mirroring", call)
        self.assertEqual(
            [_without_mirroring(call) for call in blocked_engine.calls],
            [_without_mirroring(call) for call in allowed_engine.calls],
        )
        self.assertTrue(all(call.get("mirroring_allowed") is False for call in blocked_engine.calls))
        self.assertTrue(all(call.get("mirroring_allowed") is True for call in allowed_engine.calls))

        offenders = [
            str(path.relative_to(CUTTING))
            for path in CUTTING.rglob("*.py")
            if path.name != "plan_fingerprint_contract.py"
            and "allow_piece_mirroring" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])
