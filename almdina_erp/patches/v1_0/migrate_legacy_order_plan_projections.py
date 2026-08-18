from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import (
    sanitize_plan_snapshot,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_workspace import (
    _apply_snapshot,
)


_BATCH_SIZE = 100
_LEGACY_COLUMNS = (
    "status",
    "approved_plan",
    "approved_plan_source",
    "cutting_plan_json",
    "system_plan_json",
    "custom_plan_json",
    "production_dxf",
    "packing_mode",
    "cutting_machine_type",
    "optimization_time_limit_sec",
    "kerf_mm",
    "trim_margin_mm",
    "plan_needs_recalculation",
    "calculated_plan_input_hash",
    "calculated_plan_metadata_hash",
    "packing_method",
    "engine_version",
    "board_rate_usd",
    "cutting_cost_per_board_usd",
    "mdf_cost_usd",
    "cutting_cost_usd",
    "edge_cost_usd",
    "total_cost_usd",
)


@dataclass(frozen=True, slots=True)
class _LegacyVariant:
    source_type: str
    raw_snapshot: str
    selected: bool
    dxf_file: str = ""


def _value(row: Any, fieldname: str, default: Any = None) -> Any:
    getter = getattr(row, "get", None)
    if callable(getter):
        value = getter(fieldname)
    else:
        value = getattr(row, fieldname, None)
    return default if value is None else value


def _snapshot(raw: Any) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = frappe.parse_json(text) or {}
    except Exception:
        return {}
    return sanitize_plan_snapshot(parsed) if isinstance(parsed, dict) else {}


def _has_legacy_payload(row: Any) -> bool:
    return any(
        str(_value(row, fieldname, "") or "").strip()
        for fieldname in (
            "cutting_plan_json",
            "system_plan_json",
            "custom_plan_json",
            "production_dxf",
        )
    )


def _variant_specs(row: Any) -> list[_LegacyVariant]:
    selected_raw = str(_value(row, "cutting_plan_json", "") or "").strip()
    system_raw = str(_value(row, "system_plan_json", "") or "").strip()
    custom_raw = str(_value(row, "custom_plan_json", "") or "").strip()
    dxf_file = str(_value(row, "production_dxf", "") or "").strip()
    selected_source = str(_value(row, "approved_plan_source", "System") or "System")
    selected_type = "Uploaded DXF" if selected_source == "Custom" else "System"

    variants: list[_LegacyVariant] = []
    seen_snapshots: set[str] = set()

    def add(source_type: str, raw: str, *, selected: bool, dxf: str = "") -> None:
        normalized = str(raw or "").strip()
        if normalized and normalized in seen_snapshots:
            return
        if normalized:
            seen_snapshots.add(normalized)
        if normalized or dxf:
            variants.append(
                _LegacyVariant(
                    source_type=source_type,
                    raw_snapshot=normalized,
                    selected=selected,
                    dxf_file=dxf,
                )
            )

    add(
        "System",
        system_raw,
        selected=selected_type == "System" and bool(system_raw),
    )
    add(
        "Uploaded DXF",
        custom_raw,
        selected=selected_type == "Uploaded DXF" and bool(custom_raw),
        dxf=dxf_file,
    )

    if selected_raw and selected_raw not in seen_snapshots:
        add(
            selected_type,
            selected_raw,
            selected=True,
            dxf=dxf_file if selected_type == "Uploaded DXF" else "",
        )

    if dxf_file and not any(row.source_type == "Uploaded DXF" for row in variants):
        add("Uploaded DXF", "", selected=False, dxf=dxf_file)

    if variants and not any(row.selected for row in variants):
        preferred = next(
            (index for index, item in enumerate(variants) if item.source_type == selected_type),
            0,
        )
        variants[preferred] = _LegacyVariant(
            source_type=variants[preferred].source_type,
            raw_snapshot=variants[preferred].raw_snapshot,
            selected=True,
            dxf_file=variants[preferred].dxf_file,
        )
    return variants


def _legacy_columns() -> set[str]:
    if not frappe.db.table_exists("Door Cutting Order"):
        return set()
    return set(frappe.db.get_table_columns("Door Cutting Order"))


def _query_fields(columns: set[str]) -> list[str]:
    return ["name", *[fieldname for fieldname in _LEGACY_COLUMNS if fieldname in columns]]


def _existing_order_plan(order_name: str) -> str | None:
    return frappe.db.get_value(
        "Cutting Plan",
        {"door_cutting_order": order_name, "plan_kind": "Order"},
        "name",
        order_by="revision desc, modified desc",
    )


def _working_settings(row: Any) -> tuple[str, str, float, float, float]:
    return (
        str(_value(row, "packing_mode", "Auto Pro") or "Auto Pro"),
        str(_value(row, "cutting_machine_type", "Auto") or "Auto"),
        flt(_value(row, "optimization_time_limit_sec", 10)) or 10,
        flt(_value(row, "kerf_mm", 3)),
        flt(_value(row, "trim_margin_mm", 5)),
    )


def _copy_historical_costs(plan: Any, row: Any) -> None:
    plan.cost_snapshot_version = 1
    for fieldname in (
        "board_rate_usd",
        "cutting_cost_per_board_usd",
        "mdf_cost_usd",
        "cutting_cost_usd",
        "edge_cost_usd",
        "total_cost_usd",
    ):
        plan.set(fieldname, flt(_value(row, fieldname, 0)))


def _populate_plan(
    *,
    order: Any,
    row: Any,
    variant: _LegacyVariant,
    revision: int,
    locked_order: bool,
) -> Any:
    plan = frappe.new_doc("Cutting Plan")
    plan.plan_kind = "Order"
    plan.source_type = variant.source_type
    plan.door_cutting_order = order.name
    plan.revision = revision

    optimization_mode, machine_type, time_limit, kerf_mm, trim_margin_mm = _working_settings(row)
    plan.optimization_mode = optimization_mode
    plan.machine_type = machine_type
    plan.optimization_time_limit_sec = time_limit
    plan.kerf_mm = kerf_mm
    plan.trim_margin_mm = trim_margin_mm

    snapshot = _snapshot(variant.raw_snapshot)
    stored_fingerprint = str(
        _value(row, "calculated_plan_input_hash", "")
        or snapshot.get("input_fingerprint")
        or ""
    ).strip()
    fingerprint = stored_fingerprint or "legacy-unknown"

    if snapshot:
        _apply_snapshot(
            order,
            plan,
            snapshot,
            fingerprint=fingerprint,
            method_label_fallback=str(_value(row, "packing_method", "") or ""),
            engine_version_fallback=str(_value(row, "engine_version", "") or ""),
        )
    else:
        plan.board_description = str(order.board_description or "").strip()
        plan.full_board_width_mm = flt(getattr(order, "full_board_width_mm", 0)) or flt(order.board_width_cm) * 10
        plan.full_board_length_mm = flt(getattr(order, "full_board_length_mm", 0)) or flt(order.board_length_cm) * 10
        plan.validation_status = "Pending"
        plan.snapshot_json = ""
        plan.input_fingerprint = fingerprint

    plan.metadata_fingerprint = str(
        _value(row, "calculated_plan_metadata_hash", "") or ""
    ).strip()
    plan.plan_needs_recalculation = 1 if (
        cint(_value(row, "plan_needs_recalculation", 0))
        or not stored_fingerprint
        or not snapshot
    ) else 0

    if variant.dxf_file:
        plan.dxf_file = variant.dxf_file
        plan.dxf_status = (
            "Validated" if plan.validation_status == "Valid" and snapshot else "Uploaded"
        )

    _copy_historical_costs(plan, row)

    # Preserve historical selection semantics without inventing approval for a
    # Draft order or for a file that has no geometry snapshot.
    if locked_order and variant.selected and snapshot:
        plan.status = "Approved"
    elif locked_order and snapshot and variant.source_type == "System" and not variant.selected:
        plan.status = "Superseded"
    else:
        plan.status = "Draft"
    return plan


def _migrate_order(row: Any) -> None:
    order_name = str(_value(row, "name", "") or "").strip()
    if not order_name or not _has_legacy_payload(row):
        return
    if _existing_order_plan(order_name):
        return

    order = frappe.get_doc("Door Cutting Order", order_name)
    locked_order = str(_value(row, "status", "Draft") or "Draft") != "Draft"
    approved_plan_name = ""

    for revision, variant in enumerate(_variant_specs(row), start=1):
        plan = _populate_plan(
            order=order,
            row=row,
            variant=variant,
            revision=revision,
            locked_order=locked_order,
        )
        plan.insert()
        if plan.status == "Approved":
            approved_plan_name = plan.name

    if approved_plan_name and not str(_value(row, "approved_plan", "") or "").strip():
        frappe.db.set_value(
            "Door Cutting Order",
            order_name,
            "approved_plan",
            approved_plan_name,
            update_modified=False,
        )


def execute() -> None:
    """Backfill pre-canonical DCO plan projections before their schema is retired.

    The patch is intentionally idempotent: any order that already owns a
    canonical Order Cutting Plan is left untouched. Fresh installations without
    legacy columns also no-op safely.
    """

    columns = _legacy_columns()
    if not columns.intersection(
        {"cutting_plan_json", "system_plan_json", "custom_plan_json", "production_dxf"}
    ):
        return

    fields = _query_fields(columns)
    offset = 0
    while True:
        rows = frappe.get_all(
            "Door Cutting Order",
            fields=fields,
            order_by="name asc",
            limit_start=offset,
            limit_page_length=_BATCH_SIZE,
        )
        if not rows:
            break
        for row in rows:
            _migrate_order(row)
        offset += len(rows)
