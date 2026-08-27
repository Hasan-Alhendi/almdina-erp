from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "frontend_assets.py"
GUARD = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "production"
    / "shop_floor_production_surface_guard.js"
)
SHOP_FLOOR = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "production"
    / "shop_floor_order_ux.js"
)


class TestShopFloorRequestStormUX(unittest.TestCase):
    def test_guard_loads_immediately_after_shop_floor_surface(self):
        manifest = ASSETS.read_text(encoding="utf-8")
        shop_floor = '"public/js/door_cutting_order/production/shop_floor_order_ux.js"'
        guard = '"public/js/door_cutting_order/production/shop_floor_production_surface_guard.js"'
        self.assertIn(shop_floor, manifest)
        self.assertIn(guard, manifest)
        self.assertLess(manifest.index(shop_floor), manifest.index(guard))

    def test_recovery_is_bounded_and_reuses_inflight_production_work(self):
        source = GUARD.read_text(encoding="utf-8")
        self.assertIn("MAX_RECOVERY_ATTEMPTS = 3", source)
        self.assertIn("__almdinaProductionActionsPromise", source)
        self.assertIn("if (activePass) return activePass", source)
        self.assertIn("state.attempts >= MAX_RECOVERY_ATTEMPTS", source)
        self.assertIn("context.registerSurface(SURFACE_NAME", source)
        self.assertIn("permissionVersion()", source)
        self.assertIn("stage-ready", source)
        self.assertNotIn("frappe.call", source)

    def test_guard_does_not_change_business_authority(self):
        source = GUARD.read_text(encoding="utf-8")
        # This guard is lifecycle-only. Authorization stays with the server and
        # the existing capability layer; role-name authorization must not leak in.
        for forbidden in (
            "System Manager",
            "Administrator",
            "Order Entry",
            "CNC Worker",
            "Drawing Worker",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("canDocument", source)
        self.assertNotIn("has_role", source)

    def test_legacy_surface_has_the_eager_recovery_pattern_guarded_here(self):
        source = SHOP_FLOOR.read_text(encoding="utf-8")
        self.assertIn('registerSurface("production-actions"', source)
        self.assertIn("recover(frm) { return reconcileProductionActions(frm); }", source)
        self.assertIn("__almdinaProductionActionsPromise", source)
        self.assertIn("settleSurfaces", source)


if __name__ == "__main__":
    unittest.main()
