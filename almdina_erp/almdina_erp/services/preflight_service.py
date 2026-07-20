from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


REQUIRED_ROLES = (
    "Order Entry",
    "Cutting Operator",
    "Edge Operator",
    "Production Manager",
    "Stock Manager",
    "Accounts Management",
)

REQUIRED_PRINT_FORMATS = (
    "Door Cutting Measurements",
    "Door Cutting Plan Production A4",
)

REQUIRED_REPORTS = (
    "Factory Order Analysis",
    "Production Stage Performance",
    "Remnant Inventory",
    "Production Incidents and Replacements",
    "Order Stock Availability",
    "Board Usage Analysis",
    "Piece Size Usage Analysis",
)


def _check(checks: list[dict[str, Any]], key: str, ok: bool, severity: str, message: str, details: Any = None) -> None:
    checks.append(
        {
            "key": key,
            "ok": bool(ok),
            "severity": "OK" if ok else severity,
            "message": message,
            "details": details,
        }
    )


@frappe.whitelist()
def run_factory_preflight() -> dict[str, Any]:
    require_any_role("Production Manager", "Stock Manager")
    checks: list[dict[str, Any]] = []
    settings = frappe.get_single("Almdina ERP Settings")

    warehouse = settings.default_warehouse
    warehouse_company = frappe.db.get_value("Warehouse", warehouse, "company") if warehouse else None
    _check(
        checks,
        "default_warehouse",
        bool(warehouse and warehouse_company),
        "BLOCKER",
        _("Default Warehouse is configured and linked to a Company.") if warehouse_company else _("Configure a Default Warehouse linked to a Company."),
        {"warehouse": warehouse, "company": warehouse_company},
    )

    routing = None
    if settings.default_production_routing:
        routing = frappe.db.get_value(
            "Production Routing",
            settings.default_production_routing,
            ["name", "disabled"],
            as_dict=True,
        )
    routing_ok = bool(routing and not cint(routing.disabled))
    _check(
        checks,
        "production_routing",
        routing_ok,
        "BLOCKER",
        _("Default Production Routing is active.") if routing_ok else _("Configure an active Default Production Routing."),
        {"routing": settings.default_production_routing},
    )

    if routing_ok:
        stages = frappe.get_all(
            "Production Routing Stage",
            filters={"parent": routing.name, "parenttype": "Production Routing"},
            fields=["sequence", "stage_type", "required"],
            order_by="sequence asc",
        )
        stage_types = [row.stage_type for row in stages if cint(row.required)]
        required_core = {"Review / Preparation", "Cutting", "Edge Banding"}
        _check(
            checks,
            "routing_core_stages",
            required_core.issubset(set(stage_types)),
            "BLOCKER",
            _("Routing contains the required v1.0 core stages.") if required_core.issubset(set(stage_types)) else _("Routing is missing one or more v1.0 core stages."),
            {"stages": stage_types},
        )

    missing_roles = [role for role in REQUIRED_ROLES if not frappe.db.exists("Role", role)]
    _check(
        checks,
        "roles",
        not missing_roles,
        "BLOCKER",
        _("All required factory roles exist.") if not missing_roles else _("One or more required factory roles are missing."),
        {"missing": missing_roles},
    )

    mdf_items = frappe.get_all(
        "Item",
        filters={"custom_is_mdf": 1, "disabled": 0},
        fields=[
            "name",
            "stock_uom",
            "custom_board_length_mm",
            "custom_board_width_mm",
            "custom_board_thickness_mm",
            "custom_board_material",
            "custom_board_color",
        ],
    )
    invalid_mdf: list[dict[str, Any]] = []
    for item in mdf_items:
        whole = frappe.db.get_value("UOM", item.stock_uom, "must_be_whole_number") if item.stock_uom else 0
        problems: list[str] = []
        if flt(item.custom_board_length_mm) <= 0 or flt(item.custom_board_width_mm) <= 0:
            problems.append("dimensions")
        if flt(item.custom_board_thickness_mm) <= 0:
            problems.append("thickness")
        if not item.custom_board_material:
            problems.append("material")
        if not item.custom_board_color:
            problems.append("color")
        if not item.stock_uom or not cint(whole):
            problems.append("whole-number stock UOM")
        if problems:
            invalid_mdf.append({"item": item.name, "problems": problems})

    _check(
        checks,
        "mdf_items",
        bool(mdf_items) and not invalid_mdf,
        "BLOCKER",
        _("MDF Items have valid physical identity, dimensions and whole-number stock UOM.") if mdf_items and not invalid_mdf else _("Fix MDF Item configuration before production."),
        {"count": len(mdf_items), "invalid": invalid_mdf},
    )

    edge_types = frappe.get_all(
        "Edge Banding Type",
        filters={"disabled": 0},
        fields=["name", "item_code", "rate_usd_per_meter", "width_cm", "finish_type", "application_method"],
    )
    incomplete_edges: list[dict[str, Any]] = []
    unmapped_edges: list[str] = []
    for edge in edge_types:
        missing: list[str] = []
        if flt(edge.rate_usd_per_meter) < 0:
            missing.append("rate")
        if flt(edge.width_cm) <= 0:
            missing.append("width")
        if not edge.finish_type:
            missing.append("finish")
        if not edge.application_method:
            missing.append("application_method")
        if missing:
            incomplete_edges.append({"edge_type": edge.name, "problems": missing})
        if not edge.item_code:
            unmapped_edges.append(edge.name)

    _check(
        checks,
        "edge_master_structure",
        bool(edge_types) and not incomplete_edges,
        "BLOCKER",
        _("Enabled Edge Banding Types have valid structured master data.") if edge_types and not incomplete_edges else _("Fix incomplete Edge Banding Type master data."),
        {"count": len(edge_types), "invalid": incomplete_edges},
    )
    _check(
        checks,
        "edge_stock_mapping",
        not unmapped_edges,
        "WARNING",
        _("All enabled Edge Banding Types are mapped to stock Items.") if not unmapped_edges else _("Some enabled Edge Banding Types are not mapped to stock Items; orders using them cannot be approved for stock consumption."),
        {"unmapped": unmapped_edges},
    )

    missing_formats = [name for name in REQUIRED_PRINT_FORMATS if not frappe.db.exists("Print Format", name)]
    _check(
        checks,
        "print_formats",
        not missing_formats,
        "BLOCKER",
        _("Required production Print Formats are installed.") if not missing_formats else _("Required production Print Formats are missing."),
        {"missing": missing_formats},
    )

    missing_reports = [name for name in REQUIRED_REPORTS if not frappe.db.exists("Report", name)]
    _check(
        checks,
        "reports",
        not missing_reports,
        "WARNING",
        _("Required operational reports are installed.") if not missing_reports else _("One or more operational reports are missing."),
        {"missing": missing_reports},
    )

    blockers = [row for row in checks if not row["ok"] and row["severity"] == "BLOCKER"]
    warnings = [row for row in checks if not row["ok"] and row["severity"] == "WARNING"]
    return {
        "ready_for_controlled_uat": not blockers,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
        "checks": checks,
    }
