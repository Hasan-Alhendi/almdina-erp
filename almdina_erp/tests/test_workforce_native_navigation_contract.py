from __future__ import annotations

import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]


class TestWorkforceNativeNavigationContract(unittest.TestCase):
    def test_workforce_repository_does_not_write_frappe_navigation_defaults(self) -> None:
        source = (
            APP_ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "workforce_repository.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn('user.default_app = "almdina_erp"', source)
        self.assertNotIn('user.default_workspace = "Almdina ERP"', source)
        self.assertNotIn('"default_app": "almdina_erp"', source)
        self.assertNotIn('"default_workspace": "Almdina ERP"', source)
        self.assertIn("MEMBERSHIP_FIELD", source)

    def test_shop_floor_assignees_use_workforce_membership_not_navigation(self) -> None:
        source = (
            APP_ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "shop_floor_authorization.py"
        ).read_text(encoding="utf-8")

        self.assertIn("MEMBERSHIP_FIELD", source)
        self.assertIn("user_row.get(MEMBERSHIP_FIELD)", source)
        self.assertIn("coalesce(u.`{MEMBERSHIP_FIELD}`, 0) = 1", source)
        self.assertNotIn("default_app", source)
        self.assertNotIn("ALMDINA_APP", source)
        self.assertNotIn("is_almdina_user", source)

    def test_app_card_uses_the_workspace_slug_route(self) -> None:
        hooks = (APP_ROOT / "hooks.py").read_text(encoding="utf-8")
        self.assertIn('"route": "/desk/almdina-erp"', hooks)

    def test_no_role_home_page_is_seeded_by_the_new_navigation_foundation(self) -> None:
        membership = (
            APP_ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "workforce_membership.py"
        ).read_text(encoding="utf-8")
        native_navigation = (
            APP_ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "native_app_navigation.py"
        ).read_text(encoding="utf-8")

        for forbidden_write in (
            'set_value("Role"',
            "set_value('Role'",
            'db_set("home_page"',
            "db_set('home_page'",
            'set_value("User",',
            "set_value('User',",
            'default_workspace =',
            'default_app =',
        ):
            self.assertNotIn(forbidden_write, membership)

        self.assertNotIn("Role", native_navigation)
        self.assertNotIn("home_page", native_navigation)


if __name__ == "__main__":
    unittest.main()
