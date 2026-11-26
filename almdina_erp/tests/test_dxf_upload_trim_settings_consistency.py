"""DXF upload must validate and persist using System manufacturing settings.

Regression: orders 26-00491 and 26-00478 had a System Draft with trim=0,
but an existing Uploaded DXF Draft (or cancelled lineage) still held trim=3.
Import validated against the stale Uploaded Draft, then saving/approve saw a
mismatched mandatory trim.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.infrastructure.frappe import (
    cutting_plan_command_repository as command_repo,
    cutting_plan_runtime_repository as runtime_repo,
)
from almdina_erp.almdina_erp.services import (
    cutting_plan_command_service as command_service,
    shop_floor_dxf_service as upload,
)


def _settings(*, trim: float, kerf: float = 5.0, deduct: bool = False):
    return SimpleNamespace(
        optimization_mode="smart",
        machine_type="Auto",
        optimization_time_limit_sec=10,
        kerf_mm=kerf,
        preferred_trim_mm=trim,
        trim_margin_mm=trim,
        deduct_edge_thickness=deduct,
    )


def test_cancelled_uploaded_revision_does_not_override_current_system_trim():
    system = _settings(trim=0)
    cancelled = _settings(trim=3)

    def find_plan(_order, **filters):
        if filters.get("source_type") == "System" and filters.get("status") == "Draft":
            return system
        return cancelled

    with patch.object(runtime_repo, "latest_plan", side_effect=find_plan):
        settings = runtime_repo.manufacturing_plan_settings("26-00491")
    assert settings.preferred_trim_mm == 0
    assert settings.kerf_mm == 5


def test_new_uploaded_draft_inherits_the_active_import_settings_not_cancelled_lineage():
    active = _settings(trim=0)
    repository = command_repo.FrappeCuttingPlanCommandRepository("upload_dxf")
    result = SimpleNamespace(name="UPLOADED-NEW")
    with (
        patch.object(repository, "_latest_plan_row", side_effect=[
            None, {"name": "CANCELLED-UPLOADED", "revision": 2}, None,
        ]),
        patch.object(command_repo, "manufacturing_plan_settings", return_value=active) as current,
        patch.object(command_repo, "seed_plan_settings") as old_seed,
        patch.object(repository, "create_draft", return_value=result) as create,
        patch.object(repository, "get_document", return_value=result),
    ):
        repository.ensure_uploaded_dxf_draft(SimpleNamespace(name="26-00491"))
    current.assert_called_once_with("26-00491")
    old_seed.assert_not_called()
    assert create.call_args.kwargs["settings"] is active
    assert create.call_args.kwargs["source_type"] == "Uploaded DXF"


def test_existing_uploaded_draft_is_reused_without_eager_settings_mutation():
    """ensure_* may reuse the Draft; settings sync belongs on successful save."""
    repository = command_repo.FrappeCuttingPlanCommandRepository("upload_dxf")
    existing = _settings(trim=3)
    existing.name = "UPLOADED-DRAFT"
    with (
        patch.object(repository, "_latest_plan_row", return_value={"name": existing.name}),
        patch.object(repository, "get_document", return_value=existing),
        patch.object(repository, "create_draft") as create,
        patch.object(command_repo, "manufacturing_plan_settings") as other,
    ):
        returned = repository.ensure_uploaded_dxf_draft(SimpleNamespace(name="26-00478"))
    assert returned is existing
    create.assert_not_called()
    other.assert_not_called()


def test_upload_import_always_uses_manufacturing_settings_even_with_uploaded_draft():
    system = _settings(trim=0)
    system_doc = SimpleNamespace(name="SYSTEM-DRAFT", kerf_mm=5)
    with (
        patch.object(upload, "manufacturing_plan_settings", return_value=system) as imported,
        patch.object(upload, "manufacturing_plan_document", return_value=system_doc) as diameter_doc,
    ):
        settings, source_doc = upload._uploaded_dxf_import_context("26-00478")
    imported.assert_called_once_with("26-00478")
    diameter_doc.assert_called_once_with("26-00478")
    assert settings is system
    assert source_doc is system_doc
    assert settings.preferred_trim_mm == 0


def test_successful_uploaded_save_overwrites_stale_draft_trim_from_manufacturing():
    order = SimpleNamespace(name="26-00491")
    plan = SimpleNamespace(
        name="UPLOADED-DRAFT",
        optimization_mode="auto_pro",
        machine_type="CNC Router",
        optimization_time_limit_sec=4,
        kerf_mm=3.0,
        trim_margin_mm=3.0,
        deduct_edge_thickness=1,
        placed_pieces=[],
        plan_needs_recalculation=0,
    )
    manufacturing = _settings(trim=0, kerf=5.0, deduct=False)
    saved = []

    class Repository:
        def __init__(self, capability: str):
            self.capability = capability

        def ensure_uploaded_dxf_draft(self, _order):
            return plan

        def save_document(self, saved_plan):
            saved.append(saved_plan)
            return saved_plan

    with (
        patch.object(command_service, "require_cutting_plan_capability"),
        patch.object(command_service, "backfill_piece_instance_ids"),
        patch.object(
            command_service,
            "FrappeCuttingPlanCommandRepository",
            Repository,
        ),
        patch.object(
            command_service,
            "manufacturing_plan_settings",
            return_value=manufacturing,
        ),
        patch.object(command_service, "initialize_draft_plan_cost_snapshot", return_value=False),
        patch.object(command_service, "apply_validated_dxf_snapshot"),
        patch.object(command_service, "apply_plan_costs"),
        patch.object(command_service, "factory_execution_edge_cost", return_value=0),
        patch.object(command_service, "now_datetime", return_value="2026-03-26 10:00:00"),
        patch.object(command_service.frappe, "session", SimpleNamespace(user="designer@example.com")),
    ):
        returned = command_service.save_uploaded_dxf_plan(
            order,
            {"sheets": []},
            "/private/files/replacement.dxf",
            capability=command_service.Capability.UPLOAD_DXF,
        )

    assert returned is plan
    assert len(saved) == 1
    assert plan.trim_margin_mm == 0
    assert plan.kerf_mm == 5.0
    assert plan.optimization_mode == "smart"
    assert plan.machine_type == "Auto"
    assert plan.optimization_time_limit_sec == 10
    assert plan.deduct_edge_thickness == 0
    assert plan.plan_needs_recalculation == 0
