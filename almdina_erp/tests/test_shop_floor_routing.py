from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    DEPARTMENT_STATUS_BY_STAGE_STATUS,
    PRODUCTION_PATHS,
    STAGE_DEPARTMENTS,
    next_stage_type,
    stage_sequence,
)


class TestShopFloorRouting(unittest.TestCase):
    def test_path_sequences(self):
        self.assertEqual(PRODUCTION_PATHS["Sharyoun"], ("Sharyoun", "Sanding"))
        self.assertEqual(PRODUCTION_PATHS["Drawing"], ("Drawing", "CNC", "Sanding"))
        self.assertEqual(next_stage_type("Sharyoun", "Sharyoun"), "Sanding")
        self.assertIsNone(next_stage_type("Sharyoun", "Sanding"))
        self.assertEqual(next_stage_type("Drawing", "Drawing"), "CNC")
        self.assertEqual(next_stage_type("Drawing", "CNC"), "Sanding")
        self.assertIsNone(next_stage_type("Drawing", "Sanding"))

    def test_stage_metadata_has_no_fixed_role_map(self):
        self.assertEqual(STAGE_DEPARTMENTS["Sanding"], "تقشيط")
        self.assertEqual(DEPARTMENT_STATUS_BY_STAGE_STATUS["Pending"], "بحاجة للعمل")
        self.assertEqual(DEPARTMENT_STATUS_BY_STAGE_STATUS["In Progress"], "قيد العمل")

    def test_sequence_numbers(self):
        self.assertEqual(stage_sequence("Drawing", "Drawing"), 10)
        self.assertEqual(stage_sequence("Drawing", "CNC"), 20)
        self.assertEqual(stage_sequence("Drawing", "Sanding"), 30)
        self.assertEqual(stage_sequence("Sharyoun", "Sanding"), 20)


if __name__ == "__main__":
    unittest.main()
