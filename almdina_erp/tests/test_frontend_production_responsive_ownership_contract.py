from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"

PRODUCTION_SCRIPT = "public/js/door_cutting_order/production/shop_floor_order_ux.js"
HEADER_SCRIPT = "public/js/door_cutting_order/responsive/door_cutting_order_header_ux.js"
MOBILE_CARDS_SCRIPT = "public/js/door_cutting_order/responsive/door_cutting_order_mobile_cards_ux.js"

OLD_ROOT_PATHS = (
    "public/js/shop_floor_order_ux.js",
    "public/js/door_cutting_order_header_ux.js",
    "public/js/door_cutting_order_mobile_cards_ux.js",
)


class TestFrontendProductionResponsiveOwnershipContract(unittest.TestCase):
    def test_production_and_responsive_assets_have_canonical_feature_paths(self):
        hooks = HOOKS.read_text(encoding="utf-8")

        for script in (HEADER_SCRIPT, PRODUCTION_SCRIPT, MOBILE_CARDS_SCRIPT):
            self.assertTrue((ROOT / script).exists(), f"Missing migrated asset: {script}")
            self.assertEqual(
                hooks.count(f'"{script}"'),
                1,
                f"{script} must have one canonical Door Cutting Order asset owner",
            )

        for old_path in OLD_ROOT_PATHS:
            self.assertFalse((ROOT / old_path).exists(), f"Retired root asset still exists: {old_path}")
            self.assertNotIn(
                f'"{old_path}"',
                hooks,
                f"Retired root asset path is still loaded: {old_path}",
            )

    def test_existing_form_load_order_is_preserved(self):
        hooks = HOOKS.read_text(encoding="utf-8")

        header = hooks.index(f'"{HEADER_SCRIPT}"')
        production = hooks.index(f'"{PRODUCTION_SCRIPT}"')
        mobile_cards = hooks.index(f'"{MOBILE_CARDS_SCRIPT}"')

        self.assertLess(header, production)
        self.assertLess(production, mobile_cards)

    def test_production_owner_keeps_worker_scope_and_revision_owns_edit_mode(self):
        production = (ROOT / PRODUCTION_SCRIPT).read_text(encoding="utf-8")
        revision = (
            ROOT
            / "public/js/door_cutting_order/core/door_cutting_order_revision_ux.js"
        ).read_text(encoding="utf-8")

        self.assertIn("frm.doc.current_assignee === frappe.session.user", production)
        self.assertIn("context.profile() === \"shop_floor\"", production)
        presentation = production.split("function applyShopFloorPresentation", 1)[1].split(
            "function openDispatchDialog", 1
        )[0]
        self.assertNotIn("frm.enable_save(", presentation)
        self.assertNotIn("frm.disable_save(", presentation)

        show_edit = revision.split("function canShowEditAction", 1)[1].split(
            "function primaryActionLabel", 1
        )[0]
        self.assertIn('(frm.doc.status || "Draft") !== "Draft"', show_edit)


if __name__ == "__main__":
    unittest.main()
