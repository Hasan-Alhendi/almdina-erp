from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_plan_commands_no_longer_mirror_plan_state_to_dco() -> None:
    command = source("almdina_erp/services/cutting_plan_command_service.py")

    assert "def _set_order_projection" not in command
    assert "def _set_dxf_order_projection" not in command
    assert "project_plan_costs_to_order" not in command
    assert "mirror_uploaded_dxf_projection" not in command

    for obsolete_write in (
        '"production_dxf": plan.dxf_file',
        '"custom_plan_json": snapshot_json',
        '"system_plan_json": snapshot_json',
        '"cutting_plan_source": source_label',
        '"approved_plan_source": source_label',
        '"plan_needs_recalculation": 0',
        '"calculated_plan_input_hash": plan.input_fingerprint',
        '"calculated_plan_metadata_hash": plan.metadata_fingerprint',
    ):
        assert obsolete_write not in command


def test_approval_keeps_only_real_order_relation_and_workflow_signal() -> None:
    command = source("almdina_erp/services/cutting_plan_command_service.py")
    relation = section(
        command,
        "def _set_approved_plan_relation",
        "def _legacy_plan_source",
    )

    assert '"approved_plan"' in relation
    assert "plan.name" in relation
    assert "_set_drawing_dxf_status" in relation
    for compatibility_field in (
        "approved_plan_source",
        "cutting_plan_source",
        "cutting_plan_json",
        "system_plan_json",
        "custom_plan_json",
        "production_dxf",
        "required_boards",
        "waste_area_m2",
        "waste_percent",
        "packing_method",
        "packing_score",
        "plan_needs_recalculation",
    ):
        assert compatibility_field not in relation


def test_dxf_upload_finishes_with_order_owned_state_not_plan_mirror() -> None:
    service = source("almdina_erp/services/shop_floor_dxf_service.py")
    upload = section(
        service,
        "def upload_production_dxf",
        "\n\n@frappe.whitelist()\ndef recalculate_drawing_plan",
    )

    assert "finalize_uploaded_dxf_order_state(order, plan)" in upload
    assert "mirror_uploaded_dxf_projection" not in service
    assert "Cutting Plan persistence -> File attachment -> order-owned workflow state" in service


def test_plan_cost_commands_refresh_only_order_commercial_aggregates() -> None:
    cost_command = source("almdina_erp/services/cutting_plan_cost_command_service.py")
    costing = source(
        "almdina_erp/infrastructure/frappe/cutting_plan_costing_workspace.py"
    )

    assert "refresh_order_commercial_totals(order, plan)" in cost_command
    assert "project_plan_costs_to_order" not in cost_command

    compatibility = section(
        costing,
        "def project_plan_costs_to_order",
        "def current_cost_plan",
    )
    assert "refresh_order_commercial_totals(order, plan)" in compatibility
    assert "PLAN_COST_FIELDS" not in compatibility
    assert "frappe.db.set_value" not in compatibility

    commercial = section(
        costing,
        "def refresh_order_commercial_totals",
        "def project_plan_costs_to_order",
    )
    for order_owned_field in (
        "special_shapes_baseline_cost_usd",
        "special_shapes_estimated_total_usd",
        "special_shapes_final_total_usd",
        "customer_quote_total_usd",
        "customer_quote_status",
    ):
        assert order_owned_field in commercial
    for plan_owned_field in (
        '"board_rate_usd"',
        '"cutting_cost_per_board_usd"',
        '"mdf_cost_usd"',
        '"cutting_cost_usd"',
        '"edge_cost_usd"',
        '"total_cost_usd"',
    ):
        assert plan_owned_field not in commercial


def test_invalidation_marks_only_canonical_cutting_plan_drafts() -> None:
    invalidation = source("almdina_erp/services/cutting_plan_invalidation_service.py")

    assert 'frappe.db.set_value(\n            "Cutting Plan"' in invalidation
    assert '"Door Cutting Order"' not in invalidation
    assert "order.plan_needs_recalculation" not in invalidation


def test_plan_prints_read_optimizer_mode_from_approved_cutting_plan() -> None:
    for relative in (
        "almdina_erp/print_format/door_cutting_plan_official/door_cutting_plan_official.json",
        "almdina_erp/print_format/door_cutting_plan_production_a4/door_cutting_plan_production_a4.json",
    ):
        payload = json.loads(source(relative))
        html = payload["html"]
        assert 'frappe.get_doc("Cutting Plan", doc.approved_plan)' in html
        assert "plan.optimization_mode" in html
        assert "doc.packing_mode" not in html


def test_a62_does_not_delete_legacy_schema_or_add_permission_bypasses() -> None:
    dco = json.loads(
        source("almdina_erp/doctype/door_cutting_order/door_cutting_order.json")
    )
    fields = {row["fieldname"] for row in dco["fields"]}
    for migration_field in (
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "cutting_plan_json",
        "system_plan_json",
        "custom_plan_json",
        "plan_needs_recalculation",
        "approved_plan",
    ):
        assert migration_field in fields

    for relative in (
        "almdina_erp/services/cutting_plan_command_service.py",
        "almdina_erp/services/cutting_plan_invalidation_service.py",
        "almdina_erp/services/shop_floor_dxf_service.py",
        "almdina_erp/services/cutting_plan_cost_command_service.py",
        "almdina_erp/infrastructure/frappe/cutting_plan_costing_workspace.py",
    ):
        assert "ignore_permissions" not in source(relative)


def test_read_only_legacy_migration_bridges_remain_for_historical_orders() -> None:
    costing = source(
        "almdina_erp/infrastructure/frappe/cutting_plan_costing_workspace.py"
    )
    export = source("almdina_erp/services/dxf_export_service.py")

    assert 'source_doctype = "Cutting Plan" if based_on_plan else "Door Cutting Order"' in costing
    assert "Read-only migration bridge for orders predating canonical Cutting Plan." in export
    assert "_stored_order_export_snapshot(order)" in export
