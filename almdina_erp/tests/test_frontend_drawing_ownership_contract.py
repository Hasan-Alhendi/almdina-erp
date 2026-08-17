from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "frontend_assets.py"
FACADE = ROOT / "public/js/door_cutting_order/drawing/special_shape_facade.js"
V4_BOOTSTRAP = ROOT / "public/js/door_drawing_v4/bootstrap.js"
OLD_FACADE = ROOT / "public/js/door_cutting_order_special_shape_ux.js"
DRAWING_V3_ROOT = ROOT / "public/js/door_drawing_v3"
DRAWING_V4_ROOT = ROOT / "public/js/door_drawing_v4"


class TestFrontendDrawingOwnershipContract(unittest.TestCase):
    def test_special_drawing_facade_has_one_feature_owner(self):
        hooks = HOOKS.read_text(encoding="utf-8")
        script = "public/js/door_cutting_order/drawing/special_shape_facade.js"
        old_script = "public/js/door_cutting_order_special_shape_ux.js"

        self.assertTrue(FACADE.exists())
        self.assertFalse(OLD_FACADE.exists())
        self.assertEqual(hooks.count(f'"{script}"'), 1)
        self.assertNotIn(f'"{old_script}"', hooks)

    def test_facade_keeps_drawing_permissions_and_delegates_ordered_v4_bootstrap(self):
        source = FACADE.read_text(encoding="utf-8")
        bootstrap = V4_BOOTSTRAP.read_text(encoding="utf-8")

        self.assertIn('can(frm, "edit_special_drawing")', source)
        self.assertIn('can(frm, "view_drawing_workspace")', source)
        self.assertIn('/assets/almdina_erp/js/door_drawing_v4/bootstrap.js', source)
        self.assertIn("bootstrap.boot()", source)
        self.assertIn("script.async = false", source)
        self.assertIn("__doorDrawingV4: true", source)
        self.assertNotIn("window.AlmdinaDoorDrawingV3", source)
        self.assertNotIn("door_drawing_v3/", source)

        self.assertRegex(
            bootstrap,
            re.compile(
                r"SCRIPTS\.reduce\(\s*"
                r"\(promise, src\) => promise\.then\(\(\) => loadScript\(src\)\),\s*"
                r"Promise\.resolve\(\)\s*"
                r"\)"
            ),
        )
        self.assertIn("script.async = false", bootstrap)
        self.assertIn("window.AlmdinaDoorDrawingV4Bootstrap", bootstrap)

    def test_active_v4_and_legacy_v3_remain_separate_layered_editors(self):
        for root, label in ((DRAWING_V4_ROOT, "V4"), (DRAWING_V3_ROOT, "V3")):
            for layer in ("domain", "application", "infrastructure", "presentation"):
                self.assertTrue((root / layer).is_dir(), f"Missing Door Drawing {label} layer: {layer}")


if __name__ == "__main__":
    unittest.main()
