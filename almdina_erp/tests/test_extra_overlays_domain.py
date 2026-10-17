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


def test_open_liner_path_and_groove_line_are_contained_in_host():
    host = _rect(0, 0, 400, 600)
    liner = ((40, 40), (40, 540), (55, 540), (55, 40), (70, 40), (70, 540), (85, 540), (85, 40))
    groove = ((360, 40), (360, 560))

    assert overlay_path_contained_in_polygon(host, liner, tolerance=0.25)
    assert overlay_path_contained_in_polygon(host, groove, tolerance=0.25)


@pytest.mark.parametrize("piece_type", ["Regular", "Clipped Corner", "L-Shaped Corner", "Special"])
def test_assign_extra_overlays_accepts_open_marks_for_all_piece_types(piece_type):
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
                piece_type=piece_type,
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


def test_assign_extra_overlays_rejects_overlay_without_selected_addon():
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

    assert exc_info.value.code == "extra_overlay_addon_not_selected"
    assert exc_info.value.layer == "Liner"


def test_assign_extra_overlays_rejects_floating_and_missing_addon():
    host = ExtraOverlayHost(
        key=1,
        piece_type="Special",
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
            [host],
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
            [host],
            tolerance=0.25,
        )
    assert missing.value.code == "extra_overlay_addon_not_selected"
    assert missing.value.kind == "liner"


def test_assign_extra_overlays_rejects_selected_addon_without_drawn_mark():
    host = ExtraOverlayHost(
        key=1,
        piece_type="Clipped Corner",
        polygon=_rect(0, 0, 400, 600),
        selected_codes=("liner", "back_groove"),
        label="1.1",
    )
    with pytest.raises(ExtraOverlayError) as missing:
        assign_extra_overlays(
            [
                ExtraOverlayCandidate(
                    key=1,
                    kind="liner",
                    layer="Liner",
                    path=((40, 40), (180, 160)),
                )
            ],
            [host],
            tolerance=0.25,
        )
    assert missing.value.code == "extra_overlay_addon_missing"
    assert missing.value.kind == "back_groove"
    assert missing.value.layer == "Rear Groove"
    assert missing.value.label == "1.1"


def test_assign_extra_overlays_rejects_duplicate_mark_for_one_selected_addon():
    host = ExtraOverlayHost(
        key=1,
        piece_type="L-Shaped Corner",
        polygon=_rect(0, 0, 400, 600),
        selected_codes=("liner",),
        label="2.1",
    )
    with pytest.raises(ExtraOverlayError) as duplicate:
        assign_extra_overlays(
            [
                ExtraOverlayCandidate(
                    key=1,
                    kind="liner",
                    layer="Liner",
                    path=((40, 40), (80, 80)),
                ),
                ExtraOverlayCandidate(
                    key=2,
                    kind="liner",
                    layer="Liner",
                    path=((120, 40), (180, 80)),
                ),
            ],
            [host],
            tolerance=0.25,
        )
    assert duplicate.value.code == "extra_overlay_addon_duplicate"
    assert duplicate.value.kind == "liner"


def test_piece_with_only_commercial_addons_does_not_require_dxf_marks():
    assigned = assign_extra_overlays(
        [],
        [
            ExtraOverlayHost(
                key=1,
                piece_type="Regular",
                polygon=_rect(0, 0, 400, 600),
                selected_codes=("double",),
            )
        ],
        tolerance=0.25,
    )
    assert assigned == ()


def test_assign_extra_overlays_rejects_span_across_two_hosts():
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
                    piece_type="Regular",
                    polygon=_rect(0, 0, 150, 200),
                    selected_codes=("liner",),
                ),
                ExtraOverlayHost(
                    key=2,
                    piece_type="Special",
                    polygon=_rect(160, 0, 310, 200),
                    selected_codes=("liner",),
                ),
            ],
            tolerance=0.25,
        )

    assert exc_info.value.code == "extra_overlay_spans_hosts"


def _kerf_board_hosts():
    """Three doors on one sheet. The gap between them is the 5 mm cutter kerf."""

    kerf = 5.0
    regular = _rect(0, 0, 400, 500)
    clipped = (
        (400 + kerf, 0),
        (900 + kerf, 0),
        (900 + kerf, 300),
        (700 + kerf, 500),
        (400 + kerf, 500),
    )
    shaped = (
        (900 + kerf + kerf, 0),
        (1400 + kerf + kerf, 0),
        (1400 + kerf + kerf, 180),
        (1150 + kerf + kerf, 180),
        (1150 + kerf + kerf, 500),
        (900 + kerf + kerf, 500),
    )
    return kerf, [
        ExtraOverlayHost(1, "Regular", regular, ("liner",), "1"),
        ExtraOverlayHost(2, "Clipped Corner", clipped, ("liner",), "2"),
        ExtraOverlayHost(3, "L-Shaped Corner", shaped, ("liner",), "3"),
    ]


def _edge_liner(x1, y1, x2, y2, radius):
    """One open zigzag whose ends extend by the cutter radius past the door."""

    return (
        (x1 - radius, y1),
        (x2 + radius, y1),
        (x2 + radius, y2),
        (x1 - radius, y2),
    )


def test_liner_centers_in_the_kerf_do_not_span_neighboring_doors():
    radius = 2.5
    _kerf, hosts = _kerf_board_hosts()
    # Top-edge liners. Their centers run inside each door and the ends extend
    # by one radius into the kerf of the door on the right.
    paths = [
        _edge_liner(0, 30, 400, 45, radius),
        _edge_liner(405, 30, 905, 45, radius),
        _edge_liner(910, 30, 1410, 45, radius),
    ]
    overlays = [
        ExtraOverlayCandidate(index + 1, "liner", "Liner", path)
        for index, path in enumerate(paths)
    ]

    with pytest.raises(ExtraOverlayError) as legacy:
        assign_extra_overlays(overlays, hosts, tolerance=0.25, host_margin=3.0)
    assert legacy.value.code == "extra_overlay_spans_hosts"

    assigned = assign_extra_overlays(
        overlays,
        hosts,
        tolerance=0.25,
        host_margin=3.0,
        cutter_radius_mm=radius,
    )
    assert [item.host_key for item in assigned] == [1, 2, 3]


def test_liner_disk_that_enters_the_next_door_still_spans():
    radius = 2.5
    hosts = [
        ExtraOverlayHost(1, "Regular", _rect(0, 0, 400, 500), ("liner",), "1"),
        ExtraOverlayHost(2, "Clipped Corner", _rect(405, 0, 800, 500), ("liner",), "2"),
    ]
    # The extended center is 1 mm from the next door, so a 5 mm bit cuts into it.
    path = ((20, 30), (404, 30), (404, 45), (20, 45))
    with pytest.raises(ExtraOverlayError) as exc_info:
        assign_extra_overlays(
            [ExtraOverlayCandidate(1, "liner", "Liner", path)],
            hosts,
            tolerance=0.25,
            host_margin=3.0,
            cutter_radius_mm=radius,
        )
    assert exc_info.value.code == "extra_overlay_spans_hosts"


def test_liner_path_that_crosses_two_doors_still_spans_with_cutter_radius():
    with pytest.raises(ExtraOverlayError) as exc_info:
        assign_extra_overlays(
            [ExtraOverlayCandidate(1, "liner", "Liner", ((80, 40), (220, 40)))],
            [
                ExtraOverlayHost(1, "Regular", _rect(0, 0, 150, 200), ("liner",)),
                ExtraOverlayHost(2, "L-Shaped Corner", _rect(160, 0, 310, 200), ("liner",)),
            ],
            tolerance=0.25,
            host_margin=3.0,
            cutter_radius_mm=2.5,
        )
    assert exc_info.value.code == "extra_overlay_spans_hosts"


def test_non_liner_mark_still_uses_the_host_margin_span_check():
    with pytest.raises(ExtraOverlayError) as exc_info:
        assign_extra_overlays(
            [ExtraOverlayCandidate(1, "back_groove", "Rear Groove", ((80, 40), (220, 40)))],
            [
                ExtraOverlayHost(1, "Regular", _rect(0, 0, 150, 200), ("back_groove",)),
                ExtraOverlayHost(2, "Regular", _rect(160, 0, 310, 200), ("back_groove",)),
            ],
            tolerance=0.25,
            host_margin=3.0,
            cutter_radius_mm=2.5,
        )
    assert exc_info.value.code == "extra_overlay_spans_hosts"


def test_two_overlapping_cut_paths_still_fail_material_layout():
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
