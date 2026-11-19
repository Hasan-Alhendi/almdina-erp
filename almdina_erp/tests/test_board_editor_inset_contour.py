"""Interior manufacturing contours keep their offset and reserve the blank."""

from __future__ import annotations

import copy
import io
import json
import math
import unittest

import ezdxf

from almdina_erp.almdina_erp.application.cutting.board_editor_plan_create import (
    projection_with_adopted_geometry,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_compile import (
    compile_manufacturing_geometry,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
    materialize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_rotation import (
    rederive_outline,
    rotate_point,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_transform import apply_local_flip_h
from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import cutter_center_paths
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import polygons_overlap
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
    material_outline_cm,
    occupancy_outline_cm,
)
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry_bytes
from almdina_erp.tests.test_board_editor_drawing_compile import _doc, _ring
from almdina_erp.tests.test_board_editor_plan_materialize import (
    draft_payload,
    layout_rows,
    projection,
    projection_piece,
    source_snapshot,
)


BLANK_W = 330.0
BLANK_H = 550.0
KERF_MM = 4.0


def _compile(points, width=BLANK_W, length=BLANK_H):
    return compile_manufacturing_geometry(
        _doc([_ring(points)], width=width, length=length),
        blank_width_mm=width,
        blank_length_mm=length,
    )


def _near(point, expected, tolerance=0.05):
    return math.dist(point, expected) <= tolerance


class InsetContourContractTests(unittest.TestCase):
    def test_supported_contours_keep_offset_and_reject_invalid_ones(self):
        rectangle = _compile([(50, 100), (250, 100), (250, 400), (50, 400)])
        self.assertEqual(rectangle["status"], "ready", rectangle.get("code"))
        self.assertEqual(rectangle["geometry"]["reservation"], "blank")
        self.assertEqual(rectangle["geometry"]["blank_width_cm"], 33)
        self.assertEqual(rectangle["geometry"]["blank_length_cm"], 55)
        self.assertEqual(rectangle["geometry"]["points"][0], [5.0, 10.0])
        self.assertEqual(rectangle["geometry"]["points"][2], [25.0, 40.0])

        hexagon = _compile([(90, 40), (240, 40), (290, 140), (240, 240), (90, 240), (40, 140)])
        one_edge = _compile([(0, 80), (180, 80), (180, 260), (0, 260)])
        two_edges = _compile([(0, 0), (180, 0), (180, 260), (0, 260)])
        three_edges = _compile([(0, 0), (330, 0), (330, 260), (0, 260)])
        four_edges = _compile([(0, 0), (330, 0), (330, 550), (0, 550)])
        smaller_l = _compile([(40, 40), (200, 40), (200, 160), (110, 160), (110, 320), (40, 320)])
        star = _compile([
            (80, 80), (150, 150), (230, 70), (200, 170),
            (280, 240), (170, 220), (120, 310), (110, 190),
        ])
        for result in (hexagon, one_edge, two_edges, three_edges, smaller_l, star):
            self.assertEqual(result["status"], "ready", result.get("code"))
            self.assertEqual(result["geometry"]["reservation"], "blank")
        self.assertEqual(four_edges["status"], "ready")
        self.assertNotIn("reservation", four_edges["geometry"])

        partial = _compile([(50, 100), (400, 100), (400, 400), (50, 400)])
        outside = _compile([(400, 600), (500, 600), (500, 700), (400, 700)])
        self.assertEqual(partial["code"], "outside_blank")
        self.assertEqual(outside["code"], "outside_blank")
        open_path = _ring([(50, 100), (250, 100), (250, 400)])
        open_path["closed"] = False
        open_path["segments"] = open_path["segments"][:-1]
        opened = compile_manufacturing_geometry(
            _doc([open_path], width=BLANK_W, length=BLANK_H),
            blank_width_mm=BLANK_W,
            blank_length_mm=BLANK_H,
        )
        self.assertEqual(opened["code"], "path_open")
        bowtie = _compile([(40, 40), (220, 220), (220, 40), (40, 220)])
        self.assertEqual(bowtie["code"], "self_intersection")

    def test_old_polygon_without_reservation_still_requires_four_edges(self):
        historical = {
            "version": 1,
            "kind": "polygon",
            "units": "cm",
            "template": "custom",
            "blank_width_cm": 33,
            "blank_length_cm": 55,
            "points": [[5, 10], [25, 10], [25, 40], [5, 40]],
            "exact": True,
        }
        piece = {
            "piece_type": "Special",
            "x": 0,
            "y": 0,
            "w": 33,
            "h": 55,
            "original_w": 33,
            "original_h": 55,
            "special_shape_geometry_json": json.dumps(historical),
        }
        self.assertIsNone(material_outline_cm(piece))

    def test_placement_keeps_the_offset_and_reserves_the_blank(self):
        compiled = _compile([(50, 100), (250, 100), (250, 400), (50, 400)])
        piece = projection_piece("A", 1, 100, 20, 330, 550, piece_type="Special")
        pieces = [piece]
        source = source_snapshot(pieces)
        source["sheets"][0]["pieces"][0]["piece_type"] = "Special"
        source["sheets"][0]["pieces"][0]["unit_price"] = 1250
        source["sheets"][0]["pieces"][0]["w"] = 33
        source["sheets"][0]["pieces"][0]["h"] = 55
        source_before = copy.deepcopy(source)
        adopted = {"A": json.dumps(compiled["geometry"], sort_keys=True)}
        snapshot = materialize_plan_snapshot(
            draft=draft_payload(layout_rows(pieces)),
            projection=projection_with_adopted_geometry(projection(pieces), source, adopted),
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
            adopted_geometry=adopted,
        )
        self.assertEqual(source, source_before)
        saved = snapshot["sheets"][0]["pieces"][0]
        stored = json.loads(saved["special_shape_geometry_json"])
        self.assertEqual(stored["points"][0], [5.0, 10.0])
        self.assertEqual(saved["w"], 33)
        self.assertEqual(saved["h"], 55)
        self.assertEqual(saved["original_w"], 33)
        self.assertEqual(saved["original_h"], 55)
        self.assertEqual(saved["unit_price"], 1250)
        self.assertAlmostEqual(saved["area_m2"], 0.33 * 0.55)
        placed = material_outline_cm(saved)
        self.assertTrue(any(_near(point, (15.0, 12.0)) for point in placed))
        self.assertFalse(any(_near(point, (10.0, 2.0)) for point in placed))
        occupancy = occupancy_outline_cm(saved)
        self.assertTrue(any(_near(point, (10.0, 2.0)) for point in occupancy))
        self.assertTrue(any(_near(point, (43.0, 57.0)) for point in occupancy))
        gap = ((10.0, 2.0), (14.0, 2.0), (14.0, 6.0), (10.0, 6.0))
        self.assertTrue(polygons_overlap(occupancy, gap))
        self.assertFalse(polygons_overlap(placed, gap))

    def test_rotation_and_flip_use_the_blank_center(self):
        contour = [[50, 100], [250, 100], [250, 400], [50, 400]]
        blank = [[0, 0], [330, 0], [330, 550], [0, 550]]
        piece = {
            "reserves_blank": True,
            "outline_mm": [list(point) for point in contour],
            "base_outline_mm": [list(point) for point in contour],
            "reservation_mm": [list(point) for point in blank],
            "base_reservation_mm": [list(point) for point in blank],
            "pivot_mm": {"x": 165, "y": 275},
            "rotation_deg": 90,
            "local_x_mm": 0,
            "local_y_mm": 0,
        }
        rederive_outline(piece)
        expected = rotate_point([50, 100], {"x": 165, "y": 275}, 90)
        self.assertTrue(any(_near(point, expected, 0.01) for point in piece["outline_mm"]))
        self.assertAlmostEqual(piece["pivot_mm"]["x"], 165)
        self.assertAlmostEqual(piece["pivot_mm"]["y"], 275)
        self.assertAlmostEqual(piece["local_x_mm"], min(point[0] for point in piece["reservation_mm"]))
        self.assertNotAlmostEqual(piece["local_x_mm"], min(point[0] for point in piece["outline_mm"]))

        flipped = {
            "reserves_blank": True,
            "outline_mm": [list(point) for point in contour],
            "base_outline_mm": [list(point) for point in contour],
            "reservation_mm": [list(point) for point in blank],
            "base_reservation_mm": [list(point) for point in blank],
            "pivot_mm": {"x": 165, "y": 275},
            "rotation_deg": 0,
            "local_x_mm": 0,
            "local_y_mm": 0,
            "flip_h": False,
        }
        apply_local_flip_h(flipped)
        self.assertTrue(any(_near(point, (280, 100), 0.01) for point in flipped["outline_mm"]))
        self.assertAlmostEqual(min(point[0] for point in flipped["reservation_mm"]), 0)
        self.assertAlmostEqual(max(point[0] for point in flipped["reservation_mm"]), 330)

    def test_dxf_uses_the_offset_contour_and_one_kerf(self):
        compiled = _compile([(50, 100), (250, 100), (250, 400), (50, 400)])
        piece = projection_piece("A", 1, 0, 0, 330, 550, piece_type="Special")
        pieces = [piece]
        source = source_snapshot(pieces)
        source["sheets"][0]["pieces"][0]["piece_type"] = "Special"
        adopted = {"A": json.dumps(compiled["geometry"], sort_keys=True)}
        snapshot = materialize_plan_snapshot(
            draft=draft_payload(layout_rows(pieces)),
            projection=projection_with_adopted_geometry(projection(pieces), source, adopted),
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
            adopted_geometry=adopted,
        )
        saved = snapshot["sheets"][0]["pieces"][0]
        placed = material_outline_cm(saved)
        outer_mm = tuple((point[0] * 10.0, point[1] * 10.0) for point in placed)
        self.assertTrue(any(_near(point, (50, 100)) for point in outer_mm))
        self.assertFalse(any(_near(point, (0, 0)) for point in outer_mm))
        self.assertFalse(any(_near(point, (330, 550)) for point in outer_mm))
        centers = cutter_center_paths([(outer_mm, ())], KERF_MM / 2.0)
        document = ezdxf.new("R2010")
        model = document.modelspace()
        model.add_lwpolyline(outer_mm, close=True, dxfattribs={"layer": "OUTER"})
        for path in centers:
            model.add_lwpolyline(path.points, close=path.closed, dxfattribs={"layer": "CUT_PATH"})
        stream = io.StringIO()
        document.write(stream)
        read = read_dxf_geometry_bytes(stream.getvalue().encode("utf-8"))
        layers = {segment["layer"] for segment in read["segments"]}
        self.assertIn("OUTER", layers)
        self.assertIn("CUT_PATH", layers)
        outer_points = []
        for segment in read["segments"]:
            if segment["layer"] != "OUTER":
                continue
            for key in ("start", "end"):
                point = (float(segment[key][0]), float(segment[key][1]))
                if not any(_near(point, existing) for existing in outer_points):
                    outer_points.append(point)
        self.assertEqual(len(outer_points), 4)
        top = []
        for segment in read["segments"]:
            if segment["layer"] != "CUT_PATH":
                continue
            for key in ("start", "end"):
                point = (float(segment[key][0]), float(segment[key][1]))
                if 40 <= point[0] <= 260 and 80 <= point[1] <= 120:
                    top.append(point)
        self.assertTrue(top)
        nearest = min(abs(point[1] - 100.0) for point in top)
        self.assertGreater(nearest, 1.0)
        self.assertLess(nearest, KERF_MM - 0.5)
