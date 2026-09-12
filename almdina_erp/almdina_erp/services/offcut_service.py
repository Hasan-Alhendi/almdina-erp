from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutPolicyError,
    canonicalize_snapshot_sources,
    decision_from_business_state,
    decision_from_values,
    offcut_assignment_projection,
    validate_source_resource_homogeneity,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import APPROVED, DRAFT
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    latest_plan,
)


_ASSIGNMENT_FIELDS = frozenset({"piece_instance_id", "business_state"})


def _parse_assignments(value: Any) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError) as exc:
        raise OffcutPolicyError("invalid_offcut_assignments") from exc
    if not isinstance(parsed, list) or not parsed:
        raise OffcutPolicyError("offcut_assignments_required")
    if any(not isinstance(row, dict) for row in parsed):
        raise OffcutPolicyError("invalid_offcut_assignment")
    return parsed


def _throw_policy_error(error: OffcutPolicyError) -> None:
    messages = {
        "offcut_assignments_required": "يجب تحديد قطعة نقص واحدة على الأقل.",
        "invalid_offcut_assignments": "بيانات تصنيف قطع النقص غير صالحة.",
        "invalid_offcut_assignment": "أحد تصنيفات قطع النقص غير صالح.",
        "duplicate_offcut_assignment": "تكررت هوية قطعة النقص في الطلب.",
        "unsupported_offcut_assignment_field": "طلب التصنيف يحتوي حقلاً غير مسموح.",
        "offcut_piece_not_found": "هوية قطعة النقص غير موجودة في الخطة الحالية.",
        "offcut_snapshot_piece_not_found": "هوية قطعة النقص غير موجودة في لقطة الخطة الحالية.",
        "offcut_plan_snapshot_mismatch": "قطع الخطة لا تتطابق مع لقطة الخطة الحالية.",
        "offcut_resource_mismatch": "تصنيف مورد القطعة غير متوافق داخل الخطة الحالية.",
        "mixed_full_board_offcut_source": "لا يمكن أن يجمع مصدر واحد بين لوح كامل وقطع نقص.",
        "offcut_assignment_requires_offcut_piece": "لا يمكن تصنيف قطعة لوح كامل كقطعة نقص.",
        "full_board_offcut_classification_forbidden": "لا يمكن إسناد حالة نقص إلى قطعة لوح كامل.",
        "factory_source_customer_execution_forbidden": "حالة فضلة المعمل مع التنفيذ عند الزبون غير موجودة.",
    }
    code = str(error).split(":", 1)[0]
    frappe.throw(_(messages.get(code, "بيانات تصنيف قطع النقص غير صالحة.")), frappe.ValidationError)


def _current_classifiable_plan(plan_name: str, capability: str) -> tuple[Any, Any]:
    name = str(plan_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد خطة القص."), frappe.ValidationError)

    frappe.db.sql(
        "SELECT name FROM `tabCutting Plan` WHERE name = %s FOR UPDATE",
        (name,),
    )
    plan = frappe.get_doc("Cutting Plan", name)
    order = frappe.get_doc("Door Cutting Order", plan.door_cutting_order)
    require_cutting_plan_capability(
        order,
        capability,
        message=_("لا تملك صلاحية تحديد مصدر وتنفيذ قطع النقص لهذه الخطة."),
    )
    if str(getattr(plan, "plan_kind", None) or "Order") != "Order":
        frappe.throw(_("تصنيف قطع النقص متاح لخطة الطلب الحالية فقط."), frappe.ValidationError)

    status = str(getattr(plan, "status", None) or "")
    if status == APPROVED:
        if str(getattr(order, "approved_plan", None) or "") != plan.name:
            frappe.throw(_("لا يمكن تعديل تصنيف نسخة خطة تاريخية."), frappe.ValidationError)
        return plan, order

    if status != DRAFT or cint(getattr(plan, "plan_needs_recalculation", 0)):
        frappe.throw(_("لا يمكن تعديل تصنيف خطة قديمة أو غير حالية."), frappe.ValidationError)

    current = latest_plan(
        order.name,
        status=DRAFT,
        source_type=str(getattr(plan, "source_type", None) or ""),
    )
    if not current or current.name != plan.name:
        frappe.throw(_("لا يمكن تعديل تصنيف نسخة خطة تاريخية."), frappe.ValidationError)
    return plan, order


def _unique_plan_pieces(plan: Any) -> dict[str, Any]:
    indexed: dict[str, Any] = {}
    for row in plan.placed_pieces or []:
        identity = str(getattr(row, "piece_instance_id", None) or "").strip()
        if not identity or identity in indexed:
            frappe.throw(
                _("لا يمكن تعديل التصنيف لأن هويات القطع في الخطة غير صالحة."),
                frappe.ValidationError,
            )
        indexed[identity] = row
    return indexed


def _unique_snapshot_pieces(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for sheet in snapshot.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            identity = str(piece.get("piece_instance_id") or "").strip()
            if not identity or identity in indexed:
                frappe.throw(
                    _("لا يمكن تعديل التصنيف لأن لقطة الخطة تحتوي هويات قطع غير صالحة."),
                    frappe.ValidationError,
                )
            indexed[identity] = piece
    return indexed


def _normalize_assignments(
    rows: list[dict[str, Any]],
    plan_pieces: dict[str, Any],
    snapshot_pieces: dict[str, dict[str, Any]],
) -> dict[str, dict[str, str]]:
    normalized: dict[str, dict[str, str]] = {}
    for item in rows:
        if set(item) - _ASSIGNMENT_FIELDS:
            raise OffcutPolicyError("unsupported_offcut_assignment_field")
        identity = str(item.get("piece_instance_id") or "").strip()
        if identity in normalized:
            raise OffcutPolicyError(f"duplicate_offcut_assignment:{identity}")
        row = plan_pieces.get(identity)
        if row is None:
            raise OffcutPolicyError(f"offcut_piece_not_found:{identity}")
        snapshot_piece = snapshot_pieces.get(identity)
        if snapshot_piece is None:
            raise OffcutPolicyError(f"offcut_snapshot_piece_not_found:{identity}")

        row_kind = str(getattr(row, "resource_kind", None) or "FULL_BOARD").upper()
        snapshot_kind = str(snapshot_piece.get("resource_kind") or "FULL_BOARD").upper()
        if row_kind != snapshot_kind:
            raise OffcutPolicyError(f"offcut_resource_mismatch:{identity}")
        if row_kind != "OFFCUT":
            raise OffcutPolicyError(f"offcut_assignment_requires_offcut_piece:{identity}")

        decision = decision_from_business_state(row_kind, item.get("business_state"))
        normalized[identity] = {
            "offcut_source_party": decision.source_party.value,
            "offcut_execution_party": decision.execution_party.value,
        }
    return normalized


def _assert_plan_snapshot_compatibility(
    plan_pieces: dict[str, Any],
    snapshot_pieces: dict[str, dict[str, Any]],
) -> None:
    if set(plan_pieces) != set(snapshot_pieces):
        raise OffcutPolicyError("offcut_plan_snapshot_mismatch")
    for identity, row in plan_pieces.items():
        row_kind = str(getattr(row, "resource_kind", None) or "FULL_BOARD").upper()
        snapshot_kind = str(
            snapshot_pieces[identity].get("resource_kind") or "FULL_BOARD"
        ).upper()
        if row_kind != snapshot_kind:
            raise OffcutPolicyError(f"offcut_resource_mismatch:{identity}")


def _source_business_projection(snapshot: dict[str, Any]) -> dict[str, dict[str, str]]:
    validate_source_resource_homogeneity(snapshot.get("sheets") or [])
    for sheet in snapshot.get("sheets") or []:
        pieces = list(sheet.get("pieces") or [])
        if not pieces:
            continue
        source_kind = str(sheet.get("resource_kind") or "FULL_BOARD").upper()
        piece_kind = str(pieces[0].get("resource_kind") or "FULL_BOARD").upper()
        if source_kind != piece_kind:
            raise OffcutPolicyError("offcut_resource_mismatch")
    canonicalize_snapshot_sources(snapshot)
    return {
        str(sheet.get("sheet_no")): {
            "offcut_source_party": str(sheet.get("offcut_source_party") or "UNASSIGNED"),
            "offcut_execution_party": str(sheet.get("offcut_execution_party") or "UNASSIGNED"),
        }
        for sheet in snapshot.get("sheets") or []
        if str(sheet.get("resource_kind") or "FULL_BOARD").upper() == "OFFCUT"
    }


@frappe.whitelist()
def set_offcut_execution_owner(plan_name: str, assignments: Any) -> dict[str, Any]:
    """Classify OFFCUT physical pieces without changing geometry or approval."""

    plan, _order = _current_classifiable_plan(
        plan_name,
        Capability.SET_OFFCUT_EXECUTION_OWNER,
    )
    try:
        rows = _parse_assignments(assignments)
        plan_pieces = _unique_plan_pieces(plan)
        snapshot = frappe.parse_json(plan.snapshot_json or "{}") or {}
        snapshot_pieces = _unique_snapshot_pieces(snapshot)
        _assert_plan_snapshot_compatibility(plan_pieces, snapshot_pieces)
        normalized = _normalize_assignments(rows, plan_pieces, snapshot_pieces)
    except OffcutPolicyError as error:
        _throw_policy_error(error)
        raise AssertionError("unreachable") from error

    # Validate everything before the first DB write. Classification mutates only
    # OFFCUT business fields; resource allocation, price and approval stay intact.
    for identity, values in normalized.items():
        snapshot_pieces[identity].update(values)
    source_projection = _source_business_projection(snapshot)

    for identity, values in normalized.items():
        frappe.db.set_value(
            "Cutting Plan Piece",
            plan_pieces[identity].name,
            values,
            update_modified=False,
        )
    for source in plan.sources or []:
        values = source_projection.get(str(source.sheet_no))
        if values is not None:
            frappe.db.set_value(
                "Cutting Plan Source",
                source.name,
                values,
                update_modified=False,
            )
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
        "approved_by": getattr(plan, "approved_by", None),
        "approved_on": getattr(plan, "approved_on", None),
        "approval_preserved": True,
        "assignments": [
            offcut_assignment_projection(snapshot_pieces[identity])
            for identity in normalized
        ],
    }


@frappe.whitelist()
def set_offcut_group_price(plan_name: str, offcut_price_usd: float | None = None) -> dict[str, Any]:
    """ALMADINA-178 boundary kept separate from OFFCUT classification."""

    plan, _order = _current_classifiable_plan(plan_name, Capability.EDIT_COST_SETTINGS)
    price = flt(offcut_price_usd)
    if price < 0:
        frappe.throw(_("سعر الفضلة لا يمكن أن يكون سالبًا."), frappe.ValidationError)
    has_factory_offcut = any(
        decision_from_values(
            getattr(piece, "resource_kind", None),
            getattr(piece, "offcut_source_party", None),
            getattr(piece, "offcut_execution_party", None),
        ).source_party.value == "FACTORY"
        for piece in (plan.placed_pieces or [])
    )
    if price and not has_factory_offcut:
        frappe.throw(
            _("سعر الفضلة يُستخدم فقط عندما يكون المصدر والتنفيذ من المعمل."),
            frappe.ValidationError,
        )
    frappe.db.set_value(
        "Cutting Plan",
        plan.name,
        "offcut_price_usd",
        price,
        update_modified=True,
    )
    return {"cutting_plan": plan.name, "offcut_price_usd": price}


__all__ = ["set_offcut_execution_owner", "set_offcut_group_price"]
