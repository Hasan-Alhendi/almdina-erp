from __future__ import annotations

import json
import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCTYPE_PATH = (
    ROOT
    / "almdina_erp"
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.json"
)
HOOKS_PATH = ROOT / "almdina_erp" / "hooks.py"
PATCHES_PATH = ROOT / "almdina_erp" / "patches.txt"
REVISION_SERVICE_PATH = (
    ROOT
    / "almdina_erp"
    / "almdina_erp"
    / "services"
    / "order_revision_service.py"
)


class TestOrderRevisionActivationContract(unittest.TestCase):
    def test_doctype_exposes_revision_activation_metadata(self) -> None:
        payload = json.loads(DOCTYPE_PATH.read_text(encoding="utf-8"))
        fields = {field["fieldname"]: field for field in payload["fields"]}

        state = fields["revision_state"]
        self.assertEqual(state["default"], "Current")
        self.assertEqual(
            state["options"].splitlines(),
            ["Current", "Pending Activation", "Superseded"],
        )
        self.assertEqual(fields["revision_activated_by"]["options"], "User")
        self.assertEqual(fields["revision_activated_on"]["fieldtype"], "Datetime")

    def test_remote_approval_and_dispatch_use_revision_boundaries(self) -> None:
        hooks = runpy.run_path(str(HOOKS_PATH))
        overrides = hooks["override_whitelisted_methods"]

        self.assertEqual(
            overrides[
                "almdina_erp.almdina_erp.services.cutting_plan_service.approve_order"
            ],
            "almdina_erp.almdina_erp.services.order_approval_service.approve_order",
        )
        self.assertEqual(
            overrides[
                "almdina_erp.almdina_erp.services.shop_floor_service.dispatch_order"
            ],
            "almdina_erp.almdina_erp.services.order_dispatch_service.dispatch_order",
        )
        self.assertEqual(
            overrides[
                "almdina_erp.almdina_erp.services.shop_floor_commands.dispatch_order"
            ],
            "almdina_erp.almdina_erp.services.order_dispatch_service.dispatch_order",
        )

    def test_new_revision_is_created_pending_activation(self) -> None:
        source = REVISION_SERVICE_PATH.read_text(encoding="utf-8")
        self.assertIn('"revision_state": RevisionState.PENDING_ACTIVATION', source)
        self.assertIn('"revision_activated_by": None', source)
        self.assertIn('"revision_activated_on": None', source)

    def test_migration_backfill_is_registered(self) -> None:
        patches = PATCHES_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "almdina_erp.patches.v1_0.backfill_revision_activation_state",
            patches,
        )


if __name__ == "__main__":
    unittest.main()
