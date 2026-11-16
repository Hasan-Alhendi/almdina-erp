"""DXF and saw-center round trip for a Drawing Mode outline.

This runs the same compile, snapshot, DXF reader, and cutter-center functions
the export path uses. It does not open a Frappe site or approve a production plan.
"""

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
from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import cutter_center_paths
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry_bytes
from almdina_erp.tests.test_board_editor_drawing_compile import _doc, _ring
from almdina_erp.tests.test_board_editor_plan_materialize import (
    draft_payload,
    layout_rows,
    projection,
    projection_piece,
    source_snapshot,
)


OUTER = (
    (0, 200),
    (200, 0),
    (400, 0),
    (600, 200),
    (600, 700),
    (400, 900),
    (200, 900),
    (0, 700),
)
KERF_MM = 4.0


def _near(point, expected, tolerance=0.05):
    return math.dist(point, expected) <= tolerance


class DrawingManufacturingRoundtripTests(unittest.TestCase):
    def test_saved_outline_roundtrips_through_dxf_and_one_kerf_offset(self):
        guide = _ring([(40, 40), (80, 40), (80, 80)], path_id="guide", role="construction")
        document = _doc(
            [_ring(OUTER), guide],
            width=600,
            length=900,
            references=[{
                "id": "ref-1",
                "file_id": "FILE-PRIVATE-1",
                "x_mm": 10,
                "y_mm": 10,
                "width_mm": 100,
                "height_mm": 80,
                "rotation_deg": 0,
                "opacity": 0.4,
                "locked": True,
                "hidden": False,
                "calibration": None,
            }],
        )
        before = copy.deepcopy(document)
        compiled = compile_manufacturing_geometry(document, blank_width_mm=600, blank_length_mm=900)
        self.assertEqual(compiled["status"], "ready", compiled.get("code"))
        self.assertEqual(document, before)
        geometry = json.loads(json.dumps(compiled["geometry"]))
        self.assertEqual(len(geometry["points"]), 8)
        self.assertNotIn([0.0, 0.0], geometry["points"])
        self.assertNotIn("references", geometry)
        self.assertNotIn("FILE-PRIVATE-1", json.dumps(geometry))
        self.assertNotIn([4.0, 4.0], geometry["points"])

        piece = projection_piece("A", 1, 0, 0, 600, 900, piece_type="Special")
        pieces = [piece]
        source = source_snapshot(pieces)
        source["sheets"][0]["pieces"][0]["piece_type"] = "Special"
        source_before = copy.deepcopy(source)
        adopted = {"A": json.dumps(geometry, sort_keys=True)}
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
        restored = json.loads(json.dumps(snapshot))
        stored = json.loads(restored["sheets"][0]["pieces"][0]["special_shape_geometry_json"])
        self.assertEqual(stored["points"], geometry["points"])
        placed = material_outline_cm(restored["sheets"][0]["pieces"][0])
        self.assertEqual([list(point) for point in placed], geometry["points"])

        outer_mm = tuple((point[0] * 10.0, point[1] * 10.0) for point in stored["points"])
        centers = cutter_center_paths([(outer_mm, ())], KERF_MM / 2.0)
        self.assertTrue(centers)
        document_dxf = ezdxf.new("R2010")
        model = document_dxf.modelspace()
        model.add_lwpolyline(outer_mm, close=True, dxfattribs={"layer": "OUTER"})
        for path in centers:
            model.add_lwpolyline(path.points, close=path.closed, dxfattribs={"layer": "CUT_PATH"})
        stream = io.StringIO()
        document_dxf.write(stream)
        read = read_dxf_geometry_bytes(stream.getvalue().encode("utf-8"))
        layers = {segment["layer"] for segment in read["segments"]}
        self.assertIn("OUTER", layers)
        self.assertIn("CUT_PATH", layers)
        self.assertFalse(any("GUIDE" in layer or "IMAGE" in layer or "REF" in layer for layer in layers))

        outer_points = []
        for segment in read["segments"]:
            if segment["layer"] != "OUTER":
                continue
            for key in ("start", "end"):
                point = (float(segment[key][0]), float(segment[key][1]))
                if not any(_near(point, existing) for existing in outer_points):
                    outer_points.append(point)
        self.assertEqual(len(outer_points), 8)
        for expected in outer_mm:
            self.assertTrue(any(_near(point, expected) for point in outer_points), expected)
        self.assertFalse(any(_near(point, (0.0, 0.0)) for point in outer_points))

        top_centers = []
        for segment in read["segments"]:
            if segment["layer"] != "CUT_PATH":
                continue
            for key in ("start", "end"):
                point = (float(segment[key][0]), float(segment[key][1]))
                if 180.0 <= point[0] <= 420.0 and abs(point[1]) < 20.0:
                    top_centers.append(point)
        self.assertTrue(top_centers)
        closest = min(abs(point[1]) for point in top_centers)
        self.assertAlmostEqual(closest, KERF_MM / 2.0, delta=0.2)
        self.assertGreater(closest, 1.0)
        self.assertLess(closest, KERF_MM - 0.5)
