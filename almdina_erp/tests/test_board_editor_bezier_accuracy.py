"""Bézier manufacturing curves must stay within 0.05 mm of the cubic."""

from __future__ import annotations

import copy
import io
import json
import math
import subprocess
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
from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import cutter_center_paths
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry_bytes
from almdina_erp.tests.test_board_editor_drawing_compile import _doc
from almdina_erp.tests.test_board_editor_plan_materialize import (
    draft_payload,
    layout_rows,
    projection,
    projection_piece,
    source_snapshot,
)


S_CURVE = ((0.0, 0.0), (30.0, 0.0), (70.0, 100.0), (100.0, 100.0))
KERF_MM = 4.0


def _bezier(p0, c1, c2, p3, t):
    u = 1.0 - t
    return (
        u ** 3 * p0[0] + 3 * u ** 2 * t * c1[0] + 3 * u * t ** 2 * c2[0] + t ** 3 * p3[0],
        u ** 3 * p0[1] + 3 * u ** 2 * t * c1[1] + 3 * u * t ** 2 * c2[1] + t ** 3 * p3[1],
    )


def _distance_to_segment(point, start, end):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length2 = dx * dx + dy * dy
    if length2 <= 1e-18:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2
    ratio = min(1.0, max(0.0, ratio))
    return math.hypot(point[0] - (start[0] + ratio * dx), point[1] - (start[1] + ratio * dy))


def _polyline_deviation_mm(curve, polygon_cm, samples=4000):
    polygon = [(point[0] * 10.0, point[1] * 10.0) for point in polygon_cm]
    worst = 0.0
    for index in range(samples + 1):
        point = _bezier(*curve, index / samples)
        distance = min(
            _distance_to_segment(point, polygon[i], polygon[i + 1])
            for i in range(len(polygon) - 1)
        )
        worst = max(worst, distance)
    return worst


def _closed(nodes, segments, path_id="path-1"):
    return {
        "id": path_id,
        "role": "manufacturing_outer",
        "closed": True,
        "source_shape_id": None,
        "nodes": [
            {"id": node_id, "x_mm": x, "y_mm": y}
            for node_id, x, y in nodes
        ],
        "segments": segments,
    }


def _line(segment_id, start, end):
    return {"id": segment_id, "kind": "line", "from_node": start, "to_node": end}


def _cubic(segment_id, start, end, c1, c2):
    return {
        "id": segment_id,
        "kind": "bezier",
        "from_node": start,
        "to_node": end,
        "controls": [{"x_mm": c1[0], "y_mm": c1[1]}, {"x_mm": c2[0], "y_mm": c2[1]}],
    }


def _compile(path, width, length):
    return compile_manufacturing_geometry(
        _doc([path], width=width, length=length),
        blank_width_mm=width,
        blank_length_mm=length,
    )


class BezierManufacturingAccuracyTests(unittest.TestCase):
    def test_s_curve_is_subdivided_and_stays_within_tolerance(self):
        # The previous midpoint test accepted this cubic as one chord. B(0.5)
        # lies on the chord, while B(0.25) is 5.966 mm away.
        midpoint = _bezier(*S_CURVE, 0.5)
        self.assertLess(_distance_to_segment(midpoint, S_CURVE[0], S_CURVE[3]), 1e-9)
        self.assertGreater(_distance_to_segment(_bezier(*S_CURVE, 0.25), S_CURVE[0], S_CURVE[3]), 5.9)
        path = _closed(
            [("n1", 20, 20), ("n2", 120, 120), ("n3", 180, 20)],
            [
                _cubic("s1", "n1", "n2", (50, 20), (90, 120)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n1"),
            ],
        )
        result = _compile(path, 220, 180)
        self.assertEqual(result["status"], "ready", result.get("code"))
        points = result["geometry"]["points"]
        self.assertGreater(len(points), 2)
        self.assertLessEqual(len(points), 64)
        self.assertEqual(points[0], [2.0, 2.0])
        self.assertIn([12.0, 12.0], points)
        curve = ((20, 20), (50, 20), (90, 120), (120, 120))
        self.assertLess(_polyline_deviation_mm(curve, points), 0.05)
        self.assertGreater(_distance_to_segment(_bezier(*curve, 0.25), (20, 20), (120, 120)), 5.0)

    def test_reversed_s_curve_keeps_direction(self):
        path = _closed(
            [("n1", 120, 120), ("n2", 20, 20), ("n3", 180, 20)],
            [
                _cubic("s1", "n1", "n2", (90, 120), (50, 20)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n1"),
            ],
        )
        result = _compile(path, 220, 180)
        self.assertEqual(result["status"], "ready", result.get("code"))
        points = result["geometry"]["points"]
        self.assertEqual(points[0], [12.0, 12.0])
        curve = ((120, 120), (90, 120), (50, 20), (20, 20))
        self.assertLess(_polyline_deviation_mm(curve, points), 0.05)

    def test_simple_sharp_shallow_and_collinear_curves(self):
        simple = _closed(
            [("n1", 10, 20), ("n2", 110, 20), ("n3", 110, 140), ("n4", 10, 140)],
            [
                _cubic("s1", "n1", "n2", (40, 100), (80, 100)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n4"),
                _line("s4", "n4", "n1"),
            ],
        )
        sharp = _closed(
            [("n1", 10, 20), ("n2", 110, 20), ("n3", 110, 80), ("n4", 10, 80)],
            [
                _cubic("s1", "n1", "n2", (10, 60), (30, 60)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n4"),
                _line("s4", "n4", "n1"),
            ],
        )
        shallow = _closed(
            [("n1", 0, 0), ("n2", 100, 0), ("n3", 100, 40), ("n4", 0, 40)],
            [
                _cubic("s1", "n1", "n2", (40, 0.01), (60, 0.01)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n4"),
                _line("s4", "n4", "n1"),
            ],
        )
        straight = _closed(
            [("n1", 0, 0), ("n2", 100, 0), ("n3", 100, 40), ("n4", 0, 40)],
            [
                _cubic("s1", "n1", "n2", (30, 0), (70, 0)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n4"),
                _line("s4", "n4", "n1"),
            ],
        )
        outside_controls = _closed(
            [
                ("n1", 60, 50), ("n2", 100, 50), ("n3", 150, 80),
                ("n4", 150, 120), ("n5", 10, 120), ("n6", 10, 80),
            ],
            [
                _cubic("s1", "n1", "n2", (30, 48), (130, 48)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n4"),
                _line("s4", "n4", "n5"),
                _line("s5", "n5", "n6"),
                _line("s6", "n6", "n1"),
            ],
        )
        for path, curve, width, length in (
            (simple, ((10, 20), (40, 100), (80, 100), (110, 20)), 160, 160),
            (sharp, ((10, 20), (10, 60), (30, 60), (110, 20)), 160, 120),
            (shallow, ((0, 0), (40, 0.01), (60, 0.01), (100, 0)), 120, 60),
            (straight, ((0, 0), (30, 0), (70, 0), (100, 0)), 120, 60),
            (outside_controls, ((60, 50), (30, 48), (130, 48), (100, 50)), 180, 140),
        ):
            result = _compile(path, width, length)
            self.assertEqual(result["status"], "ready", result.get("code"))
            self.assertLessEqual(len(result["geometry"]["points"]), 64)
            self.assertLess(_polyline_deviation_mm(curve, result["geometry"]["points"]), 0.05)

    def test_two_cubics_in_one_closed_outline(self):
        path = _closed(
            [("n1", 20, 40), ("n2", 140, 40), ("n3", 140, 100), ("n4", 20, 100)],
            [
                _cubic("s1", "n1", "n2", (50, 48), (110, 48)),
                _line("s2", "n2", "n3"),
                _cubic("s3", "n3", "n4", (110, 92), (50, 92)),
                _line("s4", "n4", "n1"),
            ],
        )
        result = _compile(path, 180, 140)
        self.assertEqual(result["status"], "ready", result.get("code"))
        points = result["geometry"]["points"]
        self.assertLessEqual(len(points), 64)
        self.assertLess(
            _polyline_deviation_mm(((20, 40), (50, 48), (110, 48), (140, 40)), points),
            0.05,
        )
        self.assertLess(
            _polyline_deviation_mm(((140, 100), (110, 92), (50, 92), (20, 100)), points),
            0.05,
        )

    def test_curve_that_leaves_the_blank_between_its_endpoints_is_rejected(self):
        path = _closed(
            [("n1", 10, 30), ("n2", 90, 30), ("n3", 90, 10), ("n4", 10, 10)],
            [
                _cubic("s1", "n1", "n2", (30, 180), (70, 180)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n4"),
                _line("s4", "n4", "n1"),
            ],
        )
        result = _compile(path, 100, 80)
        self.assertEqual(result["code"], "outside_blank")

    def test_self_intersecting_cubic_outline_is_rejected(self):
        path = _closed(
            [("n1", 20, 20), ("n2", 80, 20), ("n3", 80, 60), ("n4", 20, 60)],
            [
                _cubic("s1", "n1", "n2", (90, 90), (10, 90)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n4"),
                _line("s4", "n4", "n1"),
            ],
        )
        result = _compile(path, 200, 200)
        self.assertEqual(result["code"], "self_intersection")

    def test_outline_that_needs_more_than_64_vertices_is_rejected(self):
        path = _closed(
            [("n1", 0, 0), ("n2", 8000, 0), ("n3", 8000, 8000), ("n4", 0, 8000)],
            [
                _cubic("s1", "n1", "n2", (0, 8000), (8000, 8000)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n4"),
                _line("s4", "n4", "n1"),
            ],
        )
        result = _compile(path, 9000, 9000)
        self.assertEqual(result["code"], "curve_unrepresentable")

    def test_tiny_curve_does_not_invent_error(self):
        path = _closed(
            [("n1", 10, 10), ("n2", 80, 10), ("n3", 80, 40), ("n4", 10, 40)],
            [
                _cubic("s1", "n1", "n2", (30, 10.004), (50, 10.003)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n4"),
                _line("s4", "n4", "n1"),
            ],
        )
        result = _compile(path, 100, 60)
        self.assertEqual(result["status"], "ready", result.get("code"))
        self.assertLess(
            _polyline_deviation_mm(((10, 10), (30, 10.004), (50, 10.003), (80, 10)), result["geometry"]["points"]),
            0.05,
        )

    def test_javascript_compiler_matches_python_points(self):
        path = _closed(
            [("n1", 20, 20), ("n2", 120, 120), ("n3", 180, 20)],
            [
                _cubic("s1", "n1", "n2", (50, 20), (90, 120)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n1"),
            ],
        )
        python_points = _compile(path, 220, 180)["geometry"]["points"]
        script = r"""
const fs = require("node:fs");
const vm = require("node:vm");
const context = { console, __: (message) => message };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync("almdina_erp/public/js/board_editor/drawing_compile.js", "utf8"), context);
const compiled = context.AlmdinaBoardEditor.DrawingCompile.compile(%s, 220, 180);
process.stdout.write(JSON.stringify(compiled.geometry.points));
""" % json.dumps(_doc([path], width=220, length=180))
        completed = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(json.loads(completed.stdout), python_points)

    def test_closed_s_curve_reaches_dxf_without_changing_the_source_plan(self):
        path = _closed(
            [("n1", 40, 80), ("n2", 140, 180), ("n3", 240, 180), ("n4", 240, 60), ("n5", 40, 60)],
            [
                _cubic("s1", "n1", "n2", (70, 80), (110, 180)),
                _line("s2", "n2", "n3"),
                _line("s3", "n3", "n4"),
                _line("s4", "n4", "n5"),
                _line("s5", "n5", "n1"),
            ],
        )
        document = _doc([path], width=330, length=550)
        before = copy.deepcopy(document)
        compiled = compile_manufacturing_geometry(document, blank_width_mm=330, blank_length_mm=550)
        self.assertEqual(compiled["status"], "ready", compiled.get("code"))
        self.assertEqual(document, before)
        self.assertEqual(document["paths"][0]["segments"][0]["kind"], "bezier")
        self.assertEqual(document["paths"][0]["segments"][0]["controls"][0]["x_mm"], 70)
        curve = ((40, 80), (70, 80), (110, 180), (140, 180))
        self.assertLess(_polyline_deviation_mm(curve, compiled["geometry"]["points"]), 0.05)
        piece = projection_piece("A", 1, 15, 25, 330, 550, piece_type="Special")
        pieces = [piece]
        source = source_snapshot(pieces)
        source["sheets"][0]["pieces"][0]["piece_type"] = "Special"
        source["sheets"][0]["pieces"][0]["unit_price"] = 890
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
        self.assertEqual(stored["points"][0], [4.0, 8.0])
        self.assertEqual(saved["w"], 33)
        self.assertEqual(saved["h"], 55)
        self.assertEqual(saved["unit_price"], 890)
        self.assertAlmostEqual(saved["area_m2"], 0.33 * 0.55)
        placed = material_outline_cm(saved)
        self.assertTrue(any(math.dist(point, (5.5, 10.5)) < 0.05 for point in placed))
        outer_mm = tuple((point[0] * 10.0, point[1] * 10.0) for point in placed)
        centers = cutter_center_paths([(outer_mm, ())], KERF_MM / 2.0)
        dxf = ezdxf.new("R2010")
        model = dxf.modelspace()
        model.add_lwpolyline(outer_mm, close=True, dxfattribs={"layer": "OUTER"})
        for toolpath in centers:
            model.add_lwpolyline(toolpath.points, close=toolpath.closed, dxfattribs={"layer": "CUT_PATH"})
        stream = io.StringIO()
        dxf.write(stream)
        read = read_dxf_geometry_bytes(stream.getvalue().encode("utf-8"))
        layers = {segment["layer"] for segment in read["segments"]}
        self.assertIn("OUTER", layers)
        self.assertIn("CUT_PATH", layers)
        self.assertTrue(any(
            abs(float(segment["start"][0]) - 55) < 1 and abs(float(segment["start"][1]) - 105) < 1
            for segment in read["segments"]
            if segment["layer"] == "OUTER"
        ))
        offsets = []
        for segment in read["segments"]:
            if segment["layer"] != "CUT_PATH":
                continue
            start = (float(segment["start"][0]), float(segment["start"][1]))
            end = (float(segment["end"][0]), float(segment["end"][1]))
            low_x, high_x = sorted((start[0], end[0]))
            if abs(start[1] - end[1]) <= 0.2 and low_x <= 120 <= high_x and 70 <= start[1] <= 100:
                offsets.append(abs(start[1] - 85))
        self.assertEqual(offsets, [KERF_MM / 2.0])
