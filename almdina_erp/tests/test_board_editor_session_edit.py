"""Domain rules for Board Editor session-local moves (phase 3)."""

from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.cutting.board_editor_session_edit import (
    DROP_KERF,
    DROP_OVERLAP,
    DROP_PARTIAL_BOARD,
    apply_board_move,
    apply_piece_move,
    piece_edit_eligibility,
    validate_board_placement,
    validate_piece_drop,
)


def _session():
    return {
        "boards": {
            "1": {
                "sheet_no": 1,
                "origin_x_mm": 0,
                "origin_y_mm": 36,
                "width_mm": 1000,
                "height_mm": 1000,
                "trim_x_mm": 0,
                "trim_y_mm": 0,
                "usable_width_mm": 1000,
                "usable_length_mm": 1000,
                "title_band_mm": 36,
                "user_moved": False,
            },
            "2": {
                "sheet_no": 2,
                "origin_x_mm": 1100,
                "origin_y_mm": 36,
                "width_mm": 1000,
                "height_mm": 1000,
                "trim_x_mm": 0,
                "trim_y_mm": 0,
                "usable_width_mm": 1000,
                "usable_length_mm": 1000,
                "title_band_mm": 36,
                "user_moved": False,
            },
        },
        "pieces": {
            "instance:a": {
                "piece_key": "instance:a",
                "piece_id": 1,
                "piece_instance_id": "a",
                "sheet_no": 1,
                "local_x_mm": 50,
                "local_y_mm": 50,
                "placement_cm": {"x": 5, "y": 5, "w": 20, "h": 20},
                "outline_mm": [[50, 50], [250, 50], [250, 250], [50, 250]],
                "editable": True,
                "glass_host_key": None,
                "glass_hole_local_mm": [[80, 80], [180, 80], [180, 180], [80, 180]],
            },
            "instance:b": {
                "piece_key": "instance:b",
                "piece_id": 2,
                "piece_instance_id": "b",
                "sheet_no": 1,
                "local_x_mm": 100,
                "local_y_mm": 100,
                "placement_cm": {"x": 10, "y": 10, "w": 5, "h": 5},
                "outline_mm": [[100, 100], [150, 100], [150, 150], [100, 150]],
                "editable": True,
                "glass_host_key": "instance:a",
                "glass_host_piece_id": 1,
                "source_glass_host_key": "instance:a",
                "source_glass_host_piece_id": 1,
            },
            "instance:c": {
                "piece_key": "instance:c",
                "piece_id": 3,
                "piece_instance_id": "c",
                "sheet_no": 1,
                "local_x_mm": 400,
                "local_y_mm": 400,
                "placement_cm": {"x": 40, "y": 40, "w": 10, "h": 10},
                "outline_mm": [[400, 400], [500, 400], [500, 500], [400, 500]],
                "editable": True,
                "glass_host_key": None,
            },
        },
        "kerf_mm": 4,
        "stale_cut_path_sheets": [],
        "stale_unbound_text_sheets": [],
    }


class TestBoardEditorSessionEdit(unittest.TestCase):
    def test_eligibility_requires_instance_and_geometry(self):
        missing = piece_edit_eligibility({"piece_id": 9, "placement_cm": {"w": 1, "h": 1}})
        self.assertFalse(missing["editable"])
        self.assertEqual(missing["reason"], "missing_piece_instance_id")

        special = piece_edit_eligibility(
            {"piece_id": 9, "piece_instance_id": "s", "placement_cm": {"w": 1, "h": 1}},
            elements=[
                {
                    "piece_id": 9,
                    "kind": "unresolved",
                    "payload": {"reason": "special_geometry_unavailable"},
                }
            ],
        )
        self.assertFalse(special["editable"])
        self.assertEqual(special["reason"], "special_geometry_unavailable")

    def test_move_inside_board_updates_outline_and_guests(self):
        session = _session()
        decision = validate_piece_drop(
            piece=session["pieces"]["instance:a"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=60,
            world_y_mm=36 + 60,
            kerf_mm=session["kerf_mm"],
        )
        self.assertTrue(decision["ok"])
        next_session = apply_piece_move(
            session,
            piece_key="instance:a",
            sheet_no=decision["sheet_no"],
            local_x_mm=decision["local_x_mm"],
            local_y_mm=decision["local_y_mm"],
            delta_x_mm=decision["delta_x_mm"],
            delta_y_mm=decision["delta_y_mm"],
        )
        host = next_session["pieces"]["instance:a"]
        guest = next_session["pieces"]["instance:b"]
        self.assertEqual(host["piece_instance_id"], "a")
        self.assertEqual(
            host["outline_mm"][0][0],
            session["pieces"]["instance:a"]["outline_mm"][0][0] + decision["delta_x_mm"],
        )
        self.assertEqual(
            guest["local_x_mm"],
            session["pieces"]["instance:b"]["local_x_mm"] + decision["delta_x_mm"],
        )
        self.assertEqual(guest["glass_host_key"], "instance:a")
        self.assertIn("1", next_session["stale_cut_path_sheets"])

    def test_partial_drop_and_overlap_rejected(self):
        session = _session()
        partial = validate_piece_drop(
            piece=session["pieces"]["instance:c"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=950,
            world_y_mm=36 + 400,
            kerf_mm=session["kerf_mm"],
        )
        self.assertFalse(partial["ok"])
        self.assertEqual(partial["code"], DROP_PARTIAL_BOARD)

        overlap = validate_piece_drop(
            piece=session["pieces"]["instance:c"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=50,
            world_y_mm=36 + 50,
            kerf_mm=session["kerf_mm"],
        )
        self.assertFalse(overlap["ok"])
        self.assertIn(overlap["code"], {DROP_OVERLAP, DROP_KERF})

    def test_outside_and_board_move(self):
        session = _session()
        outside = validate_piece_drop(
            piece=session["pieces"]["instance:c"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=2500,
            world_y_mm=100,
            kerf_mm=session["kerf_mm"],
        )
        self.assertTrue(outside["ok"])
        self.assertIsNone(outside["sheet_no"])
        moved = apply_piece_move(
            session,
            piece_key="instance:c",
            sheet_no=None,
            local_x_mm=outside["local_x_mm"],
            local_y_mm=outside["local_y_mm"],
            delta_x_mm=outside["delta_x_mm"],
            delta_y_mm=outside["delta_y_mm"],
        )
        self.assertIsNone(moved["pieces"]["instance:c"]["sheet_no"])

        board_ok = validate_board_placement(
            session["boards"],
            sheet_no=1,
            origin_x_mm=20,
            origin_y_mm=80,
        )
        self.assertTrue(board_ok["ok"])
        after_board = apply_board_move(session, sheet_no=1, origin_x_mm=20, origin_y_mm=80)
        self.assertEqual(after_board["boards"]["1"]["origin_x_mm"], 20)
        self.assertTrue(after_board["boards"]["1"]["user_moved"])
        self.assertEqual(after_board["pieces"]["instance:a"]["local_x_mm"], 50)

        board_bad = validate_board_placement(
            after_board["boards"],
            sheet_no=1,
            origin_x_mm=1050,
            origin_y_mm=36,
        )
        self.assertFalse(board_bad["ok"])

    def test_detach_guest_when_leaving_host(self):
        session = _session()
        decision = validate_piece_drop(
            piece=session["pieces"]["instance:b"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=600,
            world_y_mm=36 + 600,
            kerf_mm=session["kerf_mm"],
        )
        self.assertTrue(decision["ok"])
        self.assertTrue(decision.get("detach_host"))
        next_session = apply_piece_move(
            session,
            piece_key="instance:b",
            sheet_no=decision["sheet_no"],
            local_x_mm=decision["local_x_mm"],
            local_y_mm=decision["local_y_mm"],
            delta_x_mm=decision["delta_x_mm"],
            delta_y_mm=decision["delta_y_mm"],
            detach_host=decision.get("detach_host", False),
        )
        self.assertIsNone(next_session["pieces"]["instance:b"]["glass_host_key"])
        self.assertEqual(
            next_session["pieces"]["instance:b"]["source_glass_host_key"],
            "instance:a",
        )

    def test_partial_exit_onto_glass_material_is_rejected(self):
        session = _session()
        before = session["pieces"]["instance:b"]["local_x_mm"]
        # Guest 100..150; hole 80..180. Shift left onto host stock around x=50..80.
        decision = validate_piece_drop(
            piece=session["pieces"]["instance:b"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=40,
            world_y_mm=36 + 100,
            kerf_mm=session["kerf_mm"],
        )
        self.assertFalse(decision["ok"])
        self.assertEqual(decision["code"], DROP_OVERLAP)
        self.assertEqual(session["pieces"]["instance:b"]["local_x_mm"], before)
        self.assertEqual(session["pieces"]["instance:b"]["glass_host_key"], "instance:a")

    def test_reenter_trusted_host_restores_relationship(self):
        session = _session()
        session["pieces"]["instance:b"]["glass_host_key"] = None
        session["pieces"]["instance:b"]["glass_host_piece_id"] = None
        decision = validate_piece_drop(
            piece=session["pieces"]["instance:b"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=110,
            world_y_mm=36 + 110,
            kerf_mm=session["kerf_mm"],
        )
        self.assertTrue(decision["ok"], decision)
        self.assertEqual(decision.get("attach_host_key"), "instance:a")
        next_session = apply_piece_move(
            session,
            piece_key="instance:b",
            sheet_no=decision["sheet_no"],
            local_x_mm=decision["local_x_mm"],
            local_y_mm=decision["local_y_mm"],
            delta_x_mm=decision["delta_x_mm"],
            delta_y_mm=decision["delta_y_mm"],
            attach_host_key=decision.get("attach_host_key"),
            attach_host_piece_id=decision.get("attach_host_piece_id"),
        )
        self.assertEqual(next_session["pieces"]["instance:b"]["glass_host_key"], "instance:a")
        self.assertEqual(next_session["pieces"]["instance:b"]["glass_host_piece_id"], 1)

    def test_l_cutout_accepts_nested_piece_with_kerf(self):
        # L 1000×1000 with free cutout from (400,400) to (1000,1000).
        l_outline = [[0, 0], [1000, 0], [1000, 400], [400, 400], [400, 1000], [0, 1000]]
        guest = [[430, 430], [730, 430], [730, 730], [430, 730]]
        pieces = {
            "instance:l": {
                "piece_key": "instance:l",
                "piece_id": 10,
                "piece_instance_id": "l",
                "piece_type": "L-Shaped Corner",
                "sheet_no": 1,
                "local_x_mm": 0,
                "local_y_mm": 0,
                "placement_cm": {"x": 0, "y": 0, "w": 100, "h": 100},
                "outline_mm": l_outline,
                "editable": True,
                "glass_host_key": None,
            },
            "instance:g": {
                "piece_key": "instance:g",
                "piece_id": 11,
                "piece_instance_id": "g",
                "piece_type": "Regular",
                "sheet_no": None,
                "local_x_mm": 2000,
                "local_y_mm": 2000,
                "placement_cm": {"x": 200, "y": 200, "w": 30, "h": 30},
                "outline_mm": [[2000, 2000], [2300, 2000], [2300, 2300], [2000, 2300]],
                "editable": True,
                "glass_host_key": None,
            },
        }
        boards = {
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
                "user_moved": False,
            }
        }
        # world_x/y are top-left of the proposed guest AABB (matches FE drop origin).
        ok = validate_piece_drop(
            piece=pieces["instance:g"],
            pieces=pieces,
            boards=boards,
            world_x_mm=430,
            world_y_mm=36 + 430,
            kerf_mm=4,
        )
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(ok["sheet_no"], 1)

        kerf_fail = validate_piece_drop(
            piece=pieces["instance:g"],
            pieces=pieces,
            boards=boards,
            world_x_mm=402,
            world_y_mm=36 + 402,
            kerf_mm=4,
        )
        self.assertFalse(kerf_fail["ok"])
        self.assertEqual(kerf_fail["code"], DROP_KERF)

        overlap = validate_piece_drop(
            piece=pieces["instance:g"],
            pieces=pieces,
            boards=boards,
            world_x_mm=200,
            world_y_mm=36 + 200,
            kerf_mm=4,
        )
        self.assertFalse(overlap["ok"])
        self.assertEqual(overlap["code"], DROP_OVERLAP)

        # Place guest in cutout, then shift L so solid material occupies the guest.
        pieces["instance:g"].update(
            {
                "sheet_no": 1,
                "local_x_mm": 430,
                "local_y_mm": 430,
                "outline_mm": guest,
            }
        )
        l_over = validate_piece_drop(
            piece=pieces["instance:l"],
            pieces=pieces,
            boards=boards,
            world_x_mm=200,
            world_y_mm=36 + 200,
            kerf_mm=4,
        )
        self.assertFalse(l_over["ok"])
        self.assertIn(l_over["code"], {DROP_OVERLAP, DROP_KERF})


if __name__ == "__main__":
    unittest.main()
