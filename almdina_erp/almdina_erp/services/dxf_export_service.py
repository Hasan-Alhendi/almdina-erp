from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    DxfGeometrySnapshotError,
    DxfTopologyError,
    validate_snapshot_material_layout,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    DRAFT,
    SYSTEM,
    UPLOADED_DXF,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import rects_have_clearance
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_doctype_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    approved_plan_for_order,
    current_working_plan,
    latest_plan,
)
from almdina_erp.almdina_erp.services import export_validation_service as legacy_export
from almdina_erp.almdina_erp.services.order_board_identity import (
    order_board_color,
    order_board_material,
    order_board_thickness_mm,
)


DXF_KERF_NUMERIC_TOLERANCE_CM = 0.01


def _require_export_access(
    *,
    order_name: str | None,
    payload: dict[str, Any] | None,
) -> Any | None:
    """Authorize before geometry or plan data is loaded."""

    if order_name:
        order = frappe.get_doc("Door Cutting Order", order_name)
        order.check_permission("read")
        require_cutting_plan_capability(
            order,
            Capability.EXPORT_DXF,
            message=_("You do not have permission to export this order as DXF."),
        )
        return order

    name = str((payload or {}).get("name") or "").strip()
    if name and frappe.db.exists("Door Cutting Order", name):
        order = frappe.get_doc("Door Cutting Order", name)
        order.check_permission("read")
        require_cutting_plan_capability(
            order,
            Capability.EXPORT_DXF,
            message=_("You do not have permission to export this order as DXF."),
        )
        return order

    require_doctype_capability(
        Capability.EXPORT_DXF,
        message=_("You do not have permission to export an unsaved order as DXF."),
    )
    return None


def _topology_kerf_error(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if code:
        first = getattr(exc, "first_key", None) or "?"
        second = getattr(exc, "second_key", None) or "?"
        return _("DXF topology validation failed ({0}) between pieces {1} and {2}.").format(
            code,
            first,
            second,
        )
    return _("Persisted DXF topology is invalid: {0}").format(str(exc))


def _kerf_errors(snapshot: dict[str, Any], *, fallback_kerf_mm: float = 0.0) -> list[str]:
    required_kerf_cm = max(
        0.0,
        flt(snapshot.get("kerf_cm")) or (max(0.0, flt(fallback_kerf_mm)) / 10.0),
    )

    try:
        if validate_snapshot_material_layout(
            snapshot,
            required_clearance_mm=required_kerf_cm * 10.0,
        ):
            return []
    except (DxfGeometrySnapshotError, DxfTopologyError) as exc:
        return [_topology_kerf_error(exc)]

    if required_kerf_cm <= 0:
        return []

    errors: list[str] = []
    for sheet in snapshot.get("sheets") or []:
        pieces = sheet.get("pieces") or []
        sheet_no = int(sheet.get("sheet_no") or 0)
        for index, first in enumerate(pieces):
            first_rect = {
                "x": flt(first.get("x")),
                "y": flt(first.get("y")),
                "w": flt(first.get("w")),
                "h": flt(first.get("h")),
            }
            for second in pieces[index + 1 :]:
                second_rect = {
                    "x": flt(second.get("x")),
                    "y": flt(second.get("y")),
                    "w": flt(second.get("w")),
                    "h": flt(second.get("h")),
                }
                if rects_have_clearance(
                    first_rect,
                    second_rect,
                    required_kerf_cm,
                    DXF_KERF_NUMERIC_TOLERANCE_CM,
                ):
                    continue
                errors.append(
                    _(
                        "القطعتان {0} و{1} على اللوح رقم {2} لا تحققان مسافة المنشار المطلوبة {3:g} مم."
                    ).format(
                        first.get("label") or first.get("id") or "?",
                        second.get("label") or second.get("id") or "?",
                        sheet_no,
                        required_kerf_cm * 10,
                    )
                )
    return errors


def _assert_export_kerf(snapshot: dict[str, Any], *, fallback_kerf_mm: float = 0.0) -> None:
    errors = _kerf_errors(snapshot, fallback_kerf_mm=fallback_kerf_mm)
    if not errors:
        return
    frappe.throw(
        _(
            "خطة القص الحالية لا تحقق مسافة المنشار (Kerf) المطلوبة بين جميع القطع. "
            "أعد حساب خطة القص ثم صدّر DXF.\n{0}"
        ).format("\n".join(errors))
    )


def _plan_manifest(order: Any, plan: Any) -> dict[str, Any]:
    return {
        "order": order.name,
        "customer": order.customer,
        "revision": cint(plan.revision),
        "cutting_plan": plan.name,
        "plan_kind": plan.plan_kind or "Order",
        "units": "mm",
        "engine_version": plan.engine_version,
        "method_key": plan.method_key,
        "method_label": plan.method_label,
        "sheet_count": len(plan.sources or []),
        "sources": [
            {
                "sheet_no": int(row.sheet_no),
                "source_type": row.source_type,
                "remnant": row.remnant,
                "board_item": row.board_item,
                "material": row.material or "",
                "color": row.color or "",
                "thickness_mm": flt(row.thickness_mm),
                "full_width_mm": flt(row.full_width_mm),
                "full_length_mm": flt(row.full_length_mm),
                "usable_width_mm": flt(row.usable_width_mm),
                "usable_length_mm": flt(row.usable_length_mm),
            }
            for row in (plan.sources or [])
        ],
    }


def _draft_manifest(order: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "order": order.name or "UNSAVED",
        "customer": order.customer,
        "revision": cint(order.revision or 1),
        "cutting_plan": None,
        "plan_kind": "Draft Preview",
        "units": "mm",
        "engine_version": snapshot.get("engine_version"),
        "method_key": snapshot.get("method_key"),
        "method_label": snapshot.get("method_label"),
        "sheet_count": len(snapshot.get("sheets") or []),
        "sources": [
            {
                "sheet_no": int(sheet.get("sheet_no") or index + 1),
                "source_type": sheet.get("source_type") or "Full Board",
                "remnant": sheet.get("remnant"),
                "board_item": getattr(order, "board_item", None),
                "material": sheet.get("material") or order_board_material(order),
                "color": sheet.get("color") or order_board_color(order),
                "thickness_mm": flt(
                    sheet.get("thickness_mm") or order_board_thickness_mm(order)
                ),
                "full_width_mm": flt(sheet.get("full_width_cm")) * 10,
                "full_length_mm": flt(sheet.get("full_length_cm")) * 10,
                "usable_width_mm": flt(sheet.get("usable_width_cm")) * 10,
                "usable_length_mm": flt(sheet.get("usable_length_cm")) * 10,
            }
            for index, sheet in enumerate(snapshot.get("sheets") or [])
        ],
    }


def _canonical_saved_plan(order: Any) -> Any | None:
    approved_name = str(getattr(order, "approved_plan", None) or "").strip()
    if approved_name and frappe.db.exists("Cutting Plan", approved_name):
        approved = frappe.get_doc("Cutting Plan", approved_name)
        if str(approved.door_cutting_order or "") == str(order.name):
            return approved
    return current_working_plan(str(order.name))


def _saved_plan_for_source(order: Any, plan_source: str | None) -> Any | None:
    """Resolve exactly the plan surface the operator chose in the UI.

    Omitting ``plan_source`` keeps the historical export behavior for compatible
    callers. Explicit sources are fail-closed so a System-tab export can never
    silently export an unrelated Approved or Uploaded plan.
    """

    normalized = str(plan_source or "").strip().lower()
    if not normalized:
        return _canonical_saved_plan(order)
    if normalized == "system":
        return latest_plan(order.name, source_type=SYSTEM, status=DRAFT)
    if normalized in {"custom", "uploaded", "uploaded dxf", "uploaded_dxf", "dxf"}:
        return latest_plan(order.name, source_type=UPLOADED_DXF, status=DRAFT)
    if normalized == "approved":
        return approved_plan_for_order(order)
    frappe.throw(_("مصدر خطة القص المحدد للتصدير غير مدعوم."), frappe.ValidationError)
    raise AssertionError("unreachable")


def _required_saved_plan(order: Any, plan_source: str | None = None) -> Any:
    plan = _saved_plan_for_source(order, plan_source)
    if not plan or not str(getattr(plan, "snapshot_json", None) or "").strip():
        source_labels = {
            "system": _("خطة النظام"),
            "custom": _("الخطة المرفوعة"),
            "approved": _("الخطة المعتمدة"),
        }
        selected = source_labels.get(str(plan_source or "").strip().lower(), _("الخطة الحالية"))
        frappe.throw(
            _("لا توجد {0} صالحة للتصدير. جهّز الخطة أولًا ثم حاول مرة أخرى.").format(selected)
        )
    return plan


@frappe.whitelist()
def get_validated_dxf_plan(
    order_name: str | None = None,
    doc: str | dict[str, Any] | None = None,
    plan_source: str | None = None,
) -> dict[str, Any]:
    """Return validated geometry only after configurable document authorization."""

    payload = None
    if doc is not None:
        payload = frappe.parse_json(doc) if isinstance(doc, str) else dict(doc or {})
        if not isinstance(payload, dict):
            frappe.throw(_("Editable DXF export requires a valid order payload."))

    order = _require_export_access(order_name=order_name, payload=payload)

    if order_name and order:
        plan = _required_saved_plan(order, plan_source)
        errors = legacy_export.validate_cutting_plan_document(plan)
        if errors:
            frappe.throw(
                _("DXF export blocked by geometry validation:\n{0}").format(
                    "\n".join(errors)
                )
            )
        try:
            snapshot = legacy_export._plan_to_export_snapshot(plan)
        except DxfGeometrySnapshotError as exc:
            frappe.throw(_("DXF export blocked by persisted topology validation: {0}").format(str(exc)))
        _assert_export_kerf(snapshot, fallback_kerf_mm=flt(plan.kerf_mm))
        return {
            "plan": snapshot,
            "manifest": _plan_manifest(order, plan),
        }

    if payload is None:
        frappe.throw(
            _(
                "Editable DXF export requires the current Door Cutting Order "
                "document payload."
            )
        )

    editable, snapshot = legacy_export._strict_editable_snapshot(payload)
    _assert_export_kerf(
        snapshot,
        fallback_kerf_mm=flt(getattr(editable, "kerf_mm", 0)),
    )
    return {
        "plan": snapshot,
        "manifest": _draft_manifest(editable, snapshot),
    }


__all__ = ["get_validated_dxf_plan"]
