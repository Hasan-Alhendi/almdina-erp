"""Write path: materialize a Board Editor Draft into a new Cutting Plan Draft.

Does not approve and never mutates the source plan. Manufacturing CUT_PATH is
generated only after the resulting Cutting Plan is approved and exported.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.cutting.board_editor_plan_create import (
    CreateBoardEditorPlanCommand,
    create_write_allowed,
    execute_create,
    geometry_rejection_parts,
)
from almdina_erp.almdina_erp.infrastructure.frappe.board_editor_plan_create_adapter import (
    FrappeBoardEditorCuttingPlanPort,
    FrappeBoardEditorPlanCreateStore,
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


def _error_message(code: str) -> str:
    messages = {
        "draft_missing": _("Save the board editor distribution before applying it to the cutting plan."),
        "draft_mismatch": _("The selected draft does not match this order and source plan."),
        "order_locked": _("This order is locked and cannot receive an applied cutting plan."),
        "version_conflict": _("The draft changed. Save again, then apply it to the cutting plan."),
        "idempotency_version_conflict": _("This apply request was already used with a different draft version."),
        "source_changed": _("The source plan changed after this draft was saved."),
        "source_plan_missing": _("The source cutting plan was not found for this order."),
        "order_scope": _("The selected cutting plan does not belong to this order."),
        "not_ready": _("The saved distribution is not ready. Review it and fix blocking issues first."),
        "invalid_create_request_id": _("The apply request token is missing or invalid."),
        "create_failed": _("Applying the layout to a cutting plan failed. The saved draft is unchanged."),
        "geometry_rejected": _("The adopted cut outline cannot be manufactured. Fix it in Drawing Mode before copying the plan."),
        "drawing_version_conflict": _("A door drawing changed while the cutting plan copy was being created. Save again and retry."),
        "drawing_copy_failed": _("The drawing could not be copied onto the new cutting plan. The plan was not created."),
        "addon_unproven": _("This door has machining that was not proven against the new cut outline. The copy was not created."),
    }
    return messages.get(code, _("The layout could not be applied to a cutting plan."))


@frappe.whitelist(methods=["POST"])
def create_board_editor_plan_copy(
    order_name: str,
    plan_name: str,
    expected_draft_version: int = 0,
    source_content_revision: str = "",
    source_input_fingerprint: str = "",
    create_request_id: str = "",
    draft_name: str = "",
    drawing_versions: str = "",
) -> dict[str, Any]:
    """Create one Board Editor Cutting Plan Draft from the locked saved draft."""

    order = _authorized_order(order_name)
    _require_use_board_editor(order)
    plan = _load_plan_for_order(order, plan_name)
    order_status = str(getattr(order, "status", "") or "")
    capabilities = _capabilities(order)
    if not create_write_allowed(
        has_edit_capability=_use_board_editor_allowed(order),
        has_plan_view=_plan_view_allowed(order, plan, capabilities),
        order_status=order_status,
    ):
        frappe.throw(
            _("You do not have permission to create a cutting plan copy from this board editor draft."),
            frappe.PermissionError,
        )

    payload = get_board_editor_projection(str(order.name), str(plan.name))
    if str((payload.get("plan") or {}).get("name") or "") != str(plan.name):
        frappe.throw(
            _("The selected cutting plan does not belong to this order."),
            frappe.PermissionError,
        )

    from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
        normalize_content_revision_token,
    )

    live_revision = str((payload.get("plan") or {}).get("content_revision_token") or "")
    live_fingerprint = str((payload.get("plan") or {}).get("input_fingerprint") or "")
    if str(source_content_revision or "") and (
        normalize_content_revision_token(str(source_content_revision))
        != normalize_content_revision_token(live_revision)
    ):
        return {
            "ok": False,
            "code": "source_changed",
            "message": _error_message("source_changed"),
        }
    if str(source_input_fingerprint or "") and str(source_input_fingerprint) != live_fingerprint:
        return {
            "ok": False,
            "code": "source_changed",
            "message": _error_message("source_changed"),
        }

    from almdina_erp.almdina_erp.infrastructure.frappe.board_editor_drawing_store import (
        FrappeBoardEditorDrawingStore,
    )

    drawing_records = FrappeBoardEditorDrawingStore().read_for_plan(str(order.name), str(plan.name))
    expected_versions = _drawing_versions(drawing_versions)
    try:
        result = execute_create(
            CreateBoardEditorPlanCommand(
                order_name=str(order.name),
                source_plan_name=str(plan.name),
                expected_draft_version=int(expected_draft_version or 0),
                source_content_revision=live_revision,
                source_input_fingerprint=live_fingerprint,
                create_request_id=str(create_request_id or ""),
                draft_name=str(draft_name or ""),
            ),
            order_status=order_status,
            projection=payload.get("projection") or {},
            machine_type=str(getattr(plan, "machine_type", "") or ""),
            draft_store=FrappeBoardEditorPlanCreateStore(),
            plan_port=FrappeBoardEditorCuttingPlanPort(),
            drawing_records=drawing_records,
            expected_drawing_versions=expected_versions,
            drawing_store=FrappeBoardEditorDrawingStore(),
        )
    except ValueError as exc:
        code = str(exc)
        return {"ok": False, "code": code, "message": _error_message(code)}
    except frappe.ValidationError as exc:
        # DocType validate / snapshot apply failures must not leave orphans or
        # mutate the editor draft. Surface a create error distinct from save conflicts.
        frappe.clear_messages()
        return {
            "ok": False,
            "code": "create_failed",
            "message": str(exc) or _error_message("create_failed"),
        }

    if not result.get("ok"):
        result["message"] = _error_message(str(result.get("code") or ""))
        if result.get("code") == "geometry_rejected":
            result["message"] = _geometry_message(
                str(result.get("reason") or ""),
                _piece_for_instance(payload.get("projection") or {}, result.get("piece_instance_id")),
            )
        return result

    result["order_name"] = str(order.name)
    result["source_plan_name"] = str(plan.name)
    result["message"] = _(
        "The edited layout was applied as cutting plan {0}. It is not approved."
    ).format(result.get("plan_name") or "")
    result["approves_plan"] = False
    result["exports_plan"] = False
    result["prefer_plan_tab"] = "BoardEditor"
    return result


def _piece_for_instance(projection: dict[str, Any] | None, instance: Any) -> dict[str, Any]:
    wanted = str(instance or "")
    for piece in (projection or {}).get("pieces") or []:
        if isinstance(piece, dict) and str(piece.get("piece_instance_id") or "") == wanted:
            return piece
    return {}


def _geometry_message(reason: str, piece: dict[str, Any] | None) -> str:
    messages = {
        "path_open": _("The cut outline is not closed. Close the path, then validate it again."),
        "self_intersection": _("The cut outline crosses itself. Move the nodes so the edges no longer cross."),
        "outside_blank": _("The cut outline extends outside the door blank. Move the whole path inside the blank."),
        "bounds_not_touched": _("The cut outline must touch all four edges of the door blank. Move it; it will not be scaled automatically."),
        "multiple_outers": _("This door already has a cut outline. Clear the extra one before copying the plan."),
        "invalid_area": _("The cut outline does not enclose a usable area. Redraw a closed shape with area."),
        "holes_unsupported": _("Internal cutouts are not supported by the manufacturing geometry. Clear that role."),
        "zero_edge": _("The cut outline has a zero-length edge. Remove the duplicate node."),
        "curve_unrepresentable": _("This curve cannot be represented within 0.05 mm and the 64-corner manufacturing limit. Simplify it."),
        "non_finite": _("The cut outline contains a value that is not a number. Edit the path and validate again."),
        "addon_unproven": _("This door has machining that was not proven against the new cut outline. The copy was not created."),
    }
    detail = messages.get(reason) or _(
        "The adopted cut outline cannot be manufactured. Fix it in Drawing Mode before copying the plan."
    )
    label, width, height = geometry_rejection_parts(piece)
    if label and width and height:
        return _("Door {0}. Size {1} × {2} cm. {3}").format(label, width, height, detail)
    if label:
        return _("Door {0}. {1}").format(label, detail)
    return detail


def _drawing_versions(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return {"__invalid__": -1}
    if not isinstance(value, dict):
        return {"__invalid__": -1}
    return value


__all__ = ["create_board_editor_plan_copy"]
