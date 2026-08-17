from __future__ import annotations

import json
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent


def _read(relative_path: str) -> str:
    return (APP_ROOT / relative_path).read_text(encoding="utf-8")


def _read_repo(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


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

    def test_reference_image_is_private_documentation_not_exact_geometry(self) -> None:
        service = _read("almdina_erp/services/special_shape_workspace_service.py")
        self.assertIn("def save_reference_image(", service)
        self.assertIn("def remove_reference_image(", service)
        self.assertIn('Capability.EDIT_SPECIAL_DRAWING', service)
        self.assertIn("_assert_editable(order)", service)
        self.assertIn("is_private=1", service)
        self.assertIn('piece.special_shape_documentation_mode = "Image"', service)
        self.assertIn('piece.special_shape_status = "Documented"', service)
        self.assertIn('piece.special_shape_drawing_json = ""', service)
        self.assertIn('piece.special_shape_geometry_json = ""', service)
        self.assertIn('_REFERENCE_IMAGE_MAX_BYTES = 8 * 1024 * 1024', service)

    def test_reference_image_fields_are_explicit_child_row_state(self) -> None:
        payload = json.loads(
            _read(
                "almdina_erp/doctype/door_cutting_order_detail/door_cutting_order_detail.json"
            )
        )
        fields = {field["fieldname"]: field for field in payload["fields"]}
        self.assertEqual(fields["special_shape_documentation_mode"]["options"], "Drawing\nImage")
        self.assertEqual(fields["special_shape_reference_image"]["fieldtype"], "Attach Image")
        self.assertEqual(fields["special_shape_reference_image"]["hidden"], 1)
        self.assertIn("special_shape_reference_image_meta_json", fields)

    def test_reference_image_change_participates_in_piece_policy_invalidation(self) -> None:
        adapter = _read(
            "almdina_erp/infrastructure/frappe/orders/piece_policy_adapter.py"
        )
        self.assertIn("def _reference_snapshot", adapter)
        self.assertIn("def _reference_has_content", adapter)
        self.assertIn("reference_changed", adapter)
        self.assertIn("or reference_has_content", adapter)
        self.assertIn("or reference_changed", adapter)

    def test_page_loads_reference_runtime_before_workspace_session(self) -> None:
        page = _read("almdina_erp/page/door_drawing/door_drawing.js")
        tokens = [
            "/reference/domain.js",
            "/reference/device_source.js",
            "/reference/scanner_bridge.js",
            "/reference/cropper.js",
            "/reference/reference_view.js",
            "/workspace/api.js",
            "/workspace/reference_controller.js",
            "/workspace/session_controller.js",
        ]
        positions = [page.index(token) for token in tokens]
        self.assertTrue(all(position >= 0 for position in positions))
        self.assertEqual(positions, sorted(positions))
        self.assertIn("door_drawing_reference.css", page)

    def test_scanner_bridge_is_loopback_and_origin_restricted(self) -> None:
        bridge = _read_repo("tools/scanner_bridge/windows/AlmdinaScannerBridge.ps1")
        browser = _read("public/js/door_drawing_v4/reference/scanner_bridge.js")
        self.assertIn("http://127.0.0.1:", bridge)
        self.assertNotIn("http://+:", bridge)
        self.assertIn("AllowedOrigins", bridge)
        self.assertIn("WIA.CommonDialog", bridge)
        self.assertIn("ShowAcquireImage", bridge)
        self.assertIn("http://127.0.0.1:17654", browser)
        self.assertIn("X-Almdina-Scanner-Bridge", browser)


if __name__ == "__main__":
    unittest.main()
