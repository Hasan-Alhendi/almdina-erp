from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_STABILITY = ROOT / "public" / "js" / "input_stability.js"
SAVE_RENDER_GUARD = (
    ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_save_render_performance_ux.js"
)
MANIFEST = ROOT / "frontend_assets.py"
CANONICAL_ORDER_FORM = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.js"
)


class TestInputStabilityUxContract(unittest.TestCase):
    def test_guard_is_loaded_app_wide_and_last_for_order_form(self) -> None:
        manifest = MANIFEST.read_text(encoding="utf-8")
        global_token = '"/assets/almdina_erp/js/input_stability.js"'
        doctype_token = '"public/js/input_stability.js"'

        self.assertIn(global_token, manifest)
        self.assertIn(doctype_token, manifest)
        self.assertGreater(
            manifest.index(doctype_token),
            manifest.index('"public/js/door_cutting_order/core/door_cutting_order_revision_ux.js"'),
        )

    def test_every_active_control_is_protected_from_async_refresh(self) -> None:
        source = INPUT_STABILITY.read_text(encoding="utf-8")

        self.assertIn("frappe.ui.form.Form.prototype", source)
        self.assertIn("prototype.refresh_field = function inputSafeRefreshField", source)
        self.assertIn("fieldContainsActiveElement(this, name)", source)
        self.assertIn("_almdinaDeferredFieldRefreshes", source)
        self.assertIn('wrapper.addEventListener("focusout"', source)
        self.assertIn("originalRefreshField.call(form, fieldname)", source)

    def test_refresh_protection_never_blocks_a_different_order(self) -> None:
        source = INPUT_STABILITY.read_text(encoding="utf-8")

        self.assertIn("function formIdentity(form)", source)
        self.assertIn("function synchronizeFormIdentity(form)", source)
        self.assertIn("previous !== identity", source)
        self.assertIn("form._almdinaDeferredFieldRefreshes.clear()", source)
        self.assertIn("dataset.almdinaFormIdentity", source)
        self.assertIn("activeIdentity === currentIdentity", source)
        self.assertIn("form._almdinaDeferredRefreshIdentity !== currentIdentity", source)

    def test_focus_identity_is_tracked_without_global_keystroke_hooks(self) -> None:
        source = INPUT_STABILITY.read_text(encoding="utf-8")

        self.assertIn('document.addEventListener("focusin"', source)
        self.assertIn("rememberEditingIdentity(event.target)", source)
        self.assertNotIn('document.addEventListener("beforeinput"', source)
        self.assertNotIn('document.addEventListener("compositionstart"', source)
        self.assertNotIn("state.generation", source)
        self.assertNotIn("state.composing", source)

    def test_input_guard_does_not_monkey_patch_network_calls(self) -> None:
        source = INPUT_STABILITY.read_text(encoding="utf-8")

        self.assertNotIn("PREVIEW_METHOD", source)
        self.assertNotIn("installPreviewResponseGuard", source)
        self.assertNotIn("frappe.call =", source)
        self.assertNotIn("_almdinaInputSafePatched", source)

    def test_render_optimizations_are_scoped_to_the_current_order(self) -> None:
        source = SAVE_RENDER_GUARD.read_text(encoding="utf-8")

        self.assertIn("wrapper._dcoFastHtmlGuardForm = frm", source)
        self.assertIn("wrapper._dcoCostHtmlGuardForm = frm", source)
        self.assertIn("root._dcoDeferredRenderForm = frm", source)
        self.assertIn("function htmlBelongsToForm(frm, value)", source)
        self.assertIn("if (!htmlBelongsToForm(currentFrm, value)) return this", source)
        self.assertIn("function costHtmlOrderName(value)", source)
        self.assertIn("incomingName !== currentName", source)
        self.assertIn("existingName === currentName", source)
        self.assertIn("tagCostShell", source)

    def test_guard_does_not_inspect_frappe_private_handler_registry(self) -> None:
        source = INPUT_STABILITY.read_text(encoding="utf-8")

        self.assertNotIn("frappe.ui.form.handlers", source)
        self.assertNotIn("removeDoorOrderLivePreviewHandlers", source)
        self.assertNotIn("Function.prototype.toString", source)

    def test_recorded_preview_failure_mechanism_has_been_removed(self) -> None:
        canonical = CANONICAL_ORDER_FORM.read_text(encoding="utf-8")
        guard = INPUT_STABILITY.read_text(encoding="utf-8")

        self.assertNotIn("preview_door_cutting_order", canonical)
        self.assertNotIn('frm.refresh_field("pieces")', canonical)
        self.assertNotIn("schedule_recalculate", canonical)
        self.assertNotIn("frappe.ui.form.on", canonical)
        self.assertIn("installRefreshFieldGuard", guard)


if __name__ == "__main__":
    unittest.main()
