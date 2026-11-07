"""Read-only readiness check for one saved board-editor draft.

The check does not change the draft, the cutting plan, approval, or CUT_PATH.
"""

from __future__ import annotations

from typing import Any, Mapping

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.cutting.board_editor_draft_review import (
    draft_review_allowed,
    review_editor_draft,
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

def _message(code: str) -> str:
    messages = {
        "draft_missing": _("Save a board editor draft before reviewing it."),
        "source_changed": _("The order or source plan changed after this draft was saved."),
        "missing_piece": _("A required piece is missing from the draft."),
        "duplicate_piece": _("A piece identity is repeated in the draft."),
        "unknown_piece": _("The draft contains a piece that is not in the source plan."),
        "piece_excluded": _("A required piece is excluded from the distribution."),
        "piece_outside_board": _("A required piece is outside the boards."),
        "partial_board_overlap": _("A piece crosses the usable edge of its board."),
        "outside_usable_sheet": _("A piece is outside the usable area of its board."),
        "piece_overlap": _("Two pieces overlap."),
        "kerf_clearance": _("The kerf clearance between two pieces is too small."),
        "hole_kerf_clearance": _("A piece inside a glass opening is closer to the material than the kerf allows."),
        "hosting_missing": _("A piece declares a glass host that is not in the distribution."),
        "hosting_cross_sheet": _("A piece and its glass host are on different boards."),
        "hosting_cycle": _("Glass hosting contains a cycle."),
        "hosting_depth": _("Glass hosting is nested deeper than the supported limit."),
        "hosting_not_contained": _("A hosted piece is not inside its glass opening."),
        "rotation_forbidden": _("This piece is not allowed to rotate."),
        "machine_rotation_forbidden": _("This rotation is not allowed for the cutting machine."),
        "machine_rotation_unproven": _("The cutting machine does not support a readiness decision for this angle."),
        "geometry_unproven": _("This piece has no supported geometry, so it cannot be marked ready."),
        "addon_material_conflict": _("A machining add-on conflicts with neighbouring material."),
        "unsupported_sheet_resource": _("A board resource is not a supported full board or offcut."),
        "offcut_unresolved": _("An offcut piece has no resolved execution owner."),
        "mixed_full_board_offcut_source": _(
            "Board {0} mixes GEOMETRY and OFFCUT pieces. Unify the classifications before applying the distribution to a cutting plan."
        ),
        "standard_board_unavailable": _(
            "A new board cannot be created because the order's standard board dimensions are missing or invalid."
        ),
        "invalid_editor_origin": _("The draft marks a board origin that is not supported."),
        "invalid_layout": _("The saved draft is not a valid edit document."),
        "schema": _("The saved draft is not a valid edit document."),
        "forbidden_field": _("The saved draft contains a field that cannot be reviewed."),
        "unknown_sheet": _("The draft uses a board that is not in the source plan."),
        "invalid_distribution": _("The saved draft contains an unsupported distribution state."),
        "forged_host": _("The saved draft changes a glass host that the source does not declare."),
    }
    return messages.get(code, _("The distribution is not ready."))


def _issue_message(issue: Mapping[str, Any]) -> str:
    code = str(issue.get("code") or "")
    kind = str(issue.get("addon_kind") or "").strip()
    reason = str(issue.get("reason") or "").strip()
    if code == "addon_material_conflict":
        if kind and reason:
            return _(
                "The {0} add-on conflicts with neighbouring material ({1})."
            ).format(kind, reason)
        if kind:
            return _("The {0} add-on conflicts with neighbouring material.").format(kind)
        return _message(code)
    if code == "geometry_unproven":
        if kind and reason:
            return _(
                "The {0} add-on has no proven geometry ({1}), so readiness cannot be declared."
            ).format(kind, reason)
        if reason:
            return _(
                "This piece has no supported geometry ({0}), so it cannot be marked ready."
            ).format(reason)
        return _message(code)
    if code == "mixed_full_board_offcut_source":
        sheet_nos = [
            str(number)
            for number in (issue.get("sheet_nos") or [])
            if number not in (None, "")
        ]
        if sheet_nos:
            return _(
                "Board {0} mixes GEOMETRY and OFFCUT pieces. Unify the classifications before applying the distribution to a cutting plan."
            ).format(sheet_nos[0])
        return _(
            "A board mixes GEOMETRY and OFFCUT pieces. Unify the classifications before applying the distribution to a cutting plan."
        )
    return _message(code)


@frappe.whitelist()
def validate_board_editor_draft(order_name: str, plan_name: str) -> dict[str, Any]:
    """Review one saved draft. View permission is required; the check is read-only."""

    order = _authorized_order(order_name)
    _require_use_board_editor(order)
    plan = _load_plan_for_order(order, plan_name)
    if not draft_review_allowed(
        has_board_editor_capability=_use_board_editor_allowed(order),
        has_plan_view=_plan_view_allowed(order, plan, _capabilities(order)),
    ):
        frappe.throw(
            _("You do not have permission to review this board editor draft."),
            frappe.PermissionError,
        )
    payload = get_board_editor_projection(str(order.name), str(plan.name))
    if str((payload.get("plan") or {}).get("name") or "") != str(plan.name):
        frappe.throw(
            _("The selected cutting plan does not belong to this order."),
            frappe.PermissionError,
        )
    result = review_editor_draft(
        draft=payload.get("editor_draft") or {},
        projection=payload.get("projection") or {},
        machine_type=str(getattr(plan, "machine_type", "") or ""),
    )
    result["order_name"] = str(order.name)
    result["plan_name"] = str(plan.name)
    result["approves_plan"] = False
    result["exports_plan"] = False
    for issue in result["issues"]:
        issue["message"] = _issue_message(issue)
    return result


__all__ = ["validate_board_editor_draft"]
