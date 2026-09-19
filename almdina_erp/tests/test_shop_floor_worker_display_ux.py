from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "production"
    / "shop_floor_order_ux.js"
)
INBOX_DIALOGS = ROOT / "public" / "js" / "shop_floor_inbox" / "dialogs.js"
QUICK_ACTIONS = ROOT / "public" / "js" / "shop_floor_quick_actions.js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestShopFloorWorkerDisplayUx(unittest.TestCase):
    def test_order_tab_strip_renders_worker_name_not_stored_user_id(self) -> None:
        text = source(PRODUCTION_UX)
        strip = text.split("function renderTrackingStrip(frm) {", 1)[1].split(
            "function applyShopFloorPresentation", 1
        )[0]

        self.assertIn("currentAssigneeDisplayName(frm.doc.current_assignee)", strip)
        self.assertNotIn('frm.doc.current_assignee || "-"', strip)
        self.assertIn("hydrateCurrentAssigneeName(frm)", strip)
        self.assertIn("function currentAssigneeDisplayName(userId)", text)
        self.assertIn("frappe.user_info", text)

    def test_stage_assignment_pickers_show_name_without_email(self) -> None:
        production = source(PRODUCTION_UX)
        inbox = source(INBOX_DIALOGS)
        quick_actions = source(QUICK_ACTIONS)

        self.assertIn("function workerDisplayName(worker)", production)
        self.assertIn("function workerSelectOptions(workers)", production)
        self.assertNotIn("${worker.full_name} — ${worker.name}", production)
        self.assertNotIn("${worker.full_name} (${worker.name})", production)
        self.assertNotIn("labels.get(values.worker)", production)
        self.assertIn("assignee: values.worker", production)

        self.assertNotIn("${worker.full_name} (${worker.name})", inbox)
        self.assertIn("fullName && fullName !== id ? fullName", inbox)

        self.assertNotIn("`${fullName} (${value})`", quick_actions)
        self.assertNotIn('meta: fullName && fullName !== value ? value : ""', quick_actions)
        self.assertIn("label: displayName", quick_actions)
        self.assertIn('meta: ""', quick_actions)


if __name__ == "__main__":
    unittest.main()
