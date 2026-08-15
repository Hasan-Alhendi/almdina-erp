from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"

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

OLD_ORDER_ENTRY_PATHS = tuple(
    f"public/js/{Path(script).name}" for script in ORDER_ENTRY_SCRIPTS
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


if __name__ == "__main__":
    unittest.main()
