from __future__ import annotations

import ast
import base64
import builtins
import os
import struct
import tempfile
import threading
import unittest
import warnings
import zlib
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFile

from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import (
    document_fingerprint,
    geometry_fingerprint,
    normalize_document,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_reference_image import (
    MAX_IMAGE_EDGE_PX,
    MAX_IMAGE_PIXELS,
    MAX_PNG_BYTES,
    MAX_UPLOAD_BYTES,
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


def _png_header(width: int, height: int) -> bytes:
    """A PNG signature and size, with no pixel data."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", checksum)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


class _LoadSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []
        self._original = ImageFile.ImageFile.load

    def __enter__(self) -> "_LoadSpy":
        calls = self.calls
        original = self._original

        def wrapped(image, *args, **kwargs):
            calls.append((int(image.width), int(image.height)))
            return original(image, *args, **kwargs)

        ImageFile.ImageFile.load = wrapped
        return self

    def __exit__(self, *_args) -> None:
        ImageFile.ImageFile.load = self._original


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
        decode = adapter.split("def decode_reference_image", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("save_file", decode)
        self.assertNotIn("Image.MAX_IMAGE_PIXELS", decode)

    def test_contract_limits_are_unchanged(self) -> None:
        self.assertEqual(MAX_UPLOAD_BYTES, 8 * 1024 * 1024)
        self.assertEqual(MAX_IMAGE_PIXELS, 16_000_000)
        self.assertEqual(MAX_IMAGE_EDGE_PX, 8192)
        self.assertEqual(MAX_PNG_BYTES, 12 * 1024 * 1024)

    def test_supported_rasters_decode_to_png(self) -> None:
        samples = {
            "png": _png(30, 20),
            "jpeg": _encoded("JPEG"),
            "gif": _encoded("GIF"),
            "bmp": _encoded("BMP"),
            "webp": _encoded("WEBP"),
            "tiff": _encoded("TIFF"),
        }
        for kind, payload in samples.items():
            with self.subTest(kind=kind):
                decoded = files.decode_reference_image(payload)
                self.assertTrue(decoded["ok"], decoded)
                self.assertEqual(decoded["format"], kind)
                self.assertTrue(decoded["png"].startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertEqual((decoded["width_px"], decoded["height_px"]), (30, 20))
                self.assertLessEqual(len(decoded["png"]), MAX_PNG_BYTES)

    def test_oversize_file_is_rejected_before_pixel_decode(self) -> None:
        huge = b"\x89PNG\r\n\x1a\n" + (b"x" * MAX_UPLOAD_BYTES)
        with _LoadSpy() as spy:
            decoded = files.decode_reference_image(huge)
        self.assertEqual(decoded["code"], "image_too_large")
        self.assertNotIn("png", decoded)
        self.assertEqual(spy.calls, [])

    def test_header_dimensions_are_rejected_without_loading_pixels(self) -> None:
        cases = {
            "width": _png_header(MAX_IMAGE_EDGE_PX + 1, 1),
            "height": _png_header(1, MAX_IMAGE_EDGE_PX + 1),
            "pixels": _png_header(4000, 4001),
            "small_file_huge_edge": _png_header(9000, 2),
            "decompression_warning": _png_header(10000, 10000),
            "decompression_error": _png_header(20000, 9000),
            "real_wide_png": _png(MAX_IMAGE_EDGE_PX + 1, 1),
        }
        self.assertEqual(4000 * 4001, 16_004_000)
        self.assertLess(len(_png_header(10000, 10000)), 128)
        for name, payload in cases.items():
            with self.subTest(name=name):
                with _LoadSpy() as spy:
                    decoded = files.decode_reference_image(payload)
                self.assertEqual(decoded["code"], "image_too_many_pixels")
                self.assertNotIn("png", decoded)
                self.assertEqual(spy.calls, [])

    def test_corrupt_svg_and_unknown_payloads_store_nothing(self) -> None:
        samples = {
            "corrupt": (b"\x89PNG\r\n\x1a\nbroken", "image_corrupt"),
            "svg": (b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', "svg_not_supported"),
            "unsafe_svg": (b"<svg><script>bad()</script></svg>", "unsafe_svg"),
            "heic": (b"\x00\x00\x00\x18ftypheic" + b"\x00" * 16, "unsupported_image"),
            "text": (b"not-an-image", "unsupported_image"),
        }
        for name, (payload, code) in samples.items():
            with self.subTest(name=name):
                with _LoadSpy() as spy:
                    decoded = files.decode_reference_image(payload)
                self.assertEqual(decoded["code"], code)
                self.assertNotIn("png", decoded)
                self.assertEqual(spy.calls, [])

    def test_output_png_over_the_cap_is_not_returned(self) -> None:
        original = Image.Image.save

        def oversized(self, target, format=None, **kwargs):
            target.write(b"\x00" * (MAX_PNG_BYTES + 1))

        Image.Image.save = oversized
        try:
            decoded = files.decode_reference_image(_png(8, 8))
        finally:
            Image.Image.save = original
        self.assertEqual(decoded["code"], "image_too_large")
        self.assertNotIn("png", decoded)

    def test_multiframe_image_keeps_only_the_first_frame(self) -> None:
        first = Image.new("RGB", (12, 9), (255, 0, 0))
        second = Image.new("RGB", (12, 9), (0, 0, 255))
        payload = BytesIO()
        first.save(payload, format="GIF", save_all=True, append_images=[second], duration=80, loop=0)
        source = Image.open(BytesIO(payload.getvalue()))
        self.assertGreaterEqual(getattr(source, "n_frames", 1), 2)
        source.close()
        decoded = files.decode_reference_image(payload.getvalue())
        self.assertTrue(decoded["ok"], decoded)
        self.assertEqual((decoded["width_px"], decoded["height_px"]), (12, 9))
        stored = Image.open(BytesIO(decoded["png"]))
        self.assertEqual(getattr(stored, "n_frames", 1), 1)
        red, _green, blue, *_rest = stored.convert("RGBA").getpixel((0, 0))
        stored.close()
        self.assertGreater(red, 200)
        self.assertLess(blue, 40)

    def test_pillow_process_limit_is_unchanged_across_requests(self) -> None:
        before = Image.MAX_IMAGE_PIXELS
        filters = list(warnings.filters)
        seen: list[int | None] = []
        stop = threading.Event()

        def watch() -> None:
            while not stop.is_set():
                seen.append(Image.MAX_IMAGE_PIXELS)

        watcher = threading.Thread(target=watch)
        watcher.start()
        try:
            self.assertTrue(files.decode_reference_image(_png(6, 4))["ok"])
            rejected = files.decode_reference_image(_png_header(9000, 2))
        finally:
            stop.set()
            watcher.join(timeout=2)
        self.assertEqual(rejected["code"], "image_too_many_pixels")
        self.assertEqual(Image.MAX_IMAGE_PIXELS, before)
        self.assertEqual(list(warnings.filters), filters)
        self.assertTrue(seen)
        self.assertTrue(all(value == before for value in seen))

    def test_read_rejects_another_plan_without_opening_the_file(self) -> None:
        calls: list[str] = []
        original_size = files.os.path.getsize
        original_open = builtins.open

        def refuse_size(path):
            calls.append("size")
            return original_size(path)

        def refuse_open(path, *args, **kwargs):
            calls.append("open")
            return original_open(path, *args, **kwargs)

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

        original_db = files.frappe.db
        files.frappe.db = Database()
        files.os.path.getsize = refuse_size
        builtins.open = refuse_open
        try:
            result = files.read_reference_png("ORD-1", "PLAN-1", "piece:a", "FILE-OTHER")
        finally:
            files.frappe.db = original_db
            files.os.path.getsize = original_size
            builtins.open = original_open
        self.assertEqual(result, {"ok": False, "code": "reference_unavailable"})
        self.assertEqual(calls, [])

    def test_read_checks_the_file_size_before_reading_bytes(self) -> None:
        payload = _png(4, 3)
        with tempfile.TemporaryDirectory() as temporary:
            path = os.path.join(temporary, "ref.png")
            with open(path, "wb") as handle:
                handle.write(payload)
            opened: list[str] = []
            original_db = files.frappe.db
            original_site = files.frappe.get_site_path
            original_size = files.os.path.getsize
            original_open = builtins.open

            class Database:
                def get_value(self, *_args, **_kwargs):
                    return {
                        "name": "FILE-1",
                        "is_private": 1,
                        "file_url": "/private/files/ref.png",
                        "attached_to_doctype": "Board Editor Drawing Draft",
                        "attached_to_name": reference_owner_name("ORD-1", "PLAN-1", "piece:a"),
                        "attached_to_field": "drawing_reference",
                    }

            def tracking_open(target, *args, **kwargs):
                opened.append(os.fspath(target))
                return original_open(target, *args, **kwargs)

            files.frappe.db = Database()
            files.frappe.get_site_path = lambda *_parts: path
            files.os.path.getsize = lambda target: MAX_PNG_BYTES + 1
            builtins.open = tracking_open
            try:
                rejected = files.read_reference_png("ORD-1", "PLAN-1", "piece:a", "FILE-1")
            finally:
                files.os.path.getsize = original_size
                builtins.open = original_open
            self.assertEqual(rejected, {"ok": False, "code": "reference_unavailable"})
            self.assertFalse(any(item == path for item in opened))

            files.os.path.getsize = original_size
            try:
                accepted = files.read_reference_png("ORD-1", "PLAN-1", "piece:a", "FILE-1")
            finally:
                files.frappe.db = original_db
                files.frappe.get_site_path = original_site
            self.assertTrue(accepted["ok"], accepted)
            self.assertEqual(base64.b64decode(accepted["content_base64"]), payload)
            self.assertNotIn("file_url", accepted)

    def test_failed_validation_does_not_reach_storage(self) -> None:
        service = (APP / "services" / "board_editor_drawing_service.py").read_text(encoding="utf-8")
        upload = service.split("def upload_board_editor_reference_image", 1)[1].split("\ndef ", 1)[0]
        self.assertLess(upload.index('if not decoded.get("ok")'), upload.index("store_reference_png"))
        rejected = files.decode_reference_image(_png_header(MAX_IMAGE_EDGE_PX + 1, 2))
        self.assertEqual(rejected["code"], "image_too_many_pixels")
        self.assertNotIn("png", rejected)


if __name__ == "__main__":
    unittest.main()
