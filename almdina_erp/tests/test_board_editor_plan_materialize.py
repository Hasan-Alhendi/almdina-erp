"""Board-editor draft → Cutting Plan snapshot conversion."""

from __future__ import annotations

import copy
import math
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.cutting.board_editor_plan_create import (
    CreateBoardEditorPlanCommand,
    create_write_allowed,
    execute_create,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_plan_materialize import (
    BoardEditorMaterializeError,
    METHOD_KEY,
    materialize_plan_snapshot,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import polygon_area
from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    BOARD_EDITOR,
    manufacturing_actions_allowed,
)

APP = Path(__file__).resolve().parents[1] / "almdina_erp"


def rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def projection_piece(instance, piece_id, x, y, w, h, **extra):
    placement = {"x": x / 10.0, "y": y / 10.0, "w": w / 10.0, "h": h / 10.0, "rotated": False}
    piece = {
        "piece_instance_id": instance,
        "piece_id": piece_id,
        "label": instance,
        "sheet_no": extra.get("sheet", 1),
        "placement_cm": placement,
        "allow_rotation": extra.get("allow", True),
        "allow_rotation_proven": extra.get("proven", True),
        "piece_type": extra.get("piece_type", "Regular"),
        "original_w": extra.get("original_w", w / 10.0),
        "original_h": extra.get("original_h", h / 10.0),
        "resource_kind": extra.get("kind", "FULL_BOARD"),
        "glass_host_piece_id": extra.get("host"),
        "glass_hole_local_mm": extra.get("hole"),
    }
    for key, value in (extra.get("machining") or {}).items():
        piece[key] = value
    return piece


def projection(pieces, sheets=None, elements=None, kerf_cm=0.4):
    sheet_map = sheets or {
        1: {"sheet_no": 1, "resource_kind": "FULL_BOARD", "usable_width_mm": 1200, "usable_length_mm": 2400},
    }
    return {
        "pieces": pieces,
        "board": {"kerf_cm": kerf_cm},
        "sheets": [
            {
                "sheet_no": number,
                "resource_kind": info.get("resource_kind", "FULL_BOARD"),
                # trusted_model_from_projection reads centimetre sheet fields.
                "usable_width_cm": info.get("usable_width_mm", 1200) / 10.0,
                "usable_length_cm": info.get("usable_length_mm", 2400) / 10.0,
                "full_width_cm": info.get("usable_width_mm", 1200) / 10.0,
                "full_length_cm": info.get("usable_length_mm", 2400) / 10.0,
            }
            for number, info in sheet_map.items()
        ],
        "elements": elements
        or [
            {
                "kind": "finished_outline",
                "piece_instance_id": piece["piece_instance_id"],
                "geometry": {
                    "outer": rect(
                        piece["placement_cm"]["x"] * 10,
                        piece["placement_cm"]["y"] * 10,
                        piece["placement_cm"]["w"] * 10,
                        piece["placement_cm"]["h"] * 10,
                    )
                },
            }
            for piece in pieces
        ],
    }


def source_snapshot(pieces, sheets=None):
    sheet_nos = sorted({int(piece["sheet_no"]) for piece in pieces})
    sheet_meta = sheets or {
        number: {
            "sheet_no": number,
            "resource_kind": "FULL_BOARD",
            "w": 120.0,
            "h": 240.0,
            "usable_width_cm": 120.0,
            "usable_length_cm": 240.0,
            "full_width_cm": 122.0,
            "full_length_cm": 244.0,
            "source_area_m2": 1.2 * 2.4,
        }
        for number in sheet_nos
    }
    return {
        "sheets": [
            {
                **sheet_meta[number],
                "pieces": [
                    {
                        "piece_instance_id": piece["piece_instance_id"],
                        "id": piece["piece_id"],
                        "label": piece["label"],
                        "x": piece["placement_cm"]["x"],
                        "y": piece["placement_cm"]["y"],
                        "w": piece["placement_cm"]["w"],
                        "h": piece["placement_cm"]["h"],
                        "original_w": piece["original_w"],
                        "original_h": piece["original_h"],
                        "rotated": False,
                        "area_m2": (piece["placement_cm"]["w"] * piece["placement_cm"]["h"]) / 10000.0,
                        "resource_kind": piece.get("resource_kind", "FULL_BOARD"),
                        "cut_path": {"stale": True, "path": [[0, 0], [1, 1]]},
                        "overlays": [{"kind": "old", "geometry": {"path": [[0, 0]]}}],
                        "glass_host_piece_id": piece.get("glass_host_piece_id"),
                        "geometry": {
                            "schema_version": 1,
                            "unit": "mm",
                            "coordinate_space": "usable_sheet",
                            "outer": rect(
                                piece["placement_cm"]["x"] * 10,
                                piece["placement_cm"]["y"] * 10,
                                piece["placement_cm"]["w"] * 10,
                                piece["placement_cm"]["h"] * 10,
                            ),
                            "holes": [piece["glass_hole_local_mm"]]
                            if piece.get("glass_hole_local_mm")
                            else [],
                        }
                        if piece.get("piece_type") != "skip_geo"
                        else None,
                    }
                    for piece in pieces
                    if int(piece["sheet_no"]) == number
                ],
            }
            for number in sheet_nos
        ],
        "used_area_m2": 0.1,
        "total_board_area_m2": 2.88,
        "waste_area_m2": 2.78,
        "method_key": "system",
        "cut_path": {"legacy": True},
    }


def layout_rows(pieces, boards=(1,), **overrides):
    rows = []
    for piece in pieces:
        instance = piece["piece_instance_id"]
        extra = overrides.get(instance, {})
        rows.append(
            {
                "piece_instance_id": instance,
                "sheet_no": extra.get("sheet", piece["sheet_no"]),
                "local_x_mm": extra.get("x", piece["placement_cm"]["x"] * 10),
                "local_y_mm": extra.get("y", piece["placement_cm"]["y"] * 10),
                "rotation_deg": extra.get("rotation", 0),
                "distribution": extra.get("distribution", "active"),
                "exclusion_reason": extra.get("reason"),
                "glass_host_piece_id": extra.get("host", piece.get("glass_host_piece_id")),
            }
        )
    return {
        "schema": 1,
        "pieces": rows,
        "boards": [{"sheet_no": number, "origin_x_mm": 0, "origin_y_mm": 0, "user_moved": False} for number in boards],
    }


def draft_payload(layout, *, version=1, fingerprint="stored", revision="rev-1", fingerprint_src="fp-1"):
    return {
        "present": True,
        "compatible": True,
        "conflict": None,
        "draft_version": version,
        "source_content_revision": revision,
        "source_input_fingerprint": fingerprint_src,
        "distribution_fingerprint": fingerprint,
        "layout": layout,
    }


def world_centroid(geometry_outer):
    xs = [point[0] for point in geometry_outer]
    ys = [point[1] for point in geometry_outer]
    return ((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5)


class BoardEditorMaterializeTests(unittest.TestCase):
    def test_move_within_and_between_boards(self):
        pieces = [
            projection_piece("A", 1, 0, 0, 400, 300),
            projection_piece("B", 2, 500, 0, 200, 200, sheet=1),
        ]
        sheets = {
            1: {"sheet_no": 1, "resource_kind": "FULL_BOARD", "usable_width_mm": 1200, "usable_length_mm": 2400},
            2: {"sheet_no": 2, "resource_kind": "FULL_BOARD", "usable_width_mm": 1200, "usable_length_mm": 2400},
        }
        proj = projection(pieces, sheets=sheets)
        source = source_snapshot(pieces, sheets={
            1: {"sheet_no": 1, "resource_kind": "FULL_BOARD", "w": 120, "h": 240, "usable_width_cm": 120, "usable_length_cm": 240, "full_width_cm": 122, "full_length_cm": 244, "source_area_m2": 2.88},
            2: {"sheet_no": 2, "resource_kind": "FULL_BOARD", "w": 120, "h": 240, "usable_width_cm": 120, "usable_length_cm": 240, "full_width_cm": 122, "full_length_cm": 244, "source_area_m2": 2.88},
        })
        # Keep sheet 2 in source by cloning B onto sheet 2 for sheet metadata only.
        source["sheets"].append(copy.deepcopy(source["sheets"][0]))
        source["sheets"][1]["sheet_no"] = 2
        source["sheets"][1]["pieces"] = []
        layout = layout_rows(
            pieces,
            boards=(1, 2),
            A={"x": 50, "y": 80},
            B={"sheet": 2, "x": 10, "y": 20},
        )
        draft = draft_payload(layout)
        snapshot = materialize_plan_snapshot(
            draft=draft,
            projection=proj,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
        )
        by_id = {
            piece["piece_instance_id"]: (sheet["sheet_no"], piece)
            for sheet in snapshot["sheets"]
            for piece in sheet["pieces"]
        }
        self.assertEqual(by_id["A"][0], 1)
        self.assertAlmostEqual(by_id["A"][1]["x"], 5.0)
        self.assertAlmostEqual(by_id["A"][1]["y"], 8.0)
        self.assertEqual(by_id["B"][0], 2)
        self.assertAlmostEqual(by_id["B"][1]["x"], 1.0)
        self.assertAlmostEqual(by_id["B"][1]["y"], 2.0)
        self.assertEqual(snapshot["method_key"], METHOD_KEY)
        self.assertEqual(snapshot["layout_origin"]["kind"], BOARD_EDITOR)
        self.assertFalse(snapshot["layout_origin"]["cut_path_carried"])
        self.assertNotIn("cut_path", by_id["A"][1])
        self.assertNotIn("cut_path", snapshot)

    def test_free_rotation_preserves_physical_dims_and_transforms_hole(self):
        hole = rect(40, 40, 80, 60)
        pieces = [projection_piece("A", 1, 0, 0, 400, 300, hole=hole, allow=True)]
        proj = projection(pieces)
        # Replace element outline with same rect; hole stays on piece.
        source = source_snapshot(pieces)
        layout = layout_rows(pieces, A={"x": 0, "y": 0, "rotation": 35})
        draft = draft_payload(layout)
        snapshot = materialize_plan_snapshot(
            draft=draft,
            projection=proj,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
        )
        piece = snapshot["sheets"][0]["pieces"][0]
        self.assertFalse(piece["rotated"])
        self.assertAlmostEqual(piece["rotation_deg"], 35.0)
        self.assertAlmostEqual(piece["w"], 40.0)
        self.assertAlmostEqual(piece["h"], 30.0)
        self.assertAlmostEqual(piece["original_w"], 40.0)
        self.assertAlmostEqual(piece["original_h"], 30.0)
        outer = piece["geometry"]["outer"]
        holes = piece["geometry"]["holes"]
        self.assertEqual(len(holes), 1)
        # Rigid transform preserves areas.
        self.assertAlmostEqual(polygon_area([(p[0], p[1]) for p in outer]), 400 * 300, places=4)
        self.assertAlmostEqual(polygon_area([(p[0], p[1]) for p in holes[0]]), 80 * 60, places=4)
        # Entry orientation is not re-applied as placement.rotated.
        self.assertFalse(piece.get("apply_rotated_to_geometry"))

    def test_host_guest_and_identities_stable(self):
        host_hole = rect(50, 50, 200, 200)
        pieces = [
            projection_piece("HOST", 1, 0, 0, 500, 500, hole=host_hole),
            # Draft hosting uses the host piece_id, not the instance string.
            projection_piece("GUEST", 2, 70, 70, 100, 100, host=1),
        ]
        elements = [
            {
                "kind": "finished_outline",
                "piece_instance_id": "HOST",
                "geometry": {"outer": rect(0, 0, 500, 500)},
            },
            {
                "kind": "finished_outline",
                "piece_instance_id": "GUEST",
                "geometry": {"outer": rect(70, 70, 100, 100)},
            },
        ]
        proj = projection(pieces, elements=elements)
        source = source_snapshot(pieces)
        layout = layout_rows(pieces, HOST={"x": 20, "y": 10}, GUEST={"x": 90, "y": 80, "host": 1})
        draft = draft_payload(layout)
        snapshot = materialize_plan_snapshot(
            draft=draft,
            projection=proj,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
        )
        by_id = {piece["piece_instance_id"]: piece for piece in snapshot["sheets"][0]["pieces"]}
        self.assertEqual(set(by_id), {"HOST", "GUEST"})
        self.assertEqual(by_id["GUEST"]["glass_host_piece_id"], 1)
        self.assertEqual(by_id["HOST"]["id"], 1)
        self.assertEqual(by_id["GUEST"]["id"], 2)

    def test_rejects_excluded_overlap_and_source_change(self):
        pieces = [
            projection_piece("A", 1, 0, 0, 400, 300),
            projection_piece("B", 2, 500, 0, 200, 200),
        ]
        proj = projection(pieces)
        source = source_snapshot(pieces)
        excluded = layout_rows(
            pieces,
            A={"distribution": "excluded", "reason": "removed_from_distribution"},
        )
        draft = draft_payload(excluded)
        with self.assertRaises(BoardEditorMaterializeError) as ctx:
            materialize_plan_snapshot(
                draft=draft,
                projection=proj,
                source_snapshot=source,
                machine_type="CNC Router",
                source_plan_name="PLAN-SRC",
                expected_draft_version=1,
                source_content_revision="rev-1",
                source_input_fingerprint="fp-1",
            )
        self.assertEqual(ctx.exception.code, "not_ready")

        overlap = layout_rows(pieces, B={"x": 50, "y": 50})
        draft = draft_payload(overlap)
        with self.assertRaises(BoardEditorMaterializeError) as ctx:
            materialize_plan_snapshot(
                draft=draft,
                projection=proj,
                source_snapshot=source,
                machine_type="CNC Router",
                source_plan_name="PLAN-SRC",
                expected_draft_version=1,
                source_content_revision="rev-1",
                source_input_fingerprint="fp-1",
            )
        self.assertEqual(ctx.exception.code, "not_ready")

        ready = draft_payload(layout_rows(pieces))
        ready["source_content_revision"] = "stale"
        with self.assertRaises(BoardEditorMaterializeError) as ctx:
            materialize_plan_snapshot(
                draft=ready,
                projection=proj,
                source_snapshot=source,
                machine_type="CNC Router",
                source_plan_name="PLAN-SRC",
                expected_draft_version=1,
                source_content_revision="rev-1",
                source_input_fingerprint="fp-1",
            )
        self.assertEqual(ctx.exception.code, "source_changed")

    def test_stats_recomputed_and_dxf_preapplied_orientation_not_doubled(self):
        # Pre-applied DXF orientation lives in outline already; draft rotation 0.
        pieces = [projection_piece("DXF", 9, 10, 20, 300, 150, original_w=15.0, original_h=30.0)]
        outline = rect(10, 20, 300, 150)
        proj = projection(
            pieces,
            elements=[{"kind": "finished_outline", "piece_instance_id": "DXF", "geometry": {"outer": outline}}],
        )
        source = source_snapshot(pieces)
        source["sheets"][0]["pieces"][0]["source_rotated_dims"] = True
        draft = draft_payload(layout_rows(pieces))
        snapshot = materialize_plan_snapshot(
            draft=draft,
            projection=proj,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
        )
        piece = snapshot["sheets"][0]["pieces"][0]
        self.assertAlmostEqual(piece["w"], 30.0)
        self.assertAlmostEqual(piece["h"], 15.0)
        self.assertFalse(piece["rotated"])
        self.assertAlmostEqual(piece["area_m2"], (300 * 150) / 1_000_000.0, places=6)
        self.assertGreater(snapshot["total_board_area_m2"], 0)
        self.assertAlmostEqual(
            snapshot["waste_area_m2"],
            snapshot["total_board_area_m2"] - snapshot["used_area_m2"],
            places=6,
        )

    def test_manufacturing_actions_allowed_for_board_editor(self):
        self.assertTrue(manufacturing_actions_allowed(BOARD_EDITOR))
        self.assertTrue(manufacturing_actions_allowed("System"))
        self.assertTrue(manufacturing_actions_allowed("Uploaded DXF"))

    def test_special_cnc_raw_keeps_type_and_does_not_promote_stock_rect(self):
        pieces = [
            projection_piece(
                "RAW",
                7,
                100,
                200,
                220,
                210,
                piece_type="Special",
                original_w=22,
                original_h=21,
            )
        ]
        pieces[0]["geometry_source"] = "cnc_raw_rect"
        pieces[0]["exact_geometry"] = False
        pieces[0]["special_representation"] = "cnc_raw"
        elements = [
            {
                "kind": "finished_outline",
                "piece_instance_id": "RAW",
                "geometry": {"outer": rect(100, 200, 220, 210)},
                "payload": {
                    "geometry_source": "cnc_raw_rect",
                    "special_representation": "cnc_raw",
                },
            }
        ]
        proj = projection(pieces, elements=elements)
        source = source_snapshot(pieces)
        source["sheets"][0]["pieces"][0]["piece_type"] = "Special"
        source["sheets"][0]["pieces"][0].pop("geometry", None)
        layout = layout_rows(pieces, RAW={"x": 150, "y": 180})
        draft = draft_payload(layout)
        snapshot = materialize_plan_snapshot(
            draft=draft,
            projection=proj,
            source_snapshot=source,
            machine_type="CNC Router",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
        )
        piece = snapshot["sheets"][0]["pieces"][0]
        self.assertEqual(piece["piece_type"], "Special")
        self.assertEqual(piece["piece_instance_id"], "RAW")
        self.assertAlmostEqual(piece["x"], 15.0)
        self.assertAlmostEqual(piece["y"], 18.0)
        self.assertAlmostEqual(piece["w"], 22.0)
        self.assertAlmostEqual(piece["h"], 21.0)
        self.assertNotIn("geometry", piece)


class BoardEditorPlanCreateApplicationTests(unittest.TestCase):
    def test_write_gate_and_idempotent_create(self):
        self.assertFalse(
            create_write_allowed(
                has_edit_capability=True,
                has_plan_view=True,
                order_status="Delivered",
            )
        )
        self.assertFalse(
            create_write_allowed(
                has_edit_capability=False,
                has_plan_view=True,
                order_status="Draft",
            )
        )
        self.assertTrue(
            create_write_allowed(
                has_edit_capability=True,
                has_plan_view=True,
                order_status="Draft",
            )
        )

        pieces = [projection_piece("A", 1, 0, 0, 200, 200)]
        proj = projection(pieces)
        source = source_snapshot(pieces)
        layout = layout_rows(pieces)
        draft = draft_payload(layout)

        class DraftStore:
            def __init__(self):
                self.row = {
                    "name": "DRAFT-1",
                    "draft_version": 1,
                    "source_content_revision": "rev-1",
                    "source_input_fingerprint": "fp-1",
                    "distribution_fingerprint": draft["distribution_fingerprint"],
                    "layout_json": draft["layout"],
                    "last_create_request_id": "",
                    "last_created_plan": "",
                    "last_created_draft_version": 0,
                }
                self.recorded = None

            def lock_draft(self, order_name, plan_name):
                return dict(self.row)

            def record_create(self, *, draft_name, request_id, plan_name, draft_version):
                self.recorded = (draft_name, request_id, plan_name, draft_version)
                self.row["last_create_request_id"] = request_id
                self.row["last_created_plan"] = plan_name
                self.row["last_created_draft_version"] = draft_version

        class PlanPort:
            def __init__(self):
                self.created = []
                self.source_mutated = False

            def existing_revisions(self, order_name):
                return [1]

            def create_board_editor_draft(self, **kwargs):
                self.created.append(kwargs)
                return {"name": "CP-NEW", "revision": 2, "status": "Draft"}

            def apply_snapshot(self, **kwargs):
                self.created.append(("apply", kwargs["plan_name"], kwargs["snapshot"]["method_key"]))
                return {"name": kwargs["plan_name"], "revision": 2, "status": "Draft"}

            def discard_incomplete_plan(self, plan_name):
                self.created.append(("discard", plan_name))

            def load_source_plan(self, order_name, plan_name):
                return {
                    "name": plan_name,
                    "order_name": order_name,
                    "status": "Approved",
                    "source_type": "System",
                    "revision": 1,
                    "optimization_mode": "auto_pro",
                    "machine_type": "CNC Router",
                    "optimization_time_limit_sec": 10,
                    "kerf_mm": 4,
                    "trim_margin_mm": 5,
                    "snapshot": source,
                }

        store = DraftStore()
        port = PlanPort()
        command = CreateBoardEditorPlanCommand(
            order_name="ORD-1",
            source_plan_name="PLAN-SRC",
            expected_draft_version=1,
            source_content_revision="rev-1",
            source_input_fingerprint="fp-1",
            create_request_id="req-1",
            draft_name="DRAFT-1",
        )
        first = execute_create(
            command,
            order_status="Draft",
            projection=proj,
            machine_type="CNC Router",
            draft_store=store,
            plan_port=port,
        )
        self.assertTrue(first["ok"])
        self.assertEqual(first["plan_name"], "CP-NEW")
        self.assertEqual(first["source_type"], BOARD_EDITOR)
        self.assertEqual(first["prefer_plan_tab"], "BoardEditor")
        self.assertFalse(first["manufacturing_blocked"])
        self.assertEqual(port.created[0]["based_on_plan"], "PLAN-SRC")
        self.assertEqual(len([row for row in port.created if isinstance(row, dict)]), 1)

        second = execute_create(
            command,
            order_status="Draft",
            projection=proj,
            machine_type="CNC Router",
            draft_store=store,
            plan_port=port,
        )
        self.assertTrue(second["ok"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(second["plan_name"], "CP-NEW")
        self.assertEqual(len([row for row in port.created if isinstance(row, dict)]), 1)

        conflict = execute_create(
            CreateBoardEditorPlanCommand(
                order_name="ORD-1",
                source_plan_name="PLAN-SRC",
                expected_draft_version=2,
                source_content_revision="rev-1",
                source_input_fingerprint="fp-1",
                create_request_id="req-1",
            ),
            order_status="Draft",
            projection=proj,
            machine_type="CNC Router",
            draft_store=store,
            plan_port=port,
        )
        self.assertFalse(conflict["ok"])
        self.assertEqual(conflict["code"], "idempotency_version_conflict")

    def test_version_conflict_rejects_without_create(self):
        pieces = [projection_piece("A", 1, 0, 0, 200, 200)]
        proj = projection(pieces)
        source = source_snapshot(pieces)
        layout = layout_rows(pieces)
        draft = draft_payload(layout, version=3)

        class DraftStore:
            def lock_draft(self, order_name, plan_name):
                return {
                    "name": "DRAFT-1",
                    "draft_version": 3,
                    "source_content_revision": "rev-1",
                    "source_input_fingerprint": "fp-1",
                    "distribution_fingerprint": draft["distribution_fingerprint"],
                    "layout_json": draft["layout"],
                    "last_create_request_id": "",
                    "last_created_plan": "",
                    "last_created_draft_version": 0,
                }

            def record_create(self, **kwargs):
                raise AssertionError("must not record")

        class PlanPort:
            def existing_revisions(self, order_name):
                raise AssertionError("must not create")

            def create_board_editor_draft(self, **kwargs):
                raise AssertionError("must not create")

            def apply_snapshot(self, **kwargs):
                raise AssertionError("must not create")

            def discard_incomplete_plan(self, plan_name):
                raise AssertionError("must not discard")

            def load_source_plan(self, order_name, plan_name):
                return {
                    "name": plan_name,
                    "order_name": order_name,
                    "machine_type": "CNC Router",
                    "kerf_mm": 4,
                    "trim_margin_mm": 5,
                    "optimization_mode": "auto_pro",
                    "optimization_time_limit_sec": 10,
                    "snapshot": source,
                }

        result = execute_create(
            CreateBoardEditorPlanCommand(
                order_name="ORD-1",
                source_plan_name="PLAN-SRC",
                expected_draft_version=1,
                source_content_revision="rev-1",
                source_input_fingerprint="fp-1",
                create_request_id="req-2",
            ),
            order_status="Draft",
            projection=proj,
            machine_type="CNC Router",
            draft_store=DraftStore(),
            plan_port=PlanPort(),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "version_conflict")

    def test_draft_source_create_and_apply_failure_rolls_back(self):
        pieces = [projection_piece("A", 1, 0, 0, 200, 200, allow=True)]
        proj = projection(pieces)
        source = source_snapshot(pieces)
        layout = layout_rows(pieces)
        draft = draft_payload(layout)
        base = "CP-SRC|2026-01-01|1|fp-a|0"
        legacy = f"{base}|idle"
        live = f"{base}|0"

        class DraftStore:
            def __init__(self):
                self.row = {
                    "name": "DRAFT-1",
                    "draft_version": 1,
                    "source_content_revision": legacy,
                    "source_input_fingerprint": "fp-1",
                    "distribution_fingerprint": draft["distribution_fingerprint"],
                    "layout_json": draft["layout"],
                    "last_create_request_id": "",
                    "last_created_plan": "",
                    "last_created_draft_version": 0,
                }
                self.recorded = None

            def lock_draft(self, order_name, plan_name):
                return dict(self.row)

            def record_create(self, **kwargs):
                self.recorded = kwargs

        class PlanPort:
            def __init__(self):
                self.created = []
                self.discarded = []
                self.fail_apply = False
                self.source_status = "Draft"

            def existing_revisions(self, order_name):
                return [1]

            def create_board_editor_draft(self, **kwargs):
                self.created.append(kwargs)
                return {"name": "CP-BE-1", "revision": 2, "status": "Draft"}

            def apply_snapshot(self, **kwargs):
                if self.fail_apply:
                    raise RuntimeError("snapshot_apply_boom")
                return {"name": kwargs["plan_name"], "revision": 2, "status": "Draft"}

            def discard_incomplete_plan(self, plan_name):
                self.discarded.append(plan_name)

            def load_source_plan(self, order_name, plan_name):
                return {
                    "name": plan_name,
                    "order_name": order_name,
                    "status": self.source_status,
                    "source_type": "System",
                    "revision": 1,
                    "optimization_mode": "auto_pro",
                    "machine_type": "CNC Router",
                    "optimization_time_limit_sec": 10,
                    "kerf_mm": 4,
                    "trim_margin_mm": 5,
                    "snapshot": source,
                }

        store = DraftStore()
        port = PlanPort()
        # Legacy idle token on the draft must still match the stable live bit.
        ok = execute_create(
            CreateBoardEditorPlanCommand(
                order_name="ORD-1",
                source_plan_name="PLAN-SRC",
                expected_draft_version=1,
                source_content_revision=live,
                source_input_fingerprint="fp-1",
                create_request_id="req-draft-src",
                draft_name="DRAFT-1",
            ),
            order_status="Draft",
            projection=proj,
            machine_type="CNC Router",
            draft_store=store,
            plan_port=port,
        )
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(ok["based_on_plan"], "PLAN-SRC")
        self.assertEqual(port.created[0]["based_on_plan"], "PLAN-SRC")
        self.assertEqual(store.recorded["plan_name"], "CP-BE-1")
        self.assertEqual(store.row["draft_version"], 1)

        # Failed apply must discard the incomplete plan and leave the draft untouched.
        store.row["last_create_request_id"] = ""
        store.row["last_created_plan"] = ""
        store.recorded = None
        port.fail_apply = True
        port.created.clear()
        with self.assertRaises(RuntimeError):
            execute_create(
                CreateBoardEditorPlanCommand(
                    order_name="ORD-1",
                    source_plan_name="PLAN-SRC",
                    expected_draft_version=1,
                    source_content_revision=live,
                    source_input_fingerprint="fp-1",
                    create_request_id="req-fail",
                    draft_name="DRAFT-1",
                ),
                order_status="Draft",
                projection=proj,
                machine_type="CNC Router",
                draft_store=store,
                plan_port=port,
            )
        self.assertEqual(port.discarded, ["CP-BE-1"])
        self.assertIsNone(store.recorded)
        self.assertEqual(store.row["draft_version"], 1)
        self.assertEqual(store.row["source_content_revision"], legacy)

        # After failure, a new save version can still apply without artificial conflict.
        store.row["draft_version"] = 2
        store.row["source_content_revision"] = live
        port.fail_apply = False
        port.discarded.clear()
        port.created.clear()
        again = execute_create(
            CreateBoardEditorPlanCommand(
                order_name="ORD-1",
                source_plan_name="PLAN-SRC",
                expected_draft_version=2,
                source_content_revision=live,
                source_input_fingerprint="fp-1",
                create_request_id="req-retry",
                draft_name="DRAFT-1",
            ),
            order_status="Draft",
            projection=proj,
            machine_type="CNC Router",
            draft_store=store,
            plan_port=port,
        )
        self.assertTrue(again["ok"], again)
        self.assertEqual(again["plan_name"], "CP-BE-1")
        self.assertEqual(port.discarded, [])

    def test_cutting_plan_validate_allows_board_editor_from_draft_source(self):
        source = (APP / "doctype" / "cutting_plan" / "cutting_plan.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("is_board_editor_source(self.source_type)", source)
        self.assertIn(
            "A new Cutting Plan revision must be based on an approved plan.",
            source,
        )
        # The approved-only gate remains for non-Board-Editor revisions.
        guard = source.split("def _validate_revision_parent", 1)[1].split(
            "def _validate_working_settings", 1
        )[0]
        self.assertIn("board_editor_copy", guard)
        self.assertIn("if self.is_new() and parent.status != APPROVED:", guard)

    def test_service_distinguishes_create_errors_from_save_conflicts(self):
        service = (APP / "services" / "board_editor_plan_create_service.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"create_failed"', service)
        self.assertIn("frappe.ValidationError", service)
        self.assertIn('result["prefer_plan_tab"] = "BoardEditor"', service)
        adapter = (
            APP / "infrastructure" / "frappe" / "board_editor_plan_create_adapter.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def discard_incomplete_plan", adapter)


if __name__ == "__main__":
    unittest.main()
