"""ArtCAM profiles are a catalog on the operational-files page, not board defaults."""

from __future__ import annotations

import json
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_profile_catalog_is_not_a_board_default_and_keeps_the_file_copy():
    settings = json.loads(_text(PACKAGE / "almdina_erp" / "doctype" / "almdina_erp_settings" / "almdina_erp_settings.json"))
    assert all(field.get("fieldname") != "cnc_machining_profiles" for field in settings.get("fields", []))
    doctype = json.loads(_text(PACKAGE / "almdina_erp" / "doctype" / "cnc_machining_profile" / "cnc_machining_profile.json"))
    assert doctype["name"] == "CNC Machining Profile"
    assert "tool_values_json" in doctype["field_order"]
    operational = json.loads(_text(PACKAGE / "almdina_erp" / "doctype" / "cnc_operational_file" / "cnc_operational_file.json"))
    assert any(field.get("fieldname") == "machining_profiles_json" for field in operational["fields"])
    service = _text(PACKAGE / "almdina_erp" / "services" / "production_settings_service.py")
    assert "def save_cnc_machining_profile" in service
    assert "normalize_profile(" in service
    hooks = _text(PACKAGE / "hooks.py")
    assert '"CNC Machining Profile"' in hooks


def test_profile_editor_lives_on_the_operational_files_page_not_the_sheet_form():
    page = _text(PACKAGE / "almdina_erp" / "page" / "cnc_operational_files" / "cnc_operational_files.js")
    sheet = _text(PACKAGE / "public" / "js" / "cnc" / "artcam_machining_ux.js")
    dialog = _text(PACKAGE / "public" / "js" / "cnc" / "artcam_profile_dialog.js")
    tool_dialog = _text(PACKAGE / "public" / "js" / "cnc" / "artcam_tool_dialog.js")
    assert "artcam_profile_dialog.js" in page
    assert "data-artcam-profile-form" not in sheet
    assert "dco-artcam-assoc__row" in sheet
    assert 'label: "Vectors"' in sheet
    assert 'label: "Profile"' in sheet
    assert 'class="section-head">Home' in sheet
    assert "data-artcam-home-fields" in sheet
    assert "machining_profiles:" in sheet
    assert "vector_associations:" in sheet
    for source in (sheet, dialog, tool_dialog):
        assert not any("\u0600" <= character <= "\u06ff" for character in source)


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
