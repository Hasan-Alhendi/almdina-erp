from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
APP = ROOT / "almdina_erp"
PAGE = APP / "page" / "door_drawing" / "door_drawing.js"
SERVICE = APP / "services" / "special_shape_workspace_service.py"
FACADE = PUBLIC / "js" / "door_cutting_order" / "drawing" / "special_shape_facade.js"
PROFESSIONAL = PUBLIC / "js" / "door_drawing_v4" / "professional"
CSS = PUBLIC / "css" / "door_drawing_professional.css"


def _function_calls(source: str, function_name: str) -> set[str]:
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == function_name)
    calls: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            calls.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            calls.add(child.func.attr)
    return calls


class TestDoorDrawingProfessionalWorkspaceContract(unittest.TestCase):
    def test_normal_entry_routes_to_standalone_workspace_not_modal(self) -> None:
        facade = FACADE.read_text(encoding="utf-8")
        self.assertIn('frappe.set_route("door-drawing", frm.doc.name, savedRow.name)', facade)
        open_source = facade.split("async function open", 1)[1].split("\n    function view", 1)[0]
        self.assertNotIn("Editor.open", open_source)
        self.assertNotIn("frappe.ui.Dialog", open_source)
        self.assertIn("__standaloneProfessionalWorkspace: true", facade)

    def test_professional_runtime_does_not_create_frappe_dialogs(self) -> None:
        for path in sorted(PROFESSIONAL.glob("*.js")):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("frappe.ui.Dialog", source, path)
            self.assertNotIn("frappe.ui.dialog", source, path)

    def test_active_tool_state_cannot_impersonate_a_tool_button(self) -> None:
        shell = (PROFESSIONAL / "workspace_shell.js").read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("workspace.dataset.activeTool = tool", shell)
        self.assertNotIn("workspace.dataset.tool = tool", shell)
        self.assertIn('[data-active-tool="pen"]', css)
        self.assertIn('[data-active-tool="dimension"]', css)
        self.assertIn('[data-active-tool="hand"]', css)
        self.assertNotIn('.ald-prof-workspace[data-tool=', css)

    def test_page_creates_frappe_scaffold_before_workspace_mount(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        self.assertIn("function ensurePageScaffold(wrapper)", page)
        self.assertIn("frappe.ui.make_app_page({", page)
        self.assertIn('wrapper.querySelector(".layout-main-section")', page)
        load_source = page.split("frappe.pages[PAGE_ROUTE].on_page_load", 1)[1].split(
            "frappe.pages[PAGE_ROUTE].on_page_show",
            1,
        )[0]
        self.assertLess(
            load_source.index("ensurePageScaffold(wrapper)"),
            load_source.index("ensureController(wrapper)"),
            "Frappe Page scaffold must exist before the professional workspace mounts",
        )
        controller_source = page.split("function ensureController", 1)[1].split(
            "function enterFullscreenMode",
            1,
        )[0]
        self.assertIn("ensurePageScaffold(wrapper)", controller_source)

    def test_page_owns_real_hide_lifecycle_and_professional_layout(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        self.assertIn('"hide.aldProfessionalDoorDrawing"', page)
        self.assertIn("controller.suspend()", page)
        self.assertNotIn("on_page_hide", page)
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("grid-template-columns:240px minmax(0,1fr) 280px", css)
        self.assertIn(".ald-prof-toolbar", css)
        self.assertIn("bottom:18px", css)
        shell = (PROFESSIONAL / "workspace_shell.js").read_text(encoding="utf-8")
        self.assertIn("Layers", shell)
        self.assertIn("Assets", shell)
        self.assertIn("Design", shell)
        self.assertIn("Prototype", shell)

    def test_workspace_save_is_capability_guarded_without_permission_bypass(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        self.assertNotIn("ignore_permissions", source)
        self.assertNotIn("order.save(", source)
        save_calls = _function_calls(source, "save_drawing_workspace")
        self.assertIn("_assert_editable", save_calls)
        self.assertIn("validate_special_shape_drawing", save_calls)
        self.assertIn("validate_special_shape_geometry", save_calls)
        guard_calls = _function_calls(source, "_assert_editable")
        self.assertIn("require_document_capability", guard_calls)
        self.assertIn("require_stage_operational_access", guard_calls)
        self.assertIn("assert_order_editable", guard_calls)

    def test_workspace_load_is_document_capability_guarded(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        order_calls = _function_calls(source, "_order")
        self.assertIn("require_any_document_capability", order_calls)
        self.assertIn("Capability.VIEW_DRAWING_WORKSPACE", source)
        self.assertIn("Capability.EDIT_SPECIAL_DRAWING", source)


if __name__ == "__main__":
    unittest.main()
