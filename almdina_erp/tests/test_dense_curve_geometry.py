"""Dense sampled curves survive manufacturing simplification and DXF import.

The original fixtures use 128 LINE segments for each curved opening. Those
vertices are locally almost collinear, and must not be deleted together.
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cnc.operational_file import catalog_sheet
from almdina_erp.almdina_erp.domain.cutting.cutter_center_paths import (
    cutter_center_paths,
    internal_center_ring,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    assemble_contours,
    is_axis_aligned_rectangle,
    point_to_polygon_distance,
    polygon_area,
    simplify_polygon,
    validate_polygon,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import CUT_INVALID_GEOMETRY
from almdina_erp.almdina_erp.presentation.cutting.dxf_error_presenter import present_issue
from almdina_erp.almdina_erp.services import dxf_import_service
from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dense_curve_dxf"
TOLERANCE = 0.25


def _circle(cx, cy, radius, count):
    return [
        (
            cx + radius * math.cos(2 * math.pi * index / count),
            cy + radius * math.sin(2 * math.pi * index / count),
        )
        for index in range(count)
    ]


def _ellipse(cx, cy, rx, ry, count):
    return [
        (
            cx + rx * math.cos(2 * math.pi * index / count),
            cy + ry * math.sin(2 * math.pi * index / count),
        )
        for index in range(count)
    ]


def _rect(x, y, width, height):
    return [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]


def _deviation(source, simplified):
    return max(point_to_polygon_distance(point, simplified) for point in source)


def _rotate(points, start):
    return points[start:] + points[:start]


class DenseCurveSimplificationTest(unittest.TestCase):
    def test_sampled_curves_keep_their_shape(self):
        samples = {
            16: _circle(0, 0, 100, 16),
            32: _circle(0, 0, 100, 32),
            64: _circle(0, 0, 100, 64),
            128: _circle(0, 0, 100, 128),
            256: _circle(0, 0, 80, 256),
            512: _circle(0, 0, 60, 512),
        }
        for count, ring in samples.items():
            with self.subTest(vertices=count):
                simplified = simplify_polygon(ring, TOLERANCE)
                self.assertGreaterEqual(len(simplified), 8)
                self.assertLessEqual(_deviation(ring, simplified), TOLERANCE + 1e-6)
                self.assertLess(abs(polygon_area(simplified) - polygon_area(ring)) / polygon_area(ring), 0.02)
                self.assertFalse(validate_polygon(simplified, TOLERANCE))

        ellipse = _ellipse(0, 0, 85, 50, 128)
        simplified_ellipse = simplify_polygon(ellipse, TOLERANCE)
        self.assertGreaterEqual(len(simplified_ellipse), 8)
        self.assertLessEqual(_deviation(ellipse, simplified_ellipse), TOLERANCE + 1e-6)

        outer = [
            (0, 0), (500, 0), (500, 500), (360, 700), (140, 700), (0, 500),
        ]
        dense_outer = []
        for start, end in zip(outer, outer[1:] + outer[:1]):
            for step in range(32):
                blend = step / 32
                dense_outer.append((
                    start[0] + (end[0] - start[0]) * blend,
                    start[1] + (end[1] - start[1]) * blend,
                ))
        simplified_outer = simplify_polygon(dense_outer, TOLERANCE)
        self.assertEqual(len(simplified_outer), 6)
        self.assertLessEqual(_deviation(dense_outer, simplified_outer), TOLERANCE + 1e-6)
        self.assertFalse(is_axis_aligned_rectangle(simplified_outer, TOLERANCE))

    def test_collinear_duplicates_and_ring_orientation(self):
        rectangle = _rect(0, 0, 500, 700)
        with_midpoints = []
        for start, end in zip(rectangle, rectangle[1:] + rectangle[:1]):
            with_midpoints.append(start)
            with_midpoints.append(((start[0] + end[0]) / 2, (start[1] + end[1]) / 2))
        simplified = simplify_polygon(with_midpoints, TOLERANCE)
        self.assertEqual(len(simplified), 4)
        self.assertTrue(is_axis_aligned_rectangle(simplified, TOLERANCE))

        duplicated = []
        for point in rectangle:
            duplicated.extend((point, point))
        self.assertEqual(len(simplify_polygon(duplicated, TOLERANCE)), 4)

        circle = _circle(200, 300, 100, 128)
        forward = simplify_polygon(circle, TOLERANCE)
        reversed_ring = simplify_polygon(list(reversed(circle)), TOLERANCE)
        shifted = simplify_polygon(_rotate(circle, 17), TOLERANCE)
        self.assertEqual(len(forward), len(reversed_ring))
        self.assertEqual(len(forward), len(shifted))
        self.assertLessEqual(_deviation(circle, shifted), TOLERANCE + 1e-6)
        self.assertGreater(polygon_area(forward), 0)

    def test_invalid_openings_remain_invalid(self):
        bow_tie = [(0, 0), (100, 100), (0, 100), (100, 0)]
        self.assertIn("self_intersection", validate_polygon(bow_tie, TOLERANCE))

        outer = _rect(0, 0, 500, 700)
        tiny = _circle(250, 350, 2, 128)
        center = internal_center_ring(outer, tiny, 2.5)
        self.assertTrue(center is None or point_to_polygon_distance(center[0], tiny) < 2.5)


class DenseCurveFixtureImportTest(unittest.TestCase):
    def setUp(self):
        self.paths = []

    def tearDown(self):
        for path in self.paths:
            Path(path).unlink(missing_ok=True)

    def _order(self, pieces):
        return SimpleNamespace(
            trim_margin_mm=0,
            board_width_cm=122,
            board_length_cm=244,
            full_board_width_mm=1220,
            full_board_length_mm=2440,
            kerf_mm=5,
            pieces=pieces,
        )

    def _piece(self, **overrides):
        values = {
            "cut_width_cm": 50,
            "cut_length_cm": 70,
            "width_cm": 50,
            "length_cm": 70,
            "qty": 1,
            "piece_type": "Special",
            "extra_liner": 0,
            "extra_back_groove": 0,
            "extra_full_door_double": 0,
            "extra_recessed_handle_cutout": 0,
            "extra_double": 0,
            "allow_rotation": 0,
            "liner_reference_side": "",
            "liner_offset_cm": 0,
            "liner_width_cm": 0,
            "glass_margin_mm": None,
            "deduct_edge_thickness": False,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def _parse(self, path, order):
        with patch.object(dxf_import_service.frappe, "get_site_path", return_value=str(path)):
            return dxf_import_service.parse_production_dxf("/private/files/fixture.dxf", order)

    def _lines(self, msp, polygon, layer):
        corners = list(polygon)
        for start, end in zip(corners, corners[1:] + corners[:1]):
            msp.add_line(start, end, dxfattribs={"layer": layer})

    def _geometry_rings(self, path):
        document = ezdxf.readfile(path)
        segments = [
            ((entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y))
            for entity in document.modelspace()
            if entity.dxftype() == "LINE" and str(entity.dxf.layer).upper() == "GEOMETRY"
        ]
        rings = []
        for contour in assemble_contours(segments, 1.5):
            points = list(contour.get("points") or [])
            if points and points[0] == points[-1]:
                points = points[:-1]
            rings.append(points)
        return rings

    def _assert_openings_manufacturable(self, piece):
        geometry = piece["geometry"]
        outer = [tuple(point) for point in geometry["outer"]]
        holes = [[tuple(point) for point in hole] for hole in geometry["holes"]]
        self.assertGreaterEqual(len(outer), 3)
        paths = cutter_center_paths([(outer, holes)], 2.5)
        self.assertEqual(sum(path.closed for path in paths), len(holes) + 1)
        for hole in holes:
            center = internal_center_ring(outer, hole, 2.5)
            self.assertIsNotNone(center)
            self.assertFalse(validate_polygon(center, TOLERANCE))
            self.assertGreaterEqual(
                min(point_to_polygon_distance(point, hole) for point in center),
                2.5 - TOLERANCE,
            )
        catalog = catalog_sheet(1, [{
            "piece_instance_id": "pi-special",
            "sheet_no": 1,
            "extra_liner": 0,
            "extra_back_groove": 0,
            "extra_recessed_handle_cutout": 0,
            "geometry": geometry,
        }])
        cut_keys = [path.path_key for path in catalog.paths if ":hole:" in path.path_key or path.path_key.endswith(":outer")]
        self.assertEqual(sum(":hole:" in key for key in cut_keys), len(holes))

    def _reimport_geometry(self, piece):
        document = ezdxf.new("R2010")
        model = document.modelspace()
        self._lines(model, [(0, 0), (1220, 0), (1220, 2440), (0, 2440)], "SHEET_OUTLINE")

        def dxf_ring(points):
            # Plan millimetres use a downward Y axis on a 2440 mm sheet.
            return [(point[0], 2440 - point[1]) for point in points]

        self._lines(model, dxf_ring(piece["geometry"]["outer"]), "GEOMETRY")
        for hole in piece["geometry"]["holes"]:
            self._lines(model, dxf_ring(hole), "GEOMETRY")
        handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
        handle.close()
        document.saveas(handle.name)
        self.paths.append(handle.name)
        return self._parse(handle.name, self._order([self._piece()]))

    def test_original_fixtures_import_and_round_trip(self):
        expected_holes = {
            "03_special_circle.dxf": 1,
            "05_special_multiple.dxf": 3,
            "07_special_trapezoid_holes.dxf": 2,
        }
        for name, hole_count in expected_holes.items():
            with self.subTest(fixture=name):
                path = FIXTURES / name
                raw_rings = self._geometry_rings(path)
                raw_holes = [ring for ring in raw_rings if len(ring) >= 128]
                self.assertGreaterEqual(len(raw_holes), 1)
                for ring in raw_holes:
                    simplified = simplify_polygon(ring, TOLERANCE)
                    self.assertGreaterEqual(len(simplified), 8)
                    self.assertLessEqual(_deviation(ring, simplified), TOLERANCE + 1e-6)
                snapshot = self._parse(path, self._order([self._piece()]))
                piece = snapshot["sheets"][0]["pieces"][0]
                self.assertEqual(piece["piece_type"], "Special")
                self.assertEqual(len(piece["geometry"]["holes"]), hole_count)
                for hole in piece["geometry"]["holes"]:
                    self.assertGreaterEqual(len(hole), 4)
                self._assert_openings_manufacturable(piece)
                again = self._reimport_geometry(piece)
                reimported = again["sheets"][0]["pieces"][0]
                self.assertEqual(len(reimported["geometry"]["holes"]), hole_count)

    def test_rectangle_and_plain_trapezoid_fixtures_still_import(self):
        rectangle = self._parse(
            FIXTURES / "04_special_offset_rectangle.dxf",
            self._order([self._piece()]),
        )["sheets"][0]["pieces"][0]
        self.assertEqual(len(rectangle["geometry"]["holes"]), 1)
        self.assertGreaterEqual(len(rectangle["geometry"]["outer"]), 4)

        trapezoid = self._parse(
            FIXTURES / "06_special_trapezoid.dxf",
            self._order([self._piece()]),
        )["sheets"][0]["pieces"][0]
        self.assertEqual(trapezoid["geometry"]["holes"], [])
        self.assertGreaterEqual(len(trapezoid["geometry"]["outer"]), 4)

    def test_mixed_order_keeps_the_original_128_vertex_circle(self):
        # The reviewed site has no separate mixed-order file named fixture 15.
        # This order uses the unchanged 128-vertex circle from fixture 03.
        rings = self._geometry_rings(FIXTURES / "03_special_circle.dxf")
        circle = next(ring for ring in rings if len(ring) == 128)
        self.assertEqual(len(circle), 128)
        document = ezdxf.new("R2010")
        model = document.modelspace()
        self._lines(model, [(0, 0), (1220, 0), (1220, 2440), (0, 2440)], "SHEET_OUTLINE")
        self._lines(model, [(100, 100), (600, 100), (600, 800), (100, 800)], "GEOMETRY")
        self._lines(model, circle, "GEOMETRY")
        self._lines(model, [(700, 100), (1000, 100), (1000, 500), (700, 500)], "GEOMETRY")
        self._lines(model, [(700, 900), (1100, 900), (1100, 1500), (700, 1500)], "GEOMETRY")
        self._lines(model, [(750, 950), (1050, 950), (1050, 1450), (750, 1450)], "GEOMETRY")
        handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
        handle.close()
        document.saveas(handle.name)
        self.paths.append(handle.name)
        snapshot = self._parse(handle.name, self._order([
            self._piece(),
            self._piece(cut_width_cm=30, cut_length_cm=40, width_cm=30, length_cm=40, piece_type="Regular"),
            self._piece(
                cut_width_cm=40,
                cut_length_cm=60,
                width_cm=40,
                length_cm=60,
                piece_type="Glass",
                glass_margin_mm=50,
            ),
        ]))
        pieces = snapshot["sheets"][0]["pieces"]
        by_type = {piece["piece_type"]: piece for piece in pieces}
        self.assertEqual(set(by_type), {"Special", "Regular", "Glass"})
        self.assertEqual(by_type["Regular"]["geometry"]["holes"], [])
        self.assertEqual(len(by_type["Glass"]["geometry"]["holes"]), 1)
        self.assertEqual(len(by_type["Special"]["geometry"]["holes"]), 1)
        self.assertGreaterEqual(len(by_type["Special"]["geometry"]["holes"][0]), 8)

    def test_geometry_layer_invalid_contour_names_its_source(self):
        document = ezdxf.new("R2010")
        model = document.modelspace()
        self._lines(model, [(0, 0), (1220, 0), (1220, 2440), (0, 2440)], "SHEET_OUTLINE")
        self._lines(model, [(100, 100), (350, 100), (600, 100)], "GEOMETRY")
        handle = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
        handle.close()
        document.saveas(handle.name)
        self.paths.append(handle.name)
        with self.assertRaises(DxfImportError) as error:
            self._parse(handle.name, self._order([self._piece()]))
        invalid = next(item for item in error.exception.issues if item.code == CUT_INVALID_GEOMETRY)
        self.assertEqual(invalid.params["outline_layer"], "GEOMETRY")
        self.assertIn("too_few_vertices", invalid.params["geometry_errors"])
        presented = present_issue(invalid)
        self.assertIn("GEOMETRY", presented.problem)
        self.assertIn("GEOMETRY", presented.action)
        self.assertNotIn("CUT_PATH", presented.action)
