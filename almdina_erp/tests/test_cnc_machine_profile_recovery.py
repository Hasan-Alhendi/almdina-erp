"""Invalid machine-profile settings must not crash the operational workspace."""

from __future__ import annotations

from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.cnc.workspace import build_operational_workspace
from almdina_erp.almdina_erp.domain.cnc.machine_profile import (
    SAMPLE_MACHINE_PROFILE,
    MachineProfileError,
    machine_profile_for_workspace,
    machine_profile_seed_updates,
    normalize_machine_profile,
)
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    SYSTEM_PLAN_SOURCE,
    ApprovedPlanRef,
)
from almdina_erp.almdina_erp.domain.cnc.tool_preset import ToolPresetError, normalize_tool_preset


APP_ROOT = Path(__file__).resolve().parents[1]
PATCH = APP_ROOT / "patches" / "v1_0" / "repair_missing_cnc_machine_profile_fields.py"
PATCHES = APP_ROOT / "patches.txt"
REPOSITORY = (
    APP_ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "cnc_operational_file_repository.py"
)
TOOL_PRESET = APP_ROOT / "almdina_erp" / "domain" / "cnc" / "tool_preset.py"


def _piece():
    return {
        "piece_instance_id": "piece-a",
        "sheet_no": 1,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
    }


def test_valid_tool_number_normalizes_and_stays_unapproved_in_the_sample():
    profile = normalize_machine_profile(SAMPLE_MACHINE_PROFILE)
    assert profile.tool_number == "T9"
    assert profile.production_approved is False
    model = machine_profile_for_workspace(SAMPLE_MACHINE_PROFILE)
    assert model["production_approved"] is False
    assert model["fingerprint_payload"]["tool_number"] == "T9"


def test_blank_or_missing_tool_number_is_a_machine_profile_error():
    cases = (
        {**SAMPLE_MACHINE_PROFILE, "cnc_machine_tool_number": ""},
        {**SAMPLE_MACHINE_PROFILE, "cnc_machine_tool_number": "   "},
        {**SAMPLE_MACHINE_PROFILE, "cnc_machine_tool_number": None},
        {key: value for key, value in SAMPLE_MACHINE_PROFILE.items() if key != "cnc_machine_tool_number"},
    )
    for raw in cases:
        with pytest.raises(MachineProfileError) as caught:
            normalize_machine_profile(raw)
        assert caught.value.code == "machine_profile_tool_number_invalid"
        assert not isinstance(caught.value, ToolPresetError)
        assert isinstance(caught.value.__cause__, ToolPresetError)
        assert caught.value.__cause__.code == "tool_number_invalid"


def test_malformed_tool_number_is_a_machine_profile_error():
    for tool_number in ("9", "T0", "T", "TOOL"):
        with pytest.raises(MachineProfileError) as caught:
            normalize_machine_profile(
                {**SAMPLE_MACHINE_PROFILE, "cnc_machine_tool_number": tool_number}
            )
        assert caught.value.code == "machine_profile_tool_number_invalid"
        assert isinstance(caught.value.__cause__, ToolPresetError)


def test_tool_preset_error_does_not_escape_normalize_machine_profile(monkeypatch):
    def unexpected(_raw):
        raise ToolPresetError("tool_diameter_invalid")

    monkeypatch.setattr(
        "almdina_erp.almdina_erp.domain.cnc.tool_preset.normalize_tool_preset",
        unexpected,
    )
    with pytest.raises(MachineProfileError) as caught:
        normalize_machine_profile(SAMPLE_MACHINE_PROFILE)
    assert caught.value.code == "machine_profile_value_invalid"
    assert isinstance(caught.value.__cause__, ToolPresetError)
    assert not isinstance(caught.value, ToolPresetError)


def test_programming_errors_are_not_hidden_as_machine_profile_errors():
    with pytest.raises(AttributeError):
        normalize_machine_profile(None)  # type: ignore[arg-type]


def test_invalid_profile_loads_an_unapproved_workspace_without_a_fingerprint():
    model = machine_profile_for_workspace(
        {**SAMPLE_MACHINE_PROFILE, "cnc_machine_tool_number": ""}
    )
    assert model == {
        "production_approved": False,
        "source_note": SAMPLE_MACHINE_PROFILE["cnc_machine_profile_source"],
        "fingerprint_payload": {},
    }
    workspace = build_operational_workspace(
        order_name="26-00132",
        approved_plan=ApprovedPlanRef("PLAN-1", 1, SYSTEM_PLAN_SOURCE, "Approved"),
        plan_is_current=True,
        pieces=[_piece()],
        saved_files=[],
        factory_defaults={},
        known_presets={},
        machine_profile=model,
        can_prepare=False,
    )
    assert workspace["eligible"] is True
    assert workspace["order_name"] == "26-00132"
    assert workspace["machine_profile_production_approved"] is False


def test_repair_values_fill_only_absent_or_blank_fields():
    updates = machine_profile_seed_updates({})
    assert updates == SAMPLE_MACHINE_PROFILE
    assert updates["cnc_machine_tool_number"] == "T9"
    assert updates["cnc_machine_profile_production_approved"] == 0

    blank = machine_profile_seed_updates(
        {"cnc_machine_tool_number": "  ", "cnc_machine_distance_mode": ""}
    )
    assert blank["cnc_machine_tool_number"] == "T9"
    assert blank["cnc_machine_distance_mode"] == "G90"


def test_repair_values_keep_user_entered_settings_and_approval():
    stored = {
        "cnc_machine_tool_number": "T4",
        "cnc_machine_cutting_feed_mm_min": "4000",
        "cnc_machine_profile_production_approved": "1",
    }
    updates = machine_profile_seed_updates(stored)
    assert "cnc_machine_tool_number" not in updates
    assert "cnc_machine_cutting_feed_mm_min" not in updates
    assert "cnc_machine_profile_production_approved" not in updates
    assert updates["cnc_machine_spindle_speed_rpm"] == SAMPLE_MACHINE_PROFILE[
        "cnc_machine_spindle_speed_rpm"
    ]

    unapproved = machine_profile_seed_updates(
        {"cnc_machine_profile_production_approved": "0"}
    )
    assert "cnc_machine_profile_production_approved" not in unapproved
    assert machine_profile_seed_updates(SAMPLE_MACHINE_PROFILE) == {}


def test_cast_zero_is_not_a_blank_value_for_the_seed_rule():
    updates = machine_profile_seed_updates({"cnc_machine_spindle_speed_rpm": 0})
    assert "cnc_machine_spindle_speed_rpm" not in updates


def test_reader_does_not_hide_unexpected_errors_or_hardcode_a_tool_number():
    body = REPOSITORY.read_text(encoding="utf-8").split("def machine_profile_view", 1)[1]
    body = body.split("\ndef ", 1)[0]
    assert "except Exception" not in body
    assert "T9" not in body
    assert "machine_profile_for_workspace" in body
    preset = TOOL_PRESET.read_text(encoding="utf-8")
    assert 'required_code="tool_number_invalid"' in preset
    assert (
        normalize_tool_preset(
            {
                "tool_number": "T9",
                "preset_name": "A",
                "tool_name": "A",
                "tool_diameter_mm": 1,
                "final_depth_mm": 1,
                "spindle_speed_rpm": 1,
                "feed_rate_mm_min": 1,
                "plunge_rate_mm_min": 1,
            }
        ).tool_number
        == "T9"
    )


def test_repair_patch_is_registered_once_at_the_end_and_uses_the_sample_rule():
    lines = [line.strip() for line in PATCHES.read_text(encoding="utf-8").splitlines() if line.strip()]
    patch_name = "almdina_erp.patches.v1_0.repair_missing_cnc_machine_profile_fields"
    assert lines[-1] == patch_name
    assert lines.count(patch_name) == 1
    source = PATCH.read_text(encoding="utf-8")
    assert "SAMPLE_MACHINE_PROFILE" in source
    assert "machine_profile_seed_updates" in source
    assert "get_single_value(" not in source
    assert ".save(" not in source
    assert "T9" not in source
