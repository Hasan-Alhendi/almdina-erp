from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.orders.numeric_input import (
    default_if_missing,
)


class TestNumericInputDefaults(unittest.TestCase):
    def test_missing_values_receive_the_default(self) -> None:
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertEqual(default_if_missing(value, 244), 244)

    def test_explicit_zero_is_never_replaced(self) -> None:
        for value in (0, 0.0, "0"):
            with self.subTest(value=value):
                self.assertEqual(default_if_missing(value, 244), value)

    def test_nonzero_values_are_preserved(self) -> None:
        self.assertEqual(default_if_missing(122, 244), 122)
        self.assertEqual(default_if_missing("10.5", 244), "10.5")


if __name__ == "__main__":
    unittest.main()
