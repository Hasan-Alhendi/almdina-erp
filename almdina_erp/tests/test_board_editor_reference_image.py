from __future__ import annotations

import ast
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import (
    document_fingerprint,
    geometry_fingerprint,
    normalize_document,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_reference_image import (
    apply_image_calibration,
    file_matches_reference_owner,
    initial_placement,
    inspect_reference_bytes,
    reference_file_is_retained,
    reference_owner_name,
)
from almdina_erp.almdina_erp.infrastructure.frappe import board_editor_reference_files as files

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"


def _png(width: int = 40, height: int = 20, color=(10, 20, 30, 255)) -> bytes:
    image = Image.new("RGBA", (width, height), color)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _encoded(kind: str, width: int = 30, height: int = 20) -> bytes:
    image = Image.new("RGB", (width, height), (20, 40, 60))
    output = BytesIO()
    image.save(output, format=kind)
    return output.getvalue()


def _reference(**overrides):
    reference = {
        "x_mm": 0,
        "y_mm": 0,
        "width_mm": 400,
        "height_mm": 600,
        "rotation_deg": 0,
    }
    reference.update(overrides)
    return reference


def _document(reference):
    return {
        "schema": "almdina.board-editor-drawing",
        "version": 1,
        "units": "mm",
        "coordinate_space": "door_local",
        "piece_instance_id": "piece:special",
        "blank": {"width_mm": 600, "length_mm": 2100},
        "paths": [],
        "shapes": [],
        "references": [reference],
    }


class TestBoardEditorReferenceImage(unittest.TestCase):
    def test_magic_bytes_accept_rasters_and_ignore_the_filename(self) -> None:
        payloads = {
            "png": _png(),
            "jpeg": _encoded("JPEG"),
            "gif": _encoded("GIF"),
            "bmp": _encoded("BMP"),
            "webp": _encoded("WEBP"),
            "tiff": _encoded("TIFF"),
        }
        for kind, payload in payloads.items():
            with self.subTest(kind=kind):
                inspected = inspect_reference_bytes(payload)
                self.assertTrue(inspected["ok"], inspected)
                self.assertEqual(inspected["format"], kind)

    def test_non_image_corrupt_and_oversize_payloads_are_rejected(self) -> None:
        self.assertEqual(inspect_reference_bytes(b"not-an-image.png")["code"], "unsupported_image")
        self.assertEqual(inspect_reference_bytes(b"\x89PNG\r\n\x1a\nbroken")["ok"], True)
        decoded = files.decode_reference_image(b"\x89PNG\r\n\x1a\nbroken")
        self.assertEqual(decoded["code"], "image_corrupt")
        huge = b"\x89PNG\r\n\x1a\n" + (b"x" * (8 * 1024 * 1024))
        self.assertEqual(inspect_reference_bytes(huge)["code"], "image_too_large")
        wide = files.decode_reference_image(_png(8193, 1))
        self.assertEqual(wide["code"], "image_too_many_pixels")

    def test_svg_and_heic_are_not_decoded(self) -> None:
        active = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        plain = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
        heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 16
        self.assertEqual(inspect_reference_bytes(active)["code"], "unsafe_svg")
        self.assertEqual(inspect_reference_bytes(plain)["code"], "svg_not_supported")
        self.assertEqual(inspect_reference_bytes(heic)["code"], "unsupported_image")
        self.assertEqual(files.decode_reference_image(active)["code"], "unsafe_svg")
        self.assertNotIn("png", files.decode_reference_image(plain))

    def test_accepted_rasters_become_private_png_without_animation(self) -> None:
        decoded = files.decode_reference_image(_encoded("GIF"))
        self.assertTrue(decoded["ok"])
        self.assertTrue(decoded["png"].startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual((decoded["width_px"], decoded["height_px"]), (30, 20))
        self.assertNotIn("file_url", decoded)

    def test_owner_binding_rejects_another_order_plan_piece_or_purpose(self) -> None:
        owner = reference_owner_name("ORD-1", "PLAN-1", "piece:a")
        row = {
            "is_private": 1,
            "attached_to_doctype": "Board Editor Drawing Draft",
            "attached_to_name": owner,
            "attached_to_field": "drawing_reference",
        }
        self.assertTrue(file_matches_reference_owner(row, order_name="ORD-1", plan_name="PLAN-1", piece_instance_id="piece:a"))
        for order_name, plan_name, piece, field, private in (
            ("ORD-2", "PLAN-1", "piece:a", "drawing_reference", 1),
            ("ORD-1", "PLAN-2", "piece:a", "drawing_reference", 1),
            ("ORD-1", "PLAN-1", "piece:b", "drawing_reference", 1),
            ("ORD-1", "PLAN-1", "piece:a", "other", 1),
            ("ORD-1", "PLAN-1", "piece:a", "drawing_reference", 0),
        ):
            rejected = dict(row, attached_to_field=field, is_private=private)
            self.assertFalse(
                file_matches_reference_owner(
                    rejected,
                    order_name=order_name,
                    plan_name=plan_name,
                    piece_instance_id=piece,
                )
            )

    def test_read_does_not_return_a_private_url_for_an_unproven_file(self) -> None:
        class Database:
            def get_value(self, *_args, **_kwargs):
                return {
                    "name": "FILE-OTHER",
                    "is_private": 1,
                    "file_url": "/private/files/secret.png",
                    "attached_to_doctype": "Board Editor Drawing Draft",
                    "attached_to_name": reference_owner_name("ORD-2", "PLAN-2", "piece:b"),
                    "attached_to_field": "drawing_reference",
                }

        original = files.frappe.db
        files.frappe.db = Database()
        try:
            result = files.read_reference_png("ORD-1", "PLAN-1", "piece:a", "FILE-OTHER")
        finally:
            files.frappe.db = original
        self.assertEqual(result, {"ok": False, "code": "reference_unavailable"})
        self.assertNotIn("file_url", result)
        self.assertNotIn("content_base64", result)

    def test_calibration_scales_about_the_first_point(self) -> None:
        result = apply_image_calibration(_reference(), {"x": 0, "y": 0}, {"x": 200, "y": 0}, 350)
        self.assertTrue(result["ok"], result)
        self.assertEqual((result["width_mm"], result["height_mm"]), (700.0, 1050.0))
        self.assertEqual((result["x_mm"], result["y_mm"]), (0.0, 0.0))
        self.assertEqual(result["calibration"]["known_distance_mm"], 350.0)
        self.assertEqual(result["calibration"]["end_mm"], {"x_mm": 350.0, "y_mm": 0.0})

        rotated = apply_image_calibration(
            _reference(rotation_deg=90),
            {"x": 0, "y": 0},
            {"x": 0, "y": 200},
            350,
        )
        self.assertEqual((rotated["x_mm"], rotated["y_mm"]), (0.0, 0.0))
        self.assertEqual((rotated["width_mm"], rotated["height_mm"]), (700.0, 1050.0))
        self.assertEqual(rotated["calibration"]["end_mm"]["y_mm"], 350.0)

    def test_invalid_calibration_does_not_scale(self) -> None:
        reference = _reference()
        for start, end, known, code in (
            ({"x": 10, "y": 10}, {"x": 10, "y": 10}, 350, "invalid_calibration"),
            ({"x": 0, "y": 0}, {"x": 200, "y": 0}, 0, "invalid_calibration"),
            ({"x": 0, "y": 0}, {"x": 200, "y": 0}, -5, "invalid_calibration"),
            ({"x": 0, "y": 0}, {"x": 200, "y": 0}, "abc", "invalid_calibration"),
            ({"x": -20, "y": 0}, {"x": 200, "y": 0}, 350, "calibration_outside"),
            ({"x": 0, "y": 0}, {"x": 200, "y": 0}, 100000000, "unbounded"),
        ):
            with self.subTest(known=known, code=code):
                result = apply_image_calibration(reference, start, end, known)
                self.assertEqual(result["code"], code)
                self.assertEqual(reference["width_mm"], 400)

    def test_image_only_document_changes_document_fingerprint_only(self) -> None:
        empty = normalize_document(_document({
            "id": "r1",
            "file_id": "FILE-PRIVATE-1",
            "x_mm": 10,
            "y_mm": 20,
            "width_mm": 400,
            "height_mm": 600,
            "rotation_deg": 0,
            "opacity": 0.5,
            "locked": False,
            "hidden": False,
            "calibration": None,
        }))
        self.assertEqual(empty["paths"], [])
        moved = normalize_document(_document({**empty["references"][0], "x_mm": 30}))
        self.assertNotEqual(document_fingerprint(empty), document_fingerprint(moved))
        self.assertEqual(geometry_fingerprint(empty), geometry_fingerprint(moved))
        serialized = str(empty)
        self.assertNotIn("content_base64", serialized)
        self.assertNotIn("data:image", serialized)

    def test_deleted_reference_file_stays_while_an_archive_names_it(self) -> None:
        active = {"references": []}
        archive = {"references": [{"file_id": "FILE-PRIVATE-1"}]}
        self.assertTrue(reference_file_is_retained("FILE-PRIVATE-1", [active, archive]))
        self.assertFalse(reference_file_is_retained("FILE-PRIVATE-1", [active]))

    def test_initial_placement_keeps_aspect_and_opacity(self) -> None:
        placed = initial_placement(600, 2100, 400, 200)
        self.assertEqual(placed["opacity"], 0.5)
        self.assertAlmostEqual(placed["width_mm"] / placed["height_mm"], 2.0, places=3)
        self.assertLess(placed["width_mm"], 600)
        self.assertLess(placed["height_mm"], 2100)

    def test_upload_endpoint_reads_the_open_order_plan_and_piece(self) -> None:
        service = (APP / "services" / "board_editor_drawing_service.py").read_text(encoding="utf-8")
        query = (APP / "services" / "board_editor_query_service.py").read_text(encoding="utf-8")
        tree = ast.parse(service)
        signatures = {
            node.name: [arg.arg for arg in node.args.args]
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertEqual(
            signatures["upload_board_editor_reference_image"],
            ["order_name", "plan_name", "piece_instance_id", "file_name", "content_base64"],
        )
        self.assertEqual(
            signatures["get_board_editor_reference_image"],
            ["order_name", "plan_name", "piece_instance_id", "file_id"],
        )
        upload = service.split("def upload_board_editor_reference_image", 1)[1].split("\ndef ", 1)[0]
        reader = service.split("def get_board_editor_reference_image", 1)[1].split("\ndef ", 1)[0]
        self.assertLess(upload.index("_authorize_drawing"), upload.index("decode_reference_image"))
        self.assertIn("_require_use_board_editor", service)
        self.assertIn("_authorize_drawing(order_name, plan_name, write=False)", reader)
        self.assertIn('frappe.throw(_("Order name is required."), frappe.ValidationError)', query)
        self.assertNotIn("ignore_permissions", service)

    def test_reference_files_do_not_enter_manufacturing_modules(self) -> None:
        domain = (APP / "domain" / "cutting" / "board_editor_reference_image.py").read_text(encoding="utf-8")
        adapter = (APP / "infrastructure" / "frappe" / "board_editor_reference_files.py").read_text(encoding="utf-8")
        plan_create = (APP / "services" / "board_editor_plan_create_service.py").read_text(encoding="utf-8")
        self.assertNotIn("import frappe", domain)
        for name in (
            "layout_json",
            "snapshot_json",
            "special_shape_geometry_json",
            "CUT_PATH",
        ):
            self.assertNotIn(name, domain)
            self.assertNotIn(name, adapter)
        self.assertNotIn("drawing_json", plan_create)
        self.assertNotIn("board_editor_reference", plan_create)
        self.assertIn("content_base64", adapter)
        self.assertNotIn("/private/files/", adapter.split("content_base64", 1)[1])


if __name__ == "__main__":
    unittest.main()
