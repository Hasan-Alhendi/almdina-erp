from __future__ import annotations

import json
import math
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.cnc.machine_profile import (
    MachineProfileError,
    normalize_machine_profile,
)
from almdina_erp.almdina_erp.domain.cnc.artcam_machining import (
    MachiningSetupError,
    artcam_tool_storage,
    machining_tool_uses,
    new_machining_id,
    normalize_artcam_tool,
    normalize_profile,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cnc_operational_file_repository import (
    known_tool_presets,
    machining_profile_catalog,
)
from almdina_erp.almdina_erp.domain.cnc.tool_preset import (
    ToolPresetError,
    normalize_tool_preset,
    resolve_selected_presets,
    unused_tool_preset_can_be_deleted,
)
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
from almdina_erp.almdina_erp.domain.backups.policy import (
    BackupSchedule,
    normalize_remote_path,
)
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
    require_doctype_capability,
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
_BACKUP_SECRET_FIELDS = frozenset(
    {"ssh_password", "ssh_private_key", "ssh_private_key_passphrase"}
)
_BACKUP_BOOLEAN_FIELDS = frozenset(
    {"local_backup_enabled", "external_backup_enabled"}
)
_BACKUP_INTEGER_FIELDS = frozenset(
    {
        "local_backup_day_of_month",
        "local_backup_retention",
        "external_backup_day_of_month",
        "external_backup_retention",
        "ssh_port",
    }
)
_BACKUP_TEXT_FIELDS = frozenset(
    {
        "local_backup_frequency",
        "local_backup_time",
        "local_backup_weekday",
        "external_backup_frequency",
        "external_backup_time",
        "external_backup_weekday",
        "ssh_host",
        "ssh_username",
        "ssh_auth_method",
        "remote_backup_path",
    }
)
_PRINT_IDENTITY_READ_CAPABILITIES = frozenset(
    {
        Capability.VIEW_FACTORY_SETTINGS,
        Capability.PRINT_MEASUREMENTS,
        Capability.PRINT_CUSTOMER_INVOICE,
        Capability.PRINT_INTERNAL_COST_REPORT,
        Capability.PRINT_CUTTING_PLAN,
    }
)
_CNC_PRESET_FIELDS = (
    "cnc_default_preset_cut_path",
    "cnc_default_preset_liner",
    "cnc_default_preset_rear_groove",
    "cnc_default_preset_handle_recess",
)
_CNC_MACHINE_FIELDS = (
    "cnc_machine_tool_number",
    "cnc_machine_spindle_speed_rpm",
    "cnc_machine_cutting_feed_mm_min",
    "cnc_machine_plunge_feed_mm_min",
    "cnc_machine_retract_z_mm",
    "cnc_machine_distance_mode",
    "cnc_machine_work_offset",
    "cnc_machine_example_depth_a_mm",
    "cnc_machine_example_depth_b_mm",
    "cnc_machine_profile_production_approved",
    "cnc_machine_profile_source",
)
_CNC_TEXT_FIELDS = frozenset(
    {
        *_CNC_PRESET_FIELDS,
        "cnc_machine_tool_number",
        "cnc_machine_distance_mode",
        "cnc_machine_work_offset",
        "cnc_machine_profile_source",
    }
)
_CNC_INTEGER_FIELDS = frozenset(
    {
        "cnc_machine_spindle_speed_rpm",
        "cnc_machine_profile_production_approved",
    }
)
_CNC_PRESET_MESSAGES = {
    "preset_not_found": "The selected CNC tool preset does not exist.",
    "preset_disabled": "The selected CNC tool preset is disabled.",
    "tool_identity_conflict": "One board file must keep the same physical tool number.",
    "tool_diameter_conflict": "The same tool cannot use two diameters in one operational file.",
}
_SETTINGS_FIELDS = (
    "default_kerf_mm",
    "default_deduct_edge_thickness",
    "default_liner_tool_diameter_mm",
    "default_handle_recess_tool_diameter_mm",
    "default_rear_groove_tool_diameter_mm",
    "default_trim_margin_mm",
    "default_packing_mode",
    "default_cutting_machine_type",
    "default_optimization_time_limit_sec",
    "optimal_search_piece_limit",
    "max_centerable_edge_gap_cm",
    "alignment_search_budget_sec",
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
    *_CNC_PRESET_FIELDS,
    *_CNC_MACHINE_FIELDS,
    *_PRINT_IDENTITY_FIELDS,
    *_WHATSAPP_MESSAGE_FIELDS,
    _WHATSAPP_STAGE_MESSAGES_FIELD,
    *_BACKUP_BOOLEAN_FIELDS,
    *_BACKUP_INTEGER_FIELDS,
    *_BACKUP_TEXT_FIELDS,
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


def _apply_tool_diameter_defaults(settings: Any, payload: dict[str, Any]) -> None:
    """Blank keeps the factory field empty so new orders copy the cutting tool."""

    labels = {
        "default_liner_tool_diameter_mm": _("Default liner tool diameter (mm)"),
        "default_handle_recess_tool_diameter_mm": _("Default handle recess tool diameter (mm)"),
        "default_rear_groove_tool_diameter_mm": _("Default rear groove tool diameter (mm)"),
    }
    for fieldname, label in labels.items():
        if fieldname not in payload:
            continue
        raw = payload[fieldname]
        if raw in (None, ""):
            settings.set(fieldname, None)
            continue
        resolved = _finite_non_negative(raw, label)
        # Zero is not a tool. An empty dialog float arrives as zero and means
        # "copy the cutting tool onto the next new order".
        settings.set(fieldname, None if resolved == 0 else flt(resolved))


def _apply_values(settings: Any, payload: dict[str, Any]) -> None:
    _apply_plan_default_values(settings, payload)
    _apply_tool_diameter_defaults(settings, payload)

    numeric_non_negative = {
        "max_centerable_edge_gap_cm": _("Maximum centerable edge gap (cm)"),
        "alignment_search_budget_sec": _("Final Alignment Search Budget (seconds)"),
        "default_cutting_cost_per_board_usd": _("Default Cutting Cost / Board USD"),
        "default_special_design_fee_usd": _("Default Special Design Fee USD"),
        "default_special_cnc_fee_usd": _("Default Special CNC Fee USD"),
        "default_special_manual_edge_fee_usd": _("Default Manual Edge Fee USD"),
        "default_special_margin_percent": _("Default Special Shape Margin Percent"),
    }
    for fieldname, label in numeric_non_negative.items():
        if fieldname in payload:
            settings.set(fieldname, flt(_finite_non_negative(payload[fieldname], label)))

    # Alignment is a separately configurable *tail* allowance, bounded by
    # the user's own optimization timeout rather than an internal magic cap.
    if flt(settings.get("alignment_search_budget_sec") or 0) > flt(
        settings.get("default_optimization_time_limit_sec") or 0
    ):
        frappe.throw(
            _("Final alignment search budget must not exceed optimization timeout."),
            frappe.ValidationError,
        )

    extra_addon_prices = {
        "default_extra_double_unit_price_usd": _("Double Price USD / Door"),
        "default_extra_full_door_double_unit_price_usd": _(
            "Full Door Double Processing Fee USD / Door"
        ),
        "default_extra_liner_unit_price_usd": _("Liner Price USD / Door"),
        "default_extra_back_groove_unit_price_usd": _(
            "Back Groove Price USD / Door"
        ),
        "default_extra_recessed_handle_cutout_unit_price_usd": _(
            "Recessed Handle Cutout Price USD / Door"
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
    if "default_deduct_edge_thickness" in payload:
        from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
            coerce_deduct_edge_thickness,
        )

        settings.set(
            "default_deduct_edge_thickness",
            1 if coerce_deduct_edge_thickness(payload["default_deduct_edge_thickness"]) else 0,
        )

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

    for fieldname in _BACKUP_BOOLEAN_FIELDS.intersection(payload):
        settings.set(fieldname, 1 if cint(payload[fieldname]) else 0)

    for fieldname in _BACKUP_INTEGER_FIELDS.intersection(payload):
        value = cint(payload[fieldname])
        if fieldname == "ssh_port":
            if not 1 <= value <= 65535:
                frappe.throw(_("SSH Port must be between 1 and 65535."), frappe.ValidationError)
        elif fieldname.endswith("day_of_month"):
            if not 1 <= value <= 31:
                frappe.throw(_("Backup day of month must be between 1 and 31."), frappe.ValidationError)
        elif not 1 <= value <= 365:
            frappe.throw(_("Backup retention must be between 1 and 365."), frappe.ValidationError)
        settings.set(fieldname, value)

    for fieldname in _BACKUP_TEXT_FIELDS.intersection(payload):
        value = str(payload[fieldname] or "").strip()
        if len(value) > 255:
            frappe.throw(_("Backup setting value is too long."), frappe.ValidationError)
        if fieldname == "remote_backup_path" and value:
            try:
                value = normalize_remote_path(value)
            except ValueError as exc:
                frappe.throw(_(str(exc)), frappe.ValidationError)
        settings.set(fieldname, value)

    for fieldname in _BACKUP_SECRET_FIELDS.intersection(payload):
        value = str(payload[fieldname] or "")
        if not value:
            continue
        if len(value) > 20000:
            frappe.throw(_("SSH credential is too long."), frappe.ValidationError)
        settings.set(fieldname, value)

    if set(payload).intersection(
        _BACKUP_BOOLEAN_FIELDS | _BACKUP_INTEGER_FIELDS | _BACKUP_TEXT_FIELDS | _BACKUP_SECRET_FIELDS
    ):
        _validate_backup_settings(settings)

    _apply_cnc_values(settings, payload)


def _apply_cnc_values(settings: Any, payload: dict[str, Any]) -> None:
    """Validate factory CNC defaults without rewriting saved operational files."""

    if set(payload).intersection(_CNC_PRESET_FIELDS):
        selected = {
            fieldname: str(
                payload[fieldname] if fieldname in payload else settings.get(fieldname) or ""
            ).strip()
            for fieldname in _CNC_PRESET_FIELDS
        }
        known = _known_cnc_presets([name for name in selected.values() if name])
        try:
            resolve_selected_presets(list(selected.values()), known)
        except ToolPresetError as exc:
            frappe.throw(
                _(_CNC_PRESET_MESSAGES.get(exc.code, "The CNC tool preset is not valid.")),
                frappe.ValidationError,
            )
        for fieldname in _CNC_PRESET_FIELDS:
            if fieldname in payload:
                settings.set(fieldname, selected[fieldname])

    if set(payload).intersection(_CNC_MACHINE_FIELDS):
        merged = {
            fieldname: payload[fieldname] if fieldname in payload else settings.get(fieldname)
            for fieldname in _CNC_MACHINE_FIELDS
        }
        try:
            profile = normalize_machine_profile(merged)
        except MachineProfileError:
            frappe.throw(_("The CNC machine profile sample is not valid."), frappe.ValidationError)
        stored = {
            "cnc_machine_tool_number": profile.tool_number,
            "cnc_machine_spindle_speed_rpm": profile.spindle_speed_rpm,
            "cnc_machine_cutting_feed_mm_min": profile.cutting_feed_mm_min,
            "cnc_machine_plunge_feed_mm_min": profile.plunge_feed_mm_min,
            "cnc_machine_retract_z_mm": profile.retract_z_mm,
            "cnc_machine_distance_mode": profile.distance_mode,
            "cnc_machine_work_offset": profile.work_offset,
            "cnc_machine_example_depth_a_mm": profile.example_depth_a_mm,
            "cnc_machine_example_depth_b_mm": profile.example_depth_b_mm,
            "cnc_machine_profile_production_approved": 1 if profile.production_approved else 0,
            "cnc_machine_profile_source": profile.source_note,
        }
        for fieldname in _CNC_MACHINE_FIELDS:
            if fieldname in payload:
                settings.set(fieldname, stored[fieldname])


def _known_cnc_presets(names: list[str]) -> dict[str, dict[str, Any]]:
    wanted = [name for name in names if name]
    if not wanted:
        return {}
    rows = frappe.get_all(
        "CNC Tool Preset",
        filters={"name": ["in", wanted]},
        fields=[
            "name",
            "preset_name",
            "tool_name",
            "tool_number",
            "tool_diameter_mm",
            "final_depth_mm",
            "spindle_speed_rpm",
            "feed_rate_mm_min",
            "plunge_rate_mm_min",
            "pass_depth_mm",
            "enabled",
        ],
        limit_page_length=0,
        ignore_permissions=True,
    )
    return {
        str(row.name): {
            "preset_name": row.preset_name,
            "tool_name": row.tool_name,
            "tool_number": row.tool_number,
            "tool_diameter_mm": row.tool_diameter_mm,
            "final_depth_mm": row.final_depth_mm,
            "spindle_speed_rpm": row.spindle_speed_rpm,
            "feed_rate_mm_min": row.feed_rate_mm_min,
            "plunge_rate_mm_min": row.plunge_rate_mm_min,
            "pass_depth_mm": row.pass_depth_mm,
            "enabled": bool(cint(row.enabled)),
        }
        for row in rows
    }


def _backup_time(value: Any, default: str) -> str:
    if hasattr(value, "total_seconds"):
        seconds = int(value.total_seconds()) % (24 * 60 * 60)
        return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"
    text = str(value or default).strip()
    parts = text.split(":")
    if len(parts) >= 2 and all(part.isdigit() for part in parts[:2]):
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    return text


def _validate_backup_settings(settings: Any) -> None:
    for prefix, defaults in (("local", ("02:00", 7)), ("external", ("03:00", 4))):
        try:
            BackupSchedule(
                frequency=settings.get(f"{prefix}_backup_frequency") or "Daily",
                time=_backup_time(settings.get(f"{prefix}_backup_time"), defaults[0]),
                weekday=settings.get(f"{prefix}_backup_weekday") or "Monday",
                day_of_month=settings.get(f"{prefix}_backup_day_of_month") or 1,
            ).validated()
        except ValueError as exc:
            frappe.throw(_(str(exc)), frappe.ValidationError)
        retention = cint(settings.get(f"{prefix}_backup_retention") or defaults[1])
        if not 1 <= retention <= 365:
            frappe.throw(_("Backup retention must be between 1 and 365."), frappe.ValidationError)

    if not cint(settings.get("external_backup_enabled")):
        return
    required = {
        "ssh_host": _("SSH Host"),
        "ssh_username": _("SSH Username"),
        "remote_backup_path": _("Remote Backup Path"),
    }
    for fieldname, label in required.items():
        if not str(settings.get(fieldname) or "").strip():
            frappe.throw(_("{0} is required before enabling External Backup.").format(label), frappe.ValidationError)
    try:
        normalize_remote_path(settings.get("remote_backup_path"))
    except ValueError as exc:
        frappe.throw(_(str(exc)), frappe.ValidationError)
    method = str(settings.get("ssh_auth_method") or "Private Key").strip()
    if method not in {"Private Key", "Password"}:
        frappe.throw(_("SSH Authentication Method is invalid."), frappe.ValidationError)
    secret_field = "ssh_private_key" if method == "Private Key" else "ssh_password"
    if not settings.get_password(secret_field, raise_exception=False):
        frappe.throw(_("The selected SSH credential is required before enabling External Backup."), frappe.ValidationError)


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


def _settings_values(settings: Any, *, include_backups: bool = True) -> dict[str, Any]:
    values: dict[str, Any] = {}
    print_values = _print_identity_values(settings)
    whatsapp_values = _whatsapp_message_values(settings)
    for fieldname in _SETTINGS_FIELDS:
        if not include_backups and fieldname in (
            _BACKUP_BOOLEAN_FIELDS | _BACKUP_INTEGER_FIELDS | _BACKUP_TEXT_FIELDS
        ):
            continue
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
        if fieldname == "default_deduct_edge_thickness":
            from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
                coerce_deduct_edge_thickness,
            )

            value = 1 if coerce_deduct_edge_thickness(value) else 0
        elif fieldname in {"allow_stage_override", "allow_unplaced_approval", *_BACKUP_BOOLEAN_FIELDS}:
            value = int(value or 0)
        elif fieldname in _BACKUP_INTEGER_FIELDS:
            value = cint(value)
        elif fieldname.endswith("_backup_time"):
            value = _backup_time(value, "03:00" if fieldname.startswith("external") else "02:00")
        elif fieldname in _BACKUP_TEXT_FIELDS:
            value = str(value or "")
        elif fieldname == "default_packing_mode":
            value = public_mode_value(value)
        elif fieldname in _CNC_TEXT_FIELDS:
            value = str(value or "")
        elif fieldname in _CNC_INTEGER_FIELDS:
            value = cint(value)
        elif fieldname not in {"default_cutting_machine_type", "default_production_routing"}:
            value = flt(value)
            if fieldname == "optimal_search_piece_limit":
                value = cint(value)
        values[fieldname] = value
    if include_backups:
        values["ssh_password_configured"] = bool(settings.get_password("ssh_password", raise_exception=False))
        values["ssh_private_key_configured"] = bool(settings.get_password("ssh_private_key", raise_exception=False))
        values["ssh_private_key_passphrase_configured"] = bool(
            settings.get_password("ssh_private_key_passphrase", raise_exception=False)
        )
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
    values = _settings_values(
        settings,
        include_backups=Capability.MANAGE_BACKUPS in granted,
    )
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
        "cnc_tool_presets": _cnc_tool_preset_catalog(),
        "cnc_machines": _cnc_machine_catalog(),
        "cnc_machining_profiles": machining_profile_catalog(),
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


def _optional_pass_depth(value: Any) -> Any:
    if value in (None, "", 0, 0.0):
        return None
    return value


def _cnc_machine_catalog() -> list[dict[str, Any]]:
    if not frappe.db.exists("DocType", "CNC Machine"):
        return []
    rows = frappe.get_all(
        "CNC Machine",
        fields=["name", "machine_name", "width_cm", "length_cm", "enabled"],
        order_by="machine_name asc",
        limit_page_length=0,
    )
    return [
        {
            "name": row.name,
            "machine_name": row.machine_name,
            "width_cm": row.width_cm,
            "length_cm": row.length_cm,
            "enabled": bool(cint(row.enabled)),
        }
        for row in rows
    ]


def _cnc_tool_preset_catalog() -> list[dict[str, Any]]:
    rows = frappe.get_all(
        "CNC Tool Preset",
        fields=[
            "name",
            "preset_name",
            "tool_name",
            "tool_number",
            "tool_diameter_mm",
            "final_depth_mm",
            "spindle_speed_rpm",
            "feed_rate_mm_min",
            "plunge_rate_mm_min",
            "pass_depth_mm",
            "enabled",
            "tool_type",
            "tool_units",
            "rate_units",
            "notes",
            "stepdown_mm",
            "final_tool_offset_mm",
            "stepover_size_mm",
            "stepover_percent",
            "feed_rate_mm_sec",
            "plunge_rate_mm_sec",
        ],
        order_by="preset_name asc",
        limit_page_length=0,
    )
    return [
        {
            "name": row.name,
            "preset_name": row.preset_name,
            "tool_name": row.tool_name,
            "tool_number": row.tool_number,
            "tool_diameter_mm": row.tool_diameter_mm,
            "final_depth_mm": row.final_depth_mm,
            "spindle_speed_rpm": row.spindle_speed_rpm,
            "feed_rate_mm_min": row.feed_rate_mm_min,
            "plunge_rate_mm_min": row.plunge_rate_mm_min,
            "pass_depth_mm": _optional_pass_depth(row.pass_depth_mm),
            "enabled": bool(cint(row.enabled)),
            "tool_type": row.tool_type or "",
            "tool_units": row.tool_units or "",
            "rate_units": row.rate_units or "",
            "notes": row.notes or "",
            "description": row.tool_name or "",
            "diameter_mm": row.tool_diameter_mm,
            "stepdown_mm": row.stepdown_mm,
            "final_tool_offset_mm": row.final_tool_offset_mm,
            "stepover_size_mm": row.stepover_size_mm,
            "stepover_percent": row.stepover_percent,
            "feed_rate_mm_sec": row.feed_rate_mm_sec,
            "plunge_rate_mm_sec": row.plunge_rate_mm_sec,
        }
        for row in rows
    ]


def _require_tool_preset_editor() -> None:
    require_doctype_capability(
        Capability.EDIT_FACTORY_CNC_DEFAULTS,
        message=_("You do not have permission to edit CNC tool presets."),
    )


def _preset_message(code: str) -> str:
    messages = {
        "preset_name_required": "Enter a preset name.",
        "tool_name_required": "Enter a tool name.",
        "tool_number_invalid": "Tool number must look like T9.",
        "tool_diameter_invalid": "Tool diameter must be a positive number of millimetres within the supported range.",
        "final_depth_invalid": "Final depth must be a positive number of millimetres within the supported range.",
        "spindle_speed_invalid": "Spindle speed must be a positive whole number of RPM within the supported range.",
        "feed_rate_invalid": "Feed rate must be a positive number of millimetres per minute within the supported range.",
        "plunge_rate_invalid": "Plunge rate must be a positive number of millimetres per minute within the supported range.",
        "pass_depth_invalid": "Pass depth must be a positive number of millimetres within the supported range.",
        "pass_depth_exceeds_final_depth": "Pass depth cannot be deeper than the final depth.",
        "preset_not_found": "The selected CNC tool preset does not exist.",
    }
    return _(messages.get(code, "The CNC tool preset is not valid."))


def _apply_tool_preset(document: Any, preset: Any, *, keep_name: bool) -> None:
    if not keep_name:
        document.preset_name = preset.preset_name
    document.tool_name = preset.tool_name
    document.tool_number = preset.tool_number
    document.tool_diameter_mm = preset.tool_diameter_mm
    document.final_depth_mm = preset.final_depth_mm
    document.spindle_speed_rpm = preset.spindle_speed_rpm
    document.feed_rate_mm_min = preset.feed_rate_mm_min
    document.plunge_rate_mm_min = preset.plunge_rate_mm_min
    document.pass_depth_mm = preset.pass_depth_mm
    document.enabled = 1 if preset.enabled else 0


def _tool_preset_use_counts(name: str) -> tuple[int, int, int, int, int]:
    operations = cint(frappe.db.count("CNC Operational Operation", {"tool_preset": name}))
    paths = cint(frappe.db.count("CNC Operational Path", {"tool_preset": name}))
    settings = frappe.get_single("Almdina ERP Settings")
    factory = sum(1 for fieldname in _CNC_PRESET_FIELDS if str(settings.get(fieldname) or "") == name)
    profile_uses = 0
    association_uses = 0
    snapshot_uses = 0
    for row in frappe.get_all(
        "CNC Operational File",
        fields=["machining_profiles_json", "vector_associations_json", "toolpath_snapshots_json"],
    ):
        uses = machining_tool_uses(
            name,
            profiles=_json_rows(row.machining_profiles_json),
            associations=_json_rows(row.vector_associations_json),
            snapshots=_json_rows(row.toolpath_snapshots_json),
        )
        profile_uses += uses["profiles"]
        association_uses += uses["associations"]
        snapshot_uses += uses["snapshots"]
    profile_uses += _catalog_profile_uses(name)
    return operations, paths, factory, profile_uses + association_uses, snapshot_uses


def _catalog_profile_uses(name: str) -> int:
    if not frappe.db.exists("DocType", "CNC Machining Profile"):
        return 0
    return cint(frappe.db.count("CNC Machining Profile", {"tool_preset": name}))


def _json_rows(raw: Any) -> list[Any]:
    if not raw:
        return []
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return list(parsed or []) if isinstance(parsed, list) else []


def _artcam_message(code: str) -> str:
    messages = {
        "tool_type_unsupported": "Only a Ball Nose tool can be created here.",
        "tool_units_invalid": "Tool units must be mm.",
        "rate_units_invalid": "Rate units must be mm/sec.",
        "description_required": "Enter the tool description.",
        "tool_number_invalid": "Tool number must be a whole number such as 9.",
        "tool_diameter_invalid": "Diameter must be a positive number of millimetres.",
        "stepdown_invalid": "Stepdown must be a positive number of millimetres.",
        "final_tool_offset_invalid": "Final tool offset must be zero or a positive number of millimetres.",
        "stepover_invalid": "Enter the stepover size and its percent of diameter.",
        "spindle_speed_invalid": "Spindle speed must be a positive whole number of RPM.",
        "feed_rate_invalid": "Feed rate must be a positive number of millimetres per second.",
        "plunge_rate_invalid": "Plunge rate must be a positive number of millimetres per second.",
        "notes_invalid": "The tool notes are too long.",
    }
    return _(messages.get(code, "The CNC tool is not valid."))


@frappe.whitelist()
def save_artcam_tool(values: str | dict[str, Any]) -> dict[str, Any]:
    """Create or update a Ball Nose tool. Profiles keep their own copies."""

    _require_tool_preset_editor()
    payload = _payload(values)
    try:
        tool = normalize_artcam_tool(payload)
    except MachiningSetupError as exc:
        frappe.throw(_artcam_message(exc.code), frappe.ValidationError)
    updates = artcam_tool_storage(tool)
    name = str(payload.get("name") or "").strip()
    if name and frappe.db.exists("CNC Tool Preset", name):
        document = frappe.get_doc("CNC Tool Preset", name)
        document.check_permission("write")
        for fieldname, value in updates.items():
            document.set(fieldname, value)
        document.save()
    else:
        if name and name != tool.description:
            frappe.throw(_("The tool description cannot be changed."), frappe.ValidationError)
        if frappe.db.exists("CNC Tool Preset", tool.description):
            frappe.throw(_("A tool with this description already exists."), frappe.ValidationError)
        document = frappe.new_doc("CNC Tool Preset")
        document.check_permission("create")
        document.preset_name = tool.description
        document.enabled = 1
        for fieldname, value in updates.items():
            document.set(fieldname, value)
        document.insert()
    return get_production_settings()


def _require_machining_profile_editor() -> None:
    require_doctype_capability(
        Capability.EDIT_FACTORY_CNC_DEFAULTS,
        message=_("You do not have permission to edit ArtCAM machining profiles."),
    )


def _profile_message(code: str) -> str:
    messages = {
        "profile_name_required": "Enter a profile name.",
        "profile_id_invalid": "The profile identity is not valid.",
        "tool_preset_required": "Choose a tool for this profile.",
        "preset_not_found": "The selected CNC tool preset does not exist.",
        "preset_disabled": "The selected CNC tool preset is disabled.",
        "safe_z_invalid": "Safe Z must be zero or a positive number of millimetres within the supported range.",
        "home_x_invalid": "Home X must be a finite number of millimetres.",
        "home_y_invalid": "Home Y must be a finite number of millimetres.",
        "home_z_invalid": "Home Z must be zero or a positive number of millimetres within the supported range.",
        "final_depth_invalid": "Final depth must be a positive number of millimetres within the supported range.",
        "pass_depth_exceeds_final_depth": "Pass depth cannot be deeper than the final depth.",
    }
    if code in messages:
        return _(messages[code])
    return _artcam_message(code)


@frappe.whitelist()
def save_cnc_machining_profile(values: str | dict[str, Any]) -> dict[str, Any]:
    """Create or update one ArtCAM profile. The tool and saved sheet copies stay unchanged."""

    _require_machining_profile_editor()
    payload = _payload(values)
    profile_id = str(payload.get("profile_id") or "").strip()
    try:
        profile = normalize_profile(
            payload,
            known_tools=known_tool_presets(),
            profile_id=profile_id or new_machining_id("profile"),
        )
    except MachiningSetupError as exc:
        frappe.throw(_profile_message(exc.code), frappe.ValidationError)
    existing_name = ""
    if profile_id:
        existing_name = str(
            frappe.db.get_value("CNC Machining Profile", {"profile_id": profile_id}, "name") or ""
        )
        if not existing_name:
            frappe.throw(_profile_message("profile_id_invalid"), frappe.ValidationError)
        document = frappe.get_doc("CNC Machining Profile", existing_name)
        document.check_permission("write")
    else:
        document = frappe.new_doc("CNC Machining Profile")
        document.check_permission("create")
        document.profile_id = profile["profile_id"]
    document.profile_name = profile["name"]
    document.tool_preset = profile["tool_preset"]
    document.tool_values_json = profile["tool_values"]
    document.final_depth_mm = profile["final_depth_mm"]
    document.safe_z_mm = profile["safe_z_mm"]
    document.home_x_mm = profile["home_x_mm"]
    document.home_y_mm = profile["home_y_mm"]
    document.home_z_mm = profile["home_z_mm"]
    document.enabled = 1
    if existing_name:
        document.save()
    else:
        document.insert()
    return get_production_settings()


@frappe.whitelist()
def save_cnc_tool_preset(values: str | dict[str, Any]) -> dict[str, Any]:
    """Create or update one tool preset. The caller must manage factory CNC defaults."""

    _require_tool_preset_editor()
    payload = _payload(values)
    try:
        preset = normalize_tool_preset(payload)
    except ToolPresetError as exc:
        frappe.throw(_preset_message(exc.code), frappe.ValidationError)
    name = str(payload.get("name") or "").strip()
    if name and frappe.db.exists("CNC Tool Preset", name):
        document = frappe.get_doc("CNC Tool Preset", name)
        document.check_permission("write")
        if preset.preset_name != str(document.preset_name or ""):
            frappe.throw(_("The preset name cannot be changed."), frappe.ValidationError)
        _apply_tool_preset(document, preset, keep_name=True)
        document.save()
    else:
        if name and name != preset.preset_name:
            frappe.throw(_("The preset name cannot be changed."), frappe.ValidationError)
        document = frappe.new_doc("CNC Tool Preset")
        document.check_permission("create")
        _apply_tool_preset(document, preset, keep_name=False)
        document.insert()
    return get_production_settings()


@frappe.whitelist()
def set_cnc_tool_preset_enabled(name: str, enabled: int | str | bool = 0) -> dict[str, Any]:
    """Disable or enable a preset without removing the sheets that already use it."""

    _require_tool_preset_editor()
    preset_name = str(name or "").strip()
    if not preset_name or not frappe.db.exists("CNC Tool Preset", preset_name):
        frappe.throw(_preset_message("preset_not_found"), frappe.ValidationError)
    document = frappe.get_doc("CNC Tool Preset", preset_name)
    document.check_permission("write")
    turning_off = not cint(enabled)
    if turning_off:
        _operations, _paths, _factory, live_uses, _snapshot_uses = _tool_preset_use_counts(preset_name)
        if live_uses:
            frappe.throw(
                _("This tool is still selected by a profile or vector association. Calculated toolpaths keep their own copy, but those live selections must choose another tool before this one can be disabled."),
                frappe.ValidationError,
            )
    document.enabled = 1 if cint(enabled) else 0
    document.save()
    return get_production_settings()


@frappe.whitelist()
def delete_cnc_tool_preset(name: str) -> dict[str, Any]:
    """Delete a preset only when no sheet, path, or factory default still points at it."""

    _require_tool_preset_editor()
    preset_name = str(name or "").strip()
    if not preset_name or not frappe.db.exists("CNC Tool Preset", preset_name):
        frappe.throw(_preset_message("preset_not_found"), frappe.ValidationError)
    operations, paths, factory, live_uses, snapshot_uses = _tool_preset_use_counts(preset_name)
    if not unused_tool_preset_can_be_deleted(
        operation_uses=operations,
        path_uses=paths,
        factory_uses=factory,
        machining_uses=live_uses + snapshot_uses,
    ):
        frappe.throw(
            _("This tool is used by a sheet, a profile, a vector association, or a calculated toolpath. It cannot be deleted."),
            frappe.ValidationError,
        )
    document = frappe.get_doc("CNC Tool Preset", preset_name)
    document.check_permission("delete")
    document.delete()
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
    "delete_cnc_tool_preset",
    "get_factory_settings_audit",
    "get_print_identity",
    "get_production_settings",
    "save_cnc_machining_profile",
    "save_cnc_tool_preset",
    "set_cnc_tool_preset_enabled",
    "update_production_settings",
    "whatsapp_message_templates",
    "whatsapp_stage_message_template",
]
