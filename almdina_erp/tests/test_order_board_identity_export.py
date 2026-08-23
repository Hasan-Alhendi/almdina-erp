from types import SimpleNamespace

from almdina_erp.almdina_erp.services.export_validation_service import (
    _validate_source_identity,
)
from almdina_erp.almdina_erp.services.order_board_identity import (
    order_board_color,
    order_board_material,
    order_board_thickness_mm,
)


def test_order_board_identity_reads_free_text_description():
    order = SimpleNamespace(board_description="MDF أبيض 18 مم")
    assert order_board_material(order) == "MDF أبيض 18 مم"
    assert order_board_color(order) == ""
    assert order_board_thickness_mm(order) == 0.0


def test_validate_source_identity_accepts_free_text_board_without_legacy_fields():
    order = SimpleNamespace(
        board_description="MDF أبيض 18 مم",
        board_item=None,
    )
    plan = SimpleNamespace(board_item=None)
    source = SimpleNamespace(
        sheet_no=1,
        board_item=None,
        board_description="MDF أبيض 18 مم",
        material="",
        color="",
        thickness_mm=0,
        source_type="Full Board",
        remnant=None,
        full_width_mm=1220,
        full_length_mm=2440,
        usable_width_mm=1200,
        usable_length_mm=2400,
    )
    errors: list[str] = []
    _validate_source_identity(source, plan, order, errors)
    assert errors == []


def test_validate_source_identity_flags_board_description_mismatch():
    order = SimpleNamespace(board_description="MDF أبيض 18 مم", board_item=None)
    plan = SimpleNamespace(board_item=None)
    source = SimpleNamespace(
        sheet_no=1,
        board_item=None,
        board_description="MDF أسود 18 مم",
        material="",
        color="",
        thickness_mm=0,
        source_type="Full Board",
        remnant=None,
        full_width_mm=1220,
        full_length_mm=2440,
        usable_width_mm=1200,
        usable_length_mm=2400,
    )
    errors: list[str] = []
    _validate_source_identity(source, plan, order, errors)
    assert any("board description" in message.lower() for message in errors)
