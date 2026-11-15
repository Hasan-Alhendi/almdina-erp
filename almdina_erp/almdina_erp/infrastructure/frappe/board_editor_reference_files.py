"""Private reference images for one board-editor drawing.

Bytes are stored as a private File owned by the drawing key. The drawing
document keeps the file id only. This module does not write a cutting plan.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from io import BytesIO
from typing import Any

import frappe

from almdina_erp.almdina_erp.domain.cutting.board_editor_reference_image import (
    MAX_IMAGE_PIXELS,
    REFERENCE_DOCTYPE,
    REFERENCE_FIELD,
    decoded_within_limits,
    file_matches_reference_owner,
    inspect_reference_bytes,
    reference_owner_name,
)


def decode_reference_image(content: bytes) -> dict[str, Any]:
    """Decode the first frame to a PNG. SVG and unknown types never reach Pillow."""

    inspected = inspect_reference_bytes(content)
    if not inspected.get("ok"):
        return inspected
    try:
        from PIL import Image
        from PIL.Image import DecompressionBombError
    except ImportError:
        return {"ok": False, "code": "image_decode_unavailable"}
    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(BytesIO(content)) as image:
            image.seek(0)
            image.load()
            limit = decoded_within_limits(int(image.width), int(image.height))
            if limit:
                return {"ok": False, "code": limit}
            frame = image.convert("RGBA")
            width_px = int(frame.width)
            height_px = int(frame.height)
            output = BytesIO()
            frame.save(output, format="PNG")
            png = output.getvalue()
    except DecompressionBombError:
        return {"ok": False, "code": "image_too_many_pixels"}
    except Exception:
        return {"ok": False, "code": "image_corrupt"}
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit
    if len(png) > 12 * 1024 * 1024:
        return {"ok": False, "code": "image_too_large"}
    return {
        "ok": True,
        "format": inspected["format"],
        "width_px": width_px,
        "height_px": height_px,
        "png": png,
    }


def proven_reference_file_ids(order_name: str, plan_name: str, piece_instance_id: str) -> tuple[str, ...]:
    piece = str(piece_instance_id or "").strip()
    if not piece or not frappe.db:
        return ()
    owner = reference_owner_name(order_name, plan_name, piece)
    rows = frappe.db.sql(
        """
        SELECT name, is_private, attached_to_doctype, attached_to_name, attached_to_field
        FROM `tabFile`
        WHERE attached_to_doctype=%s AND attached_to_name=%s AND attached_to_field=%s
        """,
        (REFERENCE_DOCTYPE, owner, REFERENCE_FIELD),
    )
    proven: list[str] = []
    for name, private, doctype, attached_name, field in rows:
        if file_matches_reference_owner(
            {
                "is_private": private,
                "attached_to_doctype": doctype,
                "attached_to_name": attached_name,
                "attached_to_field": field,
            },
            order_name=order_name,
            plan_name=plan_name,
            piece_instance_id=piece,
        ):
            proven.append(str(name))
    return tuple(proven)


def store_reference_png(order_name: str, plan_name: str, piece_instance_id: str, png: bytes) -> str:
    from frappe.utils.file_manager import save_file

    owner = reference_owner_name(order_name, plan_name, piece_instance_id)
    file_doc = save_file(
        "drawing-reference.png",
        png,
        REFERENCE_DOCTYPE,
        owner,
        is_private=1,
    )
    frappe.db.set_value("File", file_doc.name, "attached_to_field", REFERENCE_FIELD)
    return str(file_doc.name)


def read_reference_png(order_name: str, plan_name: str, piece_instance_id: str, file_id: str) -> dict[str, Any]:
    identity = str(file_id or "").strip()
    if not identity or not frappe.db:
        return {"ok": False, "code": "reference_unavailable"}
    row = frappe.db.get_value(
        "File",
        identity,
        ["name", "is_private", "file_url", "attached_to_doctype", "attached_to_name", "attached_to_field"],
        as_dict=True,
    )
    if not isinstance(row, Mapping) or not file_matches_reference_owner(
        row,
        order_name=order_name,
        plan_name=plan_name,
        piece_instance_id=piece_instance_id,
    ):
        return {"ok": False, "code": "reference_unavailable"}
    file_url = str(row.get("file_url") or "")
    if not file_url.startswith("/private/files/"):
        return {"ok": False, "code": "reference_unavailable"}
    path = frappe.get_site_path("private", "files", os.path.basename(file_url))
    try:
        with open(path, "rb") as handle:
            content = handle.read()
    except OSError:
        return {"ok": False, "code": "reference_unavailable"}
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        return {"ok": False, "code": "reference_unavailable"}
    return {
        "ok": True,
        "file_id": identity,
        "content_type": "image/png",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }
