"""Board editor: editor-created boards and GEOMETRY/OFFCUT classification."""

from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    DraftLayoutError,
    normalize_layout,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft_review import (
    review_saved_draft,
    trusted_model_from_projection,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
    BoardEditorMaterializeError,
    materialize_plan_snapshot,
)


def rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def catalog():
    return {
        "pieces": {
            "pi-a": {
                "piece_id": 1,
                "allow_rotation": True,
                "piece_type": "Regular",
            },
            "pi-b": {
                "piece_id": 2,
                "allow_rotation": True,
                "piece_type": "Glass",
            },
            "pi-c": {
                "piece_id": 3,
                "allow_rotation": True,
                "piece_type": "Regular",
            },
        },
        "source_sheet_nos": [1, 2],
    }


def layout_piece(instance, sheet, x=20, y=20, **extra):
    row = {
        "piece_instance_id": instance,
        "sheet_no": sheet,
        "local_x_mm": x,
        "local_y_mm": y,
        "rotation_deg": 0,
        "distribution": "active",
        "exclusion_reason": None,
        "glass_host_piece_id": None,
    }
    row.update(extra)
    return row


def projection_for_review():
    return {
        "board": {
            "full_width_cm": 122,
            "full_length_cm": 244,
            "usable_width_cm": 120,
            "usable_length_cm": 240,
            "trim_cm": 1,
            "kerf_cm": 0.4,
        },
        "sheets": [
            {
                "sheet_no": 1,
                "resource_kind": "FULL_BOARD",
                "full_width_cm": 122,
                "full_length_cm": 244,
                "usable_width_cm": 120,
                "usable_length_cm": 240,
                "applied_trim_width_cm": 1,
                "applied_trim_length_cm": 1,
            },
            {
                "sheet_no": 2,
                "resource_kind": "OFFCUT",
                "full_width_cm": 50,
                "full_length_cm": 50,
                "usable_width_cm": 50,
                "usable_length_cm": 50,
                "applied_trim_width_cm": 0,
                "applied_trim_length_cm": 0,
            },
        ],
        "pieces": [
            {
                "piece_instance_id": "pi-a",
                "piece_id": 1,
                "label": "A",
                "sheet_no": 1,
                "placement_cm": {"x": 2, "y": 2, "w": 40, "h": 30, "rotated": False},
                "allow_rotation": True,
                "allow_rotation_proven": True,
                "piece_type": "Regular",
                "resource_kind": "FULL_BOARD",
                "original_w": 40,
                "original_h": 30,
            },
            {
                "piece_instance_id": "pi-b",
                "piece_id": 2,
                "label": "B",
                "sheet_no": 1,
                "placement_cm": {"x": 50, "y": 2, "w": 20, "h": 20, "rotated": False},
                "allow_rotation": True,
                "allow_rotation_proven": True,
                "piece_type": "Glass",
                "resource_kind": "FULL_BOARD",
                "original_w": 20,
                "original_h": 20,
            },
            {
                "piece_instance_id": "pi-c",
                "piece_id": 3,
                "label": "C",
                "sheet_no": 1,
                "placement_cm": {"x": 2, "y": 40, "w": 15, "h": 15, "rotated": False},
                "allow_rotation": True,
                "allow_rotation_proven": True,
                "piece_type": "Regular",
                "resource_kind": "FULL_BOARD",
                "original_w": 15,
                "original_h": 15,
            },
        ],
        "elements": [
            {
                "kind": "finished_outline",
                "piece_instance_id": "pi-a",
                "geometry": {"outer": rect(20, 20, 400, 300)},
            },
            {
                "kind": "finished_outline",
                "piece_instance_id": "pi-b",
                "geometry": {"outer": rect(500, 20, 200, 200)},
            },
            {
                "kind": "finished_outline",
                "piece_instance_id": "pi-c",
                "geometry": {"outer": rect(20, 400, 150, 150)},
            },
        ],
    }


def source_snapshot():
    return {
        "full_board_width_cm": 122,
        "full_board_length_cm": 244,
        "usable_board_width_cm": 120,
        "usable_board_length_cm": 240,
        "kerf_cm": 0.4,
        "trim_cm": 1,
        "sheets": [
            {
                "sheet_no": 1,
                "resource_kind": "FULL_BOARD",
                "w": 120,
                "h": 240,
                "usable_width_cm": 120,
                "usable_length_cm": 240,
                "full_width_cm": 122,
                "full_length_cm": 244,
                "source_area_m2": 2.88,
                "pieces": [
                    {
                        "piece_instance_id": "pi-a",
                        "id": 1,
                        "label": "A",
                        "x": 2,
                        "y": 2,
                        "w": 40,
                        "h": 30,
                        "original_w": 40,
                        "original_h": 30,
                        "piece_type": "Regular",
                        "resource_kind": "FULL_BOARD",
                        "area_m2": 0.12,
                        "geometry": {"outer": rect(20, 20, 400, 300)},
                    },
                    {
                        "piece_instance_id": "pi-b",
                        "id": 2,
                        "label": "B",
                        "x": 50,
                        "y": 2,
                        "w": 20,
                        "h": 20,
                        "original_w": 20,
                        "original_h": 20,
                        "piece_type": "Glass",
                        "resource_kind": "FULL_BOARD",
                        "area_m2": 0.04,
                        "geometry": {"outer": rect(500, 20, 200, 200)},
                    },
                    {
                        "piece_instance_id": "pi-c",
                        "id": 3,
                        "label": "C",
                        "x": 2,
                        "y": 40,
                        "w": 15,
                        "h": 15,
                        "original_w": 15,
                        "original_h": 15,
                        "piece_type": "Regular",
                        "resource_kind": "FULL_BOARD",
                        "area_m2": 0.0225,
                        "geometry": {"outer": rect(20, 400, 150, 150)},
                    },
                ],
            },
            {
                "sheet_no": 2,
                "resource_kind": "OFFCUT",
                "w": 50,
                "h": 50,
                "usable_width_cm": 50,
                "usable_length_cm": 50,
                "full_width_cm": 50,
                "full_length_cm": 50,
                "source_area_m2": 0.25,
                "pieces": [],
            },
        ],
    }


class BoardEditorAddBoardClassificationTests(unittest.TestCase):
    def test_normalize_allows_editor_full_board_without_client_dims(self):
        document = {
            "schema": 1,
            "boards": [
                {"sheet_no": 1, "origin_x_mm": 0, "origin_y_mm": 36, "user_moved": False},
                {
                    "sheet_no": 3,
                    "origin_x_mm": 1300,
                    "origin_y_mm": 36,
                    "user_moved": False,
                    "editor_origin": "full_board",
                },
            ],
            "pieces": [
                layout_piece("pi-a", 1),
                layout_piece("pi-b", 3),
                layout_piece("pi-c", None),
            ],
        }
        normalized = normalize_layout(document, catalog())
        self.assertEqual(
            [board["sheet_no"] for board in normalized["boards"]],
            [1, 3],
        )
        self.assertEqual(normalized["boards"][1]["editor_origin"], "full_board")
        self.assertNotIn("full_width_cm", normalized["boards"][1])

    def test_normalize_rejects_unknown_sheet_without_editor_origin(self):
        document = {
            "schema": 1,
            "boards": [
                {"sheet_no": 9, "origin_x_mm": 0, "origin_y_mm": 36, "user_moved": False},
            ],
            "pieces": [
                layout_piece("pi-a", None),
                layout_piece("pi-b", None),
                layout_piece("pi-c", None),
            ],
        }
        with self.assertRaises(DraftLayoutError) as raised:
            normalize_layout(document, catalog())
        self.assertEqual(raised.exception.code, "unknown_sheet")

    def test_normalize_rejects_client_board_dimensions(self):
        document = {
            "schema": 1,
            "boards": [
                {
                    "sheet_no": 3,
                    "origin_x_mm": 0,
                    "origin_y_mm": 36,
                    "user_moved": False,
                    "editor_origin": "full_board",
                    "full_width_cm": 999,
                },
            ],
            "pieces": [
                layout_piece("pi-a", None),
                layout_piece("pi-b", None),
                layout_piece("pi-c", None),
            ],
        }
        with self.assertRaises(DraftLayoutError) as raised:
            normalize_layout(document, catalog())
        self.assertEqual(raised.exception.code, "forbidden_field")

    def test_legacy_draft_without_classification_still_normalizes(self):
        document = {
            "schema": 1,
            "boards": [
                {"sheet_no": 1, "origin_x_mm": 0, "origin_y_mm": 36, "user_moved": False},
            ],
            "pieces": [
                layout_piece("pi-a", 1),
                layout_piece("pi-b", 1, x=500, y=20),
                layout_piece("pi-c", 1, x=20, y=400),
            ],
        }
        normalized = normalize_layout(document, catalog())
        for piece in normalized["pieces"]:
            self.assertNotIn("resource_kind", piece)

    def test_normalize_stores_offcut_classification_without_changing_piece_type(self):
        document = {
            "schema": 1,
            "boards": [
                {"sheet_no": 1, "origin_x_mm": 0, "origin_y_mm": 36, "user_moved": False},
            ],
            "pieces": [
                layout_piece(
                    "pi-b",
                    1,
                    resource_kind="OFFCUT",
                    offcut_source_party="FACTORY",
                    offcut_execution_party="FACTORY",
                ),
                layout_piece("pi-a", None),
                layout_piece("pi-c", None),
            ],
        }
        normalized = normalize_layout(document, catalog())
        glass = next(row for row in normalized["pieces"] if row["piece_instance_id"] == "pi-b")
        self.assertEqual(glass["resource_kind"], "OFFCUT")
        self.assertEqual(glass["offcut_source_party"], "FACTORY")
        self.assertEqual(catalog()["pieces"]["pi-b"]["piece_type"], "Glass")

    def test_review_rejects_mixed_board_but_draft_normalize_allows_it(self):
        document = {
            "schema": 1,
            "boards": [
                {"sheet_no": 1, "origin_x_mm": 0, "origin_y_mm": 36, "user_moved": False},
            ],
            "pieces": [
                layout_piece("pi-a", 1, resource_kind="FULL_BOARD"),
                layout_piece(
                    "pi-b",
                    1,
                    x=500,
                    y=20,
                    resource_kind="OFFCUT",
                    offcut_source_party="FACTORY",
                    offcut_execution_party="FACTORY",
                ),
                layout_piece("pi-c", None, resource_kind="FULL_BOARD"),
            ],
        }
        normalized = normalize_layout(document, catalog())
        self.assertEqual(len(normalized["boards"]), 1)
        trusted = trusted_model_from_projection(projection_for_review(), machine_type="CNC Router")
        result = review_saved_draft(
            {
                "present": True,
                "compatible": True,
                "draft_version": 1,
                "layout": normalized,
            },
            trusted,
        )
        self.assertFalse(result["ready"])
        self.assertIn("mixed_full_board_offcut_source", [issue["code"] for issue in result["issues"]])

    def test_review_and_plan_copy_allow_unassigned_offcut_type(self):
        document = {
            "schema": 1,
            "boards": [
                {
                    "sheet_no": 3,
                    "origin_x_mm": 0,
                    "origin_y_mm": 36,
                    "user_moved": False,
                    "editor_origin": "full_board",
                },
                {
                    "sheet_no": 4,
                    "origin_x_mm": 1400,
                    "origin_y_mm": 36,
                    "user_moved": False,
                    "editor_origin": "full_board",
                },
            ],
            "pieces": [
                layout_piece("pi-a", 3, resource_kind="FULL_BOARD"),
                layout_piece("pi-b", 3, x=500, y=20, resource_kind="FULL_BOARD"),
                layout_piece(
                    "pi-c",
                    4,
                    resource_kind="OFFCUT",
                    offcut_source_party="UNASSIGNED",
                    offcut_execution_party="UNASSIGNED",
                ),
            ],
        }
        normalized = normalize_layout(document, catalog())
        trusted = trusted_model_from_projection(projection_for_review(), machine_type="CNC Router")
        draft = {
            "present": True,
            "compatible": True,
            "draft_version": 1,
            "layout": normalized,
            "source_content_revision": "rev-1",
            "source_input_fingerprint": "fp-1",
            "distribution_fingerprint": "ignored",
        }
        result = review_saved_draft(draft, trusted)
        self.assertTrue(result["ready"], result["issues"])
        self.assertNotIn("offcut_unresolved", [issue["code"] for issue in result["issues"]])
        snapshot = materialize_plan_snapshot(
            draft=draft,
            projection=projection_for_review(),
            source_snapshot=source_snapshot(),
            machine_type="CNC Router",
            source_plan_name="PLAN-1",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
        )
        offcut = next(
            piece
            for sheet in snapshot["sheets"]
            for piece in sheet["pieces"]
            if piece["piece_instance_id"] == "pi-c"
        )
        self.assertEqual(offcut["resource_kind"], "OFFCUT")
        self.assertEqual(offcut["offcut_source_party"], "UNASSIGNED")
        self.assertEqual(offcut["offcut_execution_party"], "UNASSIGNED")

    def test_review_accepts_editor_board_with_order_standard_dims(self):
        document = {
            "schema": 1,
            "boards": [
                {
                    "sheet_no": 3,
                    "origin_x_mm": 0,
                    "origin_y_mm": 36,
                    "user_moved": False,
                    "editor_origin": "full_board",
                },
            ],
            "pieces": [
                layout_piece("pi-a", 3, resource_kind="FULL_BOARD"),
                layout_piece("pi-b", 3, x=500, y=20, resource_kind="FULL_BOARD"),
                layout_piece("pi-c", 3, x=20, y=400, resource_kind="FULL_BOARD"),
            ],
        }
        normalized = normalize_layout(document, catalog())
        trusted = trusted_model_from_projection(projection_for_review(), machine_type="CNC Router")
        self.assertGreater(trusted["standard_full_board"]["usable_width_mm"], 0)
        result = review_saved_draft(
            {
                "present": True,
                "compatible": True,
                "draft_version": 1,
                "layout": normalized,
            },
            trusted,
        )
        self.assertTrue(result["ready"], result["issues"])

    def test_materialize_editor_board_and_required_full_boards(self):
        document = {
            "schema": 1,
            "boards": [
                {
                    "sheet_no": 3,
                    "origin_x_mm": 0,
                    "origin_y_mm": 36,
                    "user_moved": False,
                    "editor_origin": "full_board",
                },
                {
                    "sheet_no": 4,
                    "origin_x_mm": 1400,
                    "origin_y_mm": 36,
                    "user_moved": False,
                    "editor_origin": "full_board",
                },
            ],
            "pieces": [
                layout_piece("pi-a", 3, resource_kind="FULL_BOARD"),
                layout_piece("pi-b", 3, x=500, y=20, resource_kind="FULL_BOARD"),
                layout_piece(
                    "pi-c",
                    4,
                    resource_kind="OFFCUT",
                    offcut_source_party="FACTORY",
                    offcut_execution_party="FACTORY",
                ),
            ],
        }
        normalized = normalize_layout(document, catalog())
        draft = {
            "present": True,
            "compatible": True,
            "draft_version": 3,
            "layout": normalized,
            "source_content_revision": "rev-1",
            "source_input_fingerprint": "fp-1",
            "distribution_fingerprint": "ignored",
        }
        snapshot = materialize_plan_snapshot(
            draft=draft,
            projection=projection_for_review(),
            source_snapshot=source_snapshot(),
            machine_type="CNC Router",
            source_plan_name="PLAN-1",
            expected_draft_version=3,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
        )
        sheet_nos = [int(sheet["sheet_no"]) for sheet in snapshot["sheets"]]
        self.assertEqual(sheet_nos, [3, 4])
        by_no = {int(sheet["sheet_no"]): sheet for sheet in snapshot["sheets"]}
        self.assertAlmostEqual(by_no[3]["full_width_cm"], 122.0)
        self.assertAlmostEqual(by_no[3]["full_length_cm"], 244.0)
        self.assertNotEqual(by_no[3]["full_width_cm"], 50.0)
        self.assertEqual(by_no[3]["resource_kind"], "FULL_BOARD")
        self.assertEqual(by_no[4]["resource_kind"], "OFFCUT")
        glass = next(
            piece
            for piece in by_no[3]["pieces"]
            if piece["piece_instance_id"] == "pi-b"
        )
        self.assertEqual(glass["piece_type"], "Glass")
        self.assertEqual(glass["resource_kind"], "FULL_BOARD")
        offcut = by_no[4]["pieces"][0]
        self.assertEqual(offcut["resource_kind"], "OFFCUT")
        self.assertEqual(offcut["offcut_source_party"], "FACTORY")
        self.assertEqual(snapshot["required_full_boards"], 1)

    def test_materialize_drops_empty_editor_board(self):
        document = {
            "schema": 1,
            "boards": [
                {
                    "sheet_no": 3,
                    "origin_x_mm": 0,
                    "origin_y_mm": 36,
                    "user_moved": False,
                    "editor_origin": "full_board",
                },
                {
                    "sheet_no": 5,
                    "origin_x_mm": 1400,
                    "origin_y_mm": 36,
                    "user_moved": False,
                    "editor_origin": "full_board",
                },
            ],
            "pieces": [
                layout_piece("pi-a", 3, resource_kind="FULL_BOARD"),
                layout_piece("pi-b", 3, x=500, y=20, resource_kind="FULL_BOARD"),
                layout_piece("pi-c", 3, x=20, y=400, resource_kind="FULL_BOARD"),
            ],
        }
        normalized = normalize_layout(document, catalog())
        draft = {
            "present": True,
            "compatible": True,
            "draft_version": 4,
            "layout": normalized,
            "source_content_revision": "rev-1",
            "source_input_fingerprint": "fp-1",
        }
        snapshot = materialize_plan_snapshot(
            draft=draft,
            projection=projection_for_review(),
            source_snapshot=source_snapshot(),
            machine_type="CNC Router",
            source_plan_name="PLAN-1",
            expected_draft_version=4,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
        )
        self.assertEqual([int(sheet["sheet_no"]) for sheet in snapshot["sheets"]], [3])
        self.assertEqual(snapshot["required_full_boards"], 1)

    def test_materialize_rejects_mixed_board(self):
        document = {
            "schema": 1,
            "boards": [
                {"sheet_no": 1, "origin_x_mm": 0, "origin_y_mm": 36, "user_moved": False},
            ],
            "pieces": [
                layout_piece("pi-a", 1, resource_kind="FULL_BOARD"),
                layout_piece(
                    "pi-b",
                    1,
                    x=500,
                    y=20,
                    resource_kind="OFFCUT",
                    offcut_source_party="FACTORY",
                    offcut_execution_party="FACTORY",
                ),
                layout_piece("pi-c", None, resource_kind="FULL_BOARD"),
            ],
        }
        normalized = normalize_layout(document, catalog())
        draft = {
            "present": True,
            "compatible": True,
            "draft_version": 5,
            "layout": normalized,
            "source_content_revision": "rev-1",
            "source_input_fingerprint": "fp-1",
        }
        with self.assertRaises(BoardEditorMaterializeError) as raised:
            materialize_plan_snapshot(
                draft=draft,
                projection=projection_for_review(),
                source_snapshot=source_snapshot(),
                machine_type="CNC Router",
                source_plan_name="PLAN-1",
                expected_draft_version=5,
                source_content_revision="rev-1",
                source_input_fingerprint="fp-1",
            )
        self.assertEqual(raised.exception.code, "not_ready")


if __name__ == "__main__":
    unittest.main()
