from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt

from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutPolicyError,
    decision_from_values,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)


def _parse_assignments(value: Any) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError) as exc:
        raise OffcutPolicyError("invalid_offcut_assignments") from exc
    if not isinstance(parsed, list) or not parsed:
        raise OffcutPolicyError("offcut_assignments_required")
    return [row for row in parsed if isinstance(row, dict)]


@frappe.whitelist()
def set_offcut_execution_owner(
    plan_name: str,
    assignments: Any,
    offcut_price_usd: float | None = None,
) -> dict[str, Any]:
    """Set OFFCUT source/execution parties without reopening plan approval.

    This command deliberately accepts only classification fields. Geometry,
    placement, quantities, edges and approval state are never writable here.
    """
    plan = frappe.get_doc("Cutting Plan", plan_name)
    order = frappe.get_doc("Door Cutting Order", plan.door_cutting_order)
    require_cutting_plan_capability(
        order,
        Capability.SET_OFFCUT_EXECUTION_OWNER,
        message=_("لا تملك صلاحية تحديد مصدر وتنفيذ النقص لهذه الخطة."),
    )
    rows = _parse_assignments(assignments)
    by_identity = {
        str(row.piece_instance_id or "").strip(): row
        for row in (plan.placed_pieces or [])
        if str(row.piece_instance_id or "").strip()
    }
    if len(by_identity) != len(plan.placed_pieces or []):
        frappe.throw(_("توجد قطعة في الخطة بلا هوية فيزيائية ثابتة."), frappe.ValidationError)

    normalized: dict[str, dict[str, str]] = {}
    for item in rows:
        identity = str(item.get("piece_instance_id") or "").strip()
        if identity not in by_identity:
            frappe.throw(_("هوية قطعة النقص غير موجودة في الخطة."), frappe.ValidationError)
        try:
            decision = decision_from_values(
                item.get("resource_kind") or by_identity[identity].resource_kind,
                item.get("source_party") or item.get("offcut_source_party"),
                item.get("execution_party") or item.get("offcut_execution_party"),
            )
        except OffcutPolicyError as exc:
            frappe.throw(_("تركيبة مصدر وتنفيذ النقص غير مسموحة: {0}").format(exc), frappe.ValidationError)
        if not decision.is_offcut:
            frappe.throw(
                _("صلاحية تحديد مصدر وتنفيذ النقص لا تعدّل القطع الكاملة."),
                frappe.ValidationError,
            )
        normalized[identity] = {
            "resource_kind": decision.resource_kind.value,
            "offcut_source_party": decision.source_party.value,
            "offcut_execution_party": decision.execution_party.value,
        }

    has_factory_offcut = any(
        values["resource_kind"] == "OFFCUT"
        and values["offcut_source_party"] == "FACTORY"
        and values["offcut_execution_party"] == "FACTORY"
        for values in normalized.values()
    )

    snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
    snapshot_pieces = {
        str(piece.get("piece_instance_id") or ""): piece
        for sheet in (snapshot.get("sheets") or [])
        for piece in (sheet.get("pieces") or [])
    }
    for identity, values in normalized.items():
        row = by_identity[identity]
        row_values = {**values}
        frappe.db.set_value("Cutting Plan Piece", row.name, row_values, update_modified=False)
        if identity in snapshot_pieces:
            snapshot_pieces[identity].update(values)

    # Re-project each physical source from its pieces. A source containing at
    # least one FULL_BOARD piece still consumes one board; an OFFCUT-only
    # source never receives a visible board number or board cost.
    for sheet in snapshot.get("sheets") or []:
        pieces = sheet.get("pieces") or []
        full_board_present = any(
            str(piece.get("resource_kind") or "FULL_BOARD").upper() == "FULL_BOARD"
            for piece in pieces
        )
        source_kind = "FULL_BOARD" if full_board_present else "OFFCUT"
        sheet["resource_kind"] = source_kind
        if source_kind == "FULL_BOARD":
            sheet["source_type"] = "Full Board"
            sheet["offcut_source_party"] = "UNASSIGNED"
            sheet["offcut_execution_party"] = "UNASSIGNED"
        elif pieces:
            first = pieces[0]
            sheet["source_type"] = "Full Board"
            sheet["offcut_source_party"] = first.get("offcut_source_party") or "UNASSIGNED"
            sheet["offcut_execution_party"] = first.get("offcut_execution_party") or "UNASSIGNED"

    plan.required_boards = sum(
        1 for sheet in (snapshot.get("sheets") or [])
        if str(sheet.get("resource_kind") or "FULL_BOARD").upper() == "FULL_BOARD"
    )
    source_rows = {str(row.sheet_no): row for row in (plan.sources or [])}
    for sheet in snapshot.get("sheets") or []:
        row = source_rows.get(str(sheet.get("sheet_no")))
        if not row:
            continue
        row.resource_kind = sheet.get("resource_kind") or "FULL_BOARD"
        row.source_type = "Full Board"
        row.offcut_source_party = sheet.get("offcut_source_party") or "UNASSIGNED"
        row.offcut_execution_party = sheet.get("offcut_execution_party") or "UNASSIGNED"
        frappe.db.set_value(
            "Cutting Plan Source",
            row.name,
            {
                "resource_kind": row.resource_kind,
                "source_type": row.source_type,
                "offcut_source_party": row.offcut_source_party,
                "offcut_execution_party": row.offcut_execution_party,
            },
            update_modified=False,
        )
    frappe.db.set_value("Cutting Plan", plan.name, "required_boards", plan.required_boards, update_modified=False)

    if offcut_price_usd is not None:
        if flt(offcut_price_usd) < 0:
            frappe.throw(_("سعر الفضلة لا يمكن أن يكون سالبًا."), frappe.ValidationError)
        if flt(offcut_price_usd) and not has_factory_offcut:
            frappe.throw(
                _("سعر الفضلة يُستخدم فقط عندما يكون المصدر والتنفيذ من المعمل."),
                frappe.ValidationError,
            )
        plan.offcut_price_usd = flt(offcut_price_usd)
        frappe.db.set_value("Cutting Plan", plan.name, "offcut_price_usd", plan.offcut_price_usd, update_modified=False)
    elif not has_factory_offcut and flt(getattr(plan, "offcut_price_usd", 0)):
        plan.offcut_price_usd = 0
        frappe.db.set_value("Cutting Plan", plan.name, "offcut_price_usd", 0, update_modified=False)

    frappe.db.set_value(
        "Cutting Plan",
        plan.name,
        "snapshot_json",
        frappe.as_json(snapshot),
        update_modified=True,
    )
    return {
        "cutting_plan": plan.name,
        "status": plan.status,
        "approval_preserved": True,
        "assignments": normalized,
        "offcut_price_usd": flt(getattr(plan, "offcut_price_usd", 0)),
    }


__all__ = ["set_offcut_execution_owner"]
