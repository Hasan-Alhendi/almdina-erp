"""DXF upload must validate using the same settings that the Draft will persist.

Regression: orders 26-00491 and 26-00478 had a System Draft with trim=0,
but their latest Cancelled Uploaded DXF had trim=3. The imported geometry
passed at zero and failed mandatory trim during saving the newly seeded Draft.
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
from almdina_erp.almdina_erp.services import shop_floor_dxf_service as upload


def _settings(*, trim: float):
    return SimpleNamespace(
        optimization_mode="smart", machine_type="Auto",
        optimization_time_limit_sec=10, kerf_mm=5.0,
        trim_margin_mm=trim, deduct_edge_thickness=False,
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


def test_existing_uploaded_draft_is_reused_without_replacing_its_settings():
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


def test_new_upload_uses_system_draft_for_import_and_tool_diameters():
    system = _settings(trim=0)
    with (
        patch.object(upload, "latest_plan", return_value=None),
        patch.object(upload, "manufacturing_plan_settings", return_value=system) as imported,
        patch.object(upload, "manufacturing_plan_document", return_value=system) as diameter_doc,
        patch.object(upload, "plan_settings") as stale_settings,
    ):
        settings, source_doc = upload._uploaded_dxf_import_context("26-00478")
    imported.assert_called_once_with("26-00478")
    diameter_doc.assert_called_once_with("26-00478")
    stale_settings.assert_not_called()
    assert settings is system
    assert source_doc is system


def test_existing_uploaded_draft_owns_both_import_settings_and_tool_diameters():
    uploaded = _settings(trim=3)
    with (
        patch.object(upload, "latest_plan", return_value=uploaded) as lookup,
        patch.object(upload, "plan_settings", return_value=uploaded) as settings_reader,
        patch.object(upload, "manufacturing_plan_settings") as system_settings,
        patch.object(upload, "manufacturing_plan_document") as system_document,
    ):
        settings, tool_document = upload._uploaded_dxf_import_context("26-00491")
    assert settings is uploaded
    assert tool_document is uploaded
    lookup.assert_called_once_with("26-00491", source_type="Uploaded DXF", status="Draft")
    settings_reader.assert_called_once_with(uploaded)
    system_settings.assert_not_called()
    system_document.assert_not_called()
