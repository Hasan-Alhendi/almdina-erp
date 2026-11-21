"""Adopted Special contours survive the first plan copy.

CP-2026-00089 kept a verified interior contour in special JSON and then
deleted geometry.outer because the door was still classified cnc_raw_rect.
These tests fail on that deletion and pass once the posed contour is kept.
"""

from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.cutting.board_editor_plan_create import (
    compile_saved_drawings,
    projection_with_adopted_geometry,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import normalize_layout
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft_review import (
    pose_normalized_layout,
    trusted_model_from_projection,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_compile import (
    compile_manufacturing_geometry,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_manufacturing import (
    BoardEditorManufacturingError,
    assert_board_editor_manufacturing_ready,
    format_missing_geometry_message,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
    _catalog_from_trusted,
    materialize_plan_snapshot,
)
from almdina_erp.almdina_erp.infrastructure.cutting.dxf_reader import read_dxf_geometry_bytes
from almdina_erp.tests.test_board_editor_drawing_compile import _doc, _ring
from almdina_erp.tests.test_board_editor_drawing_manufacturing_roundtrip import _real_dxf
from almdina_erp.tests.test_board_editor_plan_materialize import (
    draft_payload,
    layout_rows,
    projection,
    projection_piece,
    rect,
    source_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "translations" / "ar.csv"

# Door 4.1 on CP-2026-00089: 115 x 70 cm blank, interior contour, reservation blank.
INCIDENT_MM = (
    (190.1, 101.09),
    (986.6, 101.09),
    (986.6, 627.81),
    (190.1, 627.81),
)
INCIDENT_CM = [[19.01, 10.109], [98.66, 10.109], [98.66, 62.781], [19.01, 62.781]]

ARABIC = {
    "The cutting plan cannot be approved because the finished outline is incomplete for these doors:": (
        "تعذر اعتماد خطة القص بسبب عدم اكتمال الهندسة النهائية للدرف التالية:"
    ),
    "The cutting plan cannot be exported because the finished outline is incomplete for these doors:": (
        "تعذر تصدير خطة القص بسبب عدم اكتمال الهندسة النهائية للدرف التالية:"
    ),
    "- Door {0} — sheet {1}.": "- الدرفة {0} — اللوح {1}.",
    "Finish and approve the cut outline in the editor then create a new plan copy.": (
        "يرجى استكمال محيط القص واعتماده داخل المحرر، ثم إنشاء نسخة جديدة من الخطة."
    ),
}


def _near(point, expected, tolerance=0.05):
    return math.dist((float(point[0]), float(point[1])), expected) <= tolerance


def _contains(points, expected, tolerance=0.05):
    return any(_near(point, expected, tolerance) for point in points)


def _boards(*numbers, width_mm=2400, length_mm=4800):
    return {
        number: {
            "sheet_no": number,
            "resource_kind": "FULL_BOARD",
            "usable_width_mm": width_mm,
            "usable_length_mm": length_mm,
            "w": width_mm / 10.0,
            "h": length_mm / 10.0,
            "usable_width_cm": width_mm / 10.0,
            "usable_length_cm": length_mm / 10.0,
            "full_width_cm": width_mm / 10.0,
            "full_length_cm": length_mm / 10.0,
            "source_area_m2": (width_mm * length_mm) / 1_000_000.0,
        }
        for number in numbers
    }


def _special(instance, piece_id, x, y, w, h, **extra):
    piece = projection_piece(
        instance,
        piece_id,
        x,
        y,
        w,
        h,
        piece_type="Special",
        original_w=extra.get("original_w", w / 10.0),
        original_h=extra.get("original_h", h / 10.0),
        sheet=extra.get("sheet", 1),
    )
    piece["label"] = extra.get("label", instance)
    piece["geometry_source"] = "cnc_raw_rect"
    piece["exact_geometry"] = False
    piece["special_representation"] = "cnc_raw"
    return piece


def _compiled(points, width, length):
    result = compile_manufacturing_geometry(
        _doc([_ring(points)], width=width, length=length),
        blank_width_mm=width,
        blank_length_mm=length,
    )
    if result["status"] != "ready":
        raise AssertionError(result.get("code") or result["status"])
    return json.dumps(result["geometry"], sort_keys=True, separators=(",", ":"))


def _strip_geometry(source, *instances):
    wanted = set(instances)
    for sheet in source["sheets"]:
        for piece in sheet["pieces"]:
            if not wanted or piece["piece_instance_id"] in wanted:
                piece["piece_type"] = "Special"
                piece.pop("geometry", None)
                piece.pop("special_shape_geometry_json", None)


def _save(pieces, source, adopted, sheets, layout):
    patched = projection_with_adopted_geometry(projection(pieces, sheets=sheets), source, adopted)
    return materialize_plan_snapshot(
        draft=draft_payload(layout),
        projection=patched,
        source_snapshot=source,
        machine_type="CNC Router",
        source_plan_name="CP-2026-00088",
        expected_draft_version=1,
        source_content_revision="rev-1",
        source_input_fingerprint="fp-1",
        adopted_geometry=adopted,
    ), patched


def _arabic(message):
    return ARABIC[message]


class AdoptedGeometryMaterializeTests(unittest.TestCase):
    def test_cp_2026_00089_first_copy_keeps_the_verified_contour(self):
        piece = _special("4", 4, 0, 0, 1150, 700, sheet=3, label="4.1", original_w=115, original_h=70)
        adopted_json = _compiled(INCIDENT_MM, 1150, 700)
        stored = json.loads(adopted_json)
        self.assertEqual(stored["points"], INCIDENT_CM)
        self.assertEqual(stored["reservation"], "blank")
        self.assertTrue(stored["exact"])
        sheets = _boards(3)
        pieces = [piece]
        source = source_snapshot(pieces, sheets=sheets)
        _strip_geometry(source, "4")
        before = copy.deepcopy(source)
        adopted = {"4": adopted_json}
        layout = layout_rows(pieces, boards=(3,))
        patched = projection_with_adopted_geometry(projection(pieces, sheets=sheets), source, adopted)
        self.assertEqual(patched["pieces"][0]["geometry_source"], "special_shape_geometry_json")
        # The classification that existed before the drawing was adopted.
        patched["pieces"][0]["geometry_source"] = "cnc_raw_rect"
        patched["pieces"][0]["special_representation"] = "cnc_raw"
        snapshot = materialize_plan_snapshot(
            draft=draft_payload(layout),
            projection=patched,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="CP-2026-00088",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
            adopted_geometry=adopted,
        )
        self.assertEqual(source, before)
        saved = snapshot["sheets"][0]["pieces"][0]
        outer = saved["geometry"]["outer"]
        self.assertGreaterEqual(len(outer), 3)
        for point in INCIDENT_MM:
            self.assertTrue(_contains(outer, point), point)
        self.assertFalse(_contains(outer, (0.0, 0.0)))
        self.assertFalse(_contains(outer, (1150.0, 700.0)))
        self.assertEqual(json.loads(saved["special_shape_geometry_json"])["points"], INCIDENT_CM)
        self.assertEqual(saved["blank_reservation_cm"], [[0.0, 0.0], [115.0, 0.0], [115.0, 70.0], [0.0, 70.0]])
        self.assertEqual((saved["w"], saved["h"]), (115.0, 70.0))
        assert_board_editor_manufacturing_ready(snapshot, machine_type="CNC Router", kerf_mm=4.0)

        reloaded = projection_piece(
            "4",
            4,
            saved["x"] * 10,
            saved["y"] * 10,
            saved["w"] * 10,
            saved["h"] * 10,
            piece_type="Special",
            original_w=115,
            original_h=70,
            sheet=3,
        )
        reloaded["label"] = "4.1"
        again_source = copy.deepcopy(snapshot)
        again, _patched = _save(
            [reloaded],
            again_source,
            adopted,
            sheets,
            layout_rows([reloaded], boards=(3,)),
        )
        self.assertEqual(snapshot, again_source)
        copied = again["sheets"][0]["pieces"][0]["geometry"]["outer"]
        for point in outer:
            self.assertTrue(_contains(copied, (point[0], point[1])), point)
        self.assertEqual(
            json.loads(again["sheets"][0]["pieces"][0]["special_shape_geometry_json"])["points"],
            INCIDENT_CM,
        )

    def test_raw_special_without_an_adopted_drawing_still_has_no_contour(self):
        piece = _special("RAW", 9, 0, 0, 220, 210, label="9.1", original_w=22, original_h=21)
        sheets = _boards(1)
        source = source_snapshot([piece], sheets=sheets)
        _strip_geometry(source, "RAW")
        snapshot, _patched = _save([piece], source, {}, sheets, layout_rows([piece]))
        saved = snapshot["sheets"][0]["pieces"][0]
        self.assertNotIn("geometry", saved)
        self.assertEqual((saved["w"], saved["h"]), (22.0, 21.0))
        with self.assertRaises(BoardEditorManufacturingError) as caught:
            assert_board_editor_manufacturing_ready(snapshot, machine_type="CNC Router", kerf_mm=4.0)
        self.assertEqual(caught.exception.code, "missing_geometry")

    def test_shape_without_a_manufacturing_path_is_not_adopted(self):
        piece = _special("RAW", 9, 0, 0, 220, 210, label="9.1", original_w=22, original_h=21)
        document = _doc(
            [_ring([(40, 40), (180, 40), (180, 160)], role="construction")],
            width=220,
            length=210,
        )
        compiled = compile_saved_drawings(
            [{
                "piece_instance_id": "RAW",
                "drawing_version": 1,
                "document": document,
                "source_input_fingerprint": "fp-1",
            }],
            {"RAW": {"piece_type": "Special", "label": "9.1", "w": 22, "h": 21, "original_w": 22, "original_h": 21}},
            {"RAW": 1},
            "fp-1",
        )
        self.assertTrue(compiled["ok"], compiled)
        self.assertEqual(compiled["adopted"], {})
        sheets = _boards(1)
        source = source_snapshot([piece], sheets=sheets)
        _strip_geometry(source, "RAW")
        snapshot, _patched = _save([piece], source, {}, sheets, layout_rows([piece]))
        self.assertNotIn("geometry", snapshot["sheets"][0]["pieces"][0])
        with self.assertRaises(BoardEditorManufacturingError) as caught:
            assert_board_editor_manufacturing_ready(snapshot, machine_type="CNC Router", kerf_mm=4.0)
        self.assertEqual(caught.exception.code, "missing_geometry")
        english = format_missing_geometry_message(caught.exception.detail, action="approve", translate=lambda text: text)
        arabic = format_missing_geometry_message(caught.exception.detail, action="approve", translate=_arabic)
        self.assertIn("- Door 9.1 — sheet 1.", english)
        self.assertIn("- الدرفة 9.1 — اللوح 1.", arabic)
        self.assertIn("create a new plan copy", english)
        self.assertIn("إنشاء نسخة جديدة من الخطة", arabic)

    def test_edge_touching_contour_is_kept_and_is_not_the_stock_rectangle(self):
        points = ((0, 0), (500, 0), (500, 300), (250, 300), (0, 150))
        piece = _special("EDGE", 2, 0, 0, 500, 300, label="2.1")
        adopted = {"EDGE": _compiled(points, 500, 300)}
        self.assertNotIn("reservation", json.loads(adopted["EDGE"]))
        sheets = _boards(1)
        source = source_snapshot([piece], sheets=sheets)
        _strip_geometry(source, "EDGE")
        patched = projection_with_adopted_geometry(projection([piece], sheets=sheets), source, adopted)
        patched["pieces"][0]["geometry_source"] = "cnc_raw_rect"
        snapshot = materialize_plan_snapshot(
            draft=draft_payload(layout_rows([piece])),
            projection=patched,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
            adopted_geometry=adopted,
        )
        outer = snapshot["sheets"][0]["pieces"][0]["geometry"]["outer"]
        self.assertEqual(len(outer), 5)
        self.assertNotEqual(outer, rect(0, 0, 500, 300))
        xs = [point[0] for point in outer]
        ys = [point[1] for point in outer]
        self.assertAlmostEqual(min(xs), 0.0)
        self.assertAlmostEqual(max(xs), 500.0)
        self.assertAlmostEqual(min(ys), 0.0)
        self.assertAlmostEqual(max(ys), 300.0)
        assert_board_editor_manufacturing_ready(snapshot, machine_type="CNC Router", kerf_mm=4.0)

    def test_adopted_bezier_contour_is_kept(self):
        path = {
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
        result = compile_manufacturing_geometry(_doc([path]), blank_width_mm=500, blank_length_mm=300)
        self.assertEqual(result["status"], "ready", result.get("code"))
        self.assertGreater(len(result["geometry"]["points"]), 4)
        piece = _special("CURVE", 6, 0, 0, 500, 300, label="6.1")
        adopted = {"CURVE": json.dumps(result["geometry"], sort_keys=True, separators=(",", ":"))}
        sheets = _boards(1)
        source = source_snapshot([piece], sheets=sheets)
        _strip_geometry(source, "CURVE")
        patched = projection_with_adopted_geometry(projection([piece], sheets=sheets), source, adopted)
        patched["pieces"][0]["geometry_source"] = "cnc_raw_rect"
        snapshot = materialize_plan_snapshot(
            draft=draft_payload(layout_rows([piece])),
            projection=patched,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
            adopted_geometry=adopted,
        )
        outer = snapshot["sheets"][0]["pieces"][0]["geometry"]["outer"]
        self.assertGreater(len(outer), 4)
        self.assertEqual(
            json.loads(snapshot["sheets"][0]["pieces"][0]["special_shape_geometry_json"])["points"],
            result["geometry"]["points"],
        )
        assert_board_editor_manufacturing_ready(snapshot, machine_type="CNC Router", kerf_mm=4.0)

    def test_move_rotation_and_flip_are_applied_once(self):
        piece = _special("A", 1, 100, 80, 400, 300, label="1.2")
        adopted_json = _compiled(((40, 40), (360, 40), (360, 260), (40, 260)), 400, 300)
        sheets = _boards(1, width_mm=4000, length_mm=4000)
        source = source_snapshot([piece], sheets=sheets)
        _strip_geometry(source, "A")
        before = copy.deepcopy(source)
        adopted = {"A": adopted_json}
        layout = layout_rows([piece], A={"x": 250, "y": 180, "rotation": 90})
        layout["pieces"][0]["flip_h"] = True
        patched = projection_with_adopted_geometry(projection([piece], sheets=sheets), source, adopted)
        patched["pieces"][0]["geometry_source"] = "cnc_raw_rect"
        trusted = trusted_model_from_projection(patched, machine_type="CNC Router")
        posed = pose_normalized_layout(normalize_layout(layout, _catalog_from_trusted(trusted)), trusted)
        pose = next(item["outline_mm"] for item in posed["pieces"] if item["piece_instance_id"] == "A")
        snapshot = materialize_plan_snapshot(
            draft=draft_payload(layout),
            projection=patched,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
            adopted_geometry=adopted,
        )
        self.assertEqual(source, before)
        saved = snapshot["sheets"][0]["pieces"][0]
        outer = saved["geometry"]["outer"]
        self.assertEqual(len(outer), len(pose))
        for point in pose:
            self.assertTrue(_contains(outer, (point[0], point[1])), point)
        unposed = [(140.0, 120.0), (460.0, 120.0), (460.0, 340.0), (140.0, 340.0)]
        self.assertFalse(all(_contains(outer, point) for point in unposed))
        door_points = json.loads(saved["special_shape_geometry_json"])["points"]
        self.assertEqual(door_points, json.loads(adopted_json)["points"])
        self.assertEqual((saved["w"], saved["h"]), (40.0, 30.0))
        assert_board_editor_manufacturing_ready(snapshot, machine_type="CNC Router", kerf_mm=4.0)

        reloaded = projection_piece(
            "A",
            1,
            saved["x"] * 10,
            saved["y"] * 10,
            saved["w"] * 10,
            saved["h"] * 10,
            piece_type="Special",
            original_w=40,
            original_h=30,
        )
        reloaded["label"] = "1.2"
        again_source = copy.deepcopy(snapshot)
        again, _patched = _save(
            [reloaded],
            again_source,
            adopted,
            sheets,
            layout_rows([reloaded], A={"x": saved["x"] * 10, "y": saved["y"] * 10, "rotation": 0}),
        )
        self.assertEqual(snapshot, again_source)
        copied = again["sheets"][0]["pieces"][0]["geometry"]["outer"]
        for point in outer:
            self.assertTrue(_contains(copied, (point[0], point[1])), point)
        self.assertEqual(
            json.loads(again["sheets"][0]["pieces"][0]["special_shape_geometry_json"])["points"],
            door_points,
        )

    def test_dxf_export_uses_the_adopted_contour(self):
        piece = _special("4", 4, 0, 0, 1150, 700, sheet=3, label="4.1", original_w=115, original_h=70)
        adopted = {"4": _compiled(INCIDENT_MM, 1150, 700)}
        sheets = _boards(3)
        source = source_snapshot([piece], sheets=sheets)
        _strip_geometry(source, "4")
        patched = projection_with_adopted_geometry(projection([piece], sheets=sheets), source, adopted)
        patched["pieces"][0]["geometry_source"] = "cnc_raw_rect"
        snapshot = materialize_plan_snapshot(
            draft=draft_payload(layout_rows([piece], boards=(3,))),
            projection=patched,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="CP-2026-00088",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
            adopted_geometry=adopted,
        )
        dxf = _real_dxf({"kerf_mm": 4.0, "sheets": snapshot["sheets"]})
        read = read_dxf_geometry_bytes(dxf.encode("utf-8"))
        sheet_height = max(point[1] for point in _layer_points(read["segments"], "SHEET_OUTLINE"))
        exported = [(point[0], sheet_height - point[1]) for point in _layer_points(read["segments"], "GEOMETRY")]
        for point in INCIDENT_MM:
            self.assertTrue(_contains(exported, point), point)
        self.assertFalse(_contains(exported, (0.0, 0.0)))
        self.assertFalse(_contains(exported, (1150.0, 700.0)))

    def test_one_unadopted_special_is_named_and_the_others_stay(self):
        regular = projection_piece("REG", 1, 0, 0, 200, 150)
        regular["label"] = "1.1"
        legacy = projection_piece("LEG", 3, 400, 0, 200, 150, piece_type="Special", original_w=20, original_h=15)
        legacy["label"] = "3.1"
        legacy["geometry_source"] = "persisted_dxf"
        legacy["exact_geometry"] = True
        legacy["special_representation"] = "exact_geometry"
        adopted_piece = _special("OK", 5, 800, 0, 400, 300, label="5.1")
        missing = _special("MISS", 4, 0, 0, 220, 210, sheet=3, label="4.1", original_w=22, original_h=21)
        pieces = [regular, legacy, adopted_piece, missing]
        sheets = _boards(1, 3)
        source = source_snapshot(pieces, sheets=sheets)
        legacy_outer = [[400, 0], [600, 0], [600, 80], [500, 150], [400, 150]]
        for sheet in source["sheets"]:
            for piece in sheet["pieces"]:
                if piece["piece_instance_id"] == "LEG":
                    piece["piece_type"] = "Special"
                    piece["geometry"]["outer"] = [list(point) for point in legacy_outer]
                    piece["special_shape_geometry_json"] = json.dumps(
                        {"version": 1, "kind": "polygon", "units": "cm", "template": "legacy", "exact": True,
                         "points": [[0, 0], [20, 0], [20, 8], [10, 15], [0, 15]]}
                    )
                elif piece["piece_instance_id"] in {"OK", "MISS"}:
                    piece["piece_type"] = "Special"
                    piece.pop("geometry", None)
        adopted = {"OK": _compiled(((30, 30), (370, 30), (370, 270), (30, 270)), 400, 300)}
        layout = layout_rows(pieces, boards=(1, 3))
        proj = projection(pieces, sheets=sheets, elements=None)
        for element in proj["elements"]:
            if element["piece_instance_id"] == "LEG":
                element["geometry"] = {"outer": [list(point) for point in legacy_outer]}
        proj = projection_with_adopted_geometry(proj, source, adopted)
        for piece in proj["pieces"]:
            if piece["piece_instance_id"] == "OK":
                piece["geometry_source"] = "cnc_raw_rect"
        before = copy.deepcopy(source)
        snapshot = materialize_plan_snapshot(
            draft=draft_payload(layout),
            projection=proj,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
            adopted_geometry=adopted,
        )
        self.assertEqual(source, before)
        by_label = {}
        for sheet in snapshot["sheets"]:
            for piece in sheet["pieces"]:
                by_label[piece["label"]] = piece
        self.assertEqual(len(by_label["1.1"]["geometry"]["outer"]), 4)
        self.assertEqual(by_label["1.1"]["piece_type"], "Regular")
        self.assertEqual(len(by_label["3.1"]["geometry"]["outer"]), 5)
        for point in legacy_outer:
            self.assertTrue(_contains(by_label["3.1"]["geometry"]["outer"], tuple(point)))
        self.assertIn("geometry", by_label["5.1"])
        self.assertGreaterEqual(len(by_label["5.1"]["geometry"]["outer"]), 3)
        self.assertNotIn("geometry", by_label["4.1"])
        self.assertEqual((by_label["4.1"]["w"], by_label["4.1"]["h"]), (22.0, 21.0))
        with self.assertRaises(BoardEditorManufacturingError) as caught:
            assert_board_editor_manufacturing_ready(snapshot, machine_type="CNC Router", kerf_mm=4.0)
        self.assertEqual(caught.exception.code, "missing_geometry")
        self.assertEqual(
            [(row["label"], row["sheet_no"]) for row in caught.exception.detail["pieces"]],
            [("4.1", 3)],
        )
        english = format_missing_geometry_message(caught.exception.detail, action="approve", translate=lambda text: text)
        arabic = format_missing_geometry_message(caught.exception.detail, action="approve", translate=_arabic)
        export_ar = format_missing_geometry_message(caught.exception.detail, action="export", translate=_arabic)
        self.assertIn("- Door 4.1 — sheet 3.", english)
        self.assertNotIn("5.1", english)
        self.assertNotIn("1.1", english)
        self.assertIn("- الدرفة 4.1 — اللوح 3.", arabic)
        self.assertIn("تعذر اعتماد خطة القص بسبب عدم اكتمال الهندسة النهائية للدرف التالية:", arabic)
        self.assertIn("تعذر تصدير خطة القص بسبب عدم اكتمال الهندسة النهائية للدرف التالية:", export_ar)
        self.assertNotIn("5.1", arabic)
        catalog = CATALOG.read_text(encoding="utf-8")
        for source_text, translation in ARABIC.items():
            self.assertIn(source_text + "," + translation, catalog)


def _layer_points(segments, layer):
    points = []
    for segment in segments:
        if segment.get("layer") != layer:
            continue
        for key in ("start", "end"):
            point = (float(segment[key][0]), float(segment[key][1]))
            if not any(_near(point, existing) for existing in points):
                points.append(point)
    return points
