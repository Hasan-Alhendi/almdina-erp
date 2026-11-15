"""Reference-image rules for a board-editor drawing.

The image is a private visual aid. These checks do not read Frappe, do not
change a piece blank, and do not produce manufacturing geometry.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_persistence import drawing_key

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_EDGE_PX = 8192
MAX_REFERENCE_MM = 100_000.0
REFERENCE_DOCTYPE = "Board Editor Drawing Draft"
REFERENCE_FIELD = "drawing_reference"
QUANTUM_MM = Decimal("0.001")
_SVG_BLOCKED = (
    "script",
    "foreignobject",
    "iframe",
    "embed",
    "object",
    "handler",
    "onload",
    "onclick",
    "onerror",
    "javascript:",
    "xlink:href",
    "href=",
)


def reference_owner_name(order_name: str, plan_name: str, piece_instance_id: str) -> str:
    """Stable file owner. It is the drawing key, not a client-supplied label."""

    return drawing_key(order_name, plan_name, piece_instance_id)


def file_matches_reference_owner(row: Mapping[str, Any], *, order_name: str, plan_name: str, piece_instance_id: str) -> bool:
    private = row.get("is_private") in (1, True, "1")
    return bool(
        private
        and str(row.get("attached_to_doctype") or "") == REFERENCE_DOCTYPE
        and str(row.get("attached_to_name") or "") == reference_owner_name(order_name, plan_name, piece_instance_id)
        and str(row.get("attached_to_field") or "") == REFERENCE_FIELD
    )


def reference_file_is_retained(file_id: str, documents: Sequence[Mapping[str, Any] | None]) -> bool:
    """True when an active drawing or an archive still names the file."""

    identity = str(file_id or "")
    if not identity:
        return False
    for document in documents:
        if not isinstance(document, Mapping):
            continue
        for reference in document.get("references") or []:
            if isinstance(reference, Mapping) and str(reference.get("file_id") or "") == identity:
                return True
    return False


def inspect_reference_bytes(content: bytes) -> dict[str, Any]:
    """Identify a payload by its bytes. The filename is ignored."""

    if not isinstance(content, (bytes, bytearray)) or not content:
        return {"ok": False, "code": "image_corrupt"}
    payload = bytes(content)
    if len(payload) > MAX_UPLOAD_BYTES:
        return {"ok": False, "code": "image_too_large"}
    kind = _magic_kind(payload)
    if kind == "svg":
        lowered = payload[:65536].lower()
        if any(token.encode("ascii") in lowered for token in _SVG_BLOCKED):
            return {"ok": False, "code": "unsafe_svg"}
        return {"ok": False, "code": "svg_not_supported"}
    if kind == "heic":
        return {"ok": False, "code": "unsupported_image"}
    if kind is None:
        return {"ok": False, "code": "unsupported_image"}
    return {"ok": True, "format": kind}


def decoded_within_limits(width_px: int, height_px: int) -> str | None:
    if width_px < 1 or height_px < 1:
        return "image_corrupt"
    if width_px > MAX_IMAGE_EDGE_PX or height_px > MAX_IMAGE_EDGE_PX:
        return "image_too_many_pixels"
    if width_px * height_px > MAX_IMAGE_PIXELS:
        return "image_too_many_pixels"
    return None


def initial_placement(blank_width_mm: float, blank_length_mm: float, pixel_width: int, pixel_height: int) -> dict[str, float]:
    """Fit the image inside the blank, keep its pixel aspect, and center it."""

    aspect = float(pixel_width) / float(pixel_height)
    width = float(blank_width_mm) * 0.8
    height = width / aspect
    if height > float(blank_length_mm) * 0.8:
        height = float(blank_length_mm) * 0.8
        width = height * aspect
    return {
        "x_mm": _quantize((float(blank_width_mm) - width) / 2),
        "y_mm": _quantize((float(blank_length_mm) - height) / 2),
        "width_mm": _quantize(width),
        "height_mm": _quantize(height),
        "rotation_deg": 0.0,
        "opacity": 0.5,
    }


def apply_image_calibration(
    reference: Mapping[str, Any],
    start: Mapping[str, float],
    end: Mapping[str, float],
    known_distance_mm: float,
) -> dict[str, Any]:
    """Scale the image around the first door point. Paths are not an input."""

    try:
        known = float(known_distance_mm)
    except (TypeError, ValueError):
        return {"ok": False, "code": "invalid_calibration"}
    if not math.isfinite(known) or known <= 0:
        return {"ok": False, "code": "invalid_calibration"}
    start_point = _door_point(start)
    end_point = _door_point(end)
    if start_point is None or end_point is None or start_point == end_point:
        return {"ok": False, "code": "invalid_calibration"}
    start_local = _to_local(reference, start_point)
    end_local = _to_local(reference, end_point)
    if not _inside(reference, start_local) or not _inside(reference, end_local):
        return {"ok": False, "code": "calibration_outside"}
    current = math.hypot(end_point[0] - start_point[0], end_point[1] - start_point[1])
    if current <= 0.05:
        return {"ok": False, "code": "invalid_calibration"}
    factor = known / current
    width = _quantize(float(reference["width_mm"]) * factor)
    height = _quantize(float(reference["height_mm"]) * factor)
    if width <= 0 or height <= 0 or width > MAX_REFERENCE_MM or height > MAX_REFERENCE_MM:
        return {"ok": False, "code": "unbounded"}
    rotated = _rotate(start_local[0] * factor, start_local[1] * factor, float(reference.get("rotation_deg") or 0))
    origin_x = _quantize(start_point[0] - rotated[0])
    origin_y = _quantize(start_point[1] - rotated[1])
    if abs(origin_x) > MAX_REFERENCE_MM or abs(origin_y) > MAX_REFERENCE_MM:
        return {"ok": False, "code": "unbounded"}
    scaled_end = _from_local(
        {"x_mm": origin_x, "y_mm": origin_y, "rotation_deg": reference.get("rotation_deg") or 0},
        end_local[0] * factor,
        end_local[1] * factor,
    )
    return {
        "ok": True,
        "x_mm": origin_x,
        "y_mm": origin_y,
        "width_mm": width,
        "height_mm": height,
        "rotation_deg": _quantize(float(reference.get("rotation_deg") or 0)),
        "calibration": {
            "start_mm": {"x_mm": _quantize(start_point[0]), "y_mm": _quantize(start_point[1])},
            "end_mm": {"x_mm": _quantize(scaled_end[0]), "y_mm": _quantize(scaled_end[1])},
            "known_distance_mm": _quantize(known),
        },
    }


def _magic_kind(payload: bytes) -> str | None:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if payload.startswith(b"BM"):
        return "bmp"
    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return "webp"
    if payload.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if len(payload) >= 12 and payload[4:8] == b"ftyp" and payload[8:12] in {b"heic", b"heix", b"heif", b"mif1"}:
        return "heic"
    head = payload[:256].lstrip().lower()
    if head.startswith((b"<svg", b"<?xml", b"<!doctype")) and b"<svg" in payload[:4096].lower():
        return "svg"
    return None


def _door_point(value: Mapping[str, Any] | None) -> tuple[float, float] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        x = float(value.get("x_mm", value.get("x")))
        y = float(value.get("y_mm", value.get("y")))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return (x, y)


def _to_local(reference: Mapping[str, Any], point: tuple[float, float]) -> tuple[float, float]:
    radians = math.radians(float(reference.get("rotation_deg") or 0))
    cosine = math.cos(radians)
    sine = math.sin(radians)
    dx = point[0] - float(reference["x_mm"])
    dy = point[1] - float(reference["y_mm"])
    return (dx * cosine + dy * sine, -dx * sine + dy * cosine)


def _from_local(reference: Mapping[str, Any], local_x: float, local_y: float) -> tuple[float, float]:
    rotated = _rotate(local_x, local_y, float(reference.get("rotation_deg") or 0))
    return (float(reference["x_mm"]) + rotated[0], float(reference["y_mm"]) + rotated[1])


def _rotate(local_x: float, local_y: float, rotation_deg: float) -> tuple[float, float]:
    radians = math.radians(rotation_deg)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return (local_x * cosine - local_y * sine, local_x * sine + local_y * cosine)


def _inside(reference: Mapping[str, Any], local: tuple[float, float]) -> bool:
    return -0.05 <= local[0] <= float(reference["width_mm"]) + 0.05 and -0.05 <= local[1] <= float(reference["height_mm"]) + 0.05


def _quantize(value: float) -> float:
    quantized = Decimal(str(value)).quantize(QUANTUM_MM, rounding=ROUND_HALF_UP)
    result = float(quantized)
    return 0.0 if result == 0 else result
