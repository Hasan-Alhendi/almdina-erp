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
    assert _matches("cutting_plan_snapshot_service") == []


def test_retired_plan_projection_facades_are_absent() -> None:
    assert _matches("dual_plan_fields") == []
    assert _matches("legacy_plan_projection_reader") == []
    assert not (APP / "services" / "dual_plan_fields.py").exists()
    assert not (
        APP / "infrastructure" / "frappe" / "legacy_plan_projection_reader.py"
    ).exists()


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

    projection = repository.split("def _project_plan_facts", 1)[1].split(
        "\n\nclass FrappeShopFloorQueryRepository", 1
    )[0]
    assert "facts = production_plan_facts(document)" in projection
    assert "facts.has_cutting_plan" in projection
    assert "facts.plan_needs_recalculation" in projection

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
    assert "_project_plan_facts" in summaries
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

    assert "class OrderState:" in commands
    assert "plan_needs_recalculation: bool" in commands
    assert "order.plan_needs_recalculation" in commands
    assert "import frappe" not in commands
    assert "from frappe" not in commands


def test_dxf_geometry_adapter_receives_plan_settings_through_a_transient_proxy() -> None:
    strict = (APP / "services" / "strict_dxf_import_service.py").read_text(
        encoding="utf-8"
    )
    legacy = (APP / "services" / "dxf_import_service.py").read_text(
        encoding="utf-8"
    )

    assert "trim_margin_mm=settings.trim_margin_mm" in strict
    assert "kerf_mm=settings.kerf_mm" in strict
    assert "_legacy_parse_production_dxf" in strict
    assert "_proxy_order(order, specs, settings)" in strict
    assert "from almdina_erp.almdina_erp.application.cutting.plan_revisions import PlanSettings" in strict
    assert "order.kerf_mm" in legacy
    assert "order.trim_margin_mm" in legacy


def test_replacement_plans_inherit_from_the_exact_approved_cutting_plan() -> None:
    snapshot = (
        APP / "infrastructure" / "frappe" / "replacements" / "snapshot_adapter.py"
    ).read_text(encoding="utf-8")
    service = (APP / "services" / "replacement_plan_service.py").read_text(
        encoding="utf-8"
    )
    persistence = (
        APP / "infrastructure" / "frappe" / "replacements" / "plan_persistence.py"
    ).read_text(encoding="utf-8")
    command_context = (
        APP / "infrastructure" / "frappe" / "cutting_plan_command_context.py"
    ).read_text(encoding="utf-8")

    for source in (snapshot, service):
        assert "approved_plan_for_order" in source
        assert "order.kerf_mm" not in source
        assert "order.trim_margin_mm" not in source
    for forbidden in (
        "order.board_rate_usd",
        "order.cutting_cost_per_board_usd",
        "ignore_permissions",
    ):
        assert forbidden not in service
    assert "source_plan.board_rate_usd" in service
    assert "source_plan.cutting_cost_per_board_usd" in service
    assert "settings.kerf_mm" in service
    assert "settings.trim_margin_mm" in service
    assert "insert_replacement_plan(plan)" in service
    assert "approve_replacement_plan(plan)" in service

    assert "REPLACEMENT_PLAN_COMMAND_FLAG" in persistence
    assert "plan.insert()" in persistence
    assert "plan.save()" in persistence
    assert "ignore_permissions" not in persistence
    assert "REPLACEMENT_PLAN_COMMAND_FLAG" in command_context
    assert "Capability.APPROVE_REPLACEMENT" not in command_context


def test_direct_persisted_dco_plan_reads_are_fully_retired() -> None:
    # dxf_import_service receives a transient PlanSettings proxy and the
    # application OrderState dataclass is not a Frappe Door Cutting Order.
    allowed: dict[str, set[str]] = {
        "order.cutting_plan_json": set(),
        "order.system_plan_json": set(),
        "order.custom_plan_json": set(),
        "order.approved_plan_source": set(),
        "order.plan_needs_recalculation": {
            "almdina_erp/application/shop_floor/commands.py",
        },
        "order.production_dxf": set(),
        "order.packing_mode": set(),
        "order.cutting_machine_type": set(),
        "order.kerf_mm": {"almdina_erp/services/dxf_import_service.py"},
        "order.trim_margin_mm": {"almdina_erp/services/dxf_import_service.py"},
    }

    for token, expected_paths in allowed.items():
        assert set(_matches(token)) == expected_paths, token


def test_preview_adapter_is_explicitly_transient_and_schema_independent() -> None:
    context = (
        APP / "infrastructure" / "frappe" / "orders" / "preview_plan_context.py"
    ).read_text(encoding="utf-8")
    controller = (
        APP / "doctype" / "door_cutting_order" / "door_cutting_order.py"
    ).read_text(encoding="utf-8")
    preview = (
        APP / "infrastructure" / "frappe" / "orders" / "plan_adapter.py"
    ).read_text(encoding="utf-8")

    assert "seed_plan_settings" in context
    assert "factory_default_plan_settings" in context
    assert "document.flags._transient_plan_preview = True" in context
    assert "apply_preview_plan_settings(self, order_name=self.name)" in controller
    assert "clear_transient_plan_results(self)" in controller
    assert "class FrappeOrderPlanAdapter" in preview
    assert "frappe.db.set_value" not in preview
    assert ".save(" not in preview
    assert ".insert(" not in preview
    assert "ignore_permissions" not in preview


def test_saved_dxf_paths_require_canonical_cutting_plan() -> None:
    export = (APP / "services" / "dxf_export_service.py").read_text(encoding="utf-8")
    compatibility = (APP / "services" / "export_validation_service.py").read_text(
        encoding="utf-8"
    )
    upload = (APP / "services" / "shop_floor_dxf_service.py").read_text(encoding="utf-8")

    # Saved export remains canonical-only, but explicit UI plan selection now
    # resolves the exact System / Uploaded / Approved Cutting Plan instead of
    # silently falling back to a different current plan.
    assert "def _saved_plan_for_source(order: Any, plan_source: str | None)" in export
    assert "_required_saved_plan(order, plan_source)" in export
    assert "current_working_plan" in export
    assert "latest_plan(order.name, source_type=SYSTEM, status=DRAFT)" in export
    assert "latest_plan(order.name, source_type=UPLOADED_DXF, status=DRAFT)" in export
    assert "approved_plan_for_order(order)" in export
    assert "_stored_order_export_snapshot(order)" not in export
    assert 'getattr(order, "kerf_mm"' not in export
    assert "Read-only migration bridge for orders predating canonical Cutting Plan." not in export

    endpoint = compatibility.split("def get_validated_dxf_plan", 1)[1]
    assert "canonical_get_validated_dxf_plan" in endpoint
    assert "dxf_export_service" in endpoint
    assert "_stored_order_export_snapshot" not in compatibility
    assert "dual_plan_fields" not in compatibility

    assert "existing_file = current_uploaded_dxf_file(order.name)" in upload
    assert "order.production_dxf" not in upload
    assert "One-time migration fallback for a legacy pre-A2 custom DXF" not in upload


def test_saved_order_api_has_no_retired_plan_snapshot_fallback() -> None:
    api = (APP / "api.py").read_text(encoding="utf-8")
    assert "approved_snapshot or stored.cutting_plan_json" not in api
    assert "order.cutting_plan_json" not in api
    assert 'cutting_plan_json=approved_snapshot or ""' in api
    assert '"snapshot_json": ""' in api


def test_a64_first_schema_batch_removes_plan_ownership_fields() -> None:
    dco = json.loads(
        (APP / "doctype" / "door_cutting_order" / "door_cutting_order.json").read_text(
            encoding="utf-8"
        )
    )
    fields = {row["fieldname"] for row in dco["fields"]}
    retired = {
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
        "cutting_plan_json",
        "system_plan_json",
        "custom_plan_json",
        "plan_needs_recalculation",
        "calculated_plan_input_hash",
        "calculated_plan_metadata_hash",
        "production_dxf",
        "approved_plan_source",
    }
    assert not fields.intersection(retired)

    assert "approved_plan" in fields
    assert "drawing_dxf_status" in fields


def test_a64_migration_runs_before_model_sync_and_drop_runs_after() -> None:
    patches = (ROOT / "patches.txt").read_text(encoding="utf-8")
    migration = "almdina_erp.patches.v1_0.migrate_legacy_order_plan_projections"
    drop = "almdina_erp.patches.v1_0.drop_legacy_order_plan_columns"
    assert migration in patches.split("[post_model_sync]", 1)[0]
    assert drop in patches.split("[post_model_sync]", 1)[1]

    migration_source = (
        ROOT / "patches" / "v1_0" / "migrate_legacy_order_plan_projections.py"
    ).read_text(encoding="utf-8")
    drop_source = (
        ROOT / "patches" / "v1_0" / "drop_legacy_order_plan_columns.py"
    ).read_text(encoding="utf-8")
    assert "ignore_permissions" not in migration_source
    assert "ignore_permissions" not in drop_source
    assert "if _existing_order_plan(order_name):" in migration_source
    assert "frappe.db.has_column" in drop_source
