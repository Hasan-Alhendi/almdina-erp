from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.cutting.plan_revisions import (
    CreatePlanRevisionCommand,
    PlanRecord,
    PlanSettings,
    UpdatePlanSettingsCommand,
    create_revision,
    update_settings,
)
from almdina_erp.almdina_erp.domain.costing.lifecycle import (
    APPROVED as COST_APPROVED,
    PRELIMINARY,
    SUPERSEDED as COST_SUPERSEDED,
    costing_status_for_plan,
    replacement_status,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    DRAFT,
    SYSTEM,
    UPLOADED_DXF,
    CuttingPlanLifecycleError,
    revision_from_approved,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_command_context import (
    PLAN_COMMAND_FLAG,
    is_authorized_plan_command,
)


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "almdina_erp"


def _doctype_json(name: str) -> dict:
    slug = name.lower().replace(" ", "_")
    path = APP_ROOT / "doctype" / slug / f"{slug}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _field_map(schema: dict) -> dict[str, dict]:
    return {field["fieldname"]: field for field in schema["fields"]}


class MemoryPlanRepository:
    def __init__(self, plan: PlanRecord):
        self.plan = plan
        self.created: PlanRecord | None = None

    def get(self, plan_name: str) -> PlanRecord:
        assert plan_name == self.plan.name
        return self.plan

    def create_draft(self, **values) -> PlanRecord:
        self.created = PlanRecord(name="CP-DRAFT", **values)
        return self.created

    def save_settings(self, plan_name: str, settings: PlanSettings) -> PlanRecord:
        assert plan_name == self.plan.name
        self.plan = replace(self.plan, settings=settings)
        return self.plan


def _settings() -> PlanSettings:
    return PlanSettings(
        optimization_mode="Auto Pro",
        machine_type="Auto",
        optimization_time_limit_sec=10,
        kerf_mm=3,
        trim_margin_mm=5,
    )


def test_approved_plan_revision_becomes_new_draft() -> None:
    revision = revision_from_approved(
        current_name="CP-0001",
        current_revision=3,
        current_status=APPROVED,
        source_type=SYSTEM,
    )
    assert revision.revision == 4
    assert revision.status == DRAFT
    assert revision.based_on_plan == "CP-0001"


def test_non_approved_plan_cannot_be_revision_source() -> None:
    with pytest.raises(CuttingPlanLifecycleError):
        revision_from_approved(
            current_name="CP-0001",
            current_revision=3,
            current_status=DRAFT,
            source_type=SYSTEM,
        )


def test_plan_revision_use_case_copies_settings_without_mutating_approved_plan() -> None:
    approved = PlanRecord(
        name="CP-0001",
        order_name="DCO-0001",
        revision=1,
        status=APPROVED,
        source_type=SYSTEM,
        based_on_plan=None,
        settings=_settings(),
    )
    repository = MemoryPlanRepository(approved)
    created = create_revision(CreatePlanRevisionCommand("CP-0001"), repository)
    assert created.status == DRAFT
    assert created.revision == 2
    assert created.settings == approved.settings
    assert repository.plan == approved


def test_new_revision_can_switch_from_uploaded_dxf_to_system_source() -> None:
    approved = PlanRecord(
        name="CP-DXF-0001",
        order_name="DCO-0001",
        revision=4,
        status=APPROVED,
        source_type=UPLOADED_DXF,
        based_on_plan="CP-0003",
        settings=_settings(),
    )
    repository = MemoryPlanRepository(approved)
    created = create_revision(
        CreatePlanRevisionCommand("CP-DXF-0001", source_type=SYSTEM),
        repository,
    )
    assert created.status == DRAFT
    assert created.revision == 5
    assert created.source_type == SYSTEM
    assert created.based_on_plan == "CP-DXF-0001"
    assert repository.plan == approved


def test_only_draft_plan_settings_are_mutable() -> None:
    draft = PlanRecord(
        name="CP-0002",
        order_name="DCO-0001",
        revision=2,
        status=DRAFT,
        source_type=SYSTEM,
        based_on_plan="CP-0001",
        settings=_settings(),
    )
    repository = MemoryPlanRepository(draft)
    updated = update_settings(
        UpdatePlanSettingsCommand(
            "CP-0002",
            PlanSettings("MaxRects Width", "Panel Saw", 8, 4, 2),
        ),
        repository,
    )
    assert updated.settings.kerf_mm == 4
    assert updated.settings.trim_margin_mm == 2

    repository.plan = replace(draft, status=APPROVED)
    with pytest.raises(CuttingPlanLifecycleError):
        update_settings(UpdatePlanSettingsCommand("CP-0002", _settings()), repository)


def test_scoped_plan_command_flag_is_ephemeral_authorization_boundary() -> None:
    class Flags(dict):
        pass

    class Doc:
        flags = Flags()

    doc = Doc()
    assert not is_authorized_plan_command(doc)
    doc.flags[PLAN_COMMAND_FLAG] = "recalculate_plan"
    assert is_authorized_plan_command(doc)
    doc.flags[PLAN_COMMAND_FLAG] = "edit_order"
    assert not is_authorized_plan_command(doc)


def test_costing_lifecycle_tracks_preliminary_and_approved_prices() -> None:
    assert costing_status_for_plan(plan_status=DRAFT) == PRELIMINARY
    assert costing_status_for_plan(plan_status=APPROVED) == COST_APPROVED
    assert replacement_status(PRELIMINARY) == COST_SUPERSEDED
    assert replacement_status(COST_APPROVED) == COST_SUPERSEDED


def test_cutting_plan_schema_owns_working_optimizer_settings() -> None:
    fields = _field_map(_doctype_json("Cutting Plan"))
    assert fields["source_type"]["options"] == "System\nUploaded DXF"
    assert fields["based_on_plan"]["options"] == "Cutting Plan"
    for fieldname in (
        "optimization_mode",
        "machine_type",
        "optimization_time_limit_sec",
        "kerf_mm",
        "trim_margin_mm",
    ):
        # A5 detached workspace editors own user intent; the native DocType form
        # is deliberately read-only so Plan settings cannot bypass scoped commands.
        assert fields[fieldname].get("read_only") == 1, fieldname
    assert fields["plan_needs_recalculation"]["read_only"] == 1
    assert fields["dxf_file"]["fieldtype"] == "Attach"

    command_source = (
        APP_ROOT / "services" / "cutting_plan_command_service.py"
    ).read_text(encoding="utf-8")
    repository_source = (
        APP_ROOT / "infrastructure" / "frappe" / "cutting_plan_command_repository.py"
    ).read_text(encoding="utf-8")
    assert "save_system_plan_settings" in command_source
    assert "EDIT_OPTIMIZER_SETTINGS" in command_source
    assert "save_settings" in repository_source


def test_costing_schema_is_separate_from_order_and_plan_geometry() -> None:
    fields = _field_map(_doctype_json("Door Cutting Costing"))
    assert fields["door_cutting_order"]["options"] == "Door Cutting Order"
    assert fields["cutting_plan"]["options"] == "Cutting Plan"
    assert fields["lines"]["options"] == "Door Cutting Costing Line"
    assert fields["customer_quote_total_usd"]["read_only"] == 1
    assert fields["actual_cost_usd"]["read_only"] == 1

    line_fields = _field_map(_doctype_json("Door Cutting Costing Line"))
    assert line_fields["piece_uid"]["reqd"] == 1
    assert line_fields["edge_cost_usd"]["read_only"] == 1


def test_a2_plan_command_path_does_not_bypass_permissions_or_save_the_order() -> None:
    repository_source = (
        APP_ROOT / "infrastructure" / "frappe" / "cutting_plan_command_repository.py"
    ).read_text(encoding="utf-8")
    command_source = (
        APP_ROOT / "services" / "cutting_plan_command_service.py"
    ).read_text(encoding="utf-8")
    legacy_recalculation = (
        APP_ROOT / "services" / "order_plan_permission_service.py"
    ).read_text(encoding="utf-8")
    native_permissions = (
        APP_ROOT / "infrastructure" / "frappe" / "native_document_permissions.py"
    ).read_text(encoding="utf-8")
    settings_service = (
        APP_ROOT / "services" / "plan_settings_edit_service.py"
    ).read_text(encoding="utf-8")

    assert "ignore_permissions" not in repository_source
    assert "ignore_permissions" not in command_source
    assert "order.save(" not in command_source
    assert "calculate_system_plan(order, plan)" in command_source
    assert "FrappeCuttingPlanCommandRepository" in command_source
    assert "is_authorized_plan_command" in native_permissions
    assert 'resolved_type in {"create", "write"}' in native_permissions
    assert "save_system_plan_settings" in settings_service
    assert 'frappe.db.set_value(\n        "Door Cutting Order"' not in settings_service

    # The method path used by the existing browser UI is now a compatibility
    # facade only; it must never reintroduce a broad Door Cutting Order save.
    assert "cutting_plan_command_service import" in legacy_recalculation
    assert "recalculate_order_plan(" in legacy_recalculation
    assert "ignore_permissions=True" not in legacy_recalculation
    assert "doc.save(" not in legacy_recalculation
