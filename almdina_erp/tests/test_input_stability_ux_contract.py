from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_STABILITY = ROOT / "public" / "js" / "input_stability.js"
SAVE_RENDER_GUARD = (
    ROOT / "public" / "js" / "door_cutting_order_save_render_performance_ux.js"
)
HOOKS = ROOT / "hooks.py"
LEGACY_ORDER_FORM = (
    ROOT
    / "almdina_erp"
    / "doctype"
    / "door_cutting_order"
    / "door_cutting_order.js"
)


class TestInputStabilityUxContract(unittest.TestCase):
    def test_guard_is_loaded_app_wide_and_last_for_order_form(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")
        global_token = '"/assets/almdina_erp/js/input_stability.js"'
        doctype_token = '"public/js/input_stability.js"'

        self.assertIn(global_token, hooks)
        self.assertIn(doctype_token, hooks)
        self.assertGreater(
            hooks.index(doctype_token),
            hooks.index('"public/js/door_cutting_order_revision_ux.js"'),
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

    def test_arabic_composition_and_normal_typing_invalidate_old_responses(self) -> None:
        source = INPUT_STABILITY.read_text(encoding="utf-8")

        self.assertIn('document.addEventListener("focusin"', source)
        self.assertIn('document.addEventListener("beforeinput"', source)
        self.assertIn('document.addEventListener("compositionstart"', source)
        self.assertIn('document.addEventListener("compositionend"', source)
        self.assertIn("state.generation += 1", source)
        self.assertIn("state.composing = true", source)
        self.assertIn("state.composing = false", source)

    def test_stale_live_preview_cannot_write_back_over_user_input_or_another_order(self) -> None:
        source = INPUT_STABILITY.read_text(encoding="utf-8")

        self.assertIn("options.method !== PREVIEW_METHOD", source)
        self.assertIn("const requestGeneration = state.generation", source)
        self.assertIn("const requestIdentity = formIdentity(requestForm)", source)
        self.assertIn("state.generation !== requestGeneration", source)
        self.assertIn("activeElementBelongsToForm(requestForm)", source)
        self.assertIn("const documentChanged", source)
        self.assertIn("formIdentity(window.cur_frm) !== requestIdentity", source)
        self.assertIn("if (inputChanged || state.composing || editing || documentChanged)", source)

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

    def test_obsolete_live_preview_handlers_are_removed_for_all_order_inputs(self) -> None:
        source = INPUT_STABILITY.read_text(encoding="utf-8")

        for fieldname in (
            "board_description",
            "customer",
            "width_cm",
            "length_cm",
            "qty",
            "notes",
            "edge_type",
        ):
            self.assertIn(f'"{fieldname}"', source)

        self.assertIn("removeDoorOrderLivePreviewHandlers", source)
        self.assertIn('source.includes("schedule_recalculate")', source)

    def test_contract_covers_the_recorded_failure_mechanism(self) -> None:
        legacy = LEGACY_ORDER_FORM.read_text(encoding="utf-8")
        guard = INPUT_STABILITY.read_text(encoding="utf-8")

        # The historical form still shows why the bug occurred: preview writes
        # source fields back and refreshes the whole child grid asynchronously.
        self.assertIn('"board_description"', legacy)
        self.assertIn('frm.refresh_field("pieces")', legacy)
        self.assertIn("schedule_recalculate(frm)", legacy)

        # The central policy must guard both mechanisms until that legacy file is
        # removed during the planned frontend consolidation.
        self.assertIn("installPreviewResponseGuard", guard)
        self.assertIn("installRefreshFieldGuard", guard)
        self.assertIn("removeDoorOrderLivePreviewHandlers", guard)


if __name__ == "__main__":
    unittest.main()
