"""Board-editor flip / angle-mirror transform contract."""

from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    DraftLayoutError,
    normalize_layout,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_transform import (
    apply_draft_parity_to_entry,
    apply_local_horizontal_mirror,
    apply_piece_angle_mirror,
    apply_piece_board_flip,
    draft_flip_h,
    draft_mirrored,
)


def _rect_piece(**overrides):
    piece = {
        "piece_key": "instance:a",
        "piece_instance_id": "pi-a",
        "piece_id": 1,
        "piece_type": "Regular",
        "editable": True,
        "allow_rotation": True,
        "allow_rotation_proven": True,
        "distribution": "active",
        "sheet_no": 1,
        "rotation_deg": 0,
        "flip_h": False,
        "flip_v": False,
        "mirrored": False,
        "local_x_mm": 100,
        "local_y_mm": 120,
        "base_outline_mm": [[100, 120], [140, 120], [140, 180], [100, 180]],
        "outline_mm": [[100, 120], [140, 120], [140, 180], [100, 180]],
        "pivot_mm": {"x": 120, "y": 150},
        "machining_paths": [],
    }
    piece.update(overrides)
    return piece


def _session(piece, *, machine_type="CNC Router"):
    return {
        "pieces": {piece["piece_key"]: piece},
        "boards": {
            "1": {
                "sheet_no": 1,
                "origin_x_mm": 0,
                "origin_y_mm": 0,
                "trim_x_mm": 0,
                "trim_y_mm": 0,
                "usable_width_mm": 2800,
                "usable_length_mm": 2100,
            }
        },
        "kerf_mm": 0,
        "machine_type": machine_type,
        "stale_cut_path_sheets": [],
        "stale_unbound_text_sheets": [],
    }


class BoardEditorTransformTests(unittest.TestCase):
    def test_angle_mirror_twice_restores_shape(self):
        piece = _rect_piece(piece_type="Clipped Corner")
        original = [list(point) for point in piece["base_outline_mm"]]
        apply_local_horizontal_mirror(piece)
        self.assertTrue(piece["mirrored"])
        self.assertNotEqual(piece["base_outline_mm"], original)
        apply_local_horizontal_mirror(piece)
        self.assertFalse(piece["mirrored"])
        for left, right in zip(piece["base_outline_mm"], original):
            self.assertAlmostEqual(left[0], right[0], places=4)
            self.assertAlmostEqual(left[1], right[1], places=4)

    def test_plus_thirty_sequence_and_board_flip_conjugation(self):
        piece = _rect_piece(rotation_deg=0)
        session = _session(piece)
        first = apply_piece_board_flip(session, piece_key="instance:a", axis="h")
        self.assertTrue(first["pieces"]["instance:a"]["flip_h"])
        # From 45°, board H flip conjugates to 315° with flip_h set.
        angled = _rect_piece(rotation_deg=45)
        flipped = apply_piece_board_flip(_session(angled), piece_key="instance:a", axis="h")
        self.assertAlmostEqual(flipped["pieces"]["instance:a"]["rotation_deg"], 315.0, places=4)
        self.assertTrue(flipped["pieces"]["instance:a"]["flip_h"])

    def test_draft_accepts_transform_parity_and_rejects_legacy_aliases(self):
        catalog = {
            "pieces": {
                "pi-a": {
                    "piece_id": 1,
                    "allow_rotation": True,
                    "glass_host_piece_id": None,
                    "piece_type": "Clipped Corner",
                }
            },
            "source_sheet_nos": [1],
        }
        layout = {
            "schema": 1,
            "pieces": [
                {
                    "piece_instance_id": "pi-a",
                    "sheet_no": 1,
                    "local_x_mm": 10,
                    "local_y_mm": 20,
                    "rotation_deg": 30,
                    "flip_h": True,
                    "flip_v": False,
                    "mirrored": True,
                    "distribution": "active",
                    "exclusion_reason": None,
                    "glass_host_piece_id": None,
                }
            ],
            "boards": [
                {"sheet_no": 1, "origin_x_mm": 0, "origin_y_mm": 36, "user_moved": False}
            ],
        }
        normalized = normalize_layout(layout, catalog)
        self.assertTrue(draft_flip_h(normalized["pieces"][0]))
        self.assertTrue(draft_mirrored(normalized["pieces"][0]))

        legacy = {
            "schema": 1,
            "pieces": [
                {
                    "piece_instance_id": "pi-a",
                    "sheet_no": 1,
                    "local_x_mm": 10,
                    "local_y_mm": 20,
                    "rotation_deg": 0,
                    "distribution": "active",
                    "exclusion_reason": None,
                    "glass_host_piece_id": None,
                }
            ],
            "boards": [
                {"sheet_no": 1, "origin_x_mm": 0, "origin_y_mm": 36, "user_moved": False}
            ],
        }
        old = normalize_layout(legacy, catalog)
        self.assertFalse(old["pieces"][0]["flip_h"])
        self.assertFalse(old["pieces"][0]["mirrored"])

        bad = dict(layout)
        bad["pieces"] = [dict(layout["pieces"][0])]
        bad["pieces"][0]["mirror"] = True
        with self.assertRaises(DraftLayoutError) as ctx:
            normalize_layout(bad, catalog)
        self.assertEqual(ctx.exception.code, "forbidden_field")

    def test_draft_parity_then_angle_mirror_roundtrip(self):
        piece = _rect_piece(piece_type="L-Shaped Corner")
        apply_draft_parity_to_entry(piece, {"mirrored": True, "flip_h": False, "flip_v": False})
        self.assertTrue(piece["mirrored"])
        session = _session(piece)
        once = apply_piece_angle_mirror(session, piece_key="instance:a")
        self.assertFalse(once["pieces"]["instance:a"]["mirrored"])


if __name__ == "__main__":
    unittest.main()
