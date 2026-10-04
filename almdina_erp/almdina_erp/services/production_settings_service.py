from __future__ import annotations

import json
import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.cutting.catalog import (
    DEFAULT_OPTIMIZATION_MODE_ID,
    MACHINE_TYPES as CANONICAL_MACHINE_TYPES,
    machine_type_catalog,
    optimization_catalog,
    public_mode_value,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    DEFAULT_KERF_MM,
    DEFAULT_MACHINE_TYPE,
    DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
    DEFAULT_PREFERRED_TRIM_MM,
    PlanSettingsValidationError,
    normalize_plan_settings,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.domain.security.factory_settings import (
    FactorySettingsSection,
    decide_settings_update,
    expand_factory_settings_capabilities,
    settings_context,
)
from almdina_erp.almdina_erp.domain.whatsapp.message_templates import (
    INVOICE_TEXT_TEMPLATE,
    MEASUREMENT_AMENDMENTS_TEXT_TEMPLATE,
    MEASUREMENTS_TEXT_TEMPLATE,
    STAGE_COMPLETION_TEXT_TEMPLATE,
)
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    granted_capabilities,
)
from almdina_erp.almdina_erp.infrastructure.frappe.master_data_audit import (
    document_snapshot,
    record_master_data_audit,
)
from almdina_erp.almdina_erp.infrastructure.frappe.optimization_mode_validation import (
    require_executable_optimization_mode,
)


MACHINE_OPTIONS = tuple(machine.id for machine in CANONICAL_MACHINE_TYPES)
PRINT_IDENTITY_DEFAULTS = {
    "print_factory_name": "مجمع المدينة المنورة التجاري",
    "print_factory_description": "الواح هايغلوس - فورميكا - cnc - ليزر - قشر",
    "print_factory_address": "دمشق - ببيلا - طريق السيدة زينب",
    "print_factory_contacts": "",
}
_PRINT_IDENTITY_FIELDS = tuple(PRINT_IDENTITY_DEFAULTS)
WHATSAPP_MESSAGE_DEFAULTS = {
    "whatsapp_measurements_text": MEASUREMENTS_TEXT_TEMPLATE,
    "whatsapp_measurement_amendments_text": MEASUREMENT_AMENDMENTS_TEXT_TEMPLATE,
    "whatsapp_invoice_text": INVOICE_TEXT_TEMPLATE,
}
_WHATSAPP_MESSAGE_FIELDS = tuple(WHATSAPP_MESSAGE_DEFAULTS)
_WHATSAPP_STAGE_MESSAGES_FIELD = "whatsapp_stage_messages"
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
    "default_extra_double_unit_price_usd",
    "default_extra_full_door_double_unit_price_usd",
    "default_extra_liner_unit_price_usd",
    "default_extra_back_groove_unit_price_usd",
    "default_extra_recessed_handle_cutout_unit_price_usd",
    "default_production_routing",
    "allow_stage_override",
    "allow_unplaced_approval",
    *_PRINT_IDENTITY_FIELDS,
    *_WHATSAPP_MESSAGE_FIELDS,
    _WHATSAPP_STAGE_MESSAGES_FIELD,
)
_PLAN_DEFAULT_FIELDS = frozenset(
    {
        "default_kerf_mm",
        "default_trim_margin_mm",
        "default_packing_mode",
        "default_cutting_machine_type",
        "default_optimization_time_limit_sec",
    }
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


def _stored_numeric(value: Any, default: float) -> Any:
    return default if value is None else value


def _apply_plan_default_values(settings: Any, payload: dict[str, Any]) -> None:
    if not _PLAN_DEFAULT_FIELDS.intersection(payload):
        return

    try:
        normalized = normalize_plan_settings(
            optimization_mode=payload.get(
                "default_packing_mode",
                str(settings.default_packing_mode or "").strip()
                or DEFAULT_OPTIMIZATION_MODE_ID,
            ),
            machine_type=payload.get(
                "default_cutting_machine_type",
                str(settings.default_cutting_machine_type or "").strip()
                or DEFAULT_MACHINE_TYPE,
            ),
            optimization_time_limit_sec=payload.get(
                "default_optimization_time_limit_sec",
                _stored_numeric(
                    settings.default_optimization_time_limit_sec,
                    DEFAULT_OPTIMIZATION_TIME_LIMIT_SEC,
                ),
            ),
            kerf_mm=payload.get(
                "default_kerf_mm",
                _stored_numeric(settings.default_kerf_mm, DEFAULT_KERF_MM),
            ),
            preferred_trim_mm=payload.get(
                "default_trim_margin_mm",
                _stored_numeric(
                    settings.default_trim_margin_mm,
                    DEFAULT_PREFERRED_TRIM_MM,
                ),
            ),
        )
    except PlanSettingsValidationError:
        frappe.throw(_("Invalid Cutting Plan default settings."), frappe.ValidationError)
        raise AssertionError("unreachable")

    if "default_packing_mode" in payload:
        require_executable_optimization_mode(normalized.optimization_mode)

    canonical = {
        "default_packing_mode": normalized.optimization_mode,
        "default_cutting_machine_type": normalized.machine_type,
        "default_optimization_time_limit_sec": normalized.optimization_time_limit_sec,
        "default_kerf_mm": normalized.kerf_mm,
        "default_trim_margin_mm": normalized.preferred_trim_mm,
    }
    for fieldname in _PLAN_DEFAULT_FIELDS.intersection(payload):
        settings.set(fieldname, canonical[fieldname])


def _apply_values(settings: Any, payload: dict[str, Any]) -> None:
    _apply_plan_default_values(settings, payload)

    numeric_non_negative = {
        "default_cutting_cost_per_board_usd": _("Default Cutting Cost / Board USD"),
        "default_special_design_fee_usd": _("Default Special Design Fee USD"),
        "default_special_cnc_fee_usd": _("Default Special CNC Fee USD"),
        "default_special_manual_edge_fee_usd": _("Default Manual Edge Fee USD"),
        "default_special_margin_percent": _("Default Special Shape Margin Percent"),
    }
    for fieldname, label in numeric_non_negative.items():
        if fieldname in payload:
            settings.set(fieldname, flt(_finite_non_negative(payload[fieldname], label)))

    extra_addon_prices = {
        "default_extra_double_unit_price_usd": _("Extra Double Price USD / Door"),
        "default_extra_full_door_double_unit_price_usd": _(
            "Full Door Double Processing Fee USD / Door"
        ),
        "default_extra_liner_unit_price_usd": _("Extra Liner Price USD / Door"),
        "default_extra_back_groove_unit_price_usd": _(
            "Extra Back Groove Price USD / Door"
        ),
        "default_extra_recessed_handle_cutout_unit_price_usd": _(
            "Extra Recessed Handle Cutout Price USD / Door"
        ),
    }
    for fieldname, label in extra_addon_prices.items():
        if fieldname in payload:
            settings.set(fieldname, flt(_finite_positive(payload[fieldname], label)))

    if "optimal_search_piece_limit" in payload:
        limit = cint(payload["optimal_search_piece_limit"])
        if limit <= 0:
            frappe.throw(_("Optimal Search Piece Limit must be greater than zero."), frappe.ValidationError)
        settings.optimal_search_piece_limit = limit

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

    whatsapp_labels = {
        "whatsapp_measurements_text": _("WhatsApp Measurements Text"),
        "whatsapp_measurement_amendments_text": _("WhatsApp Measurement Amendments Text"),
        "whatsapp_invoice_text": _("WhatsApp Invoice Text"),
    }
    for fieldname in _WHATSAPP_MESSAGE_FIELDS:
        if fieldname not in payload:
            continue
        stored = _normalized_print_text(
            payload[fieldname],
            whatsapp_labels[fieldname],
            1000,
            required=False,
        )
        settings.set(fieldname, stored or WHATSAPP_MESSAGE_DEFAULTS[fieldname])

    if _WHATSAPP_STAGE_MESSAGES_FIELD in payload:
        settings.set(
            _WHATSAPP_STAGE_MESSAGES_FIELD,
            _normalized_stage_messages(
                payload[_WHATSAPP_STAGE_MESSAGES_FIELD],
                _stage_messages_dict(settings),
            ),
        )


def _print_identity_values(settings: Any) -> dict[str, str]:
    values: dict[str, str] = {}
    for fieldname in _PRINT_IDENTITY_FIELDS:
        stored = str(settings.get(fieldname) or "").strip()
        values[fieldname] = stored or PRINT_IDENTITY_DEFAULTS[fieldname]
    return values


def _single_text(fieldname: str) -> str:
    """Read a Single field from tabSingles even when DocType meta is stale."""

    row = frappe.db.sql(
        "select value from `tabSingles` where doctype = %s and field = %s",
        ("Almdina ERP Settings", fieldname),
    )
    if not row:
        return ""
    return str(row[0][0] or "").strip()


def _write_single_text(fieldname: str, value: str) -> None:
    """Write a Single field without requiring it to exist on cached DocType meta.

    Document.save() for Singles deletes every tabSingles row then reinserts
    get_valid_dict(). Fields missing from meta are dropped; this restores them.
    """

    frappe.db.sql(
        "delete from `tabSingles` where doctype = %s and field = %s",
        ("Almdina ERP Settings", fieldname),
    )
    frappe.db.sql(
        "insert into `tabSingles` (doctype, field, value) values (%s, %s, %s)",
        ("Almdina ERP Settings", fieldname, value),
    )


def _persist_whatsapp_message_singles(settings: Any, payload: dict[str, Any]) -> None:
    wrote = False
    for fieldname in _WHATSAPP_MESSAGE_FIELDS:
        if fieldname not in payload:
            continue
        value = str(settings.get(fieldname) or "").strip() or WHATSAPP_MESSAGE_DEFAULTS[fieldname]
        _write_single_text(fieldname, value)
        wrote = True
    if _WHATSAPP_STAGE_MESSAGES_FIELD in payload:
        stored = settings.get(_WHATSAPP_STAGE_MESSAGES_FIELD)
        if not isinstance(stored, str):
            stored = json.dumps(stored or {}, ensure_ascii=False)
        _write_single_text(_WHATSAPP_STAGE_MESSAGES_FIELD, stored)
        wrote = True
    if not wrote:
        return
    frappe.clear_document_cache("Almdina ERP Settings", "Almdina ERP Settings")
    cache = getattr(frappe.db, "value_cache", None)
    if isinstance(cache, dict):
        cache.pop("Almdina ERP Settings", None)


def _whatsapp_message_values(settings: Any) -> dict[str, str]:
    values: dict[str, str] = {}
    for fieldname in _WHATSAPP_MESSAGE_FIELDS:
        stored = str(settings.get(fieldname) or "").strip() or _single_text(fieldname)
        values[fieldname] = stored or WHATSAPP_MESSAGE_DEFAULTS[fieldname]
    return values


def _parse_stage_messages(raw: Any) -> dict[str, str]:
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        try:
            raw = json.loads(raw)
        except ValueError:
            parsed = frappe.parse_json(raw)
            raw = parsed if isinstance(parsed, dict) else {}
    if not isinstance(raw, dict):
        return {}
    values: dict[str, str] = {}
    for key, value in raw.items():
        stage_id = str(key or "").strip()
        if not stage_id:
            continue
        values[stage_id] = str(value or "").strip()
    return values


def _stage_messages_dict(settings: Any) -> dict[str, str]:
    stored = _parse_stage_messages(settings.get(_WHATSAPP_STAGE_MESSAGES_FIELD))
    if stored:
        return stored
    return _parse_stage_messages(_single_text(_WHATSAPP_STAGE_MESSAGES_FIELD))


def _normalized_stage_messages(payload_value: Any, existing: dict[str, str]) -> dict[str, str]:
    incoming = _parse_stage_messages(payload_value)
    merged = dict(existing)
    for stage_id, text in incoming.items():
        merged[stage_id] = _normalized_print_text(
            text,
            _("WhatsApp Stage Message"),
            1000,
            required=False,
        )
    return merged


def _enabled_whatsapp_stage_catalog() -> list[dict[str, str]]:
    from almdina_erp.almdina_erp.infrastructure.frappe.production_routing_repository import (
        list_active_routes,
    )

    seen: dict[str, str] = {}
    for route in list_active_routes():
        for stage in route.stages:
            if not stage.notify_whatsapp_on_complete:
                continue
            stage_id = str(stage.stage_type or "").strip()
            if not stage_id or stage_id in seen:
                continue
            seen[stage_id] = str(stage.department_label or stage_id).strip() or stage_id
    return [
        {"id": stage_id, "label": label}
        for stage_id, label in sorted(seen.items(), key=lambda item: item[1])
    ]


def _whatsapp_stage_message_rows(settings: Any) -> list[dict[str, str]]:
    stored = _stage_messages_dict(settings)
    return [
        {
            "id": row["id"],
            "label": row["label"],
            "text": stored.get(row["id"]) or STAGE_COMPLETION_TEXT_TEMPLATE,
        }
        for row in _enabled_whatsapp_stage_catalog()
    ]


def whatsapp_message_templates() -> dict[str, Any]:
    """Return stored WhatsApp preamble copy with factory defaults."""

    settings = frappe.get_single("Almdina ERP Settings")
    return {
        **_whatsapp_message_values(settings),
        _WHATSAPP_STAGE_MESSAGES_FIELD: _stage_messages_dict(settings),
    }


def whatsapp_stage_message_template(stage_type: object) -> str:
    stage_id = str(stage_type or "").strip()
    stored = whatsapp_message_templates()[_WHATSAPP_STAGE_MESSAGES_FIELD].get(stage_id, "")
    return stored or STAGE_COMPLETION_TEXT_TEMPLATE


def _settings_values(settings: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    print_values = _print_identity_values(settings)
    whatsapp_values = _whatsapp_message_values(settings)
    for fieldname in _SETTINGS_FIELDS:
        if fieldname in print_values:
            values[fieldname] = print_values[fieldname]
            continue
        if fieldname in whatsapp_values:
            values[fieldname] = whatsapp_values[fieldname]
            continue
        if fieldname == _WHATSAPP_STAGE_MESSAGES_FIELD:
            values[fieldname] = _stage_messages_dict(settings)
            continue
        value = settings.get(fieldname)
        if fieldname in {"allow_stage_override", "allow_unplaced_approval"}:
            value = int(value or 0)
        elif fieldname == "default_packing_mode":
            value = public_mode_value(value)
        elif fieldname not in {"default_cutting_machine_type", "default_production_routing"}:
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
    catalog = optimization_catalog()
    machines = machine_type_catalog()
    return {
        **values,
        "values": values,
        "legacy_values": _legacy_settings_values(settings),
        "permissions": context,
        "optimization_catalog": catalog,
        "machine_type_catalog": machines,
        # Compatibility projections retain the complete public contract.
        "packing_options": [item["id"] for item in catalog],
        "machine_options": [item["id"] for item in machines],
        "routing_options": routing_options,
        "whatsapp_stage_message_rows": _whatsapp_stage_message_rows(settings),
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
    # Section-scoped updates must not fail because unrelated Single-DocType
    # mandatory fields (print identity) are empty. Payload fields are already
    # validated in _apply_values; this service is the only allowed writer.
    settings.flags.ignore_mandatory = True
    settings.save(ignore_permissions=True)
    _persist_whatsapp_message_singles(settings, payload)
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
    "whatsapp_message_templates",
    "whatsapp_stage_message_template",
]
