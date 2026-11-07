"""Domain snap suggestions for Board Editor session moves."""

from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.cutting.board_editor_session_edit import (
    apply_piece_move,
    validate_piece_drop,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_snap import (
    SNAP_ENTER_PX,
    SNAP_EXIT_PX,
    footprint_edges,
    suggest_piece_snap,
)


def _session():
    return {
        "boards": {
            "1": {
                "sheet_no": 1,
                "origin_x_mm": 0,
                "origin_y_mm": 0,
                "width_mm": 1000,
                "height_mm": 1000,
                "trim_x_mm": 10,
                "trim_y_mm": 10,
                "usable_width_mm": 980,
                "usable_length_mm": 980,
                "title_band_mm": 36,
            }
        },
        "pieces": {
            "instance:a": {
                "piece_key": "instance:a",
                "piece_id": 1,
                "piece_instance_id": "a",
                "sheet_no": 1,
                "local_x_mm": 100,
                "local_y_mm": 100,
                "placement_cm": {"x": 10, "y": 10, "w": 20, "h": 20},
                "outline_mm": [[100, 100], [300, 100], [300, 300], [100, 300]],
                "editable": True,
                "glass_host_key": None,
            },
            "instance:b": {
                "piece_key": "instance:b",
                "piece_id": 2,
                "piece_instance_id": "b",
                "sheet_no": 1,
                "local_x_mm": 500,
                "local_y_mm": 100,
                "placement_cm": {"x": 50, "y": 10, "w": 20, "h": 20},
                "outline_mm": [[500, 100], [700, 100], [700, 300], [500, 300]],
                "editable": True,
                "glass_host_key": None,
            },
            "instance:c": {
                "piece_key": "instance:c",
                "piece_id": 3,
                "piece_instance_id": "c",
                "sheet_no": 1,
                "local_x_mm": 500,
                "local_y_mm": 500,
                "placement_cm": {"x": 50, "y": 50, "w": 10, "h": 10},
                "outline_mm": [[500, 500], [600, 500], [600, 600], [500, 600]],
                "editable": True,
                "glass_host_key": None,
            },
            "instance:l": {
                "piece_key": "instance:l",
                "piece_id": 4,
                "piece_instance_id": "l",
                "sheet_no": 1,
                "local_x_mm": 50,
                "local_y_mm": 500,
                "placement_cm": {"x": 5, "y": 50, "w": 20, "h": 20},
                # L-shape polygon in usable-sheet mm.
                "outline_mm": [
                    [50, 500],
                    [250, 500],
                    [250, 600],
                    [150, 600],
                    [150, 700],
                    [50, 700],
                ],
                "editable": True,
                "glass_host_key": None,
            },
        },
        "kerf_mm": 4.0,
        "stale_cut_path_sheets": [],
        "stale_unbound_text_sheets": [],
    }


class TestBoardEditorSnap(unittest.TestCase):
    def test_threshold_constants_are_pixels(self):
        self.assertEqual(SNAP_ENTER_PX, 8.0)
        self.assertEqual(SNAP_EXIT_PX, 12.0)

    def test_snap_to_usable_left(self):
        session = _session()
        piece = session["pieces"]["instance:a"]
        # Current world x = local 100 + trim 10 = 110. Usable left world x = 10.
        suggestion = suggest_piece_snap(
            piece=piece,
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=12,
            world_y_mm=110,
            kerf_mm=session["kerf_mm"],
            threshold_mm=10,
        )
        self.assertTrue(suggestion["ok"])
        self.assertAlmostEqual(suggestion["dx"], 10 - 110, places=3)
        check = validate_piece_drop(
            piece=piece,
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=110 + suggestion["dx"],
            world_y_mm=110 + suggestion["dy"],
            kerf_mm=session["kerf_mm"],
        )
        self.assertTrue(check["ok"])
        self.assertAlmostEqual(check["local_x_mm"], 0.0, places=3)

    def test_snap_to_neighbour_with_single_kerf(self):
        session = _session()
        piece = session["pieces"]["instance:a"]
        # Move a near left of b (b local 500 → world left 510).
        # With kerf 4, a world right should land at 506 → local 296.
        suggestion = suggest_piece_snap(
            piece=piece,
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=300,
            world_y_mm=110,
            kerf_mm=session["kerf_mm"],
            threshold_mm=20,
        )
        self.assertTrue(suggestion["ok"])
        check = validate_piece_drop(
            piece=piece,
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=110 + suggestion["dx"],
            world_y_mm=110 + suggestion["dy"],
            kerf_mm=session["kerf_mm"],
        )
        self.assertTrue(check["ok"])
        # Gap between a.right and b.left equals kerf once (not 2×).
        a_right = check["local_x_mm"] + 200
        self.assertAlmostEqual(a_right + session["kerf_mm"], 500.0, places=3)

    def test_reject_snap_that_overlaps_third_piece(self):
        session = _session()
        # Place c between a and the would-be kerf slot so a horizontal snap to b conflicts.
        session["pieces"]["instance:c"]["local_x_mm"] = 320
        session["pieces"]["instance:c"]["local_y_mm"] = 100
        session["pieces"]["instance:c"]["outline_mm"] = [
            [320, 100],
            [420, 100],
            [420, 300],
            [320, 300],
        ]
        piece = session["pieces"]["instance:a"]
        suggestion = suggest_piece_snap(
            piece=piece,
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=300,
            world_y_mm=100,
            kerf_mm=session["kerf_mm"],
            threshold_mm=20,
        )
        if suggestion["ok"]:
            check = validate_piece_drop(
                piece=piece,
                pieces=session["pieces"],
                boards=session["boards"],
                world_x_mm=100 + suggestion["dx"],
                world_y_mm=100 + suggestion["dy"],
                kerf_mm=session["kerf_mm"],
            )
            self.assertTrue(check["ok"])
            # Must not land where it overlaps c.
            self.assertFalse(
                check["local_x_mm"] < 420 and check["local_x_mm"] + 200 > 320
                and abs(check["local_y_mm"] - 100) < 1
            )

    def test_no_snap_outside_boards(self):
        session = _session()
        piece = dict(session["pieces"]["instance:a"])
        piece["sheet_no"] = None
        piece["local_x_mm"] = 2000
        piece["local_y_mm"] = 50
        piece["outline_mm"] = [[2000, 50], [2100, 50], [2100, 150], [2000, 150]]
        suggestion = suggest_piece_snap(
            piece=piece,
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=2010,
            world_y_mm=50,
            kerf_mm=session["kerf_mm"],
            threshold_mm=20,
        )
        self.assertFalse(suggestion["ok"])

    def test_l_shape_edges_extracted(self):
        session = _session()
        edges = footprint_edges(
            {
                "kind": "polygon",
                "points": session["pieces"]["instance:l"]["outline_mm"],
                "bounds": {"x": 50, "y": 500, "w": 200, "h": 200},
            }
        )
        self.assertGreaterEqual(len(edges), 6)
        kinds = {edge["kind"] for edge in edges}
        self.assertIn("h", kinds)
        self.assertIn("v", kinds)

    def test_host_guest_excluded_from_mutual_snap(self):
        session = _session()
        session["pieces"]["instance:b"]["glass_host_key"] = "instance:a"
        session["pieces"]["instance:a"]["glass_hole_local_mm"] = [
            [150, 150],
            [250, 150],
            [250, 250],
            [150, 250],
        ]
        suggestion = suggest_piece_snap(
            piece=session["pieces"]["instance:b"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=160,
            world_y_mm=160,
            kerf_mm=session["kerf_mm"],
            threshold_mm=30,
        )
        # May snap to usable, but source must not be the host piece edge.
        if suggestion["ok"]:
            self.assertNotEqual(suggestion["source"], "piece:instance:a")

    def test_magnet_disabled_and_hysteresis(self):
        session = _session()
        piece = session["pieces"]["instance:a"]
        off = suggest_piece_snap(
            piece=piece,
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=12,
            world_y_mm=100,
            kerf_mm=session["kerf_mm"],
            threshold_mm=10,
            magnet_enabled=False,
        )
        self.assertFalse(off["ok"])

        on = suggest_piece_snap(
            piece=piece,
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=12,
            world_y_mm=100,
            kerf_mm=session["kerf_mm"],
            threshold_mm=10,
        )
        self.assertTrue(on["ok"])
        sticky = suggest_piece_snap(
            piece=piece,
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=12 + 5,
            world_y_mm=100,
            kerf_mm=session["kerf_mm"],
            threshold_mm=10,
            exit_threshold_mm=20,
            active_snap=on,
        )
        self.assertTrue(sticky["ok"])
        self.assertAlmostEqual(sticky["dx"], on["dx"], places=3)

    def test_apply_snapped_move_marks_history_payload(self):
        session = _session()
        piece = session["pieces"]["instance:a"]
        suggestion = suggest_piece_snap(
            piece=piece,
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=12,
            world_y_mm=110,
            kerf_mm=session["kerf_mm"],
            threshold_mm=10,
        )
        self.assertTrue(suggestion["ok"])
        decision = validate_piece_drop(
            piece=piece,
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=110 + suggestion["dx"],
            world_y_mm=110 + suggestion["dy"],
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
        self.assertEqual(next_session["pieces"]["instance:a"]["piece_instance_id"], "a")
        self.assertAlmostEqual(next_session["pieces"]["instance:a"]["local_x_mm"], 0.0, places=3)

    def test_alignment_top_and_guide(self):
        session = _session()
        session["pieces"].pop("instance:c", None)
        session["pieces"].pop("instance:l", None)
        session["pieces"]["instance:b"]["local_y_mm"] = 105
        session["pieces"]["instance:b"]["outline_mm"] = [
            [500, 105],
            [700, 105],
            [700, 305],
            [500, 305],
        ]
        suggestion = suggest_piece_snap(
            piece=session["pieces"]["instance:a"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=110,
            world_y_mm=112,
            kerf_mm=session["kerf_mm"],
            threshold_mm=8,
        )
        self.assertTrue(suggestion["ok"])
        self.assertTrue(str(suggestion["source"]).startswith("align:top:"))
        self.assertAlmostEqual(110 + suggestion["dy"], 115, places=3)
        guide = next(g for g in suggestion["guides"] if g.get("kind") == "alignment")
        self.assertEqual(guide["mode"], "top")
        self.assertAlmostEqual(guide["y1"], guide["y2"], places=3)
        self.assertAlmostEqual(guide["y1"], 115, places=3)
        self.assertGreater(guide["x2"], guide["x1"])

    def test_alignment_center_x(self):
        session = _session()
        session["pieces"].pop("instance:c", None)
        session["pieces"].pop("instance:l", None)
        session["pieces"]["instance:b"]["local_x_mm"] = 550
        session["pieces"]["instance:b"]["local_y_mm"] = 550
        session["pieces"]["instance:b"]["outline_mm"] = [
            [550, 550],
            [650, 550],
            [650, 650],
            [550, 650],
        ]
        suggestion = suggest_piece_snap(
            piece=session["pieces"]["instance:a"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=506,
            world_y_mm=110,
            kerf_mm=session["kerf_mm"],
            threshold_mm=8,
        )
        self.assertTrue(suggestion["ok"])
        self.assertIn("align:centerX:", str(suggestion["source"]))
        self.assertAlmostEqual(110 + suggestion["dx"] + 100, 610, places=3)

    def test_alignment_rejects_overlap(self):
        session = _session()
        session["pieces"]["instance:b"]["local_x_mm"] = 100
        session["pieces"]["instance:b"]["local_y_mm"] = 105
        session["pieces"]["instance:b"]["outline_mm"] = [
            [100, 105],
            [300, 105],
            [300, 305],
            [100, 305],
        ]
        suggestion = suggest_piece_snap(
            piece=session["pieces"]["instance:a"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=110,
            world_y_mm=112,
            kerf_mm=session["kerf_mm"],
            threshold_mm=8,
        )
        if suggestion["ok"]:
            self.assertNotIn("align:top:", str(suggestion["source"]))

    def test_combined_kerf_and_top_alignment(self):
        session = _session()
        session["pieces"]["instance:b"]["local_y_mm"] = 105
        session["pieces"]["instance:b"]["outline_mm"] = [
            [500, 105],
            [700, 105],
            [700, 305],
            [500, 305],
        ]
        suggestion = suggest_piece_snap(
            piece=session["pieces"]["instance:a"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=304,
            world_y_mm=112,
            kerf_mm=session["kerf_mm"],
            threshold_mm=8,
        )
        self.assertTrue(suggestion["ok"])
        check = validate_piece_drop(
            piece=session["pieces"]["instance:a"],
            pieces=session["pieces"],
            boards=session["boards"],
            world_x_mm=110 + suggestion["dx"],
            world_y_mm=110 + suggestion["dy"],
            kerf_mm=session["kerf_mm"],
        )
        self.assertTrue(check["ok"])
        self.assertAlmostEqual(check["local_x_mm"] + 200 + session["kerf_mm"], 500.0, places=3)
        self.assertAlmostEqual(check["local_y_mm"], 105.0, places=3)


if __name__ == "__main__":
    unittest.main()
