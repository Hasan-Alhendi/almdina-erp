from __future__ import annotations

import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
ASSETS = ROOT / "frontend_assets.py"
CLOSURE_DOC = REPO / "docs" / "reference" / "14_FRONTEND_REFACTOR_CLOSURE.md"
LIFECYCLE_DOC = REPO / "docs" / "reference" / "15_FRONTEND_LIFECYCLE_CLOSURE.md"

ORDER_ENTRY = ROOT / "public" / "js" / "door_cutting_order" / "order_entry"
MEASUREMENTS = ORDER_ENTRY / "measurements"
EDGE = ORDER_ENTRY / "edge_banding"
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"

LEGACY_OPERATOR_PATCH = ORDER_ENTRY / "door_cutting_order_operator_ux_patch.js"
MEASUREMENT_LIFECYCLE = MEASUREMENTS / "door_cutting_order_measurement_lifecycle.js"
FAST_KEYBOARD = MEASUREMENTS / "door_cutting_order_fast_entry_keyboard_ux.js"
EDGE_OWNER = EDGE / "door_cutting_order_edge_render_owner.js"
PLAN_STYLES = CUTTING_PLAN / "door_cutting_order_plan_content_styles.js"
PLAN_PRESENTER = CUTTING_PLAN / "door_cutting_order_plan_board_presenter.js"
PLAN_CONTENT = CUTTING_PLAN / "door_cutting_order_plan_content_ux.js"


def asset_manifest() -> dict:
    return runpy.run_path(str(ASSETS))


class FrontendRefactorClosureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = asset_manifest()
        cls.dco_assets = cls.manifest["doctype_js"]["Door Cutting Order"]
        cls.app_assets = cls.manifest["app_include_js"]
        cls.doc = CLOSURE_DOC.read_text(encoding="utf-8")
        cls.lifecycle_doc = LIFECYCLE_DOC.read_text(encoding="utf-8")

    def test_frontend_asset_registrations_have_no_duplicates(self) -> None:
        self.assertEqual(len(self.app_assets), len(set(self.app_assets)))
        self.assertEqual(len(self.dco_assets), len(set(self.dco_assets)))

    def test_every_registered_local_dco_javascript_asset_exists(self) -> None:
        missing = [asset for asset in self.dco_assets if not (ROOT / asset).is_file()]
        self.assertEqual(missing, [], f"Missing DCO frontend assets: {missing}")

    def test_legacy_operator_patch_cannot_return_silently(self) -> None:
        self.assertFalse(LEGACY_OPERATOR_PATCH.exists())
        self.assertFalse(any("door_cutting_order_operator_ux_patch.js" in asset for asset in self.dco_assets))
        self.assertIn("لا تعيد Patch القديم", self.doc)

    def test_required_final_owners_exist(self) -> None:
        for path in (
            MEASUREMENT_LIFECYCLE,
            FAST_KEYBOARD,
            EDGE_OWNER,
            PLAN_STYLES,
            PLAN_PRESENTER,
            PLAN_CONTENT,
        ):
            self.assertTrue(path.is_file(), str(path))

    def test_runtime_order_preserves_final_owner_dependencies(self) -> None:
        def index(suffix: str) -> int:
            matches = [i for i, asset in enumerate(self.dco_assets) if asset.endswith(suffix)]
            self.assertEqual(len(matches), 1, suffix)
            return matches[0]

        self.assertLess(index("door_cutting_order_operator_ux.js"), index("door_cutting_order_fast_entry_keyboard_ux.js"))
        self.assertLess(index("door_cutting_order_fast_entry_keyboard_ux.js"), index("door_cutting_order_measurement_lifecycle.js"))

        self.assertLess(index("door_cutting_order_multi_edge_ux.js"), index("door_cutting_order_edge_profile_controls_ux.js"))
        self.assertLess(index("door_cutting_order_edge_profile_controls_ux.js"), index("door_cutting_order_edge_profile_double_click_guard.js"))
        self.assertLess(index("door_cutting_order_edge_profile_double_click_guard.js"), index("door_cutting_order_edge_render_owner.js"))
        self.assertLess(index("door_cutting_order_edge_render_owner.js"), index("door_cutting_order_cut_dimensions_ux.js"))

        self.assertLess(index("door_cutting_order_plan_controls_ux.js"), index("door_cutting_order_plan_content_styles.js"))
        self.assertLess(index("door_cutting_order_plan_content_styles.js"), index("door_cutting_order_plan_board_presenter.js"))
        self.assertLess(index("door_cutting_order_plan_board_presenter.js"), index("door_cutting_order_plan_content_ux.js"))
        self.assertLess(index("door_cutting_order_plan_content_ux.js"), index("door_cutting_order_plan_tabs_ux.js"))

    def test_measurement_lifecycle_is_explicit_and_immutable(self) -> None:
        source = MEASUREMENT_LIFECYCLE.read_text(encoding="utf-8")
        self.assertIn("createLifecycleScope", source)
        self.assertIn("const scopesByForm = new WeakMap()", source)
        self.assertIn("scope.dispose()", source)
        self.assertIn("window.AlmdinaMeasurementLifecycle = Object.freeze", source)

    def test_edge_render_owner_remains_structural_not_interaction_owner(self) -> None:
        source = EDGE_OWNER.read_text(encoding="utf-8")
        self.assertIn('"_dcoSideEdgeObserver"', source)
        self.assertIn('"_dcoCompactEdgeProfileControlsObserver"', source)
        self.assertIn("structuralMeasurementMutation", source)
        self.assertIn("observer.disconnect()", source)
        self.assertIn("window.AlmdinaEdgeRenderOwner = Object.freeze", source)
        self.assertNotIn("toggleButtonImmediately", source)
        self.assertNotIn("CHECK_FIELDS", source)

    def test_cutting_plan_content_stays_a_small_orchestrator(self) -> None:
        source = PLAN_CONTENT.read_text(encoding="utf-8")
        self.assertLess(len(source.splitlines()), 600)
        self.assertNotIn("style.textContent", source)
        self.assertNotIn("function openBoardFocus", source)
        self.assertNotIn("function desiredBoardColumns", source)
        self.assertIn("AlmdinaPlanContentStyles", source)
        self.assertIn("AlmdinaPlanBoardPresenter", source)
        self.assertIn("window.AlmdinaPlanContentUX = Object.freeze", source)

    def test_closure_document_names_critical_owners_and_residual_compatibility(self) -> None:
        for marker in (
            "frontend_foundation.js",
            "door_cutting_order_document_context.js",
            "shop_floor_inbox/controller.js",
            "door_cutting_order_measurement_lifecycle.js",
            "door_cutting_order_fast_entry_keyboard_ux.js",
            "door_cutting_order_edge_profile_double_click_guard.js",
            "door_cutting_order_edge_render_owner.js",
            "door_cutting_order_plan_content_styles.js",
            "door_cutting_order_plan_board_presenter.js",
            "door_cutting_order_plan_content_ux.js",
            "_dcoSideEdgeObserver",
            "_dcoCompactEdgeProfileControlsObserver",
            "260 ms",
        ):
            self.assertIn(marker, self.doc)

    def test_closure_is_structural_not_product_behavior_change(self) -> None:
        for marker in (
            "UI redesign",
            "business-rule changes",
            "authorization changes",
            "workflow changes",
            "schema/data migration",
        ):
            self.assertIn(marker, self.doc)

    def test_project_lifecycle_closure_is_part_of_the_canonical_reference(self) -> None:
        for marker in (
            "Synchronous shell",
            "inactive ⇄ active visits",
            "factory-permissions",
            "shop-floor-inbox",
            "factory-master-data",
            "door-drawing",
            "Door Cutting Order Form",
            "Door Cutting Order List",
            "Replacement Piece Form",
            "dirty state",
            "remount",
        ):
            self.assertIn(marker, self.lifecycle_doc)


if __name__ == "__main__":
    unittest.main()
