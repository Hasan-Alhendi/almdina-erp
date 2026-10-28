from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from almdina_erp.almdina_erp.application.costing.customer_invoice_addon_summary import (
    summarize_extra_addon_lines,
)
from almdina_erp.almdina_erp.application.costing.financial_documents import (
    build_customer_invoice_document,
)
from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutPolicyError,
    business_state_options,
    decision_from_piece,
    offcut_assignment_projection,
    offcut_summary,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import (
    is_corner_cut,
    pending_custom_edge_price_labels,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    current_cost_plan,
    overlay_authoritative_costs,
    physical_execution_for_plan,
    refresh_order_commercial_totals,
)
from almdina_erp.almdina_erp.services.order_edit_policy import assert_order_editable


ORDER_COST_FIELDS = (
    "board_description",
    "default_edge_type",
    "total_edge_meters",
    "board_rate_usd",
    "cutting_cost_per_board_usd",
    "mdf_cost_usd",
    "cutting_cost_usd",
    "edge_cost_usd",
    "total_cost_usd",
    "special_shapes_baseline_cost_usd",
    "special_shapes_estimated_total_usd",
    "special_shapes_final_total_usd",
    "extra_addons_total_usd",
    "customer_quote_total_usd",
    "customer_quote_status",
    "material_variance_cost_usd",
    "actual_cost_usd",
)
PIECE_COST_FIELDS = (
    "piece_no",
    "piece_type",
    "qty",
    "width_cm",
    "length_cm",
    "edge_type",
    "edge_meters",
    "notes",
    "edge_long_right",
    "edge_long_left",
    "edge_width_top",
    "edge_width_bottom",
    "edge_long_right_type_override",
    "edge_long_left_type_override",
    "edge_width_top_type_override",
    "edge_width_bottom_type_override",
    "edge_long_rate_usd",
    "edge_width_rate_usd",
    "edge_long_cost_usd",
    "edge_width_cost_usd",
    "edge_cost_usd",
    "edge_rate_usd",
    "edge_break",
    "edge_break_only",
    "special_shape_estimated_unit_price_usd",
    "special_shape_custom_unit_price_usd",
    "special_shape_final_unit_price_usd",
    "special_shape_price_status",
    "special_shape_price_note",
    "special_shape_price_approved_by",
    "special_shape_price_approved_on",
    "edge_break_length_cm",
    "edge_break_meters",
    "edge_break_rate_usd",
    "edge_break_cost_usd",
    "clipped_corner_position",
    "clipped_corner_width_cm",
    "clipped_corner_length_cm",
    "clipped_corner_edge_price_usd",
    "clipped_corner_edge_price_status",
    "clipped_corner_edge_price_note",
    "clipped_corner_edge_price_set_by",
    "clipped_corner_edge_price_set_on",
    "extra_double",
    "extra_double_unit_price_usd",
    "extra_double_total_usd",
    "extra_full_door_double",
    "extra_full_door_double_unit_price_usd",
    "extra_full_door_double_total_usd",
    "extra_liner",
    "extra_liner_unit_price_usd",
    "extra_liner_total_usd",
    "extra_back_groove",
    "extra_back_groove_unit_price_usd",
    "extra_back_groove_total_usd",
    "extra_recessed_handle_cutout",
    "extra_recessed_handle_cutout_unit_price_usd",
    "extra_recessed_handle_cutout_total_usd",
    "extra_addons_total_usd",
)
_FACTORY_SCALED_TOTAL_FIELDS = (
    "extra_double_total_usd",
    "extra_full_door_double_total_usd",
    "extra_liner_total_usd",
    "extra_back_groove_total_usd",
    "extra_recessed_handle_cutout_total_usd",
    "extra_addons_total_usd",
)


def _finite_non_negative(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        frappe.throw(_("{0} must be a valid number.").format(label))
    if not math.isfinite(number):
        frappe.throw(_("{0} must be finite.").format(label))
    if number < 0:
        frappe.throw(_("{0} cannot be negative.").format(label))
    return number


def _required_cost_input(value: Any, label: str) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        frappe.throw(
            _("يجب إدخال {0} من صفحة التكلفة.").format(label),
            frappe.ValidationError,
        )
    return _finite_non_negative(value, label)


def _authorized_order(order_name: str, capability: str) -> Any:
    order = frappe.get_doc("Door Cutting Order", order_name)
    order.check_permission("read")
    require_cutting_plan_capability(order, capability)
    return order


def _locked_order(order_name: str) -> Any:
    """Lock and load one DCO before a focused pricing mutation."""

    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)
    frappe.db.sql(
        "select name from `tabDoor Cutting Order` where name = %s for update",
        (name,),
    )
    order = frappe.get_doc("Door Cutting Order", name)
    order.check_permission("read")
    return order


def _require_expected_document_version(order: Any, expected_modified: str | None) -> None:
    """Preserve optimistic concurrency for commands that save the parent DCO."""

    expected = str(expected_modified or "").strip()
    current = _document_version(order)
    if expected and expected == current:
        return
    frappe.throw(
        _(
            "تم تعديل الطلب بعد فتحه. أعد تحميل الطلب لمراجعة آخر التغييرات "
            "قبل حفظ السعر."
        ),
        frappe.TimestampMismatchError,
    )


def _require_cost_visibility(order: Any) -> None:
    require_cutting_plan_capability(order, Capability.VIEW_COSTS)


def _require_cost_settings_edit(order: Any) -> None:
    from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
        require_cost_settings_edit,
    )
    require_cost_settings_edit(order)


def _json_value(value: Any, *, label: str) -> Any:
    if isinstance(value, str):
        try:
            return frappe.parse_json(value)
        except Exception:
            frappe.throw(_("قيمة {0} غير صالحة.").format(label), frappe.ValidationError)
    return value


def _cost_settings_payload(value: Any) -> dict[str, Any]:
    parsed = _json_value(value, label=_("إعدادات التكلفة"))
    if parsed is None:
        return {}
    if not isinstance(parsed, Mapping):
        frappe.throw(_("إعدادات التكلفة يجب أن تكون كائنًا."), frappe.ValidationError)
    allowed = {"board_rate_usd", "cutting_cost_per_board_usd", "offcut_price_usd"}
    if set(parsed) - allowed:
        frappe.throw(_("تحتوي إعدادات التكلفة على حقول غير مسموحة."), frappe.ValidationError)
    return dict(parsed)


def _special_prices_payload(value: Any) -> list[dict[str, Any]]:
    parsed = _json_value(value, label=_("أسعار الدرف الخاصة"))
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        frappe.throw(_("أسعار الدرف الخاصة يجب أن تكون قائمة."), frappe.ValidationError)
    allowed = {"piece_name", "unit_price_usd", "note"}
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in parsed:
        if not isinstance(row, Mapping) or set(row) - allowed:
            frappe.throw(_("بيانات سعر الدرفة تحتوي حقولًا غير مسموحة."), frappe.ValidationError)
        piece_name = str(row.get("piece_name") or "").strip()
        if not piece_name or piece_name in seen:
            frappe.throw(_("معرّف الدرفة مفقود أو مكرر."), frappe.ValidationError)
        if "unit_price_usd" not in row:
            frappe.throw(_("يجب إدخال سعر الدرفة الخاصة."), frappe.ValidationError)
        seen.add(piece_name)
        result.append(
            {
                "piece_name": piece_name,
                "unit_price_usd": _finite_non_negative(
                    row.get("unit_price_usd"),
                    _("سعر الدرفة الخاصة"),
                ),
                "note": str(row.get("note") or "").strip(),
            }
        )
        if len(result[-1]["note"]) > 500:
            frappe.throw(_("Pricing note cannot exceed 500 characters."), frappe.ValidationError)
    return result


def _apply_special_prices(order: Any, rows: list[dict[str, Any]]) -> bool:
    """Persist only allowlisted financial fields on Special child rows."""

    if not rows:
        return False
    pieces_by_name = {
        str(getattr(piece, "name", None) or ""): piece
        for piece in (getattr(order, "pieces", None) or [])
    }
    if len(rows) != len(set(row["piece_name"] for row in rows)):
        frappe.throw(_("معرّف الدرفة مكرر."), frappe.ValidationError)

    changes: list[tuple[Any, dict[str, Any]]] = []
    for row in rows:
        piece = pieces_by_name.get(row["piece_name"])
        if piece is None or str(getattr(piece, "piece_type", "") or "") != "Special":
            frappe.throw(_("الدرفة المحددة ليست درفة خاصة تابعة لهذا الطلب."), frappe.PermissionError)
        price = row["unit_price_usd"]
        approved = price > 0
        values = {
            "special_shape_custom_unit_price_usd": price,
            "special_shape_price_status": "Approved" if approved else "Estimated",
            "special_shape_price_note": row["note"],
            "special_shape_price_approved_by": frappe.session.user if approved else None,
            "special_shape_price_approved_on": now_datetime() if approved else None,
        }
        changed = any(
            (
                flt(getattr(piece, fieldname, 0)) != flt(value)
                if fieldname == "special_shape_custom_unit_price_usd"
                else str(getattr(piece, fieldname, None) or "")
                != str(value or "")
            )
            for fieldname, value in values.items()
        )
        if changed:
            changes.append((piece, values))

    if not changes:
        return False

    names = [piece.name for piece, _ in changes]
    placeholders = ", ".join(["%s"] * len(names))
    frappe.db.sql(
        f"select name from `tabDoor Cutting Order Detail` where parent = %s "
        f"and name in ({placeholders}) for update",
        (order.name, *names),
    )
    for piece, values in changes:
        frappe.db.set_value(
            "Door Cutting Order Detail",
            piece.name,
            values,
            update_modified=False,
        )
        for fieldname, value in values.items():
            setattr(piece, fieldname, value)
    return True


def _special_piece(order: Any, piece_name: str) -> Any:
    for piece in order.pieces or []:
        if piece.name == piece_name:
            return piece
    frappe.throw(_("The selected door row does not belong to this order."))


def _piece_snapshot(piece: Any) -> dict[str, Any]:
    return {
        "name": piece.name,
        **{fieldname: getattr(piece, fieldname, None) for fieldname in PIECE_COST_FIELDS},
    }


def _order_edge_profile_rates(order: Any) -> dict[str, float]:
    """Authoritative Edge Banding Type rates for per-type quotation lines.

    Returns an empty map when the order document cannot host the repository
    cache (e.g. lightweight unit-test doubles without ``flags``). Live Frappe
    documents always provide rates via ``FrappeEdgeProfileRepository``.
    """

    if getattr(order, "flags", None) is None:
        return {}
    from almdina_erp.almdina_erp.infrastructure.frappe.orders.edge_profile_repository import (
        FrappeEdgeProfileRepository,
    )

    return FrappeEdgeProfileRepository(order).rate_map()


def _document_version(order: Any) -> str:
    return str(getattr(order, "modified", None) or "")


def _commercial_piece_projection(
    order: Any,
    projection: Any | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build UI metadata plus an invoice-only factory-service projection.

    The customer requirement ``qty`` remains untouched. Factory execution is a
    separate physical-plan projection and may be lower or higher than that order
    quantity depending on the canonical physical expansion/classification.
    """

    ui_rows: list[dict[str, Any]] = []
    invoice_rows: list[dict[str, Any]] = []
    for source_piece_no, piece in enumerate(order.pieces or [], start=1):
        ui_row = _piece_snapshot(piece)
        invoice_row = dict(ui_row)
        if projection is not None:
            physical_qty = projection.physical_qty_by_source_piece_no.get(source_piece_no)
            if physical_qty is not None:
                factory_qty = projection.factory_processing_qty_by_source_piece_no.get(
                    source_piece_no,
                    0,
                )
                ratio = factory_qty / physical_qty if physical_qty else 0
                ui_row["factory_execution_qty"] = factory_qty
                ui_row["factory_execution_ratio"] = ratio
                invoice_row["factory_execution_qty"] = factory_qty
                invoice_row["factory_execution_ratio"] = ratio
                for fieldname in (
                    "edge_meters",
                    "edge_cost_usd",
                    *_FACTORY_SCALED_TOTAL_FIELDS,
                ):
                    invoice_row[fieldname] = flt(invoice_row.get(fieldname)) * ratio
        ui_rows.append(ui_row)
        invoice_rows.append(invoice_row)
    return ui_rows, invoice_rows


def _invoice_preview(
    order_snapshot: dict[str, Any],
    invoice_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], float, tuple[str, ...]]:
    document = build_customer_invoice_document(order_snapshot, invoice_rows)
    lines = summarize_extra_addon_lines(document.get("lines") or [])
    total = round(sum(float(line.get("amount_usd") or 0) for line in lines), 2)
    pending = pending_custom_edge_price_labels(invoice_rows)
    return lines, total, pending


def _offcut_projection(plan: Any | None) -> dict[str, Any] | None:
    """Project the canonical plan's physical OFFCUT pieces for the Cost workspace."""

    if plan is None or not str(getattr(plan, "name", None) or "").strip():
        return None
    snapshot = frappe.parse_json(str(getattr(plan, "snapshot_json", None) or "{}")) or {}
    pieces = [
        piece
        for sheet in snapshot.get("sheets") or []
        for piece in sheet.get("pieces") or []
    ]
    try:
        offcut_pieces = [piece for piece in pieces if decision_from_piece(piece).is_offcut]
        assignments = []
        for index, piece in enumerate(offcut_pieces, start=1):
            assignment = offcut_assignment_projection(piece)
            assignment["piece_number"] = (
                piece.get("piece_number")
                or piece.get("piece_no")
                or piece.get("label")
                or index
            )
            assignment["width"] = piece.get("width") or piece.get("width_cm") or piece.get("w")
            assignment["length"] = piece.get("length") or piece.get("length_cm") or piece.get("h")
            assignment["measurement"] = (
                piece.get("measurement")
                or piece.get("size")
                or (
                    f"{assignment['width']} × {assignment['length']} سم"
                    if assignment.get("width") and assignment.get("length")
                    else assignment.get("piece_label")
                )
            )
            assignments.append(assignment)
    except OffcutPolicyError:
        # Historical/partial snapshots are intentionally not editable as OFFCUT.
        return None
    if not assignments:
        return None
    return {
        "plan_name": plan.name,
        "assignments": assignments,
        "summary": offcut_summary(offcut_pieces),
        "state_options": business_state_options(),
    }


def _cost_snapshot(order: Any, *, plan: Any | None = None) -> dict[str, Any]:
    from almdina_erp.almdina_erp.application.orders.final_price_approval import (
        decide_final_price_approval_actions,
    )
    from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
        fingerprint_final_price_basis,
        price_basis_token,
    )
    from almdina_erp.almdina_erp.domain.orders.price_approval import (
        FinalPriceApprovalEligibilityError,
        evaluate_final_price_approval_eligibility,
        normalize_price_approval_status,
    )
    from almdina_erp.almdina_erp.domain.security.authorization import Capability
    from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
        document_has_capability,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
        cutting_plan_capability_allowed,
    )
    from almdina_erp.almdina_erp.infrastructure.frappe.final_price_approval_gateway import (
        FrappeFinalPriceApprovalGateway,
    )

    order_snapshot = {
        fieldname: getattr(order, fieldname, None)
        for fieldname in ORDER_COST_FIELDS
    }
    resolved_plan = plan if plan is not None else current_cost_plan(order)
    resolved_order = overlay_authoritative_costs(
        order,
        order_snapshot,
        plan=resolved_plan,
    )
    resolved_order["edge_profile_rates"] = _order_edge_profile_rates(order)
    projection = physical_execution_for_plan(resolved_plan) if resolved_plan else None
    offcut_applicable = bool(projection and projection.has_factory_source_offcut)
    resolved_order["offcut_price_applicable"] = offcut_applicable
    resolved_order["offcut_factory_factory"] = offcut_applicable
    pieces, invoice_rows = _commercial_piece_projection(order, projection)
    invoice_lines, invoice_total, pending_labels = _invoice_preview(
        resolved_order,
        invoice_rows,
    )

    gateway = FrappeFinalPriceApprovalGateway()
    price_status = normalize_price_approval_status(
        getattr(order, "price_approval_status", None)
    )
    current_approval = str(getattr(order, "current_price_approval", None) or "").strip() or None
    basis_token = None
    approval_payload = None
    eligibility_error = None
    if resolved_plan is not None:
        basis = gateway.build_basis_payload(order, resolved_plan)
        digest = fingerprint_final_price_basis(basis)
        basis_token = price_basis_token(
            digest,
            formula_version=str(basis.get("formula_version") or ""),
        )
        board_present, cutting_present = gateway.cost_input_presence(resolved_plan)
        try:
            evaluate_final_price_approval_eligibility(
                order_name=str(order.name),
                order_status=str(getattr(order, "status", None) or ""),
                revision_state=str(getattr(order, "revision_state", None) or "Current"),
                docstatus=int(getattr(order, "docstatus", 0) or 0),
                cutting_plan=str(getattr(resolved_plan, "name", None) or ""),
                plan_belongs_to_order=gateway.plan_belongs_to_order(
                    resolved_plan, str(order.name)
                ),
                plan_is_current=gateway.plan_is_current(order, resolved_plan),
                pending_price_labels=tuple(pending_labels),
                board_rate_present=board_present,
                cutting_rate_present=cutting_present,
                board_rate_usd=float((basis.get("plan") or {}).get("board_rate_usd") or 0),
                cutting_cost_per_board_usd=float(
                    (basis.get("plan") or {}).get("cutting_cost_per_board_usd") or 0
                ),
                offcut_price_usd=float((basis.get("plan") or {}).get("offcut_price_usd") or 0),
                approved_amount_usd=float(basis.get("approved_amount_usd") or 0),
            )
        except FinalPriceApprovalEligibilityError as error:
            eligibility_error = error
    else:
        eligibility_error = FinalPriceApprovalEligibilityError(
            "cost_plan_missing",
            "A valid cost-reference cutting plan is required before approving the final price.",
        )

    if current_approval:
        approval_doc = gateway.load_approval(current_approval)
        if approval_doc is not None:
            note = str(getattr(approval_doc, "approval_note", None) or "").strip() or None
            approval_payload = {
                "name": approval_doc.name,
                "approved_amount_usd": flt(approval_doc.approved_amount),
                "currency": approval_doc.currency,
                "cutting_plan": approval_doc.cutting_plan,
                "approved_by": approval_doc.approved_by,
                "approved_on": approval_doc.approved_on,
                "approval_note": note,
                "validity_status": approval_doc.validity_status,
                "fingerprint_formula_version": approval_doc.fingerprint_formula_version,
            }

    decision = decide_final_price_approval_actions(
        has_approve_final_price=document_has_capability(
            order, Capability.APPROVE_FINAL_PRICE
        ),
        has_view_costs=cutting_plan_capability_allowed(order, Capability.VIEW_COSTS),
        has_edit_cost_settings=cutting_plan_capability_allowed(
            order, Capability.EDIT_COST_SETTINGS
        ),
        has_cancel_final_price_approval=document_has_capability(
            order, Capability.CANCEL_FINAL_PRICE_APPROVAL
        ),
        price_approval_status=price_status,
        current_price_approval=current_approval,
        price_basis_token_value=basis_token,
        eligibility_error=eligibility_error,
        order_status=getattr(order, "status", None),
        revision_state=getattr(order, "revision_state", None),
        docstatus=int(getattr(order, "docstatus", 0) or 0),
    )

    return {
        "order_name": order.name,
        "order_modified": _document_version(order),
        "cutting_plan": str(getattr(resolved_plan, "name", None) or "") or None,
        "offcut": _offcut_projection(resolved_plan),
        "order": resolved_order,
        "pieces": pieces,
        "invoice_preview_lines": invoice_lines,
        "invoice_preview_total_usd": invoice_total,
        "pending_factory_price_labels": list(pending_labels),
        "price_approval_status": decision.price_approval_status,
        "current_price_approval": decision.current_price_approval,
        "price_approval": approval_payload,
        "price_basis_token": decision.price_basis_token,
        "can_approve_final_price": decision.can_approve_final_price,
        "final_price_approval_blocker": (
            {
                "code": decision.reason_code,
                "message": decision.reason_message,
            }
            if decision.reason_code
            else None
        ),
        "can_cancel_final_price_approval": decision.can_cancel_final_price_approval,
        "final_price_cancellation_blocker": (
            {
                "code": decision.cancel_reason_code,
                "message": decision.cancel_reason_message,
            }
            if decision.cancel_reason_code
            else None
        ),
        "can_edit_cost_settings": decision.can_edit_cost_settings,
    }


@frappe.whitelist()
def get_order_cost_snapshot(order_name: str) -> dict[str, Any]:
    """Return cost data only to users granted ``view_costs`` by the administrator."""

    order = _authorized_order(order_name, Capability.VIEW_COSTS)
    return _cost_snapshot(order)


@frappe.whitelist()
def save_cost_workspace(
    order_name: str,
    cost_settings: dict[str, Any] | str | None = None,
    special_prices: list[dict[str, Any]] | str | None = None,
    expected_modified: str | None = None,
) -> dict[str, Any]:
    """Save one Cost edit session as one authorized financial transaction."""

    frappe.flags.final_price_approval_invalidated = False

    settings = _cost_settings_payload(cost_settings)
    prices = _special_prices_payload(special_prices)
    if not settings and not prices:
        frappe.throw(_("لا توجد تغييرات تكلفة لحفظها."), frappe.ValidationError)
    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_("يجب تحديد طلب القص."), frappe.ValidationError)

    order = _locked_order(name)
    _require_cost_visibility(order)
    _require_cost_settings_edit(order)
    _require_expected_document_version(order, expected_modified)

    from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
        authoritative_cost_values,
        current_cost_plan,
        refresh_order_commercial_totals,
    )

    plan = current_cost_plan(order)
    cost_changed = False
    if settings:
        if plan is None:
            frappe.throw(
                _("لا توجد خطة قص يمكن حفظ إعدادات التكلفة عليها."),
                frappe.ValidationError,
            )
        current = authoritative_cost_values(order, plan=plan)
        board_rate = _required_cost_input(
            settings.get("board_rate_usd", current.get("board_rate_usd")),
            _("سعر اللوح"),
        )
        cutting_rate = _required_cost_input(
            settings.get(
                "cutting_cost_per_board_usd",
                current.get("cutting_cost_per_board_usd"),
            ),
            _("أجور القص / لوح"),
        )
        offcut_rate = (
            _finite_non_negative(settings["offcut_price_usd"], _("سعر الفضلة"))
            if "offcut_price_usd" in settings
            else flt(current.get("offcut_price_usd"))
        )
        cost_changed = any(
            (
                board_rate != flt(current.get("board_rate_usd")),
                cutting_rate != flt(current.get("cutting_cost_per_board_usd")),
                offcut_rate != flt(current.get("offcut_price_usd")),
            )
        )
        if cost_changed:
            from almdina_erp.almdina_erp.services.cutting_plan_cost_command_service import (
                update_plan_cost_settings,
            )

            update_plan_cost_settings(
                order,
                board_rate_usd=board_rate,
                cutting_cost_per_board_usd=cutting_rate,
                offcut_price_usd=offcut_rate,
                invalidate_approval=False,
            )
            plan = current_cost_plan(order)

    special_changed = _apply_special_prices(order, prices)
    if special_changed:
        refresh_order_commercial_totals(order, plan)

    changed = cost_changed or special_changed
    if changed:
        from almdina_erp.almdina_erp.services.final_price_approval_service import (
            maybe_invalidate_final_price_approval,
        )

        maybe_invalidate_final_price_approval(
            order.name,
            reason="cost_workspace_financial_inputs_changed",
            only_if_basis_changed=True,
            order=order,
        )
        frappe.db.set_value(
            "Door Cutting Order",
            order.name,
            {
                "modified": now_datetime(),
                "modified_by": frappe.session.user,
            },
            update_modified=False,
        )
        order.reload()

    plan = current_cost_plan(order)
    snapshot = _cost_snapshot(order, plan=plan)
    from almdina_erp.almdina_erp.services.final_price_approval_service import (
        final_price_approval_was_invalidated,
    )

    if final_price_approval_was_invalidated():
        snapshot["final_price_approval_invalidated"] = True
        snapshot["price_approval_status"] = getattr(
            order, "price_approval_status", snapshot.get("price_approval_status")
        )
        snapshot["current_price_approval"] = getattr(
            order, "current_price_approval", None
        )
        snapshot["price_approval"] = None
        snapshot["can_approve_final_price"] = snapshot.get("can_approve_final_price")
    snapshot["saved_special_piece_names"] = [row["piece_name"] for row in prices]
    snapshot["financial_inputs_changed"] = changed
    return snapshot


@frappe.whitelist()
def update_order_cost_settings(
    order_name: str,
    board_rate_usd: float | None = None,
    cutting_cost_per_board_usd: float | None = None,
    offcut_price_usd: float | None = None,
    expected_modified: str | None = None,
) -> dict[str, Any]:
    """Compatibility RPC delegated to the unified Cost workspace command."""

    settings: dict[str, Any] = {
        "board_rate_usd": board_rate_usd,
        "cutting_cost_per_board_usd": cutting_cost_per_board_usd,
    }
    if offcut_price_usd is not None:
        settings["offcut_price_usd"] = offcut_price_usd
    return save_cost_workspace(
        order_name=order_name,
        cost_settings=settings,
        expected_modified=expected_modified,
    )


@frappe.whitelist()
def approve_special_piece_price(
    order_name: str,
    piece_name: str,
    unit_price_usd: float,
    note: str | None = None,
    expected_modified: str | None = None,
) -> dict[str, Any]:
    """Compatibility RPC delegated to the unified Special price save command."""

    snapshot = save_cost_workspace(
        order_name=order_name,
        special_prices=[
            {
                "piece_name": piece_name,
                "unit_price_usd": unit_price_usd,
                "note": note or "",
            }
        ],
        expected_modified=expected_modified,
    )
    piece = next(
        (row for row in snapshot.get("pieces", []) if row.get("name") == piece_name),
        {},
    )
    return {
        "order_name": snapshot.get("order_name"),
        "order_modified": snapshot.get("order_modified"),
        "piece_name": piece_name,
        "unit_price_usd": flt(piece.get("special_shape_final_unit_price_usd")),
        "price_status": piece.get("special_shape_price_status"),
        "approved_by": piece.get("special_shape_price_approved_by"),
        "approved_on": piece.get("special_shape_price_approved_on"),
        "customer_quote_total_usd": flt(snapshot.get("order", {}).get("customer_quote_total_usd")),
        "customer_quote_status": snapshot.get("order", {}).get("customer_quote_status"),
    }


@frappe.whitelist()
def update_clipped_corner_edge_price(
    order_name: str,
    piece_name: str,
    edge_price_usd: float,
    note: str | None = None,
    expected_modified: str | None = None,
) -> dict[str, Any]:
    """Set or update cut-corner edge banding processing cost via pricing capabilities."""

    order = _locked_order(order_name)
    _require_cost_visibility(order)
    piece = _special_piece(order, piece_name)
    required_capability = (
        Capability.EDIT_SPECIAL_PRICE
        if piece.clipped_corner_edge_price_status == "Priced"
        else Capability.APPROVE_SPECIAL_PRICE
    )
    require_document_capability(order, required_capability)
    _require_expected_document_version(order, expected_modified)
    assert_order_editable(order)

    if not is_corner_cut(piece.piece_type):
        frappe.throw(_("Only a cut-corner door can receive a custom edge banding price."))

    price = _finite_non_negative(edge_price_usd, _("Cut-Corner Edge Banding Price USD"))
    approval_note = str(note or "").strip()
    if len(approval_note) > 500:
        frappe.throw(_("Pricing note cannot exceed 500 characters."))

    piece.clipped_corner_edge_price_usd = price
    piece.clipped_corner_edge_price_status = "Priced"
    piece.clipped_corner_edge_price_note = approval_note
    piece.clipped_corner_edge_price_set_by = frappe.session.user
    piece.clipped_corner_edge_price_set_on = now_datetime()
    order.flags.special_price_approval_action = True
    order.save(ignore_permissions=True)

    return {
        "order_name": order.name,
        "order_modified": _document_version(order),
        "piece_name": piece.name,
        "edge_price_usd": flt(piece.clipped_corner_edge_price_usd),
        "price_status": piece.clipped_corner_edge_price_status,
        "set_by": piece.clipped_corner_edge_price_set_by,
        "set_on": piece.clipped_corner_edge_price_set_on,
        "required_capability": required_capability,
    }


__all__ = [
    "approve_special_piece_price",
    "get_order_cost_snapshot",
    "update_clipped_corner_edge_price",
    "update_order_cost_settings",
    "save_cost_workspace",
]
