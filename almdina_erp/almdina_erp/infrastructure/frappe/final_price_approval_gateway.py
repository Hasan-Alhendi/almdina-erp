"""Frappe adapter for final-price approval persistence and locked fact gathering."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from almdina_erp.almdina_erp.application.costing.customer_invoice_addon_summary import (
    summarize_extra_addon_lines,
)
from almdina_erp.almdina_erp.application.costing.financial_documents import (
    build_customer_invoice_document,
)
from almdina_erp.almdina_erp.domain.cutting.offcut_policy import (
    OffcutPolicyError,
    decision_from_piece,
    offcut_assignment_projection,
)
from almdina_erp.almdina_erp.domain.orders.final_price_basis import (
    build_final_price_basis_payload,
    build_order_pricing_input_payload,
    fingerprint_order_pricing_inputs,
    geometry_token,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import pending_custom_edge_price_labels
from almdina_erp.almdina_erp.domain.orders.price_approval import (
    PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION,
    PRICE_APPROVAL_VALIDITY_ACTIVE,
    PRICE_APPROVAL_VALIDITY_INVALIDATED,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_costing_workspace import (
    COST_SNAPSHOT_VERSION,
    authoritative_cost_values,
    current_cost_plan,
    overlay_authoritative_costs,
    physical_execution_for_plan,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    production_plan_facts,
)


_ORDER_COST_FIELDS = (
    "board_description",
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
_PIECE_COST_FIELDS = (
    "piece_no",
    "piece_type",
    "qty",
    "width_cm",
    "length_cm",
    "allow_rotation",
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
    "special_shape_geometry_json",
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


def _piece_snapshot(piece: Any) -> dict[str, Any]:
    snapshot = {
        "name": getattr(piece, "name", None),
        **{fieldname: getattr(piece, fieldname, None) for fieldname in _PIECE_COST_FIELDS},
    }
    snapshot["special_shape_geometry_token"] = geometry_token(
        snapshot.get("special_shape_geometry_json")
    )
    return snapshot


def _order_pricing_input_fingerprint(order: Any) -> str:
    pieces = [_piece_snapshot(piece) for piece in (getattr(order, "pieces", None) or [])]
    width = flt(getattr(order, "full_board_width_mm", 0)) or (
        flt(getattr(order, "board_width_cm", 0)) * 10
    )
    length = flt(getattr(order, "full_board_length_mm", 0)) or (
        flt(getattr(order, "board_length_cm", 0)) * 10
    )
    return fingerprint_order_pricing_inputs(
        build_order_pricing_input_payload(
            pieces=pieces,
            full_board_width_mm=width,
            full_board_length_mm=length,
            order_cutting_machine=getattr(order, "order_cutting_machine", None),
        )
    )


def order_commercial_inputs_changed(order: Any) -> bool:
    """True when saved commercial inputs diverge from the pre-save document."""

    if not getattr(order, "name", None):
        return False
    previous = None
    get_previous = getattr(order, "get_doc_before_save", None)
    if callable(get_previous):
        previous = get_previous()
    if previous is None:
        return False
    return _order_pricing_input_fingerprint(previous) != _order_pricing_input_fingerprint(order)


def _commercial_piece_projection(
    order: Any,
    projection: Any | None,
) -> list[dict[str, Any]]:
    invoice_rows: list[dict[str, Any]] = []
    for source_piece_no, piece in enumerate(order.pieces or [], start=1):
        invoice_row = _piece_snapshot(piece)
        if projection is not None:
            physical_qty = projection.physical_qty_by_source_piece_no.get(source_piece_no)
            if physical_qty is not None:
                factory_qty = projection.factory_processing_qty_by_source_piece_no.get(
                    source_piece_no,
                    0,
                )
                ratio = factory_qty / physical_qty if physical_qty else 0
                invoice_row["factory_execution_qty"] = factory_qty
                invoice_row["factory_execution_ratio"] = ratio
                for fieldname in ("edge_meters", "edge_cost_usd", *_FACTORY_SCALED_TOTAL_FIELDS):
                    invoice_row[fieldname] = flt(invoice_row.get(fieldname)) * ratio
        invoice_rows.append(invoice_row)
    return invoice_rows


def _invoice_preview_total(
    order_snapshot: dict[str, Any],
    invoice_rows: list[dict[str, Any]],
) -> float:
    document = build_customer_invoice_document(order_snapshot, invoice_rows)
    lines = summarize_extra_addon_lines(document.get("lines") or [])
    return round(sum(float(line.get("amount_usd") or 0) for line in lines), 2)


def _offcut_assignments(plan: Any | None) -> list[dict[str, Any]]:
    if plan is None or not str(getattr(plan, "name", None) or "").strip():
        return []
    snapshot = frappe.parse_json(str(getattr(plan, "snapshot_json", None) or "{}")) or {}
    pieces = [
        piece
        for sheet in snapshot.get("sheets") or []
        for piece in sheet.get("pieces") or []
    ]
    try:
        assignments = []
        for index, piece in enumerate(
            (piece for piece in pieces if decision_from_piece(piece).is_offcut),
            start=1,
        ):
            assignment = offcut_assignment_projection(piece)
            assignment["piece_number"] = (
                piece.get("piece_number")
                or piece.get("piece_no")
                or piece.get("label")
                or index
            )
            assignments.append(assignment)
        return assignments
    except OffcutPolicyError:
        return []


class FrappeFinalPriceApprovalGateway:
    """Locks, gathers canonical commercial facts, and persists approval history."""

    def lock_order(self, order_name: str) -> Any:
        name = str(order_name or "").strip()
        frappe.db.sql(
            "select name from `tabDoor Cutting Order` where name = %s for update",
            (name,),
        )
        return frappe.get_doc("Door Cutting Order", name)

    def lock_cost_plan(self, plan_name: str) -> Any:
        name = str(plan_name or "").strip()
        frappe.db.sql(
            "select name from `tabCutting Plan` where name = %s for update",
            (name,),
        )
        return frappe.get_doc("Cutting Plan", name)

    def lock_approval(self, approval_name: str) -> Any | None:
        name = str(approval_name or "").strip()
        if not name:
            return None
        rows = frappe.db.sql(
            "select name from `tabDoor Cutting Price Approval` where name = %s for update",
            (name,),
        )
        if not rows:
            return None
        return frappe.get_doc("Door Cutting Price Approval", name)

    def resolve_cost_plan(self, order: Any) -> Any | None:
        return current_cost_plan(order)

    def plan_belongs_to_order(self, plan: Any, order_name: str) -> bool:
        return str(getattr(plan, "door_cutting_order", None) or "") == str(order_name)

    def plan_is_current(self, order: Any, plan: Any) -> bool:
        facts = production_plan_facts(order)
        if not facts.has_cutting_plan:
            return False
        if facts.plan_needs_recalculation:
            return False
        return str(facts.plan_name or "") == str(getattr(plan, "name", None) or "")

    def cost_input_presence(self, plan: Any) -> tuple[bool, bool]:
        # cost_snapshot_version marks explicit Plan cost ownership, including valid zeros.
        owned = cint(getattr(plan, "cost_snapshot_version", 0)) >= COST_SNAPSHOT_VERSION
        return owned, owned

    def pending_price_labels(self, order: Any, plan: Any) -> tuple[str, ...]:
        projection = physical_execution_for_plan(plan) if plan is not None else None
        invoice_rows = _commercial_piece_projection(order, projection)
        return pending_custom_edge_price_labels(invoice_rows)

    def build_basis_payload(self, order: Any, plan: Any) -> dict[str, Any]:
        order_snapshot = {
            fieldname: getattr(order, fieldname, None)
            for fieldname in _ORDER_COST_FIELDS
        }
        resolved_order = overlay_authoritative_costs(order, order_snapshot, plan=plan)
        projection = physical_execution_for_plan(plan) if plan is not None else None
        offcut_applicable = bool(projection and projection.has_factory_source_offcut)
        resolved_order["offcut_price_applicable"] = offcut_applicable
        resolved_order["offcut_factory_factory"] = offcut_applicable
        invoice_rows = _commercial_piece_projection(order, projection)
        invoice_total = _invoice_preview_total(resolved_order, invoice_rows)
        costs = authoritative_cost_values(order, plan=plan)
        return build_final_price_basis_payload(
            cutting_plan=str(getattr(plan, "name", None) or ""),
            currency="USD",
            plan_costs=costs,
            required_boards=int(getattr(plan, "required_boards", 0) or 0),
            pieces=invoice_rows,
            offcut_applicable=offcut_applicable,
            offcut_assignments=_offcut_assignments(plan),
            invoice_preview_total_usd=float(invoice_total),
            customer_quote_total_usd=flt(resolved_order.get("customer_quote_total_usd")),
            formula_version=PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION,
        )

    def find_active_approval(self, order_name: str) -> Any | None:
        rows = frappe.get_all(
            "Door Cutting Price Approval",
            filters={
                "door_cutting_order": order_name,
                "validity_status": PRICE_APPROVAL_VALIDITY_ACTIVE,
            },
            fields=["name"],
            order_by="approved_on desc, creation desc",
            limit_page_length=1,
        )
        if not rows:
            return None
        return frappe.get_doc("Door Cutting Price Approval", rows[0].name)

    def load_approval(self, approval_name: str) -> Any | None:
        name = str(approval_name or "").strip()
        if not name or not frappe.db.exists("Door Cutting Price Approval", name):
            return None
        return frappe.get_doc("Door Cutting Price Approval", name)

    def insert_approval(
        self,
        *,
        order_name: str,
        cutting_plan: str,
        approved_amount: float,
        currency: str,
        fingerprint: str,
        formula_version: str,
        approval_note: str | None = None,
    ) -> Any:
        document = frappe.get_doc(
            {
                "doctype": "Door Cutting Price Approval",
                "door_cutting_order": order_name,
                "cutting_plan": cutting_plan,
                "approved_amount": flt(approved_amount),
                "currency": str(currency or "USD"),
                "approved_by": frappe.session.user,
                "approved_on": now_datetime(),
                "approval_note": approval_note,
                "pricing_basis_fingerprint": fingerprint,
                "fingerprint_formula_version": formula_version
                or PRICE_APPROVAL_FINGERPRINT_FORMULA_VERSION,
                "validity_status": PRICE_APPROVAL_VALIDITY_ACTIVE,
            }
        )
        document.flags.price_approval_action = True
        document.insert(ignore_permissions=True)
        return document

    def update_order_price_approval(
        self,
        order_name: str,
        *,
        status: str,
        approval_name: str | None,
    ) -> None:
        # Focused write avoids full DCO recalculation paths while remaining
        # command-owned (ordinary form saves still cannot forge these fields).
        frappe.db.set_value(
            "Door Cutting Order",
            order_name,
            {
                "price_approval_status": status,
                "current_price_approval": approval_name,
            },
            update_modified=False,
        )
        frappe.clear_document_cache("Door Cutting Order", order_name)

    def invalidate_approval(
        self,
        approval: Any,
        *,
        reason: str,
        actor: str | None = None,
    ) -> None:
        document = approval
        if not hasattr(document, "save"):
            document = frappe.get_doc("Door Cutting Price Approval", approval)
        # Idempotent: never rewrite an already-Invalidated history row.
        if str(getattr(document, "validity_status", None) or "") != PRICE_APPROVAL_VALIDITY_ACTIVE:
            return
        document.validity_status = PRICE_APPROVAL_VALIDITY_INVALIDATED
        document.invalidated_on = now_datetime()
        document.invalidation_reason = str(reason or "").strip() or "pricing_basis_changed"
        if actor and hasattr(document, "invalidated_by"):
            document.invalidated_by = actor
        document.flags.allow_price_approval_invalidate = True
        document.flags.price_approval_action = True
        document.save(ignore_permissions=True)

    def current_user(self) -> str:
        return str(frappe.session.user or "")

    def now_iso(self) -> str:
        return str(now_datetime())


def assert_cost_settings_unlocked_for_order(order: Any) -> None:
    """Historical hook: Approved price no longer blocks cost-settings edits.

    Capability, document scope, and plan lifecycle remain the authority. Kept so
    older call sites stay safe after the product-contract change.
    """

    del order


__all__ = [
    "FrappeFinalPriceApprovalGateway",
    "assert_cost_settings_unlocked_for_order",
    "order_commercial_inputs_changed",
]
