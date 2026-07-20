from types import SimpleNamespace

from almdina_erp.almdina_erp.services.remnant_service import derive_free_rectangles


def test_free_rectangles_are_non_overlapping_after_piece_subtraction():
    source = SimpleNamespace(usable_width_mm=1000, usable_length_mm=1000)
    pieces = [
        SimpleNamespace(x_mm=0, y_mm=0, width_mm=400, height_mm=400, piece_label="1.1"),
        SimpleNamespace(x_mm=400, y_mm=0, width_mm=300, height_mm=400, piece_label="2.1"),
    ]
    free = derive_free_rectangles(source, pieces, kerf_mm=0)

    def intersects(a, b):
        return not (
            a["x"] + a["w"] <= b["x"]
            or b["x"] + b["w"] <= a["x"]
            or a["y"] + a["h"] <= b["y"]
            or b["y"] + b["h"] <= a["y"]
        )

    for index, first in enumerate(free):
        for second in free[index + 1:]:
            assert not intersects(first, second)


def test_free_area_plus_piece_area_equals_source_area_without_kerf():
    source = SimpleNamespace(usable_width_mm=1000, usable_length_mm=1000)
    pieces = [
        SimpleNamespace(x_mm=0, y_mm=0, width_mm=400, height_mm=400, piece_label="1.1"),
        SimpleNamespace(x_mm=400, y_mm=0, width_mm=300, height_mm=400, piece_label="2.1"),
    ]
    free = derive_free_rectangles(source, pieces, kerf_mm=0)
    free_area = sum(row["w"] * row["h"] for row in free)
    piece_area = sum(row.width_mm * row.height_mm for row in pieces)
    assert abs((free_area + piece_area) - 1_000_000) < 0.001


def test_kerf_reduces_reusable_free_area():
    source = SimpleNamespace(usable_width_mm=1000, usable_length_mm=1000)
    pieces = [SimpleNamespace(x_mm=0, y_mm=0, width_mm=500, height_mm=500, piece_label="1.1")]
    no_kerf = derive_free_rectangles(source, pieces, kerf_mm=0)
    with_kerf = derive_free_rectangles(source, pieces, kerf_mm=3)
    area_no_kerf = sum(row["w"] * row["h"] for row in no_kerf)
    area_with_kerf = sum(row["w"] * row["h"] for row in with_kerf)
    assert area_with_kerf < area_no_kerf
