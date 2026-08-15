from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
FACADE = ROOT / "public/js/door_cutting_order/drawing/special_shape_facade.js"
OLD_FACADE = ROOT / "public/js/door_cutting_order_special_shape_ux.js"
DRAWING_ROOT = ROOT / "public/js/door_drawing_v3"


class TestFrontendDrawingOwnershipContract(unittest.TestCase):
    def test_special_drawing_facade_has_one_feature_owner(self):
        hooks = HOOKS.read_text(encoding="utf-8")
        script = "public/js/door_cutting_order/drawing/special_shape_facade.js"
        old_script = "public/js/door_cutting_order_special_shape_ux.js"

        self.assertTrue(FACADE.exists())
        self.assertFalse(OLD_FACADE.exists())
        self.assertEqual(hooks.count(f'"{script}"'), 1)
        self.assertNotIn(f'"{old_script}"', hooks)

    def test_facade_keeps_drawing_permissions_and_ordered_bootstrap(self):
        source = FACADE.read_text(encoding="utf-8")

        self.assertIn('can(frm, "edit_special_drawing")', source)
        self.assertIn('can(frm, "view_drawing_workspace")', source)
        self.assertIn("SCRIPTS.reduce((promise, src) => promise.then(() => loadScript(src))", source)
        self.assertIn("script.async = false", source)
        self.assertIn("window.AlmdinaDoorDrawingV3", source)

    def test_door_drawing_v3_remains_a_separate_layered_editor(self):
        for layer in ("domain", "application", "infrastructure", "presentation"):
            self.assertTrue((DRAWING_ROOT / layer).is_dir(), f"Missing Door Drawing V3 layer: {layer}")


if __name__ == "__main__":
    unittest.main()
