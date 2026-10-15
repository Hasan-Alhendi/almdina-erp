"""Shared machining overlay: one toolpath for liner, back groove, and handle."""

from almdina_erp.almdina_erp.domain.cutting.liner_geometry import (
    LinerPiece,
    liner_toolpath_mm,
)
from almdina_erp.almdina_erp.domain.cutting.machining_overlay import (
    MACHINING_ADDONS,
    generate_toolpath,
    machining_metadata,
    machining_values,
)


def test_three_addons_share_one_zigzag_and_keep_separate_fields():
    piece = LinerPiece("Regular", 40, 60)
    paths = [
        generate_toolpath(
            kind=addon.kind,
            piece=piece,
            reference_side="edge_width_top",
            offset_cm=2,
            width_cm=1.8,
            start_cm=0,
            length_cm=0,
            cutter_diameter_mm=6,
        )
        for addon in MACHINING_ADDONS
    ]
    assert paths[0] == paths[1] == paths[2]
    assert paths[0] == liner_toolpath_mm(
        piece, "edge_width_top", 2, 1.8, 6, 0, 0
    )
    assert {addon.layer for addon in MACHINING_ADDONS} == {
        "Liner",
        "Rear Groove",
        "Handle Recess",
    }
    stored = machining_metadata(
        {
            "extra_liner": 1,
            "liner_reference_side": "edge_width_top",
            "liner_offset_cm": 2,
            "liner_width_cm": 1.5,
            "extra_back_groove": 1,
            "back_groove_reference_side": "edge_long_right",
            "back_groove_offset_cm": 1,
            "back_groove_width_cm": 0.8,
            "extra_recessed_handle_cutout": 0,
        }
    )
    assert stored["liner_reference_side"] == "edge_width_top"
    assert stored["back_groove_reference_side"] == "edge_long_right"
    assert stored["recessed_handle_reference_side"] == ""
    assert stored["extra_recessed_handle_cutout"] == 0
    values = machining_values(stored)
    assert values["liner"]["side"] != values["back_groove"]["side"]
    assert values["recessed_handle_cutout"]["enabled"] is False
