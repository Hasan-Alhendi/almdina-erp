"""USE_BOARD_EDITOR is an independent Cutting Plan capability.

It is assignable via Permission Matrix, independent of EDIT_OPTIMIZER_SETTINGS,
and required by every Board Editor backend entry point.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.cutting.board_editor_draft_review import (
    draft_review_allowed,
)
from almdina_erp.almdina_erp.application.cutting.board_editor_draft_save import (
    draft_write_allowed,
)
from almdina_erp.almdina_erp.application.cutting.board_editor_plan_create import (
    create_write_allowed,
)
from almdina_erp.almdina_erp.application.security.business_capability_state import (
    normalize_business_capability_state,
)
from almdina_erp.almdina_erp.application.security.permission_matrix import (
    capability_catalog_payload,
    normalize_capability_state,
)
from almdina_erp.almdina_erp.application.security.supporting_doctype_permissions import (
    supporting_standard_permission_projection,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    CAPABILITY_CATALOG,
    CUTTING_PLAN_DOCTYPE,
    Capability,
    capability_definition,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
PUBLIC = ROOT / "public"
TRANSLATIONS = ROOT / "translations" / "ar.csv"


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class UseBoardEditorCatalogTests(unittest.TestCase):
    def test_capability_is_in_cutting_plan_catalog(self) -> None:
        definition = capability_definition(Capability.USE_BOARD_EDITOR)
        self.assertEqual(definition.key, "use_board_editor")
        self.assertEqual(definition.permission_type, "use_board_editor")
        self.assertEqual(definition.applies_to, CUTTING_PLAN_DOCTYPE)
        self.assertEqual(definition.category, "cutting_plan")
        self.assertTrue(definition.custom)
        self.assertEqual(
            CAPABILITY_CATALOG[Capability.USE_BOARD_EDITOR].permission_type,
            "use_board_editor",
        )

    def test_presentation_appears_in_cutting_plan_group(self) -> None:
        groups = capability_catalog_payload()
        plan_group = next(group for group in groups if group["key"] == "cutting_plan")
        keys = [item["key"] for item in plan_group["capabilities"]]
        self.assertIn(Capability.USE_BOARD_EDITOR, keys)
        editor = next(
            item
            for item in plan_group["capabilities"]
            if item["key"] == Capability.USE_BOARD_EDITOR
        )
        self.assertEqual(editor["label"], "Use Board Editor")
        self.assertEqual(editor["risk"], "sensitive")
        self.assertIn("board editor", editor["description"].lower())
        optimizer_index = keys.index(Capability.EDIT_OPTIMIZER_SETTINGS)
        editor_index = keys.index(Capability.USE_BOARD_EDITOR)
        self.assertEqual(editor_index, optimizer_index + 1)

    def test_arabic_labels_exist(self) -> None:
        text = TRANSLATIONS.read_text(encoding="utf-8")
        self.assertIn("Use Board Editor,استخدام محرر الألواح", text)
        self.assertIn(
            "You do not have permission to use the board editor.,"
            "ليست لديك صلاحية استخدام محرر الألواح.",
            text,
        )


class UseBoardEditorIndependenceTests(unittest.TestCase):
    def test_use_board_editor_implies_plan_view_only(self) -> None:
        state = normalize_capability_state({Capability.USE_BOARD_EDITOR: True})
        self.assertTrue(state[Capability.USE_BOARD_EDITOR])
        self.assertTrue(state[Capability.VIEW_CUTTING_PLAN])
        self.assertTrue(state[Capability.VIEW_ORDERS])
        self.assertFalse(state[Capability.EDIT_OPTIMIZER_SETTINGS])
        self.assertFalse(state[Capability.RECALCULATE_PLAN])
        self.assertFalse(state[Capability.APPROVE_DXF])
        self.assertFalse(state[Capability.EXPORT_DXF])
        self.assertFalse(state[Capability.EDIT_ORDER])
        self.assertFalse(state[Capability.MANAGE_PERMISSIONS])

        business = normalize_business_capability_state(
            {Capability.USE_BOARD_EDITOR: True}
        )
        self.assertTrue(business[Capability.USE_BOARD_EDITOR])
        self.assertFalse(business[Capability.EDIT_OPTIMIZER_SETTINGS])
        self.assertFalse(business[Capability.RECALCULATE_PLAN])
        self.assertFalse(business[Capability.APPROVE_DXF])

    def test_edit_optimizer_does_not_grant_board_editor(self) -> None:
        state = normalize_capability_state({Capability.EDIT_OPTIMIZER_SETTINGS: True})
        self.assertTrue(state[Capability.EDIT_OPTIMIZER_SETTINGS])
        self.assertTrue(state[Capability.RECALCULATE_PLAN])
        self.assertFalse(state[Capability.USE_BOARD_EDITOR])

    def test_view_plan_alone_does_not_grant_board_editor(self) -> None:
        state = normalize_capability_state(
            {
                Capability.VIEW_CUTTING_PLAN: True,
                Capability.VIEW_SYSTEM_CUTTING_PLAN: True,
            }
        )
        self.assertFalse(state[Capability.USE_BOARD_EDITOR])

    def test_revoking_board_editor_leaves_optimizer_untouched(self) -> None:
        state = normalize_capability_state(
            {
                Capability.EDIT_OPTIMIZER_SETTINGS: True,
                Capability.USE_BOARD_EDITOR: False,
            }
        )
        self.assertTrue(state[Capability.EDIT_OPTIMIZER_SETTINGS])
        self.assertFalse(state[Capability.USE_BOARD_EDITOR])

    def test_empty_matrix_does_not_auto_grant_board_editor(self) -> None:
        state = normalize_capability_state({})
        self.assertFalse(state[Capability.USE_BOARD_EDITOR])

    def test_cutting_plan_create_projection_includes_board_editor(self) -> None:
        projection = supporting_standard_permission_projection(
            CUTTING_PLAN_DOCTYPE,
            {Capability.USE_BOARD_EDITOR: True},
        )
        self.assertTrue(projection["read"])
        self.assertTrue(projection["create"])
        self.assertTrue(projection["write"])
        self.assertFalse(projection["delete"])

        optimizer_only = supporting_standard_permission_projection(
            CUTTING_PLAN_DOCTYPE,
            {Capability.EDIT_OPTIMIZER_SETTINGS: True},
        )
        self.assertTrue(optimizer_only["create"])
        view_only = supporting_standard_permission_projection(
            CUTTING_PLAN_DOCTYPE,
            {
                Capability.VIEW_CUTTING_PLAN: True,
                Capability.VIEW_SYSTEM_CUTTING_PLAN: True,
            },
        )
        self.assertTrue(view_only["read"])
        self.assertFalse(view_only["create"])
        self.assertFalse(view_only["write"])


class UseBoardEditorGateTests(unittest.TestCase):
    def test_application_gates_require_capability(self) -> None:
        self.assertFalse(
            draft_write_allowed(
                has_edit_capability=False,
                has_plan_view=True,
                order_status="Draft",
            )
        )
        self.assertTrue(
            draft_write_allowed(
                has_edit_capability=True,
                has_plan_view=True,
                order_status="Draft",
            )
        )
        self.assertFalse(
            draft_review_allowed(
                has_board_editor_capability=False,
                has_plan_view=True,
            )
        )
        self.assertTrue(
            draft_review_allowed(
                has_board_editor_capability=True,
                has_plan_view=True,
            )
        )
        self.assertFalse(
            create_write_allowed(
                has_edit_capability=False,
                has_plan_view=True,
                order_status="Draft",
            )
        )
        self.assertTrue(
            create_write_allowed(
                has_edit_capability=True,
                has_plan_view=True,
                order_status="Draft",
            )
        )

    def test_services_require_use_board_editor_not_optimizer(self) -> None:
        query = _source("almdina_erp/services/board_editor_query_service.py")
        self.assertIn("Capability.USE_BOARD_EDITOR", query)
        self.assertIn("def _require_use_board_editor", query)
        self.assertIn("get_board_editor_projection", query)
        self.assertGreater(
            query.index("_require_use_board_editor(order)"),
            query.index("def get_board_editor_projection"),
        )
        self.assertNotIn("EDIT_OPTIMIZER_SETTINGS", query)

        for relative in (
            "almdina_erp/services/board_editor_draft_service.py",
            "almdina_erp/services/board_editor_draft_review_service.py",
            "almdina_erp/services/board_editor_plan_create_service.py",
        ):
            with self.subTest(relative=relative):
                source = _source(relative)
                self.assertIn("_require_use_board_editor", source)
                self.assertIn("_use_board_editor_allowed", source)
                self.assertNotIn("EDIT_OPTIMIZER_SETTINGS", source)

        adapter = _source(
            "almdina_erp/infrastructure/frappe/board_editor_plan_create_adapter.py"
        )
        self.assertIn("Capability.USE_BOARD_EDITOR", adapter)
        self.assertNotIn("EDIT_OPTIMIZER_SETTINGS", adapter)

        draft = _source("almdina_erp/services/board_editor_draft_service.py")
        self.assertIn("save_board_editor_draft", draft)
        self.assertIn("begin_board_editor_draft_from_current_source", draft)

        review = _source("almdina_erp/services/board_editor_draft_review_service.py")
        self.assertIn("validate_board_editor_draft", review)

        create = _source("almdina_erp/services/board_editor_plan_create_service.py")
        self.assertIn("create_board_editor_plan_copy", create)

        delivered = _source(
            "almdina_erp/infrastructure/frappe/cutting_plan_authorization.py"
        )
        self.assertIn("Capability.USE_BOARD_EDITOR", delivered)
        self.assertIn("_DELIVERED_PLAN_MUTATIONS", delivered)

    def test_frontend_open_button_requires_capability(self) -> None:
        context = (
            PUBLIC
            / "js"
            / "door_cutting_order"
            / "cutting_plan"
            / "door_cutting_order_plan_context_actions_ux.js"
        ).read_text(encoding="utf-8")
        can_open = context.split("function canOpenBoardEditor", 1)[1].split(
            "function runOpenBoardEditor", 1
        )[0]
        self.assertIn('can(frm, "use_board_editor")', can_open)
        self.assertNotIn("edit_optimizer_settings", can_open)
        self.assertIn("almdina:permissions-updated", context)

        page_json = (APP / "page" / "board_editor" / "board_editor.json").read_text(
            encoding="utf-8"
        )
        self.assertIn('"roles": []', page_json)


class UseBoardEditorMatrixRoundTripContractTests(unittest.TestCase):
    def test_matrix_toggle_round_trip_semantics(self) -> None:
        enabled = normalize_capability_state({Capability.USE_BOARD_EDITOR: True})
        self.assertTrue(enabled[Capability.USE_BOARD_EDITOR])
        disabled = normalize_capability_state(
            {
                Capability.VIEW_CUTTING_PLAN: True,
                Capability.USE_BOARD_EDITOR: False,
            }
        )
        self.assertFalse(disabled[Capability.USE_BOARD_EDITOR])
        self.assertTrue(disabled[Capability.VIEW_CUTTING_PLAN])


if __name__ == "__main__":
    unittest.main()
