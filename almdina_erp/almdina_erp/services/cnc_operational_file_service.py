"""Thin RPC boundary for CNC operational files.

Authorization and the current approved plan are resolved here. Machining
rules stay in the domain, and this module never generates NC text.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.application.cnc.workspace import (
    build_operational_workspace,
    operational_board_layout,
    prepare_sheet_settings,
)
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    OperationalFileError,
    assert_viewed_plan_token,
)
from almdina_erp.almdina_erp.domain.cnc.tool_preset import ToolPresetError
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    document_has_capability,
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cnc_operational_file_repository import (
    approved_plan_ref,
    approved_plan_snapshot,
    factory_operation_defaults,
    known_tool_presets,
    machine_profile_view,
    placed_piece_views,
    save_sheet,
    saved_operational_files,
    sync_status,
)


_NO_APPROVED_PLAN = (
    "This order has no approved cutting plan. Operational files can be prepared "
    "only from the current approved plan, whether the system calculated it or "
    "it was uploaded and then approved."
)
_MESSAGES = {
    "no_approved_plan": _NO_APPROVED_PLAN,
    "draft_plan": _NO_APPROVED_PLAN,
    "plan_not_current": _NO_APPROVED_PLAN,
    "unsupported_plan_source": "This approved plan source cannot be used for operational files.",
    "missing_piece_instance_id": "The approved plan is missing a stable piece identity.",
    "liner_specs_invalid": "The approved plan liner setup cannot be read.",
    "sheet_not_in_plan": "That sheet is not part of the approved cutting plan.",
    "unknown_operation": "That machining operation is not on this sheet.",
    "unknown_path": "That machining path is not on this sheet.",
    "preset_not_found": "The selected CNC tool preset does not exist.",
    "preset_disabled": "The selected CNC tool preset is disabled.",
    "tool_identity_conflict": "One board file must keep the same physical tool number.",
    "tool_diameter_conflict": "The same tool cannot use two diameters in one operational file.",
    "tool_number_invalid": "Tool number must look like T9.",
    "tool_diameter_invalid": "Tool diameter must be a positive number of millimetres within the supported range.",
    "final_depth_invalid": "Final depth must be a positive number of millimetres within the supported range.",
    "spindle_speed_invalid": "Spindle speed must be a positive whole number of RPM within the supported range.",
    "feed_rate_invalid": "Feed rate must be a positive number of millimetres per minute within the supported range.",
    "plunge_rate_invalid": "Plunge rate must be a positive number of millimetres per minute within the supported range.",
    "pass_depth_invalid": "Pass depth must be a positive number of millimetres within the supported range.",
    "pass_depth_exceeds_final_depth": "Pass depth cannot be deeper than the final depth.",
    "operation_order_incomplete": "The operation order does not include every operation on this sheet.",
    "cut_path_early_unconfirmed": "Confirm the warning before saving a cut that comes before the internal operations.",
}


def _message(code: str) -> str:
    return _(_MESSAGES.get(code, _NO_APPROVED_PLAN))


def _authorized_order(order_name: str, capability: str) -> Any:
    name = str(order_name or "").strip()
    if not name or not frappe.db.exists("Door Cutting Order", name):
        frappe.throw(
            _("Door Cutting Order {0} was not found.").format(name or "—"),
            frappe.DoesNotExistError,
        )
    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    require_document_capability(
        order,
        capability,
        message=_("You do not have permission to use operational files for this order."),
    )
    return order


def _workspace_for(order: Any, *, can_prepare: bool) -> dict[str, Any]:
    plan = approved_plan_ref(order)
    try:
        pieces = placed_piece_views(order) if plan is not None else []
        workspace = build_operational_workspace(
            order_name=str(order.name),
            approved_plan=plan,
            plan_is_current=plan is not None,
            pieces=pieces,
            saved_files=saved_operational_files(str(order.name)),
            factory_defaults=factory_operation_defaults(),
            known_presets=known_tool_presets(),
            machine_profile=machine_profile_view(),
            can_prepare=can_prepare,
        )
    except OperationalFileError as exc:
        frappe.throw(_message(exc.code), frappe.ValidationError)
    except json.JSONDecodeError as exc:
        raise frappe.ValidationError(_("The approved plan snapshot cannot be read.")) from exc
    workspace["message"] = _message(workspace["reason_code"]) if workspace["reason_code"] else ""
    try:
        workspace["layout"] = (
            operational_board_layout(approved_plan_snapshot(order))
            if workspace["eligible"]
            else None
        )
    except json.JSONDecodeError as exc:
        raise frappe.ValidationError(_("The approved plan snapshot cannot be read.")) from exc
    for sheet in workspace["sheets"]:
        if sheet["operational_file"]:
            sync_status(sheet["operational_file"], sheet["status"])
    for historical in workspace["historical_files"]:
        if historical["name"]:
            sync_status(historical["name"], historical["status"])
    return workspace


@frappe.whitelist()
def get_cnc_operational_workspace(order_name: str) -> dict[str, Any]:
    order = _authorized_order(order_name, Capability.VIEW_CNC_OPERATIONAL_FILES)
    can_prepare = document_has_capability(
        order,
        Capability.PREPARE_CNC_OPERATIONAL_FILES,
    )
    return _workspace_for(order, can_prepare=can_prepare)


@frappe.whitelist()
def save_cnc_operational_sheet(
    order_name: str,
    sheet_no: int | str,
    operation_presets: str | dict[str, Any] | None = None,
    path_overrides: str | dict[str, Any] | None = None,
    operation_order: str | list[Any] | None = None,
    cut_path_early_confirmed: int | str | bool = 0,
    viewed_plan_token: str | None = None,
) -> dict[str, Any]:
    order = _authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)
    plan = approved_plan_ref(order)
    existing = _existing_sheet(str(order.name), plan, cint(sheet_no))
    parsed_operations = frappe.parse_json(operation_presets) if isinstance(operation_presets, str) else dict(operation_presets or {})
    if path_overrides is None and existing is not None:
        parsed_paths = {
            str(row.get("path_key") or ""): row.get("tool_preset")
            for row in existing.get("paths") or []
            if str(row.get("tool_preset") or "").strip()
        }
    else:
        parsed_paths = frappe.parse_json(path_overrides) if isinstance(path_overrides, str) else dict(path_overrides or {})
    if operation_order is None:
        parsed_order = None
    else:
        parsed_order = frappe.parse_json(operation_order) if isinstance(operation_order, str) else list(operation_order)
    if not isinstance(parsed_operations, dict) or not isinstance(parsed_paths, dict) or (
        parsed_order is not None and not isinstance(parsed_order, list)
    ):
        frappe.throw(_("Operational file settings are not valid."), frappe.ValidationError)
    try:
        assert_viewed_plan_token(plan, viewed_plan_token)
        prepared = prepare_sheet_settings(
            order_name=str(order.name),
            approved_plan=plan,
            plan_is_current=plan is not None,
            pieces=placed_piece_views(order),
            sheet_no=cint(sheet_no),
            existing=existing,
            operation_presets={str(key): value for key, value in parsed_operations.items()},
            path_overrides={str(key): value for key, value in parsed_paths.items()},
            known_presets=known_tool_presets(),
            machine_profile=machine_profile_view(),
            operation_order=None if parsed_order is None else [str(item) for item in parsed_order],
            cut_path_early_confirmed=(
                None if parsed_order is None else bool(cint(cut_path_early_confirmed))
            ),
        )
    except (OperationalFileError, ToolPresetError) as exc:
        frappe.throw(_message(exc.code), frappe.ValidationError)
    existing_name = str((existing or {}).get("name") or "")
    save_sheet(existing_name, prepared)
    return _workspace_for(order, can_prepare=True)


def _existing_sheet(order_name: str, plan: Any, sheet_no: int) -> dict[str, Any] | None:
    if plan is None:
        return None
    for row in saved_operational_files(order_name):
        if (
            row["cutting_plan"] == plan.name
            and int(row["plan_revision"]) == int(plan.revision)
            and int(row["sheet_no"]) == int(sheet_no)
        ):
            return row
    return None


__all__ = [
    "get_cnc_operational_workspace",
    "save_cnc_operational_sheet",
]
