from __future__ import annotations

import json
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
    CuttingPlanLifecycleError,
    revision_from_approved,
)


ROOT = Path(__file__).resolve().parents[1]


def _doctype_json(name: str) -> dict:
    slug = name.lower().replace(" ", "_")
    path = ROOT / "almdina_erp" / "doctype" / slug / f"{slug}.json"
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
        self.plan = PlanRecord(
            name=self.plan.name,
            order_name=self.plan.order_name,
            revision=self.plan.revision,
            status=self.plan.status,
            source_type=self.plan.source_type,
            based_on_plan=self.plan.based_on_plan,
            settings=settings,
        )
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

    repository.plan = PlanRecord(
        **{**draft.__dict__, "status": APPROVED}
    )
    with pytest.raises(CuttingPlanLifecycleError):
        update_settings(UpdatePlanSettingsCommand("CP-0002", _settings()), repository)


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
        assert not fields[fieldname].get("read_only"), fieldname
    assert fields["plan_needs_recalculation"]["read_only"] == 1
    assert fields["dxf_file"]["fieldtype"] == "Attach"


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
