from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "frontend_assets.py"

CORE_SCRIPTS = (
    "public/js/door_cutting_order/core/door_cutting_order_document_context.js",
    "public/js/door_cutting_order/core/door_cutting_order_action_permission_guard.js",
    "public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_revision_ux.js",
    "public/js/door_cutting_order/core/order_lifecycle.js",
)

ORDER_ENTRY_SCRIPTS = (
    "public/js/door_cutting_order/order_entry/door_cutting_order_defaults.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux_patch.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_bulk_rows_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_keyboard_columns_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_compact_measurements_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_toolbar_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_resilience_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_table_performance_ux.js",
    "public/js/door_cutting_order/order_entry/door_cutting_order_board_text_ux.js",
)

EDGE_BANDING_SCRIPTS = (
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_controls_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_double_click_guard.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_cut_dimensions_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_color_ux.js",
)

CUTTING_PLAN_SCRIPTS = (
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_cutting_plan_renderer.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_content_ux.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_tabs_ux.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_surface_bootstrap.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_drawing_plan_ux.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_drawing_approval_ux.js",
    "public/js/door_cutting_order/cutting_plan/secure_dxf_export.js",
)

COSTING_SCRIPTS = (
    "public/js/door_cutting_order/costing/door_cutting_order_multi_edge_documents_ux.js",
    "public/js/door_cutting_order/costing/door_cutting_order_cost_presenter.js",
    "public/js/door_cutting_order/costing/door_cutting_order_cost_permissions_ux.js",
    "public/js/door_cutting_order/costing/door_cutting_order_financial_documents_ux.js",
    "public/js/door_cutting_order/costing/door_cutting_order_customer_invoice_toolbar_ux.js",
)

PRINTING_SCRIPTS = (
    "public/js/door_cutting_order/printing/door_cutting_order_print_identity.js",
    "public/js/door_cutting_order/printing/door_cutting_order_shape_print.js",
    "public/js/door_cutting_order/printing/door_cutting_order_document_print_theme.js",
    "public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js",
    "public/js/door_cutting_order/printing/door_cutting_order_document_compactness_ux.js",
)

OLD_ORDER_ENTRY_PATHS = tuple(
    f"public/js/{Path(script).name}" for script in ORDER_ENTRY_SCRIPTS
)
OLD_EDGE_BANDING_PATHS = tuple(
    f"public/js/{Path(script).name}" for script in EDGE_BANDING_SCRIPTS
)
OLD_CUTTING_PLAN_PATHS = tuple(
    f"public/js/{Path(script).name}" for script in CUTTING_PLAN_SCRIPTS
)
OLD_COSTING_PATHS = tuple(
    f"public/js/{Path(script).name}" for script in COSTING_SCRIPTS
)
OLD_PRINTING_PATHS = tuple(
    f"public/js/{Path(script).name}" for script in PRINTING_SCRIPTS
)


class TestFrontendFeatureOwnershipContract(unittest.TestCase):
    def test_first_core_batch_is_loaded_once_in_stable_order(self):
        hooks = HOOKS.read_text(encoding="utf-8")
        positions = []

        for script in CORE_SCRIPTS:
            self.assertEqual(
                hooks.count(f'"{script}"'),
                1,
                f"{script} must have one canonical Door Cutting Order asset owner",
            )
            positions.append(hooks.index(f'"{script}"'))

        self.assertEqual(
            positions,
            sorted(positions),
            "Core script load order changed during the architecture migration",
        )

    def test_document_context_stays_ahead_of_other_core_modules(self):
        hooks = HOOKS.read_text(encoding="utf-8")
        document_context = hooks.index(f'"{CORE_SCRIPTS[0]}"')

        for script in CORE_SCRIPTS[1:]:
            self.assertLess(
                document_context,
                hooks.index(f'"{script}"'),
                f"Document context must initialize before {script}",
            )

    def test_order_entry_measurement_batch_has_canonical_feature_paths(self):
        hooks = HOOKS.read_text(encoding="utf-8")
        positions = []

        for script in ORDER_ENTRY_SCRIPTS:
            source = ROOT / script
            self.assertTrue(source.exists(), f"Missing migrated asset: {script}")
            self.assertEqual(
                hooks.count(f'"{script}"'),
                1,
                f"{script} must have one canonical Door Cutting Order asset owner",
            )
            positions.append(hooks.index(f'"{script}"'))

        self.assertEqual(
            positions,
            sorted(positions),
            "Order Entry / Measurements load order changed during migration",
        )

        for old_path in OLD_ORDER_ENTRY_PATHS:
            self.assertNotIn(
                f'"{old_path}"',
                hooks,
                f"Retired root asset path still loaded: {old_path}",
            )

    def test_edge_banding_batch_has_canonical_feature_paths(self):
        hooks = HOOKS.read_text(encoding="utf-8")
        positions = []

        for script in EDGE_BANDING_SCRIPTS:
            source = ROOT / script
            self.assertTrue(source.exists(), f"Missing migrated asset: {script}")
            self.assertEqual(
                hooks.count(f'"{script}"'),
                1,
                f"{script} must have one canonical Door Cutting Order asset owner",
            )
            positions.append(hooks.index(f'"{script}"'))

        self.assertEqual(
            positions,
            sorted(positions),
            "Edge Banding load order changed during migration",
        )

        for old_path in OLD_EDGE_BANDING_PATHS:
            self.assertNotIn(
                f'"{old_path}"',
                hooks,
                f"Retired root edge-banding asset path still loaded: {old_path}",
            )

    def test_cutting_plan_batch_has_canonical_feature_paths(self):
        hooks = HOOKS.read_text(encoding="utf-8")
        positions = []

        for script in CUTTING_PLAN_SCRIPTS:
            source = ROOT / script
            self.assertTrue(source.exists(), f"Missing migrated asset: {script}")
            self.assertEqual(
                hooks.count(f'"{script}"'),
                1,
                f"{script} must have one canonical Door Cutting Order asset owner",
            )
            positions.append(hooks.index(f'"{script}"'))

        self.assertEqual(
            positions,
            sorted(positions),
            "Cutting Plan load order changed during migration",
        )

        for old_path in OLD_CUTTING_PLAN_PATHS:
            self.assertNotIn(
                f'"{old_path}"',
                hooks,
                f"Retired root cutting-plan asset path still loaded: {old_path}",
            )

        self.assertIn(
            '"/assets/almdina_erp/js/door_cutting_order/cutting_plan/secure_dxf_export.js"',
            hooks,
        )
        self.assertIn(
            '"/assets/almdina_erp/js/door_cutting_order/cutting_plan/door_cutting_order_drawing_plan_ux.js"',
            hooks,
        )

    def test_costing_batch_has_canonical_feature_paths(self):
        hooks = HOOKS.read_text(encoding="utf-8")
        positions = []

        for script in COSTING_SCRIPTS:
            source = ROOT / script
            self.assertTrue(source.exists(), f"Missing migrated asset: {script}")
            self.assertEqual(
                hooks.count(f'"{script}"'),
                1,
                f"{script} must have one canonical Door Cutting Order asset owner",
            )
            positions.append(hooks.index(f'"{script}"'))

        self.assertEqual(
            positions,
            sorted(positions),
            "Costing load order changed during migration",
        )

        for old_path in OLD_COSTING_PATHS:
            self.assertNotIn(
                f'"{old_path}"',
                hooks,
                f"Retired root costing asset path still loaded: {old_path}",
            )

    def test_printing_batch_has_canonical_feature_paths(self):
        hooks = HOOKS.read_text(encoding="utf-8")
        positions = []

        for script in PRINTING_SCRIPTS:
            source = ROOT / script
            self.assertTrue(source.exists(), f"Missing migrated asset: {script}")
            self.assertEqual(
                hooks.count(f'"{script}"'),
                1,
                f"{script} must have one canonical Door Cutting Order asset owner",
            )
            positions.append(hooks.index(f'"{script}"'))

        self.assertEqual(
            positions,
            sorted(positions),
            "Printing load order changed during migration",
        )

        for old_path in OLD_PRINTING_PATHS:
            self.assertNotIn(
                f'"{old_path}"',
                hooks,
                f"Retired root printing asset path still loaded: {old_path}",
            )


if __name__ == "__main__":
    unittest.main()
