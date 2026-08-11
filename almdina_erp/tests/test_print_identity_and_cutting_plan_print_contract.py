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
IDENTITY_JS = APP_ROOT / "public" / "js" / "door_cutting_order_print_identity.js"
DOCUMENT_PRINT_JS = APP_ROOT / "public" / "js" / "door_cutting_order_document_print_presenter.js"
DOCUMENT_THEME_JS = APP_ROOT / "public" / "js" / "door_cutting_order_document_print_theme.js"
CUTTING_PRINT_JS = APP_ROOT / "public" / "js" / "door_cutting_order_cutting_plan_renderer.js"


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
    source = SETTINGS_PAGE.read_text(encoding="utf-8")
    required = [
        'sectionCard("print_identity"',
        "هوية أوراق الطباعة",
        "اسم المعمل",
        "لمحة مختصرة عن المعمل",
        "العنوان",
        "أرقام التواصل",
        'section === "print_identity"',
    ]
    assert not [fragment for fragment in required if fragment not in source]


def test_print_identity_is_loaded_once_and_shared_by_all_order_prints():
    hooks = HOOKS.read_text(encoding="utf-8")
    identity = IDENTITY_JS.read_text(encoding="utf-8")
    documents = DOCUMENT_PRINT_JS.read_text(encoding="utf-8")
    theme = DOCUMENT_THEME_JS.read_text(encoding="utf-8")
    service = SETTINGS_SERVICE.read_text(encoding="utf-8")

    assert hooks.index('"public/js/door_cutting_order_print_identity.js"') < hooks.index('"public/js/door_cutting_order_cutting_plan_renderer.js"')
    assert "get_print_identity" in identity
    assert "get_print_identity" in service
    assert "AlmdinaFactoryPrintIdentity" in documents
    assert "factoryIdentityHtml" in documents
    assert ".factory-name" in theme
    assert ".factory-contacts" in theme


def test_cutting_plan_print_uses_landscape_dynamic_pages_of_at_most_ten_boards():
    source = CUTTING_PRINT_JS.read_text(encoding="utf-8")
    required = [
        "const MAX_SHEETS_PER_PAGE = 10",
        "@page { size: A4 landscape; margin: 6mm; }",
        "function printGridColumns(count)",
        "if (count <= 6) return 3",
        "if (count <= 8) return 4",
        "return 5",
        "index += MAX_SHEETS_PER_PAGE",
        "page-break-after: always",
        "لوح ${globalBoardIndex}",
        "AlmdinaFactoryPrintIdentity",
    ]
    assert not [fragment for fragment in required if fragment not in source]

    for label in ("رقم الطلب", "اسم الزبون", "لون اللوح", "عدد الألواح", "عدد القطع", "قياس اللوح"):
        assert label in source


def test_cutting_plan_print_is_workshop_monochrome_and_preserves_board_aspect():
    source = CUTTING_PRINT_JS.read_text(encoding="utf-8")
    required = [
        "boardAspectFromCards",
        "const boardHmm = boardWmm * aspect",
        ".dco-edge-line { border-color: #111 !important; }",
        ".dco-shaped-piece-outline polygon { fill: #fff !important; stroke: #111 !important; }",
        "background: #fff !important",
    ]
    assert not [fragment for fragment in required if fragment not in source]
