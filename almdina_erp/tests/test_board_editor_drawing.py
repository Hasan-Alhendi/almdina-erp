"""Structural contract for Board Editor vector drawings.

These tests do not touch a site, a Cutting Plan, or manufacturing compilation.
"""

from __future__ import annotations

import inspect
import math
import unittest

from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import (
    COORDINATE_SPACE,
    MAX_NODES,
    MAX_NODES_PER_PATH,
    MAX_PATHS,
    ROLE_MANUFACTURING_OUTER,
    SCHEMA,
    UNITS,
    VERSION,
    DrawingDocumentError,
    document_fingerprint,
    document_to_json,
    empty_document,
    geometry_fingerprint,
    normalize_document,
    parse_document,
    path_bounds_mm,
    segment_line_metrics,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    FORBIDDEN_FIELDS,
    TOP_FIELDS,
    DraftLayoutError,
    catalog_from_projection,
    normalize_layout,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    GEOMETRY_COORDINATE_SPACE,
    GEOMETRY_SCHEMA_VERSION,
    GEOMETRY_UNIT,
)
from almdina_erp.almdina_erp.domain.cutting import board_editor_drawing as drawing_module


def _blank_document(**overrides):
    document = {
        "schema": SCHEMA,
        "version": VERSION,
        "units": UNITS,
        "coordinate_space": COORDINATE_SPACE,
        "piece_instance_id": "piece:door-1",
        "blank": {"width_mm": 600, "length_mm": 2100},
        "paths": [],
        "shapes": [],
        "references": [],
    }
    document.update(overrides)
    return document


def _line_path(path_id, role, closed, nodes, segments, source_shape_id=None):
    return {
        "id": path_id,
        "role": role,
        "closed": closed,
        "nodes": [{"id": node_id, "x_mm": x, "y_mm": y} for node_id, x, y in nodes],
        "segments": [
            {"id": segment_id, "kind": "line", "from_node": start, "to_node": end}
            for segment_id, start, end in segments
        ],
        "source_shape_id": source_shape_id,
    }


def _rectangle(**params):
    value = {"x_mm": 0, "y_mm": 0, "width_mm": 600, "height_mm": 400, "rotation_deg": 0}
    value.update(params)
    return {
        "id": "shape-rect",
        "kind": "rectangle",
        "exploded": False,
        "path_id": None,
        "params": value,
    }


def _reference(**overrides):
    value = {
        "id": "ref-1",
        "file_id": "FILE-PRIVATE-1",
        "x_mm": 0,
        "y_mm": 0,
        "width_mm": 600,
        "height_mm": 2100,
        "rotation_deg": 0,
        "opacity": 0.45,
        "locked": True,
        "hidden": False,
        "calibration": {
            "start_mm": {"x_mm": 0, "y_mm": 0},
            "end_mm": {"x_mm": 350, "y_mm": 0},
            "known_distance_mm": 350,
        },
    }
    value.update(overrides)
    return value


class BoardEditorDrawingContractTests(unittest.TestCase):
    def test_empty_document_is_structurally_valid(self):
        document = empty_document("piece:door-1", 600, 2100)
        self.assertEqual(document["schema"], SCHEMA)
        self.assertEqual(document["version"], VERSION)
        self.assertEqual(document["units"], "mm")
        self.assertEqual(document["coordinate_space"], "door_local")
        self.assertEqual(document["piece_instance_id"], "piece:door-1")
        self.assertEqual(document["blank"], {"width_mm": 600.0, "length_mm": 2100.0})
        self.assertEqual(document["paths"], [])
        self.assertEqual(document["shapes"], [])
        self.assertEqual(document["references"], [])

    def test_normalize_serialize_and_parse_preserve_geometry(self):
        raw = _blank_document(
            paths=[
                _line_path(
                    "path-poly",
                    "construction",
                    False,
                    [("n1", 0, 0), ("n2", 350, 0), ("n3", 350, 120)],
                    [("s1", "n1", "n2"), ("s2", "n2", "n3")],
                )
            ]
        )
        normalized = normalize_document(raw)
        restored = parse_document(document_to_json(normalized))
        self.assertEqual(restored, normalized)
        self.assertEqual(
            [(node["id"], node["x_mm"], node["y_mm"]) for node in restored["paths"][0]["nodes"]],
            [("n1", 0.0, 0.0), ("n2", 350.0, 0.0), ("n3", 350.0, 120.0)],
        )
        self.assertEqual(document_to_json(restored), document_to_json(normalized))

    def test_polyline_reuses_one_node_between_segments(self):
        document = normalize_document(
            _blank_document(
                paths=[
                    _line_path(
                        "path-poly",
                        "construction",
                        False,
                        [("n1", 0, 0), ("n2", 350, 0), ("n3", 350, 80)],
                        [("s1", "n1", "n2"), ("s2", "n2", "n3")],
                    )
                ]
            )
        )
        path = document["paths"][0]
        node_ids = [node["id"] for node in path["nodes"]]
        self.assertEqual(node_ids.count("n2"), 1)
        self.assertEqual(path["segments"][0]["to_node"], "n2")
        self.assertEqual(path["segments"][1]["from_node"], "n2")

    def test_horizontal_line_length_is_350_mm(self):
        document = _blank_document(
            paths=[
                _line_path(
                    "path-width",
                    "construction",
                    False,
                    [("n1", 0, 0), ("n2", 350, 0)],
                    [("s-width", "n1", "n2")],
                )
            ]
        )
        metrics = segment_line_metrics(document, "path-width", "s-width")
        self.assertEqual(metrics["length_mm"], 350.0)
        self.assertEqual(metrics["angle_deg"], 0.0)

    def test_diagonal_line_length_and_angle_are_derived(self):
        document = _blank_document(
            paths=[
                _line_path(
                    "path-diagonal",
                    "construction",
                    False,
                    [("n1", 0, 0), ("n2", 300, 400)],
                    [("s-diagonal", "n1", "n2")],
                )
            ]
        )
        metrics = segment_line_metrics(document, "path-diagonal", "s-diagonal")
        self.assertAlmostEqual(metrics["length_mm"], 500.0, places=6)
        self.assertAlmostEqual(metrics["angle_deg"], math.degrees(math.atan2(400, 300)), places=6)
        bounds = path_bounds_mm(document, "path-diagonal")
        self.assertEqual(bounds["max_x_mm"], 300.0)
        self.assertEqual(bounds["max_y_mm"], 400.0)

    def test_open_path_is_saved_without_becoming_a_cut_contour(self):
        document = normalize_document(
            _blank_document(
                paths=[
                    _line_path(
                        "path-open",
                        ROLE_MANUFACTURING_OUTER,
                        False,
                        [("n1", 0, 0), ("n2", 350, 0)],
                        [("s1", "n1", "n2")],
                    )
                ]
            )
        )
        self.assertFalse(document["paths"][0]["closed"])
        self.assertEqual(document["paths"][0]["role"], ROLE_MANUFACTURING_OUTER)
        self.assertNotIn("geometry", document)
        self.assertNotIn("special_shape_geometry_json", document)

    def test_closed_chain_is_structurally_valid(self):
        document = normalize_document(
            _blank_document(
                paths=[
                    _line_path(
                        "path-loop",
                        "manufacturing_outer",
                        True,
                        [("n1", 0, 0), ("n2", 100, 0), ("n3", 50, 80)],
                        [("s1", "n1", "n2"), ("s2", "n2", "n3"), ("s3", "n3", "n1")],
                    )
                ]
            )
        )
        path = document["paths"][0]
        self.assertTrue(path["closed"])
        self.assertEqual(path["segments"][-1]["to_node"], path["nodes"][0]["id"])
        self.assertEqual(len(path["nodes"]), 3)

    def test_duplicate_node_id_is_rejected(self):
        path = _line_path(
            "path-dup",
            "construction",
            False,
            [("n1", 0, 0), ("n1", 10, 0)],
            [("s1", "n1", "n1")],
        )
        with self.assertRaises(DrawingDocumentError) as caught:
            normalize_document(_blank_document(paths=[path]))
        self.assertEqual(caught.exception.code, "duplicate_id")

    def test_segment_to_unknown_node_is_rejected(self):
        path = _line_path(
            "path-missing",
            "construction",
            False,
            [("n1", 0, 0), ("n2", 10, 0)],
            [("s1", "n1", "missing")],
        )
        with self.assertRaises(DrawingDocumentError) as caught:
            normalize_document(_blank_document(paths=[path]))
        self.assertEqual(caught.exception.code, "unknown_node")

    def test_inconsistent_closure_is_rejected(self):
        open_marked_closed = _line_path(
            "path-open-as-closed",
            "construction",
            True,
            [("n1", 0, 0), ("n2", 40, 0)],
            [("s1", "n1", "n2")],
        )
        with self.assertRaises(DrawingDocumentError) as closed:
            normalize_document(_blank_document(paths=[open_marked_closed]))
        self.assertEqual(closed.exception.code, "inconsistent_closure")

        loop_marked_open = _line_path(
            "path-loop-as-open",
            "construction",
            False,
            [("n1", 0, 0), ("n2", 40, 0), ("n3", 20, 30)],
            [("s1", "n1", "n2"), ("s2", "n2", "n3"), ("s3", "n3", "n1")],
        )
        with self.assertRaises(DrawingDocumentError) as opened:
            normalize_document(_blank_document(paths=[loop_marked_open]))
        self.assertEqual(opened.exception.code, "inconsistent_closure")

    def test_non_finite_coordinates_are_rejected(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            path = _line_path(
                "path-bad",
                "construction",
                False,
                [("n1", 0, 0), ("n2", bad, 0)],
                [("s1", "n1", "n2")],
            )
            with self.assertRaises(DrawingDocumentError) as caught:
                normalize_document(_blank_document(paths=[path]))
            self.assertEqual(caught.exception.code, "invalid_number")

    def test_bezier_requires_two_controls(self):
        valid = {
            "id": "path-curve",
            "role": "annotation",
            "closed": False,
            "source_shape_id": None,
            "nodes": [
                {"id": "n1", "x_mm": 0, "y_mm": 0},
                {"id": "n2", "x_mm": 100, "y_mm": 0},
            ],
            "segments": [
                {
                    "id": "s-curve",
                    "kind": "bezier",
                    "from_node": "n1",
                    "to_node": "n2",
                    "controls": [
                        {"x_mm": 20, "y_mm": 40},
                        {"x_mm": 80, "y_mm": -10},
                    ],
                }
            ],
        }
        normalized = normalize_document(_blank_document(paths=[valid]))
        self.assertEqual(len(normalized["paths"][0]["segments"][0]["controls"]), 2)
        with self.assertRaises(DrawingDocumentError) as curve_metrics:
            segment_line_metrics(normalized, "path-curve", "s-curve")
        self.assertEqual(curve_metrics.exception.code, "segment_not_line")

        incomplete = {
            **valid,
            "segments": [
                {
                    "id": "s-curve",
                    "kind": "bezier",
                    "from_node": "n1",
                    "to_node": "n2",
                    "controls": [{"x_mm": 20, "y_mm": 40}],
                }
            ],
        }
        with self.assertRaises(DrawingDocumentError) as caught:
            normalize_document(_blank_document(paths=[incomplete]))
        self.assertEqual(caught.exception.code, "curve_incomplete")

    def test_arc_radius_must_span_the_chord(self):
        def arc(radius):
            return {
                "id": "path-arc",
                "role": "construction",
                "closed": False,
                "source_shape_id": None,
                "nodes": [
                    {"id": "n1", "x_mm": 0, "y_mm": 0},
                    {"id": "n2", "x_mm": 100, "y_mm": 0},
                ],
                "segments": [
                    {
                        "id": "s-arc",
                        "kind": "arc",
                        "from_node": "n1",
                        "to_node": "n2",
                        "radius_mm": radius,
                        "large_arc": False,
                        "sweep_clockwise": True,
                    }
                ],
            }

        self.assertEqual(normalize_document(_blank_document(paths=[arc(60)]))["paths"][0]["segments"][0]["kind"], "arc")
        with self.assertRaises(DrawingDocumentError) as caught:
            normalize_document(_blank_document(paths=[arc(40)]))
        self.assertEqual(caught.exception.code, "curve_inconsistent")

    def test_parametric_rectangle_stays_parametric_until_exploded(self):
        document = normalize_document(_blank_document(shapes=[_rectangle()]))
        shape = document["shapes"][0]
        self.assertEqual(shape["kind"], "rectangle")
        self.assertFalse(shape["exploded"])
        self.assertIsNone(shape["path_id"])
        self.assertEqual(shape["params"]["width_mm"], 600.0)
        self.assertEqual(document["paths"], [])

    def test_reference_image_stores_placement_not_bytes(self):
        document = normalize_document(_blank_document(references=[_reference()]))
        reference = document["references"][0]
        self.assertEqual(reference["file_id"], "FILE-PRIVATE-1")
        self.assertEqual(reference["opacity"], 0.45)
        self.assertNotIn("content_base64", reference)
        serialized = document_to_json(document)
        self.assertNotIn("base64", serialized)
        self.assertNotIn("data:image", serialized)

        embedded = _reference(content_base64="aGk=")
        with self.assertRaises(DrawingDocumentError) as caught:
            normalize_document(_blank_document(references=[embedded]))
        self.assertEqual(caught.exception.code, "embedded_image")

    def test_fingerprint_ignores_json_key_order(self):
        first = _blank_document(
            paths=[
                _line_path(
                    "path-width",
                    "construction",
                    False,
                    [("n1", 0, 0), ("n2", 350, 0)],
                    [("s-width", "n1", "n2")],
                )
            ],
            shapes=[_rectangle()],
            references=[_reference()],
        )
        second = {
            "references": first["references"],
            "shapes": first["shapes"],
            "paths": first["paths"],
            "blank": {"length_mm": 2100, "width_mm": 600},
            "piece_instance_id": first["piece_instance_id"],
            "coordinate_space": first["coordinate_space"],
            "units": first["units"],
            "version": first["version"],
            "schema": first["schema"],
        }
        self.assertEqual(document_fingerprint(first), document_fingerprint(second))

    def test_drawing_fingerprint_changes_for_geometry_shape_and_image(self):
        base = _blank_document(
            paths=[
                _line_path(
                    "path-width",
                    "construction",
                    False,
                    [("n1", 0, 0), ("n2", 350, 0)],
                    [("s-width", "n1", "n2")],
                )
            ],
            shapes=[_rectangle()],
            references=[_reference()],
        )
        base_document = document_fingerprint(base)
        base_geometry = geometry_fingerprint(base)

        moved = _blank_document(
            paths=[
                _line_path(
                    "path-width",
                    "construction",
                    False,
                    [("n1", 0, 0), ("n2", 351, 0)],
                    [("s-width", "n1", "n2")],
                )
            ],
            shapes=[_rectangle()],
            references=[_reference()],
        )
        resized = _blank_document(
            paths=base["paths"],
            shapes=[_rectangle(width_mm=610)],
            references=[_reference()],
        )
        faded = _blank_document(
            paths=base["paths"],
            shapes=[_rectangle()],
            references=[_reference(opacity=0.2)],
        )
        self.assertNotEqual(document_fingerprint(moved), base_document)
        self.assertNotEqual(document_fingerprint(resized), base_document)
        self.assertNotEqual(document_fingerprint(faded), base_document)
        self.assertNotEqual(geometry_fingerprint(moved), base_geometry)
        self.assertNotEqual(geometry_fingerprint(resized), base_geometry)
        self.assertEqual(geometry_fingerprint(faded), base_geometry)

    def test_limits_reject_oversized_documents_without_copying_the_manufacturing_cap(self):
        self.assertGreater(MAX_NODES, 64)
        self.assertGreater(MAX_NODES_PER_PATH, 64)
        paths = [
            _line_path(
                f"path-{index}",
                "annotation",
                False,
                [(f"n-{index}-a", 0, 0), (f"n-{index}-b", 1, 0)],
                [(f"s-{index}", f"n-{index}-a", f"n-{index}-b")],
            )
            for index in range(MAX_PATHS + 1)
        ]
        with self.assertRaises(DrawingDocumentError) as counted:
            normalize_document(_blank_document(paths=paths))
        self.assertEqual(counted.exception.code, "too_many_elements")

        original = drawing_module.MAX_DOCUMENT_UTF8_BYTES
        try:
            drawing_module.MAX_DOCUMENT_UTF8_BYTES = 32
            with self.assertRaises(DrawingDocumentError) as sized:
                normalize_document(_blank_document())
            self.assertEqual(sized.exception.code, "document_too_large")
        finally:
            drawing_module.MAX_DOCUMENT_UTF8_BYTES = original

    def test_board_editor_layout_still_rejects_geometry(self):
        self.assertIn("geometry", FORBIDDEN_FIELDS)
        self.assertNotIn("geometry", TOP_FIELDS)
        self.assertEqual(GEOMETRY_SCHEMA_VERSION, 1)
        self.assertEqual(GEOMETRY_UNIT, "mm")
        self.assertEqual(GEOMETRY_COORDINATE_SPACE, "usable_sheet")
        self.assertNotIn("import frappe", inspect.getsource(drawing_module))
        catalog = catalog_from_projection(
            {
                "pieces": [
                    {
                        "piece_instance_id": "pi-a",
                        "piece_id": 1,
                        "allow_rotation": True,
                        "allow_rotation_proven": True,
                    }
                ],
                "sheets": [{"sheet_no": 1}],
            }
        )
        layout = {
            "schema": 1,
            "pieces": [
                {
                    "piece_instance_id": "pi-a",
                    "sheet_no": 1,
                    "local_x_mm": 0,
                    "local_y_mm": 0,
                    "rotation_deg": 0,
                    "distribution": "active",
                }
            ],
            "boards": [
                {"sheet_no": 1, "origin_x_mm": 0, "origin_y_mm": 0, "user_moved": False}
            ],
            "geometry": {"outer": [[0, 0], [1, 0], [0, 1]]},
        }
        with self.assertRaises(DraftLayoutError) as caught:
            normalize_layout(layout, catalog)
        self.assertEqual(caught.exception.code, "forbidden_field")

    def test_stored_segment_length_is_not_a_second_source_of_truth(self):
        path = _line_path(
            "path-width",
            "construction",
            False,
            [("n1", 0, 0), ("n2", 300, 0)],
            [("s-width", "n1", "n2")],
        )
        path["segments"][0]["length_mm"] = 350
        with self.assertRaises(DrawingDocumentError) as caught:
            normalize_document(_blank_document(paths=[path]))
        self.assertEqual(caught.exception.code, "unknown_field")


if __name__ == "__main__":
    unittest.main()
