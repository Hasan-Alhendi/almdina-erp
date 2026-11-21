"""Manufacturing text stays out of the door contour until it is approved."""

from __future__ import annotations

import unittest

import ezdxf

from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import (
    SCHEMA,
    VERSION,
    document_fingerprint,
    normalize_document,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_compile import (
    compile_manufacturing_geometry,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_copy import (
    clone_drawing_document,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_text import (
    TextGeometryError,
    approved_text_rings,
    layout_text,
    place_outlines,
    pose_rings_once,
    validate_text_export,
    write_text_outline_dxf,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_layer_catalog import (
    CUT_PATH_LAYER,
    GEOMETRY_LAYER,
    TEXT_OUTLINE_LAYER,
)


def _document(paths=None, texts=None):
    document = {
        "schema": SCHEMA,
        "version": VERSION,
        "units": "mm",
        "coordinate_space": "door_local",
        "piece_instance_id": "piece:door-1",
        "blank": {"width_mm": 600, "length_mm": 2100},
        "paths": paths or [],
        "shapes": [],
        "references": [{"id": "ref-1", "file_id": "file-1", "x_mm": 0, "y_mm": 0, "width_mm": 10, "height_mm": 10, "rotation_deg": 0, "opacity": 1, "locked": False, "hidden": False, "calibration": None}],
    }
    if texts is not None:
        document["texts"] = texts
    return document


def _outer():
    nodes = [("n1", 20, 20), ("n2", 580, 20), ("n3", 580, 2080), ("n4", 20, 2080)]
    return {
        "id": "path-outer",
        "role": "manufacturing_outer",
        "closed": True,
        "source_shape_id": None,
        "nodes": [{"id": item[0], "x_mm": item[1], "y_mm": item[2]} for item in nodes],
        "segments": [
            {"id": f"s{index}", "kind": "line", "from_node": nodes[index][0], "to_node": nodes[(index + 1) % 4][0]}
            for index in range(4)
        ],
    }


def _text(content, outlines, **overrides):
    value = {
        "id": "text-1",
        "role": "manufacturing_text",
        "text": content,
        "font_id": "noto-naskh-arabic",
        "font_version": "1",
        "font_size_mm": 20,
        "font_weight": "regular",
        "direction": "auto",
        "align": "right",
        "x_mm": 40,
        "y_mm": 40,
        "rotation_deg": 0,
        "aspect_locked": True,
        "state": "vector",
        "export_approved": False,
        "outlines": outlines,
    }
    value.update(overrides)
    return value


def _stored_outlines(laid, x=40, y=40, rotation=0, text_id="text-1"):
    placed = place_outlines(laid["outlines"], x_mm=x, y_mm=y, rotation_deg=rotation)
    return [
        {
            "id": f"{text_id}-r{index}",
            "points": [{"x_mm": point[0], "y_mm": point[1]} for point in ring],
        }
        for index, ring in enumerate(placed)
    ]


class BoardEditorTextTests(unittest.TestCase):
    def test_old_drawing_without_text_keeps_its_fingerprint(self):
        raw = _document()
        raw.pop("texts", None)
        normalized = normalize_document(raw)
        self.assertNotIn("texts", normalized)
        self.assertEqual(document_fingerprint(raw), document_fingerprint(normalized))

    def test_arabic_english_mixed_joining_and_diacritics(self):
        arabic = layout_text("باب", font_size_mm=20, direction="auto")
        english = layout_text("Door", font_size_mm=20, direction="ltr")
        mixed = layout_text("Door 12 باب", font_size_mm=20, direction="auto")
        marks = layout_text("مَدِينَة", font_size_mm=20, direction="rtl")
        self.assertGreaterEqual(len(arabic["outlines"]), 5)
        self.assertGreater(english["width_mm"], 0)
        self.assertGreater(mixed["width_mm"], english["width_mm"])
        self.assertGreaterEqual(len(marks["outlines"]), len(arabic["outlines"]))
        self.assertNotEqual(arabic["font_size_mm"], arabic["height_mm"])

    def test_letter_curves_do_not_cross_themselves(self):
        samples = ["A", "B", "O", "M", "S", "e", "a", "Malfunction", "Almadina ERP", "معمل المدينة المنورة", "مَدِينَة", "باب", "المدينة 2026 ERP"]
        for sample in samples:
            direction = "ltr" if sample.isascii() else "auto"
            laid = layout_text(sample, font_size_mm=20, direction=direction, align="left")
            self.assertGreater(len(laid["outlines"]), 0, sample)
            for ring in laid["outlines"]:
                self.assertFalse(_self_crosses(ring), sample)

    def test_property_edit_keeps_the_alignment_anchor(self):
        narrow = layout_text("A", font_size_mm=20, direction="ltr", align="left")
        wide = layout_text("WWW", font_size_mm=20, direction="ltr", align="left")
        placed_narrow = place_outlines(narrow["outlines"], x_mm=80, y_mm=40, rotation_deg=0)
        placed_wide = place_outlines(wide["outlines"], x_mm=80, y_mm=40, rotation_deg=0)
        self.assertAlmostEqual(min(point[0] for ring in placed_narrow for point in ring), 80, delta=0.05)
        self.assertAlmostEqual(min(point[0] for ring in placed_wide for point in ring), 80, delta=0.05)
        short = layout_text("ب", font_size_mm=18, direction="rtl", align="right")
        long = layout_text("المدينة", font_size_mm=18, direction="rtl", align="right")
        placed_short = place_outlines(short["outlines"], x_mm=200, y_mm=30, rotation_deg=0)
        placed_long = place_outlines(long["outlines"], x_mm=200, y_mm=30, rotation_deg=0)
        self.assertAlmostEqual(max(point[0] for ring in placed_short for point in ring), 200, delta=0.05)
        self.assertAlmostEqual(max(point[0] for ring in placed_long for point in ring), 200, delta=0.05)

    def test_sheet_pose_is_applied_once_and_only_approved_text_is_attached(self):
        from almdina_erp.almdina_erp.domain.cutting.board_editor_rotation import rotate_point
        from almdina_erp.almdina_erp.domain.cutting.board_editor_text import (
            attach_approved_text_outlines,
            pose_door_rings_to_sheet,
        )

        door = [(0.0, 0.0), (100.0, 0.0), (100.0, 40.0), (0.0, 40.0)]
        center = (50.0, 20.0)
        sheet = [(rotate_point(point, center, 90)[0] + 200.0, rotate_point(point, center, 90)[1] + 300.0) for point in door]
        local = [[(10.0, 10.0), (16.0, 10.0), (16.0, 14.0), (10.0, 14.0)]]
        posed = pose_door_rings_to_sheet(local, door, sheet)
        self.assertEqual(posed, pose_door_rings_to_sheet(local, door, sheet))
        expected = rotate_point((10.0, 10.0), center, 90)
        self.assertAlmostEqual(posed[0][0][0], expected[0] + 200.0, delta=0.05)
        self.assertAlmostEqual(posed[0][0][1], expected[1] + 300.0, delta=0.05)
        laid = layout_text("O", font_size_mm=12, direction="ltr", align="left")
        text = _text("O", _stored_outlines(laid, x=30, y=8), export_approved=True, direction="ltr", align="left", x_mm=30, y_mm=8)
        hidden = _text("A", _stored_outlines(layout_text("A", font_size_mm=12, direction="ltr", align="left"), x=30, y=8, text_id="text-2"), id="text-2", export_approved=False, direction="ltr", align="left", x_mm=30, y_mm=8)
        document = _document([_outer()], [text, hidden])
        snapshot = {
            "sheets": [{
                "pieces": [{
                    "piece_instance_id": "piece:door-1",
                    "original_w": 60,
                    "original_h": 210,
                    "w": 60,
                    "h": 210,
                    "geometry": {"outer": [[20.0, 20.0], [580.0, 20.0], [580.0, 2080.0], [20.0, 2080.0]]},
                }],
            }],
        }
        attached = attach_approved_text_outlines(snapshot, [{"piece_instance_id": "piece:door-1", "drawing_json": document}])
        rings = attached["sheets"][0]["pieces"][0]["approved_text_outlines"]
        self.assertEqual(len(rings), len(text["outlines"]))
        self.assertNotIn("references", str(attached))
        self.assertGreater(min(point[0] for ring in rings for point in ring), 20)

    def test_counters_stay_open_rings(self):
        letter = layout_text("O", font_size_mm=30)
        self.assertEqual(len(letter["outlines"]), 2)
        areas = []
        for ring in letter["outlines"]:
            area = 0.0
            for index, point in enumerate(ring):
                nxt = ring[(index + 1) % len(ring)]
                area += point[0] * nxt[1] - nxt[0] * point[1]
            areas.append(abs(area))
        self.assertGreater(max(areas), min(areas))

    def test_bold_is_wider_than_regular_for_the_same_em(self):
        regular = layout_text("باب", font_size_mm=20, font_weight="regular")
        bold = layout_text("باب", font_size_mm=20, font_weight="bold")
        self.assertGreater(bold["width_mm"], regular["width_mm"])

    def test_missing_font_is_not_replaced(self):
        with self.assertRaises(TextGeometryError) as caught:
            layout_text("باب", font_size_mm=20, font_weight="black")
        self.assertEqual(caught.exception.code, "invalid_font_weight")

    def test_markup_is_rejected(self):
        with self.assertRaises(TextGeometryError) as caught:
            layout_text("<script>alert(1)</script>", font_size_mm=20)
        self.assertEqual(caught.exception.code, "invalid_text")

    def test_convert_pose_and_approval_round_trip(self):
        laid = layout_text("O", font_size_mm=18, align="left")
        outlines = _stored_outlines(laid, x=80, y=80)
        text = _text("O", outlines, align="left")
        moved = _text("O", _stored_outlines(laid, x=120, y=90), x_mm=120, y_mm=90, align="left")
        self.assertNotEqual(text["outlines"][0]["points"][0], moved["outlines"][0]["points"][0])
        document = _document([_outer()], [text])
        compiled = compile_manufacturing_geometry(document, blank_width_mm=600, blank_length_mm=2100)
        self.assertEqual(compiled["status"], "ready")
        self.assertEqual(approved_text_rings(document), [])
        refused = validate_text_export(document, "text-1", blank_width_mm=600, blank_length_mm=2100)
        self.assertEqual(refused["code"], "text_not_vector") if text["state"] != "vector" else self.assertEqual(refused["ok"], True)
        approved = dict(text)
        approved["export_approved"] = True
        approved_document = _document([_outer()], [approved])
        self.assertTrue(validate_text_export(approved_document, "text-1", blank_width_mm=600, blank_length_mm=2100)["ok"])
        outside = dict(approved)
        outside["outlines"] = _stored_outlines(laid, x=0, y=0)
        outside["x_mm"] = 0
        outside["y_mm"] = 0
        self.assertEqual(
            validate_text_export(_document([_outer()], [outside]), "text-1", blank_width_mm=600, blank_length_mm=2100)["code"],
            "text_outside_contour",
        )

    def test_copy_keeps_text_and_drops_reference_images(self):
        laid = layout_text("باب", font_size_mm=16)
        text = _text("باب", _stored_outlines(laid), export_approved=True)
        copied = clone_drawing_document(_document([_outer()], [text]), "piece:copy-1")
        self.assertEqual(copied["texts"][0]["text"], "باب")
        self.assertTrue(copied["texts"][0]["export_approved"])
        self.assertEqual(copied["references"], [])
        self.assertEqual(copied["piece_instance_id"], "piece:copy-1")

    def test_dxf_exports_only_approved_text_outlines(self):
        laid = layout_text("A", font_size_mm=16, direction="ltr", align="left")
        text = _text("A", _stored_outlines(laid), export_approved=True, direction="ltr", align="left")
        hidden = _text(
            "B",
            _stored_outlines(layout_text("B", font_size_mm=16, direction="ltr", align="left"), text_id="text-2"),
            id="text-2",
            export_approved=False,
            text="B",
            direction="ltr",
            align="left",
        )
        dxf_text = write_text_outline_dxf(_document([_outer()], [text, hidden]))
        self.assertIn(TEXT_OUTLINE_LAYER, dxf_text)
        self.assertNotIn(f"\n{GEOMETRY_LAYER}\n", dxf_text)
        self.assertNotIn(f"\n{CUT_PATH_LAYER}\n", dxf_text)
        parsed = ezdxf.read(io_from(dxf_text))
        polylines = list(parsed.modelspace().query(f'LWPOLYLINE[layer=="{TEXT_OUTLINE_LAYER}"]'))
        self.assertEqual(len(polylines), len(text["outlines"]))
        self.assertGreater(len(polylines[0]), 3)
        posed = write_text_outline_dxf(
            _document([_outer()], [text]),
            pose={"pivot": {"x": 300, "y": 1050}, "rotation_deg": 90, "dx_mm": 10, "dy_mm": 0},
        )
        again = write_text_outline_dxf(
            _document([_outer()], [text]),
            pose={"pivot": {"x": 300, "y": 1050}, "rotation_deg": 90, "dx_mm": 10, "dy_mm": 0},
        )
        self.assertEqual(_polyline_points(posed), _polyline_points(again))
        rings = approved_text_rings(_document([_outer()], [text]))
        once = pose_rings_once(rings, {"x": 300, "y": 1050}, 90, 10, 0)
        twice = pose_rings_once(rings, {"x": 300, "y": 1050}, 90, 10, 0)
        self.assertEqual(once, twice)


def _self_crosses(ring):
    count = len(ring)
    for index in range(count):
        start = ring[index]
        end = ring[(index + 1) % count]
        for other in range(index + 1, count):
            if other == index or (other + 1) % count == index or (index + 1) % count == other:
                continue
            left = ring[other]
            right = ring[(other + 1) % count]
            if _crosses(start, end, left, right):
                return True
    return False


def _crosses(a, b, c, d):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def io_from(text):
    import io
    return io.StringIO(text)


def _polyline_points(dxf_text):
    parsed = ezdxf.read(io_from(dxf_text))
    return [
        [(round(point[0], 4), round(point[1], 4)) for point in entity.get_points("xy")]
        for entity in parsed.modelspace().query(f'LWPOLYLINE[layer=="{TEXT_OUTLINE_LAYER}"]')
    ]


if __name__ == "__main__":
    unittest.main()
