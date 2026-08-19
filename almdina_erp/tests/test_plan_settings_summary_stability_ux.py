from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_plan_settings_summary_has_dedicated_owner_after_page_edit_coordinator() -> None:
    manifest = source("frontend_assets.py")
    page_owner = "public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js"
    summary_owner = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_settings_summary_ux.js"

    assert page_owner in manifest
    assert summary_owner in manifest
    assert manifest.index(page_owner) < manifest.index(summary_owner)


def test_readonly_summary_is_anchored_outside_plan_command_surface() -> None:
    summary = source(
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_settings_summary_ux.js"
    )

    assert "plan_actions_section" in summary
    assert "anchor.parentNode.insertBefore(summary, anchor)" in summary
    assert 'frm.fields_dict.plan_control_actions' not in summary
    assert 'data-almdina-plan-settings-summary-owner' in summary
    assert '[data-fieldname=\"plan_control_actions\"] > .${SUMMARY_CLASS}' in summary


def test_summary_reads_canonical_plan_workspace_settings_and_identity() -> None:
    summary = source(
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_settings_summary_ux.js"
    )

    assert "AlmdinaPlanWorkspacePresenterAdapter" in summary
    assert "adapter.activeSettings(frm)" in summary
    assert "AlmdinaPlanWorkspaceState" in summary
    assert 'state.status === "ready"' in summary
    assert 'data-almdina-order' in summary
    assert "frm.doc.name" in summary


def test_summary_recovers_from_workspace_and_surface_rerenders_without_timers() -> None:
    summary = source(
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_settings_summary_ux.js"
    )

    assert '"almdina:plan-workspace-updated"' in summary
    assert '"almdina:surfaces-settled"' in summary
    assert '"almdina:permissions-updated"' in summary
    assert "context.scheduleFrame" in summary
    assert "setTimeout" not in summary
    assert "MutationObserver" not in summary


def test_summary_disappears_only_during_plan_edit_and_returns_from_workspace() -> None:
    summary = source(
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_settings_summary_ux.js"
    )

    assert "AlmdinaPlanEditSessionUX" in summary
    assert "isPlanEditing(frm)" in summary
    assert "removeOwnedSummary(frm)" in summary
    assert "workspaceReady(frm)" in summary
    assert "activeSettings(frm)" in summary
