"""Evidence contracts for the opt-in read-only search observer."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json

import pytest

from almdina_erp.almdina_erp.domain.cutting.search_trace import observe_search, traced
from almdina_erp.almdina_erp.application.cutting.search_report import SearchReport
from almdina_erp.almdina_erp.domain.cutting import optimizer as opt
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature


def problem():
    return expand_piece_groups(
        [dict(width_cm=20, length_cm=30, qty=3, allow_rotation=1)]
    )


def test_trace_off_and_on_preserve_untimed_result_and_input():
    pieces = problem()
    before = deepcopy(pieces)
    baseline = opt.auto_fast(pieces, 100, 100, 0.3)
    report = SearchReport()
    with observe_search(report):
        actual = opt.auto_fast(pieces, 100, 100, 0.3)
    assert actual == baseline
    assert pieces == before
    data = report.export()
    assert data["attempts"]
    assert len(data["geometries"]) <= len(data["candidates"])
    assert all(
        s["end_seq"] > s["start_seq"] and s["stop_reason"] for s in data["spans"]
    )
    assert any(s["parent_span_id"] for s in data["spans"])
    assert [e["seq"] for e in data["events"]] == list(range(1, len(data["events"]) + 1))


def test_actual_comparator_keys_and_legacy_fallback_are_recorded():
    from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import (
        final_system_sort_keys,
    )

    first = opt.auto_fast(problem(), 100, 100, 0.3)
    second = deepcopy(first)
    second["industrial_rank"] = (
        *first["industrial_rank"][:3],
        first["industrial_rank"][3] + 1,
        *first["industrial_rank"][4:],
    )
    report = SearchReport()
    with observe_search(report):
        assert opt._candidate_is_better(first, second)
        keys = final_system_sort_keys([first, second])
    decisions = report.export()["decisions"]
    assert decisions[0]["decisive_criterion"] == "largest_eligible_remnant_area_m2"
    assert decisions[-1]["keys"] == json.loads(json.dumps(keys))
    assert decisions[-1]["cutter_center_available"] is False


def test_limits_and_observer_failure_never_silently_claim_complete():
    report = SearchReport(max_events=20, max_geometry_bytes=1)
    with observe_search(report):
        opt.auto_fast(problem(), 100, 100, 0.3)
    data = report.export()
    assert data["coverage_manifest"]["status"] == "TRUNCATED"
    assert data["coverage_manifest"]["dropped_events"] > 0
    assert data["coverage_manifest"]["omitted_geometries"] > 0
    assert any(e["kind"] == "evidence_loss" for e in data["events"])

    # The final gallery is reserved evidence even after the search event quota.
    limited = SearchReport(max_events=1, max_geometry_bytes=1)
    with observe_search(limited):
        plan = opt.auto_fast(problem(), 100, 100, 0.3)
    limited.gallery([], [plan], "published_preview")
    assert limited.export()["final_gallery"][0][
        "geometry_fingerprint"
    ] == geometry_signature(plan)


def test_exception_closes_spans_and_context_isolated_between_threads():
    @traced("probe")
    def probe(fail):
        if fail:
            raise ValueError("private input must not be logged")
        return opt.auto_fast(problem(), 100, 100, 0.3)

    def run(fail):
        report = SearchReport()
        with observe_search(report):
            try:
                probe(fail)
            except ValueError:
                pass
        return report.export()

    with ThreadPoolExecutor(2) as pool:
        bad, good = list(pool.map(run, [True, False]))
    assert bad["run_id"] != good["run_id"]
    assert bad["spans"][0]["stop_reason"] == "exception:ValueError"
    assert "private input" not in json.dumps(bad)
    assert not bad["geometries"] and good["geometries"]


def test_offline_html_uses_same_evidence_and_escapes_untrusted_text():
    from almdina_erp.almdina_erp.presentation.cutting.search_report_html import (
        render_search_report,
    )

    report = SearchReport()
    with observe_search(report):
        plan = opt.auto_fast(problem(), 100, 100, 0.3)
        report.gallery([], [plan], "test_publish")
    report.metadata["preview_id"] = "</script><img src=x onerror=alert(1)>"
    data = report.export()
    html = render_search_report(data)
    assert data["data_fingerprint"] in html
    assert data["report_id"] in html
    assert "</script><img" not in html
    assert 'src="http' not in html and 'href="http' not in html
    assert 'dir="rtl"' in html
    assert data["final_gallery"][0]["geometry_fingerprint"] == geometry_signature(plan)


def test_generator_exception_and_broken_observer_do_not_change_engine():
    @traced("failed_generator")
    def failed():
        yield "first"
        raise RuntimeError("not public")

    report = SearchReport()
    with observe_search(report):
        with pytest.raises(RuntimeError):
            list(failed())
    assert report.export()["spans"][0]["stop_reason"] == "exception:RuntimeError"

    class BrokenObserver:
        def emit(self, *args, **kwargs):
            raise ValueError("observer")

        def failure(self, *args, **kwargs):
            raise ValueError("observer failure")

    baseline = opt.auto_fast(problem(), 100, 100, 0.3)
    with observe_search(BrokenObserver()):
        assert opt.auto_fast(problem(), 100, 100, 0.3) == baseline


def test_input_evidence_excludes_costs_and_board_patterns_are_not_complete_orders():
    from almdina_erp.almdina_erp.application.cutting.optimize_order_plan import (
        BoardGeometry,
        OptimizerOptions,
        OptimizeOrderPlanCommand,
        optimize_order_plan,
    )
    from almdina_erp.almdina_erp.infrastructure.cutting.domain_engine import (
        DomainCuttingEngineAdapter,
    )

    command = OptimizeOrderPlanCommand(
        "test",
        "input",
        BoardGeometry(100, 100, 0, 0.3),
        OptimizerOptions("auto", "CNC Router", 1, 40, 30, 30, 0.09),
        (
            dict(
                width_cm=20, length_cm=30, qty=3, allow_rotation=1, glass_cost_usd=12345
            ),
        ),
    )
    report = SearchReport()
    with observe_search(report):
        outcome = optimize_order_plan(command, engine=DomainCuttingEngineAdapter())
    plan = deepcopy(outcome.snapshot)
    plan["sheets"][0]["pieces"] = plan["sheets"][0]["pieces"][:1]
    key = report.candidate(plan, source="partial_pattern")
    data = report.export()
    assert not data["candidates"][key]["complete"]
    assert data["candidates"][key]["incomplete_reason"] == "partial_inventory"
    assert "glass_cost_usd" not in json.dumps(data)


def test_report_messages_have_official_arabic_translations():
    from almdina_erp.almdina_erp.presentation.cutting.search_report_html import (
        MESSAGES,
        CODE_MESSAGES,
        _arabic_catalog,
    )

    catalog = _arabic_catalog()
    for message in (set(MESSAGES) - set(CODE_MESSAGES)) | set(CODE_MESSAGES.values()):
        assert message in catalog, message
        assert catalog[message] != message, message


def test_elapsed_deadline_is_not_invented_as_the_cause_of_a_return():
    @traced("returns_normally")
    def normal(*, deadline):
        return None

    report = SearchReport()
    with observe_search(report):
        normal(deadline=0)
    data = report.export()
    assert data["spans"][0]["stop_reason"] == "returned"
    assert next(e for e in data["events"] if e["kind"] == "span_end")[
        "budget_expired_at_return"
    ]
