"""Edited/Approved Board Editor identity + reopen contracts (no Frappe runtime)."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    BOARD_EDITOR,
    DRAFT,
    SYSTEM,
    select_board_editor_surface_plan,
)

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
QUERY = APP / "services" / "board_editor_query_service.py"
WORKSPACE = APP / "services" / "cutting_plan_workspace_query_service.py"
LIFECYCLE = APP / "domain" / "cutting" / "plan_lifecycle.py"
TABS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_tabs_ux.js"
)
CONTEXT = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_context_actions_ux.js"
)
STATE = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_workspace_state.js"
)
AR = ROOT / "translations" / "ar.csv"


def _row(name: str, *, revision: int, status: str, source: str = BOARD_EDITOR, modified: str = ""):
    return {
        "name": name,
        "revision": revision,
        "status": status,
        "source_type": source,
        "modified": modified or f"2026-01-0{revision} 00:00:00",
    }


class SelectBoardEditorSurfacePlanTests(unittest.TestCase):
    def test_prefers_approved_tip_over_older_draft(self):
        rows = [
            _row("CP-OLD-DRAFT", revision=10, status=DRAFT),
            _row("CP-APPROVED-A", revision=11, status=APPROVED),
            _row("CP-SYSTEM", revision=5, status=DRAFT, source=SYSTEM),
        ]
        selected = select_board_editor_surface_plan(
            rows, approved_plan_name="CP-APPROVED-A"
        )
        self.assertEqual(selected["name"], "CP-APPROVED-A")

    def test_newer_draft_b_wins_after_apply_while_a_remains_approved(self):
        rows = [
            _row("CP-APPROVED-A", revision=11, status=APPROVED),
            _row("CP-DRAFT-B", revision=12, status=DRAFT),
        ]
        selected = select_board_editor_surface_plan(
            rows, approved_plan_name="CP-APPROVED-A"
        )
        self.assertEqual(selected["name"], "CP-DRAFT-B")

    def test_ignores_approved_non_board_editor_and_other_orders_rows(self):
        rows = [
            _row("CP-SYS-APPROVED", revision=20, status=APPROVED, source=SYSTEM),
            _row("CP-BE-DRAFT", revision=3, status=DRAFT),
        ]
        selected = select_board_editor_surface_plan(
            rows, approved_plan_name="CP-SYS-APPROVED"
        )
        self.assertEqual(selected["name"], "CP-BE-DRAFT")

    def test_empty_when_only_historical_board_editor_approved(self):
        rows = [
            _row("CP-OLD-APPROVED", revision=8, status=APPROVED),
        ]
        selected = select_board_editor_surface_plan(
            rows, approved_plan_name="CP-OTHER"
        )
        self.assertIsNone(selected)


class BoardEditorViewGateSourceTests(unittest.TestCase):
    def test_query_allows_board_editor_draft_and_specific_denials(self):
        source = QUERY.read_text(encoding="utf-8")
        self.assertIn("BOARD_EDITOR", source)
        self.assertIn("_plan_view_denial_code", source)
        self.assertIn("_plan_view_denial_message", source)
        self.assertIn("missing_view_system_capability", source)
        self.assertIn("board_editor_plan_not_openable", source)
        self.assertIn('return "board_editor"', source)
        self.assertIn("mutate_approved_snapshot", source)
        self.assertIn("_plan_view_denial_message(denial)", source)
        open_gate = source.split("def get_board_editor_projection", 1)[1].split(
            "snapshot = _enrich_snapshot_allow_rotation", 1
        )[0]
        self.assertIn("denial = _plan_view_denial_code", open_gate)
        self.assertIn("_plan_view_denial_message(denial)", open_gate)

    def test_plan_view_denial_helpers_cover_board_editor_paths(self):
        source = QUERY.read_text(encoding="utf-8")
        denial = source.split("def _plan_view_denial_code", 1)[1].split(
            "def _plan_view_denial_message", 1
        )[0]
        kind = source.split("def _source_kind_for_plan", 1)[1].split(
            "def _display_context_for_plan", 1
        )[0]
        self.assertIn("is_board_editor_source", denial)
        self.assertIn("view_system", denial)
        self.assertIn("missing_view_system_capability", denial)
        self.assertIn("board_editor_plan_not_openable", denial)
        self.assertIn('return "board_editor"', kind)
        self.assertIn('return "approved"', kind)


class WorkspaceSurfaceContractTests(unittest.TestCase):
    def test_workspace_uses_surface_selector_and_content_identity(self):
        source = WORKSPACE.read_text(encoding="utf-8")
        self.assertIn("select_board_editor_surface_plan", source)
        self.assertIn("_board_editor_plan(rows, order)", source)
        self.assertIn("content_identity", source)
        self.assertIn("editor_draft", source)
        self.assertIn("is_current_approved_tip", source)
        self.assertIn("surface_role", source)
        # Payload key stays for compatibility; selection is no longer Draft-only.
        self.assertIn('"board_editor_draft": board_editor_payload', source)
        self.assertNotIn(
            "return _latest(rows, status=DRAFT, source_type=BOARD_EDITOR)",
            source,
        )

    def test_workspace_snapshot_function_still_capability_scoped(self):
        tree = ast.parse(WORKSPACE.read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "get_plan_workspace_snapshot"
        )
        calls = [
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else ""
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
        ]
        self.assertIn("_authorized_order", calls)
        self.assertIn("_board_editor_plan", calls)

    def test_ui_paint_key_and_open_identity_share_plan_for_tab(self):
        tabs = TABS.read_text(encoding="utf-8")
        context = CONTEXT.read_text(encoding="utf-8")
        state = STATE.read_text(encoding="utf-8")
        self.assertIn("planPaintIdentity", tabs)
        self.assertIn("data-almdina-plan-paint-key", tabs)
        self.assertIn("content_identity", tabs)
        self.assertIn("Unapplied board-editor draft", tabs)
        self.assertIn("rowForTab(frm)", context)
        self.assertIn("boardEditorAppPath", context)
        self.assertIn('target="_blank"', context)
        self.assertIn("noopener noreferrer", context)
        self.assertNotIn("frappe.set_route(\"board-editor\", orderName, planName)", context)
        self.assertIn('if (tab === "BoardEditor") {', state)
        self.assertIn("plans.board_editor_draft", state)
        # Tab switch must not rewrite approved_plan.
        self.assertNotIn("approved_plan =", tabs.split("function onTabClick", 1)[1][:400])

    def test_arabic_localization_covers_new_user_strings(self):
        ar = AR.read_text(encoding="utf-8")
        for key in (
            "Unapplied board-editor draft",
            "This board-editor cutting plan cannot be opened in its current status.",
            "You do not have permission to view the system cutting plan.",
            "The board editor has saved changes that are not applied to this cutting plan yet.",
        ):
            self.assertIn(key, ar)

    def test_lifecycle_exports_selector(self):
        source = LIFECYCLE.read_text(encoding="utf-8")
        self.assertIn("select_board_editor_surface_plan", source)
        self.assertIn('"select_board_editor_surface_plan"', source)


class MaterializeReuseGeometryContractTests(unittest.TestCase):
    def test_materialize_marks_posed_geometry_without_reapply_flag(self):
        from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
            METHOD_KEY,
        )
        from almdina_erp.tests.test_board_editor_manufacturing_approve_export import (
            _ready_snapshot,
        )

        snapshot = _ready_snapshot(rotation_deg=15.0)
        self.assertEqual(snapshot.get("method_key"), METHOD_KEY)
        piece = snapshot["sheets"][0]["pieces"][0]
        self.assertFalse(piece.get("apply_rotated_to_geometry"))
        self.assertIn("geometry", piece)
        self.assertAlmostEqual(float(piece.get("rotation_deg") or 0), 15.0, places=6)


if __name__ == "__main__":
    unittest.main()
