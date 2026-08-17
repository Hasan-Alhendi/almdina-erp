from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js" / "door_cutting_order"
COORDINATOR = PUBLIC / "core" / "door_cutting_order_page_edit_action_ux.js"
COST_SESSION = PUBLIC / "costing" / "door_cutting_order_cost_edit_session_ux.js"
PLAN_SESSION = PUBLIC / "cutting_plan" / "door_cutting_order_plan_edit_session_ux.js"
PLAN_FIELD_ACCESS = PUBLIC / "cutting_plan" / "door_cutting_order_plan_field_access_adapter.js"
MANIFEST = ROOT / "frontend_assets.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _dco_assets() -> str:
    manifest = source(MANIFEST)
    return manifest.split('"Door Cutting Order": [', 1)[1].split(
        '],\n    "Edge Banding Type"', 1
    )[0]


def test_contextual_edit_action_preserves_final_plan_field_owner() -> None:
    assets = _dco_assets()
    coordinator = (
        '"public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js"'
    )
    plan_session = (
        '"public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_edit_session_ux.js"'
    )
    plan_access = (
        '"public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_field_access_adapter.js"'
    )
    cost_session = (
        '"public/js/door_cutting_order/costing/door_cutting_order_cost_edit_session_ux.js"'
    )

    assert assets.count(coordinator) == 1
    assert assets.count(cost_session) == 1
    assert assets.index(cost_session) < assets.index(plan_session)
    assert assets.index(plan_session) < assets.index(coordinator)
    assert assets.index(coordinator) < assets.index(plan_access)
    # The toolbar coordinator does not own field status. Preserve the established
    # final PlanFieldAccessAdapter contract so no later layer can reopen inputs.
    assert assets.rstrip().endswith(plan_access + ",")


def test_financial_presenter_keeps_its_existing_owner_chain() -> None:
    assets = _dco_assets()
    permissions = (
        '"public/js/door_cutting_order/costing/door_cutting_order_cost_permissions_ux.js"'
    )
    financial = (
        '"public/js/door_cutting_order/costing/door_cutting_order_financial_documents_ux.js"'
    )
    cost_session = (
        '"public/js/door_cutting_order/costing/door_cutting_order_cost_edit_session_ux.js"'
    )

    # The existing financial-doc contract separately verifies exact adjacency.
    # This feature only adds the cost edit-session after that protected chain.
    assert assets.index(permissions) < assets.index(financial) < assets.index(cost_session)


def test_active_top_level_tab_selects_one_edit_command_family() -> None:
    coordinator = source(COORDINATOR)

    assert 'order_tab: "order"' in coordinator
    assert 'results_tab: "plan"' in coordinator
    assert 'cost_tab: "cost"' in coordinator
    assert 'order: "تعديل الطلب"' in coordinator
    assert 'plan: "تعديل خطة القص"' in coordinator
    assert 'cost: "تعديل التكلفة"' in coordinator
    assert 'const SAVE_LABEL = "حفظ"' in coordinator
    assert 'const CANCEL_LABEL = "إلغاء"' in coordinator

    # Existing domain/session owners remain authoritative; the page action only
    # delegates to them instead of re-implementing capability rules.
    assert "api.canOfferEditSession(frm)" in coordinator
    assert "api.canEditPlanSettings(frm)" in coordinator
    assert "api.canEditCostSettings(frm)" in coordinator
    assert "api.enterEditSession(frm)" in coordinator
    assert "api.commitEditSession(frm)" in coordinator
    assert "api.startEditing(frm)" in coordinator
    assert "api.saveEditing(frm)" in coordinator


def test_switching_tabs_is_blocked_while_any_page_edit_session_is_open() -> None:
    coordinator = source(COORDINATOR)

    assert "function activeEditingKind(frm)" in coordinator
    assert "if (editingKind && targetField !== currentField)" in coordinator
    assert "event.preventDefault();" in coordinator
    assert "event.stopImmediatePropagation();" in coordinator
    assert "احفظ أو ألغِ التعديل الحالي قبل الانتقال إلى قسم آخر" in coordinator


def test_plan_card_edit_toolbar_is_hidden_when_page_toolbar_owns_editing() -> None:
    coordinator = source(COORDINATOR)
    plan_session = source(PLAN_SESSION)

    # Plan session keeps its state/save API for backwards compatibility, while
    # the page-level coordinator is now the only visible edit affordance.
    assert ".dco-plan-settings-edit-toolbar { display:none !important; }" in coordinator
    assert "window.AlmdinaPlanEditSessionUX" in plan_session
    assert "startEditing," in plan_session
    assert "saveEditing," in plan_session
    assert "cancelEditing," in plan_session


def test_cost_page_is_read_only_until_explicit_cost_edit_session() -> None:
    cost = source(COST_SESSION)

    assert '"board_rate_usd"' in cost
    assert '"cutting_cost_per_board_usd"' in cost
    assert 'can(frm, "view_costs")' in cost
    assert 'can(frm, "edit_cost_settings")' in cost
    assert "costSettingsMayWrite(frm)" in cost
    assert 'df.get_status = function almdinaFocusedCostFieldStatus' in cost
    assert 'field.df[STATUS_KEY] = mayWrite ? "Write" : "Read"' in cost

    assert (
        "almdina_erp.almdina_erp.services.cost_permission_service."
        "update_order_cost_settings"
    ) in cost
    assert "frm.reload_doc()" in cost
    assert "ignore_permissions" not in cost
    assert "frm.save(" not in cost
    assert "order.save(" not in cost


def test_focused_field_owners_are_separate_between_plan_and_cost() -> None:
    plan_access = source(PLAN_FIELD_ACCESS)
    cost = source(COST_SESSION)

    for fieldname in (
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
    ):
        assert f'"{fieldname}"' in plan_access
        assert f'"{fieldname}"' not in cost

    for fieldname in ("board_rate_usd", "cutting_cost_per_board_usd"):
        assert f'"{fieldname}"' in cost
        assert f'"{fieldname}"' not in plan_access
