"""Isolated real-order inputs and actual persisted DXF round trip."""
from types import SimpleNamespace
import pytest

def assert_snapshot_dxf_roundtrip(tmp_path,outcome,*,rows=None,edge_profiles=None):
    import json
    import os
    from pathlib import Path
    import subprocess
    from almdina_erp.tests.frappe_test_stub import install_if_unavailable
    install_if_unavailable()
    from almdina_erp.tests.test_glass_opening_nesting import _lifecycle_placed_row
    from almdina_erp.tests.test_cutter_center_paths import _import,_order,_piece
    from almdina_erp.almdina_erp.application.orders.plan_snapshot_security import sanitize_plan_snapshot
    from almdina_erp.almdina_erp.services.export_validation_service import _plan_to_export_snapshot
    from almdina_erp.almdina_erp.services.dxf_export_service import _kerf_errors
    from almdina_erp.almdina_erp.services.dxf_autocad_normalization import rebuild_autocad_dxf
    count = len(outcome.snapshot["sheets"])
    full_w = outcome.snapshot["full_board_width_cm"] * 10
    full_h = outcome.snapshot["full_board_length_cm"] * 10
    usable_w = outcome.snapshot["usable_board_width_cm"] * 10
    usable_h = outcome.snapshot["usable_board_length_cm"] * 10
    kerf_mm = outcome.snapshot["kerf_cm"] * 10
    trim_mm = outcome.snapshot["trim_cm"] * 10
    saved = sanitize_plan_snapshot(json.loads(json.dumps(outcome.snapshot)))
    from almdina_erp.almdina_erp.application.cutting.board_editor_projection import project_board_editor
    before_projection = json.dumps(saved,sort_keys=True)
    editor = project_board_editor(saved)
    expected_placements = {(s["sheet_no"],p["piece_instance_id"]):
        {key:p[key] for key in ("x","y","w","h","rotated")}
        for s in saved["sheets"] for p in s["pieces"]}
    assert {(p["sheet_no"],p["piece_instance_id"]):p["placement_cm"] for p in editor["pieces"]} == expected_placements
    assert json.dumps(saved,sort_keys=True) == before_projection
    placed_rows = []
    for sheet in saved["sheets"]:
        for piece in sheet["pieces"]:
            row = _lifecycle_placed_row(piece,sheet["sheet_no"])
            for key,value in piece.items():
                if hasattr(row,key) or key=="liner_specs_json":
                    setattr(row,key,value)
            placed_rows.append(row)
    cutting_plan = SimpleNamespace(snapshot_json=json.dumps(saved),
        placed_pieces=placed_rows,
        sources=[SimpleNamespace(sheet_no=s["sheet_no"],source_type="Full Board",remnant=None,
            board_item=None,material="",color="",thickness_mm=18,full_width_mm=full_w,
            full_length_mm=full_h,usable_width_mm=usable_w,usable_length_mm=usable_h,source_area_m2=full_w*full_h/1e6)
            for s in saved["sheets"]],
        engine_version=saved["engine_version"],method_key=saved["method_key"],method_label=saved["method_label"],
        full_board_width_mm=full_w,full_board_length_mm=full_h,usable_board_width_mm=usable_w,usable_board_length_mm=usable_h,
        kerf_mm=kerf_mm,trim_margin_mm=trim_mm,used_area_m2=saved["used_area_m2"],total_source_area_m2=saved["total_board_area_m2"],
        waste_area_m2=saved["waste_area_m2"],required_boards=count)
    rebuilt = _plan_to_export_snapshot(cutting_plan)
    from almdina_erp.almdina_erp.domain.cutting.machining_overlay import machining_metadata
    # Reconstruction orders sheets by their persisted number; compare each
    # physical identity, including its board, rather than incidental row order.
    def machining_by_identity(plan):
        return {(s["sheet_no"],p["piece_instance_id"]): machining_metadata(p)
                for s in plan["sheets"] for p in s["pieces"]}
    assert machining_by_identity(saved) == machining_by_identity(rebuilt)
    assert not _kerf_errors(rebuilt)
    cases = tmp_path/"multi.json"
    cases.write_text(json.dumps([rebuilt]))
    subprocess.run(["node",str(Path(__file__).parents[1]/"tests/js/secure_dxf_topology_export.test.js")],
        check=True,capture_output=True,text=True,
        env=dict(os.environ,PERIMETER_CASES=str(cases),PERIMETER_OUTPUT_DIR=str(tmp_path)))
    path = tmp_path/"0.dxf"
    path.write_bytes(rebuild_autocad_dxf(path.read_bytes()))
    order_rows = rows or [dict(s,qty=1,piece_instance_id=s["piece_instance_id"].rsplit(":",1)[0])
                          for s in outcome.expanded_pieces]
    order = _order([_piece(**dict(s,cut_width_cm=s.get("cut_width_cm",s["width_cm"]),
                                cut_length_cm=s.get("cut_length_cm",s["length_cm"])))
                    for s in order_rows])
    order.kerf_mm = kerf_mm
    from unittest.mock import patch
    from almdina_erp.almdina_erp.services import piece_cut_dimension_service
    # The isolated fixture supplies the exact persisted band thicknesses; only
    # the database catalog port is replaced. Cut-dimension validation runs.
    if edge_profiles is None:
        imported = _import(str(path),order,kerf_mm=kerf_mm,trim_mm=trim_mm)
    else:
        with patch.object(piece_cut_dimension_service,"_default_profile_loader",lambda names: edge_profiles):
            imported = _import(str(path),order,kerf_mm=kerf_mm,trim_mm=trim_mm)
    def geometry(plan):
        return sorted((s["sheet_no"],*(round(p[k],6) for k in ("x","y","w","h")))
                      for s in plan["sheets"] for p in s["pieces"])
    assert saved["validation"]["is_valid"]
    assert geometry(saved) == geometry(rebuilt) == geometry(imported)
    assert sorted(p["piece_instance_id"] for s in saved["sheets"] for p in s["pieces"]) == sorted(
        p["piece_instance_id"] for s in imported["sheets"] for p in s["pieces"])
    from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import sheet_cut_line_quality
    import math
    import ezdxf
    from almdina_erp.tests.test_cutter_center_paths import _layer_segments
    # Imported protected contours remain conservative/unsupported for System
    # ranking. Measure the actual emitted CUT_PATH, rather than coercing them
    # back into rectangles to make an unavailable imported score look exact.
    actual = sum(math.dist(*segment) for segment in _layer_segments(ezdxf.readfile(path),"CUT_PATH"))
    assert actual == pytest.approx(sum(sheet_cut_line_quality(s,kerf_mm/10)[0] for s in saved["sheets"]),abs=.05)
    assert imported["saw_center_status"] == "Present"
    assert len(imported["sheets"]) == count
