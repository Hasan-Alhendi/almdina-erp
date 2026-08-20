from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
PUBLIC = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"


class TestPlanPreviewSessionExactCommit(unittest.TestCase):
    def test_application_preview_contract_is_framework_neutral(self) -> None:
        source = (
            APP / "application" / "cutting" / "plan_preview_session.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertIn("CuttingPlanPreviewSession", source)
        self.assertIn("optimizer_settings_fingerprint", source)
        self.assertIn("input_fingerprint", source)
        self.assertIn("source_plan_modified", source)

    def test_preview_store_is_short_lived_and_single_use(self) -> None:
        source = (
            APP / "infrastructure" / "frappe" / "cutting_plan_preview_store.py"
        ).read_text(encoding="utf-8")
        self.assertIn("expires_in_sec=self.ttl_seconds", source)
        self.assertIn("def consume", source)
        consume = source[source.index("def consume"):source.index("def discard")]
        self.assertIn("get_value", consume)
        self.assertIn("delete_value", consume)
        self.assertLess(consume.index("get_value"), consume.index("delete_value"))

    def test_preview_calculates_without_persisting_and_commit_does_not_recalculate(self) -> None:
        path = APP / "services" / "cutting_plan_preview_service.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        preview = ast.unparse(functions["preview_cutting_plan"])
        commit = ast.unparse(functions["commit_cutting_plan_preview"])

        self.assertIn("calculate_system_plan(order, preview_plan)", preview)
        self.assertNotIn("save_document", preview)
        self.assertNotIn(".save(", preview)
        self.assertNotIn(".insert(", preview)

        self.assertIn("apply_exact_system_preview", commit)
        self.assertIn("repository.save_document(plan)", commit)
        self.assertNotIn("calculate_system_plan", commit)
        self.assertNotIn("optimize_order_plan", commit)
        self.assertIn("session.source_plan_modified", commit)
        self.assertIn("session.user != frappe.session.user", commit)

    def test_exact_commit_recomputes_input_fingerprint_and_rejects_invalid_geometry(self) -> None:
        source = (
            APP
            / "infrastructure"
            / "frappe"
            / "cutting_plan_preview_commit.py"
        ).read_text(encoding="utf-8")
        self.assertIn("plan_input_fingerprint(order, plan)", source)
        self.assertIn("live_fingerprint != expected_input_fingerprint", source)
        self.assertIn("apply_calculation_outcome", source)
        self.assertIn('not validation.get("is_valid")', source)
        self.assertNotIn("_apply_snapshot", source)
        self.assertNotIn("calculate_system_plan", source)

    def test_transport_exposes_preview_and_commit_without_ui_logic(self) -> None:
        source = (PUBLIC / "door_cutting_order_plan_workspace_api.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("PREVIEW_METHOD", source)
        self.assertIn("COMMIT_PREVIEW_METHOD", source)
        self.assertIn("function preview(orderName, settings)", source)
        self.assertIn("function commitPreview(orderName, previewId)", source)
        self.assertNotIn("querySelector", source)
        self.assertNotIn("fields_dict", source)

    def test_frontend_preview_state_is_separate_from_canonical_workspace(self) -> None:
        source = (PUBLIC / "door_cutting_order_plan_preview_session.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("__almdinaPlanPreviewSession", source)
        self.assertIn("almdina:plan-preview-updated", source)
        self.assertIn("api.preview(frm.doc.name", source)
        self.assertIn("api.commitPreview(frm.doc.name, previewId)", source)
        self.assertIn("function isCommittable(frm)", source)
        self.assertIn('String(validation.status || "") === "Valid"', source)
        self.assertNotIn("AlmdinaWorkspaceStore", source)
        self.assertNotIn("refresh_plan_controls", source)

    def test_edit_controller_requires_valid_preview_and_invalidates_on_change(self) -> None:
        source = (PUBLIC / "door_cutting_order_plan_preview_edit_ux.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("owner.isCommittable(frm)", source)
        self.assertIn("button.disabled = !allowed", source)
        self.assertIn("owner.invalidate(frm)", source)
        self.assertIn("await owner.commit(frm)", source)
        self.assertNotIn("legacy.saveEditing(frm)", source)
        self.assertIn("المعاينة الحالية لم تنجح في التحقق الهندسي", source)
        self.assertNotIn("<style", source)
        self.assertNotIn("renderer.build", source)

    def test_presenter_owns_preview_and_stale_visuals_only(self) -> None:
        source = (PUBLIC / "door_cutting_order_plan_preview_presenter.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("function renderPersistedEditingState(frm, status)", source)
        self.assertIn("function renderPreviewPlan(frm, previewState, committable)", source)
        self.assertIn("المعاينة السابقة أصبحت قديمة", source)
        self.assertIn("الخطة المعروضة أدناه هي الخطة المحفوظة", source)
        self.assertIn("معاينة غير صالحة للحفظ", source)
        self.assertNotIn("frappe.call", source)
        self.assertNotIn("api.preview", source)
        self.assertNotIn("api.commitPreview", source)

    def test_plan_controls_are_the_single_preview_command_owner(self) -> None:
        controls = (PUBLIC / "door_cutting_order_plan_controls_ux.js").read_text(
            encoding="utf-8"
        )
        controller = (PUBLIC / "door_cutting_order_plan_preview_edit_ux.js").read_text(
            encoding="utf-8"
        )
        edit_session = (PUBLIC / "door_cutting_order_plan_edit_session_ux.js").read_text(
            encoding="utf-8"
        )

        # The first persisted System Plan is an explicit bootstrap command and
        # must not require an optimizer edit session. Once a System Draft exists,
        # recalculation returns to Preview -> review -> exact commit semantics.
        self.assertIn("(firstPlan || workspaceEditing(frm))", controls)
        self.assertIn('typeof transport.bootstrapPlan === "function"', controls)
        self.assertIn("await transport.bootstrapPlan(frm.doc.name, settings)", controls)
        self.assertIn('typeof previews.preview === "function"', controls)
        self.assertIn("await previews.preview(frm, settings)", controls)
        self.assertIn('"almdina:plan-preview-updated"', controls)
        self.assertNotIn("transport.recalculate(frm.doc.name, settings)", controls)
        self.assertNotIn(".dco-recalculate-plan", controller)
        self.assertNotIn("bindPreviewButton", controller)

        blocked = edit_session[
            edit_session.index("const BLOCKED_PLAN_ACTIONS"):
            edit_session.index("const ORIGINAL_DISABLED_ATTR")
        ]
        self.assertNotIn(".dco-recalculate-plan", blocked)
        self.assertIn(".dco-approve-cutting-plan", blocked)

    def test_preview_assets_load_at_the_correct_architecture_boundaries(self) -> None:
        manifest = (ROOT / "frontend_assets.py").read_text(encoding="utf-8")
        api = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js"
        state = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js"
        preview = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_session.js"
        edit = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_edit_session_ux.js"
        presenter = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_presenter.js"
        preview_edit = "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_edit_ux.js"
        page = "public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js"

        for asset in (preview, presenter, preview_edit):
            self.assertEqual(manifest.count(asset), 1)
        self.assertLess(manifest.index(api), manifest.index(state))
        self.assertLess(manifest.index(state), manifest.index(preview))
        self.assertLess(manifest.index(edit), manifest.index(presenter))
        self.assertLess(manifest.index(presenter), manifest.index(preview_edit))
        self.assertLess(manifest.index(preview_edit), manifest.index(page))


if __name__ == "__main__":
    unittest.main()
