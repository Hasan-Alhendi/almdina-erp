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

PLAN_LEVEL_ZERO_FIELDS = {
    "results_tab",
    "cut_geometry_section",
    "kerf_mm",
    "trim_margin_mm",
    "optimizer_section",
    "packing_mode",
    "optimization_time_limit_sec",
    "plan_control_actions",
    "plan_section",
    "cutting_plan_html",
    "total_area_m2",
    "total_edge_meters",
    "required_boards",
    "waste_area_m2",
    "waste_percent",
    "cutting_plan_json",
    "system_plan_json",
    "custom_plan_json",
    "approved_plan_source",
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
    schema = json.loads(ORDER_SCHEMA.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in schema["fields"]}

    for fieldname in PLAN_LEVEL_ZERO_FIELDS:
        assert fieldname in fields
        assert int(fields[fieldname].get("permlevel", 0) or 0) == 0, fieldname

    for fieldname in COST_LEVEL_ONE_FIELDS:
        assert fieldname in fields
        assert int(fields[fieldname].get("permlevel", 0) or 0) == 1, fieldname


def test_cost_capability_projects_only_to_field_level_one() -> None:
    source = PERMISSION_MATRIX.read_text(encoding="utf-8")

    assert "def field_permission_projection" in source
    assert 'if doctype != "Door Cutting Order"' in source
    assert '"read": normalized[Capability.VIEW_COSTS]' in source
    assert '"write": normalized[Capability.EDIT_COST_SETTINGS]' in source
    assert "Capability.VIEW_CUTTING_PLAN" not in source.split(
        "def field_permission_projection", 1
    )[1].split("def enabled_capabilities", 1)[0]


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


def test_plan_metadata_repair_does_not_touch_cost_fields() -> None:
    repair = METADATA_SYNC.read_text(encoding="utf-8")

    for fieldname in COST_LEVEL_ONE_FIELDS:
        assert f'"{fieldname}"' not in repair
