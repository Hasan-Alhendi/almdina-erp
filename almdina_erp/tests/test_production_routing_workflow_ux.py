from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "almdina_erp" / "page" / "factory_master_data" / "factory_master_data.js"
CSS = ROOT / "public" / "css" / "factory_routing_workflow.css"
APPLICATION = (
    ROOT
    / "almdina_erp"
    / "application"
    / "factory"
    / "production_routing_management.py"
)
REPOSITORY = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "production_routing_management_repository.py"
)


class TestProductionRoutingWorkflowUx(unittest.TestCase):
    def test_page_is_a_dedicated_workflow_editor_not_a_generic_doctype_form(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("get_production_routing_console", source)
        self.assertIn("save_production_routing", source)
        self.assertIn("set_production_routing_disabled", source)
        self.assertIn("delete_production_routing", source)
        self.assertNotIn("frappe.new_doc", source)
        self.assertNotIn("Edge Banding Type", source)
        self.assertNotIn("edge_types", source)

    def test_editor_supports_story_reordering_templates_and_concurrency(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("Workflow Story", source)
        self.assertIn("prw-stage-library", source)
        self.assertIn("dragstart.prw", source)
        self.assertIn("prw-move-stage", source)
        self.assertIn("expected_modified", source)
        self.assertIn("operational_roles", source)
        self.assertIn("is_planning_stage", source)
        self.assertIn("completed.workingId === editor.workingId", source)
        self.assertIn("editor.expected_modified = String(saved.modified)", source)

    def test_stage_library_interaction_contract_is_one_click_and_read_only(self) -> None:
        source = PAGE.read_text(encoding="utf-8")

        self.assertIn("＋ ${__(\"إضافة مرحلة\")}", source)
        self.assertNotIn("إضافة مكتبة جديدة", source)
        self.assertNotIn("إضافة مرحلة مخصصة", source)
        self.assertIn("prw-library-card-actions", source)
        self.assertIn("prw-edit-stage-definition", source)
        self.assertIn("prw-toggle-stage-definition", source)
        self.assertIn("prw-delete-stage-definition", source)
        self.assertIn("event.stopPropagation()", source)
        self.assertIn('role=\"button\" tabindex=\"0\"', source)
        self.assertIn('event.key !== \"Enter\" && event.key !== \" \"', source)
        self.assertIn('message: __(\"المرحلة موجودة بالفعل\")', source)
        self.assertNotIn('data-stage-field=\"stage_type\"', source)
        self.assertNotIn('data-stage-field=\"department_label\"', source)
        self.assertIn("prw-stage-identity", source)
        self.assertIn("libraryMutationPending", source)
        self.assertIn("beginLibraryMutation", source)

    def test_styles_are_scoped_responsive_and_accessible(self) -> None:
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".prw-shell", css)
        self.assertIn(".prw-editor-layout", css)
        self.assertIn(".prw-story-row.is-drag-over", css)
        self.assertIn("@media (max-width: 640px)", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)

    def test_application_use_case_is_framework_independent(self) -> None:
        source = APPLICATION.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertIn("ProductionRoutingManagementPort", source)
        self.assertIn("ProductionRoute", source)

    def test_frappe_repository_is_versioned_atomic_and_avoids_n_plus_one(self) -> None:
        source = REPOSITORY.read_text(encoding="utf-8")
        self.assertIn("for update", source.lower())
        self.assertIn("_assert_version", source)
        self.assertIn("ignore_permissions=True", source)
        self.assertIn('group_by="production_path"', source)
        self.assertIn('{"COUNT": "name", "as": "order_count"}', source)
        self.assertNotIn('"count(name) as order_count"', source)
        self.assertEqual(source.count('"Production Routing Stage"'), 1)


if __name__ == "__main__":
    unittest.main()
