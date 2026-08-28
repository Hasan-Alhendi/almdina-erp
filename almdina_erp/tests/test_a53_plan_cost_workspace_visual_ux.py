from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VISUAL = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_plan_cost_workspace_visual_ux.js"
)
MANIFEST = ROOT / "frontend_assets.py"
REGISTRY = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_workspace_asset_registry.js"
)


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def dco_assets() -> str:
    manifest = source(MANIFEST)
    return manifest.split('"Door Cutting Order": [', 1)[1].split(
        '],\n    "Edge Banding Type"', 1
    )[0]


def test_a53_visual_layer_loads_after_edit_coordinator_before_lazy_plan_field_owner() -> None:
    assets = dco_assets()
    registry = source(REGISTRY)
    visual = (
        '"public/js/door_cutting_order/core/'
        'door_cutting_order_plan_cost_workspace_visual_ux.js"'
    )
    coordinator = (
        '"public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js"'
    )
    field_owner = "door_cutting_order_plan_field_access_adapter.js"

    # A5.3 remains an eager, transport-free document visual decorator and still
    # follows the page edit coordinator on the first-open path.
    assert assets.count(visual) == 1
    assert assets.index(coordinator) < assets.index(visual)

    # The final Plan field-access owner is deliberately lazy in P2. It must not
    # return to the critical path, and it remains the final Plan feature asset.
    assert field_owner not in assets
    assert registry.count(field_owner) == 1
    plan_bundle = registry.split("plan: Object.freeze({", 1)[1].split(
        "cost: Object.freeze({", 1
    )[0]
    assert plan_bundle.rfind(field_owner) > plan_bundle.rfind(
        "door_cutting_order_plan_settings_summary_ux.js"
    )


def test_a53_visual_layer_is_snapshot_only_and_transport_free() -> None:
    visual = source(VISUAL)

    assert "AlmdinaPlanWorkspaceState" in visual
    assert "AlmdinaCostWorkspaceState" in visual
    assert 'typeof owner.snapshot === "function"' in visual
    assert '"almdina:plan-workspace-updated"' in visual
    assert '"almdina:cost-workspace-updated"' in visual
    assert 'context.scheduleFrame(frm, "a53-plan-cost-workspace-visuals"' in visual

    for forbidden in (
        "frappe.call",
        "frm.call",
        "frm.save(",
        "frm.reload_doc",
        "frm.set_value",
        "ignore_permissions",
        "beginEdit(",
        "patchDraft(",
        "cancelEdit(",
        "saveSettings(",
        ".load(frm",
    ):
        assert forbidden not in visual

    # A5.3 must not make DCO business fields or role names into visual authority.
    assert "frm.doc." not in visual
    assert "System Manager" not in visual
    assert "Administrator" not in visual


def test_a53_visual_states_are_explicit_accessible_and_arabic_first() -> None:
    visual = source(VISUAL)

    assert 'data-almdina-workspace-kind' in visual
    assert 'data-almdina-workspace-status' in visual
    assert 'data-almdina-workspace-editing' in visual
    assert 'data-almdina-workspace-stale' in visual
    assert 'node.setAttribute("aria-busy", "true")' in visual
    assert 'node.setAttribute("aria-live", "polite")' in visual
    assert '"idle", "loading", "ready", "error"' in visual
    assert "وضع التعديل مفعّل" in visual
    assert "اضغط «حفظ» من أعلى الصفحة" in visual


def test_a53_polishes_plan_and_cost_without_replacing_existing_presenters() -> None:
    visual = source(VISUAL)

    for plan_selector in (
        '[data-fieldname="plan_controls_intro"] .dco-plan-intro',
        '[data-fieldname="plan_control_actions"] .dco-plan-actions-shell',
        '[data-fieldname="cutting_plan_html"] .dco-plan-tabs',
        '[data-fieldname="cutting_plan_html"] .dco-board-gallery',
    ):
        assert plan_selector in visual

    for cost_selector in (
        ".dco-cost-shell",
        ".dco-cost-section",
        ".dco-cost-table th",
        ".dco-special-price-card",
        ".dco-invoice-total-card",
    ):
        assert cost_selector in visual

    # It decorates the established DOM rather than becoming a second renderer.
    assert "AlmdinaOrderCostUX" not in visual
    assert "AlmdinaPlanTabsUX" not in visual
    assert ".html(" not in visual
    assert "innerHTML" not in visual


def test_a53_is_responsive_keyboard_visible_and_reduced_motion_safe() -> None:
    visual = source(VISUAL)

    assert "@media (max-width:900px)" in visual
    assert "@media (max-width:560px)" in visual
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in visual
    assert "grid-template-columns:1fr" in visual
    assert ":focus-visible" in visual
    assert "@media (prefers-reduced-motion:reduce)" in visual
    assert "animation-duration:.001ms" in visual