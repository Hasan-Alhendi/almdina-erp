"""Pure cut-direction rules must not alter geometry or old DXF outputs."""
from __future__ import annotations

import math
import unittest

from almdina_erp.almdina_erp.domain.cam.cut_direction import (
    CutDirectionError,
    orient_path,
    stable_path_id,
)


class TestCutDirectionContract(unittest.TestCase):
    def test_reverse_open_path_preserves_segments_and_input(self):
        original = [(10, 20), (10, 40), (14, 40)]
        self.assertEqual(orient_path(original, closed=False, reverse=True),
                         ((14, 40), (10, 40), (10, 20)))
        self.assertEqual(original, [(10, 20), (10, 40), (14, 40)])

    def test_open_path_can_select_only_endpoints(self):
        line = [(0, 0), (5, 0), (5, 10)]
        self.assertEqual(orient_path(line, closed=False, start_vertex=2),
                         ((5, 10), (5, 0), (0, 0)))
        with self.assertRaisesRegex(CutDirectionError, "open_path_requires_endpoint"):
            orient_path(line, closed=False, start_vertex=1)

    def test_ring_start_and_orientation_preserve_geometry(self):
        square = [(0, 0), (100, 0), (100, 30), (0, 30)]
        self.assertEqual(orient_path(square, closed=True, start_vertex=2),
                         ((100, 30), (0, 30), (0, 0), (100, 0)))
        self.assertEqual(orient_path(square, closed=True, reverse=True, start_vertex=2),
                         ((100, 30), (100, 0), (0, 0), (0, 30)))

    def test_closed_terminal_duplicate_is_normalized(self):
        self.assertEqual(orient_path([(0, 0), (3, 0), (3, 3), (0, 0)], closed=True),
                         ((0, 0), (3, 0), (3, 3)))

    def test_ids_stable_under_start_rotation_and_reversal(self):
        ring = [(0, 0), (10, 0), (10, 20), (0, 20)]
        key = stable_path_id(1, ring, closed=True)
        self.assertEqual(key, stable_path_id(1, ring[2:] + ring[:2], closed=True))
        self.assertEqual(key, stable_path_id(1, ring[::-1], closed=True))
        self.assertNotEqual(key, stable_path_id(2, ring, closed=True))
        self.assertEqual(stable_path_id(1, ring[:3], closed=False),
                         stable_path_id(1, ring[:3][::-1], closed=False))

    def test_open_and_closed_are_different_paths(self):
        vertices = [(0, 0), (10, 0), (10, 20)]
        self.assertNotEqual(stable_path_id(1, vertices, closed=False),
                            stable_path_id(1, vertices, closed=True))

    def test_invalid_geometry_rejected(self):
        for points, closed in (
            ([(0, 0)], False),
            ([(0, 0), (0, 0)], False),
            ([(0, 0), (float("nan"), 1)], False),
            ([(0, 0), (math.inf, 1)], False),
            ([(0, 0), (1_000_001, 1)], False),
        ):
            with self.subTest(points=points):
                with self.assertRaises(CutDirectionError):
                    orient_path(points, closed=closed)

    def test_invalid_direction_and_conflicting_start_rejected(self):
        points = [(0, 0), (1, 0), (2, 0)]
        with self.assertRaises(CutDirectionError):
            orient_path(points, closed=False, reverse=1)
        with self.assertRaises(CutDirectionError):
            orient_path(points, closed=False, reverse=True, start_vertex=0)
        with self.assertRaises(CutDirectionError):
            stable_path_id(True, points, closed=False)


if __name__ == "__main__":
    unittest.main()
