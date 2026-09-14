from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
SAVE_USE_CASE = APP / "application" / "orders" / "process_order_save.py"
CONTROLLER = (
    APP / "doctype" / "door_cutting_order" / "door_cutting_order_controller.py"
)
JOB_SERVICE = APP / "services" / "cutting_plan_recalculation_job_service.py"
JOB_STORE = (
    APP / "infrastructure" / "frappe" / "system_plan_recalculation_job_store.py"
)
WORKSPACE_QUERY = APP / "services" / "cutting_plan_workspace_query_service.py"
JOB_JS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_recalculation_job.js"
)
MUTATION = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_mutation_impact_policy.js"
)
ASSETS = ROOT / "frontend_assets.py"


class TestSystemPlanRecalculationJobService(unittest.TestCase):
    def test_order_save_still_does_not_enqueue_or_run_the_optimizer(self) -> None:
        save = SAVE_USE_CASE.read_text(encoding="utf-8")
        controller = CONTROLLER.read_text(encoding="utf-8")
        on_update = controller.split("def on_update(self)", 1)[1].split(
            "def ensure_special_shapes_documented", 1
        )[0]

        self.assertIn("without touching Cutting Plan state", save)
        self.assertNotIn("enqueue", save)
        self.assertNotIn("recalculate_system_plan", save)
        self.assertNotIn("frappe.enqueue", on_update)
        self.assertNotIn("recalculate", on_update.lower())
        self.assertNotIn("enqueue_system_plan_recalculation", on_update)

    def test_job_service_reuses_plan_command_and_never_embeds_cost_in_realtime(self) -> None:
        service = JOB_SERVICE.read_text(encoding="utf-8")
        store = JOB_STORE.read_text(encoding="utf-8")

        self.assertIn("frappe.enqueue(", service)
        self.assertIn('queue="long"', service)
        self.assertIn("enqueue_after_commit=True", service)
        self.assertIn("recalculate_system_plan(order)", service)
        self.assertIn("require_cutting_plan_capability", service)
        self.assertIn("Capability.RECALCULATE_PLAN", service)
        self.assertIn("pending_rerun", service)
        self.assertNotIn("mdf_cost_usd", service)
        self.assertNotIn("total_cost_usd", service)
        self.assertNotIn("board_rate_usd", store)
        self.assertIn('"status": state.status', store)
        self.assertIn('"generation": int(state.generation or 0)', store)
        self.assertNotIn("total_cost_usd", store)

    def test_workspace_snapshot_overlays_progress_without_money(self) -> None:
        source = WORKSPACE_QUERY.read_text(encoding="utf-8")
        snapshot = source.split("def get_plan_workspace_snapshot", 1)[1]
        self.assertIn("overlay_background_recalculation(order.name)", snapshot)
        self.assertIn('"background_recalculation"', snapshot)
        for field in (
            '"board_rate_usd"',
            '"cutting_cost_per_board_usd"',
            '"mdf_cost_usd"',
            '"total_cost_usd"',
        ):
            self.assertNotIn(field, source)

    def test_client_job_owner_is_eager_non_blocking_and_skips_checkpoints(self) -> None:
        job = JOB_JS.read_text(encoding="utf-8")
        mutation = MUTATION.read_text(encoding="utf-8")
        assets = ASSETS.read_text(encoding="utf-8")

        self.assertIn("freeze: false", job)
        self.assertNotIn("freeze: true", job)
        self.assertIn("__almdina_preserve_edit_session_after_save", job)
        self.assertIn("__almdina_order_checkpoint_save_in_progress", job)
        self.assertIn("recalculate_plan", job)
        self.assertIn("frappe.realtime.on", job)
        self.assertIn("AlmdinaDocumentContext", job)
        self.assertIn("enqueueAfterSave(frm, impact)", mutation)
        self.assertNotIn("frappe.call", mutation)
        job_path = (
            "public/js/door_cutting_order/cutting_plan/"
            "door_cutting_order_plan_recalculation_job.js"
        )
        policy_path = (
            "public/js/door_cutting_order/order_entry/"
            "door_cutting_order_mutation_impact_policy.js"
        )
        self.assertLess(assets.index(job_path), assets.index(policy_path))


if __name__ == "__main__":
    unittest.main()
