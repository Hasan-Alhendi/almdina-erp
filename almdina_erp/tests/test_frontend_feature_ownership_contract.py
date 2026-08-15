from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"

CORE_SCRIPTS = (
    "public/js/door_cutting_order_document_context.js",
    "public/js/door_cutting_order_action_permission_guard.js",
    "public/js/door_cutting_order_toolbar_stability_ux.js",
    "public/js/door_cutting_order_revision_ux.js",
    "public/js/order_lifecycle.js",
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


if __name__ == "__main__":
    unittest.main()
