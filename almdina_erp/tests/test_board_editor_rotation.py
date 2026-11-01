"""Domain contracts for Board Editor free rotation."""

from __future__ import annotations

import math
import unittest

from almdina_erp.almdina_erp.domain.cutting.board_editor_rotation import (
    ROTATE_BLOCK_GUEST_FORBIDDEN,
    ROTATE_BLOCK_NOT_ALLOWED,
    angles_equivalent,
    apply_piece_rotation,
    ensure_base_geometry,
    normalize_angle_deg,
    piece_rotation_eligibility,
    rotate_point,
    validate_piece_rotation,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_session_edit import (
    DROP_KERF,
    DROP_OVERLAP,
    DROP_PARTIAL_BOARD,
    apply_piece_move,
    piece_footprint_mm,
    validate_piece_drop,
)


def _rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _piece(
    key,
    *,
    piece_id,
    x,
    y,
    w,
    h,
    allow=True,
    host=None,
    hole=None,
    editable=True,
):
    outline = _rect(x, y, w, h)
    piece = {
        "piece_key": key,
        "piece_id": piece_id,
        "piece_instance_id": key.replace("instance:", ""),
        "sheet_no": 1,
        "local_x_mm": x,
        "local_y_mm": y,
        "placement_cm": {"x": x / 10, "y": y / 10, "w": w / 10, "h": h / 10, "rotated": False},
        "outline_mm": outline,
        "base_outline_mm": [row[:] for row in outline],
        "pivot_mm": {"x": x + w / 2, "y": y + h / 2},
        "entry_pivot_mm": {"x": x + w / 2, "y": y + h / 2},
        "rotation_deg": 0,
        "editable": editable,
        "allow_rotation": allow,
        "allow_rotation_proven": True,
        "glass_host_key": host,
        "glass_host_piece_id": None,
        "piece_type": "Regular",
        "apply_rotated_to_geometry": False,
        "source_orientation_applied": True,
        "source_rotated_dims": False,
    }
    if hole is not None:
        piece["glass_hole_local_mm"] = hole
        piece["base_hole_mm"] = [row[:] for row in hole]
    return piece


def _session(pieces):
    return {
        "boards": {
            "1": {
                "sheet_no": 1,
                "origin_x_mm": 0,
                "origin_y_mm": 36,
                "width_mm": 2000,
                "height_mm": 2000,
                "trim_x_mm": 0,
                "trim_y_mm": 0,
                "usable_width_mm": 2000,
                "usable_length_mm": 2000,
                "title_band_mm": 36,
            }
        },
        "pieces": pieces,
        "kerf_mm": 4,
        "stale_cut_path_sheets": [],
        "stale_unbound_text_sheets": [],
    }


class TestBoardEditorRotation(unittest.TestCase):
    def test_normalize_and_zero_crossing(self):
        self.assertEqual(normalize_angle_deg(360), 0)
        self.assertEqual(normalize_angle_deg(-90), 270)
        self.assertTrue(angles_equivalent(359.999999, 0, eps=1e-4))
        self.assertTrue(angles_equivalent(37, 37 + 360))

    def test_rect_37_then_move_and_snap_edges(self):
        session = _session(
            {
                "instance:a": _piece("instance:a", piece_id=1, x=100, y=100, w=200, h=100),
                "instance:c": _piece("instance:c", piece_id=3, x=500, y=500, w=100, h=100),
            }
        )
        decision = validate_piece_rotation(session, piece_key="instance:a", rotation_deg=37)
        self.assertTrue(decision["ok"], decision)
        next_session = apply_piece_rotation(session, piece_key="instance:a", rotation_deg=37)
        piece = next_session["pieces"]["instance:a"]
        self.assertTrue(angles_equivalent(piece["rotation_deg"], 37))
        self.assertEqual(piece["piece_type"], "Regular")
        # Manufacturing placement size stays original; AABB may grow.
        self.assertEqual(piece["placement_cm"]["w"], 20)
        self.assertEqual(piece["placement_cm"]["h"], 10)
        # Derive again from base — no cumulative drift after second apply of same angle.
        again = apply_piece_rotation(next_session, piece_key="instance:a", rotation_deg=37)
        self.assertEqual(again["pieces"]["instance:a"]["outline_mm"], piece["outline_mm"])

        from almdina_erp.almdina_erp.domain.cutting.board_editor_session_edit import (
            _world_footprint,
        )

        world = _world_footprint(again["pieces"]["instance:a"], again["boards"])
        drop = validate_piece_drop(
            piece=again["pieces"]["instance:a"],
            pieces=again["pieces"],
            boards=again["boards"],
            world_x_mm=world["bounds"]["x"] + 40,
            world_y_mm=world["bounds"]["y"] + 20,
            kerf_mm=4,
        )
        self.assertTrue(drop["ok"], drop)
        moved = apply_piece_move(
            again,
            piece_key="instance:a",
            sheet_no=drop["sheet_no"],
            local_x_mm=drop["local_x_mm"],
            local_y_mm=drop["local_y_mm"],
            delta_x_mm=drop["delta_x_mm"],
            delta_y_mm=drop["delta_y_mm"],
        )
        self.assertTrue(angles_equivalent(moved["pieces"]["instance:a"]["rotation_deg"], 37))
        # Edges remain the rotated outline edges (not AABB box sides alone).
        fp = piece_footprint_mm(moved["pieces"]["instance:a"])
        self.assertEqual(fp["kind"], "polygon")
        self.assertGreaterEqual(len(fp["points"]), 4)

    def test_cardinal_and_full_turn(self):
        session = _session(
            {"instance:a": _piece("instance:a", piece_id=1, x=200, y=200, w=120, h=80)}
        )
        for angle in (90, 180, 270, 360):
            decision = validate_piece_rotation(session, piece_key="instance:a", rotation_deg=angle)
            self.assertTrue(decision["ok"], (angle, decision))
            session = apply_piece_rotation(session, piece_key="instance:a", rotation_deg=angle)
            expected = 0 if angle == 360 else angle
            self.assertTrue(
                angles_equivalent(session["pieces"]["instance:a"]["rotation_deg"], expected)
            )

    def test_l_shape_and_special_with_geometry(self):
        l_outline = [
            [50, 50],
            [200, 50],
            [200, 100],
            [100, 100],
            [100, 200],
            [50, 200],
        ]
        piece = _piece("instance:l", piece_id=4, x=50, y=50, w=150, h=150)
        piece["outline_mm"] = l_outline
        piece["base_outline_mm"] = [row[:] for row in l_outline]
        piece["pivot_mm"] = {"x": 125, "y": 125}
        piece["entry_pivot_mm"] = {"x": 125, "y": 125}
        piece["piece_type"] = "L"
        session = _session({"instance:l": piece})
        decision = validate_piece_rotation(session, piece_key="instance:l", rotation_deg=45)
        self.assertTrue(decision["ok"], decision)
        next_session = apply_piece_rotation(session, piece_key="instance:l", rotation_deg=45)
        self.assertEqual(next_session["pieces"]["instance:l"]["piece_type"], "L")

    def test_glass_host_and_nested_guests(self):
        host = _piece("instance:host", piece_id=1, x=100, y=100, w=400, h=400)
        host["glass_hole_local_mm"] = _rect(150, 150, 200, 200)
        host["base_hole_mm"] = _rect(150, 150, 200, 200)
        guest = _piece(
            "instance:guest",
            piece_id=2,
            x=180,
            y=180,
            w=80,
            h=80,
            host="instance:host",
        )
        nested = _piece(
            "instance:nested",
            piece_id=3,
            x=200,
            y=200,
            w=30,
            h=30,
            host="instance:guest",
        )
        session = _session(
            {
                "instance:host": host,
                "instance:guest": guest,
                "instance:nested": nested,
            }
        )
        decision = validate_piece_rotation(session, piece_key="instance:host", rotation_deg=30)
        self.assertTrue(decision["ok"], decision)
        next_session = apply_piece_rotation(session, piece_key="instance:host", rotation_deg=30)
        host2 = next_session["pieces"]["instance:host"]
        guest2 = next_session["pieces"]["instance:guest"]
        nested2 = next_session["pieces"]["instance:nested"]
        self.assertTrue(angles_equivalent(host2["rotation_deg"], 30))
        self.assertTrue(angles_equivalent(guest2["rotation_deg"], 30))
        self.assertTrue(angles_equivalent(nested2["rotation_deg"], 30))
        self.assertEqual(guest2["glass_host_key"], "instance:host")
        self.assertEqual(nested2["glass_host_key"], "instance:guest")
        # Guest pivot followed the host rigid motion (not left at the entry seat).
        expected_guest_pivot = rotate_point(
            [180 + 40, 180 + 40],
            host["pivot_mm"],
            30,
        )
        self.assertAlmostEqual(guest2["pivot_mm"]["x"], expected_guest_pivot[0], places=5)
        self.assertAlmostEqual(guest2["pivot_mm"]["y"], expected_guest_pivot[1], places=5)

    def test_allow_rotation_fail_closed_and_guest_blocks_host(self):
        host = _piece("instance:host", piece_id=1, x=100, y=100, w=300, h=300, allow=True)
        host["glass_hole_local_mm"] = _rect(140, 140, 120, 120)
        host["base_hole_mm"] = _rect(140, 140, 120, 120)
        guest = _piece(
            "instance:guest",
            piece_id=2,
            x=160,
            y=160,
            w=40,
            h=40,
            allow=False,
            host="instance:host",
        )
        session = _session({"instance:host": host, "instance:guest": guest})
        eligibility = piece_rotation_eligibility(host, pieces=session["pieces"])
        self.assertFalse(eligibility["rotatable"])
        self.assertEqual(eligibility["reason"], ROTATE_BLOCK_GUEST_FORBIDDEN)

        locked = _piece("instance:x", piece_id=9, x=50, y=50, w=40, h=40, allow=False)
        self.assertEqual(
            piece_rotation_eligibility(locked)["reason"],
            ROTATE_BLOCK_NOT_ALLOWED,
        )
        missing = dict(locked)
        missing.pop("allow_rotation")
        missing.pop("allow_rotation_proven")
        self.assertEqual(
            piece_rotation_eligibility(missing)["reason"],
            ROTATE_BLOCK_NOT_ALLOWED,
        )

    def test_reject_partial_board_and_overlap_not_aabb_only(self):
        a = _piece("instance:a", piece_id=1, x=10, y=10, w=100, h=20)
        # Place near the usable edge so 90° rotation clips partially.
        edge = _piece("instance:edge", piece_id=2, x=1950, y=100, w=40, h=200)
        session = _session({"instance:a": a, "instance:edge": edge})
        decision = validate_piece_rotation(session, piece_key="instance:edge", rotation_deg=90)
        self.assertFalse(decision["ok"])
        self.assertIn(decision["code"], {DROP_PARTIAL_BOARD, "outside_usable_sheet"})

        # Two diamonds whose AABBs intersect after rotation but material may clear —
        # construct thin bars that overlap in AABB after rotation yet keep polygon gap.
        left = _piece("instance:left", piece_id=3, x=100, y=200, w=200, h=20)
        right = _piece("instance:right", piece_id=4, x=250, y=100, w=20, h=200)
        session2 = _session({"instance:left": left, "instance:right": right})
        # Rotate left 90° around centre → tall bar that would AABB-hit right.
        # With kerf 4, if polygons don't overlap and AABB clearance fails → KERF.
        # Place so after rotation polygons do not overlap and AABB still has clearance.
        far = _piece("instance:far", piece_id=5, x=800, y=100, w=20, h=200)
        session3 = _session({"instance:left": left, "instance:far": far})
        ok = validate_piece_rotation(session3, piece_key="instance:left", rotation_deg=90)
        self.assertTrue(ok["ok"], ok)

        # True material overlap must reject.
        blocker = _piece("instance:block", piece_id=6, x=150, y=150, w=80, h=80)
        session4 = _session({"instance:left": left, "instance:block": blocker})
        bad = validate_piece_rotation(session4, piece_key="instance:left", rotation_deg=90)
        self.assertFalse(bad["ok"])
        self.assertIn(bad["code"], {DROP_OVERLAP, DROP_KERF})

    def test_dxf_oriented_geometry_not_double_rotated(self):
        # Entry geometry already oriented; source_rotated_dims is metadata only.
        outline = _rect(40, 40, 100, 50)
        piece = _piece("instance:dxf", piece_id=7, x=40, y=40, w=100, h=50)
        piece["outline_mm"] = outline
        piece["base_outline_mm"] = [row[:] for row in outline]
        piece["source_rotated_dims"] = True
        piece["placement_cm"]["rotated"] = True
        piece["apply_rotated_to_geometry"] = False
        piece["source_orientation_applied"] = True
        ensure_base_geometry(piece)
        session = _session({"instance:dxf": piece})
        next_session = apply_piece_rotation(session, piece_key="instance:dxf", rotation_deg=15)
        out = next_session["pieces"]["instance:dxf"]["outline_mm"]
        # Base stayed the entry outline; only one 15° edit applied.
        self.assertEqual(
            next_session["pieces"]["instance:dxf"]["base_outline_mm"],
            outline,
        )
        expected = [
            rotate_point(point, piece["pivot_mm"], 15) for point in outline
        ]
        for got, want in zip(out, expected):
            self.assertAlmostEqual(got[0], want[0], places=6)
            self.assertAlmostEqual(got[1], want[1], places=6)

    def test_noop_equivalent_angle_and_identity_stable(self):
        session = _session(
            {"instance:a": _piece("instance:a", piece_id=1, x=120, y=120, w=60, h=60)}
        )
        session = apply_piece_rotation(session, piece_key="instance:a", rotation_deg=40)
        decision = validate_piece_rotation(session, piece_key="instance:a", rotation_deg=400)
        self.assertTrue(decision["ok"])
        self.assertTrue(decision["noop"])
        before = session["pieces"]["instance:a"]["piece_instance_id"]
        after = apply_piece_rotation(session, piece_key="instance:a", rotation_deg=400)
        self.assertEqual(after["pieces"]["instance:a"]["piece_instance_id"], before)
        self.assertEqual(after["pieces"]["instance:a"]["piece_type"], "Regular")


if __name__ == "__main__":
    unittest.main()
