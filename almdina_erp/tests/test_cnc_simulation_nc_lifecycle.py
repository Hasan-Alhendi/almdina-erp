"""Simulation NC lifecycle: status, snapshot, persistence contracts."""

from __future__ import annotations

import ast
from pathlib import Path

from almdina_erp.almdina_erp.application.cnc.simulation_nc import (
    build_generation_snapshot,
    nc_content_sha256,
    simulation_nc_filename,
)
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    GENERATED,
    NEEDS_REGENERATION,
    NOT_GENERATED,
    effective_status,
    generation_snapshot_is_complete,
)


APP_ROOT = Path(__file__).resolve().parents[1]
SERVICE = APP_ROOT / "almdina_erp" / "services" / "cnc_operational_file_service.py"
REPO = APP_ROOT / "almdina_erp" / "infrastructure" / "frappe" / "cnc_operational_file_repository.py"
UX = APP_ROOT / "public" / "js" / "door_cutting_order" / "cnc" / "door_cutting_order_operational_files_ux.js"


def _preset(**overrides):
    values = {
        "preset_name": "Finish",
        "tool_name": "Finish",
        "tool_number": "T9",
        "tool_diameter_mm": 5,
        "final_depth_mm": 18.5,
        "spindle_speed_rpm": 15000,
        "feed_rate_mm_min": 10200,
        "plunge_rate_mm_min": 1800,
        "pass_depth_mm": None,
        "enabled": True,
    }
    values.update(overrides)
    return values


def test_effective_status_requires_real_file_and_complete_snapshot():
    fingerprint = "abc"
    assert (
        effective_status(
            generation_fingerprint=fingerprint,
            current_fingerprint=fingerprint,
            stored_plan=("PLAN", 1),
            current_plan=("PLAN", 1),
        )
        == NOT_GENERATED
    )
    assert (
        effective_status(
            generation_fingerprint=fingerprint,
            current_fingerprint=fingerprint,
            stored_plan=("PLAN", 1),
            current_plan=("PLAN", 1),
            generated_file="/private/files/x.sim.nc",
            file_present=True,
            snapshot_complete=False,
        )
        == NOT_GENERATED
    )
    assert (
        effective_status(
            generation_fingerprint=fingerprint,
            current_fingerprint=fingerprint,
            stored_plan=("PLAN", 1),
            current_plan=("PLAN", 1),
            generated_file="/private/files/x.sim.nc",
            file_present=True,
            snapshot_complete=True,
        )
        == GENERATED
    )
    assert (
        effective_status(
            generation_fingerprint=fingerprint,
            current_fingerprint="other",
            stored_plan=("PLAN", 1),
            current_plan=("PLAN", 1),
            generated_file="/private/files/x.sim.nc",
            file_present=True,
            snapshot_complete=True,
        )
        == NEEDS_REGENERATION
    )


def test_generation_snapshot_freezes_settings_and_content_hash():
    text = "G90\nG54\nM30\n"
    package = {
        "text": text,
        "post_processor_version": "almadina_simulation_v1",
        "dialect": "simulation",
        "tool_number": "T9",
        "path_count": 1,
        "pass_count": 1,
        "verification": {"ok": True, "issues": []},
        "content_sha256": nc_content_sha256(text),
    }
    snapshot = build_generation_snapshot(
        order_name="DCO-1",
        cutting_plan="PLAN-1",
        plan_revision=3,
        plan_source_type="System",
        sheet_no=2,
        settings_fingerprint="fp-1",
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["cut_path"],
        cut_path_early_confirmed=False,
        known_presets={"Finish": _preset()},
        machine_profile={"tool_number": "T9", "production_approved": False},
        package=package,
        program={"geometry_ready": True},
        previous_generated_file="/private/files/old.sim.nc",
        generated_by="operator@example.com",
        generated_on="2026-01-01 00:00:00",
    )
    assert generation_snapshot_is_complete(snapshot)
    assert snapshot["file_kind"] == "simulation"
    assert snapshot["production"] is False
    assert snapshot["content_sha256"] == nc_content_sha256(text)
    assert snapshot["layer_presets"]["cut_path"]["values"]["tool_number"] == "T9"
    assert snapshot["previous_generated_file"].endswith("old.sim.nc")
    assert simulation_nc_filename(
        order_name="DCO-1",
        cutting_plan="PLAN-1",
        plan_revision=3,
        sheet_no=2,
        content_sha256=snapshot["content_sha256"],
    ).endswith(".sim.nc")


def test_generate_path_persists_private_file_before_generated_status():
    service = SERVICE.read_text(encoding="utf-8")
    repo = REPO.read_text(encoding="utf-8")
    assert "attach_simulation_nc" in service
    assert "record_nc_generation" in service
    assert "download_cnc_sheet_nc" in service
    assert "Capability.VIEW_CNC_OPERATIONAL_FILES" in service
    assert "save_sheet(" in service.split("def generate_cnc_sheet_nc", 1)[1]
    assert 'is_private=1' in repo
    assert "Generated status requires a stored simulation NC file." in repo
    assert "discard_orphan_file" in repo
    # Must not mark Generated when file_url is optional/empty.
    assert "if file_url:" not in repo.split("def record_nc_generation", 1)[1].split("def ", 1)[0]


def test_generate_path_imports_the_saved_direction_guard_it_calls():
    source = SERVICE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "almdina_erp.almdina_erp.domain.cnc.artcam_machining"
        for alias in node.names
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "reversed_direction_block" in called
    assert "reversed_direction_block" in imported


def test_ui_uses_server_download_not_ephemeral_blob_only():
    panel = UX.read_text(encoding="utf-8")
    assert "download_cnc_sheet_nc" in panel
    assert "data-cnc-card-download" in panel
    assert "Generate simulation NC" in panel
    assert "Download previous simulation NC" in panel
    assert "URL.createObjectURL" not in panel
    assert "geometry problems block simulation NC generation" in panel

def test_workspace_marks_generated_only_with_file_and_needs_regen_after_settings_change():
    from almdina_erp.almdina_erp.application.cnc.workspace import build_operational_workspace
    from almdina_erp.almdina_erp.domain.cnc.operational_file import (
        ApprovedPlanRef,
        settings_fingerprint,
    )

    plan = ApprovedPlanRef(name="PLAN-1", revision=1, source_type="System", status="Approved")
    piece = {
        "piece_instance_id": "p1",
        "label": "1.1",
        "sheet_no": 1,
        "extra_liner": 0,
        "extra_back_groove": 0,
        "extra_recessed_handle_cutout": 0,
        "geometry": {
            "schema_version": 1,
            "unit": "mm",
            "coordinate_space": "usable_sheet",
            "outer": [[0, 0], [100, 0], [100, 40], [0, 40]],
            "holes": [],
        },
    }
    presets = {"Finish": _preset()}
    fingerprint = settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets=presets,
        machine_profile={"tool_number": "T9"},
        operation_order=["cut_path"],
        cut_path_early_confirmed=False,
    )
    snapshot = build_generation_snapshot(
        order_name="DCO-1",
        cutting_plan="PLAN-1",
        plan_revision=1,
        plan_source_type="System",
        sheet_no=1,
        settings_fingerprint=fingerprint,
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        operation_order=["cut_path"],
        cut_path_early_confirmed=False,
        known_presets=presets,
        machine_profile={"tool_number": "T9", "production_approved": False},
        package={
            "text": "G90\nM30\n",
            "post_processor_version": "almadina_simulation_v1",
            "dialect": "simulation",
            "tool_number": "T9",
            "path_count": 1,
            "pass_count": 1,
            "verification": {"ok": True},
            "content_sha256": nc_content_sha256("G90\nM30\n"),
        },
    )
    saved = [{
        "name": "CNC-FILE-1",
        "cutting_plan": "PLAN-1",
        "plan_revision": 1,
        "plan_source_type": "System",
        "sheet_no": 1,
        "status": "Generated",
        "settings_fingerprint": fingerprint,
        "generation_fingerprint": fingerprint,
        "generation_snapshot": snapshot,
        "snapshot_complete": True,
        "generated_file": "/private/files/a.sim.nc",
        "file_present": True,
        "generated_by": "user",
        "generated_on": "2026-01-01",
        "cut_path_early_confirmed": False,
        "operations": [{"operation_key": "cut_path", "dxf_layer": "CUT_PATH", "sequence": 1, "tool_preset": "", "preset_source": "Factory"}],
        "paths": [],
    }]
    workspace = build_operational_workspace(
        order_name="DCO-1",
        approved_plan=plan,
        plan_is_current=True,
        pieces=[piece],
        saved_files=saved,
        factory_defaults={"cut_path": "Finish"},
        known_presets=presets,
        machine_profile={"production_approved": False, "source_note": "sample", "fingerprint_payload": {"tool_number": "T9"}},
        can_prepare=True,
    )
    sheet = workspace["sheets"][0]
    assert sheet["status"] == GENERATED
    assert sheet["can_download_current"] is True
    assert sheet["download_is_previous"] is False

    orphan = dict(saved[0])
    orphan["generated_file"] = ""
    orphan["file_present"] = False
    orphan_workspace = build_operational_workspace(
        order_name="DCO-1",
        approved_plan=plan,
        plan_is_current=True,
        pieces=[piece],
        saved_files=[orphan],
        factory_defaults={"cut_path": "Finish"},
        known_presets=presets,
        machine_profile={"production_approved": False, "source_note": "sample", "fingerprint_payload": {"tool_number": "T9"}},
        can_prepare=True,
    )
    assert orphan_workspace["sheets"][0]["status"] == NOT_GENERATED
    assert orphan_workspace["sheets"][0]["can_download_current"] is False

