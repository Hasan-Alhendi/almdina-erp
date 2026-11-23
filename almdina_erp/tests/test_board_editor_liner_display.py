"""Visual liner centerlines stay separate from stored cutter paths.

The picture is rebuilt from saved liner fields in the piece outline's frame.
A cutter wider than the liner blocks the copy. A fitting cutter stores one
center path, and that path is what later moves, rotations, and mirrors pose.
"""

from __future__ import annotations

import copy
import unittest

from almdina_erp.almdina_erp.application.cutting.board_editor_projection import (
    ELEMENT_KIND_OVERLAY,
    project_board_editor,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft_review import (
    apply_plan_tool_diameters,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
    BoardEditorMaterializeError,
    materialize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_rotation import rotate_point
from almdina_erp.almdina_erp.domain.cutting.tool_diameters import (
    _persisted_toolpath,
    snapshot_tool_errors,
    diameters_for_record,
)
from almdina_erp.tests.test_board_editor_draft_review import groove_fields, liner_fields
from almdina_erp.tests.test_board_editor_plan_materialize import (
    draft_payload,
    layout_rows,
    projection,
    projection_piece,
    source_snapshot,
)
from almdina_erp.tests.test_board_editor_copy_tool_diameters import _carry_machining


def _visual_liners(projected, instance="pi-a"):
    return [
        element
        for element in projected["elements"]
        if element["kind"] == ELEMENT_KIND_OVERLAY
        and element.get("piece_instance_id") == instance
        and (element.get("payload") or {}).get("kind") == "liner"
    ]


def _copy(pieces, *, kerf_mm, liner_diameter, layout=None, groove_diameter=None, sheets=None):
    plan = {
        "kerf_mm": kerf_mm,
        "liner_tool_diameter_mm": liner_diameter,
        "machine_type": "CNC Router",
    }
    if groove_diameter is not None:
        plan["rear_groove_tool_diameter_mm"] = groove_diameter
    projected = apply_plan_tool_diameters(
        projection(pieces, sheets=sheets, kerf_cm=kerf_mm / 10.0),
        plan,
    )
    source = _carry_machining(source_snapshot(pieces), pieces)
    if sheets:
        present = {int(sheet["sheet_no"]) for sheet in source["sheets"]}
        for number, info in sheets.items():
            if int(number) in present:
                continue
            source["sheets"].append({
                "sheet_no": int(number),
                "resource_kind": "FULL_BOARD",
                "w": 120.0,
                "h": 240.0,
                "usable_width_cm": info.get("usable_width_mm", 1200) / 10.0,
                "usable_length_cm": info.get("usable_length_mm", 2400) / 10.0,
                "full_width_cm": 122.0,
                "full_length_cm": 244.0,
                "source_area_m2": 2.88,
                "pieces": [],
            })
    source["kerf_cm"] = kerf_mm / 10.0
    snapshot = materialize_plan_snapshot(
        draft=draft_payload(layout or layout_rows(pieces)),
        projection=projected,
        source_snapshot=source,
        machine_type="CNC Router",
        source_plan_name="PLAN-SRC",
        expected_draft_version=1,
        source_content_revision="rev-1",
        source_input_fingerprint="fp-1",
    )
    return snapshot


def _stored_piece(snapshot, instance="pi-a"):
    for sheet in snapshot["sheets"]:
        for piece in sheet["pieces"]:
            if piece.get("piece_instance_id") == instance:
                return piece
    raise AssertionError(instance)


class LinerDisplaySeparationTests(unittest.TestCase):
    def test_wider_bit_blocks_the_copy_and_a_fitting_bit_keeps_its_center(self):
        machining = liner_fields(side="edge_width_top", offset=0, width=0.6, start=0, length=0)
        pieces = [projection_piece("pi-a", 1, 100, 100, 400, 500, machining=machining)]
        with self.assertRaises(BoardEditorMaterializeError):
            _copy(pieces, kerf_mm=4, liner_diameter=8)
        narrower = _copy(pieces, kerf_mm=8, liner_diameter=4)
        narrower_piece = _stored_piece(narrower)
        self.assertTrue(any(item.get("kind") == "liner" for item in narrower_piece["overlays"]))
        self.assertFalse(any(
            item.get("geometry_source") == "parametric_visual" or item.get("display_only")
            for item in narrower_piece["overlays"]
        ))
        narrower_view = _visual_liners(project_board_editor(narrower))
        self.assertEqual(len(narrower_view), 1)
        path = narrower_view[0]["geometry"]["path"]
        self.assertGreaterEqual(len(path), 2)
        self.assertTrue(all(abs(point[1] - 103) < 0.05 for point in path))
        stored_path = next(
            item["geometry"]["path"]
            for item in narrower_piece["overlays"]
            if item.get("kind") == "liner"
        )
        self.assertTrue(all(abs(point[1] - 102) < 0.05 for point in stored_path[:2]))

    def test_reopen_and_second_copy_keep_one_line(self):
        machining = liner_fields(side="edge_width_top", offset=0, width=0.6, start=0, length=0)
        pieces = [projection_piece("pi-a", 1, 100, 100, 400, 500, machining=machining)]
        first = _copy(pieces, kerf_mm=4, liner_diameter=6)
        reopened = project_board_editor(first)
        self.assertEqual(len(_visual_liners(reopened)), 1)
        second_layout = layout_rows(pieces)
        second = materialize_plan_snapshot(
            draft=draft_payload(second_layout),
            projection=reopened,
            source_snapshot=first,
            machine_type="CNC Router",
            source_plan_name="PLAN-EDITED",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
        )
        second_view = _visual_liners(project_board_editor(second))
        self.assertEqual(len(second_view), 1)
        self.assertFalse(any(
            item.get("display_only") or item.get("geometry_source") == "parametric_visual"
            for item in _stored_piece(second)["overlays"]
        ))

    def test_move_rotation_mirror_and_board_transfer_pose_the_line_once(self):
        machining = liner_fields(side="edge_long_left", offset=0, width=0.6, start=0, length=0)
        pieces = [projection_piece("pi-a", 1, 100, 100, 400, 500, machining=machining, allow=True)]
        moved = _copy(
            pieces,
            kerf_mm=4,
            liner_diameter=4,
            layout=layout_rows(pieces, **{"pi-a": {"x": 250, "y": 100}}),
        )
        moved_path = _visual_liners(project_board_editor(moved))[0]["geometry"]["path"]
        self.assertTrue(all(abs(point[0] - 253) < 0.05 for point in moved_path))

        turned = _copy(
            pieces,
            kerf_mm=4,
            liner_diameter=4,
            layout=layout_rows(pieces, **{"pi-a": {"x": 100, "y": 100, "rotation": 35}}),
        )
        turned_piece = _stored_piece(turned)
        turned_path = _visual_liners(project_board_editor(turned))[0]["geometry"]["path"]
        outer = turned_piece["geometry"]["outer"]
        xs = [point[0] for point in outer]
        ys = [point[1] for point in outer]
        pivot = {"x": (min(xs) + max(xs)) / 2.0, "y": (min(ys) + max(ys)) / 2.0}
        restored = [rotate_point(point, pivot, -35) for point in turned_path]
        restored_outer = [rotate_point(point, pivot, -35) for point in outer]
        left = min(point[0] for point in restored_outer)
        self.assertTrue(all(abs(point[0] - (left + 3)) < 0.75 for point in restored))
        self.assertGreater(max(point[0] for point in turned_path) - min(point[0] for point in turned_path), 1)

        mirrored_layout = layout_rows(pieces, **{"pi-a": {"x": 100, "y": 100}})
        mirrored_layout["pieces"][0]["flip_h"] = True
        mirrored = _copy(pieces, kerf_mm=4, liner_diameter=6, layout=mirrored_layout)
        mirrored_path = _visual_liners(project_board_editor(mirrored))[0]["geometry"]["path"]
        self.assertTrue(all(abs(point[0] - 497) < 0.75 for point in mirrored_path))

        board = {
            "resource_kind": "FULL_BOARD",
            "usable_width_mm": 1200,
            "usable_length_mm": 2400,
        }
        transferred_layout = layout_rows(pieces, boards=(1, 2), **{"pi-a": {"sheet": 2, "x": 40, "y": 70}})
        transferred = _copy(
            pieces,
            kerf_mm=4,
            liner_diameter=4,
            layout=transferred_layout,
            sheets={1: dict(board, sheet_no=1), 2: dict(board, sheet_no=2)},
        )
        stored = _stored_piece(transferred)
        self.assertEqual(
            next(sheet["sheet_no"] for sheet in transferred["sheets"] for piece in sheet["pieces"] if piece is stored),
            2,
        )
        transferred_view = _visual_liners(project_board_editor(transferred))
        self.assertEqual(len(transferred_view), 1)
        self.assertEqual(transferred_view[0]["sheet_no"], 2)
        self.assertTrue(all(abs(point[0] - 43) < 0.05 for point in transferred_view[0]["geometry"]["path"]))

    def test_two_liners_and_a_groove_stay_distinct(self):
        machining = {}
        machining.update(liner_fields(
            side="edge_width_top",
            offset=0,
            width=0.6,
            specs=[
                {"id": "liner_1", "side": "edge_width_top", "offset_cm": 0, "start_cm": 0, "length_cm": 0},
                {"id": "liner_2", "side": "edge_width_bottom", "offset_cm": 0, "start_cm": 0, "length_cm": 0},
            ],
        ))
        machining.update(groove_fields(side="edge_long_right", offset=1, width=1.8, start=0, length=20))
        pieces = [projection_piece("pi-a", 1, 100, 100, 400, 500, machining=machining)]
        snapshot = _copy(pieces, kerf_mm=4, liner_diameter=6, groove_diameter=4)
        stored = _stored_piece(snapshot)
        self.assertEqual(sum(item.get("kind") == "liner" for item in stored["overlays"]), 2)
        self.assertTrue(any(item.get("kind") == "back_groove" for item in stored["overlays"]))
        view = project_board_editor(snapshot)
        liners = _visual_liners(view)
        grooves = [
            element
            for element in view["elements"]
            if element["kind"] == ELEMENT_KIND_OVERLAY
            and (element.get("payload") or {}).get("kind") == "back_groove"
        ]
        self.assertEqual(len(liners), 2)
        self.assertTrue(all(element["payload"].get("display_only") for element in liners))
        ys = sorted(element["geometry"]["path"][0][1] for element in liners)
        self.assertLess(abs(ys[0] - 103), 0.05)
        self.assertLess(abs(ys[1] - 597), 0.05)
        self.assertEqual(len(grooves), 1)
        self.assertFalse(grooves[0]["payload"].get("display_only"))

    def test_visual_mark_is_not_a_persisted_toolpath(self):
        visual = {
            "kind": "liner",
            "geometry_source": "parametric_visual",
            "display_only": True,
            "geometry": {"path": [[0, 3], [400, 3]]},
        }
        cutter = {
            "kind": "liner",
            "geometry": {"path": [[0, 4], [400, 4]]},
        }
        self.assertFalse(_persisted_toolpath({"overlays": [visual]}, "liner"))
        self.assertTrue(_persisted_toolpath({"overlays": [cutter]}, "liner"))
        self.assertTrue(_persisted_toolpath({"overlays": [visual, cutter]}, "liner"))
        untouched = {"overlays": [{"kind": "back_groove", "geometry": {"path": [[1, 1], [2, 2]]}}]}
        self.assertTrue(_persisted_toolpath(untouched, "back_groove"))
        self.assertEqual(copy.deepcopy(untouched), untouched)
