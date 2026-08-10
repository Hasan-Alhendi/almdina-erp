from __future__ import annotations

import json
import unittest
from html import escape
from types import SimpleNamespace

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.presentation.shop_floor.data_policy import (
    PLAN_AND_DXF_PAYLOAD_FIELDS,
    sanitize_shop_floor_detail,
)
from almdina_erp.almdina_erp.presentation.shop_floor.presenters import (
    present_order_detail,
    render_pieces_html,
    render_plan_html,
)


class TestShopFloorPresenters(unittest.TestCase):
    def test_piece_presenter_renders_measurements_edges_and_read_only_label(self) -> None:
        order = SimpleNamespace(
            default_edge_type="قشاط رئيسي",
            pieces=[
                SimpleNamespace(
                    edge_type="",
                    width_cm=40,
                    length_cm=80,
                    qty=2,
                    allow_rotation=1,
                    edge_long_right=1,
                    edge_long_left=0,
                    edge_width_top=1,
                    edge_width_bottom=0,
                )
            ],
        )

        html = render_pieces_html(
            order,
            translate=lambda value: value,
            escape=escape,
        )

        self.assertIn("قائمة القطع والقشاط", html)
        self.assertIn("الطلب للعرض فقط", html)
        self.assertIn(">40<", html)
        self.assertIn(">80<", html)
        self.assertIn("قشاط رئيسي", html)
        self.assertIn("is-checked", html)

    def test_plan_presenter_preserves_piece_geometry_and_edge_marks(self) -> None:
        snapshot = {
            "usable_board_width_cm": 122,
            "usable_board_length_cm": 244,
            "sheets": [
                {
                    "sheet_no": 1,
                    "pieces": [
                        {
                            "x": 0,
                            "y": 0,
                            "w": 40,
                            "h": 80,
                            "original_w": 40,
                            "original_h": 80,
                            "label": "P-1",
                            "edge_long_left": 1,
                        }
                    ],
                }
            ],
        }

        html = render_plan_html(
            order_name="DCO-1",
            customer="Customer",
            snapshot=snapshot,
            translate=lambda value: value,
            escape=escape,
        )

        self.assertIn("خطة القص", html)
        self.assertIn("DCO-1", html)
        self.assertIn("P-1", html)
        self.assertIn("40.0*80.0 سم", html)
        self.assertIn("border-left:3px solid #d00000", html)

    def test_detail_presenter_keeps_existing_api_shape(self) -> None:
        order = SimpleNamespace(
            name="DCO-2",
            customer="Customer",
            status="At Drawing",
            production_path="Drawing",
            current_department="رسم",
            current_assignee="drawing@example.com",
            department_status="قيد العمل",
            current_production_stage="PST-2",
            approved_plan=None,
            pieces=[],
            packing_mode="Auto Pro",
            kerf_mm=3,
            trim_margin_mm=5,
            cutting_machine_type="Panel Saw",
            production_dxf=None,
            drawing_dxf_status="None",
        )
        system_snapshot = {
            "usable_board_width_cm": 122,
            "usable_board_length_cm": 244,
            "sheets": [{"sheet_no": 1, "pieces": []}],
        }
        result = present_order_detail(
            {
                "order": order,
                "stages": [{"name": "PST-2"}],
                "stage_snapshot": {
                    "active_stage_name": "PST-2",
                    "active_stage_status": "In Progress",
                    "active_stage_type": "Drawing",
                    "can_start_stage": False,
                    "can_handoff_stage": True,
                    "can_handoff_to": "CNC",
                },
                "system_snapshot": system_snapshot,
                "custom_snapshot": {},
                "approved_snapshot": system_snapshot,
                "active_snapshot": system_snapshot,
                "approved_plan_source": "System",
                "active_plan_source": "System",
                "visible_plan_tabs": ["System", "Custom", "Approved"],
                "show_dual_tabs": True,
                "can_recalculate_drawing_plan": True,
            },
            translate=lambda value: value,
            escape=escape,
            dumps=lambda value: json.dumps(value, ensure_ascii=False),
        )

        required_keys = {
            "pieces_html",
            "cutting_plan_html",
            "system_plan_html",
            "custom_plan_html",
            "approved_plan_html",
            "system_plan_json",
            "custom_plan_json",
            "active_plan_source",
            "visible_plan_tabs",
            "show_dual_tabs",
            "can_start_stage",
            "can_handoff_stage",
            "can_handoff_to",
            "can_recalculate_drawing_plan",
        }
        self.assertTrue(required_keys.issubset(result))
        self.assertEqual(result["current_stage_type"], "Drawing")
        self.assertEqual(result["can_handoff_to"], "CNC")
        self.assertIn('"sheets"', result["system_plan_json"])

    def test_plan_and_dxf_data_are_removed_without_view_capability(self) -> None:
        payload = {
            "name": "DCO-3",
            "pieces_html": "pieces",
            "production_actions": {"start_assigned_stage": {"allowed": True}},
            **{fieldname: f"secret:{fieldname}" for fieldname in PLAN_AND_DXF_PAYLOAD_FIELDS},
        }

        sanitized = sanitize_shop_floor_detail(
            payload,
            {Capability.VIEW_CUTTING_PLAN: False},
        )

        self.assertEqual(sanitized["name"], "DCO-3")
        self.assertEqual(sanitized["pieces_html"], "pieces")
        self.assertIn("production_actions", sanitized)
        for fieldname in PLAN_AND_DXF_PAYLOAD_FIELDS:
            self.assertNotIn(fieldname, sanitized)

    def test_plan_permission_does_not_leak_dxf_data(self) -> None:
        payload = {
            "name": "DCO-4",
            "production_dxf": "/private/files/order.dxf",
            "system_plan_json": '{"sheets":[]}',
        }
        sanitized = sanitize_shop_floor_detail(
            payload,
            {Capability.VIEW_CUTTING_PLAN: True},
        )
        self.assertEqual(
            sanitized,
            {
                "name": "DCO-4",
                "system_plan_json": '{"sheets":[]}',
            },
        )
        self.assertIsNot(sanitized, payload)


if __name__ == "__main__":
    unittest.main()
