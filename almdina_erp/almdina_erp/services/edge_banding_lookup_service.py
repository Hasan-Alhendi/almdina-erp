from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    doctype_has_capability,
    document_has_capability,
    require_document_capability,
    require_doctype_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders.cut_dimension_adapter import (
    FrappeOrderCutDimensionAdapter,
)
from almdina_erp.almdina_erp.infrastructure.frappe.orders.edge_profile_repository import (
    FrappeEdgeProfileRepository,
)
from almdina_erp.almdina_erp.infrastructure.frappe.stage_operational_access import (
    require_stage_operational_access,
)
from almdina_erp.almdina_erp.services.cutting_plan_invalidation_service import (
    invalidate_stale_draft_plans,
)
from almdina_erp.almdina_erp.services.order_edit_policy import (
    is_order_at_drawing_stage,
    user_can_edit_order,
)


_OPERATIONAL_FIELDS = (
    "name",
    "edge_type_name",
    "width_cm",
    "thickness_mm",
)
_FINANCIAL_FIELD = "rate_usd_per_meter"
_SIDE_FIELDS: dict[str, tuple[str, str]] = {
    "long_right": ("edge_long_right", "edge_long_right_type_override"),
    "long_left": ("edge_long_left", "edge_long_left_type_override"),
    "width_top": ("edge_width_top", "edge_width_top_type_override"),
    "width_bottom": ("edge_width_bottom", "edge_width_bottom_type_override"),
}
_DERIVED_PIECE_FIELDS = (
    "edge_long_type",
    "edge_width_type",
    "edge_type",
    "edge_long_thickness_mm",
    "edge_width_thickness_mm",
    "edge_thickness_mm",
    "cut_width_cm",
    "cut_length_cm",
    "cut_size_label",
)


def _authorized_order_for_lookup(order_name: str) -> Any | None:
    normalized_name = str(order_name or "").strip()
    if not normalized_name or normalized_name.startswith("new-"):
        require_doctype_capability(
            Capability.CREATE_ORDER,
            message=_("لا تملك صلاحية إنشاء طلب واختيار نوع القشاط له."),
        )
        return None

    order = frappe.get_doc("Door Cutting Order", normalized_name)
    order.check_permission("read")
    require_document_capability(
        order,
        Capability.VIEW_ORDERS,
        message=_("لا تملك صلاحية عرض هذا الطلب أو أنواع القشاط التشغيلية الخاصة به."),
    )
    return order


def _serialize_row(row: Any, *, include_financial: bool) -> dict[str, Any]:
    payload = {
        "name": str(row.name or ""),
        "edge_type_name": str(row.edge_type_name or row.name or ""),
        "width_cm": row.width_cm,
        "thickness_mm": row.thickness_mm,
    }
    if include_financial:
        payload[_FINANCIAL_FIELD] = row.rate_usd_per_meter
    return payload


def _piece(order: Any, piece_name: str) -> Any:
    requested = str(piece_name or "").strip()
    for row in order.pieces or []:
        if str(row.name or "") == requested:
            return row
    frappe.throw(_("الدرفة المحددة لا تنتمي إلى هذا الطلب."), frappe.DoesNotExistError)


def _authorize_profile_override(order: Any) -> str:
    can_edit_order = document_has_capability(order, Capability.EDIT_ORDER)
    if can_edit_order and user_can_edit_order(
        getattr(order, "status", None),
        revision_state=getattr(order, "revision_state", None),
    ):
        return "order"

    require_document_capability(
        order,
        Capability.EDIT_SPECIAL_DRAWING,
        message=_("لا تملك صلاحية اختيار نوع القشاط أثناء عمل الرسم."),
    )
    if not is_order_at_drawing_stage(order):
        frappe.throw(
            _("يمكن لموظف الرسم تغيير نوع القشاط فقط عندما يكون الطلب في مرحلة الرسم."),
            frappe.PermissionError,
        )
    require_stage_operational_access(order)
    if str(getattr(order, "approved_plan", None) or "").strip():
        frappe.throw(
            _("خطة القص معتمدة ومقفلة؛ لا يمكن تغيير نوع القشاط بعد الاعتماد."),
            frappe.PermissionError,
        )
    return "drawing"


def _validate_profile_name(profile_name: str, *, fallback: str = "") -> str:
    requested = str(profile_name or "").strip()
    effective = requested or str(fallback or "").strip()
    if not effective:
        frappe.throw(_("اختر نوع قشاط لهذا الضلع أو حدد القشاط الافتراضي للطلب أولًا."))

    row = frappe.db.get_value(
        "Edge Banding Type",
        effective,
        ["name", "disabled"],
        as_dict=True,
    )
    if not row:
        frappe.throw(_("نوع القشاط المحدد غير موجود."))
    if cint(row.disabled):
        frappe.throw(_("نوع القشاط المحدد معطل ولا يمكن استخدامه في الطلب."))
    return requested


def _persist_operational_piece_state(order: Any, piece: Any, override_field: str) -> None:
    profiles = FrappeEdgeProfileRepository(order)
    FrappeOrderCutDimensionAdapter(order, profiles).calculate_rows()

    values = {override_field: getattr(piece, override_field, "") or ""}
    values.update(
        {
            fieldname: getattr(piece, fieldname, None)
            for fieldname in _DERIVED_PIECE_FIELDS
        }
    )
    frappe.db.set_value(
        "Door Cutting Order Detail",
        piece.name,
        values,
        update_modified=True,
    )

    # Keep the parent audit timestamp aligned with the controlled child mutation.
    frappe.db.set_value(
        "Door Cutting Order",
        order.name,
        "modified_by",
        frappe.session.user,
        update_modified=True,
    )
    invalidate_stale_draft_plans(order)
    frappe.clear_document_cache("Door Cutting Order", order.name)


def _operational_piece_payload(piece: Any, override_field: str) -> dict[str, Any]:
    payload = {
        "name": str(piece.name or ""),
        override_field: str(getattr(piece, override_field, "") or ""),
    }
    payload.update(
        {
            fieldname: getattr(piece, fieldname, None)
            for fieldname in _DERIVED_PIECE_FIELDS
        }
    )
    return payload


@frappe.whitelist()
def get_order_edge_banding_options(order_name: str = "") -> dict[str, Any]:
    """Return order-safe edge-band lookup data without granting master-data access.

    ``Edge Banding Type`` remains factory master data. Creating/editing an order
    or working on an assigned drawing may *use* an active profile without opening
    or administering that master DocType. Prices stay protected unless the actor
    independently holds ``view_costs``.
    """

    _authorized_order_for_lookup(order_name)
    include_financial = doctype_has_capability(Capability.VIEW_COSTS)
    fields = list(_OPERATIONAL_FIELDS)
    if include_financial:
        fields.append(_FINANCIAL_FIELD)

    rows = frappe.get_all(
        "Edge Banding Type",
        filters={"disabled": 0},
        fields=fields,
        order_by="width_cm asc, edge_type_name asc",
        limit_page_length=200,
    )
    return {
        "options": [
            _serialize_row(row, include_financial=include_financial)
            for row in rows
        ],
        "include_financial": include_financial,
    }


@frappe.whitelist()
def save_order_edge_banding_override(
    order_name: str,
    piece_name: str,
    side: str,
    edge_type: str = "",
) -> dict[str, Any]:
    """Persist only one per-side edge profile selection for an existing order.

    Full order authors continue to use the normal Order edit/save session.  A
    drawing worker may use this narrow command while assigned to the Drawing
    stage; the command cannot alter dimensions, customer data, edge positions,
    pricing, or master data.
    """

    order = _authorized_order_for_lookup(order_name)
    if order is None:
        frappe.throw(_("يجب حفظ الطلب أولًا قبل تخصيص قشاط ضلع منفرد."))
    _authorize_profile_override(order)

    side_key = str(side or "").strip()
    config = _SIDE_FIELDS.get(side_key)
    if not config:
        frappe.throw(_("جهة القشاط المحددة غير صالحة."))
    selected_field, override_field = config

    piece = _piece(order, piece_name)
    if not cint(getattr(piece, selected_field, 0)):
        frappe.throw(_("لا يمكن اختيار نوع قشاط لضلع غير محدد عليه قشاط في الطلب."))

    normalized_type = _validate_profile_name(
        edge_type,
        fallback=str(getattr(order, "default_edge_type", None) or ""),
    )
    setattr(piece, override_field, normalized_type)
    _persist_operational_piece_state(order, piece, override_field)

    return {
        "order_name": order.name,
        "piece": _operational_piece_payload(piece, override_field),
        "side": side_key,
        "effective_edge_type": str(normalized_type or order.default_edge_type or ""),
    }


__all__ = [
    "get_order_edge_banding_options",
    "save_order_edge_banding_override",
]
