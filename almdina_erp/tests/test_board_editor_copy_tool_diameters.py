"""Board-editor plan copy uses each layer's stored tool diameter.

Copy readiness is separate from machining-path validity. A liner bit wider
than the liner strip does not reject the copy and does not store a center path.
"""

from __future__ import annotations

import copy
import csv
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.cutting.board_editor_draft_review import (
    review_editor_draft,
)
from almdina_erp.almdina_erp.application.cutting.board_editor_projection import (
    project_board_editor,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft_review import (
    apply_plan_tool_diameters,
    pose_normalized_layout,
    review_saved_draft,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_manufacturing import (
    assert_board_editor_manufacturing_ready,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
    materialize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerGeometryError,
    LinerPiece,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import generate_toolpath
from almdina_erp.almdina_erp.domain.cutting.tool_diameters import (
    diameters_for_record,
    initial_diameters,
    snapshot_tool_errors,
)
from almdina_erp.tests.test_board_editor_draft_review import (
    boards,
    codes,
    draft,
    groove_fields,
    handle_fields,
    liner_fields,
    model,
    piece,
    row,
)
from almdina_erp.tests.test_board_editor_plan_materialize import (
    draft_payload,
    layout_rows,
    projection,
    projection_piece,
    source_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
MESSAGE = (
    "The liner tool is wider than the liner strip, so no machining path was stored with this copy."
)
ARABIC = "ريشة اللاينر أعرض من شريط اللاينر، لذلك لم يُحفظ مسار تشغيل مع هذه النسخة."


def _ys(path):
    return sorted({round(float(point[1]), 3) for point in path})


def _review(pieces, *, kerf, diameters=None, machine="CNC Router"):
    trusted = model(pieces, kerf=kerf, machine=machine)
    for field, value in (diameters or {}).items():
        trusted[field] = value
    layout = {
        "schema": 1,
        "pieces": [row(item[0], item[1]["local_x_mm"], item[1]["local_y_mm"]) for item in pieces],
        "boards": boards(1),
    }
    return review_saved_draft(draft(layout), trusted), trusted, layout


def _posed_paths(trusted, layout):
    posed = pose_normalized_layout(layout, trusted)
    paths = []
    for piece_row in posed["pieces"]:
        paths.extend(piece_row.get("machining_paths") or [])
    return paths


def _carry_machining(snapshot, pieces):
    by_id = {item["piece_instance_id"]: item for item in pieces}
    for sheet in snapshot["sheets"]:
        for stored in sheet["pieces"]:
            source = by_id[stored["piece_instance_id"]]
            for key, value in source.items():
                if key.startswith(("extra_", "liner_", "back_groove_", "recessed_handle_")):
                    stored[key] = copy.deepcopy(value)
    return snapshot


class BoardEditorCopyToolDiameterTests(unittest.TestCase):
    def test_saw_wider_than_strip_still_copies_when_liner_bit_fits(self):
        machining = liner_fields(side="edge_width_top", offset=0, width=0.6, start=0, length=0)
        pieces = [piece("pi-a", 1, 0, 0, 400, 500, machining=machining)]
        result, trusted, layout = _review(
            pieces,
            kerf=8,
            diameters={"liner_tool_diameter_mm": 4},
        )
        self.assertTrue(result["ready"], result["issues"])
        self.assertNotIn("geometry_unproven", codes(result))
        self.assertNotIn("machining_path_unproven", codes(result))
        paths = [item for item in _posed_paths(trusted, layout) if item["kind"] == "liner"]
        self.assertTrue(paths)
        self.assertTrue(all(item["cutter_diameter_mm"] == 4 for item in paths))
        expected = generate_toolpath(
            kind="liner",
            piece=LinerPiece("Regular", 40, 50),
            reference_side="edge_width_top",
            offset_cm=0,
            width_cm=0.6,
            start_cm=0,
            length_cm=0,
            cutter_diameter_mm=4,
        )
        self.assertEqual(_ys(paths[0]["path_mm"]), _ys(expected))
        with self.assertRaises(LinerGeometryError) as caught:
            generate_toolpath(
                kind="liner",
                piece=LinerPiece("Regular", 40, 50),
                reference_side="edge_width_top",
                offset_cm=0,
                width_cm=0.6,
                start_cm=0,
                length_cm=0,
                cutter_diameter_mm=8,
            )
        self.assertEqual(caught.exception.code, "liner_narrower_than_cutter")

    def test_liner_bit_equal_to_the_strip_is_accepted(self):
        # Inset from the sheet so both contour ends are sawn. One center can
        # then be stored; a flat unsawn end still has no proven closure.
        machining = liner_fields(side="edge_width_top", offset=0, width=0.6, start=0, length=0)
        result, trusted, layout = _review(
            [piece("pi-a", 1, 100, 100, 400, 500, machining=machining)],
            kerf=8,
            diameters={"liner_tool_diameter_mm": 6},
        )
        self.assertTrue(result["ready"], result["issues"])
        paths = [item for item in _posed_paths(trusted, layout) if item["kind"] == "liner"]
        self.assertTrue(paths)
        self.assertTrue(all(item["cutter_diameter_mm"] == 6 for item in paths))
        self.assertEqual(len({round(point[1], 3) for point in paths[0]["path_mm"]}), 1)

    def test_liner_bit_wider_than_the_strip_does_not_block_the_copy(self):
        machining = liner_fields(side="edge_width_top", offset=0, width=0.6, start=0, length=0)
        result, trusted, layout = _review(
            [piece("pi-a", 1, 0, 0, 400, 500, machining=machining)],
            kerf=4,
            diameters={"liner_tool_diameter_mm": 8},
        )
        self.assertTrue(result["ready"], result["issues"])
        warnings = [
            issue for issue in result["issues"] if issue["code"] == "machining_path_unproven"
        ]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["severity"], "warning")
        self.assertEqual(warnings[0]["addon_kind"], "liner")
        self.assertEqual(warnings[0]["reason"], "liner_narrower_than_cutter")
        self.assertNotIn("geometry_unproven", codes(result))
        self.assertFalse(
            [item for item in _posed_paths(trusted, layout) if item["kind"] == "liner"]
        )
        self.assertEqual(trusted["pieces"]["pi-a"]["liner_width_cm"], 0.6)

    def test_each_addon_uses_its_own_diameter(self):
        machining = {}
        machining.update(liner_fields(side="edge_width_top", offset=0, width=1.8, start=0, length=40))
        machining.update(groove_fields(side="edge_width_top", offset=0, width=1.8, start=0, length=40))
        machining.update(handle_fields(side="edge_width_top", offset=0, width=1.8, start=0, length=40))
        result, trusted, layout = _review(
            [piece("pi-a", 1, 0, 0, 400, 800, machining=machining)],
            kerf=8,
            diameters={
                "liner_tool_diameter_mm": 4,
                "handle_recess_tool_diameter_mm": 8,
                "rear_groove_tool_diameter_mm": 5,
            },
        )
        self.assertTrue(result["ready"], result["issues"])
        paths = _posed_paths(trusted, layout)
        by_kind = {}
        for item in paths:
            by_kind.setdefault(item["kind"], item["cutter_diameter_mm"])
        self.assertEqual(
            by_kind,
            {
                "liner": 4,
                "recessed_handle_cutout": 8,
                "back_groove": 5,
            },
        )
        host = LinerPiece("Regular", 40, 80)
        for kind, diameter in by_kind.items():
            expected = generate_toolpath(
                kind=kind,
                piece=host,
                reference_side="edge_width_top",
                offset_cm=0,
                width_cm=1.8,
                start_cm=0,
                length_cm=40,
                cutter_diameter_mm=diameter,
            )
            stored = next(item["path_mm"] for item in paths if item["kind"] == kind)
            self.assertEqual(_ys(stored), _ys(expected))
            other = next(value for value in by_kind.values() if value != diameter)
            different = generate_toolpath(
                kind=kind,
                piece=host,
                reference_side="edge_width_top",
                offset_cm=0,
                width_cm=1.8,
                start_cm=0,
                length_cm=40,
                cutter_diameter_mm=other,
            )
            self.assertNotEqual(_ys(stored), _ys(different))

    def test_old_plan_without_layer_diameters_inherits_kerf(self):
        plan = {"kerf_mm": 6}
        projection_board = apply_plan_tool_diameters({"board": {"kerf_cm": 0.6}}, plan)
        self.assertEqual(plan, {"kerf_mm": 6})
        self.assertEqual(projection_board["board"]["liner_tool_diameter_mm"], 6)
        self.assertEqual(projection_board["board"]["handle_recess_tool_diameter_mm"], 6)
        self.assertEqual(projection_board["board"]["rear_groove_tool_diameter_mm"], 6)
        machining = {}
        machining.update(liner_fields(side="edge_width_top", offset=0, width=1.8, start=0, length=20))
        machining.update(groove_fields(side="edge_width_top", offset=0, width=1.8, start=0, length=20))
        result, trusted, layout = _review(
            [piece("pi-a", 1, 0, 0, 400, 500, machining=machining)],
            kerf=6,
        )
        self.assertTrue(result["ready"], result["issues"])
        paths = _posed_paths(trusted, layout)
        self.assertTrue(paths)
        self.assertTrue(all(item["cutter_diameter_mm"] == 6 for item in paths))

    def test_real_neighbor_collision_uses_the_liner_bit(self):
        machining = liner_fields(side="edge_width_top", offset=0, width=2.0, start=0, length=0)
        pieces = [
            piece("pi-a", 1, 0, 0, 400, 500, machining=machining),
            piece("pi-b", 2, 406, 0, 400, 500),
        ]
        result, _trusted, _layout = _review(
            pieces,
            kerf=4,
            diameters={"liner_tool_diameter_mm": 16},
        )
        self.assertFalse(result["ready"])
        self.assertIn("addon_material_conflict", codes(result))
        self.assertNotIn("kerf_clearance", codes(result))

    def test_liner_bit_inside_the_kerf_gap_is_not_a_false_collision(self):
        machining = liner_fields(side="edge_width_top", offset=0, width=2.0, start=0, length=0)
        pieces = [
            piece("pi-a", 1, 0, 0, 400, 500, machining=machining),
            piece("pi-b", 2, 406, 0, 400, 500),
        ]
        result, _trusted, _layout = _review(
            pieces,
            kerf=4,
            diameters={"liner_tool_diameter_mm": 4},
        )
        self.assertTrue(result["ready"], result["issues"])
        self.assertNotIn("addon_material_conflict", codes(result))

    def test_groove_bit_wider_than_its_strip_still_blocks(self):
        machining = groove_fields(side="edge_width_top", offset=1, width=0.4, start=0, length=20)
        result, _trusted, _layout = _review(
            [piece("pi-a", 1, 0, 0, 400, 500, machining=machining)],
            kerf=3,
            diameters={"rear_groove_tool_diameter_mm": 6},
        )
        self.assertFalse(result["ready"])
        unproven = [issue for issue in result["issues"] if issue["code"] == "geometry_unproven"]
        self.assertTrue(any(
            issue["addon_kind"] == "back_groove" and issue["reason"] == "liner_narrower_than_cutter"
            for issue in unproven
        ))
        self.assertNotIn("machining_path_unproven", codes(result))

    def test_copy_reopen_keeps_geometry_settings_and_diameters(self):
        plan = {
            "kerf_mm": 8,
            "optimization_mode": "smart",
            "machine_type": "CNC Router",
            "liner_tool_diameter_mm": 4,
            "handle_recess_tool_diameter_mm": 7,
            "rear_groove_tool_diameter_mm": 5,
        }
        before_plan = copy.deepcopy(plan)
        machining = liner_fields(side="edge_width_top", offset=2, width=0.6, start=1, length=20)
        pieces = [
            projection_piece("pi-a", 1, 0, 0, 400, 500, machining=machining),
            projection_piece("pi-b", 2, 408, 0, 300, 400),
        ]
        projected = apply_plan_tool_diameters(projection(pieces, kerf_cm=0.8), plan)
        source = _carry_machining(source_snapshot(pieces), pieces)
        source["kerf_cm"] = 0.8
        before_source = copy.deepcopy(source)
        layout = layout_rows(pieces)
        snapshot = materialize_plan_snapshot(
            draft=draft_payload(layout),
            projection=projected,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
        )
        self.assertEqual(plan, before_plan)
        self.assertEqual(source, before_source)
        copied = {item["piece_instance_id"]: item for item in snapshot["sheets"][0]["pieces"]}
        self.assertEqual(copied["pi-a"]["w"], 40)
        self.assertEqual(copied["pi-a"]["h"], 50)
        self.assertEqual(copied["pi-a"]["x"], 0)
        self.assertEqual(copied["pi-a"]["liner_width_cm"], 0.6)
        self.assertEqual(copied["pi-a"]["liner_offset_cm"], 2)
        self.assertEqual(copied["pi-b"]["x"], 40.8)
        self.assertEqual(copied["pi-b"]["w"], 30)
        self.assertTrue(any(item.get("kind") == "liner" for item in copied["pi-a"]["overlays"]))
        self.assertEqual(snapshot["saw_center_status"], "Absent")
        self.assertFalse(snapshot["layout_origin"]["cut_path_carried"])
        seeded = initial_diameters(kerf_mm=8, lineage=plan)
        self.assertEqual(seeded["liner_tool_diameter_mm"], 4)
        self.assertEqual(seeded["handle_recess_tool_diameter_mm"], 7)
        self.assertEqual(seeded["rear_groove_tool_diameter_mm"], 5)
        reopened = apply_plan_tool_diameters(project_board_editor(snapshot), plan)
        reopened_piece = next(
            item for item in reopened["pieces"] if item["piece_instance_id"] == "pi-a"
        )
        self.assertEqual(reopened_piece["liner_width_cm"], 0.6)
        self.assertEqual(reopened_piece["placement_cm"]["w"], 40)
        self.assertEqual(reopened["board"]["kerf_cm"], 0.8)
        self.assertEqual(reopened["board"]["liner_tool_diameter_mm"], 4)
        reviewed = review_editor_draft(
            draft=draft_payload(layout),
            projection=reopened,
            machine_type="CNC Router",
        )
        self.assertTrue(reviewed["ready"], reviewed["issues"])

    def test_export_safety_accepts_the_fitting_bit_and_refuses_the_wider_one(self):
        fitting = self._materialized_liner(width_cm=0.6, liner_diameter=4, kerf=8)
        assert_board_editor_manufacturing_ready(
            fitting,
            machine_type="CNC Router",
            kerf_mm=8,
        )
        fitting_diameters = diameters_for_record({
            "kerf_mm": 8,
            "liner_tool_diameter_mm": 4,
        })
        self.assertEqual(snapshot_tool_errors(fitting, fitting_diameters), [])
        bare = copy.deepcopy(fitting)
        bare["sheets"][0]["pieces"][0]["overlays"] = []
        self.assertEqual(snapshot_tool_errors(bare, fitting_diameters), [])
        saw_as_liner = diameters_for_record({"kerf_mm": 8, "liner_tool_diameter_mm": 8})
        refused = snapshot_tool_errors(bare, saw_as_liner)
        self.assertEqual(refused[0]["code"], "liner_narrower_than_cutter")

        wider = self._materialized_liner(width_cm=0.6, liner_diameter=8, kerf=4)
        assert_board_editor_manufacturing_ready(
            wider,
            machine_type="CNC Router",
            kerf_mm=4,
        )
        self.assertFalse(any(
            item.get("kind") == "liner"
            for item in wider["sheets"][0]["pieces"][0]["overlays"]
        ))
        self.assertEqual(wider["sheets"][0]["pieces"][0]["liner_width_cm"], 0.6)
        wider_errors = snapshot_tool_errors(
            wider,
            diameters_for_record({"kerf_mm": 4, "liner_tool_diameter_mm": 8}),
        )
        self.assertEqual(wider_errors[0]["code"], "liner_narrower_than_cutter")
        self.assertEqual(wider_errors[0]["kind"], "liner")

    def test_projection_wiring_preserves_translation_and_lineage_copy(self):
        query = (ROOT / "almdina_erp" / "services" / "board_editor_query_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("apply_plan_tool_diameters(", query)
        review = (
            ROOT / "almdina_erp" / "services" / "board_editor_draft_review_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn(MESSAGE, review)
        with (ROOT / "translations" / "ar.csv").open(encoding="utf-8", newline="") as handle:
            translations = {
                row[0]: row[1] for row in csv.reader(handle) if len(row) >= 2
            }
        self.assertEqual(translations[MESSAGE], ARABIC)
        repository = (
            ROOT / "almdina_erp" / "infrastructure" / "frappe" / "cutting_plan_command_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("initial_diameters(", repository)
        adapter = (
            ROOT / "almdina_erp" / "infrastructure" / "frappe" / "board_editor_plan_create_adapter.py"
        ).read_text(encoding="utf-8")
        self.assertIn("based_on_plan=based_on_plan", adapter)

    def _materialized_liner(self, *, width_cm, liner_diameter, kerf):
        plan = {"kerf_mm": kerf, "liner_tool_diameter_mm": liner_diameter}
        machining = liner_fields(
            side="edge_width_top", offset=0, width=width_cm, start=0, length=20
        )
        pieces = [projection_piece("pi-a", 1, 80, 80, 400, 500, machining=machining)]
        projected = apply_plan_tool_diameters(projection(pieces, kerf_cm=kerf / 10.0), plan)
        source = _carry_machining(source_snapshot(pieces), pieces)
        return materialize_plan_snapshot(
            draft=draft_payload(layout_rows(pieces)),
            projection=projected,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
        )


if __name__ == "__main__":
    unittest.main()
