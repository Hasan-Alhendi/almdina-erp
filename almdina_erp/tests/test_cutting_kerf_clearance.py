from almdina_erp.almdina_erp.domain.cutting.evaluation import validate_plan
from almdina_erp.almdina_erp.domain.cutting.primitives import rects_have_clearance


def _pieces():
    return [
        {
            "id": 1,
            "label": "1.1",
            "width_cm": 40,
            "length_cm": 40,
            "allow_rotation": 0,
        },
        {
            "id": 2,
            "label": "1.2",
            "width_cm": 40,
            "length_cm": 40,
            "allow_rotation": 0,
        },
    ]


def _plan(second_x: float):
    pieces = _pieces()
    return {
        "sheets": [
            {
                "sheet_no": 1,
                "pieces": [
                    {**pieces[0], "x": 0, "y": 0, "w": 40, "h": 40, "rotated": False},
                    {**pieces[1], "x": second_x, "y": 0, "w": 40, "h": 40, "rotated": False},
                ],
            }
        ],
        "unplaced": [],
    }


def test_clearance_rule_requires_one_kerf_gap_not_double_kerf():
    first = {"x": 0.0, "y": 0.0, "w": 40.0, "h": 40.0}
    exact_kerf = {"x": 40.3, "y": 0.0, "w": 40.0, "h": 40.0}
    short_gap = {"x": 40.2, "y": 0.0, "w": 40.0, "h": 40.0}

    assert rects_have_clearance(first, exact_kerf, 0.3)
    assert not rects_have_clearance(first, short_gap, 0.3)


def test_validator_rejects_non_overlapping_paths_that_lose_saw_kerf():
    errors = validate_plan(_plan(40.2), _pieces(), 100, 100, kerf_cm=0.3)

    assert not any("overlap" in error.lower() for error in errors)
    assert any("kerf clearance" in error.lower() for error in errors)


def test_validator_accepts_exact_required_saw_kerf():
    errors = validate_plan(_plan(40.3), _pieces(), 100, 100, kerf_cm=0.3)

    assert errors == []
