"""ArtCAM profiles are a catalog on the operational-files page, not board defaults."""

from __future__ import annotations

import json
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
_ARABIC = range(0x0600, 0x06FF + 1)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _doctype(name: str) -> dict:
    return json.loads(_text(PACKAGE / "almdina_erp" / "doctype" / name / f"{name}.json"))


def _assert_english_required_fields(doctype: dict) -> None:
    for field in doctype["fields"]:
        label = str(field.get("label") or "")
        assert label, field["fieldname"]
        assert not any(_ARABIC.start <= ord(character) <= _ARABIC.stop - 1 for character in label)
        assert field.get("reqd") == 1, field["fieldname"]


def test_profile_catalog_is_not_a_board_default_and_keeps_the_file_copy():
    settings = json.loads(_text(PACKAGE / "almdina_erp" / "doctype" / "almdina_erp_settings" / "almdina_erp_settings.json"))
    assert all(field.get("fieldname") != "cnc_machining_profiles" for field in settings.get("fields", []))
    doctype = _doctype("cnc_machining_profile")
    assert doctype["name"] == "CNC Machining Profile"
    assert "cnc_machine" not in doctype["field_order"]
    assert all(field.get("fieldname") != "cnc_machine" for field in doctype["fields"])
    assert "tool_values_json" in doctype["field_order"]
    snapshot = next(field for field in doctype["fields"] if field["fieldname"] == "tool_values_json")
    assert snapshot["hidden"] == 1
    assert snapshot["label"] == "Tool Snapshot"
    assert "cnc_machine" not in doctype["field_order"]
    tool = _doctype("cnc_tool_preset")
    assert "final_depth_mm" not in tool["field_order"]
    assert "preset_name" not in tool["field_order"]
    assert "feed_rate_mm_min" not in tool["field_order"]
    assert "pass_depth_mm" not in tool["field_order"]
    assert tool["autoname"] == "field:tool_name"
    operational = json.loads(_text(PACKAGE / "almdina_erp" / "doctype" / "cnc_operational_file" / "cnc_operational_file.json"))
    assert any(field.get("fieldname") == "machining_profiles_json" for field in operational["fields"])
    service = _text(PACKAGE / "almdina_erp" / "services" / "production_settings_service.py")
    assert "def save_cnc_machining_profile" in service
    assert "normalize_profile(" in service
    assert 'document.tool_values_json = profile["tool_values"]' in service
    assert "document.cnc_machine" not in service
    domain = _text(PACKAGE / "almdina_erp" / "domain" / "cnc" / "artcam_machining.py")
    assert "cnc_machine_required" not in domain
    hooks = _text(PACKAGE / "hooks.py")
    assert '"CNC Machining Profile"' in hooks


def test_tool_machine_and_profile_fields_are_required_english_labels():
    tool = _doctype("cnc_tool_preset")
    machine = _doctype("cnc_machine")
    profile = _doctype("cnc_machining_profile")
    for field in tool["fields"]:
        label = str(field.get("label") or "")
        assert label
        assert not any(_ARABIC.start <= ord(character) <= _ARABIC.stop - 1 for character in label)
        expected = 0 if field["fieldname"] == "notes" else 1
        assert field.get("reqd") == expected, field["fieldname"]
    assert tool["field_order"][-1] == "notes"
    _assert_english_required_fields(machine)
    _assert_english_required_fields(profile)
    assert all(field.get("fieldname") != "final_depth_mm" for field in tool["fields"])
    assert any(field.get("fieldname") == "final_depth_mm" and field.get("reqd") == 1 for field in profile["fields"])


def test_profile_editor_lives_on_the_operational_files_page_not_the_sheet_form():
    page = _text(PACKAGE / "almdina_erp" / "page" / "cnc_operational_files" / "cnc_operational_files.js")
    sheet = _text(PACKAGE / "public" / "js" / "cnc" / "artcam_machining_ux.js")
    controller = _text(PACKAGE / "public" / "js" / "factory_production_settings" / "controller.js")
    assert "artcam_profile_dialog.js" not in page
    assert "artcam_tool_dialog.js" not in page
    assert 'frappe.set_route("List", "CNC Machining Profile")' in controller
    assert "data-artcam-profile-form" not in sheet
    assert "dco-artcam-assoc__row" in sheet
    assert 'label: "Vectors"' in sheet
    assert 'label: "Profile"' in sheet
    assert 'class="section-head">Home' in sheet
    assert "data-artcam-home-fields" in sheet
    assert "machining_profiles:" in sheet
    assert "vector_associations:" in sheet
    assert not any("\u0600" <= character <= "\u06ff" for character in sheet)
    cleanup = _text(PACKAGE / "patches" / "v1_0" / "clear_artcam_catalog_and_operational_files.py")
    restore = _text(PACKAGE / "patches" / "v1_0" / "restore_cnc_profile_tool_snapshot.py")
    assert "almdina_artcam_catalog_cleaned_v1" in cleanup
    assert 'delete_doc("Door Cutting Order"' not in cleanup
    assert 'delete_doc("Cutting Plan"' not in cleanup
    assert "cnc_machine_tool_number" not in cleanup
    assert "delete_doc" not in restore
    assert "almdina_artcam_catalog_cleaned_v1" not in restore
    form = _text(PACKAGE / "almdina_erp" / "doctype" / "cnc_machining_profile" / "cnc_machining_profile.js")
    assert "CNC Machine" not in form
    assert "tool_values_json" in form
    assert 'frm.set_df_property("tool_values_json", "hidden", 1)' in form


def test_machining_profile_permission_matches_the_tool_catalog():
    from almdina_erp.almdina_erp.application.security.supporting_doctype_permissions import (
        supporting_standard_permission_projection,
    )
    from almdina_erp.almdina_erp.domain.security.authorization import Capability

    maintainer = supporting_standard_permission_projection(
        "CNC Machining Profile",
        {Capability.EDIT_FACTORY_CNC_DEFAULTS: True},
    )
    assert maintainer["read"] is True
    assert maintainer["write"] is True
    viewer = supporting_standard_permission_projection(
        "CNC Machining Profile",
        {Capability.VIEW_CNC_OPERATIONAL_FILES: True},
    )
    assert viewer["read"] is True
    assert viewer["write"] is False


def test_profile_can_be_normalized_without_a_machine():
    from almdina_erp.almdina_erp.domain.cnc.artcam_machining import normalize_profile
    from almdina_erp.tests.test_artcam_machining import _profile, _stored_tool

    known = {"T9_CUT": _stored_tool()}
    profile = normalize_profile(_profile(), known_tools=known)
    assert "cnc_machine" not in profile
    assert profile["final_depth_mm"] == 20
    assert profile["tool_values"]["diameter_mm"] == 5.0
    known["T9_CUT"]["diameter_mm"] = 12
    known["T9_CUT"]["tool_diameter_mm"] = 12
    reopened = normalize_profile(
        {**profile, "tool_values": dict(profile["tool_values"])},
        known_tools=known,
    )
    assert reopened["tool_values"]["diameter_mm"] == 5.0
