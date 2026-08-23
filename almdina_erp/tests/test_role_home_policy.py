from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.security.role_home_policy import (
    analyze_role_home_pages,
    normalize_home_route,
)


class TestRoleHomePolicy(unittest.TestCase):
    def test_blank_home_pages_do_not_create_a_route(self) -> None:
        policy = analyze_role_home_pages(
            ("Operator", "Reviewer"),
            {"Operator": "", "Reviewer": None},
        )
        self.assertEqual(policy.routes, ())
        self.assertFalse(policy.has_conflict)

    def test_same_home_page_across_roles_is_not_a_conflict(self) -> None:
        policy = analyze_role_home_pages(
            ("Operator", "Reviewer"),
            {"Operator": "desk/orders", "Reviewer": "/desk/orders"},
        )
        self.assertEqual(policy.routes, ("/desk/orders",))
        self.assertFalse(policy.has_conflict)

    def test_different_role_home_pages_are_reported_as_conflict(self) -> None:
        policy = analyze_role_home_pages(
            ("Operator", "Reviewer"),
            {"Operator": "/desk/orders", "Reviewer": "/desk/review"},
        )
        self.assertEqual(policy.routes, ("/desk/orders", "/desk/review"))
        self.assertTrue(policy.has_conflict)

    def test_external_home_page_is_preserved(self) -> None:
        self.assertEqual(
            normalize_home_route("https://example.com/start"),
            "https://example.com/start",
        )


if __name__ == "__main__":
    unittest.main()
