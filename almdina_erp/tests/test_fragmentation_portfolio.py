"""Free-space quality is an alternative policy, with independent safety gates."""

from copy import deepcopy
import json

import pytest

from almdina_erp.almdina_erp.domain.cutting.fragmentation import (
    _envelope_regions,
    analysis_scales_cm,
    envelope_profile,
    fragmentation_key,
    has_fragmentation_benefit,
    FragmentationNominee,
    fragmentation_export_rejection,
)
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import (
    geometry_signature,
    retain_system_gallery,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import (
    expand_piece_groups,
    make_placed_piece,
)
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.infrastructure.cutting.fragmentation_geometry import (
    measure_fragmentation,
)


def layouts(kerf=0):
    sources = expand_piece_groups(
        [
            dict(
                width_cm=2,
                length_cm=5,
                qty=2,
                allow_rotation=0,
                piece_instance_id="two",
            )
        ]
    )

    def plan(xs):
        sheet = dict(
            sheet_no=1,
            w=20,
            h=10,
            pieces=[
                make_placed_piece(p, x, 0, 2, 5, False) for p, x in zip(sources, xs)
            ],
        )
        p = enrich_plan_metrics(dict(sheets=[sheet], unplaced=[]), "MaxRects Best Area")
        p.update(
            kerf_cm=kerf, machine_type="Auto", validation=dict(is_valid=True, errors=[])
        )
        return p

    return sources, plan([0, 2 + kerf]), plan([5, 13])


def test_disjoint_strip_union_is_exact_and_does_not_connect_corner_contacts():
    assert _envelope_regions(10, 10, ((4, 0, 2, 10),), 0, 0) == (40, 40)
    assert _envelope_regions(10, 10, ((0, 0, 5, 5), (5, 5, 5, 5)), 0, 0) == (25, 25)
    # Overlapping envelope obstacles are unioned, never summed.
    assert sum(_envelope_regions(10, 10, ((0, 0, 6, 5), (4, 0, 6, 5)), 0, 0)) == 50


@pytest.mark.parametrize("kerf", [0, 0.3, 0.5])
def test_exact_profile_matches_independent_rectangle_areas_and_keeps_inputs(kerf):
    _, compact, scattered = layouts(kerf)
    before = deepcopy((compact, scattered))
    exact = measure_fragmentation(compact, kerf)
    assert exact["measured_sheets"] == 1
    assert exact["scope"] == []
    assert exact["levels"][0]["free_area_cm2"] > 0
    proxy = envelope_profile(compact, kerf)
    # Rectangle sweeps and the exact miter subtraction agree before opening.
    assert exact["levels"][0]["free_area_cm2"] == pytest.approx(
        proxy["levels"][0]["free_area_cm2"], abs=4 * kerf * kerf
    )
    assert (compact, scattered) == before


def test_multiscale_widths_follow_piece_sizes_and_tool_not_a_fixed_mm_threshold():
    _, plan, _ = layouts(0.3)
    scales = analysis_scales_cm(plan, 0.3)
    assert 0 in scales and 0.6 in scales and len(scales) > 2
    scaled = deepcopy(plan)
    for sheet in scaled["sheets"]:
        sheet["w"] *= 3
        sheet["h"] *= 3
        for p in sheet["pieces"]:
            for key in ("x", "y", "w", "h", "original_w", "original_h"):
                p[key] *= 3
    assert analysis_scales_cm(scaled, 0.9) == pytest.approx([v * 3 for v in scales])


def test_nominee_never_prefers_more_boards_even_with_better_empty_space():
    _, compact, scattered = layouts(0.3)
    extra = deepcopy(compact)
    extra["sheets"].append(dict(w=20, h=10, pieces=[]))
    pool = FragmentationNominee(0.3)
    pool.offer(extra)
    pool.offer(scattered)
    assert len(pool.plan["sheets"]) == 1
    assert len(pool.profile["levels"]) == len(analysis_scales_cm(scattered, 0.3))


@pytest.mark.parametrize("resource", ["sheet", "piece"])
def test_offcut_never_enters_fragmentation_nomination(resource):
    _, plan, _ = layouts()
    target = (
        plan["sheets"][0] if resource == "sheet" else plan["sheets"][0]["pieces"][0]
    )
    target["resource_kind"] = "OFFCUT"
    assert envelope_profile(plan, 0) is None
    assert measure_fragmentation(plan, 0) is None


def test_unknown_special_excludes_its_whole_sheet_and_prevents_unlike_scope_comparison():
    _, plan, _ = layouts(0.3)
    special = deepcopy(plan["sheets"][0])
    special["pieces"][0]["piece_type"] = "Special"
    plan["sheets"].append(special)
    a = measure_fragmentation(plan, 0.3)
    assert a["measured_sheets"] == 1 and a["total_sheets"] == 2 and len(a["scope"]) == 1
    changed = deepcopy(plan)
    changed["sheets"][1]["pieces"][0]["x"] += 0.5
    b = measure_fragmentation(changed, 0.3)
    assert a["scope"] != b["scope"]
    assert not has_fragmentation_benefit(a, b)


def test_exact_clipped_outline_and_glass_hole_are_used():
    _, plan, _ = layouts()
    p = plan["sheets"][0]["pieces"][0]
    p.update(
        piece_type="Clipped Corner",
        clipped_corner_position="Bottom Right",
        clipped_corner_width_cm=1,
        clipped_corner_length_cm=1,
    )
    exact = measure_fragmentation(plan, 0)
    assert exact["board_profiles"][0]["material_area_cm2"] == pytest.approx(19.5)
    p.update(piece_type="Glass", glass_margin_mm=2)
    exact = measure_fragmentation(plan, 0)
    assert exact and exact["board_profiles"][0]["material_area_cm2"] < 20


def profile(secondary):
    return dict(
        tier="material_opening",
        scope=(),
        kerf_cm=0.5,
        levels=[
            dict(
                scale_cm=s,
                secondary_area_cm2=secondary,
                free_area_cm2=100,
                primary_area_cm2=100 - secondary,
                regions=2,
            )
            for s in (0, 1, 3)
        ],
    )


def test_gallery_protects_default_and_reserves_low_fragmentation_verified_alternative():
    _, winner, alternate = layouts()
    winner["industrial_rank"] = [0, 1, 0, -1, 10, 100, 0, 0]
    winner["fragmentation_metrics"] = profile(40)
    native = []
    for i in range(5):
        p = deepcopy(winner)
        p["sheets"][0]["pieces"][0]["x"] += i * 0.01
        p["industrial_rank"] = [0, 1, 0, -1, 10 + i, 100, 0, 0]
        native.append(p)
    alternate.update(
        industrial_rank=[0, 1, 0, -0.2, 20, 200, 0, 0],
        gallery_role="fragmentation_alternative",
        fragmentation_metrics=profile(5),
    )
    gallery = retain_system_gallery(native + [alternate])
    assert gallery[0] is native[0] and len(gallery) == 5 and alternate in gallery
    alternate["validation"]["is_valid"] = False
    assert alternate not in retain_system_gallery(native + [alternate])


def test_preview_continuation_uses_same_policy_after_json_reload():
    from almdina_erp.almdina_erp.application.cutting.plan_preview_session import (
        merge_preview_candidates,
    )

    _, winner, alternate = layouts()
    winner.update(
        industrial_rank=[0, 1, 0, -1, 10, 100, 0, 0], fragmentation_metrics=profile(40)
    )
    alternate.update(
        industrial_rank=[0, 1, 0, -0.2, 20, 200, 0, 0],
        gallery_role="fragmentation_alternative",
        fragmentation_metrics=profile(5),
    )

    def record(p):
        key = geometry_signature(p)
        return dict(candidate_id=key, geometry_fingerprint=key, snapshot=p)

    candidates = {r["candidate_id"]: r for r in map(record, [winner, alternate])}
    reloaded = json.loads(json.dumps(candidates))
    merged = merge_preview_candidates({}, reloaded)
    assert list(merged) == list(reloaded)
    assert len(merged) == 2


@pytest.mark.parametrize(
    "failure",
    [
        "missing_copy",
        "rotation",
        "duplicate_identity",
        "stable_identity",
        "measurement",
    ],
)
def test_application_rejects_invalid_side_proposals_and_measurement_failure_keeps_default(
    failure,
):
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry,
        OptimizerOptions,
        OptimizeOrderPlanCommand,
        optimize_order_plan,
    )
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import (
        DomainCuttingEngineAdapter,
    )

    sources, compact, scattered = layouts(0.5)
    proposal = deepcopy(scattered)
    if failure == "missing_copy":
        proposal["sheets"][0]["pieces"].pop()
    elif failure == "rotation":
        proposal["sheets"][0]["pieces"][0]["rotated"] = True
    elif failure == "duplicate_identity":
        first, second = proposal["sheets"][0]["pieces"]
        second["id"] = first["id"]
        second["piece_instance_id"] = first["piece_instance_id"]
    elif failure == "stable_identity":
        first, second = proposal["sheets"][0]["pieces"]
        second["piece_instance_id"] = first["piece_instance_id"]

    class Engine(DomainCuttingEngineAdapter):
        def optimize(self, *args, **kwargs):
            return dict(
                deepcopy(compact),
                smart_candidates=[deepcopy(compact)],
                smart_fragmentation_candidates=[deepcopy(proposal)],
            )

        def measure_fragmentation(self, plan, kerf):
            if failure == "measurement":
                raise ValueError("unavailable geometry backend")
            return super().measure_fragmentation(plan, kerf)

    rows = (
        dict(width_cm=2, length_cm=5, qty=2, allow_rotation=0, piece_instance_id="two"),
    )
    command = OptimizeOrderPlanCommand(
        "test",
        "test",
        BoardGeometry(20, 10, 0, 0.5),
        OptimizerOptions(
            "smart", "Auto", 0.1, 40, 30, 30, 0.09, alignment_search_budget_sec=0
        ),
        rows,
    )
    result = optimize_order_plan(command, engine=Engine())
    assert result.snapshot["validation"]["is_valid"]
    assert len(result.candidate_snapshots) == 1
    assert {
        p["piece_instance_id"] for s in result.snapshot["sheets"] for p in s["pieces"]
    } == {p["piece_instance_id"] for p in sources}
    assert not result.snapshot.get("gallery_role")


def test_regroup_uses_regular_sheets_in_a_mixed_order_and_keeps_protected_sheet():
    import time
    from almdina_erp.almdina_erp.domain.cutting.plan_search import (
        _regrouped_board_candidates,
    )

    sources, compact, _ = layouts(0.5)
    protected = deepcopy(compact["sheets"][0])
    protected["sheet_no"] = 3
    for p in protected["pieces"]:
        p["piece_type"] = "Special"
        p["id"] += 10
        p["piece_instance_id"] += ":protected"
        p["special_shape_geometry_json"] = json.dumps(
            dict(
                version=1,
                kind="polygon",
                units="cm",
                exact=True,
                blank_width_cm=2,
                blank_length_cm=5,
                points=[[0, 0], [1, 0], [2, 1], [2, 5], [0, 5]],
            )
        )
    plan = deepcopy(compact)
    plan["sheets"].append(deepcopy(plan["sheets"][0]))
    plan["sheets"][1]["sheet_no"] = 2
    for p in plan["sheets"][1]["pieces"]:
        p["id"] += 2
        p["piece_instance_id"] += ":other"
    for p in plan["sheets"][1]["pieces"] + protected["pieces"]:
        sources.append(
            dict(p, width_cm=p["w"], length_cm=p["h"], group_qty=1, allow_rotation=0)
        )
    plan["sheets"].append(protected)
    before = deepcopy(plan)
    candidates = list(
        _regrouped_board_candidates(plan, sources, 20, 10, 0.5, time.monotonic() + 2)
    )
    assert candidates
    for candidate in candidates:
        kept = next(
            s
            for s in candidate["sheets"]
            if any(p["piece_type"] == "Special" for p in s["pieces"])
        )
        assert kept["pieces"] == protected["pieces"]
        assert kept["w"] == protected["w"] and kept["h"] == protected["h"]
        assert fragmentation_export_rejection(candidate) is None
    assert plan == before


def test_returned_geometry_profiles_cannot_mutate_the_shared_cache():
    _, plan, _ = layouts(0.3)
    first = measure_fragmentation(plan, 0.3)
    expected = first["board_profiles"][0]["free_area_cm2"]
    first["board_profiles"][0]["free_area_cm2"] = -1
    first["board_profiles"][0]["levels"][0]["regions"] = -1
    second = measure_fragmentation(plan, 0.3)
    assert second["board_profiles"][0]["free_area_cm2"] == expected
    assert second["board_profiles"][0]["levels"][0]["regions"] > 0


def test_empty_plan_and_zero_gallery_limit_are_safe():
    plan = dict(sheets=[dict(w=10, h=10, pieces=[])], unplaced=[])
    assert envelope_profile(plan, 0) is None
    _, valid, _ = layouts()
    assert retain_system_gallery([valid], limit=0) == []


def test_missing_or_rectangular_special_geometry_cannot_certify_a_new_alternative():
    _, plan, _ = layouts()
    piece = plan["sheets"][0]["pieces"][0]
    piece["piece_type"] = "Special"
    assert fragmentation_export_rejection(plan) == "unproven_special_outline"
    piece["special_shape_geometry_json"] = json.dumps(
        dict(
            version=1,
            kind="polygon",
            units="cm",
            exact=True,
            blank_width_cm=2,
            blank_length_cm=5,
            points=[[0, 0], [2, 0], [2, 5], [0, 5]],
        )
    )
    assert fragmentation_export_rejection(plan) == "rectangular_special_outline"
    piece["special_shape_geometry_json"] = json.dumps(
        dict(
            version=1,
            kind="polygon",
            units="cm",
            exact=True,
            blank_width_cm=2,
            blank_length_cm=5,
            points=[[0, 0], [1, 0], [2, 1], [2, 5], [0, 5]],
        )
    )
    assert fragmentation_export_rejection(plan) is None
