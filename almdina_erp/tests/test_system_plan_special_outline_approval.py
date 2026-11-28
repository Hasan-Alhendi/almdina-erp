"""System plan approval rejects rectangular Special doors without openings."""

from __future__ import annotations

import json
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import is_rectangle
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    serialize_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import SPECIAL_OUTLINE_IS_RECTANGLE
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry
from almdina_erp.almdina_erp.domain.cutting.system_plan_special_outline import (
    collect_system_plan_special_outline_issues,
    special_outline_blocks_system_plan_approval,
)
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import (
    present_issue,
    render_error_cards_html,
)
from almdina_erp.almdina_erp.services import cutting_plan_command_service as command_service


def _rect(x1, y1, x2, y2):
    return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))


def _circle(cx, cy, radius, count=16):
    return tuple(
        (
            cx + radius * math.cos(2 * math.pi * index / count),
            cy + radius * math.sin(2 * math.pi * index / count),
        )
        for index in range(count)
    )


def _rotate(points, degrees):
    angle = math.radians(degrees)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    cx = sum(point[0] for point in points) / len(points)
    cy = sum(point[1] for point in points) / len(points)
    rotated = []
    for x, y in points:
        dx, dy = x - cx, y - cy
        rotated.append((cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a))
    return tuple(rotated)


def _special_json(points, *, width=40.0, height=60.0):
    return json.dumps(
        {
            "version": 1,
            "kind": "polygon",
            "units": "cm",
            "exact": True,
            "blank_width_cm": width,
            "blank_length_cm": height,
            "points": [list(point) for point in points],
        }
    )


def _piece(
    *,
    source_piece_no=1,
    copy_no=1,
    label="1.1",
    piece_type="Special",
    special_json="",
    geometry=None,
    liner=False,
    w=40.0,
    h=60.0,
    x=0.0,
    y=0.0,
):
    piece = {
        "source_piece_no": source_piece_no,
        "copy_no": copy_no,
        "label": label,
        "piece_type": piece_type,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
        "original_w": w,
        "original_h": h,
        "original_width_cm": w,
        "original_length_cm": h,
        "special_shape_geometry_json": special_json or "",
        "rotated": False,
    }
    if geometry is not None:
        piece["geometry"] = geometry
    if liner:
        piece["extra_liner"] = 1
        piece["liner_specs_json"] = json.dumps(
            [{"side": "edge_width_top", "offset_cm": 0, "width_cm": 0.5}]
        )
        piece["overlays"] = [{"kind": "liner", "path_mm": [[10, 10], [30, 10]]}]
    return piece


def _snapshot(sheets):
    return {"sheets": sheets, "unplaced": []}


class SystemPlanSpecialOutlineApprovalTest(unittest.TestCase):
    def test_plan_without_specials_passes(self):
        snapshot = _snapshot(
            [
                {
                    "sheet_no": 1,
                    "pieces": [
                        _piece(piece_type="Regular", special_json=""),
                        _piece(
                            source_piece_no=2,
                            label="2.1",
                            piece_type="Glass",
                            special_json="",
                        ),
                    ],
                }
            ]
        )
        self.assertEqual(collect_system_plan_special_outline_issues(snapshot), [])

    def test_rectangular_special_without_openings_is_rejected(self):
        piece = _piece(
            special_json=_special_json(((0, 0), (40, 0), (40, 60), (0, 60))),
        )
        self.assertTrue(special_outline_blocks_system_plan_approval(piece))
        issues = collect_system_plan_special_outline_issues(
            _snapshot([{"sheet_no": 1, "pieces": [piece]}])
        )
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, SPECIAL_OUTLINE_IS_RECTANGLE)
        self.assertEqual(issues[0].target.sheet_no, 1)
        self.assertEqual(issues[0].target.source_piece_no, 1)

    def test_cnc_raw_special_without_geometry_is_rejected(self):
        piece = _piece(special_json="")
        self.assertTrue(special_outline_blocks_system_plan_approval(piece))

    def test_rectangular_special_with_valid_internal_opening_passes(self):
        geometry = serialize_geometry_mm(
            PartGeometry(
                outer=_rect(0, 0, 400, 600),
                holes=(_rect(80, 80, 320, 520),),
            )
        )
        piece = _piece(geometry=geometry)
        self.assertFalse(special_outline_blocks_system_plan_approval(piece))
        self.assertEqual(
            collect_system_plan_special_outline_issues(
                _snapshot([{"sheet_no": 2, "pieces": [piece]}])
            ),
            [],
        )

    def test_non_rectangular_special_passes(self):
        piece = _piece(
            special_json=_special_json(
                ((0, 0), (40, 0), (40, 60), (10, 60), (0, 40))
            ),
        )
        self.assertFalse(special_outline_blocks_system_plan_approval(piece))

    def test_curved_special_outline_passes(self):
        geometry = serialize_geometry_mm(
            PartGeometry(outer=_circle(200, 300, 150), holes=())
        )
        piece = _piece(geometry=geometry)
        self.assertFalse(special_outline_blocks_system_plan_approval(piece))

    def test_rotated_rectangle_still_blocks_without_openings(self):
        rotated = _rotate(_rect(0, 0, 400, 600), 35)
        self.assertTrue(is_rectangle(rotated, 0.25))
        geometry = serialize_geometry_mm(PartGeometry(outer=rotated, holes=()))
        piece = _piece(geometry=geometry)
        self.assertTrue(special_outline_blocks_system_plan_approval(piece))

    def test_liner_only_does_not_count_as_internal_opening(self):
        piece = _piece(
            special_json=_special_json(((0, 0), (40, 0), (40, 60), (0, 60))),
            liner=True,
        )
        self.assertTrue(special_outline_blocks_system_plan_approval(piece))

    def test_multiple_violations_across_boards_are_collected(self):
        first = _piece(source_piece_no=3, label="3.1", special_json="")
        second = _piece(
            source_piece_no=7,
            label="7.1",
            special_json=_special_json(((0, 0), (40, 0), (40, 60), (0, 60))),
        )
        third = _piece(
            source_piece_no=9,
            label="9.1",
            special_json=_special_json(((0, 0), (40, 0), (40, 60), (10, 60), (0, 40))),
        )
        issues = collect_system_plan_special_outline_issues(
            _snapshot(
                [
                    {"sheet_no": 2, "pieces": [second, third]},
                    {"sheet_no": 1, "pieces": [first]},
                ]
            )
        )
        self.assertEqual(
            [(item.target.sheet_no, item.target.source_piece_no) for item in issues],
            [(1, 3), (2, 7)],
        )
        html = render_error_cards_html(issues, context="save")
        presented = [present_issue(item) for item in issues]
        self.assertTrue(any("3" in item.target for item in presented))
        self.assertTrue(any("7" in item.target for item in presented))
        self.assertIn("1", html)
        self.assertIn("2", html)

    def test_system_plan_message_names_board_and_reason(self):
        piece = _piece(source_piece_no=4, label="4.1", special_json="")
        issues = collect_system_plan_special_outline_issues(
            _snapshot([{"sheet_no": 5, "pieces": [piece]}])
        )
        presented = present_issue(issues[0])
        self.assertIn("5", presented.target)
        self.assertIn("4", presented.target)
        self.assertIn("rectangular", presented.problem.lower())
        self.assertIn("opening", presented.action.lower())

    def test_uploaded_and_board_editor_approval_skip_this_gate(self):
        snapshot = _snapshot(
            [{"sheet_no": 1, "pieces": [_piece(special_json="")]}]
        )
        for source in ("Uploaded DXF", "Board Editor"):
            plan = SimpleNamespace(
                source_type=source,
                snapshot_json=json.dumps(snapshot),
            )
            # Must not throw for non-System sources.
            command_service._assert_system_plan_special_outline_approval(plan)

    def test_api_approval_rejects_before_status_change(self):
        snapshot = _snapshot(
            [{"sheet_no": 1, "pieces": [_piece(source_piece_no=2, special_json="")]}]
        )
        plan = SimpleNamespace(
            name="PLAN-DRAFT",
            source_type="System",
            snapshot_json=json.dumps(snapshot),
            status="Draft",
        )
        order = SimpleNamespace(name="ORD-1", approved_plan="PLAN-OLD")
        threw = []

        def _throw(message, *args, **kwargs):
            threw.append({"message": str(message), "kwargs": kwargs})
            raise RuntimeError("blocked")

        with patch.object(command_service.frappe, "throw", side_effect=_throw):
            with patch.object(
                command_service.frappe,
                "parse_json",
                side_effect=lambda value: json.loads(value or "{}"),
            ):
                with self.assertRaises(RuntimeError):
                    command_service._assert_system_plan_special_outline_approval(plan)
        self.assertEqual(len(threw), 1)
        message = threw[0]["message"]
        self.assertIn("rectangular", message.lower())
        self.assertIn("Board 1", message)
        self.assertIn("2", message)
        self.assertEqual(order.approved_plan, "PLAN-OLD")
        self.assertEqual(plan.status, "Draft")

    def test_failed_gate_keeps_existing_approval_pointer_in_approve_flow(self):
        snapshot = _snapshot(
            [{"sheet_no": 1, "pieces": [_piece(special_json="")]}]
        )
        draft = SimpleNamespace(
            name="PLAN-NEW",
            source_type="System",
            snapshot_json=json.dumps(snapshot),
            status="Draft",
            validation_status="Valid",
            plan_needs_recalculation=0,
            cost_snapshot_version=command_service.COST_SNAPSHOT_VERSION,
            input_fingerprint="fp-1",
            revision=2,
            door_cutting_order="ORD-KEEP",
        )
        order = SimpleNamespace(
            name="ORD-KEEP",
            approved_plan="PLAN-OLD",
            ensure_special_shapes_documented=lambda: None,
        )
        calls = {"supersede": 0, "save": 0, "ready_calls": 0}

        class Repo:
            def latest_document(self, *args, **kwargs):
                return draft

            def approved_documents(self, *args, **kwargs):
                calls["supersede"] += 1
                return [SimpleNamespace(name="PLAN-OLD", status="Approved")]

            def save_document(self, *args, **kwargs):
                calls["save"] += 1

            def get_document(self, name):
                return draft

            def ensure_geometry_draft_from_cancelled(self, *args, **kwargs):
                return None

        def _ready(current_order, current_plan):
            calls["ready_calls"] += 1
            command_service._assert_system_plan_special_outline_approval(current_plan)

        with patch.object(
            command_service,
            "require_cutting_plan_capability",
            return_value=None,
        ), patch.object(
            command_service,
            "FrappeCuttingPlanCommandRepository",
            return_value=Repo(),
        ), patch.object(
            command_service,
            "_assert_plan_ready_for_approval",
            side_effect=_ready,
        ), patch.object(
            command_service.frappe,
            "parse_json",
            side_effect=lambda value: json.loads(value or "{}"),
        ), patch.object(
            command_service.frappe,
            "throw",
            side_effect=lambda message, *a, **k: (_ for _ in ()).throw(
                RuntimeError(str(message))
            ),
        ):
            with self.assertRaises(RuntimeError):
                command_service.approve_order_plan(order, "System")

        self.assertEqual(order.approved_plan, "PLAN-OLD")
        self.assertEqual(draft.status, "Draft")
        self.assertEqual(calls["ready_calls"], 1)
        self.assertEqual(calls["supersede"], 0)
        self.assertEqual(calls["save"], 0)

    def test_approve_order_plan_source_checks_before_supersede(self):
        with open(command_service.__file__, encoding="utf-8") as handle:
            source = handle.read()
        approval = source.split("def approve_order_plan", 1)[1].split(
            "def _apply_tool_diameters", 1
        )[0]
        ready_body = source.split("def _assert_plan_ready_for_approval", 1)[1].split(
            "def plan_payload", 1
        )[0]
        self.assertIn("_assert_system_plan_special_outline_approval(plan)", ready_body)
        self.assertLess(
            approval.index("_assert_plan_ready_for_approval(order, plan)"),
            approval.index("repository.approved_documents"),
        )


if __name__ == "__main__":
    unittest.main()
