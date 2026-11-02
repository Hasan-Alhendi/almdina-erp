"""Read-only readiness of a saved board-editor draft."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.cutting.board_editor_draft_review import (
    draft_review_allowed,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft_review import (
    review_saved_draft,
)

APP = Path(__file__).resolve().parents[1] / "almdina_erp"


def rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def piece(instance, piece_id, x, y, w, h, **extra):
    row = {
        "piece_instance_id": instance,
        "piece_id": piece_id,
        "label": instance,
        "sheet_no": extra.get("entry_sheet", 1),
        "local_x_mm": x,
        "local_y_mm": y,
        "width_mm": w,
        "length_mm": h,
        "original_w": extra.get("original_w", w / 10.0),
        "original_h": extra.get("original_h", h / 10.0),
        "piece_type": extra.get("piece_type", "Regular"),
        "outline_mm": extra.get("outline", rect(x, y, w, h)),
        "glass_hole_local_mm": extra.get("hole"),
        "glass_host_piece_id": extra.get("host"),
        "allow_rotation": extra.get("allow", False),
        "allow_rotation_proven": extra.get("proven", True),
        "resource_kind": extra.get("kind"),
        "offcut_source_party": extra.get("source_party"),
        "offcut_execution_party": extra.get("execution_party"),
        "clipped_corner_position": extra.get("clipped_corner_position", "Top Right"),
        "clipped_corner_width_cm": extra.get("clipped_corner_width_cm", 0),
        "clipped_corner_length_cm": extra.get("clipped_corner_length_cm", 0),
        "corner_mirrored": extra.get("corner_mirrored", False),
        "corner_rotation_quarter_turns": extra.get("corner_rotation_quarter_turns", 0),
    }
    for key, value in extra.get("machining", {}).items():
        row[key] = value
    return instance, row


def liner_fields(side="edge_width_top", offset=2, width=1.8, start=0, length=None, specs=None):
    payload = {
        "extra_liner": 1,
        "liner_reference_side": side,
        "liner_offset_cm": offset,
        "liner_width_cm": width,
        "liner_start_cm": start,
        "liner_length_cm": length if length is not None else 0,
        "liner_specs_json": "",
    }
    if specs is not None:
        import json

        payload["liner_specs_json"] = json.dumps(
            {"width_cm": width, "liners": specs},
            ensure_ascii=True,
        )
    return payload


def groove_fields(side="edge_width_top", offset=4, width=1.8, start=0, length=20):
    return {
        "extra_back_groove": 1,
        "back_groove_reference_side": side,
        "back_groove_offset_cm": offset,
        "back_groove_width_cm": width,
        "back_groove_start_cm": start,
        "back_groove_length_cm": length,
    }


def handle_fields(side="edge_long_left", offset=5, width=1.8, start=5, length=15):
    return {
        "extra_recessed_handle_cutout": 1,
        "recessed_handle_reference_side": side,
        "recessed_handle_offset_cm": offset,
        "recessed_handle_width_cm": width,
        "recessed_handle_start_cm": start,
        "recessed_handle_length_cm": length,
    }


def model(pieces, sheets=None, kerf=4, machine="CNC Router"):
    return {
        "pieces": dict(pieces),
        "sheets": sheets
        or {1: {"resource_kind": "FULL_BOARD", "usable_width_mm": 1200, "usable_length_mm": 2400}},
        "kerf_mm": kerf,
        "machine_type": machine,
    }


def row(instance, x, y, **extra):
    return {
        "piece_instance_id": instance,
        "sheet_no": extra.get("sheet", 1),
        "local_x_mm": x,
        "local_y_mm": y,
        "rotation_deg": extra.get("rotation", 0),
        "distribution": extra.get("distribution", "active"),
        "exclusion_reason": extra.get("reason"),
        "glass_host_piece_id": extra.get("host"),
    }


def boards(*numbers):
    return [
        {"sheet_no": number, "origin_x_mm": 900, "origin_y_mm": 700, "user_moved": True}
        for number in numbers
    ]


def draft(layout, **extra):
    payload = {
        "present": True,
        "compatible": True,
        "conflict": None,
        "draft_version": 2,
        "distribution_fingerprint": "stored",
        "layout": layout,
    }
    payload.update(extra)
    return payload


def codes(result):
    return [issue["code"] for issue in result["issues"]]


class BoardEditorDraftReviewTests(unittest.TestCase):
    def test_complete_distribution_is_ready_without_using_workspace_origin(self):
        trusted = model(
            [
                piece("pi-a", 1, 20, 20, 100, 80),
                piece(
                    "pi-off",
                    2,
                    20,
                    20,
                    40,
                    40,
                    entry_sheet=2,
                    kind="OFFCUT",
                    source_party="FACTORY",
                    execution_party="FACTORY",
                ),
                piece(
                    "pi-customer",
                    3,
                    0,
                    0,
                    30,
                    30,
                    kind="OFFCUT",
                    source_party="CUSTOMER",
                    execution_party="CUSTOMER",
                ),
            ],
            sheets={
                1: {"resource_kind": "FULL_BOARD", "usable_width_mm": 1200, "usable_length_mm": 2400},
                2: {"resource_kind": "OFFCUT", "usable_width_mm": 500, "usable_length_mm": 500},
            },
        )
        layout = {
            "schema": 1,
            "pieces": [
                row("pi-a", 20, 20),
                row("pi-off", 20, 20, sheet=2),
                row("pi-customer", 0, 0, sheet=None, distribution="excluded", reason="removed_from_distribution"),
            ],
            "boards": boards(1, 2),
        }
        before = copy.deepcopy(layout)
        result = review_saved_draft(draft(layout), trusted)
        self.assertTrue(result["ready"], result["issues"])
        self.assertEqual(result["draft_version"], 2)
        self.assertTrue(result["distribution_fingerprint"])
        self.assertEqual(layout, before)
        self.assertEqual(layout["boards"][0]["origin_x_mm"], 900)

    def test_excluded_and_outside_pieces_block_readiness(self):
        trusted = model([piece("pi-a", 1, 20, 20, 100, 80), piece("pi-b", 2, 200, 20, 100, 80)])
        excluded = draft(
            {
                "schema": 1,
                "pieces": [
                    row("pi-a", 20, 20, distribution="excluded", reason="removed_from_distribution", sheet=None),
                    row("pi-b", 200, 20),
                ],
                "boards": boards(1),
            }
        )
        outside = draft(
            {
                "schema": 1,
                "pieces": [
                    row("pi-a", 20, 20, sheet=None),
                    row("pi-b", 200, 20),
                ],
                "boards": boards(1),
            }
        )
        self.assertIn("piece_excluded", codes(review_saved_draft(excluded, trusted)))
        self.assertIn("piece_outside_board", codes(review_saved_draft(outside, trusted)))

    def test_missing_and_duplicate_identities_are_rejected(self):
        trusted = model([piece("pi-a", 1, 20, 20, 100, 80), piece("pi-b", 2, 200, 20, 100, 80)])
        missing = draft({"schema": 1, "pieces": [row("pi-a", 20, 20)], "boards": boards(1)})
        duplicated = draft(
            {
                "schema": 1,
                "pieces": [row("pi-a", 20, 20), row("pi-a", 40, 20), row("pi-b", 200, 20)],
                "boards": boards(1),
            }
        )
        self.assertIn("missing_piece", codes(review_saved_draft(missing, trusted)))
        self.assertIn("duplicate_piece", codes(review_saved_draft(duplicated, trusted)))

    def test_edge_overlap_and_kerf(self):
        trusted = model(
            [piece("pi-a", 1, 20, 20, 100, 80), piece("pi-b", 2, 200, 20, 100, 80)],
            kerf=4,
        )
        partial = draft(
            {
                "schema": 1,
                "pieces": [row("pi-a", -20, 20), row("pi-b", 200, 20)],
                "boards": boards(1),
            }
        )
        overlap = draft(
            {
                "schema": 1,
                "pieces": [row("pi-a", 20, 20), row("pi-b", 40, 30)],
                "boards": boards(1),
            }
        )
        kerf = draft(
            {
                "schema": 1,
                "pieces": [row("pi-a", 0, 0), row("pi-b", 102, 0)],
                "boards": boards(1),
            }
        )
        self.assertIn("partial_board_overlap", codes(review_saved_draft(partial, trusted)))
        self.assertIn("piece_overlap", codes(review_saved_draft(overlap, trusted)))
        self.assertIn("kerf_clearance", codes(review_saved_draft(kerf, trusted)))

    def test_glass_guest_inside_the_opening_is_not_material(self):
        hole = rect(100, 100, 200, 200)
        trusted = model(
            [
                piece("pi-host", 1, 0, 0, 400, 400, hole=hole),
                piece("pi-guest", 2, 150, 150, 40, 40, host=1),
            ],
            kerf=4,
        )
        layout = {
            "schema": 1,
            "pieces": [row("pi-host", 0, 0), row("pi-guest", 150, 150, host=1)],
            "boards": boards(1),
        }
        result = review_saved_draft(draft(layout), trusted)
        self.assertTrue(result["ready"], result["issues"])
        self.assertNotIn("piece_overlap", codes(result))

    def test_rotation_follows_piece_and_machine_limits(self):
        trusted = model([piece("pi-a", 1, 400, 400, 40, 40, allow=True)])
        turned = draft(
            {
                "schema": 1,
                "pieces": [row("pi-a", 400, 400, rotation=15)],
                "boards": boards(1),
            }
        )
        self.assertTrue(review_saved_draft(turned, trusted)["ready"])
        blocked = model([piece("pi-a", 1, 400, 400, 40, 40, allow=False)])
        denied = review_saved_draft(turned, blocked)
        self.assertIn("rotation_forbidden", codes(denied))
        saw = review_saved_draft(turned, model([piece("pi-a", 1, 400, 400, 40, 40, allow=True)], machine="Panel Saw"))
        self.assertIn("machine_rotation_forbidden", codes(saw))
        orthogonal = draft(
            {
                "schema": 1,
                "pieces": [row("pi-a", 400, 400, rotation=90)],
                "boards": boards(1),
            }
        )
        self.assertTrue(
            review_saved_draft(
                orthogonal,
                model([piece("pi-a", 1, 400, 400, 40, 40, allow=True)], machine="Panel Saw"),
            )["ready"]
        )

    def test_plain_piece_without_addons_stays_ready(self):
        trusted = model([piece("pi-a", 1, 20, 20, 400, 500)])
        layout = {"schema": 1, "pieces": [row("pi-a", 20, 20)], "boards": boards(1)}
        result = review_saved_draft(draft(layout), trusted)
        self.assertTrue(result["ready"], result["issues"])
        self.assertNotIn("geometry_unproven", codes(result))
        self.assertNotIn("addon_material_conflict", codes(result))

    def test_each_supported_addon_is_ready_when_clear(self):
        cases = [
            liner_fields(side="edge_width_top", offset=2, width=1.8, start=2, length=30),
            groove_fields(side="edge_width_top", offset=5, width=1.8, start=2, length=20),
            handle_fields(side="edge_long_left", offset=5, width=1.8, start=5, length=15),
        ]
        for machining in cases:
            trusted = model(
                [piece("pi-a", 1, 100, 100, 400, 500, machining=machining)],
                kerf=4,
            )
            layout = {"schema": 1, "pieces": [row("pi-a", 100, 100)], "boards": boards(1)}
            result = review_saved_draft(draft(layout), trusted)
            self.assertTrue(result["ready"], (machining, result["issues"]))
            self.assertNotIn("geometry_unproven", codes(result))

    def test_multiple_liners_on_one_piece_are_reviewed(self):
        machining = liner_fields(
            side="edge_width_top",
            offset=2,
            width=1.8,
            start=1,
            length=20,
            specs=[
                {
                    "id": "liner_1",
                    "side": "edge_width_top",
                    "offset_cm": 2,
                    "start_cm": 1,
                    "length_cm": 20,
                },
                {
                    "id": "liner_2",
                    "side": "edge_long_left",
                    "offset_cm": 3,
                    "start_cm": 2,
                    "length_cm": 25,
                },
            ],
        )
        trusted = model([piece("pi-a", 1, 80, 80, 500, 600, machining=machining)], kerf=4)
        layout = {"schema": 1, "pieces": [row("pi-a", 80, 80)], "boards": boards(1)}
        result = review_saved_draft(draft(layout), trusted)
        self.assertTrue(result["ready"], result["issues"])

    def test_addon_survives_board_move_and_free_rotation(self):
        machining = liner_fields(side="edge_width_top", offset=2, width=1.8, start=2, length=20)
        trusted = model(
            [
                piece("pi-a", 1, 40, 40, 400, 500, machining=machining, allow=True),
                piece("pi-b", 2, 40, 40, 300, 300, entry_sheet=2),
            ],
            sheets={
                1: {"resource_kind": "FULL_BOARD", "usable_width_mm": 1200, "usable_length_mm": 2400},
                2: {"resource_kind": "FULL_BOARD", "usable_width_mm": 1200, "usable_length_mm": 2400},
            },
            kerf=4,
            machine="CNC Router",
        )
        moved = draft(
            {
                "schema": 1,
                "pieces": [
                    row("pi-a", 40, 40, sheet=2, rotation=15),
                    row("pi-b", 600, 40, sheet=2),
                ],
                "boards": boards(1, 2),
            }
        )
        result = review_saved_draft(moved, trusted)
        self.assertTrue(result["ready"], result["issues"])

    def test_addon_conflict_with_neighbour_and_glass_host_material(self):
        machining = {
            "extra_liner": 1,
            "liner_reference_side": "edge_width_top",
            "liner_offset_cm": 0,
            "liner_width_cm": 1.8,
            "liner_start_cm": 0,
            "liner_length_cm": 0,
            "liner_specs_json": "",
        }
        neighbour = model(
            [
                piece("pi-a", 1, 0, 0, 400, 500, machining=machining),
                piece("pi-b", 2, 401, 0, 400, 500),
            ],
            kerf=4,
        )
        layout = {
            "schema": 1,
            "pieces": [row("pi-a", 0, 0), row("pi-b", 401, 0)],
            "boards": boards(1),
        }
        conflicted = review_saved_draft(draft(layout), neighbour)
        self.assertIn("addon_material_conflict", codes(conflicted))
        addon_issue = next(
            issue for issue in conflicted["issues"] if issue["code"] == "addon_material_conflict"
        )
        self.assertEqual(addon_issue["addon_kind"], "liner")
        self.assertTrue(addon_issue["reason"])

        # Guest pressed against the glass hole edge: host material is the obstacle.
        hole = rect(100, 100, 250, 250)
        guest_machining = liner_fields(
            side="edge_long_left", offset=0, width=1.8, start=1, length=5
        )
        glass = model(
            [
                piece("pi-host", 1, 0, 0, 400, 400, hole=hole, piece_type="Glass Door"),
                piece(
                    "pi-guest",
                    2,
                    102,
                    160,
                    80,
                    80,
                    host=1,
                    machining=guest_machining,
                ),
            ],
            kerf=10,
        )
        glass_layout = {
            "schema": 1,
            "pieces": [row("pi-host", 0, 0), row("pi-guest", 102, 160, host=1)],
            "boards": boards(1),
        }
        glass_result = review_saved_draft(draft(glass_layout), glass)
        self.assertFalse(glass_result["ready"])
        self.assertTrue(
            {"addon_material_conflict", "hole_kerf_clearance"} & set(codes(glass_result)),
            glass_result["issues"],
        )

    def test_hosted_addon_inside_glass_hole_can_be_ready(self):
        hole = rect(100, 100, 250, 250)
        machining = liner_fields(side="edge_width_top", offset=2, width=1.0, start=1, length=4)
        trusted = model(
            [
                piece("pi-host", 1, 0, 0, 400, 400, hole=hole, piece_type="Glass Door"),
                piece(
                    "pi-guest",
                    2,
                    160,
                    160,
                    100,
                    100,
                    host=1,
                    machining=machining,
                ),
            ],
            kerf=4,
        )
        layout = {
            "schema": 1,
            "pieces": [row("pi-host", 0, 0), row("pi-guest", 160, 160, host=1)],
            "boards": boards(1),
        }
        result = review_saved_draft(draft(layout), trusted)
        self.assertTrue(result["ready"], result["issues"])
        self.assertNotIn("addon_material_conflict", codes(result))

    def test_layer_visibility_is_irrelevant_and_special_stays_unproven(self):
        machining = liner_fields(side="edge_width_top", offset=2, width=1.8, start=2, length=20)
        trusted = model([piece("pi-a", 1, 100, 100, 400, 500, machining=machining)], kerf=4)
        # No overlay elements / layer table are consulted by review_saved_draft.
        layout = {"schema": 1, "pieces": [row("pi-a", 100, 100)], "boards": boards(1)}
        visible = review_saved_draft(draft(layout), trusted)
        self.assertTrue(visible["ready"], visible["issues"])
        # Hiding addon_overlay in the UI cannot change readiness: the trusted
        # model is field-driven, not layer-driven.
        trusted_with_noise = copy.deepcopy(trusted)
        trusted_with_noise["hidden_addon_overlay_kinds"] = ["liner", "back_groove"]
        hidden = review_saved_draft(draft(layout), trusted_with_noise)
        self.assertEqual(codes(visible), codes(hidden))
        self.assertEqual(visible["ready"], hidden["ready"])

        special = model(
            [
                piece(
                    "pi-s",
                    1,
                    100,
                    100,
                    400,
                    500,
                    piece_type="Special",
                    outline=None,
                    machining=machining,
                )
            ],
            kerf=4,
        )
        # Provide no outline so piece geometry is unproven; addon also unproven.
        special_piece = special["pieces"]["pi-s"]
        special_piece["outline_mm"] = None
        special_layout = {"schema": 1, "pieces": [row("pi-s", 100, 100)], "boards": boards(1)}
        result = review_saved_draft(draft(special_layout), special)
        self.assertFalse(result["ready"])
        unproven = [issue for issue in result["issues"] if issue["code"] == "geometry_unproven"]
        self.assertTrue(unproven)
        self.assertTrue(any(issue.get("addon_kind") == "liner" for issue in unproven) or any(
            issue.get("reason") for issue in unproven
        ))

    def test_tool_disk_into_neighbour_is_rejected_without_double_kerf(self):
        from almdina_erp.almdina_erp.domain.cutting.board_editor_draft_review import (
            _addon_rules,
        )

        kerf = 4.0
        # Pieces themselves keep a safe gap (> kerf). The add-on path is forced
        # into the neighbour so only the cutter-disk rule can fire.
        pieces = [
            {
                "piece_instance_id": "pi-a",
                "piece_id": 1,
                "label": "pi-a",
                "sheet_no": 1,
                "local_x_mm": 0,
                "local_y_mm": 0,
                "rotation_deg": 0,
                "outline_mm": rect(0, 0, 400, 500),
                "machining_paths": [
                    {
                        "kind": "liner",
                        "path_index": 0,
                        # Tip sits 1 mm from the neighbour. Cutter radius = kerf/2 = 2,
                        # so the disk enters neighbour material while piece gaps stay safe.
                        "path_mm": [[20, 30], [419, 30], [419, 45], [20, 45]],
                    }
                ],
            },
            {
                "piece_instance_id": "pi-b",
                "piece_id": 2,
                "label": "pi-b",
                "sheet_no": 1,
                "local_x_mm": 420,
                "local_y_mm": 0,
                "rotation_deg": 0,
                "outline_mm": rect(420, 0, 400, 500),
                "machining_paths": [],
            },
        ]
        issues = []
        _addon_rules(
            pieces,
            {
                "1": {
                    "sheet_no": 1,
                    "usable_width_mm": 1200,
                    "usable_length_mm": 2400,
                }
            },
            kerf,
            issues,
        )
        self.assertEqual([item["code"] for item in issues], ["addon_material_conflict"])
        self.assertEqual(issues[0]["addon_kind"], "liner")
        self.assertTrue(issues[0]["reason"])

        # Parametric tip with exact kerf gap does not invent a second piece-kerf hit.
        machining = {
            "extra_liner": 1,
            "liner_reference_side": "edge_width_top",
            "liner_offset_cm": 0,
            "liner_width_cm": 1.8,
            "liner_start_cm": 0,
            "liner_length_cm": 0,
            "liner_specs_json": "",
        }
        trusted = model(
            [
                piece("pi-a", 1, 0, 0, 400, 500, machining=machining),
                piece("pi-b", 2, 400 + kerf, 0, 400, 500),
            ],
            kerf=kerf,
        )
        layout = {
            "schema": 1,
            "pieces": [row("pi-a", 0, 0), row("pi-b", 400 + kerf, 0)],
            "boards": boards(1),
        }
        ready = review_saved_draft(draft(layout), trusted)
        self.assertTrue(ready["ready"], ready["issues"])
        self.assertNotIn("kerf_clearance", codes(ready))
        self.assertNotIn("addon_material_conflict", codes(ready))

    def test_all_addons_survive_move_and_free_rotation(self):
        cases = [
            ("liner", liner_fields(side="edge_width_top", offset=2, width=1.8, start=2, length=20)),
            ("back_groove", groove_fields(side="edge_width_top", offset=5, width=1.8, start=2, length=20)),
            (
                "recessed_handle_cutout",
                handle_fields(side="edge_long_left", offset=5, width=1.8, start=5, length=15),
            ),
        ]
        for kind, machining in cases:
            trusted = model(
                [piece("pi-a", 1, 80, 80, 400, 500, machining=machining, allow=True)],
                kerf=4,
                machine="CNC Router",
            )
            layout = {
                "schema": 1,
                "pieces": [row("pi-a", 120, 90, rotation=18)],
                "boards": boards(1),
            }
            result = review_saved_draft(draft(layout), trusted)
            self.assertTrue(result["ready"], (kind, result["issues"]))
            self.assertNotIn("geometry_unproven", codes(result))
            self.assertNotIn("addon_material_conflict", codes(result))

    def test_piece_outside_board_differs_from_allowed_addon_board_extension(self):
        # Material past the usable sheet is a placement fault.
        outside = model([piece("pi-a", 1, 20, 20, 400, 500)], kerf=4)
        outside_layout = {
            "schema": 1,
            "pieces": [row("pi-a", 1100, 20)],
            "boards": boards(1),
        }
        outside_result = review_saved_draft(draft(outside_layout), outside)
        self.assertTrue(
            {"partial_board_overlap", "outside_usable_sheet"} & set(codes(outside_result)),
            outside_result["issues"],
        )

        # Contour-end liner tip may leave the usable sheet; that alone is not a
        # readiness fault under the historical extension_conflict board policy.
        machining = {
            "extra_liner": 1,
            "liner_reference_side": "edge_width_top",
            "liner_offset_cm": 0,
            "liner_width_cm": 1.8,
            "liner_start_cm": 0,
            "liner_length_cm": 0,
            "liner_specs_json": "",
        }
        # Piece flush to the left usable edge so the tip extends to x < 0.
        edge = model(
            [piece("pi-a", 1, 0, 40, 400, 500, machining=machining)],
            sheets={1: {"resource_kind": "FULL_BOARD", "usable_width_mm": 1200, "usable_length_mm": 2400}},
            kerf=4,
        )
        edge_layout = {"schema": 1, "pieces": [row("pi-a", 0, 40)], "boards": boards(1)}
        edge_result = review_saved_draft(draft(edge_layout), edge)
        self.assertTrue(edge_result["ready"], edge_result["issues"])
        self.assertNotIn("addon_material_conflict", codes(edge_result))
        self.assertNotIn("outside_usable_sheet", codes(edge_result))
        self.assertNotIn("partial_board_overlap", codes(edge_result))

    def test_changed_source_is_not_merged_and_review_does_not_write(self):
        trusted = model([piece("pi-a", 1, 20, 20, 100, 80)])
        layout = {"schema": 1, "pieces": [row("pi-a", 20, 20)], "boards": boards(1)}
        before = copy.deepcopy(layout)
        result = review_saved_draft(
            draft(layout, compatible=False, conflict="source", distribution_fingerprint="old"),
            trusted,
        )
        self.assertFalse(result["ready"])
        self.assertEqual(codes(result), ["source_changed"])
        self.assertEqual(result["distribution_fingerprint"], "old")
        self.assertEqual(layout, before)
        self.assertFalse(draft_review_allowed(has_plan_view=False))
        self.assertTrue(draft_review_allowed(has_plan_view=True))
        source = (APP / "services" / "board_editor_draft_review_service.py").read_text(encoding="utf-8")
        self.assertIn("draft_review_allowed", source)
        self.assertIn("_plan_view_allowed", source)
        self.assertIn("frappe.PermissionError", source)
        self.assertIn("_load_plan_for_order", source)
        self.assertNotIn(".save(", source)
        self.assertNotIn("snapshot_json", source)
        self.assertEqual(source.count("approves_plan"), 1)


if __name__ == "__main__":
    unittest.main()
