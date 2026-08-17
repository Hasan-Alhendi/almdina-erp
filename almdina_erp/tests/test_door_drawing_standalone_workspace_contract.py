from __future__ import annotations

import json
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (APP_ROOT / relative_path).read_text(encoding="utf-8")


class TestDoorDrawingStandaloneWorkspaceContract(unittest.TestCase):
    def test_standalone_drawing_page_is_unrestricted_by_fixed_frappe_roles(self) -> None:
        payload = json.loads(
            _read("almdina_erp/page/door_drawing/door_drawing.json")
        )
        self.assertEqual(payload["name"], "door-drawing")
        self.assertEqual(payload["page_name"], "door-drawing")
        self.assertEqual(payload["roles"], [])

    def test_special_shape_facade_routes_to_workspace_instead_of_opening_dialog(self) -> None:
        source = _read(
            "public/js/door_cutting_order/drawing/special_shape_facade.js"
        )
        self.assertIn('const WORKSPACE_ROUTE = "door-drawing"', source)
        self.assertIn("frappe.set_route(WORKSPACE_ROUTE", source)
        self.assertIn("frm.save()", source)
        self.assertNotIn("frappe.ui.Dialog", source)

    def test_workspace_server_endpoint_keeps_capability_and_geometry_boundaries(self) -> None:
        source = _read(
            "almdina_erp/services/special_shape_workspace_service.py"
        )
        self.assertIn("Capability.VIEW_DRAWING_WORKSPACE", source)
        self.assertIn("Capability.EDIT_SPECIAL_DRAWING", source)
        self.assertIn("require_stage_operational_access(order)", source)
        self.assertIn("validate_special_shape_drawing", source)
        self.assertIn("validate_special_shape_geometry", source)
        self.assertIn("order.flags.allow_approved_edit = True", source)
        self.assertIn("order.save(ignore_permissions=True)", source)

    def test_workspace_uses_existing_v4_runtime_instead_of_forking_geometry(self) -> None:
        page = _read("almdina_erp/page/door_drawing/door_drawing.js")
        session = _read(
            "public/js/door_drawing_v4/workspace/session_controller.js"
        )
        bootstrap = _read("public/js/door_drawing_v4/bootstrap.js")

        self.assertIn("/assets/almdina_erp/js/door_drawing_v4/bootstrap.js", page)
        self.assertIn("runtime.PersistenceAdapter.fromStored", session)
        self.assertIn("runtime.EditorController.create", session)
        self.assertIn("runtime.ManufacturingProjection.project", session)
        self.assertIn("/door_drawing_v4/domain/document.js", bootstrap)
        self.assertIn("/door_drawing_v4/application/constraint_solver.js", bootstrap)
        self.assertIn("/door_drawing_v4/application/snap_resolver.js", bootstrap)

    def test_workspace_has_explicit_session_cleanup_and_unsaved_state(self) -> None:
        page = _read("almdina_erp/page/door_drawing/door_drawing.js")
        session = _read(
            "public/js/door_drawing_v4/workspace/session_controller.js"
        )
        self.assertIn("session.destroy()", page)
        self.assertIn('hide.aldDoorDrawingWorkspace', page)
        self.assertNotIn("on_page_hide", page)
        self.assertIn('shell.setSaveState("dirty", "غير محفوظ")', session)
        self.assertIn("editor.destroy()", session)
        self.assertIn("لديك تعديلات غير محفوظة", session)

    def test_workspace_is_not_registered_as_a_global_dco_surface(self) -> None:
        assets = _read("frontend_assets.py")
        self.assertNotIn(
            '"public/js/door_drawing_v4/workspace/session_controller.js"',
            assets,
        )
        self.assertNotIn(
            '"public/css/door_drawing_workspace.css"',
            assets,
        )


if __name__ == "__main__":
    unittest.main()
