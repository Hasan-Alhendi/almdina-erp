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


def test_dual_plan_helper_is_confined_to_historical_export_bridge() -> None:
    # Shop-floor runtime was migrated in A6.3. The only remaining caller is the
    # saved-order export fallback for records predating canonical Cutting Plan.
    assert _matches("dual_plan_fields") == [
        "almdina_erp/services/export_validation_service.py"
    ]


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


def test_shop_floor_plan_reads_are_canonical_only() -> None:
    repository = (
        APP / "infrastructure" / "frappe" / "shop_floor_query_repository.py"
    ).read_text(encoding="utf-8")

    assert "production_plan_facts" in repository
    assert "current_working_plan" in repository
    assert "latest_plan" in repository
    assert "source_type=UPLOADED_DXF" in repository
    assert "source_type=SYSTEM" in repository
    assert "dual_plan_fields" not in repository

    summaries = repository.split("def order_summaries", 1)[1].split(
        "\n    def get_order", 1
    )[0]
    for legacy_db_field in (
        '"cutting_plan_json",',
        '"plan_needs_recalculation",',
        '"production_dxf",',
        '"system_plan_json",',
        '"custom_plan_json",',
    ):
        assert legacy_db_field not in summaries
    assert "facts.has_cutting_plan" in summaries
    assert "facts.plan_needs_recalculation" in summaries
    assert "dxf_plan" in summaries


def test_shop_floor_command_state_is_built_from_canonical_plan_facts() -> None:
    repository = (
        APP / "infrastructure" / "frappe" / "shop_floor_command_repository.py"
    ).read_text(encoding="utf-8")
    commands = (APP / "application" / "shop_floor" / "commands.py").read_text(
        encoding="utf-8"
    )

    state = repository.split("def get_order_state", 1)[1].split(
        "\n    def get_stage_state", 1
    )[0]
    assert "plan = production_plan_facts(order)" in state
    assert "has_cutting_plan=plan.has_cutting_plan" in state
    assert "plan_needs_recalculation=plan.plan_needs_recalculation" in state
    assert "has_approved_plan=plan.has_approved_plan" in state
    assert "order.plan_needs_recalculation" not in repository

    # These tokens are reads from the pure application OrderState DTO, not from
    # a Frappe Door Cutting Order document. The repository above proves their
    # source is canonical Cutting Plan facts.
    assert "class OrderState:" in commands
    assert "plan_needs_recalculation: bool" in commands
    assert "order.plan_needs_recalculation" in commands
    assert "import frappe" not in commands
    assert "from frappe" not in commands


def test_direct_legacy_dco_plan_reads_are_confined_to_named_migration_bridges() -> None:
    # Direct persisted-order reads are exceptional in A6.3. API fallback keeps
    # historical locked orders readable; upload fallback distinguishes a legacy
    # pre-A2 DXF. The application shop-floor command hit is a canonical DTO read
    # and is separately proved above rather than treated as persisted DCO state.
    allowed: dict[str, set[str]] = {
        "order.cutting_plan_json": {"almdina_erp/api.py"},
        "order.system_plan_json": set(),
        "order.custom_plan_json": set(),
        "order.approved_plan_source": set(),
        "order.plan_needs_recalculation": {
            "almdina_erp/application/shop_floor/commands.py",
        },
        "order.production_dxf": {
            "almdina_erp/services/shop_floor_dxf_service.py",
        },
        "order.packing_mode": set(),
        "order.cutting_machine_type": set(),
        "order.kerf_mm": set(),
        "order.trim_margin_mm": set(),
    }

    for token, expected_paths in allowed.items():
        assert set(_matches(token)) == expected_paths, token


def test_historical_projection_boundary_is_read_only() -> None:
    boundary = (
        APP
        / "infrastructure"
        / "frappe"
        / "legacy_plan_projection_reader.py"
    ).read_text(encoding="utf-8")
    dual = (APP / "services" / "dual_plan_fields.py").read_text(encoding="utf-8")

    for fieldname in (
        "cutting_plan_json",
        "system_plan_json",
        "custom_plan_json",
        "approved_plan_source",
        "production_dxf",
        "kerf_mm",
    ):
        assert fieldname in boundary
    for forbidden in (
        "frappe.db.set_value",
        "frappe.new_doc",
        ".insert(",
        ".save(",
        "ignore_permissions",
    ):
        assert forbidden not in boundary
    assert "legacy_system_plan_json" in dual
    assert "legacy_custom_plan_json" in dual
    assert "_retired_writer" in dual
    assert "frappe.db" not in dual
    assert "ignore_permissions" not in dual


def test_allowed_noncanonical_paths_are_documented_and_nonpersistent() -> None:
    export = (APP / "services" / "dxf_export_service.py").read_text(encoding="utf-8")
    upload = (APP / "services" / "shop_floor_dxf_service.py").read_text(encoding="utf-8")
    preview = (
        APP / "infrastructure" / "frappe" / "orders" / "plan_adapter.py"
    ).read_text(encoding="utf-8")

    assert "Read-only migration bridge for orders predating canonical Cutting Plan." in export
    assert "One-time migration fallback for a legacy pre-A2 custom DXF" in upload
    # The DCO plan adapter survives only for transient preview/experiment paths.
    # It may mutate its in-memory document but may not persist or bypass security.
    assert "class FrappeOrderPlanAdapter" in preview
    assert "optimize_order_plan" in preview
    assert "frappe.db.set_value" not in preview
    assert ".save(" not in preview
    assert ".insert(" not in preview
    assert "ignore_permissions" not in preview


def test_a63_keeps_schema_until_historical_data_migration_is_complete() -> None:
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
