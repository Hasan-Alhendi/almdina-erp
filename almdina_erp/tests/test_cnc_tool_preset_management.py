"""Layer presets, factory inheritance, and tool-preset management."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from almdina_erp.almdina_erp.application.cnc.workspace import (
    build_operational_workspace,
    prepare_sheet_settings,
)
from almdina_erp.almdina_erp.domain.cnc.operational_file import (
    NEEDS_REGENERATION,
    NOT_GENERATED,
    OperationalFileError,
    ApprovedPlanRef,
    cut_path_precedes_internal,
    settings_fingerprint,
)
from almdina_erp.almdina_erp.domain.cnc.tool_preset import (
    normalize_tool_preset,
    tool_preset_write_allowed,
    unused_tool_preset_can_be_deleted,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


APP_ROOT = Path(__file__).resolve().parents[1]
SERVICE = APP_ROOT / "almdina_erp" / "services" / "production_settings_service.py"
PANEL = (
    APP_ROOT
    / "public"
    / "js"
    / "factory_production_settings"
    / "renderer.js"
)


def _raw(**overrides):
    values = {
        "preset_name": "Finish",
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


def _known():
    return {
        "Finish": _raw(),
        "Shallow": _raw(preset_name="Shallow", final_depth_mm=7, pass_depth_mm=2),
        "Other": _raw(preset_name="Other", tool_number="T8"),
        "Wide": _raw(preset_name="Wide", tool_diameter_mm=8),
        "Disabled": _raw(preset_name="Disabled", enabled=False),
    }


def _piece():
    return {
        "piece_instance_id": "piece-a",
        "label": "piece-a",
        "sheet_no": 1,
        "extra_liner": 0,
        "overlays": [
            {"kind": "liner", "layer": "Liner", "geometry": {"n": index}}
            for index in range(5)
        ],
    }


def _plan():
    return ApprovedPlanRef("PLAN-1", 3, "System", "Approved")


def _workspace(*, factory, saved=None, known=None):
    return build_operational_workspace(
        order_name="DCO-1",
        approved_plan=_plan(),
        plan_is_current=True,
        pieces=[_piece()],
        saved_files=[] if saved is None else [saved],
        factory_defaults=factory,
        known_presets=_known() if known is None else known,
        machine_profile={"production_approved": False, "source_note": "", "fingerprint_payload": {}},
        can_prepare=True,
    )


def _prepare(**kwargs):
    return prepare_sheet_settings(
        order_name="DCO-1",
        approved_plan=_plan(),
        plan_is_current=True,
        pieces=[_piece()],
        sheet_no=1,
        existing=kwargs.get("existing"),
        operation_presets=kwargs.get("presets") or {},
        path_overrides=kwargs.get("paths") or {},
        known_presets=_known(),
        machine_profile={"fingerprint_payload": {}},
        operation_order=kwargs.get("order"),
        cut_path_early_confirmed=kwargs.get("confirmed", False),
        operation_sources=kwargs.get("sources"),
        factory_defaults=kwargs.get("factory") or {},
    )


def _liner_paths(rows):
    return [row for row in rows if row["operation_key"] == "liner"]


def test_creating_a_preset_requires_the_factory_capability_and_then_appears_for_layers():
    created = normalize_tool_preset(_raw(preset_name="Liner finish"))
    assert created.preset_name == "Liner finish"
    assert created.enabled is True
    assert tool_preset_write_allowed({Capability.EDIT_FACTORY_CNC_DEFAULTS}) is True
    assert tool_preset_write_allowed({Capability.PREPARE_CNC_OPERATIONAL_FILES}) is False
    assert tool_preset_write_allowed({Capability.VIEW_FACTORY_SETTINGS}) is False
    assert tool_preset_write_allowed({Capability.EDIT_FACTORY_CUTTING_DEFAULTS}) is False

    service = SERVICE.read_text(encoding="utf-8")
    for name in ("save_cnc_tool_preset", "set_cnc_tool_preset_enabled", "delete_cnc_tool_preset"):
        body = service.split(f"def {name}", 1)[1].split("\ndef ", 1)[0]
        assert "_require_tool_preset_editor()" in body
        assert "ignore_permissions" not in body
        assert "check_permission(" in body
    assert "assert_tool_preset_can_be_deleted" in service
    assert "tool_delete_blockers" in service
    assert "active_snapshot_uses=counts[\"active_snapshots\"]" in service
    assert unused_tool_preset_can_be_deleted(operation_uses=0, path_uses=0, factory_uses=0) is True
    assert unused_tool_preset_can_be_deleted(operation_uses=1, path_uses=0, factory_uses=0) is False
    assert unused_tool_preset_can_be_deleted(operation_uses=0, path_uses=1, factory_uses=0) is False
    assert unused_tool_preset_can_be_deleted(operation_uses=0, path_uses=0, factory_uses=1) is False
    delete_body = service.split("def delete_cnc_tool_preset", 1)[1].split("\ndef ", 1)[0]
    assert "assert_tool_preset_can_be_deleted(preset_name)" in delete_body
    assert "historical_snapshots" not in delete_body
    disable_body = service.split("def set_cnc_tool_preset_enabled", 1)[1].split("\ndef ", 1)[0]
    assert "if live_uses:" in disable_body
    assert "_snapshot_uses" in disable_body
    panel = PANEL.read_text(encoding="utf-8")
    assert "Operational file settings" in panel
    assert "CNC tool presets" in panel
    assert "Manage tool presets" in panel
    assert "Add a tool preset" in panel
    assert "aps-cnc-preset-manage" in panel
    assert "aps-cnc-preset-edit" not in panel
    assert "aps-cnc-tool-delete" not in panel
    assert "Manage machining profiles" in panel
    doctype_py = (
        APP_ROOT / "almdina_erp" / "doctype" / "cnc_tool_preset" / "cnc_tool_preset.py"
    ).read_text(encoding="utf-8")
    assert "assert_tool_preset_can_be_deleted" in doctype_py.split("def on_trash", 1)[1]
    presets_js = (
        APP_ROOT / "public" / "js" / "factory_production_settings" / "cnc_presets.js"
    ).read_text(encoding="utf-8")
    assert 'frappe.set_route("List", DOCTYPE)' in presets_js or 'frappe.set_route("List", "CNC Tool Preset")' in presets_js
    assert "frappe.new_doc" in presets_js
    doctype = (
        APP_ROOT / "almdina_erp" / "doctype" / "cnc_tool_preset" / "cnc_tool_preset.json"
    ).read_text(encoding="utf-8")
    assert '"quick_entry": 1' in doctype
    assert "final_depth_mm" not in doctype
    assert '"search_fields": "tool_name,tool_number"' in doctype
    assert '"in_list_view": 1' in doctype
    assert "spindle_speed_rpm" in doctype

    known = {"Liner finish": _raw(preset_name="Liner finish")}
    workspace = _workspace(
        factory={"liner": "Liner finish", "cut_path": "Liner finish"},
        known=known,
    )
    assert [row["name"] for row in workspace["presets"]] == ["Liner finish"]
    liner = next(row for row in workspace["sheets"][0]["operations"] if row["operation_key"] == "liner")
    assert liner["tool_preset"] == "Liner finish"
    assert liner["preset_source"] == "factory"


def test_five_liner_paths_inherit_one_layer_preset_and_one_path_can_be_restored():
    workspace = _workspace(factory={"liner": "Finish", "cut_path": "Finish"})
    sheet = workspace["sheets"][0]
    liner_paths = _liner_paths(sheet["paths"])
    assert len(liner_paths) == 5
    assert all(path["tool_preset"] == "" for path in liner_paths)
    liner = next(row for row in sheet["operations"] if row["operation_key"] == "liner")
    assert liner["tool_preset"] == "Finish"
    assert liner["preset_source"] == "factory"
    assert [row["operation_key"] for row in sheet["operations"]] == ["liner", "cut_path"]

    changed = _prepare(
        presets={"liner": "Shallow", "cut_path": "Shallow"},
        sources={"liner": "sheet", "cut_path": "sheet"},
        factory={"liner": "Finish", "cut_path": "Finish"},
    )
    assert next(row for row in changed["operations"] if row["operation_key"] == "liner")["tool_preset"] == "Shallow"
    assert all(path["tool_preset"] == "" for path in _liner_paths(changed["paths"]))

    custom_key = liner_paths[0]["path_key"]
    custom = _prepare(
        presets={"liner": "Shallow", "cut_path": "Shallow"},
        sources={"liner": "sheet", "cut_path": "sheet"},
        paths={custom_key: "Finish"},
        factory={"liner": "Finish", "cut_path": "Finish"},
    )
    saved_paths = {row["path_key"]: row["tool_preset"] for row in custom["paths"]}
    assert saved_paths[custom_key] == "Finish"
    assert sum(1 for key, value in saved_paths.items() if key.startswith("liner:") and value) == 1
    assert sum(1 for key, value in saved_paths.items() if key.startswith("liner:") and value == "") == 4

    restored = _prepare(
        presets={"liner": "Shallow", "cut_path": "Shallow"},
        sources={"liner": "sheet", "cut_path": "sheet"},
        paths={},
        factory={"liner": "Finish", "cut_path": "Finish"},
    )
    assert all(path["tool_preset"] == "" for path in _liner_paths(restored["paths"]))


def test_factory_inheritance_keeps_sheet_choices_and_marks_a_generated_file():
    inherited = _prepare(
        presets={"liner": "Finish", "cut_path": "Finish"},
        sources={"liner": "factory", "cut_path": "factory"},
        factory={"liner": "Finish", "cut_path": "Finish"},
    )
    liner = next(row for row in inherited["operations"] if row["operation_key"] == "liner")
    assert liner["tool_preset"] == ""
    assert liner["preset_source"] == "Factory"

    first = _workspace(
        factory={"liner": "Finish", "cut_path": "Finish"},
        saved={
            "name": "CNC-1",
            "cutting_plan": "PLAN-1",
            "plan_revision": 3,
            "sheet_no": 1,
            "operations": inherited["operations"],
            "paths": [],
            "generation_fingerprint": "",
            "generated_file": "kept-file",
        },
    )
    current = first["sheets"][0]["settings_fingerprint"]
    assert next(row for row in first["sheets"][0]["operations"] if row["operation_key"] == "liner")["tool_preset"] == "Finish"
    assert first["sheets"][0]["status"] == NOT_GENERATED

    generated = {
        "name": "CNC-1",
        "cutting_plan": "PLAN-1",
        "plan_revision": 3,
        "sheet_no": 1,
        "operations": inherited["operations"],
        "paths": [],
        "generation_fingerprint": current,
        "generated_file": "kept-file",
    }
    changed_factory = _workspace(
        factory={"liner": "Shallow", "cut_path": "Shallow"},
        saved=generated,
    )
    assert next(row for row in changed_factory["sheets"][0]["operations"] if row["operation_key"] == "liner")["tool_preset"] == "Shallow"
    assert changed_factory["sheets"][0]["status"] == NEEDS_REGENERATION
    assert changed_factory["sheets"][0]["generated_file"] == "kept-file"
    assert generated["generation_fingerprint"] == current

    choice = _prepare(
        presets={"liner": "Finish", "cut_path": "Finish"},
        sources={"liner": "sheet", "cut_path": "factory"},
        factory={"liner": "Finish", "cut_path": "Finish"},
    )
    kept = _workspace(
        factory={"liner": "Shallow", "cut_path": "Shallow"},
        saved={
            "name": "CNC-2",
            "cutting_plan": "PLAN-1",
            "plan_revision": 3,
            "sheet_no": 1,
            "operations": choice["operations"],
            "paths": [{"path_key": _liner_paths(choice["paths"])[0]["path_key"], "operation_key": "liner", "tool_preset": "Finish"}],
            "generation_fingerprint": "",
            "generated_file": "",
        },
    )
    rows = {row["operation_key"]: row for row in kept["sheets"][0]["operations"]}
    assert rows["liner"]["tool_preset"] == "Finish"
    assert rows["liner"]["preset_source"] == "sheet"
    assert rows["cut_path"]["tool_preset"] == "Shallow"
    assert rows["cut_path"]["preset_source"] == "factory"
    custom = next(path for path in kept["sheets"][0]["paths"] if path["tool_preset"])
    assert custom["tool_preset"] == "Finish"
    assert sum(1 for path in _liner_paths(kept["sheets"][0]["paths"]) if path["tool_preset"]) == 1


def test_a_blank_legacy_preset_inherits_the_factory_and_a_saved_name_stays():
    blank = _workspace(
        factory={"liner": "Finish", "cut_path": "Shallow"},
        saved={
            "name": "CNC-OLD",
            "cutting_plan": "PLAN-1",
            "plan_revision": 3,
            "sheet_no": 1,
            "operations": [
                {"operation_key": "liner", "tool_preset": ""},
                {"operation_key": "cut_path", "tool_preset": "Saved preset"},
            ],
            "paths": [],
            "generation_fingerprint": "",
            "generated_file": "",
        },
    )
    rows = {row["operation_key"]: row for row in blank["sheets"][0]["operations"]}
    assert rows["liner"]["tool_preset"] == "Finish"
    assert rows["liner"]["preset_source"] == "factory"
    assert rows["cut_path"]["tool_preset"] == "Saved preset"
    assert rows["cut_path"]["preset_source"] == "sheet"


def test_a_sheet_rejects_a_second_tool_and_an_unconfirmed_early_cut():
    with pytest.raises(OperationalFileError) as conflict:
        _prepare(
            presets={"liner": "Finish", "cut_path": "Other"},
            sources={"liner": "sheet", "cut_path": "sheet"},
        )
    assert conflict.value.code == "tool_identity_conflict"

    with pytest.raises(OperationalFileError) as diameter:
        _prepare(
            presets={"liner": "Finish", "cut_path": "Wide"},
            sources={"liner": "sheet", "cut_path": "sheet"},
        )
    assert diameter.value.code == "tool_diameter_conflict"

    with pytest.raises(OperationalFileError) as early:
        _prepare(
            presets={"liner": "Finish", "cut_path": "Finish"},
            sources={"liner": "sheet", "cut_path": "sheet"},
            order=["cut_path", "liner"],
            confirmed=False,
        )
    assert early.value.code == "cut_path_early_unconfirmed"
    assert cut_path_precedes_internal(("cut_path", "liner")) is True
    assert settings_fingerprint(
        operation_presets={"liner": "Finish"},
        path_overrides={},
        presets=_known(),
    )


def test_tool_notes_are_optional_and_last_on_both_forms():
    doctype = json.loads(
        (
            APP_ROOT / "almdina_erp" / "doctype" / "cnc_tool_preset" / "cnc_tool_preset.json"
        ).read_text(encoding="utf-8")
    )
    assert doctype["field_order"][-1] == "notes"
    assert [field["fieldname"] for field in doctype["fields"]][-1] == "notes"
    notes = next(field for field in doctype["fields"] if field["fieldname"] == "notes")
    assert notes["label"] == "Notes"
    assert notes["reqd"] == 0
    controller = (
        APP_ROOT / "almdina_erp" / "doctype" / "cnc_tool_preset" / "cnc_tool_preset.py"
    ).read_text(encoding="utf-8")
    assert "notes_required" not in controller
    dialog = (APP_ROOT / "public" / "js" / "cnc" / "artcam_tool_dialog.js").read_text(encoding="utf-8")
    fields = dialog.split("function fieldsFor", 1)[1].split("function open", 1)[0]
    assert fields.rfind('fieldname: "notes"') > fields.rfind('fieldname: "plunge_rate_mm_sec"')
    assert 'label: "Notes", reqd: 0' in fields
