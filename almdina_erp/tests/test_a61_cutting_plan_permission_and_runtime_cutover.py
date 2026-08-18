from __future__ import annotations

import json
from pathlib import Path

from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    CUTTING_PLAN_DOCTYPE,
    Capability,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    field_permission_projection,
    normalize_capability_state,
    standard_permission_projection,
)


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_plan_owned_capabilities_are_attached_to_cutting_plan() -> None:
    expected = {
        Capability.VIEW_COSTS,
        Capability.EDIT_COST_SETTINGS,
        Capability.VIEW_CUTTING_PLAN,
        Capability.VIEW_SYSTEM_CUTTING_PLAN,
        Capability.VIEW_UPLOADED_CUTTING_PLAN,
        Capability.VIEW_APPROVED_CUTTING_PLAN,
        Capability.RECALCULATE_PLAN,
        Capability.EDIT_OPTIMIZER_SETTINGS,
        Capability.PRINT_CUTTING_PLAN,
        Capability.APPROVE_DXF,
        Capability.EXPORT_DXF,
        Capability.UPLOAD_DXF,
        Capability.REPLACE_DXF,
        Capability.ARCHIVE_APPROVED_PLAN,
    }
    assert all(CAPABILITY_CATALOG[key].applies_to == CUTTING_PLAN_DOCTYPE for key in expected)

    # These operations still mutate customer/order input and must stay order-owned.
    assert CAPABILITY_CATALOG[Capability.EDIT_SPECIAL_PRICE].applies_to == "Door Cutting Order"
    assert CAPABILITY_CATALOG[Capability.APPROVE_SPECIAL_PRICE].applies_to == "Door Cutting Order"
    assert CAPABILITY_CATALOG[Capability.EDIT_SPECIAL_DRAWING].applies_to == "Door Cutting Order"


def test_plan_capability_implies_parent_order_read_but_not_order_edit() -> None:
    normalized = normalize_capability_state({Capability.EDIT_OPTIMIZER_SETTINGS: True})
    assert normalized[Capability.VIEW_ORDERS] is True
    assert normalized[Capability.VIEW_CUTTING_PLAN] is True
    assert normalized[Capability.RECALCULATE_PLAN] is True
    assert normalized[Capability.EDIT_ORDER] is False


def test_cutting_plan_native_projection_is_read_only_and_cost_fields_are_command_owned() -> None:
    state = {
        Capability.VIEW_CUTTING_PLAN: True,
        Capability.VIEW_SYSTEM_CUTTING_PLAN: True,
        Capability.VIEW_COSTS: True,
        Capability.EDIT_COST_SETTINGS: True,
    }
    standard = standard_permission_projection(CUTTING_PLAN_DOCTYPE, state)
    assert standard == {
        "read": True,
        "select": True,
        "create": False,
        "write": False,
        "delete": False,
    }
    fields = field_permission_projection(CUTTING_PLAN_DOCTYPE, state)
    assert fields[1] == {"read": True, "write": False}
    assert field_permission_projection("Door Cutting Order", state)[1]["write"] is False


def test_cutting_plan_schema_protects_optimizer_and_financial_snapshot() -> None:
    payload = json.loads(
        source("almdina_erp/doctype/cutting_plan/cutting_plan.json")
    )
    fields = {row["fieldname"]: row for row in payload["fields"]}

    for fieldname in (
        "optimization_mode",
        "machine_type",
        "optimization_time_limit_sec",
        "kerf_mm",
        "trim_margin_mm",
    ):
        assert fields[fieldname].get("read_only") == 1

    for fieldname in (
        "cost_snapshot_version",
        "board_rate_usd",
        "cutting_cost_per_board_usd",
        "mdf_cost_usd",
        "cutting_cost_usd",
        "edge_cost_usd",
        "total_cost_usd",
    ):
        assert fields[fieldname].get("permlevel") == 1
        assert fields[fieldname].get("read_only") == 1


def test_plan_authorization_requires_capability_and_parent_order_scope() -> None:
    authorization = source(
        "almdina_erp/infrastructure/frappe/cutting_plan_authorization.py"
    )
    assert "capability_definition(capability)" in authorization
    assert "definition.applies_to != CUTTING_PLAN_DOCTYPE" in authorization
    assert "doctype_has_capability(capability" in authorization
    assert 'frappe.has_permission(order, "read"' in authorization
    assert "allow_new_order: bool = False" in authorization
    assert "ignore_permissions" not in authorization


def test_production_readiness_no_longer_reads_dco_plan_projection() -> None:
    repository = source(
        "almdina_erp/infrastructure/frappe/shop_floor_command_repository.py"
    )
    facade = source("almdina_erp/services/shop_floor_commands.py")
    runtime = source(
        "almdina_erp/infrastructure/frappe/cutting_plan_runtime_repository.py"
    )

    for text in (repository, facade):
        assert "production_plan_facts" in text
        assert "cutting_plan_json" not in text
        assert "getattr(order, \"plan_needs_recalculation\"" not in text

    assert '"Cutting Plan"' in runtime
    assert "snapshot_json" in runtime
    assert "plan_input_fingerprint(order, plan)" in runtime
    assert "approved_plan" in runtime


def test_new_plan_settings_no_longer_seed_from_dco_optimizer_fields() -> None:
    repository = source(
        "almdina_erp/infrastructure/frappe/cutting_plan_command_repository.py"
    )
    runtime = source(
        "almdina_erp/infrastructure/frappe/cutting_plan_runtime_repository.py"
    )
    assert "_settings_from_order" not in repository
    assert "seed_plan_settings(order.name)" in repository
    assert 'frappe.get_cached_doc("Almdina ERP Settings")' in runtime
    for legacy in (
        "order.packing_mode",
        "order.cutting_machine_type",
        "order.kerf_mm",
        "order.trim_margin_mm",
        "order.optimization_time_limit_sec",
    ):
        assert legacy not in runtime


def test_dxf_validation_receives_plan_settings_explicitly() -> None:
    strict = source("almdina_erp/services/strict_dxf_import_service.py")
    upload = source("almdina_erp/services/shop_floor_dxf_service.py")
    assert "settings: PlanSettings" in strict
    assert "trim_margin_mm=settings.trim_margin_mm" in strict
    assert "kerf_mm=settings.kerf_mm" in strict
    assert 'getattr(order, "kerf_mm"' not in strict
    assert 'getattr(order, "trim_margin_mm"' not in strict
    assert "settings=seed_plan_settings(order.name)" in upload


def test_cost_workspace_no_longer_selects_plan_from_dco_source_projection() -> None:
    workspace = source(
        "almdina_erp/infrastructure/frappe/cutting_plan_costing_workspace.py"
    )
    command = source("almdina_erp/services/cutting_plan_cost_command_service.py")
    assert "current_working_plan" in workspace
    assert "cutting_plan_source" not in workspace
    assert "current_working_plan" in command
    assert "cutting_plan_source" not in command


def test_permission_sync_moves_projection_without_changing_canonical_keys() -> None:
    sync = source(
        "almdina_erp/infrastructure/frappe/permission_type_sync.py"
    )
    assert "_clear_relocated_cutting_plan_projections" in sync
    assert "_relocated_plan_permission_types" in sync
    assert '"Door Cutting Order"' in sync
    assert "CUTTING_PLAN_DOCTYPE" in sync
    # Cleanup is database projection maintenance, not an authorization bypass.
    cleanup = sync.split("def _clear_relocated_cutting_plan_projections", 1)[1].split(
        "def sync_permission_types", 1
    )[0]
    assert "ignore_permissions" not in cleanup
