from __future__ import annotations

import json
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    CANCELLED,
    CuttingPlanLifecycleError,
    cancel_approval_transition,
)


ROOT = Path(__file__).resolve().parents[1]
DCO = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
CUTTING_PLAN_DOCTYPE = ROOT / "almdina_erp" / "doctype" / "cutting_plan" / "cutting_plan.py"
MANIFEST = ROOT / "frontend_assets.py"
REGISTRY = ROOT / "public" / "js" / "door_cutting_order" / "core" / "door_cutting_order_workspace_asset_registry.js"
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
CONTEXT = CUTTING_PLAN / "door_cutting_order_plan_context_actions_ux.js"
TABS = CUTTING_PLAN / "door_cutting_order_plan_tabs_ux.js"
WORKSPACE_API = CUTTING_PLAN / "door_cutting_order_plan_workspace_api.js"
SETTINGS_SUMMARY = CUTTING_PLAN / "door_cutting_order_plan_settings_summary_ux.js"
SECURE_EXPORT = CUTTING_PLAN / "secure_dxf_export.js"
DXF_SERVICE = ROOT / "almdina_erp" / "services" / "dxf_export_service.py"
CANCEL_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_plan_approval_cancellation_service.py"
APPROVAL_BOUNDARY = ROOT / "almdina_erp" / "services" / "drawing_approval_service.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestPlanContextualActionsUI(unittest.TestCase):
    def test_current_result_summary_is_removed_from_doctype(self) -> None:
        payload = json.loads(source(DCO))
        fieldnames = [field.get("fieldname") for field in payload["fields"]]

        self.assertNotIn("plan_result_section", payload["field_order"])
        self.assertNotIn("plan_controls_intro", payload["field_order"])
        self.assertNotIn("plan_result_section", fieldnames)
        self.assertNotIn("plan_controls_intro", fieldnames)

    def test_context_actions_load_before_tabs_and_live_between_tabs_and_plan(self) -> None:
        manifest = source(MANIFEST)
        registry = source(REGISTRY)
        tabs = source(TABS)
        context_asset = "door_cutting_order_plan_context_actions_ux.js"
        tabs_asset = "door_cutting_order_plan_tabs_ux.js"

        self.assertNotIn(context_asset, manifest)
        self.assertNotIn(tabs_asset, manifest)
        self.assertEqual(registry.count(context_asset), 1)
        self.assertEqual(registry.count(tabs_asset), 1)
        self.assertLess(registry.index(context_asset), registry.index(tabs_asset))
        self.assertIn('class="dco-plan-context-actions-host"', tabs)
        self.assertIn("renderContextActions(frm, wrapper)", tabs)
        self.assertLess(
            tabs.index("buildTabBar(frm, activeTab, tabs)"),
            tabs.index('class="dco-plan-context-actions-host"'),
        )
        self.assertLess(
            tabs.index('class="dco-plan-context-actions-host"'),
            tabs.index('class="dco-plan-tab-content"'),
        )

    def test_active_plan_owns_approval_replacement_and_document_tools(self) -> None:
        context = source(CONTEXT)

        for label in (
            "اعتماد خطة النظام",
            "اعتماد الخطة المرفوعة",
            "استبدال الخطة المعتمدة بخطة النظام",
            "استبدال الخطة المعتمدة بالخطة المرفوعة",
            "إلغاء اعتماد الخطة",
            "رفع خطة DXF",
            "استبدال الخطة المرفوعة",
            "تصدير DXF",
            "طباعة",
        ):
            with self.subTest(label=label):
                self.assertIn(label, context)

        self.assertIn("frm.__almdina_active_plan_tab", context)
        self.assertIn("rowForTab(frm, tab", context)
        self.assertIn("controls.runApproval(frm)", context)
        self.assertIn("api.cancelApproval(frm.doc.name)", context)
        self.assertIn("tabs.printActivePlan(frm)", context)
        self.assertIn("export_order_dxf(frm.doc.name, activeTab(frm))", context)
        self.assertIn("upload_production_dxf(frm)", context)
        self.assertNotIn("frappe.call", context)

    def test_legacy_general_action_surface_is_edit_only(self) -> None:
        context = source(CONTEXT)

        self.assertIn("field.$wrapper.toggle(Boolean(isEditing(frm)))", context)
        self.assertIn(
            '[data-fieldname="plan_control_actions"] .dco-plan-document-actions',
            context,
        )
        self.assertIn(
            '[data-fieldname="plan_control_actions"] .dco-approve-cutting-plan',
            context,
        )
        self.assertIn(
            '[data-fieldname="plan_control_actions"]:has(.dco-plan-settings-editor)',
            context,
        )
        self.assertIn("almdina_edit_session_changed(frm) { refresh(frm); }", context)

    def test_optimizer_time_limit_has_operator_help(self) -> None:
        summary = source(SETTINGS_SUMMARY)
        self.assertIn("TIME_LIMIT_HELP", summary)
        self.assertIn("أقصى مدة يمنحها النظام لمحرك التحسين للبحث عن توزيع أفضل", summary)
        self.assertIn('cursor:help', summary)
        self.assertIn('title=', summary)

    def test_settings_summary_does_not_reparent_the_shared_tab_toolbar(self) -> None:
        summary = source(SETTINGS_SUMMARY)

        self.assertNotIn("PLAN_TOOLBAR_SELECTOR", summary)
        self.assertIn("function attachPlanToolbar(frm, summary)", summary)
        self.assertIn("function restorePlanToolbar(frm)", summary)
        self.assertIn("restorePlanToolbar(frm);", summary)
        self.assertNotIn("header.appendChild(toolbar)", summary)
        self.assertNotIn('toolbar.getAttribute("data-editing")', summary)
        self.assertIn("function attachPlanToolbar(frm, summary) {\n        return true;", summary)

    def test_dxf_export_is_explicitly_scoped_to_active_plan_source(self) -> None:
        frontend = source(SECURE_EXPORT)
        backend = source(DXF_SERVICE)

        self.assertIn("function exportOrderDxf(orderName, planSource = null)", frontend)
        self.assertIn("args.plan_source = planSource", frontend)
        self.assertIn(
            "almdina_erp.almdina_erp.services.dxf_export_service.get_validated_dxf_plan",
            frontend,
        )
        self.assertIn("def _saved_plan_for_source(order: Any, plan_source: str | None)", backend)
        self.assertIn("source_type=SYSTEM, status=DRAFT", backend)
        self.assertIn("source_type=UPLOADED_DXF, status=DRAFT", backend)
        self.assertIn("approved_plan_for_order(order)", backend)
        self.assertIn("plan_source: str | None = None", backend)

    def test_approval_cancellation_is_a_domain_command_not_a_ui_mutation(self) -> None:
        api = source(WORKSPACE_API)
        boundary = source(APPROVAL_BOUNDARY)
        service = source(CANCEL_SERVICE)
        context = source(CONTEXT)

        self.assertIn("CANCEL_APPROVAL_METHOD", api)
        self.assertIn("cancel_production_plan_approval", api)
        self.assertIn("def cancel_production_plan_approval", boundary)
        self.assertIn("cancel_approved_order_plan(order)", boundary)
        self.assertIn("Capability.APPROVE_DXF", service)
        self.assertIn("cancel_approval_transition", service)
        self.assertIn('"approved_plan"', service)
        self.assertIn("repository.save_document(plan, allow_status_transition=True)", service)
        self.assertNotIn("frappe.db.set_value", context)

    def test_domain_cancel_transition_preserves_immutable_history(self) -> None:
        self.assertEqual(cancel_approval_transition(APPROVED), (APPROVED, CANCELLED))
        for status in ("Draft", "Superseded", "Cancelled", ""):
            with self.subTest(status=status):
                with self.assertRaises(CuttingPlanLifecycleError):
                    cancel_approval_transition(status)

    def test_revision_lineage_survives_replacement_and_cancellation(self) -> None:
        doctype = source(CUTTING_PLAN_DOCTYPE)
        parent_guard = doctype.split("def _validate_revision_parent(self)", 1)[1].split(
            "\n    def _validate_working_settings", 1
        )[0]

        self.assertIn("IMMUTABLE_STATUSES = {APPROVED, SUPERSEDED, CANCELLED}", doctype)
        self.assertIn("if self.is_new() and parent.status != APPROVED", parent_guard)
        self.assertIn(
            "if not self.is_new() and parent.status not in IMMUTABLE_STATUSES",
            parent_guard,
        )
        self.assertIn("cint(self.revision) <= cint(parent.revision)", parent_guard)


if __name__ == "__main__":
    unittest.main()
