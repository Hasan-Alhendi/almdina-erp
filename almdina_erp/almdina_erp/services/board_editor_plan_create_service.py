"""Write path: materialize a Board Editor Draft into a new Cutting Plan Draft.

Does not approve and never mutates the source plan. Manufacturing CUT_PATH is
generated only after the resulting Cutting Plan is approved and exported.
"""

from __future__ import annotations

from typing import Any, Mapping

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.cutting.board_editor_plan_create import (
    CreateBoardEditorPlanCommand,
    create_write_allowed,
    execute_create,
)
from almdina_erp.almdina_erp.infrastructure.frappe.board_editor_plan_create_adapter import (
    FrappeBoardEditorCuttingPlanPort,
    FrappeBoardEditorPlanCreateStore,
)
from almdina_erp.almdina_erp.services.board_editor_draft_review_service import (
    format_board_editor_review_issue,
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


def _decorate_review_issues(review: Any) -> dict[str, Any] | None:
    if not isinstance(review, Mapping):
        return None
    decorated = dict(review)
    issues = []
    for raw in list(decorated.get("issues") or []):
        if not isinstance(raw, Mapping):
            continue
        issue = dict(raw)
        issue["message"] = str(issue.get("message") or "").strip() or format_board_editor_review_issue(issue)
        issues.append(issue)
    decorated["issues"] = issues
    return decorated


def _blocking_issue_lines(review: Mapping[str, Any] | None) -> list[str]:
    if not review:
        return []
    lines: list[str] = []
    for issue in list(review.get("issues") or []):
        if not isinstance(issue, Mapping):
            continue
        severity = str(issue.get("severity") or "error").strip().lower() or "error"
        if severity not in {"error", "blocking"}:
            continue
        message = str(issue.get("message") or "").strip()
        if message:
            lines.append(message)
        if len(lines) >= 5:
            break
    return lines


def _format_not_ready_message(review: Mapping[str, Any] | None) -> str:
    base = _("The saved distribution is not ready. Review it and fix blocking issues first.")
    details = _blocking_issue_lines(review)
    if not details:
        return base
    return base + "\n\n" + "\n".join(f"• {line}" for line in details)


def _error_message(code: str, review: Mapping[str, Any] | None = None) -> str:
    if code == "not_ready":
        return _format_not_ready_message(review)
    messages = {
        "draft_missing": _("Save the board editor distribution before applying it to the cutting plan."),
        "draft_mismatch": _("The selected draft does not match this order and source plan."),
        "order_locked": _("This order is locked and cannot receive an applied cutting plan."),
        "version_conflict": _("The draft changed. Save again, then apply it to the cutting plan."),
        "idempotency_version_conflict": _("This apply request was already used with a different draft version."),
        "source_changed": _("The source plan changed after this draft was saved."),
        "source_plan_missing": _("The source cutting plan was not found for this order."),
        "order_scope": _("The selected cutting plan does not belong to this order."),
        "invalid_create_request_id": _("The apply request token is missing or invalid."),
        "create_failed": _("Applying the layout to a cutting plan failed. The saved draft is unchanged."),
        "invalid_layout": _("The saved draft is not a valid edit document."),
        "schema": _("The saved draft is not a valid edit document."),
        "forbidden_field": _("The saved draft contains a field that cannot be reviewed."),
        "unknown_sheet": _("The draft uses a board that is not in the source plan."),
        "invalid_distribution": _("The saved draft contains an unsupported distribution state."),
        "forged_host": _("The saved draft changes a glass host that the source does not declare."),
        "missing_piece": _("A required piece is missing from the draft."),
        "duplicate_piece": _("A piece identity is repeated in the draft."),
        "unknown_piece": _("The draft contains a piece that is not in the source plan."),
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
        )
    except ValueError as exc:
        code = str(exc)
        return {"ok": False, "code": code, "message": _error_message(code)}
    except frappe.ValidationError as exc:
        # DocType validate / snapshot apply failures must not leave orphans or
        # mutate the editor draft. Surface a create error distinct from save conflicts.
        frappe.clear_messages()
        detail = str(exc).strip()
        base = _error_message("create_failed")
        return {
            "ok": False,
            "code": "create_failed",
            "message": f"{base}\n\n• {detail}" if detail else base,
        }

    if not result.get("ok"):
        code = str(result.get("code") or "")
        review = _decorate_review_issues(result.get("review"))
        if review is not None:
            result["review"] = review
        result["message"] = _error_message(code, review)
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


__all__ = ["create_board_editor_plan_copy"]
