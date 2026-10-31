from __future__ import annotations

import json
from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.cnc.workspace import build_operational_workspace
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
)
from almdina_erp.almdina_erp.application.security.supporting_doctype_permissions import (
    supporting_standard_permission_projection,
)
from almdina_erp.almdina_erp.domain.cnc.machine_profile import (
    SAMPLE_MACHINE_PROFILE,
    machine_profile_seed_updates,
    normalize_machine_profile,
)
from almdina_erp.almdina_erp.domain.cnc.operations import (
    CNC_OPERATION_TYPES,
    is_operational_layer,
)
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    GENERATED,
    NEEDS_REGENERATION,
    NOT_GENERATED,
    SYSTEM_PLAN_SOURCE,
    UPLOADED_PLAN_SOURCE,
    ApprovedPlanRef,
    OperationalFileError,
    assess_approved_plan,
    assign_sheet_presets,
    catalog_sheet,
    effective_status,
    settings_fingerprint,
)
from almdina_erp.almdina_erp.domain.cnc.tool_preset import (
    ToolPresetError,
    assert_single_tool_for_file,
    normalize_tool_preset,
    resolve_selected_presets,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.domain.security.factory_settings import decide_settings_update


APP_ROOT = Path(__file__).resolve().parents[1]
SERVICE = (
    APP_ROOT
    / "almdina_erp"
    / "services"
    / "cnc_operational_file_service.py"
)
PANEL = (
    APP_ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cnc"
    / "door_cutting_order_operational_files_ux.js"
)


def _raw(**overrides):
    values = {
        "preset_name": "Finish T9",
        "tool_name": "Finish",
        "tool_number": "T9",
        "tool_diameter_mm": 6,
        "final_depth_mm": 18.5,
        "spindle_speed_rpm": 15000,
        "feed_rate_mm_min": 10200,
        "plunge_rate_mm_min": 1800,
        "pass_depth_mm": 7,
        "enabled": True,
    }
    values.update(overrides)
    return values


def _preset(**overrides):
    return normalize_tool_preset(_raw(**overrides))


def _piece(instance_id, **extra):
    piece = {
        "piece_instance_id": instance_id,
        "sheet_no": 1,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }
    piece.update(extra)
    return piece


def _approved(source, revision=2):
    return ApprovedPlanRef(f"PLAN-{source}", revision, source, "Approved")


def test_operational_layers_follow_the_current_dxf_contract():
    assert [operation.dxf_layer for operation in CNC_OPERATION_TYPES] == [
        "CUT_PATH",
        "Liner",
        "Rear Groove",
        "Handle Recess",
    ]
    assert is_operational_layer("CUT_PATH")
    for layer in ("GEOMETRY", "SHEET_OUTLINE", "TEXT", "OFFCUT", "text", "0"):
        assert not is_operational_layer(layer)


def test_tool_preset_rejects_invalid_measurements():
    with pytest.raises(ToolPresetError) as diameter:
        _preset(tool_diameter_mm=0)
    assert diameter.value.code == "tool_diameter_invalid"

    with pytest.raises(ToolPresetError) as tool_number:
        _preset(tool_number="9")
    assert tool_number.value.code == "tool_number_invalid"

    with pytest.raises(ToolPresetError) as spindle:
        _preset(spindle_speed_rpm=True)
    assert spindle.value.code == "spindle_speed_invalid"

    with pytest.raises(ToolPresetError) as depth:
        _preset(pass_depth_mm=20, final_depth_mm=18.5)
    assert depth.value.code == "pass_depth_exceeds_final_depth"

    valid = _preset()
    assert valid.tool_number == "T9"
    assert valid.tool_diameter_mm == 6
    assert valid.pass_depth_mm == 7


def test_one_operational_file_keeps_one_physical_tool():
    narrow = _preset(preset_name="Narrow", tool_diameter_mm=6)
    wide = _preset(preset_name="Wide", tool_diameter_mm=8)
    other = _preset(preset_name="Other", tool_number="T8", tool_diameter_mm=6)

    with pytest.raises(ToolPresetError) as diameter:
        assert_single_tool_for_file([narrow, wide])
    assert diameter.value.code == "tool_diameter_conflict"

    with pytest.raises(ToolPresetError) as identity:
        assert_single_tool_for_file([narrow, other])
    assert identity.value.code == "tool_identity_conflict"

    known = {
        "Narrow": _raw(preset_name="Narrow"),
        "Disabled": _raw(preset_name="Disabled", enabled=False),
    }
    with pytest.raises(ToolPresetError) as disabled:
        resolve_selected_presets(["Disabled"], known)
    assert disabled.value.code == "preset_disabled"


def test_approved_system_and_uploaded_plans_are_eligible_and_drafts_are_not():
    system = assess_approved_plan(_approved(SYSTEM_PLAN_SOURCE), current=True)
    uploaded = assess_approved_plan(_approved(UPLOADED_PLAN_SOURCE), current=True)
    assert system.source_type == "System"
    assert uploaded.source_type == "Uploaded DXF"

    with pytest.raises(OperationalFileError) as missing:
        assess_approved_plan(None, current=False)
    assert missing.value.code == "no_approved_plan"

    with pytest.raises(OperationalFileError) as draft:
        assess_approved_plan(
            ApprovedPlanRef("PLAN-DRAFT", 1, SYSTEM_PLAN_SOURCE, "Draft"),
            current=True,
        )
    assert draft.value.code == "draft_plan"


def test_path_identity_is_stable_and_keeps_geometry_separate_from_settings():
    liner = {
        "extra_liner": 1,
        "liner_reference_side": "Left",
        "liner_offset_cm": 2,
        "liner_width_cm": 1.5,
        "liner_start_cm": 0,
        "liner_length_cm": 10,
        "extra_back_groove": 1,
    }
    first = _piece("piece-a", **liner)
    second = _piece("piece-b")
    forward = catalog_sheet(1, [first, second])
    reversed_order = catalog_sheet(1, [second, first])
    assert [path.path_key for path in forward.paths] == [
        path.path_key for path in reversed_order.paths
    ]
    assert "liner:piece-a:liner_1" in [path.path_key for path in forward.paths]
    assert "back_groove:piece-a:primary" in [path.path_key for path in forward.paths]
    assert all(path.path_key != str(path.sequence) for path in forward.paths)

    uploaded = _piece(
        "piece-upload",
        extra_liner=1,
        overlays=[
            {"kind": "liner", "layer": "Liner", "geometry": {"holes": [[0, 0], [1, 0]]}},
            {"kind": "note", "layer": "GEOMETRY", "geometry": {"holes": [[2, 2]]}},
        ],
    )
    uploaded_keys = [path.path_key for path in catalog_sheet(1, [uploaded]).paths]
    assert any(key.startswith("liner:piece-upload:overlay:") for key in uploaded_keys)
    assert "liner:piece-upload:liner_1" not in uploaded_keys
    assert not any("GEOMETRY" in key for key in uploaded_keys)


def test_saved_sheet_settings_ignore_a_later_factory_default_change():
    piece = _piece("piece-a")
    plan = _approved(SYSTEM_PLAN_SOURCE)
    saved = {
        "name": "CNC-FILE-00001",
        "cutting_plan": plan.name,
        "plan_revision": plan.revision,
        "sheet_no": 1,
        "operations": [{"operation_key": "cut_path", "tool_preset": "Saved preset"}],
        "paths": [],
        "generation_fingerprint": "",
        "generated_file": "",
    }
    workspace = build_operational_workspace(
        order_name="DCO-1",
        approved_plan=plan,
        plan_is_current=True,
        pieces=[piece],
        saved_files=[saved],
        factory_defaults={"cut_path": "Factory default"},
        known_presets={},
        machine_profile={"production_approved": False, "source_note": "", "fingerprint_payload": {}},
        can_prepare=False,
    )
    assert workspace["eligible"] is True
    assert workspace["sheets"][0]["operations"][0]["tool_preset"] == "Saved preset"
    assert workspace["sheets"][0]["status"] == NOT_GENERATED


def test_status_asks_for_regeneration_without_deleting_the_previous_file():
    known = {"Finish T9": _raw()}
    original = settings_fingerprint(
        operation_presets={"cut_path": "Finish T9"},
        path_overrides={},
        presets=known,
        machine_profile={"tool_number": "T9"},
    )
    changed = settings_fingerprint(
        operation_presets={"cut_path": "Finish T9"},
        path_overrides={},
        presets={"Finish T9": _raw(feed_rate_mm_min=8000)},
        machine_profile={"tool_number": "T9"},
    )
    assert effective_status(
        generation_fingerprint="",
        current_fingerprint=original,
        stored_plan=("PLAN-1", 1),
        current_plan=("PLAN-1", 1),
    ) == NOT_GENERATED
    assert effective_status(
        generation_fingerprint=original,
        current_fingerprint=original,
        stored_plan=("PLAN-1", 1),
        current_plan=("PLAN-1", 1),
    ) == GENERATED
    assert effective_status(
        generation_fingerprint=original,
        current_fingerprint=changed,
        stored_plan=("PLAN-1", 1),
        current_plan=("PLAN-1", 1),
    ) == NEEDS_REGENERATION
    assert effective_status(
        generation_fingerprint=original,
        current_fingerprint=original,
        stored_plan=("PLAN-1", 1),
        current_plan=("PLAN-1", 2),
    ) == NEEDS_REGENERATION


def test_sheet_assignment_rejects_conflicting_tools_and_unknown_paths():
    catalog = catalog_sheet(1, [_piece("piece-a", extra_back_groove=1)])
    known = {
        "Narrow": _raw(preset_name="Narrow"),
        "Other": _raw(preset_name="Other", tool_number="T8"),
    }
    with pytest.raises(OperationalFileError) as conflict:
        assign_sheet_presets(
            catalog=catalog,
            operation_presets={"cut_path": "Narrow", "back_groove": "Other"},
            path_overrides={},
            known_presets=known,
        )
    assert conflict.value.code == "tool_identity_conflict"
    with pytest.raises(OperationalFileError) as unknown:
        assign_sheet_presets(
            catalog=catalog,
            operation_presets={"cut_path": ""},
            path_overrides={"missing-path": "Narrow"},
            known_presets=known,
        )
    assert unknown.value.code == "unknown_path"


def test_machine_profile_sample_is_not_production_approved_and_seed_is_idempotent():
    profile = normalize_machine_profile(SAMPLE_MACHINE_PROFILE)
    assert profile.production_approved is False
    assert profile.tool_number == "T9"
    assert profile.example_depth_a_mm == 7
    assert profile.example_depth_b_mm == 18.5

    updates = machine_profile_seed_updates(
        {"cnc_machine_tool_number": "T4", "cnc_machine_profile_production_approved": 0}
    )
    assert "cnc_machine_tool_number" not in updates
    assert "cnc_machine_profile_production_approved" not in updates
    assert updates["cnc_machine_distance_mode"] == "G90"
    assert machine_profile_seed_updates(SAMPLE_MACHINE_PROFILE) == {}


def test_capabilities_split_view_prepare_and_factory_defaults():
    prepare = normalize_capability_state({Capability.PREPARE_CNC_OPERATIONAL_FILES: True})
    assert prepare[Capability.VIEW_CNC_OPERATIONAL_FILES] is True
    assert prepare[Capability.VIEW_ORDERS] is True
    assert prepare[Capability.VIEW_CUTTING_PLAN] is False

    view_only = normalize_capability_state({Capability.VIEW_CNC_OPERATIONAL_FILES: True})
    assert view_only[Capability.PREPARE_CNC_OPERATIONAL_FILES] is False

    denied = supporting_standard_permission_projection("CNC Operational File", {})
    assert denied == {
        "read": False,
        "select": False,
        "create": False,
        "write": False,
        "delete": False,
    }
    viewer = supporting_standard_permission_projection(
        "CNC Operational File",
        {Capability.VIEW_CNC_OPERATIONAL_FILES: True},
    )
    assert viewer["read"] is True
    assert viewer["write"] is False

    maintainer = supporting_standard_permission_projection(
        "CNC Tool Preset",
        {Capability.EDIT_FACTORY_CNC_DEFAULTS: True},
    )
    assert maintainer["read"] is True
    assert maintainer["write"] is True
    assert maintainer["delete"] is True

    without_factory = decide_settings_update(
        {Capability.EDIT_FACTORY_CUTTING_DEFAULTS},
        {"cnc_default_preset_cut_path": "Finish T9"},
    )
    with_factory = decide_settings_update(
        {Capability.EDIT_FACTORY_CNC_DEFAULTS},
        {"cnc_default_preset_cut_path": "Finish T9"},
    )
    assert without_factory.allowed is False
    assert with_factory.allowed is True


def test_server_boundary_does_not_accept_a_client_plan_or_offer_machine_output():
    service = SERVICE.read_text(encoding="utf-8")
    signature = service.split("def save_cnc_operational_sheet", 1)[1].split(") ->", 1)[0]
    assert "require_document_capability" in service
    assert "Capability.VIEW_CNC_OPERATIONAL_FILES" in service
    assert "Capability.PREPARE_CNC_OPERATIONAL_FILES" in service
    assert "cutting_plan" not in signature
    assert "plan_name" not in signature

    panel = PANEL.read_text(encoding="utf-8")
    assert "get_cnc_operational_workspace" in panel
    assert "save_cnc_operational_sheet" in panel
    assert "Save sheet settings" in panel
    assert ".nc" not in panel
    assert "G01" not in panel
    assert "Download" not in panel

    order = json.loads(
        (APP_ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json").read_text(
            encoding="utf-8"
        )
    )
    field_order = order["field_order"]
    assert field_order.index("operational_files_tab") < field_order.index("cost_tab")
    assert field_order.index("results_tab") < field_order.index("operational_files_tab")
    tab = next(field for field in order["fields"] if field["fieldname"] == "operational_files_tab")
    assert tab["label"] == "Operational Files"
    assert not tab.get("hidden")

    hooks = (APP_ROOT / "hooks.py").read_text(encoding="utf-8")
    assert "cnc_operational_file_has_permission" in hooks
    assert "cnc_tool_preset_has_permission" in hooks

    translations = (APP_ROOT / "translations" / "ar.csv").read_text(encoding="utf-8")
    assert "الملفات التشغيلية" in translations
    assert "لا توجد خطة قص معتمدة لهذا الطلب" in translations
