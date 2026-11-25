"""Regression guards for DCO form freezes after Frappe 16.60 form-chrome changes."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js" / "door_cutting_order" / "core"
SIDEBAR = PUBLIC / "door_cutting_order_form_sidebar_controller.js"
PRESENTATION = PUBLIC / "door_cutting_order_form_presentation_owner.js"
ACTION_GUARD = PUBLIC / "door_cutting_order_action_permission_guard.js"
EVENT_LOOP = ROOT / "tests" / "test_new_order_workspace_event_loop_regression.py"


class TestDcoFormHangFrappe1660Regression(unittest.TestCase):
    def test_missing_native_form_sidebar_does_not_block_presentation_ready(self) -> None:
        source = SIDEBAR.read_text(encoding="utf-8")
        ready = source.split("function isPreferenceApplied(frm)", 1)[1].split(
            "window.AlmdinaDcoFormSidebarController",
            1,
        )[0]
        self.assertIn("if (actual === null) return true;", ready)
        self.assertIn("Missing native sidebar must not block the presentation settle loop", ready)
        self.assertIn("setNativeSidebarExpanded", source)

    def test_surfaces_settled_does_not_reenter_recover_when_already_ready(self) -> None:
        source = PRESENTATION.read_text(encoding="utf-8")
        self.assertIn('eventName === "almdina:surfaces-settled" && isReady(frm)', source)
        self.assertIn("if (eventName === \"almdina:surfaces-settled\" && isReady(frm)) return;", source)

    def test_action_permission_observer_is_scoped_to_form_root(self) -> None:
        source = ACTION_GUARD.read_text(encoding="utf-8")
        self.assertIn("function observeFormRoot(frm)", source)
        self.assertIn("observer.observe(root, { childList: true, subtree: true });", source)
        self.assertNotIn("document.documentElement", source)
        self.assertIn("observeFormRoot(frm);", source)

    def test_prior_workspace_event_loop_regression_remains_in_suite(self) -> None:
        self.assertTrue(EVENT_LOOP.exists())
        source = EVENT_LOOP.read_text(encoding="utf-8")
        self.assertIn("TestNewOrderWorkspaceEventLoopRegression", source)
        self.assertIn("settleUnavailable", source)


if __name__ == "__main__":
    unittest.main()
