from __future__ import annotations

import json
from pathlib import Path

from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.domain.security.factory_settings import decide_settings_update


APP_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_JSON = APP_ROOT / "almdina_erp" / "doctype" / "almdina_erp_settings" / "almdina_erp_settings.json"
SETTINGS_SERVICE = APP_ROOT / "almdina_erp" / "services" / "production_settings_service.py"
SETTINGS_PAGE = APP_ROOT / "almdina_erp" / "page" / "factory_production_settings" / "factory_production_settings.js"
HOOKS = APP_ROOT / "hooks.py"
IDENTITY_JS = APP_ROOT / "public" / "js" / "door_cutting_order" / "printing" / "door_cutting_order_print_identity.js"
DOCUMENT_PRINT_JS = APP_ROOT / "public" / "js" / "door_cutting_order" / "printing" / "door_cutting_order_document_print_presenter.js"
DOCUMENT_THEME_JS = APP_ROOT / "public" / "js" / "door_cutting_order" / "printing" / "door_cutting_order_document_print_theme.js"
CUTTING_PRINT_JS = APP_ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan" / "door_cutting_order_cutting_plan_renderer.js"


def test_print_identity_is_configurable_without_hardcoded_phone_numbers():
    payload = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    fields = {field["fieldname"]: field for field in payload["fields"]}

    assert fields["print_factory_name"]["default"] == "مجمع المدينة المنورة التجاري"
    assert fields["print_factory_description"]["default"] == "الواح هايغلوس - فورميكا - cnc - ليزر - قشر"
    assert fields["print_factory_address"]["default"] == "دمشق - ببيلا - طريق السيدة زينب"
    assert fields["print_factory_contacts"].get("default", "") == ""

    denied = decide_settings_update(
        {Capability.EDIT_FACTORY_CUTTING_DEFAULTS},
        {"print_factory_name": "اسم جديد"},
    )
    allowed = decide_settings_update(
        {Capability.EDIT_FACTORY_PRINT_IDENTITY},
        {"print_factory_name": "اسم جديد", "print_factory_contacts": "واتس اب: 000"},
    )
    assert not denied.allowed
    assert allowed.allowed


def test_settings_console_exposes_a_dedicated_print_identity_section():
    view = (APP_ROOT / "public" / "js" / "factory_production_settings" / "view_model.js").read_text(encoding="utf-8")
    dialogs = (APP_ROOT / "public" / "js" / "factory_production_settings" / "dialogs.js").read_text(encoding="utf-8")
    for fragment in (
        'section("print_identity"',
        "هوية أوراق الطباعة",
        "اسم المعمل",
        "لمحة عن المعمل",
        "العنوان",
        "أرقام التواصل",
    ):
        assert fragment in view
    assert 'section === "print_identity"' in dialogs


def test_print_identity_is_loaded_once_and_shared_by_all_order_prints():
    hooks = HOOKS.read_text(encoding="utf-8")
    identity = IDENTITY_JS.read_text(encoding="utf-8")
    documents = DOCUMENT_PRINT_JS.read_text(encoding="utf-8")
    theme = DOCUMENT_THEME_JS.read_text(encoding="utf-8")
    service = SETTINGS_SERVICE.read_text(encoding="utf-8")

    assets = (APP_ROOT / "frontend_assets.py").read_text(encoding="utf-8")
    identity_asset = "public/js/door_cutting_order/printing/door_cutting_order_print_identity.js"
    presenter_asset = "public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js"
    assert assets.index(identity_asset) < assets.index(presenter_asset)
    assert "door_cutting_order_cutting_plan_renderer.js" not in assets
    assert "door_cutting_order_print_identity.js" not in hooks
    assert "get_print_identity" in identity
    assert "get_print_identity" in service
    assert "AlmdinaFactoryPrintIdentity" in documents
    assert "resolvePrintIdentity" in documents
    assert ".dco-unified-print-factory-name" in theme
    assert ".dco-unified-print-factory-contacts" in theme


def test_cutting_plan_print_uses_landscape_dynamic_pages_of_at_most_ten_boards():
    source = CUTTING_PRINT_JS.read_text(encoding="utf-8")
    required = [
        "const MAX_SHEETS_PER_PAGE = 10",
        "@page { size: A4 landscape; margin: 6mm; }",
        "function printGridColumns(count)",
        "function printRowSizes(count)",
        "if (count <= 6) return [count]",
        "if (count === 8) return [4, 4]",
        "return [5, Math.max(0, count - 5)].filter(Boolean)",
        "index += MAX_SHEETS_PER_PAGE",
        "page-break-after: always",
        'htmlText("Board {0}", [globalBoardIndex])',
        "AlmdinaFactoryPrintIdentity",
    ]
    assert not [fragment for fragment in required if fragment not in source]

    for label in ("Order number", "Customer name", "Board color", "Board count", "Piece count", "Board size"):
        assert label in source

    meta = source.split("function printOrderMetaHtml", 1)[1].split(
        "function boardAspectFromCards", 1
    )[0]
    assert 'translate("Plan name")' not in meta
    assert 'translate("Plan revision")' not in meta
    assert 'data-resource-kind="OFFCUT"] .dco-sheet-board' in source
    assert "background: #E5E7EB !important" in source
    assert "stripPrintOnlyBoardChrome" in source
    assert "printCardHtml" in source


def test_section_scoped_settings_save_does_not_require_unrelated_mandatory_fields() -> None:
    """Extra/pricing saves must not fail when print identity columns are empty.

    Print identity fields are reqd on the Single DocType, but the unified
    console saves one section at a time. Read path substitutes defaults;
    write path must ignore unrelated mandatory fields and must not backfill
    print identity without edit_factory_print_identity.
    """
    source = SETTINGS_SERVICE.read_text(encoding="utf-8")
    update = source.split("def update_production_settings", 1)[1].split(
        "def get_factory_settings_audit", 1
    )[0]
    apply_values = source.split("def _apply_values", 1)[1].split(
        "def _print_identity_values", 1
    )[0]
    assert "settings.flags.ignore_mandatory = True" in update
    assert "settings.save(ignore_permissions=True)" in update
    assert "PRINT_IDENTITY_DEFAULTS" not in apply_values


def test_cutting_plan_print_is_workshop_monochrome_and_preserves_board_aspect():
    source = CUTTING_PRINT_JS.read_text(encoding="utf-8")
    required = [
        "boardAspectFromCards",
        "const boardHmm = boardWmm * aspect",
        ".dco-edge-line {",
        "border-color: #e00000 !important;",
        ".dco-shaped-piece-outline path { fill: #fff !important; stroke: #111 !important; }",
        "background: #fff !important",
    ]
    assert not [fragment for fragment in required if fragment not in source]
