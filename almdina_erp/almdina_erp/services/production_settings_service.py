from __future__ import annotations

import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.cutting import PACKING_OPTIONS
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.domain.security.factory_settings import (
    FactorySettingsSection,
    decide_settings_update,
    expand_factory_settings_capabilities,
    settings_context,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    granted_capabilities,
)
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_audit import (
    document_snapshot,
    record_master_data_audit,
)


MACHINE_OPTIONS = ("Auto", "CNC Router", "Panel Saw")
PRINT_IDENTITY_DEFAULTS = {
    "print_factory_name": "مجمع المدينة المنورة التجاري",
    "print_factory_description": "الواح هايغلوس - فورميكا - cnc - ليزر - قشر",
    "print_factory_address": "دمشق - ببيلا - طريق السيدة زينب",
    "print_factory_contacts": "",
}
_PRINT_IDENTITY_FIELDS = tuple(PRINT_IDENTITY_DEFAULTS)
_PRINT_IDENTITY_READ_CAPABILITIES = frozenset(
    {
        Capability.VIEW_FACTORY_SETTINGS,
        Capability.PRINT_MEASUREMENTS,
        Capability.PRINT_CUSTOMER_INVOICE,
        Capability.PRINT_INTERNAL_COST_REPORT,
        Capability.PRINT_CUTTING_PLAN,
    }
)
_SETTINGS_FIELDS = (
    "default_kerf_mm",
    "default_trim_margin_mm",
    "default_packing_mode",
    "default_cutting_machine_type",
    "default_optimization_time_limit_sec",
    "optimal_search_piece_limit",
    "default_cutting_cost_per_board_usd",
    "default_special_design_fee_usd",
    "default_special_cnc_fee_usd",
    "default_special_manual_edge_fee_usd",
    "default_special_margin_percent",
    "default_production_routing",
    "allow_stage_override",
    "allow_unplaced_approval",
    *_PRINT_IDENTITY_FIELDS,
)
LEGACY_PRESERVED_FIELDS = (
    "enforce_stock_control",
    "default_warehouse",
    "reserve_stock_on_approval",
    "stock_consumption_point",
    "prefer_remnants_before_full_boards",
    "min_remnant_width_mm",
    "min_remnant_length_mm",
    "min_remnant_area_m2",
    "remnant_cost_policy",
    "remnant_rate_usd_per_m2",
)
_LEGACY_BOOLEAN_FIELDS = frozenset(
    {
        "enforce_stock_control",
        "reserve_stock_on_approval",
        "prefer_remnants_before_full_boards",
    }
)
_LEGACY_TEXT_FIELDS = frozenset(
    {
        "default_warehouse",
        "stock_consumption_point",
        "remnant_cost_policy",
    }
)


def _granted() -> frozenset[str]:
    return expand_factory_settings_capabilities(granted_capabilities())


def _require_view() -> frozenset[str]:
    granted = _granted()
    if Capability.VIEW_FACTORY_SETTINGS not in granted:
        frappe.throw(_("You do not have permission to view factory settings."), frappe.PermissionError)
    return granted


def _require_print_identity_view() -> frozenset[str]:
    granted = _granted()
    if not granted.intersection(_PRINT_IDENTITY_READ_CAPABILITIES):
        frappe.throw(_("You do not have permission to view factory print identity."), frappe.PermissionError)
    return granted


def _payload(values: str | dict[str, Any]) -> dict[str, Any]:
    parsed = frappe.parse_json(values) if isinstance(values, str) else dict(values or {})
    return {str(key): value for key, value in parsed.items()}


def _finite_non_negative(value: Any, label: str) -> float:
    try:
        resolved = float(value or 0)
    except (TypeError, ValueError) as error:
        raise frappe.ValidationError(_("{0} must be a valid number.").format(label)) from error
    if not math.isfinite(resolved) or resolved < 0:
        frappe.throw(_("{0} cannot be negative or non-finite.").format(label), frappe.ValidationError)
    return resolved


def _finite_positive(value: Any, label: str) -> float:
    resolved = _finite_non_negative(value, label)
    if resolved <= 0:
        frappe.throw(_("{0} must be greater than zero.").format(label), frappe.ValidationError)
    return resolved


def _normalized_print_text(value: Any, label: str, limit: int, required: bool = False) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if required and not text:
        frappe.throw(_("{0} is required.").format(label), frappe.ValidationError)
    if len(text) > limit:
        frappe.throw(_("{0} is too long (maximum {1} characters).").format(label, limit), frappe.ValidationError)
    return text


def _validate_routing(name: Any) -> str:
    """Validate an optional default routing.

    A factory may intentionally have no default routing while administrators are
    still defining roles and production paths. Dispatch remains responsible for
    requiring an explicit configured route when work is actually sent to the
    shop floor.
    """

    routing_name = str(name or "").strip()
    if not routing_name:
        return ""
    routing = frappe.db.get_value(
        "Production Routing",
        routing_name,
        ["name", "disabled"],
        as_dict=True,
    )
    if not routing:
        frappe.throw(_("Production Routing {0} does not exist.").format(routing_name), frappe.ValidationError)
    if routing.disabled:
        frappe.throw(_("Production Routing {0} is disabled.").format(routing_name), frappe.ValidationError)
    return routing_name


def _apply_values(settings: Any, payload: dict[str, Any]) -> None:
    numeric_non_negative = {
        "default_kerf_mm": _("Default Kerf MM"),
        "default_trim_margin_mm": _("Default Trim Margin MM"),
        "default_cutting_cost_per_board_usd": _("Default Cutting Cost / Board USD"),
        "default_special_design_fee_usd": _("Default Special Design Fee USD"),
        "default_special_cnc_fee_usd": _("Default Special CNC Fee USD"),
        "default_special_manual_edge_fee_usd": _("Default Manual Edge Fee USD"),
        "default_special_margin_percent": _("Default Special Shape Margin Percent"),
    }
    for fieldname, label in numeric_non_negative.items():
        if fieldname in payload:
            settings.set(fieldname, flt(_finite_non_negative(payload[fieldname], label)))

    if "default_optimization_time_limit_sec" in payload:
        settings.default_optimization_time_limit_sec = flt(
            _finite_positive(payload["default_optimization_time_limit_sec"], _("Optimization Time Limit"))
        )
    if "optimal_search_piece_limit" in payload:
        limit = cint(payload["optimal_search_piece_limit"])
        if limit <= 0:
            frappe.throw(_("Optimal Search Piece Limit must be greater than zero."), frappe.ValidationError)
        settings.optimal_search_piece_limit = limit

    if "default_packing_mode" in payload:
        packing_mode = str(payload["default_packing_mode"] or "").strip()
        if packing_mode not in PACKING_OPTIONS:
            frappe.throw(_("Unsupported Packing Mode: {0}").format(packing_mode), frappe.ValidationError)
        settings.default_packing_mode = packing_mode
    if "default_cutting_machine_type" in payload:
        machine_type = str(payload["default_cutting_machine_type"] or "").strip()
        if machine_type not in MACHINE_OPTIONS:
            frappe.throw(_("Unsupported Cutting Machine Type: {0}").format(machine_type), frappe.ValidationError)
        settings.default_cutting_machine_type = machine_type
    if "default_production_routing" in payload:
        settings.default_production_routing = _validate_routing(payload["default_production_routing"])
    for fieldname in ("allow_stage_override", "allow_unplaced_approval"):
        if fieldname in payload:
            settings.set(fieldname, cint(payload[fieldname]) and 1 or 0)

    print_labels = {
        "print_factory_name": _("Factory Name"),
        "print_factory_description": _("Factory Description"),
        "print_factory_address": _("Factory Address"),
        "print_factory_contacts": _("Factory Contacts"),
    }
    print_limits = {
        "print_factory_name": 140,
        "print_factory_description": 400,
        "print_factory_address": 400,
        "print_factory_contacts": 1000,
    }
    for fieldname in _PRINT_IDENTITY_FIELDS:
        if fieldname not in payload:
            continue
        settings.set(
            fieldname,
            _normalized_print_text(
                payload[fieldname],
                print_labels[fieldname],
                print_limits[fieldname],
                required=fieldname != "print_factory_contacts",
            ),
        )


def _print_identity_values(settings: Any) -> dict[str, str]:
    values: dict[str, str] = {}
    for fieldname in _PRINT_IDENTITY_FIELDS:
        stored = str(settings.get(fieldname) or "").strip()
        values[fieldname] = stored or PRINT_IDENTITY_DEFAULTS[fieldname]
    return values


def _settings_values(settings: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    print_values = _print_identity_values(settings)
    for fieldname in _SETTINGS_FIELDS:
        if fieldname in print_values:
            values[fieldname] = print_values[fieldname]
            continue
        value = settings.get(fieldname)
        if fieldname in {"allow_stage_override", "allow_unplaced_approval"}:
            value = int(value or 0)
        elif fieldname not in {"default_packing_mode", "default_cutting_machine_type", "default_production_routing"}:
            value = flt(value)
            if fieldname == "optimal_search_piece_limit":
                value = cint(value)
        values[fieldname] = value
    return values


def _legacy_settings_values(settings: Any) -> dict[str, Any]:
    """Expose retired values read-only so upgrades never make stored data invisible."""

    values: dict[str, Any] = {}
    for fieldname in LEGACY_PRESERVED_FIELDS:
        value = settings.get(fieldname)
        if fieldname in _LEGACY_BOOLEAN_FIELDS:
            value = int(value or 0)
        elif fieldname in _LEGACY_TEXT_FIELDS:
            value = str(value or "")
        else:
            value = flt(value)
        values[fieldname] = value
    return values


@frappe.whitelist()
def get_print_identity() -> dict[str, str]:
    """Return only the public-facing factory identity needed by authorized print actions."""

    _require_print_identity_view()
    return _print_identity_values(frappe.get_single("Almdina ERP Settings"))


@frappe.whitelist()
def get_production_settings() -> dict[str, Any]:
    granted = _require_view()
    settings = frappe.get_single("Almdina ERP Settings")
    context = settings_context(granted)
    can_choose_routing = bool(context["sections"][FactorySettingsSection.PRODUCTION]["editable"])
    routing_options = []
    if can_choose_routing or Capability.VIEW_PRODUCTION_ROUTINGS in granted:
        routing_options = frappe.get_all(
            "Production Routing",
            filters={"disabled": 0},
            pluck="name",
            order_by="routing_name asc",
        )
    values = _settings_values(settings)
    return {
        **values,
        "values": values,
        "legacy_values": _legacy_settings_values(settings),
        "permissions": context,
        "packing_options": list(PACKING_OPTIONS),
        "machine_options": list(MACHINE_OPTIONS),
        "routing_options": routing_options,
    }


@frappe.whitelist()
def update_production_settings(values: str | dict[str, Any]) -> dict[str, Any]:
    payload = _payload(values)
    granted = _granted()
    decision = decide_settings_update(granted, payload)
    if not decision.allowed:
        exception = frappe.PermissionError if decision.code == "missing_capability" else frappe.ValidationError
        frappe.throw(_(decision.reason), exception)

    frappe.db.sql(
        "select doctype from `tabSingles` where doctype = %s limit 1 for update",
        ("Almdina ERP Settings",),
    )
    settings = frappe.get_single("Almdina ERP Settings")
    before = document_snapshot(settings)
    _apply_values(settings, payload)
    settings.save(ignore_permissions=True)
    after = document_snapshot(settings)
    record_master_data_audit(
        target_doctype="Almdina ERP Settings",
        target_name="Almdina ERP Settings",
        action="Settings Updated",
        before=before,
        after=after,
        source="Factory Settings Console",
    )
    return get_production_settings()


@frappe.whitelist()
def get_factory_settings_audit(limit: int = 30) -> list[dict[str, Any]]:
    _require_view()
    rows = frappe.get_all(
        "Almdina Master Data Audit",
        filters={"target_doctype": "Almdina ERP Settings"},
        fields=["name", "action", "changed_by", "changed_on", "changed_fields", "source"],
        order_by="changed_on desc",
        limit_page_length=max(1, min(cint(limit or 30), 100)),
    )
    return [dict(row) for row in rows]


__all__ = [
    "LEGACY_PRESERVED_FIELDS",
    "MACHINE_OPTIONS",
    "PRINT_IDENTITY_DEFAULTS",
    "get_factory_settings_audit",
    "get_print_identity",
    "get_production_settings",
    "update_production_settings",
]
