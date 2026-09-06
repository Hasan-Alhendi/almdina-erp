from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECTION = ROOT / "almdina_erp" / "services" / "notes_projection_service.py"


class TestA156ProjectionConcurrency(unittest.TestCase):
    def test_dco_save_serializes_with_pin_and_unpin(self) -> None:
        source = PROJECTION.read_text(encoding="utf-8")
        body = source.split("def preserve_order_projection_on_save", 1)[1].split(
            "def refresh_important_projection_from_comment",
            1,
        )[0]
        self.assertIn("_repository.lock_reference(ORDER_DOCTYPE, name)", body)
        self.assertLess(
            body.index("_repository.lock_reference(ORDER_DOCTYPE, name)"),
            body.index("_repository.order_projection(name)"),
        )

    def test_native_comment_refresh_checks_pointer_under_order_lock(self) -> None:
        source = PROJECTION.read_text(encoding="utf-8")
        body = source.split("def refresh_important_projection_from_comment", 1)[1].split(
            "def clear_important_projection_for_deleted_comment",
            1,
        )[0]
        self.assertIn(
            "_repository.lock_reference(ORDER_DOCTYPE, order_name)",
            body,
        )
        self.assertLess(
            body.index("_repository.lock_reference(ORDER_DOCTYPE, order_name)"),
            body.index("_repository.order_projection(order_name)"),
        )

    def test_native_comment_delete_checks_pointer_under_order_lock(self) -> None:
        source = PROJECTION.read_text(encoding="utf-8")
        body = source.split("def clear_important_projection_for_deleted_comment", 1)[1]
        self.assertIn(
            "_repository.lock_reference(ORDER_DOCTYPE, order_name)",
            body,
        )
        self.assertLess(
            body.index("_repository.lock_reference(ORDER_DOCTYPE, order_name)"),
            body.index("_repository.order_projection(order_name)"),
        )


if __name__ == "__main__":
    unittest.main()
