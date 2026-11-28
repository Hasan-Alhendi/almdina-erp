"""Operational-files permissions: VIEW may download NC from saved settings only."""

from __future__ import annotations

import ast
import csv
import inspect
from pathlib import Path

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    CATEGORY_ORDER,
    capability_catalog_payload,
    normalize_capability_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    CAPABILITY_CATALOG,
    OPERATIONAL_FILES_CAPABILITIES,
    Capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe import authorization_gateway as gateway


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "almdina_erp" / "services" / "cnc_operational_file_service.py"
PANEL = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cnc"
    / "door_cutting_order_operational_files_ux.js"
)
AR_CSV = ROOT / "translations" / "ar.csv"
AUTH = ROOT / "almdina_erp" / "domain" / "security" / "authorization.py"
GATEWAY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "authorization_gateway.py"

_OPERATIONAL_KEYS = (
    Capability.VIEW_CNC_OPERATIONAL_FILES,
    Capability.PREPARE_CNC_OPERATIONAL_FILES,
    Capability.EDIT_FACTORY_CNC_DEFAULTS,
)


def _service_source() -> str:
    return SERVICE.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    tree = ast.parse(_service_source())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(_service_source(), node) or ""
    raise AssertionError(f"function {name} not found")


def test_operational_files_capabilities_live_only_in_new_section() -> None:
    groups = {group["key"]: group for group in capability_catalog_payload()}
    assert "operational_files" in CATEGORY_ORDER
    assert CATEGORY_ORDER.index("cutting_plan") < CATEGORY_ORDER.index("operational_files")
    assert CATEGORY_ORDER.index("operational_files") < CATEGORY_ORDER.index("drawing")

    operational = groups["operational_files"]
    assert operational["label"] == "Operational files"
    keys = [item["key"] for item in operational["capabilities"]]
    assert keys == list(_OPERATIONAL_KEYS)
    assert set(keys) == OPERATIONAL_FILES_CAPABILITIES

    for group in groups.values():
        if group["key"] == "operational_files":
            continue
        overlap = {item["key"] for item in group["capabilities"]}.intersection(_OPERATIONAL_KEYS)
        assert not overlap, f"{group['key']} still lists {sorted(overlap)}"

    for capability in _OPERATIONAL_KEYS:
        assert CAPABILITY_CATALOG[capability].category == "operational_files"


def test_reorganizing_categories_does_not_change_capability_keys_or_grants() -> None:
    before = {
        Capability.VIEW_CNC_OPERATIONAL_FILES: True,
        Capability.PREPARE_CNC_OPERATIONAL_FILES: True,
        Capability.EDIT_FACTORY_CNC_DEFAULTS: True,
        Capability.VIEW_ORDERS: True,
    }
    after = normalize_capability_state(before)
    assert after[Capability.VIEW_CNC_OPERATIONAL_FILES] is True
    assert after[Capability.PREPARE_CNC_OPERATIONAL_FILES] is True
    assert after[Capability.EDIT_FACTORY_CNC_DEFAULTS] is True
    assert after[Capability.VIEW_FACTORY_SETTINGS] is True
    assert after[Capability.VIEW_ORDERS] is True

    view_only = normalize_capability_state({Capability.VIEW_CNC_OPERATIONAL_FILES: True})
    assert view_only[Capability.VIEW_CNC_OPERATIONAL_FILES] is True
    assert view_only[Capability.PREPARE_CNC_OPERATIONAL_FILES] is False
    assert view_only[Capability.EDIT_FACTORY_CNC_DEFAULTS] is False

    prepare = normalize_capability_state({Capability.PREPARE_CNC_OPERATIONAL_FILES: True})
    assert prepare[Capability.VIEW_CNC_OPERATIONAL_FILES] is True
    assert prepare[Capability.PREPARE_CNC_OPERATIONAL_FILES] is True

    for capability in _OPERATIONAL_KEYS:
        assert capability in ALL_CAPABILITIES
        assert capability == CAPABILITY_CATALOG[capability].key


def test_administrator_receives_all_operational_file_capabilities_by_default() -> None:
    assert set(_OPERATIONAL_KEYS).issubset(ALL_CAPABILITIES)
    source = GATEWAY.read_text(encoding="utf-8")
    assert 'if resolved_user == "Administrator"' in source
    assert "return ALL_CAPABILITIES" in inspect.getsource(gateway.granted_capabilities)
    assert 'if resolved_user == "Administrator":\n        return True' in inspect.getsource(
        gateway.doctype_has_capability
    )
    assert 'if resolved_user == "Administrator":\n        return True' in inspect.getsource(
        gateway.document_has_capability
    )
    # No extra DB seed for these three keys is required once ALL_CAPABILITIES covers them.
    auth = AUTH.read_text(encoding="utf-8")
    assert "view_cnc_operational_files" in auth
    assert "prepare_cnc_operational_files" in auth
    assert "edit_factory_cnc_defaults" in auth


def test_generate_nc_allows_view_with_trusted_saved_settings_only() -> None:
    generate = _function_source("generate_cnc_sheet_nc")
    download = _function_source("download_cnc_sheet_nc")

    assert "_authorized_order(order_name, Capability.VIEW_CNC_OPERATIONAL_FILES)" in generate
    assert "document_has_capability" in generate
    assert "Capability.PREPARE_CNC_OPERATIONAL_FILES" in generate
    assert "sheet_settings_required_for_nc" in generate
    assert "_settings_from_saved" in generate
    assert "Ignore every client machining override" in generate
    assert "save_sheet(" not in generate
    assert "build_post_processed_nc(" in generate
    assert "assert_viewed_plan_token" in generate

    assert "_authorized_order(order_name, Capability.VIEW_CNC_OPERATIONAL_FILES)" in download
    assert "Capability.PREPARE_CNC_OPERATIONAL_FILES" not in download


def test_view_only_generate_path_cannot_accept_client_machining_overrides() -> None:
    generate = _function_source("generate_cnc_sheet_nc")
    else_branch = generate.split("else:", 1)[1]
    discarded = else_branch.split("sheet_arguments", 1)[0]
    assert "del (" in discarded
    for name in (
        "operation_presets",
        "path_overrides",
        "operation_order",
        "cut_path_early_confirmed",
        "operation_sources",
        "perimeter_join_mode",
        "cut_path_sequence",
        "perimeter_cut_early_confirmed",
        "cnc_machine",
        "offset_left_cm",
        "offset_bottom_cm",
        "width_stop_side",
        "width_stop_cm",
        "length_stop_side",
        "length_stop_cm",
        "post_processor",
    ):
        assert name in discarded
    assert 'existing.get("cnc_machine")' in else_branch
    assert "saved_operations" in else_branch
    assert "_parse_sheet_settings" not in discarded


def test_workspace_exposes_can_generate_nc_independently_of_prepare() -> None:
    workspace_fn = _function_source("get_cnc_operational_workspace")
    assert "can_generate_nc=True" in workspace_fn
    assert "Capability.VIEW_CNC_OPERATIONAL_FILES" in workspace_fn
    assert "Capability.PREPARE_CNC_OPERATIONAL_FILES" in workspace_fn

    panel = PANEL.read_text(encoding="utf-8")
    assert "can_generate_nc" in panel
    assert "generateNcControlState" in panel
    assert "sheetHasTrustedNcSettings" in panel
    assert "canGenerateNc" in panel
    # View-only download must not open prepare-gated editors.
    assert "live.workspace.can_prepare" in panel
    assert "save.disabled = !canPrepare" in panel
    assert "method: `${METHOD}.generate_cnc_sheet_nc`" in panel


def test_mutation_endpoints_remain_prepare_only_and_order_scoped() -> None:
    authorized = _function_source("_authorized_order")
    assert "require_document_capability" in authorized
    assert 'order.check_permission("read")' in authorized
    assert "You do not have permission to use operational files for this order." in authorized

    for name in (
        "save_cnc_operational_sheet",
        "calculate_cnc_association_toolpath",
        "set_cnc_path_direction",
        "delete_cnc_association",
    ):
        body = _function_source(name)
        assert (
            "_authorized_order(order_name, Capability.PREPARE_CNC_OPERATIONAL_FILES)"
            in body
        )


def test_nc_geometry_pipeline_unchanged_for_permission_split() -> None:
    generate = _function_source("generate_cnc_sheet_nc")
    assert "prepare_sheet_settings(" in generate
    assert "_compile_authorized_program(" in generate
    assert "build_post_processed_nc(" in generate
    assert "resolve_sheet_placement(" in generate
    assert "reversed_direction_block(" in generate
    assert "nc_download_payload(" in generate
    assert "save_sheet(" not in generate
    # Permission change must not reintroduce stored-NC download as the active path.
    download = _function_source("download_cnc_sheet_nc")
    assert "stored_nc_unavailable" in download


def test_arabic_translations_cover_operational_files_permission_copy() -> None:
    rows = {row[0]: row[1] for row in csv.reader(AR_CSV.open(encoding="utf-8")) if row}
    required = {
        "Operational files": "الملفات التشغيلية",
        "View operational files": "عرض الملفات التشغيلية",
        "Prepare operational files": "تجهيز الملفات التشغيلية",
        "Edit CNC defaults": "تعديل إعدادات CNC الافتراضية",
        "Save the sheet settings before generating the NC file.": "احفظ إعدادات اللوح قبل توليد ملف NC.",
        "View and prepare CNC operational files, download NC cutting files, and edit factory CNC defaults.": (
            "عرض وتجهيز الملفات التشغيلية لـ CNC، وتحميل ملفات القص NC، وتعديل إعدادات CNC الافتراضية للمعمل."
        ),
    }
    for english, arabic in required.items():
        assert rows[english] == arabic
