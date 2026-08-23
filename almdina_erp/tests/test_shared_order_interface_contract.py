from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP_FLOOR_PAGE = (
    ROOT / "almdina_erp" / "page" / "shop_floor_inbox" / "shop_floor_inbox.js"
)
ORDER_UX = ROOT / "public" / "js" / "shop_floor_order_ux.js"
PLAN_TABS = ROOT / "public" / "js" / "door_cutting_order_plan_tabs_ux.js"
ORDER_LIST = ROOT / "public" / "js" / "door_cutting_order_list.js"
HOOKS = ROOT / "hooks.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shop_floor_cards_open_the_canonical_order_form() -> None:
    page = source(SHOP_FLOOR_PAGE)

    assert 'frappe.set_route("Form", "Door Cutting Order", context.order)' in page
    assert "METHODS.detail" not in page
    assert "buildPlanTabsHtml" not in page
    assert "renderDetail" not in page
    assert "system_plan_html" not in page
    assert "custom_plan_html" not in page
    assert "approved_plan_html" not in page


def test_shop_floor_profile_never_replaces_or_whitelists_the_form_layout() -> None:
    order_ux = source(ORDER_UX)
    presentation = order_ux.split("function applyShopFloorPresentation", 1)[1].split(
        "function openDispatchDialog", 1
    )[0]

    assert "const keep = new Set" not in presentation
    assert "clear_inner_toolbar" not in presentation
    assert 'set_tab("results_tab")' not in presentation
    assert 'can(frm, "edit_order")' in presentation
    assert "frm.disable_save()" in presentation
    assert 'frm.add_custom_button(__("رجوع لصالة الإنتاج")' in presentation

    dispatch = order_ux.split("function addDispatchButton", 1)[1].split(
        "function addRevertButton", 1
    )[0]
    delivery = order_ux.split("function addDeliveryButtons", 1)[1].split(
        "function openRevertDialog", 1
    )[0]
    assert "isShopFloorProfile" not in dispatch
    assert "isShopFloorProfile" not in delivery


def test_plan_tabs_never_expand_an_umbrella_permission_in_the_browser() -> None:
    tabs = source(PLAN_TABS)
    visible = tabs.split("function visibleTabs", 1)[1].split(
        "function parseJsonField", 1
    )[0]

    assert "PLAN_TABS.filter" in visible
    assert "PLAN_TABS.slice" not in visible
    assert 'canCapability(frm, "view_cutting_plan")' not in visible


def test_order_list_never_treats_the_header_as_an_order_row() -> None:
    order_list = source(ORDER_LIST)
    mobile = order_list.split("function renderMobileCards", 1)[1].split(
        "function installResponsiveObserver", 1
    )[0]
    presentation = order_list.split(
        "function applyOperationalRolePresentation", 1
    )[1].split("function applyOperationalRoleRows", 1)[0]
    schedule = order_list.split("function schedule", 1)[1].split(
        "frappe.listview_settings", 1
    )[0]

    assert ".filter(item => item.name && docs.has(item.name))" in mobile
    assert "if (!name) return;" in presentation
    assert "needsReorder" in presentation
    assert schedule.count("applyOperationalRoleRows(listview)") == 1


def test_order_list_actions_are_server_authorized_not_status_guesses() -> None:
    order_list = source(ORDER_LIST)
    quick_action = order_list.split("function quickActionContext", 1)[1].split(
        "function field", 1
    )[0]

    assert "__almdinaProductionActionContext" in quick_action
    assert "authorized.canStart === true" in quick_action
    assert "authorized.canHandoff === true" in quick_action
    assert "current_assignee === frappe.session.user" not in quick_action
    assert 'department_status === "بحاجة للعمل"' not in quick_action


def test_retired_shop_floor_detail_adapter_is_not_loaded_globally() -> None:
    assert "shop_floor_dxf_visibility_ux.js" not in source(HOOKS)
