from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.revisions import (
    RevisionNotAllowed,
    assert_revision_allowed,
    can_create_revision,
    next_revision,
    revision_root,
)


class TestOrderRevisionDomain(unittest.TestCase):
    def test_approved_and_active_production_orders_can_create_revisions(self) -> None:
        for status in ("Approved", "At Drawing", "At CNC", "Cutting In Progress", "Completed"):
            with self.subTest(status=status):
                self.assertTrue(can_create_revision(status))
                assert_revision_allowed(status)

    def test_editable_and_terminal_orders_cannot_create_revisions(self) -> None:
        for status in (None, "Draft", "Pending Review", "Rejected", "Delivered", "Cancelled"):
            with self.subTest(status=status):
                self.assertFalse(can_create_revision(status))
                with self.assertRaises(RevisionNotAllowed):
                    assert_revision_allowed(status)

    def test_revision_number_and_root_are_deterministic(self) -> None:
        self.assertEqual(next_revision(None), 2)
        self.assertEqual(next_revision("4"), 5)
        self.assertEqual(revision_root(order_name="DCO-1", current_root=None), "DCO-1")
        self.assertEqual(revision_root(order_name="DCO-2", current_root="DCO-1"), "DCO-1")

    def test_domain_module_has_no_frappe_dependency(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "almdina_erp"
            / "domain"
            / "orders"
            / "revisions.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)


if __name__ == "__main__":
    unittest.main()
