from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.domain.cutting.dxf_topology import (
    DxfTopologyError,
    PartGeometry,
    PlacedPartGeometry,
    validate_material_layout,
)
from almdina_erp.almdina_erp.domain.cutting.extra_overlays import (
    ExtraOverlayCandidate,
    ExtraOverlayError,
    ExtraOverlayHost,
    assign_extra_overlays,
    overlay_path_contained_in_polygon,
)


def _rect(x1: float, y1: float, x2: float, y2: float):
    return ((x1, y1), (x2, y1), (x2, y2), (x1, y2))


def test_open_liner_path_and_groove_line_are_contained_in_extra():
    extra = _rect(0, 0, 400, 600)
    liner = ((40, 40), (40, 540), (55, 540), (55, 40), (70, 40), (70, 540), (85, 540), (85, 40))
    groove = ((360, 40), (360, 560))

    assert overlay_path_contained_in_polygon(extra, liner, tolerance=0.25)
    assert overlay_path_contained_in_polygon(extra, groove, tolerance=0.25)


def test_assign_extra_overlays_accepts_open_marks_inside_selected_extra():
    assigned = assign_extra_overlays(
        [
            ExtraOverlayCandidate(
                key=1,
                kind="liner",
                layer="Liner",
                path=((40, 40), (40, 160), (55, 160), (55, 40)),
            ),
            ExtraOverlayCandidate(
                key=2,
                kind="back_groove",
                layer="Rear Groove",
                path=((360, 40), (360, 560)),
            ),
            ExtraOverlayCandidate(
                key=3,
                kind="recessed_handle_cutout",
                layer="Handle Recess",
                path=((80, 200), (180, 200), (180, 280), (80, 280), (80, 210)),
            ),
        ],
        [
            ExtraOverlayHost(
                key=1,
                piece_type="Extra",
                polygon=_rect(0, 0, 400, 600),
                selected_codes=("liner", "back_groove", "recessed_handle_cutout"),
            )
        ],
        tolerance=0.25,
    )

    assert [item.kind for item in assigned] == [
        "liner",
        "back_groove",
        "recessed_handle_cutout",
    ]
    assert assigned[1].path == ((360, 40), (360, 560))
    assert assigned[1].closed is False


def test_assign_extra_overlays_rejects_overlay_on_regular():
    with pytest.raises(ExtraOverlayError) as exc_info:
        assign_extra_overlays(
            [
                ExtraOverlayCandidate(
                    key=1,
                    kind="liner",
                    layer="Liner",
                    path=((40, 40), (180, 160)),
                )
            ],
            [
                ExtraOverlayHost(
                    key="1.1",
                    piece_type="Regular",
                    polygon=_rect(0, 0, 400, 600),
                    selected_codes=(),
                )
            ],
            tolerance=0.25,
        )

    assert exc_info.value.code == "extra_overlay_on_non_extra"
    assert exc_info.value.layer == "Liner"


def test_assign_extra_overlays_rejects_floating_and_missing_addon():
    extra = ExtraOverlayHost(
        key=1,
        piece_type="Extra",
        polygon=_rect(0, 0, 400, 600),
        selected_codes=("back_groove",),
    )
    with pytest.raises(ExtraOverlayError) as floating:
        assign_extra_overlays(
            [
                ExtraOverlayCandidate(
                    key=1,
                    kind="liner",
                    layer="Liner",
                    path=((500, 500), (600, 600)),
                )
            ],
            [extra],
            tolerance=0.25,
        )
    assert floating.value.code == "extra_overlay_floating"

    with pytest.raises(ExtraOverlayError) as missing:
        assign_extra_overlays(
            [
                ExtraOverlayCandidate(
                    key=2,
                    kind="liner",
                    layer="Liner",
                    path=((40, 40), (180, 160)),
                )
            ],
            [extra],
            tolerance=0.25,
        )
    assert missing.value.code == "extra_overlay_addon_not_selected"


def test_assign_extra_overlays_rejects_span_across_two_extras():
    with pytest.raises(ExtraOverlayError) as exc_info:
        assign_extra_overlays(
            [
                ExtraOverlayCandidate(
                    key=1,
                    kind="liner",
                    layer="Liner",
                    path=((80, 40), (220, 40)),
                )
            ],
            [
                ExtraOverlayHost(
                    key=1,
                    piece_type="Extra",
                    polygon=_rect(0, 0, 150, 200),
                    selected_codes=("liner",),
                ),
                ExtraOverlayHost(
                    key=2,
                    piece_type="Extra",
                    polygon=_rect(160, 0, 310, 200),
                    selected_codes=("liner",),
                ),
            ],
            tolerance=0.25,
        )

    assert exc_info.value.code == "extra_overlay_spans_hosts"


def test_two_overlapping_extra_cut_paths_still_fail_material_layout():
    with pytest.raises(DxfTopologyError) as exc_info:
        validate_material_layout(
            [
                PlacedPartGeometry(
                    key="1.1",
                    geometry=PartGeometry(outer=_rect(0, 0, 400, 600)),
                ),
                PlacedPartGeometry(
                    key="2.1",
                    geometry=PartGeometry(outer=_rect(200, 0, 600, 600)),
                ),
            ],
            required_clearance=5.0,
            geometry_tolerance=0.25,
        )

    assert exc_info.value.code == "MATERIAL_FOOTPRINT_OVERLAP"
