from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"


def _python_sources() -> list[Path]:
    return sorted(path for path in APP.rglob("*.py") if "__pycache__" not in path.parts)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _matches(token: str) -> list[str]:
    hits: list[str] = []
    for path in _python_sources():
        if token in path.read_text(encoding="utf-8"):
            hits.append(_relative(path))
    return hits


def test_retired_snapshot_service_has_no_runtime_callers() -> None:
    # The fail-closed module may remain importable during the migration window,
    # but no production module is allowed to route through it anymore.
    assert _matches("cutting_plan_snapshot_service") == []


def test_dual_plan_helper_has_no_runtime_callers_before_retirement() -> None:
    # A6.3 proves whether the old DCO dual-plan helper can be removed safely.
    # Its own source does not contain the module name, so every hit is a caller.
    assert _matches("dual_plan_fields") == []


def test_retired_snapshot_surface_contains_no_old_aggregate_logic_or_bypass() -> None:
    snapshot = (APP / "services" / "cutting_plan_snapshot_service.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "order.cutting_plan_json",
        "order.system_plan_json",
        "order.custom_plan_json",
        "order.packing_mode",
        "order.cutting_machine_type",
        "order.kerf_mm",
        "order.trim_margin_mm",
        "order.plan_needs_recalculation",
        "order.production_dxf",
        "order.board_rate_usd",
        "order.cutting_cost_per_board_usd",
        "frappe.db.set_value",
        "frappe.new_doc",
        ".insert(",
        ".save(",
        "ignore_permissions",
    ):
        assert forbidden not in snapshot
    assert "_retired_snapshot_api" in snapshot


def test_cutting_plan_compatibility_facade_does_not_import_snapshot_owner() -> None:
    facade = (APP / "services" / "cutting_plan_service.py").read_text(
        encoding="utf-8"
    )
    assert "cutting_plan_snapshot_service" not in facade
    assert "_snapshot." not in facade
    assert "_retired_snapshot_api" in facade
    assert "approve_production_dxf" in facade
    assert "validate_order_for_dispatch" in facade


def test_direct_legacy_dco_plan_reads_are_confined_to_named_migration_bridges() -> None:
    # Exact attribute reads distinguish DCO reads from response keys, schema
    # field names, and canonical Cutting Plan attributes with the same labels.
    allowed: dict[str, set[str]] = {
        "order.cutting_plan_json": {
            "almdina_erp/services/dxf_export_service.py",
        },
        "order.system_plan_json": set(),
        "order.custom_plan_json": set(),
        "order.approved_plan_source": set(),
        "order.plan_needs_recalculation": set(),
        "order.production_dxf": {
            "almdina_erp/services/shop_floor_dxf_service.py",
        },
        "order.packing_mode": {
            "almdina_erp/infrastructure/frappe/orders/plan_adapter.py",
        },
        "order.cutting_machine_type": {
            "almdina_erp/infrastructure/frappe/orders/plan_adapter.py",
        },
        "order.kerf_mm": {
            "almdina_erp/infrastructure/frappe/orders/plan_adapter.py",
            "almdina_erp/services/dxf_export_service.py",
        },
        "order.trim_margin_mm": {
            "almdina_erp/infrastructure/frappe/orders/plan_adapter.py",
        },
    }

    for token, expected_paths in allowed.items():
        assert set(_matches(token)) == expected_paths, token


def test_allowed_legacy_reads_are_documented_read_only_bridges() -> None:
    export = (APP / "services" / "dxf_export_service.py").read_text(encoding="utf-8")
    upload = (APP / "services" / "shop_floor_dxf_service.py").read_text(encoding="utf-8")
    preview = (
        APP / "infrastructure" / "frappe" / "orders" / "plan_adapter.py"
    ).read_text(encoding="utf-8")

    assert "Read-only migration bridge for orders predating canonical Cutting Plan." in export
    assert "One-time migration fallback for a legacy pre-A2 custom DXF" in upload
    assert "def persist" in preview
    # Preview adapter may mutate only the in-memory copied order supplied by the
    # experiment flow; it must never bypass permissions or persist directly.
    assert "frappe.db.set_value" not in preview
    assert "ignore_permissions" not in preview


def test_a63_keeps_schema_until_zero_read_data_migration_is_complete() -> None:
    dco = json.loads(
        (APP / "doctype" / "door_cutting_order" / "door_cutting_order.json").read_text(
            encoding="utf-8"
        )
    )
    fields = {row["fieldname"] for row in dco["fields"]}
    for legacy_field in (
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "cutting_plan_json",
        "system_plan_json",
        "custom_plan_json",
        "plan_needs_recalculation",
        "production_dxf",
        "approved_plan_source",
    ):
        assert legacy_field in fields

    # Real DCO-owned relationship/workflow fields survive schema retirement too.
    assert "approved_plan" in fields
    assert "drawing_dxf_status" in fields
