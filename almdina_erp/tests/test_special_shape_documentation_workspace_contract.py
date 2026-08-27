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
DOCUMENTATION = PUBLIC / "js" / "special_shape_documentation"
CSS = PUBLIC / "css" / "special_shape_documentation.css"


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


class TestSpecialShapeDocumentationWorkspaceContract(unittest.TestCase):
    def test_entry_routes_to_one_standalone_documentation_workspace(self) -> None:
        facade = FACADE.read_text(encoding="utf-8")
        self.assertIn('frappe.set_route("door-drawing", frm.doc.name, saved.name)', facade)
        self.assertIn("__documentationOnly: true", facade)
        self.assertIn("__manufacturingGeometrySeparated: true", facade)
        self.assertNotIn("frappe.ui.Dialog", facade)

    def test_page_loads_only_new_layered_subsystem(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        for layer in ("domain", "application", "infrastructure", "presentation"):
            self.assertIn(f"${{ASSET_ROOT}}/{layer}/", page)
        self.assertNotIn("door_drawing_v3", page)
        self.assertNotIn("door_drawing_v4", page)
        self.assertIn("hide.aldDocumentation", page)
        self.assertIn("active.suspend()", page)
        self.assertIn("renderBootState(wrapper)", page)
        self.assertIn("Promise.all(MODULES.map", page)
        self.assertNotIn("MODULES.reduce", page)
        self.assertIn("infrastructure/scanner_bridge.js", page)
        self.assertIn("application/element_clipboard.js", page)
        self.assertIn("application/keyboard_shortcuts.js", page)
        self.assertIn("domain/reference_crop.js", page)
        self.assertIn("presentation/canvas_viewport.js", page)

    def test_legacy_editor_directories_and_styles_are_deleted(self) -> None:
        self.assertFalse(any((PUBLIC / "js" / "door_drawing_v3").rglob("*.js")))
        self.assertFalse(any((PUBLIC / "js" / "door_drawing_v4").rglob("*.js")))
        self.assertFalse(any((PUBLIC / "css").glob("door_drawing_v3*.css")))
        self.assertFalse(any((PUBLIC / "css").glob("door_drawing_v4*.css")))
        self.assertTrue(DOCUMENTATION.is_dir())
        self.assertTrue(CSS.is_file())

    def test_save_is_capability_guarded_and_has_no_manufacturing_projection(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        calls = _function_calls(source, "save_documentation_workspace")
        self.assertIn("_assert_editable", calls)
        self.assertIn("validate_special_shape_drawing", calls)
        self.assertIn("_validate_reference_scope", calls)
        save_source = source.split("def save_documentation_workspace", 1)[1].split("\n\n__all__", 1)[0]
        self.assertNotIn("special_shape_geometry_json", save_source)
        self.assertNotIn("plan_needs_recalculation", save_source)
        self.assertNotIn("calculated_plan", save_source)
        self.assertNotIn("reset_price_values", save_source)
        self.assertNotIn("validate_special_shape_geometry", source)

    def test_private_image_upload_is_piece_scoped(self) -> None:
        source = SERVICE.read_text(encoding="utf-8")
        upload_calls = _function_calls(source, "upload_reference_image")
        self.assertIn("_assert_editable", upload_calls)
        self.assertIn("_decode_image", upload_calls)
        self.assertIn("save_file", upload_calls)
        self.assertIn('"Door Cutting Order Detail"', source)
        reference_calls = _function_calls(source, "_reference_file")
        self.assertIn("get_value", reference_calls)
        self.assertIn("is_private", source)
        self.assertNotIn("ignore_permissions", source)

    def test_ui_contains_required_intake_and_designer_handoff(self) -> None:
        shell = (DOCUMENTATION / "presentation" / "workspace_shell.js").read_text(encoding="utf-8")
        controller = (DOCUMENTATION / "presentation" / "workspace_controller.js").read_text(encoding="utf-8")
        renderer = (DOCUMENTATION / "presentation" / "canvas_renderer.js").read_text(encoding="utf-8")
        for label in ("رفع صورة", "مسح بالسكانر", "التقاط بالكاميرا", "شكل جاهز", "قلم ذكي", "ملاحظات المصمم", "حفظ التوثيق"):
            self.assertIn(label, shell)
        self.assertIn("تنزيل الصورة الأصلية للمصمم", shell)
        self.assertIn("هذا توثيق لطلب العميل وليس ملف تصنيع", shell)
        self.assertIn("pointerdown", controller)
        self.assertIn("Scanner.health()", controller)
        self.assertIn("Scanner.scan()", controller)
        self.assertIn("تنزيل برنامج السكانر — تثبيت مرة واحدة", shell)
        self.assertIn("Scanner.INSTALLER_URL", controller)
        self.assertNotIn("PowerShell", controller)
        self.assertIn("getCoalescedEvents", controller)
        self.assertIn("Shortcuts.resolve(event)", controller)
        self.assertIn("copySelection()", controller)
        self.assertIn("pasteSelection()", controller)
        self.assertIn("renderer.zoomAt", controller)
        self.assertIn("Ctrl+Z", shell)
        self.assertIn("Ctrl+Y", shell)
        for label in ("اقتصاص الصورة", "اقتصاص تلقائي", "إعادة ضبط", "إلغاء", "تطبيق"):
            self.assertIn(label, shell)
        self.assertIn("renderer.cropRegion", controller)
        self.assertIn("renderer.suggestReferenceCrop", controller)
        self.assertIn("renderer.referenceImageSize", controller)
        self.assertNotIn("data-opacity", shell)
        self.assertNotIn("الشفافية", shell)
        self.assertNotIn("data-opacity", controller)
        self.assertNotIn("opacity: 0.72", controller)
        self.assertIn("context.globalAlpha = 1", renderer)
        self.assertNotIn("document.reference.opacity", renderer)


if __name__ == "__main__":
    unittest.main()
