"""Read and save one vector drawing for a special piece on a cutting plan.

The drawing row is independent of the distribution draft. This module does not
modify Cutting Plan snapshots, order geometry, pricing, or DXF/NC output.
Reference file ids are trusted only after a private File is proven for this
order, source plan, and piece.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.cutting.board_editor_drawing_save import (
    drawing_read_allowed,
    drawing_write_allowed,
    execute_archive_drawings_for_new_source,
    execute_get_drawing,
    execute_get_drawing_archive,
    execute_list_drawings,
    execute_save_drawing,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_persistence import (
    drawing_catalog_from_pieces,
)
from almdina_erp.almdina_erp.domain.orders.lifecycle import LOCKED_ORDER_STATUSES
from almdina_erp.almdina_erp.infrastructure.frappe.board_editor_drawing_store import (
    FrappeBoardEditorDrawingStore,
    drawing_storage_ready,
)
from almdina_erp.almdina_erp.infrastructure.frappe.board_editor_reference_files import (
    decode_reference_image,
    proven_reference_file_ids,
    read_reference_png,
    store_reference_png,
)
from almdina_erp.almdina_erp.services.board_editor_query_service import (
    _authorized_order,
    _capabilities,
    _load_plan_for_order,
    _plan_view_allowed,
    _require_use_board_editor,
    _use_board_editor_allowed,
    get_board_editor_projection,
)


def _authorize_drawing(order_name: str, plan_name: str, *, write: bool):
    order = _authorized_order(order_name)
    _require_use_board_editor(order)
    plan = _load_plan_for_order(order, plan_name)
    order_status = str(getattr(order, "status", "") or "")
    if write and order_status in LOCKED_ORDER_STATUSES:
        return order, plan, order_status, {"ok": False, "code": "order_locked"}
    capabilities = _capabilities(order)
    flags = {
        "has_edit_capability": _use_board_editor_allowed(order),
        "has_plan_view": _plan_view_allowed(order, plan, capabilities),
    }
    allowed = (
        drawing_write_allowed(order_status=order_status, **flags)
        if write
        else drawing_read_allowed(**flags)
    )
    if not allowed:
        frappe.throw(
            _("You do not have permission to save this board editor drawing.")
            if write
            else _("You do not have permission to view this board editor drawing."),
            frappe.PermissionError,
        )
    return order, plan, order_status, None


def _editor_context(
    order: Any,
    plan: Any,
    order_status: str,
    payload: Mapping[str, Any],
    piece_instance_id: str = "",
) -> dict[str, Any]:
    plan_payload = payload.get("plan") or {}
    projection = payload.get("projection") or {}
    pieces = projection.get("pieces") if isinstance(projection, Mapping) else []
    return {
        "order_name": str(order.name),
        "plan_name": str(plan.name),
        "order_status": order_status,
        "has_edit_capability": True,
        "has_plan_view": True,
        "source_input_fingerprint": str(plan_payload.get("input_fingerprint") or ""),
        "source_content_revision": str(plan_payload.get("content_revision_token") or ""),
        "catalog": drawing_catalog_from_pieces(pieces if isinstance(pieces, list) else []),
        "trusted_file_ids": proven_reference_file_ids(str(order.name), str(plan.name), piece_instance_id),
    }


def _load_editor(order_name: str, plan_name: str, order: Any, plan: Any):
    payload = get_board_editor_projection(order_name, plan_name)
    if str((payload.get("plan") or {}).get("name") or "") != str(plan.name):
        frappe.throw(
            _("The selected cutting plan does not belong to this order."),
            frappe.PermissionError,
        )
    return payload


def _storage_unavailable(*, write: bool) -> dict[str, Any]:
    if write:
        return {"ok": False, "code": "storage_not_installed", "storage_ready": False}
    return {
        "ok": True,
        "code": "storage_not_installed",
        "storage_ready": False,
        "present": False,
        "active": False,
        "compatible": True,
        "conflict": None,
        "drawing": None,
        "drawings": [],
        "entries": [],
        "can_edit": False,
    }


@frappe.whitelist(methods=["POST"])
def get_board_editor_drawing(
    order_name: str,
    plan_name: str,
    piece_instance_id: str,
) -> dict[str, Any]:
    """Return one piece drawing when it belongs to the live source."""

    order, plan, order_status, early = _authorize_drawing(order_name, plan_name, write=False)
    if early is not None:
        return early
    if not drawing_storage_ready():
        return _storage_unavailable(write=False)
    payload = _load_editor(order_name, plan_name, order, plan)
    return execute_get_drawing(
        {
            "order_name": str(order.name),
            "plan_name": str(plan.name),
            "piece_instance_id": str(piece_instance_id or ""),
        },
        _editor_context(order, plan, order_status, payload, str(piece_instance_id or "")),
        FrappeBoardEditorDrawingStore(),
    )


@frappe.whitelist(methods=["POST"])
def list_board_editor_drawings(order_name: str, plan_name: str) -> dict[str, Any]:
    """Return drawing metadata for special pieces. Documents stay on get."""

    order, plan, order_status, early = _authorize_drawing(order_name, plan_name, write=False)
    if early is not None:
        return early
    if not drawing_storage_ready():
        result = _storage_unavailable(write=False)
        result["code"] = "storage_not_installed"
        return result
    payload = _load_editor(order_name, plan_name, order, plan)
    result = execute_list_drawings(
        {"order_name": str(order.name), "plan_name": str(plan.name)},
        _editor_context(order, plan, order_status, payload),
        FrappeBoardEditorDrawingStore(),
    )
    result["storage_ready"] = True
    return result


@frappe.whitelist(methods=["POST"])
def save_board_editor_drawing(
    order_name: str,
    plan_name: str,
    piece_instance_id: str,
    expected_drawing_version: int = 0,
    source_content_revision: str = "",
    drawing: Any = None,
) -> dict[str, Any]:
    """Save one structural drawing. Manufacturing validity is not required."""

    order, plan, order_status, early = _authorize_drawing(order_name, plan_name, write=True)
    if early is not None:
        return early
    if not drawing_storage_ready():
        return _storage_unavailable(write=True)
    payload = _load_editor(order_name, plan_name, order, plan)
    return execute_save_drawing(
        {
            "order_name": str(order.name),
            "plan_name": str(plan.name),
            "piece_instance_id": str(piece_instance_id or ""),
            "expected_drawing_version": expected_drawing_version,
            "source_content_revision": str(source_content_revision or ""),
            "drawing": _parse_drawing(drawing),
        },
        _editor_context(order, plan, order_status, payload, str(piece_instance_id or "")),
        FrappeBoardEditorDrawingStore(),
    )


@frappe.whitelist(methods=["POST"])
def get_board_editor_drawing_archive(
    order_name: str,
    plan_name: str,
    piece_instance_id: str,
) -> dict[str, Any]:
    """Return retained drawings for one special piece. They are not the active document."""

    order, plan, order_status, early = _authorize_drawing(order_name, plan_name, write=False)
    if early is not None:
        return early
    if not drawing_storage_ready():
        return _storage_unavailable(write=False)
    payload = _load_editor(order_name, plan_name, order, plan)
    return execute_get_drawing_archive(
        {
            "order_name": str(order.name),
            "plan_name": str(plan.name),
            "piece_instance_id": str(piece_instance_id or ""),
        },
        _editor_context(order, plan, order_status, payload, str(piece_instance_id or "")),
        FrappeBoardEditorDrawingStore(),
    )


def archive_drawings_after_source_begin(
    order: Any,
    plan: Any,
    order_status: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Archive drawings bound to the previous source after a layout begin succeeds.

    A missing drawing table does not fail the layout begin. An archive that
    cannot be stored rolls the request back, including the layout begin, so an
    old drawing is not dropped and is not rebound to the new source.
    """

    if not drawing_storage_ready():
        return {"ok": True, "code": "storage_not_installed", "archived_count": 0}
    live_revision = str((payload.get("plan") or {}).get("content_revision_token") or "")
    result = execute_archive_drawings_for_new_source(
        {
            "order_name": str(order.name),
            "plan_name": str(plan.name),
            "source_content_revision": live_revision,
        },
        _editor_context(order, plan, order_status, payload),
        FrappeBoardEditorDrawingStore(),
    )
    if not result.get("ok"):
        frappe.db.rollback()
    return result


def _drawable_piece(context: Mapping[str, Any], piece_instance_id: str) -> dict[str, Any] | None:
    catalog = context.get("catalog") or {}
    piece = catalog.get(str(piece_instance_id or "")) if isinstance(catalog, Mapping) else None
    if not isinstance(piece, Mapping) or str(piece.get("piece_type") or "") != "Special":
        return None
    return piece


@frappe.whitelist(methods=["POST"])
def upload_board_editor_reference_image(
    order_name: str,
    plan_name: str,
    piece_instance_id: str,
    file_name: str = "",
    content_base64: str = "",
) -> dict[str, Any]:
    """Store one private reference image for this special piece."""

    order, plan, order_status, early = _authorize_drawing(order_name, plan_name, write=True)
    if early is not None:
        return early
    payload = _load_editor(order_name, plan_name, order, plan)
    context = _editor_context(order, plan, order_status, payload, str(piece_instance_id or ""))
    if _drawable_piece(context, str(piece_instance_id or "")) is None:
        return {"ok": False, "code": "piece_not_drawable"}
    encoded = str(content_base64 or "")
    if "," in encoded and encoded.lstrip().startswith("data:"):
        encoded = encoded.split(",", 1)[1]
    if len(encoded) > ((8 * 1024 * 1024 * 4) // 3) + 32:
        return {"ok": False, "code": "image_too_large"}
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return {"ok": False, "code": "image_corrupt"}
    decoded = decode_reference_image(content)
    if not decoded.get("ok"):
        return {"ok": False, "code": decoded.get("code") or "image_corrupt"}
    file_id = store_reference_png(str(order.name), str(plan.name), str(piece_instance_id or ""), decoded["png"])
    return {
        "ok": True,
        "file_id": file_id,
        "width_px": decoded["width_px"],
        "height_px": decoded["height_px"],
        "content_type": "image/png",
        "content_base64": base64.b64encode(decoded["png"]).decode("ascii"),
    }


@frappe.whitelist(methods=["POST"])
def get_board_editor_reference_image(
    order_name: str,
    plan_name: str,
    piece_instance_id: str,
    file_id: str,
) -> dict[str, Any]:
    """Return one proven reference image. A missing file does not change the drawing."""

    order, plan, _order_status, early = _authorize_drawing(order_name, plan_name, write=False)
    if early is not None:
        return early
    _load_editor(order_name, plan_name, order, plan)
    return read_reference_png(str(order.name), str(plan.name), str(piece_instance_id or ""), str(file_id or ""))


@frappe.whitelist(methods=["POST"])
def shape_board_editor_text(
    order_name: str,
    plan_name: str,
    content: str,
    font_size_mm: float,
    font_weight: str = "regular",
    direction: str = "auto",
    align: str = "left",
    x_mm: float = 0,
    y_mm: float = 0,
    rotation_deg: float = 0,
) -> dict[str, Any]:
    """Return pinned-font outlines. This does not save the drawing."""

    _order, _plan, _status, early = _authorize_drawing(order_name, plan_name, write=True)
    if early is not None:
        return early
    from almdina_erp.almdina_erp.domain.cutting.board_editor_text import (
        TextGeometryError,
        layout_text,
        place_outlines,
    )

    try:
        laid = layout_text(
            str(content or ""),
            font_size_mm=float(font_size_mm),
            font_weight=str(font_weight or "regular"),
            direction=str(direction or "auto"),
            align=str(align or "left"),
        )
        placed = place_outlines(
            laid["outlines"],
            x_mm=float(x_mm or 0),
            y_mm=float(y_mm or 0),
            rotation_deg=float(rotation_deg or 0),
        )
    except (TextGeometryError, TypeError, ValueError) as exc:
        code = getattr(exc, "code", "") or "invalid_text"
        return {"ok": False, "code": code}
    return {
        "ok": True,
        "font_id": laid["font_id"],
        "font_version": laid["font_version"],
        "width_mm": laid["width_mm"],
        "height_mm": laid["height_mm"],
        "outlines": [
            [{"x_mm": point[0], "y_mm": point[1]} for point in ring]
            for ring in placed
        ],
    }


@frappe.whitelist(methods=["POST"])
def validate_board_editor_text(
    order_name: str,
    plan_name: str,
    piece_instance_id: str,
    text_id: str,
    drawing: Any,
) -> dict[str, Any]:
    """Check one text element against the door contour. This does not save or approve it."""

    _order, _plan, _status, early = _authorize_drawing(order_name, plan_name, write=True)
    if early is not None:
        return early
    from almdina_erp.almdina_erp.domain.cutting.board_editor_text import validate_text_export

    document = _parse_drawing(drawing)
    if not isinstance(document, dict):
        return {"ok": False, "code": "invalid_text"}
    if str(document.get("piece_instance_id") or "") != str(piece_instance_id or ""):
        return {"ok": False, "code": "piece_not_drawable"}
    blank = document.get("blank") if isinstance(document.get("blank"), dict) else {}
    return validate_text_export(
        document,
        str(text_id or ""),
        blank_width_mm=float(blank.get("width_mm") or 0),
        blank_length_mm=float(blank.get("length_mm") or 0),
    )


def _parse_drawing(drawing: Any) -> Any:
    if isinstance(drawing, str):
        try:
            return json.loads(drawing)
        except ValueError:
            return None
    return drawing


__all__ = [
    "get_board_editor_drawing",
    "get_board_editor_drawing_archive",
    "list_board_editor_drawings",
    "save_board_editor_drawing",
    "upload_board_editor_reference_image",
    "get_board_editor_reference_image",
    "shape_board_editor_text",
    "validate_board_editor_text",
]
