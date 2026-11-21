"""Manufacturing compile of an adopted drawing path."""

from __future__ import annotations

import copy
import json
import unittest

from almdina_erp.almdina_erp.application.cutting.board_editor_plan_create import (
    CreateBoardEditorPlanCommand,
    compile_saved_drawings,
    execute_create,
    format_geometry_rejection,
    projection_with_adopted_geometry,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import document_fingerprint
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_copy import (
    build_copied_drawing_rows,
    clone_drawing_document,
    document_from_editable_outline,
    editable_outline_points_mm,
    map_piece_instances,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_persistence import drawing_key
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import serialize_geometry_mm
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry
from almdina_erp.almdina_erp.domain.cutting.liner_geometry import LinerPiece
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import generate_toolpath
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_compile import (
    MAX_VERTICES,
    compile_manufacturing_geometry,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
    BoardEditorMaterializeError,
    materialize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
from almdina_erp.tests.test_board_editor_plan_materialize import (
    draft_payload,
    layout_rows,
    projection,
    projection_piece,
    source_snapshot,
)


def _reference(opacity=0.45):
    return {
        "id": "ref-1",
        "file_id": "FILE-PRIVATE-1",
        "x_mm": 0,
        "y_mm": 0,
        "width_mm": 500,
        "height_mm": 300,
        "rotation_deg": 0,
        "opacity": opacity,
        "locked": True,
        "hidden": False,
        "calibration": None,
    }


def _doc(paths, width=500, length=300, references=None):
    return {
        "schema": "almdina.board-editor-drawing",
        "version": 1,
        "units": "mm",
        "coordinate_space": "door_local",
        "piece_instance_id": "piece:a",
        "blank": {"width_mm": width, "length_mm": length},
        "paths": paths,
        "shapes": [],
        "references": list(references or []),
    }


def _ring(points, path_id="path-1", role="manufacturing_outer", kind="line"):
    nodes = [{"id": f"{path_id}-n{index}", "x_mm": point[0], "y_mm": point[1]} for index, point in enumerate(points)]
    segments = []
    for index in range(len(points)):
        nxt = (index + 1) % len(points)
        segment = {
            "id": f"{path_id}-s{index}",
            "kind": kind,
            "from_node": f"{path_id}-n{index}",
            "to_node": f"{path_id}-n{nxt}",
        }
        segments.append(segment)
    return {
        "id": path_id,
        "role": role,
        "closed": True,
        "source_shape_id": None,
        "nodes": nodes,
        "segments": segments,
    }


class DrawingCompileTests(unittest.TestCase):
    def test_rectangle_is_the_centimetre_contract(self):
        result = compile_manufacturing_geometry(
            _doc([_ring([(0, 0), (500, 0), (500, 300), (0, 300)])]),
            blank_width_mm=500,
            blank_length_mm=300,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["geometry"]["units"], "cm")
        self.assertEqual(result["geometry"]["points"], [[0.0, 0.0], [50.0, 0.0], [50.0, 30.0], [0.0, 30.0]])
        self.assertNotIn("references", result["geometry"])

    def test_l_trapezoid_and_clipped_corner(self):
        shapes = [
            [(0, 0), (500, 0), (500, 150), (250, 150), (250, 300), (0, 300)],
            [(0, 0), (500, 0), (400, 300), (100, 300)],
            [(0, 0), (400, 0), (500, 100), (500, 300), (0, 300)],
        ]
        for points in shapes:
            with self.subTest(points=points):
                result = compile_manufacturing_geometry(
                    _doc([_ring(points)]),
                    blank_width_mm=500,
                    blank_length_mm=300,
                )
                self.assertEqual(result["status"], "ready", result.get("code"))

    def test_guides_images_and_shapes_are_absent(self):
        guide = _ring([(0, 0), (500, 0), (500, 300), (0, 300)], role="construction")
        result = compile_manufacturing_geometry(
            _doc([guide], references=[_reference(0.2)]),
            blank_width_mm=500,
            blank_length_mm=300,
        )
        self.assertEqual(result["status"], "absent")

    def test_image_opacity_does_not_change_the_manufacturing_fingerprint(self):
        path = _ring([(0, 0), (500, 0), (500, 300), (0, 300)])
        first = compile_manufacturing_geometry(
            _doc([path], references=[_reference(0.2)]),
            blank_width_mm=500,
            blank_length_mm=300,
        )
        second = compile_manufacturing_geometry(
            _doc([path], references=[_reference(0.9)]),
            blank_width_mm=500,
            blank_length_mm=300,
        )
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_open_crossing_outside_duplicate_and_hole(self):
        open_path = _ring([(0, 0), (500, 0), (500, 300)])
        open_path["closed"] = False
        open_path["segments"].pop()
        cases = [
            ([open_path], "path_open"),
            ([_ring([(0, 0), (500, 300), (500, 0), (0, 300)])], "self_intersection"),
            ([_ring([(0, 0), (520, 0), (520, 300), (0, 300)])], "outside_blank"),
            ([
                _ring([(0, 0), (500, 0), (500, 300), (0, 300)]),
                _ring([(0, 0), (500, 0), (500, 300), (0, 300)], path_id="path-2"),
            ], "multiple_outers"),
            ([_ring([(0, 0), (500, 0), (500, 300), (0, 300)], role="manufacturing_hole")], "holes_unsupported"),
        ]
        for paths, code in cases:
            with self.subTest(code=code):
                result = compile_manufacturing_geometry(_doc(paths), blank_width_mm=500, blank_length_mm=300)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["code"], code)

    def test_blank_330_by_550_distinguishes_outside_from_smaller(self):
        full = _ring([(0, 0), (330, 0), (330, 550), (0, 550)])
        ready = compile_manufacturing_geometry(
            _doc([full], width=330, length=550),
            blank_width_mm=330,
            blank_length_mm=550,
        )
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["geometry"]["blank_width_cm"], 33)
        self.assertEqual(ready["geometry"]["blank_length_cm"], 55)
        smaller = compile_manufacturing_geometry(
            _doc([_ring([(20, 20), (300, 20), (300, 500), (20, 500)])], width=330, length=550),
            blank_width_mm=330,
            blank_length_mm=550,
        )
        self.assertEqual(smaller["status"], "ready")
        self.assertEqual(smaller["geometry"]["reservation"], "blank")
        self.assertNotIn("reservation", ready["geometry"])
        self.assertEqual(smaller["geometry"]["points"][0], [2.0, 2.0])
        outside = compile_manufacturing_geometry(
            _doc([_ring([(-5, 0), (330, 0), (330, 550), (0, 550)])], width=330, length=550),
            blank_width_mm=330,
            blank_length_mm=550,
        )
        self.assertEqual(outside["code"], "outside_blank")
        partial = compile_manufacturing_geometry(
            _doc([_ring([(0, 0), (400, 0), (400, 550), (0, 550)])], width=330, length=550),
            blank_width_mm=330,
            blank_length_mm=550,
        )
        self.assertEqual(partial["code"], "outside_blank")

    def test_guide_outside_does_not_replace_the_adopted_outline_error(self):
        guide = _ring([(-80, -80), (900, -80), (900, 900), (-80, 900)], path_id="guide", role="construction")
        cut = _ring([(0, 0), (400, 0), (400, 550), (0, 550)], path_id="cut-rect")
        result = compile_manufacturing_geometry(
            _doc([guide, cut], width=330, length=550),
            blank_width_mm=330,
            blank_length_mm=550,
        )
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["code"], "outside_blank")
        self.assertEqual(result["path_id"], "cut-rect")
        absent = compile_manufacturing_geometry(
            _doc([guide], width=330, length=550),
            blank_width_mm=330,
            blank_length_mm=550,
        )
        self.assertEqual(absent["status"], "absent")
        self.assertEqual(
            format_geometry_rejection(
                "The cut outline extends outside the door blank. Move the whole path inside the blank.",
                {"label": "8.1", "original_w": 33, "original_h": 55, "piece_instance_id": "secret-id"},
            ),
            "Door 8.1. Size 33 × 55 cm. The cut outline extends outside the door blank. Move the whole path inside the blank.",
        )
        self.assertNotIn("secret-id", format_geometry_rejection("problem", {"label": "8.1", "original_w": 33, "original_h": 55, "piece_instance_id": "secret-id"}))

    def test_zero_edge_is_rejected(self):
        path = _ring([(0, 0), (0, 0), (500, 0), (500, 300), (0, 300)])
        result = compile_manufacturing_geometry(_doc([path]), blank_width_mm=500, blank_length_mm=300)
        self.assertEqual(result["code"], "zero_edge")

    def test_circle_on_a_square_blank_keeps_the_curve(self):
        path = {
            "id": "path-1",
            "role": "manufacturing_outer",
            "closed": True,
            "source_shape_id": None,
            "nodes": [
                {"id": "n1", "x_mm": 80, "y_mm": 40},
                {"id": "n2", "x_mm": 0, "y_mm": 40},
            ],
            "segments": [
                {"id": "s1", "kind": "arc", "from_node": "n1", "to_node": "n2", "radius_mm": 40, "large_arc": False, "sweep_clockwise": True},
                {"id": "s2", "kind": "arc", "from_node": "n2", "to_node": "n1", "radius_mm": 40, "large_arc": False, "sweep_clockwise": True},
            ],
        }
        result = compile_manufacturing_geometry(_doc([path], width=80, length=80), blank_width_mm=80, blank_length_mm=80)
        self.assertEqual(result["status"], "ready", result.get("code"))
        self.assertGreater(len(result["geometry"]["points"]), 8)
        self.assertLessEqual(len(result["geometry"]["points"]), MAX_VERTICES)
        xs = [point[0] for point in result["geometry"]["points"]]
        ys = [point[1] for point in result["geometry"]["points"]]
        self.assertEqual(min(xs), 0)
        self.assertEqual(max(xs), 8)
        self.assertEqual(min(ys), 0)
        self.assertEqual(max(ys), 8)

    def test_arc_and_bezier_are_not_replaced_by_one_chord(self):
        arc = {
            "id": "path-1",
            "role": "manufacturing_outer",
            "closed": True,
            "source_shape_id": None,
            "nodes": [
                {"id": "n1", "x_mm": 0, "y_mm": 0},
                {"id": "n2", "x_mm": 500, "y_mm": 0},
                {"id": "n3", "x_mm": 500, "y_mm": 300},
                {"id": "n4", "x_mm": 0, "y_mm": 300},
            ],
            "segments": [
                {"id": "s1", "kind": "arc", "from_node": "n1", "to_node": "n2", "radius_mm": 300, "large_arc": False, "sweep_clockwise": False},
                {"id": "s2", "kind": "line", "from_node": "n2", "to_node": "n3"},
                {"id": "s3", "kind": "line", "from_node": "n3", "to_node": "n4"},
                {"id": "s4", "kind": "line", "from_node": "n4", "to_node": "n1"},
            ],
        }
        bezier = {
            "id": "path-1",
            "role": "manufacturing_outer",
            "closed": True,
            "source_shape_id": None,
            "nodes": [
                {"id": "n1", "x_mm": 0, "y_mm": 0},
                {"id": "n2", "x_mm": 500, "y_mm": 0},
                {"id": "n3", "x_mm": 500, "y_mm": 300},
                {"id": "n4", "x_mm": 0, "y_mm": 300},
            ],
            "segments": [
                {
                    "id": "s1",
                    "kind": "bezier",
                    "from_node": "n1",
                    "to_node": "n2",
                    "controls": [{"x_mm": 150, "y_mm": 40}, {"x_mm": 350, "y_mm": 40}],
                },
                {"id": "s2", "kind": "line", "from_node": "n2", "to_node": "n3"},
                {"id": "s3", "kind": "line", "from_node": "n3", "to_node": "n4"},
                {"id": "s4", "kind": "line", "from_node": "n4", "to_node": "n1"},
            ],
        }
        for path in (arc, bezier):
            result = compile_manufacturing_geometry(_doc([path]), blank_width_mm=500, blank_length_mm=300)
            self.assertEqual(result["status"], "ready", result.get("code"))
            self.assertGreater(len(result["geometry"]["points"]), 4)

    def test_a_curve_past_the_vertex_cap_is_rejected(self):
        path = {
            "id": "path-1",
            "role": "manufacturing_outer",
            "closed": True,
            "source_shape_id": None,
            "nodes": [
                {"id": "n1", "x_mm": 0, "y_mm": 0},
                {"id": "n2", "x_mm": 10000, "y_mm": 0},
            ],
            "segments": [
                {"id": "s1", "kind": "arc", "from_node": "n1", "to_node": "n2", "radius_mm": 5000, "large_arc": False, "sweep_clockwise": True},
                {"id": "s2", "kind": "arc", "from_node": "n2", "to_node": "n1", "radius_mm": 5000, "large_arc": False, "sweep_clockwise": True},
            ],
        }
        result = compile_manufacturing_geometry(_doc([path], width=10000, length=10000), blank_width_mm=10000, blank_length_mm=10000)
        self.assertEqual(result["code"], "curve_unrepresentable")

    def test_copy_keeps_source_geometry_and_separates_same_size_doors(self):
        rectangle = compile_manufacturing_geometry(
            _doc([_ring([(0, 0), (500, 0), (500, 300), (0, 300)])]),
            blank_width_mm=500,
            blank_length_mm=300,
        )["geometry"]
        notch = compile_manufacturing_geometry(
            _doc([_ring([(0, 0), (500, 0), (500, 150), (250, 150), (250, 300), (0, 300)])]),
            blank_width_mm=500,
            blank_length_mm=300,
        )["geometry"]
        pieces = [
            projection_piece("A", 1, 0, 0, 500, 300, piece_type="Special"),
            projection_piece("B", 2, 600, 0, 500, 300, piece_type="Special"),
        ]
        proj = projection(pieces)
        source = source_snapshot(pieces)
        for piece in source["sheets"][0]["pieces"]:
            piece["piece_type"] = "Special"
            piece["special_shape_geometry_json"] = '{"kind":"old"}'
        before = copy.deepcopy(source)
        adopted = {
            "A": json.dumps(rectangle, sort_keys=True),
            "B": json.dumps(notch, sort_keys=True),
        }
        snapshot = materialize_plan_snapshot(
            draft=draft_payload(layout_rows(pieces)),
            projection=projection_with_adopted_geometry(proj, source, adopted),
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
            adopted_geometry=adopted,
        )
        self.assertEqual(source, before)
        stored = {
            piece["piece_instance_id"]: json.loads(piece["special_shape_geometry_json"])
            for sheet in snapshot["sheets"]
            for piece in sheet["pieces"]
        }
        self.assertEqual(stored["A"]["points"], rectangle["points"])
        self.assertEqual(stored["B"]["points"], notch["points"])
        self.assertNotEqual(stored["A"]["points"], stored["B"]["points"])
        encoded = json.dumps(stored)
        self.assertNotIn("file_id", encoded)
        self.assertNotIn("construction", encoded)
        placed = material_outline_cm(snapshot["sheets"][0]["pieces"][0])
        self.assertEqual([list(point) for point in placed], rectangle["points"])

    def test_invalid_adopted_outline_and_version_conflict_do_not_fall_back(self):
        pieces = {"A": {"piece_type": "Special", "original_w": 50, "original_h": 30}}
        open_path = _ring([(0, 0), (500, 0), (500, 300)])
        open_path["closed"] = False
        open_path["segments"].pop()
        rejected = compile_saved_drawings(
            [{"piece_instance_id": "A", "drawing_version": 2, "document": _doc([open_path])}],
            pieces,
            expected_versions={"A": 2},
        )
        self.assertEqual(rejected["code"], "geometry_rejected")
        self.assertEqual(rejected["reason"], "path_open")
        conflict = compile_saved_drawings(
            [{"piece_instance_id": "A", "drawing_version": 2, "document": _doc([])}],
            pieces,
            expected_versions={"A": 1},
        )
        self.assertEqual(conflict["code"], "drawing_version_conflict")
        absent = compile_saved_drawings(
            [{"piece_instance_id": "A", "drawing_version": 2, "document": _doc([]), "source_input_fingerprint": "fp-1"}],
            pieces,
            expected_versions={"A": 2},
            source_input_fingerprint="fp-1",
        )
        self.assertEqual(absent["adopted"], {})

    def test_changed_outline_that_collides_is_not_materialized(self):
        rectangle = compile_manufacturing_geometry(
            _doc([_ring([(0, 0), (500, 0), (500, 300), (0, 300)])]),
            blank_width_mm=500,
            blank_length_mm=300,
        )["geometry"]
        pieces = [
            projection_piece("A", 1, 0, 0, 500, 300, piece_type="Special"),
            projection_piece("B", 2, 100, 0, 500, 300, piece_type="Special"),
        ]
        source = source_snapshot(pieces)
        adopted = {"A": json.dumps(rectangle, sort_keys=True), "B": json.dumps(rectangle, sort_keys=True)}
        with self.assertRaises(BoardEditorMaterializeError) as raised:
            materialize_plan_snapshot(
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
        self.assertEqual(raised.exception.code, "not_ready")

    def test_vertex_cap_matches_the_manufacturing_contract(self):
        from almdina_erp.almdina_erp.services.special_shape_service import MAX_GEOMETRY_VERTICES

        self.assertEqual(MAX_VERTICES, MAX_GEOMETRY_VERTICES)

    def test_new_outline_with_unproven_machining_is_not_exported(self):
        piece = LinerPiece("Regular", 50, 30)
        liner = generate_toolpath(
            kind="liner", piece=piece, reference_side="edge_width_top",
            offset_cm=0, width_cm=1.8, start_cm=0, length_cm=30, cutter_diameter_mm=3,
        )
        handle = generate_toolpath(
            kind="recessed_handle_cutout", piece=piece, reference_side="edge_width_top",
            offset_cm=0, width_cm=1.8, start_cm=0, length_cm=30, cutter_diameter_mm=8,
        )
        groove = generate_toolpath(
            kind="back_groove", piece=piece, reference_side="edge_width_top",
            offset_cm=0, width_cm=1.8, start_cm=0, length_cm=30, cutter_diameter_mm=5,
        )
        self.assertGreaterEqual(len(liner), 2)
        self.assertGreaterEqual(len(handle), 2)
        self.assertGreaterEqual(len(groove), 2)
        self.assertNotEqual(liner, handle)
        rejected = compile_saved_drawings(
            [{
                "piece_instance_id": "A",
                "drawing_version": 1,
                "document": _doc([_ring([(0, 0), (500, 0), (500, 300), (0, 300)])]),
            }],
            {"A": {"piece_type": "Special", "original_w": 50, "original_h": 30, "extra_liner": 1}},
            expected_versions={"A": 1},
        )
        self.assertEqual(rejected["code"], "geometry_rejected")
        self.assertEqual(rejected["reason"], "addon_unproven")
        self.assertNotIn("adopted", rejected)

    def test_compiled_rectangle_is_the_dxf_outer(self):
        geometry = compile_manufacturing_geometry(
            _doc([_ring([(0, 0), (500, 0), (500, 300), (0, 300)])]),
            blank_width_mm=500,
            blank_length_mm=300,
        )["geometry"]
        placed = {
            "piece_type": "Special",
            "original_w": 50,
            "original_h": 30,
            "x": 0,
            "y": 0,
            "w": 50,
            "h": 30,
            "special_shape_geometry_json": json.dumps(geometry),
        }
        outline = material_outline_cm(placed)
        self.assertEqual([list(point) for point in outline], geometry["points"])
        snapshot = serialize_geometry_mm(
            PartGeometry(
                outer=tuple((point[0] * 10.0, point[1] * 10.0) for point in outline),
                holes=(),
            )
        )
        self.assertEqual(snapshot["outer"][0], [0.0, 0.0])
        self.assertEqual(snapshot["outer"][2], [500.0, 300.0])
        self.assertEqual(snapshot["holes"], [])


class DrawingCopyTests(unittest.TestCase):
    def _document(self):
        guide = _ring([(10, 10), (40, 10), (40, 30)], path_id="guide", role="annotation")
        guide["closed"] = False
        guide["segments"] = guide["segments"][:2]
        curve = {
            "id": "curve",
            "role": "construction",
            "closed": False,
            "source_shape_id": None,
            "nodes": [
                {"id": "c1", "x_mm": 0, "y_mm": 0},
                {"id": "c2", "x_mm": 80, "y_mm": 20},
            ],
            "segments": [{
                "id": "cs",
                "kind": "bezier",
                "from_node": "c1",
                "to_node": "c2",
                "controls": [{"x_mm": 20, "y_mm": 30}, {"x_mm": 60, "y_mm": -10}],
            }],
        }
        return _doc(
            [guide, curve],
            references=[_reference()],
        ) | {
            "shapes": [{
                "id": "shape-1",
                "kind": "rectangle",
                "exploded": False,
                "path_id": None,
                "params": {
                    "x_mm": 10, "y_mm": 12, "width_mm": 30, "height_mm": 18, "rotation_deg": 0,
                },
            }]
        }

    def test_copy_keeps_vectors_and_drops_reference_images(self):
        source = self._document()
        before = copy.deepcopy(source)
        cloned = clone_drawing_document(source, "A")
        self.assertEqual(source, before)
        self.assertEqual(cloned["references"], [])
        self.assertEqual(cloned["paths"][0]["role"], "annotation")
        self.assertEqual(cloned["paths"][1]["segments"][0]["kind"], "bezier")
        self.assertEqual(cloned["shapes"][0]["params"]["width_mm"], 30)
        self.assertNotEqual(document_fingerprint(cloned), document_fingerprint(source))
        rows = build_copied_drawing_rows(
            records=[{
                "piece_instance_id": "A",
                "drawing_key": "source-key",
                "drawing_version": 4,
                "source_content_revision": "old-token",
                "document_fingerprint": "old-fp",
                "drawing_json": source,
            }],
            source_snapshot={"sheets": [{"sheet_no": 1, "pieces": [{"piece_instance_id": "A"}]}]},
            copied_snapshot={"sheets": [{"sheet_no": 1, "pieces": [{"piece_instance_id": "A"}]}]},
            order_name="ORD-1",
            plan_name="CP-NEW",
            source_content_revision="CP-NEW| |2|fp-new|0|0",
            source_input_fingerprint="fp-new",
        )
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]["drawing_key"], "source-key")
        self.assertEqual(rows[0]["drawing_key"], drawing_key("ORD-1", "CP-NEW", "A"))
        self.assertEqual(rows[0]["drawing_version"], 1)
        self.assertEqual(rows[0]["source_content_revision"], "CP-NEW| |2|fp-new|0|0")
        self.assertEqual(rows[0]["source_input_fingerprint"], "fp-new")
        self.assertEqual(rows[0]["prior_drawing_archive_json"], [])
        self.assertEqual(rows[0]["drawing_json"]["references"], [])
        self.assertIn("annotation", json.dumps(rows[0]["drawing_json"]))

    def test_piece_ids_map_by_identity_or_complete_order(self):
        source = {"sheets": [{"sheet_no": 1, "pieces": [{"piece_instance_id": "A"}, {"piece_instance_id": "B"}]}]}
        renamed = {"sheets": [{"sheet_no": 1, "pieces": [{"piece_instance_id": "A2"}, {"piece_instance_id": "B2"}]}]}
        self.assertEqual(map_piece_instances(source, renamed), {"A": "A2", "B": "B2"})
        partial = {"sheets": [{"sheet_no": 1, "pieces": [{"piece_instance_id": "A"}, {"piece_instance_id": "B2"}]}]}
        with self.assertRaises(Exception):
            map_piece_instances(source, partial)

    def test_plan_copy_inserts_an_independent_drawing_or_discards_the_plan(self):
        pieces = [projection_piece("A", 1, 0, 0, 200, 200)]
        proj = projection(pieces)
        source = source_snapshot(pieces)
        layout = layout_rows(pieces)
        draft = draft_payload(layout)
        document = self._document()
        document["piece_instance_id"] = "A"

        class DraftStore:
            def __init__(self):
                self.row = {
                    "name": "DRAFT-1",
                    "draft_version": 1,
                    "source_content_revision": "rev-1",
                    "source_input_fingerprint": "fp-1",
                    "distribution_fingerprint": draft["distribution_fingerprint"],
                    "layout_json": draft["layout"],
                    "last_create_request_id": "",
                    "last_created_plan": "",
                    "last_created_draft_version": 0,
                }
                self.recorded = None

            def lock_draft(self, order_name, plan_name):
                return dict(self.row)

            def record_create(self, **kwargs):
                self.recorded = kwargs

        class PlanPort:
            def __init__(self):
                self.discarded = []

            def existing_revisions(self, order_name):
                return [1]

            def create_board_editor_draft(self, **kwargs):
                return {"name": "CP-NEW", "revision": 2, "status": "Draft"}

            def apply_snapshot(self, **kwargs):
                return {
                    "name": kwargs["plan_name"],
                    "revision": 2,
                    "status": "Draft",
                    "input_fingerprint": "fp-new",
                    "content_revision_token": "CP-NEW|sha|2|fp-new|0|0",
                }

            def discard_incomplete_plan(self, plan_name):
                self.discarded.append(plan_name)

            def load_source_plan(self, order_name, plan_name):
                return {"name": plan_name, "order_name": order_name, "snapshot": source, "machine_type": "CNC Router"}

        class DrawingStore:
            def __init__(self, fail=False):
                self.fail = fail
                self.rows = {}

            def insert(self, row):
                if self.fail:
                    raise RuntimeError("disk")
                self.rows[row["drawing_key"]] = copy.deepcopy(row)
                return copy.deepcopy(row)

            def delete(self, key):
                self.rows.pop(key, None)

        command = CreateBoardEditorPlanCommand(
            order_name="ORD-1",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
            create_request_id="req-copy",
            draft_name="DRAFT-1",
        )
        drawings = DrawingStore()
        drafts = DraftStore()
        created = execute_create(
            command,
            order_status="Draft",
            projection=proj,
            machine_type="CNC Router",
            draft_store=drafts,
            plan_port=PlanPort(),
            drawing_records=[{"piece_instance_id": "A", "drawing_version": 3, "drawing_json": document}],
            expected_drawing_versions={"A": 3},
            drawing_store=drawings,
        )
        self.assertTrue(created["ok"])
        self.assertIsNotNone(drafts.recorded)
        stored = next(iter(drawings.rows.values()))
        self.assertEqual(stored["source_plan"], "CP-NEW")
        self.assertEqual(stored["piece_instance_id"], "A")
        self.assertEqual(stored["drawing_version"], 1)
        self.assertEqual(stored["source_content_revision"], "CP-NEW|sha|2|fp-new|0|0")
        self.assertEqual(stored["drawing_json"]["references"], [])
        self.assertEqual(stored["drawing_json"]["paths"][1]["segments"][0]["controls"][0]["x_mm"], 20)
        stored["drawing_json"]["paths"][1]["nodes"][1]["x_mm"] = 999
        self.assertEqual(document["paths"][1]["nodes"][1]["x_mm"], 80)

        failed_drawings = DrawingStore(fail=True)
        failed_drafts = DraftStore()
        failed_port = PlanPort()
        failed = execute_create(
            command,
            order_status="Draft",
            projection=proj,
            machine_type="CNC Router",
            draft_store=failed_drafts,
            plan_port=failed_port,
            drawing_records=[{"piece_instance_id": "A", "drawing_version": 3, "drawing_json": document}],
            expected_drawing_versions={"A": 3},
            drawing_store=failed_drawings,
        )
        self.assertEqual(failed["code"], "drawing_copy_failed")
        self.assertEqual(failed_port.discarded, ["CP-NEW"])
        self.assertIsNone(failed_drafts.recorded)
        self.assertEqual(failed_drawings.rows, {})

    def test_stored_polygon_restores_lines_only(self):
        geometry = {
            "version": 1,
            "kind": "polygon",
            "units": "cm",
            "template": "drawing",
            "blank_width_cm": 50,
            "blank_length_cm": 30,
            "points": [[0, 0], [50, 0], [50, 30], [0, 30], [0, 0]],
            "exact": True,
        }
        points = editable_outline_points_mm(json.dumps(geometry))
        self.assertEqual(points[1], [500.0, 0.0])
        self.assertEqual(len(points), 4)
        restored = document_from_editable_outline(points, "A", 500, 300)
        self.assertEqual(restored["paths"][0]["role"], "manufacturing_outer")
        self.assertTrue(all(segment["kind"] == "line" for segment in restored["paths"][0]["segments"]))
        self.assertEqual(restored["references"], [])
        self.assertEqual(restored["shapes"], [])
        self.assertIsNone(editable_outline_points_mm('{"version":1,"kind":"polygon","units":"cm","exact":false,"points":[[0,0],[1,0],[1,1]]}'))
