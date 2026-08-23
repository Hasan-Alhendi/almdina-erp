from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORDER_SCHEMA = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.json"
)
PLAN_SCHEMA = ROOT / "almdina_erp" / "doctype" / "cutting_plan" / "cutting_plan.json"
METADATA_SYNC = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "cutting_plan_surface_metadata.py"
)
LIFECYCLE = ROOT / "lifecycle.py"
PERMISSION_MATRIX = (
    ROOT / "almdina_erp" / "application" / "security" / "permission_matrix.py"
)

DCO_PLAN_PRESENTATION_LEVEL_ZERO_FIELDS = {
    "results_tab",
    "plan_actions_section",
    "plan_control_actions",
    "plan_section",
    "cutting_plan_html",
    "total_area_m2",
    "total_edge_meters",
    "required_boards",
    "waste_area_m2",
    "waste_percent",
}

RETIRED_DCO_PLAN_FIELDS = {
    "cut_geometry_section",
    "kerf_mm",
    "trim_margin_mm",
    "optimizer_section",
    "packing_mode",
    "cutting_machine_type",
    "optimization_time_limit_sec",
    "cutting_plan_json",
    "system_plan_json",
    "custom_plan_json",
    "approved_plan_source",
    "production_dxf",
}

CANONICAL_PLAN_FIELDS = {
    "optimization_mode",
    "machine_type",
    "optimization_time_limit_sec",
    "kerf_mm",
    "trim_margin_mm",
    "plan_needs_recalculation",
    "input_fingerprint",
    "metadata_fingerprint",
    "dxf_file",
    "snapshot_json",
}

COST_LEVEL_ONE_FIELDS = {
    "board_rate_usd",
    "cutting_cost_per_board_usd",
    "mdf_cost_usd",
    "cutting_cost_usd",
    "edge_cost_usd",
    "total_cost_usd",
    "material_variance_cost_usd",
    "internal_loss_cost_usd",
    "actual_cost_usd",
}


def test_cutting_plan_surface_never_inherits_cost_permlevel() -> None:
    order_schema = json.loads(ORDER_SCHEMA.read_text(encoding="utf-8"))
    order_fields = {row["fieldname"]: row for row in order_schema["fields"]}
    plan_schema = json.loads(PLAN_SCHEMA.read_text(encoding="utf-8"))
    plan_fields = {row["fieldname"]: row for row in plan_schema["fields"]}

    for fieldname in DCO_PLAN_PRESENTATION_LEVEL_ZERO_FIELDS:
        assert fieldname in order_fields
        assert int(order_fields[fieldname].get("permlevel", 0) or 0) == 0, fieldname

    for fieldname in RETIRED_DCO_PLAN_FIELDS:
        assert fieldname not in order_fields, fieldname

    for fieldname in CANONICAL_PLAN_FIELDS:
        assert fieldname in plan_fields, fieldname
        assert int(plan_fields[fieldname].get("permlevel", 0) or 0) == 0, fieldname

    for fieldname in COST_LEVEL_ONE_FIELDS:
        assert fieldname in order_fields
        assert int(order_fields[fieldname].get("permlevel", 0) or 0) == 1, fieldname


def test_cost_capability_projects_read_only_field_level_one_on_plan_and_legacy_order() -> None:
    source = PERMISSION_MATRIX.read_text(encoding="utf-8")
    projection = source.split("def field_permission_projection", 1)[1].split(
        "def enabled_capabilities", 1
    )[0]

    assert 'if doctype not in {"Door Cutting Order", CUTTING_PLAN_DOCTYPE}' in projection
    assert '"read": normalized[Capability.VIEW_COSTS]' in projection
    assert '"write": False' in projection
    assert "Capability.EDIT_COST_SETTINGS" not in projection
    assert "Capability.VIEW_CUTTING_PLAN" not in projection


def test_migrate_repairs_site_local_plan_permlevel_drift() -> None:
    repair = METADATA_SYNC.read_text(encoding="utf-8")
    lifecycle = LIFECYCLE.read_text(encoding="utf-8")

    assert '"plan_control_actions"' in repair
    assert '"cutting_plan_html"' in repair
    assert '"Property Setter"' in repair
    assert '"property": "permlevel"' in repair
    assert "set permlevel = 0" in repair
    assert "frappe.clear_cache(doctype=DOCTYPE)" in repair
    assert "sync_cutting_plan_surface_metadata()" in lifecycle


def test_migrate_repairs_hidden_plan_command_containers() -> None:
    repair = METADATA_SYNC.read_text(encoding="utf-8")

    assert "VISIBLE_PLAN_SURFACE_FIELDS" in repair
    assert '"plan_actions_section"' in repair
    assert '("hidden", VISIBLE_PLAN_SURFACE_FIELDS)' in repair
    assert '("depends_on", VISIBLE_PLAN_SURFACE_FIELDS)' in repair
    assert "set hidden = 0" in repair
    assert "depends_on = null" in repair


def test_plan_commands_use_a_native_full_width_section_without_native_settings_fields() -> None:
    schema = json.loads(ORDER_SCHEMA.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in schema["fields"]}
    order = schema["field_order"]

    assert fields["plan_actions_section"]["fieldtype"] == "Section Break"
    assert fields["plan_control_actions"]["fieldtype"] == "HTML"
    assert order.index("plan_actions_section") + 1 == order.index("plan_control_actions")
    for retired in ("cut_geometry_section", "optimizer_section", "kerf_mm", "trim_margin_mm", "packing_mode"):
        assert retired not in fields


def test_plan_metadata_repair_does_not_touch_cost_fields() -> None:
    repair = METADATA_SYNC.read_text(encoding="utf-8")

    for fieldname in COST_LEVEL_ONE_FIELDS:
        assert f'"{fieldname}"' not in repair
