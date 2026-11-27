"""On-demand NC export: one verified download, no stored operational file."""

from __future__ import annotations

import ast
import base64
import importlib
from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.cnc.legacy_nc_cleanup import plan_legacy_nc_cleanup
from almdina_erp.almdina_erp.application.cnc.simulation_nc import (
    nc_content_sha256,
    nc_download_payload,
    nc_export_filename,
)
from almdina_erp.almdina_erp.application.cnc.workspace import build_operational_workspace
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    SETTINGS_NOT_CONFIGURED,
    SETTINGS_SAVED,
    ApprovedPlanRef,
    settings_fingerprint,
)
from almdina_erp.patches.v1_0.migrate_cnc_operational_file_status import (
    mapped_operational_status,
)


APP_ROOT = Path(__file__).resolve().parents[1]
SERVICE = APP_ROOT / "almdina_erp" / "services" / "cnc_operational_file_service.py"
REPO = APP_ROOT / "almdina_erp" / "infrastructure" / "frappe" / "cnc_operational_file_repository.py"
UX = APP_ROOT / "public" / "js" / "door_cutting_order" / "cnc" / "door_cutting_order_operational_files_ux.js"
PATCH = APP_ROOT / "patches" / "v1_0" / "backfill_cnc_operational_file_settings_revision.py"
PATCHES = APP_ROOT / "patches.txt"
OPERATIONAL_FILE_META = (
    APP_ROOT / "almdina_erp" / "doctype" / "cnc_operational_file" / "cnc_operational_file.json"
)
AR_TRANSLATIONS = APP_ROOT / "translations" / "ar.csv"


def test_cnc_modules_import_without_broken_names():
    modules = (
        "almdina_erp.almdina_erp.application.cnc.simulation_nc",
        "almdina_erp.almdina_erp.application.cnc.workspace",
        "almdina_erp.almdina_erp.application.cnc.nc_export",
        "almdina_erp.almdina_erp.application.cnc.legacy_nc_cleanup",
        "almdina_erp.almdina_erp.domain.cnc.operational_file",
        "almdina_erp.almdina_erp.domain.cnc.post_processor",
        "almdina_erp.almdina_erp.services.cnc_operational_file_service",
        "almdina_erp.almdina_erp.infrastructure.frappe.cnc_operational_file_repository",
    )
    for name in modules:
        importlib.import_module(name)


def test_verified_download_uses_the_same_nc_bytes_once():
    text = "G90\nG00 X0 Y0\nM30\n"
    payload = nc_download_payload(
        filename="sheet.nc",
        text=text,
        verification={"ok": True, "issues": []},
    )
    assert payload["filename"].endswith(".nc")
    assert base64.standard_b64decode(payload["content_b64"]).decode("utf-8") == text
    assert payload["verification"]["ok"] is True
    with pytest.raises(ValueError):
        nc_download_payload(filename="sheet.nc", text=text, verification={"ok": False})


def test_export_filename_is_nc_and_does_not_imply_a_stored_copy():
    name = nc_export_filename(
        order_name="26-00335",
        cutting_plan="PLAN-1",
        plan_revision=3,
        sheet_no=2,
        content_sha256=nc_content_sha256("G90\nM30\n"),
    )
    assert name == "26-00335(2).nc"
    assert name.endswith(".nc")
    assert not name.endswith(".sim.nc")
    assert "PLAN-1" not in name
    assert "sheet" not in name
    assert "_" not in name


def test_generate_returns_content_without_saving_a_file_or_settings():
    service = SERVICE.read_text(encoding="utf-8")
    repo = REPO.read_text(encoding="utf-8")
    generate = service.split("def generate_cnc_sheet_nc", 1)[1].split("@frappe.whitelist()", 1)[0]
    download = service.split("def download_cnc_sheet_nc", 1)[1].split("def _existing_sheet", 1)[0]
    assert "nc_download_payload(" in generate
    assert "build_post_processed_nc(" in generate
    assert "build_simulation_nc(" not in generate
    assert "_effective_sheet_program(" in generate
    assert "resolve_sheet_placement(" in generate
    assert "save_sheet(" not in generate
    assert "save_file(" not in generate
    assert "record_nc_generation(" in generate
    assert "generated_file" not in generate
    for retired in (
        "simulation_nc_filename",
        "attach_simulation_nc",
        "build_generation_snapshot",
        "discard_orphan_file",
        "read_simulation_nc_bytes",
        "file_url",
        "workspace",
    ):
        assert retired not in generate
    assert "Capability.VIEW_CNC_OPERATIONAL_FILES" in download
    assert "Capability.PREPARE_CNC_OPERATIONAL_FILES" not in download
    assert "stored_nc_unavailable" in download
    assert "filecontent" not in download
    assert "save_file" not in repo
    assert "def record_nc_generation" in repo
    receipt = repo.split("def record_nc_generation", 1)[1].split("def update_machining_json", 1)[0]
    assert "nc_generation_fingerprint" in receipt
    assert "nc_generation_sha256" in receipt
    assert "generated_file" not in receipt
    for retired in (
        "def attach_simulation_nc",
        "def read_simulation_nc_bytes",
        "def discard_orphan_file",
        "def sync_status",
        "generation_snapshot_is_complete",
    ):
        assert retired not in repo


def test_mutations_use_revision_while_fingerprint_stays_a_manufacturing_identity():
    service = SERVICE.read_text(encoding="utf-8")
    calculate = service.split("def calculate_cnc_association_toolpath", 1)[1].split(
        "@frappe.whitelist()", 1
    )[0]
    assert "base_revision" in calculate
    assert "post_processor" in calculate
    assert "post_processor=post_processor" in calculate
    assert "width_stop_side" in calculate
    assert "width_stop_side=width_stop_side" in calculate
    assert "length_stop_cm=length_stop_cm" in calculate
    assert "expected_revision=_revision(base_revision)" in calculate
    assert "base_fingerprint" not in service
    assert "_snapshot_for_request" in calculate

    panel = UX.read_text(encoding="utf-8")
    assert "base_revision" in panel
    assert "beginSheetMutation" in panel
    assert "sheetMutationIsCurrent" in panel
    assert "base_fingerprint" not in panel


def test_revision_backfill_is_registered_and_idempotent_by_predicate():
    source = PATCH.read_text(encoding="utf-8")
    patches = PATCHES.read_text(encoding="utf-8")
    assert "where ifnull(settings_revision, 0) < 1" in source
    assert source.count("set settings_revision = 1") == 1
    assert patches.count("backfill_cnc_operational_file_settings_revision") == 1
    meta = OPERATIONAL_FILE_META.read_text(encoding="utf-8")
    translations = AR_TRANSLATIONS.read_text(encoding="utf-8")
    assert '"fieldname": "settings_revision"' in meta
    assert "Settings Revision,إصدار إعدادات اللوح" in translations


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
    assert "nc_download_payload" in called


def test_ui_downloads_the_returned_nc_without_a_stored_file_prompt():
    panel = UX.read_text(encoding="utf-8")
    assert "content_b64" in panel
    assert "downloadGeneratedNc(" in panel
    assert "Preparing the NC file..." in panel
    assert "NC file generated successfully." in panel
    assert "Save sheet settings" in panel
    assert "Generate NC file" in panel
    assert "_cncNcInFlight" in panel
    assert "download_cnc_sheet_nc" not in panel
    assert "frappe.confirm(" not in panel
    assert "Earlier operational files" not in panel
    assert "data-cnc-back-order" not in panel
    assert "data-cnc-card-download" not in panel
    assert "Simulation NC" not in panel
    assert "not approved for a workshop machine" not in panel
    assert "geometry problems block NC generation" in panel


def test_workspace_status_follows_saved_settings_not_a_stored_nc_file():
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
    presets = {
        "Finish": {
            "preset_name": "Finish",
            "tool_name": "Finish",
            "tool_number": "T9",
            "tool_diameter_mm": 5,
            "enabled": True,
        }
    }
    empty = build_operational_workspace(
        order_name="DCO-1",
        approved_plan=plan,
        plan_is_current=True,
        pieces=[piece],
        saved_files=[],
        factory_defaults={"cut_path": "Finish"},
        known_presets=presets,
        machine_profile={"production_approved": False, "source_note": "sample", "fingerprint_payload": {"tool_number": "T9"}},
        can_prepare=True,
    )
    assert empty["sheets"][0]["status"] == SETTINGS_NOT_CONFIGURED
    assert "historical_files" not in empty
    assert "can_download_current" not in empty["sheets"][0]
    saved = build_operational_workspace(
        order_name="DCO-1",
        approved_plan=plan,
        plan_is_current=True,
        pieces=[piece],
        saved_files=[{
            "name": "CNC-FILE-1",
            "cutting_plan": "PLAN-1",
            "plan_revision": 1,
            "plan_source_type": "System",
            "sheet_no": 1,
            "status": "Generated",
            "settings_fingerprint": "",
            "cut_path_early_confirmed": False,
            "operations": [{"operation_key": "cut_path", "dxf_layer": "CUT_PATH", "sequence": 1, "tool_preset": "", "preset_source": "Factory"}],
            "paths": [],
            "generated_file": "/private/files/a.sim.nc",
        }],
        factory_defaults={"cut_path": "Finish"},
        known_presets=presets,
        machine_profile={"production_approved": False, "source_note": "sample", "fingerprint_payload": {"tool_number": "T9"}},
        can_prepare=True,
    )
    assert saved["sheets"][0]["status"] == SETTINGS_SAVED
    assert saved["sheets"][0]["operational_file"] == "CNC-FILE-1"
    assert "generated_file" not in saved["sheets"][0]
    assert saved["sheets"][0]["nc_file_current"] is False


def test_nc_ready_mark_follows_the_saved_generation_receipt():
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
    presets = {
        "Finish": {
            "preset_name": "Finish",
            "tool_name": "Finish",
            "tool_number": "T9",
            "tool_diameter_mm": 5,
            "enabled": True,
        }
    }
    saved_row = {
        "name": "CNC-FILE-1",
        "cutting_plan": "PLAN-1",
        "plan_revision": 1,
        "plan_source_type": "System",
        "sheet_no": 1,
        "status": "Settings Saved",
        "settings_fingerprint": "",
        "cut_path_early_confirmed": False,
        "cnc_machine": "Router A",
        "operations": [{
            "operation_key": "cut_path",
            "dxf_layer": "CUT_PATH",
            "sequence": 1,
            "tool_preset": "",
            "preset_source": "Factory",
        }],
        "paths": [],
    }
    common = dict(
        order_name="DCO-1",
        approved_plan=plan,
        plan_is_current=True,
        pieces=[piece],
        factory_defaults={"cut_path": "Finish"},
        known_presets=presets,
        machine_profile={"production_approved": False, "source_note": "sample", "fingerprint_payload": {"tool_number": "T9"}},
        cnc_machines=[{
            "name": "Router A",
            "machine_name": "Router A",
            "width_cm": 210,
            "length_cm": 310,
            "enabled": True,
            "work_zero_position": "Bottom Left",
            "width_stop_side": "Left Side",
            "length_stop_side": "Bottom Side",
        }],
        plan_snapshot={"sheets": [{"sheet_no": 1, "full_width_cm": 183, "full_length_cm": 280}]},
        can_prepare=True,
    )
    current = build_operational_workspace(saved_files=[saved_row], **common)
    fingerprint = current["sheets"][0]["settings_fingerprint"]
    assert current["sheets"][0]["nc_file_current"] is False
    ready = build_operational_workspace(
        saved_files=[{**saved_row, "nc_generation_fingerprint": fingerprint, "nc_generation_sha256": "abc"}],
        **common,
    )
    assert ready["sheets"][0]["nc_file_current"] is True
    stale = build_operational_workspace(
        saved_files=[{**saved_row, "nc_generation_fingerprint": "stale"}],
        **common,
    )
    assert stale["sheets"][0]["nc_file_current"] is False
    missing = build_operational_workspace(saved_files=[], **common)
    assert missing["sheets"][0]["nc_file_current"] is False


def test_legacy_status_migration_preserves_saved_sheet_meaning():
    assert mapped_operational_status("Not Generated") == SETTINGS_SAVED
    assert mapped_operational_status("Generated") == SETTINGS_SAVED
    assert mapped_operational_status("Needs Regeneration") == SETTINGS_SAVED
    assert mapped_operational_status(SETTINGS_SAVED) is None
    assert mapped_operational_status(SETTINGS_NOT_CONFIGURED) is None
    assert settings_fingerprint(
        operation_presets={"cut_path": "Finish"},
        path_overrides={},
        presets={"Finish": {"tool_number": "T9"}},
        machine_profile={"tool_number": "T9"},
        operation_order=["cut_path"],
        cut_path_early_confirmed=False,
    )


def test_legacy_nc_cleanup_is_a_dry_run_and_skips_shared_files():
    plan = plan_legacy_nc_cleanup(
        [
            {
                "name": "CNC-1",
                "generated_file": "/private/files/a.nc",
                "generation_snapshot_json": {"previous_generated_file": "/private/files/old.sim.nc"},
                "generated_by": "user@example.com",
            },
            {
                "name": "CNC-2",
                "generated_file": "/private/files/shared.nc",
            },
        ],
        [
            {
                "name": "FILE-1",
                "file_name": "a.nc",
                "file_url": "/private/files/a.nc",
                "attached_to_doctype": "CNC Operational File",
                "attached_to_name": "CNC-1",
            },
            {
                "name": "FILE-2",
                "file_name": "old.sim.nc",
                "file_url": "/private/files/old.sim.nc",
                "attached_to_doctype": "CNC Operational File",
                "attached_to_name": "CNC-1",
            },
            {
                "name": "FILE-3",
                "file_name": "shared.nc",
                "file_url": "/private/files/shared.nc",
                "attached_to_doctype": "CNC Operational File",
                "attached_to_name": "CNC-2",
            },
            {
                "name": "FILE-4",
                "file_name": "shared.nc",
                "file_url": "/private/files/shared.nc",
                "attached_to_doctype": "Door Cutting Order",
                "attached_to_name": "DCO-9",
            },
        ],
    )
    assert plan["dry_run"] is True
    assert plan["deletes_executed"] == 0
    assert "/private/files/a.nc" in plan["deletable_file_urls"]
    assert "/private/files/old.sim.nc" in plan["deletable_file_urls"]
    assert "/private/files/shared.nc" in plan["shared_file_urls"]
    assert "/private/files/shared.nc" not in plan["deletable_file_urls"]
    assert plan["would_clear_generated_file"] == 2
    assert plan["would_clear_generation_snapshot"] == 1
    assert plan["operational_files_with_legacy_fields"] == 2
