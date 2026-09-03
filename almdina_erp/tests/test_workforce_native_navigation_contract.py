from __future__ import annotations

import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]


class TestWorkforceNativeNavigationContract(unittest.TestCase):
    def test_new_workforce_users_get_almdina_default_app_only(self) -> None:
        source = (
            APP_ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "workforce_repository.py"
        ).read_text(encoding="utf-8")

        create_source = source.split("def create_user", 1)[1].split(
            "def update_identity", 1
        )[0]
        adopt_source = source.split("def adopt_user", 1)[1].split(
            "def create_user", 1
        )[0]

        self.assertIn("ALMDINA_APP", source)
        self.assertIn('"default_app": ALMDINA_APP', create_source)
        self.assertIn("MEMBERSHIP_FIELD", create_source)
        self.assertNotIn("default_workspace", create_source)
        self.assertNotIn("default_app", adopt_source)

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

    def test_default_app_is_navigation_only_not_membership_authority(self) -> None:
        scope = (
            APP_ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "factory_user_scope.py"
        ).read_text(encoding="utf-8")

        self.assertIn('ALMDINA_APP = "almdina_erp"', scope)
        self.assertIn('ALMDINA_WORKSPACE = "Almdina ERP"', scope)
        self.assertNotIn("def is_almdina_user", scope)

        app_source = APP_ROOT / "almdina_erp"
        for path in app_source.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "is_almdina_user",
                source,
                f"default_app membership authority returned in {path}",
            )

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
