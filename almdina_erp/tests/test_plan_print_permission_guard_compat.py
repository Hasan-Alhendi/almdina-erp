from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
PLAN_ADAPTER = (
    APP_ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_workspace_presenter_adapter.js"
)
ACTION_GUARD = (
    APP_ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_action_permission_guard.js"
)


def test_plan_tabs_facade_stays_decoratable_for_print_permission_guard():
    adapter_source = PLAN_ADAPTER.read_text(encoding="utf-8")
    guard_source = ACTION_GUARD.read_text(encoding="utf-8")

    assert "window.AlmdinaPlanTabsUX = wrapped;" in adapter_source
    assert "window.AlmdinaPlanTabsUX = Object.freeze(wrapped);" not in adapter_source
    assert "tabs.printActivePlan =" in guard_source
    assert "__almdinaPrintPermissionGuarded" in guard_source


def test_presenter_adapter_itself_remains_immutable():
    adapter_source = PLAN_ADAPTER.read_text(encoding="utf-8")

    assert "window.AlmdinaPlanWorkspacePresenterAdapter = Object.freeze({" in adapter_source
