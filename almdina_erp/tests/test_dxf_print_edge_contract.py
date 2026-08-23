from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STRICT = ROOT / "almdina_erp" / "services" / "strict_dxf_import_service.py"
TABS = ROOT / "public" / "js" / "door_cutting_order_plan_tabs_ux.js"
RENDERER = ROOT / "public" / "js" / "door_cutting_order_cutting_plan_renderer.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_accepted_dxf_piece_inherits_all_four_semantic_edge_flags():
    strict = _source(STRICT)
    for fieldname in [
        "edge_long_right",
        "edge_long_left",
        "edge_width_top",
        "edge_width_bottom",
    ]:
        assert fieldname in strict
    assert 'piece.update(_edge_print_contract(spec))' in strict
    assert '"edge_profiles"' in strict


def test_edge_contract_keeps_order_orientation_and_renderer_owns_rotation():
    strict = _source(STRICT)
    renderer = _source(RENDERER)

    assert '"rotation_owned_by_renderer": True' in strict
    assert "if (!piece.rotated)" in renderer
    assert "top = piece.edge_long_left ? 1 : 0;" in renderer
    assert "bottom = piece.edge_long_right ? 1 : 0;" in renderer
    assert "right = piece.edge_width_top ? 1 : 0;" in renderer
    assert "left = piece.edge_width_bottom ? 1 : 0;" in renderer


def test_custom_dxf_and_system_plan_share_the_same_print_renderer():
    tabs = _source(TABS)
    renderer = _source(RENDERER)

    assert "frm.doc.custom_plan_json" in tabs
    assert 'getPlanForTab(frm, "Custom")' in tabs
    assert 'typeof renderer.print === "function"' in tabs
    assert "renderer.print(frm, plan)" in tabs
    assert "window.AlmdinaCuttingPlanRender" in renderer


def test_shared_renderer_draws_edge_markers_on_screen_and_print():
    renderer = _source(RENDERER)

    assert "render_piece_edge_lines(piece)" in renderer
    assert 'class="dco-edge-line"' in renderer
    assert ".dco-edge-line {" in renderer
    assert "border-color: #e00000 !important;" in renderer
