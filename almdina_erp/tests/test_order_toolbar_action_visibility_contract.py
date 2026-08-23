from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js"


class TestOrderToolbarActionVisibilityContract(unittest.TestCase):
    def test_draft_never_offers_return_to_draft(self) -> None:
        source = (PUBLIC / "door_cutting_order/core/order_lifecycle.js").read_text(encoding="utf-8")
        predicate = source.split("function canReturnToDraft", 1)[1].split(
            "function canCancelOrder", 1
        )[0]

        self.assertIn('"Draft", "Rejected", "Delivered", "Cancelled"', source)
        self.assertIn("NON_RETURNABLE_STATUSES.has(status)", predicate)
        self.assertIn('actionAllowed(context, "return_to_draft")', predicate)
        self.assertNotIn('|| can(frm, "return_order_to_draft")', predicate)

    def test_cancel_is_a_red_standalone_action(self) -> None:
        source = (PUBLIC / "door_cutting_order/core/order_lifecycle.js").read_text(encoding="utf-8")
        installer = source.split("function installButtons", 1)[1].split(
            "function loadContext", 1
        )[0]

        self.assertIn('LABELS.cancel', installer)
        self.assertIn('addClass("btn-danger")', installer)
        self.assertNotIn("ACTION_GROUP\n", installer)
        self.assertNotIn(",\n                ACTION_GROUP", installer)

    def test_previous_stage_button_requires_real_server_targets(self) -> None:
        source = (
            PUBLIC
            / "door_cutting_order"
            / "production"
            / "shop_floor_order_ux.js"
        ).read_text(encoding="utf-8")
        predicate = source.split("function canCheckRevertTargets", 1)[1].split(
            "function ensureRevertTargets", 1
        )[0]
        button = source.split("function addRevertButton", 1)[1].split(
            "function addDeliveryButtons", 1
        )[0]

        self.assertIn("NON_REVERTABLE_ORDER_STATUSES.has(status)", predicate)
        self.assertIn("frm.doc.current_production_stage", predicate)
        self.assertIn("get_revert_targets", source)
        self.assertIn("current && rows.length", button)
        self.assertLess(button.index("current && rows.length"), button.index("frm.add_custom_button"))

    def test_toolbar_never_hides_actions_and_stays_at_top_left(self) -> None:
        toolbar = (PUBLIC / "door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js").read_text(
            encoding="utf-8"
        )
        production = (
            PUBLIC
            / "door_cutting_order"
            / "production"
            / "shop_floor_order_ux.js"
        ).read_text(encoding="utf-8")
        lifecycle = (PUBLIC / "door_cutting_order/core/order_lifecycle.js").read_text(encoding="utf-8")

        self.assertNotIn("dco-actions-settling", toolbar)
        self.assertNotIn("toolbar-final-reveal", toolbar)
        self.assertNotIn(
            ".dco-actions-settling .custom-actions",
            toolbar,
        )
        self.assertIn("--dco-viewport-left-compensation", toolbar)
        self.assertIn("anchorActionsToViewportLeft(head)", toolbar)
        self.assertIn("Math.min(...visibleLefts)", toolbar)
        self.assertIn("right:auto!important", toolbar)
        self.assertIn("position:fixed!important", toolbar)
        self.assertIn("flex-wrap:nowrap!important", toolbar)
        self.assertIn("[0, 180]", toolbar)
        self.assertNotIn("[0, 80, 250, 650, 1200]", toolbar)
        self.assertNotIn("permissionVersion", production)
        self.assertIn(
            "frm.__almdinaProductionActionsKey === productionActionsKey(frm)",
            production,
        )
        self.assertIn("renderedOwned.every(label => expected.has(label))", production)
        installer = lifecycle.split("function installButtons", 1)[1].split(
            "function loadContext", 1
        )[0]
        self.assertNotIn("removeLifecycleButtons(frm);", installer)
        self.assertIn("ensureLifecycleButton", installer)

    def test_revision_actions_use_a_clear_group_name(self) -> None:
        source = (PUBLIC / "door_cutting_order/core/door_cutting_order_revision_ux.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('const REVISION_GROUP = __("نسخ الطلب")', source)
        self.assertIn('const LEGACY_LIFECYCLE_GROUP = __("دورة الطلب")', source)
        self.assertEqual(source.count('__("دورة الطلب")'), 1)


if __name__ == "__main__":
    unittest.main()
