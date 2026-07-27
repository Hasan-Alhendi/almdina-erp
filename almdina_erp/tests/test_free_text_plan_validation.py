from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_FIX = ROOT / "public" / "js" / "door_cutting_order_text_board_plan_ux.js"
HOOKS = ROOT / "hooks.py"


def test_plan_buttons_validate_free_text_board_and_real_measurement_rows():
    source = PLAN_FIX.read_text(encoding="utf-8")

    assert 'frm.doc.board_description' in source
    assert 'frm.doc.board_length_cm' in source
    assert 'frm.doc.board_width_cm' in source
    assert 'frm.doc.pieces || []' in source
    assert 'Number(row.width_cm || 0) > 0' in source
    assert 'Number(row.length_cm || 0) > 0' in source
    assert 'Number(row.qty || 0) > 0' in source
    assert '!frm.doc.board_item' not in source
    assert 'اختر اللوح وأدخل القياسات' not in source


def test_free_text_layer_replaces_obsolete_plan_click_handlers_after_renderer():
    source = PLAN_FIX.read_text(encoding="utf-8")
    hooks = HOOKS.read_text(encoding="utf-8")

    assert 'buttons.off("click")' in source
    assert 'click.dcoTextBoardPlan' in source
    assert 'await frm.save()' in source

    renderer = '"public/js/door_cutting_order_plan_ux.js"'
    free_text = '"public/js/door_cutting_order_text_board_plan_ux.js"'
    assert hooks.index(renderer) < hooks.index(free_text)
