"""Board Editor approve/export manufacturing contracts (no Frappe runtime)."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.cutting.board_editor_manufacturing import (
    BoardEditorManufacturingError,
    assert_board_editor_manufacturing_ready,
    piece_uses_posed_geometry,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
    materialize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import serialize_geometry_mm
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    BOARD_EDITOR,
    MANUFACTURING_EXPORT_SOURCES,
    manufacturing_actions_allowed,
)
from almdina_erp.tests.test_board_editor_plan_materialize import (
    draft_payload,
    layout_rows,
    projection,
    projection_piece,
    source_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
COMMAND = (
    ROOT
    / "almdina_erp"
    / "services"
    / "cutting_plan_command_service.py"
)
DXF_EXPORT = ROOT / "almdina_erp" / "services" / "dxf_export_service.py"
EXPORT_VALIDATION = ROOT / "almdina_erp" / "services" / "export_validation_service.py"
WORKSPACE_QUERY = (
    ROOT / "almdina_erp" / "services" / "cutting_plan_workspace_query_service.py"
)
CREATE_ADAPTER = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "board_editor_plan_create_adapter.py"
)
CONTEXT_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_context_actions_ux.js"
)
TABS_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_tabs_ux.js"
)
SECURE_DXF = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "secure_dxf_export.js"
)


def _rect(x: float, y: float, w: float, h: float):
    return ((x, y), (x + w, y), (x + w, y + h), (x, y + h))


def _ready_snapshot(*, rotation_deg: float = 0.0, machine_ok: bool = True):
    pieces = [projection_piece("A", 1, 0, 0, 400, 300, allow=True)]
    proj = projection(pieces)
    source = source_snapshot(pieces)
    layout = layout_rows(pieces, A={"x": 20, "y": 30, "rotation": rotation_deg})
    draft = draft_payload(layout)
    return materialize_plan_snapshot(
        draft=draft,
        projection=proj,
        source_snapshot=source,
        machine_type="CNC Router" if machine_ok or abs(rotation_deg % 90) < 1e-9 else "Panel Saw",
        source_plan_name="PLAN-SRC",
        expected_draft_version=1,
        source_content_revision="rev-1",
        source_input_fingerprint="fp-1",
    )


class BoardEditorManufacturingReadyTests(unittest.TestCase):
    def test_lifecycle_includes_board_editor_export_source(self):
        self.assertIn(BOARD_EDITOR, MANUFACTURING_EXPORT_SOURCES)
        self.assertTrue(manufacturing_actions_allowed(BOARD_EDITOR))

    def test_ready_for_0_90_and_free_cnc_angle(self):
        for angle in (0.0, 90.0, 35.0):
            snapshot = _ready_snapshot(rotation_deg=angle, machine_ok=True)
            assert_board_editor_manufacturing_ready(
                snapshot,
                machine_type="CNC Router",
                kerf_mm=4.0,
            )
            piece = snapshot["sheets"][0]["pieces"][0]
            self.assertTrue(piece_uses_posed_geometry(piece))
            self.assertFalse(piece.get("rotated"))
            self.assertAlmostEqual(piece["rotation_deg"], angle)

    def test_panel_saw_rejects_free_angle(self):
        snapshot = _ready_snapshot(rotation_deg=35.0, machine_ok=True)
        with self.assertRaises(BoardEditorManufacturingError) as ctx:
            assert_board_editor_manufacturing_ready(
                snapshot,
                machine_type="Panel Saw",
                kerf_mm=4.0,
            )
        self.assertEqual(ctx.exception.code, "machine_rotation_forbidden")

    def test_missing_geometry_rejected(self):
        snapshot = _ready_snapshot(rotation_deg=0.0)
        snapshot["sheets"][0]["pieces"][0].pop("geometry", None)
        with self.assertRaises(BoardEditorManufacturingError) as ctx:
            assert_board_editor_manufacturing_ready(
                snapshot,
                machine_type="CNC Router",
                kerf_mm=4.0,
            )
        self.assertEqual(ctx.exception.code, "missing_geometry")

    def test_material_overlap_rejected(self):
        geometry = serialize_geometry_mm(
            PartGeometry(outer=_rect(0, 0, 200, 200), holes=())
        )
        snapshot = {
            "sheets": [
                {
                    "sheet_no": 1,
                    "pieces": [
                        {
                            "id": 1,
                            "label": "A",
                            "piece_instance_id": "A",
                            "x": 0,
                            "y": 0,
                            "w": 20,
                            "h": 20,
                            "rotation_deg": 0,
                            "geometry": geometry,
                        },
                        {
                            "id": 2,
                            "label": "B",
                            "piece_instance_id": "B",
                            "x": 5,
                            "y": 5,
                            "w": 20,
                            "h": 20,
                            "rotation_deg": 0,
                            "geometry": copy.deepcopy(geometry),
                        },
                    ],
                }
            ]
        }
        with self.assertRaises(BoardEditorManufacturingError) as ctx:
            assert_board_editor_manufacturing_ready(
                snapshot,
                machine_type="CNC Router",
                kerf_mm=4.0,
            )
        self.assertEqual(ctx.exception.code, "material_layout_invalid")


class BoardEditorApproveExportWiringContractTests(unittest.TestCase):
    def test_export_snapshot_carries_posed_fields(self):
        source = EXPORT_VALIDATION.read_text(encoding="utf-8")
        block = source.split("def _plan_to_export_snapshot", 1)[1].split(
            "def _strict_editable_snapshot", 1
        )[0]
        self.assertIn('public_piece["rotation_deg"]', block)
        self.assertIn('public_piece["apply_rotated_to_geometry"]', block)
        self.assertIn('public_piece["overlays"]', block)
        # Outside-sheet uses posed outer when geometry is present.
        validate = source.split("def validate_cutting_plan_issues", 1)[1].split(
            "def validate_cutting_plan_document", 1
        )[0]
        self.assertIn("posed_outer", validate)

    def test_command_accepts_board_editor_source_and_revalidates(self):
        source = COMMAND.read_text(encoding="utf-8")
        self.assertIn('normalized in {"board editor"', source)
        self.assertIn("_assert_board_editor_manufacturing_ready", source)
        self.assertNotIn(
            "Board editor cutting plan copies cannot be approved yet",
            source,
        )
        self.assertIn('return "BoardEditor"', source)

    def test_dxf_export_resolves_board_editor_source(self):
        source = DXF_EXPORT.read_text(encoding="utf-8")
        self.assertIn("board editor", source)
        self.assertIn("assert_board_editor_manufacturing_ready", source)
        self.assertNotIn(
            "Board editor cutting plan copies cannot be exported yet",
            source,
        )
        include = source.split("def _include_saw_centers_for_export", 1)[1].split(
            "def _assert_saved_plan_fresh", 1
        )[0]
        self.assertIn("board editor", include)

    def test_workspace_no_longer_forces_permanent_block(self):
        source = WORKSPACE_QUERY.read_text(encoding="utf-8")
        self.assertNotIn("board_editor_geometry_not_exportable", source)
        self.assertIn("board_editor_plan_not_ready", source)
        self.assertIn(
            'board_editor_payload["can_approve"] = status == DRAFT and ready',
            source,
        )
        self.assertIn("select_board_editor_surface_plan", source)

    def test_create_adapter_initializes_existing_cost_snapshot(self):
        source = CREATE_ADAPTER.read_text(encoding="utf-8")
        self.assertIn("initialize_draft_plan_cost_snapshot", source)
        self.assertIn("apply_plan_costs", source)
        self.assertIn("factory_execution_edge_cost", source)

    def test_ui_exposes_edited_plan_actions_without_upload(self):
        context = CONTEXT_UX.read_text(encoding="utf-8")
        tabs = TABS_UX.read_text(encoding="utf-8")
        dxf = SECURE_DXF.read_text(encoding="utf-8")
        self.assertIn("Approve the edited plan", context)
        self.assertIn('BoardEditor: "board_editor_draft"', context)
        self.assertIn("approveDenialReason", context)
        self.assertNotIn(
            'if (tab === "BoardEditor" || String((row && row.source_type) || "") === "Board Editor") {\n            return false;',
            context,
        )
        self.assertIn('tab !== "BoardEditor" && canUpload(frm)', context)
        self.assertIn("Edited plan blocked", tabs)
        self.assertNotIn("Edited plan (view only)", tabs)
        self.assertIn("trustPosedOverlays", dxf)

    def test_approve_path_accepts_explicit_plan_name(self):
        command = COMMAND.read_text(encoding="utf-8")
        drawing = (
            ROOT / "almdina_erp" / "services" / "drawing_approval_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("plan_name: str | None = None", command)
        self.assertIn("explicit_name", command)
        self.assertIn("plan_name: str | None = None", drawing)


if __name__ == "__main__":
    unittest.main()
