from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.services import shop_floor_service as sfs


class TestShopFloorRouting(unittest.TestCase):
    def test_path_sequences(self):
        self.assertEqual(sfs.PATH_SEQUENCE["Sharyoun"], ("Sharyoun", "Sanding"))
        self.assertEqual(sfs.PATH_SEQUENCE["Drawing"], ("Drawing", "CNC", "Sanding"))
        self.assertEqual(sfs._next_stage_type("Sharyoun", "Sharyoun"), "Sanding")
        self.assertIsNone(sfs._next_stage_type("Sharyoun", "Sanding"))
        self.assertEqual(sfs._next_stage_type("Drawing", "Drawing"), "CNC")
        self.assertEqual(sfs._next_stage_type("Drawing", "CNC"), "Sanding")
        self.assertIsNone(sfs._next_stage_type("Drawing", "Sanding"))

    def test_stage_metadata_has_no_fixed_role_map(self):
        self.assertFalse(hasattr(sfs, "STAGE_ROLE"))
        self.assertEqual(sfs.STAGE_DEPARTMENT["Sanding"], "تقشيط")
        self.assertEqual(sfs.STAGE_ORDER_STATUS["Drawing"], "At Drawing")
        self.assertEqual(sfs.DEPARTMENT_STATUS_MAP["Pending"], "بحاجة للعمل")
        self.assertEqual(sfs.DEPARTMENT_STATUS_MAP["In Progress"], "قيد العمل")

    def test_sequence_numbers(self):
        self.assertEqual(sfs._sequence_for_stage("Drawing", "Drawing"), 10)
        self.assertEqual(sfs._sequence_for_stage("Drawing", "CNC"), 20)
        self.assertEqual(sfs._sequence_for_stage("Drawing", "Sanding"), 30)
        self.assertEqual(sfs._sequence_for_stage("Sharyoun", "Sanding"), 20)


if __name__ == "__main__":
    unittest.main()
