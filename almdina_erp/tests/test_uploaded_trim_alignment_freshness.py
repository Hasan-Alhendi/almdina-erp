"""Uploaded DXF Draft must stale when manufacturing trim diverges.

Fingerprints for an uploaded revision include that revision's own trim, so a
later System trim edit does not stale the uploaded fingerprint. Alignment is
decided by comparing manufacturing trim to the trim stored on the Uploaded
Draft (the value used at validation).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.tests.frappe_test_stub import install_if_unavailable

install_if_unavailable()

from almdina_erp.almdina_erp.domain.cutting.plan_freshness import (
    decide_uploaded_manufacturing_trim_mismatch,
    manufacturing_trim_matches,
)
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import APPROVED, DRAFT, UPLOADED_DXF
from almdina_erp.almdina_erp.services import (
    cutting_plan_command_service as command_service,
    cutting_plan_invalidation_service as invalidation,
    cutting_plan_workspace_query_service as workspace,
)


def test_trim_mismatch_detects_increase_and_decrease():
    increased = decide_uploaded_manufacturing_trim_mismatch(
        source_type=UPLOADED_DXF,
        status=DRAFT,
        uploaded_trim_mm=0,
        manufacturing_trim_mm=5,
    )
    decreased = decide_uploaded_manufacturing_trim_mismatch(
        source_type=UPLOADED_DXF,
        status=DRAFT,
        uploaded_trim_mm=10,
        manufacturing_trim_mm=0,
    )
    assert increased.should_invalidate
    assert increased.reason == "trim_margin_changed"
    assert decreased.should_invalidate
    assert decreased.reason == "trim_margin_changed"


def test_matching_trim_and_approved_revision_are_not_invalidated_in_place():
    fresh = decide_uploaded_manufacturing_trim_mismatch(
        source_type=UPLOADED_DXF,
        status=DRAFT,
        uploaded_trim_mm=5,
        manufacturing_trim_mm=5.0000001,
    )
    approved = decide_uploaded_manufacturing_trim_mismatch(
        source_type=UPLOADED_DXF,
        status=APPROVED,
        uploaded_trim_mm=0,
        manufacturing_trim_mm=5,
    )
    assert not fresh.should_invalidate
    assert fresh.reason == "fresh"
    assert manufacturing_trim_matches(5, 5.0000001)
    assert not approved.should_invalidate
    assert approved.reason == "immutable_revision"


def test_save_system_settings_syncs_uploaded_draft_staleness_for_trim_change():
    order = SimpleNamespace(name="26-00501")
    plan = SimpleNamespace(
        name="SYSTEM-DRAFT",
        revision=2,
        status=DRAFT,
        source_type="System",
        optimization_mode="smart",
        machine_type="Auto",
        optimization_time_limit_sec=10,
        kerf_mm=5,
        trim_margin_mm=0,
        deduct_edge_thickness=0,
        plan_needs_recalculation=0,
        snapshot_json="{}",
        required_boards=1,
        waste_area_m2=0,
        waste_percent=0,
        method_label="smart",
        packing_score=None,
    )

    class Repository:
        def __init__(self, capability):
            self.capability = capability

        def ensure_system_draft(self, _order):
            return plan

        def get_document(self, _name):
            return plan

        def save_document(self, saved):
            return saved

    with (
        patch.object(command_service, "require_cutting_plan_capability"),
        patch.object(command_service, "FrappeCuttingPlanCommandRepository", Repository),
        patch.object(command_service, "update_settings") as update,
        patch.object(
            command_service,
            "_settings_from_plan",
            return_value=SimpleNamespace(preferred_trim_mm=5),
        ),
        patch.object(
            command_service,
            "sync_uploaded_draft_manufacturing_trim",
            return_value="UPLOADED-DRAFT",
        ) as sync,
        patch.object(command_service, "plan_payload", return_value={"cutting_plan": plan.name}),
    ):
        result = command_service.save_system_plan_settings(
            order,
            {"trim_margin_mm": 5},
        )

    assert update.called
    sync.assert_called_once_with(order)
    assert result["uploaded_plan_trim_invalidated"] is True


def test_save_system_settings_without_trim_change_still_syncs_but_reports_false_when_aligned():
    order = SimpleNamespace(name="26-00502")
    plan = SimpleNamespace(
        name="SYSTEM-DRAFT",
        revision=2,
        status=DRAFT,
        source_type="System",
        optimization_mode="smart",
        machine_type="Auto",
        optimization_time_limit_sec=10,
        kerf_mm=5,
        trim_margin_mm=0,
        deduct_edge_thickness=0,
        plan_needs_recalculation=0,
        snapshot_json="{}",
        required_boards=1,
        waste_area_m2=0,
        waste_percent=0,
        method_label="smart",
    )

    class Repository:
        def __init__(self, capability):
            self.capability = capability

        def ensure_system_draft(self, _order):
            return plan

        def get_document(self, _name):
            return plan

        def save_document(self, saved):
            return saved

    with (
        patch.object(command_service, "require_cutting_plan_capability"),
        patch.object(command_service, "FrappeCuttingPlanCommandRepository", Repository),
        patch.object(command_service, "update_settings") as update,
        patch.object(
            command_service,
            "sync_uploaded_draft_manufacturing_trim",
            return_value=None,
        ) as sync,
        patch.object(command_service, "plan_payload", return_value={"cutting_plan": plan.name}),
    ):
        result = command_service.save_system_plan_settings(order, {"kerf_mm": 5})

    update.assert_not_called()
    sync.assert_called_once_with(order)
    assert result["uploaded_plan_trim_invalidated"] is False


def test_sync_marks_uploaded_draft_when_trim_diverges():
    order = SimpleNamespace(name="26-00503", is_new=lambda: False)
    writes = []

    with (
        patch.object(
            invalidation.frappe,
            "get_all",
            return_value=[{
                "name": "UPLOADED-DRAFT",
                "status": DRAFT,
                "source_type": UPLOADED_DXF,
                "trim_margin_mm": 0,
                "input_fingerprint": "same",
                "plan_needs_recalculation": 0,
            }],
            create=True,
        ),
        patch.object(
            invalidation,
            "manufacturing_plan_settings",
            return_value=SimpleNamespace(preferred_trim_mm=5),
        ),
        patch.object(
            invalidation,
            "_mark_plan_needs_recalculation",
            side_effect=lambda name: writes.append(name),
        ),
    ):
        marked = invalidation.sync_uploaded_draft_manufacturing_trim(order)

    assert marked == "UPLOADED-DRAFT"
    assert writes == ["UPLOADED-DRAFT"]


def test_sync_clears_stale_flag_only_when_trim_rematches_and_fingerprint_is_fresh():
    order = SimpleNamespace(name="26-00504", is_new=lambda: False)
    plan = SimpleNamespace(
        name="UPLOADED-DRAFT",
        source_type=UPLOADED_DXF,
        input_fingerprint="same",
    )
    clears = []

    with (
        patch.object(
            invalidation.frappe,
            "get_all",
            return_value=[{
                "name": "UPLOADED-DRAFT",
                "status": DRAFT,
                "source_type": UPLOADED_DXF,
                "trim_margin_mm": 0,
                "input_fingerprint": "same",
                "plan_needs_recalculation": 1,
            }],
            create=True,
        ),
        patch.object(
            invalidation,
            "manufacturing_plan_settings",
            return_value=SimpleNamespace(preferred_trim_mm=0),
        ),
        patch.object(invalidation.frappe, "get_doc", return_value=plan, create=True),
        patch.object(invalidation, "_expected_fingerprint", return_value="same"),
        patch.object(
            invalidation,
            "_set_plan_needs_recalculation",
            side_effect=lambda name, value: clears.append((name, value)),
        ),
    ):
        marked = invalidation.sync_uploaded_draft_manufacturing_trim(order)

    assert marked is None
    assert clears == [("UPLOADED-DRAFT", 0)]


def test_sync_keeps_stale_flag_when_trim_rematches_but_fingerprint_diverged():
    order = SimpleNamespace(name="26-00505", is_new=lambda: False)
    plan = SimpleNamespace(
        name="UPLOADED-DRAFT",
        source_type=UPLOADED_DXF,
        input_fingerprint="old",
    )

    with (
        patch.object(
            invalidation.frappe,
            "get_all",
            return_value=[{
                "name": "UPLOADED-DRAFT",
                "status": DRAFT,
                "source_type": UPLOADED_DXF,
                "trim_margin_mm": 0,
                "input_fingerprint": "old",
                "plan_needs_recalculation": 1,
            }],
            create=True,
        ),
        patch.object(
            invalidation,
            "manufacturing_plan_settings",
            return_value=SimpleNamespace(preferred_trim_mm=0),
        ),
        patch.object(invalidation.frappe, "get_doc", return_value=plan, create=True),
        patch.object(invalidation, "_expected_fingerprint", return_value="new"),
        patch.object(invalidation, "_set_plan_needs_recalculation") as clear,
    ):
        marked = invalidation.sync_uploaded_draft_manufacturing_trim(order)

    assert marked is None
    clear.assert_not_called()


def test_workspace_read_marks_legacy_uploaded_draft_trim_mismatch_without_rewrite():
    order = SimpleNamespace(name="26-00491", approved_plan=None)
    plan = {
        "name": "UPLOADED-DRAFT",
        "source_type": UPLOADED_DXF,
        "status": DRAFT,
        "revision": 3,
        "trim_margin_mm": 0,
        "plan_needs_recalculation": 0,
        "input_fingerprint": "same",
        "validation_status": "Valid",
        "optimization_mode": "smart",
        "machine_type": "Auto",
        "kerf_mm": 5,
        "deduct_edge_thickness": 0,
    }
    compatibility = SimpleNamespace(
        compatible=True,
        state="COMPATIBLE",
        reason="fresh",
        contract="v4",
    )

    with (
        patch.object(workspace, "plan_fingerprint_compatibility", return_value=compatibility),
        patch.object(
            workspace,
            "manufacturing_plan_settings",
            return_value=SimpleNamespace(preferred_trim_mm=5),
        ),
        patch.object(workspace, "_plan_content_identity", return_value="id"),
        patch.object(
            workspace,
            "_plan_row",
            return_value={
                "name": plan["name"],
                "source_type": UPLOADED_DXF,
                "status": DRAFT,
                "settings": {"trim_margin_mm": 0},
                "validation": {"needs_recalculation": False, "status": "Valid"},
            },
        ),
    ):
        payload = workspace._plan_row_with_freshness(order, plan, "{}")

    assert payload["validation"]["needs_recalculation"] is True
    assert payload["validation"]["freshness_reason"] == "trim_margin_changed"
    assert payload["validation"]["freshness_state"] == "MISMATCH"
    assert payload["settings_alignment"] == {
        "manufacturing_trim_margin_mm": 5.0,
        "validated_trim_margin_mm": 0.0,
        "trim_matches": False,
    }
    assert plan["trim_margin_mm"] == 0


def test_approval_rejects_uploaded_draft_with_mismatched_trim():
    order = SimpleNamespace(name="26-00506")
    plan = SimpleNamespace(
        status=DRAFT,
        source_type=UPLOADED_DXF,
        validation_status="Valid",
        snapshot_json='{"sheets":[{"sheet_no":1}]}',
        plan_needs_recalculation=0,
        cost_snapshot_version=command_service.COST_SNAPSHOT_VERSION,
        input_fingerprint="same",
        trim_margin_mm=0,
        dxf_file="/private/files/ok.dxf",
        dxf_status="Validated",
        saw_center_status="Absent",
    )

    with (
        patch.object(
            command_service,
            "manufacturing_plan_settings",
            return_value=SimpleNamespace(preferred_trim_mm=5),
        ),
        patch.object(command_service, "freshness_expected_fingerprint") as fingerprint,
    ):
        try:
            command_service._assert_plan_ready_for_approval(order, plan)
            raised = None
        except Exception as error:  # noqa: BLE001 - assert message contract
            raised = error

    assert raised is not None
    fingerprint.assert_not_called()
    assert "does not match the current manufacturing trim" in str(raised)


def test_previous_upload_trim_sync_still_applies_manufacturing_settings_on_save():
    order = SimpleNamespace(name="26-00478")
    plan = SimpleNamespace(
        name="UPLOADED-DRAFT",
        optimization_mode="auto_pro",
        machine_type="CNC Router",
        optimization_time_limit_sec=4,
        kerf_mm=3.0,
        trim_margin_mm=3.0,
        deduct_edge_thickness=1,
        placed_pieces=[],
        plan_needs_recalculation=1,
    )
    manufacturing = SimpleNamespace(
        optimization_mode="smart",
        machine_type="Auto",
        optimization_time_limit_sec=10,
        kerf_mm=5.0,
        preferred_trim_mm=0.0,
        deduct_edge_thickness=False,
    )

    class Repository:
        def __init__(self, capability):
            self.capability = capability

        def ensure_uploaded_dxf_draft(self, _order):
            return plan

        def save_document(self, saved):
            return saved

    with (
        patch.object(command_service, "require_cutting_plan_capability"),
        patch.object(command_service, "backfill_piece_instance_ids"),
        patch.object(command_service, "FrappeCuttingPlanCommandRepository", Repository),
        patch.object(command_service, "manufacturing_plan_settings", return_value=manufacturing),
        patch.object(command_service, "initialize_draft_plan_cost_snapshot", return_value=False),
        patch.object(command_service, "apply_validated_dxf_snapshot"),
        patch.object(command_service, "apply_plan_costs"),
        patch.object(command_service, "factory_execution_edge_cost", return_value=0),
        patch.object(command_service, "now_datetime", return_value="2026-03-26 10:00:00"),
        patch.object(command_service.frappe, "session", SimpleNamespace(user="designer@example.com")),
    ):
        command_service.save_uploaded_dxf_plan(
            order,
            {"sheets": []},
            "/private/files/new.dxf",
            capability=command_service.Capability.UPLOAD_DXF,
        )

    assert plan.trim_margin_mm == 0.0
    assert plan.kerf_mm == 5.0
