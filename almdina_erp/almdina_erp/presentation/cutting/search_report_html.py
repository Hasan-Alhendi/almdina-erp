"""Offline report presentation, driven exclusively by recorded JSON evidence."""

from __future__ import annotations

import csv
from functools import lru_cache
from html import escape
import json
from pathlib import Path


@lru_cache(maxsize=1)
def _arabic_catalog():
    with (Path(__file__).resolve().parents[3] / "translations" / "ar.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        return {row[0]: row[1] for row in csv.reader(stream) if len(row) >= 2}


MESSAGES = (
    "Cutting search report",
    "Management summary",
    "Actual search journey",
    "Recorded candidates",
    "Why these five plans?",
    "Technical evidence",
    "Read-only diagnostic evidence. This report cannot be saved or approved as a cutting plan.",
    "Evidence status",
    "Recorded attempts",
    "Completed arrangements",
    "Incomplete arrangements",
    "Rejected candidates",
    "Duplicate candidates",
    "Selected plans",
    "Boards in the first plan",
    "Search candidates",
    "All statuses",
    "Complete",
    "Incomplete",
    "Rejected",
    "Duplicate",
    "Selected",
    "Candidate",
    "Source",
    "Boards",
    "Status",
    "Reason",
    "Compare two plans",
    "Select up to two candidates to compare their recorded geometry.",
    "Inputs",
    "Outputs",
    "What happened",
    "Stop reason",
    "Duration (seconds)",
    "No recorded geometry is available.",
    "An unproven contour is omitted. A bounding rectangle is not a substitute.",
    "Before",
    "After",
    "Removed",
    "Comparison rule",
    "First decisive criterion",
    "Cutter center available",
    "Yes",
    "No",
    "Equal comparison keys",
    "No competing candidate",
    "Show more",
    "No recorded entries.",
    "The largest eligible remnant is a ranking measure; it does not prove the best industrial reuse.",
    "unplaced_count",
    "board_count",
    "panel_saw_penalty",
    "largest_eligible_remnant_area_m2",
    "estimated_cut_count",
    "estimated_cut_length_cm",
    "rotation_count",
    "complexity",
    "cutter_center_length_mm",
    "longest_internal_center_mm",
    "cutter_center_segment_count",
    "returned",
    "deadline",
    "generator_exhausted",
    "consumer_stopped",
    "no_result",
    "validation_failed",
    "duplicate_geometry",
    "duplicate_raw_geometry",
    "duplicate_preview_geometry",
    "duplicate_geometry_not_better",
    "batch_shortlist_limit",
    "batch_leader_or_diverse_second",
    "completion_limit",
    "no_final_improvement",
    "validation_or_permission",
    "snapshot_manufacturing_validation",
    "preview_export_validation",
    "repair_failed",
    "remnant_regression",
    "changed_board_count",
    "changed_pinned_geometry",
    "organization_network_regression",
    "accepted_final_improvement",
    "pre_refinement_validation",
    "Coordinate probes and uninstrumented inner solver states are not captured.",
    "Some recorded pieces have unproven contours; no bounding-box substitute is drawn.",
    "Previous round evidence was not recorded or has expired.",
    "Search round",
    "Recorded comparison events",
    "These are actual sort keys; lower values sort first.",
    "The deployed Git revision could not be resolved.",
    "Previous round",
    "Evidence limitations",
    "Dropped events",
    "Omitted geometries",
)

CODE_MESSAGES = {
    "unplaced_count": "Unplaced pieces",
    "board_count": "Board count",
    "panel_saw_penalty": "Panel saw constraint penalty",
    "largest_eligible_remnant_area_m2": "Largest eligible remnant area",
    "estimated_cut_count": "Estimated cut count",
    "estimated_cut_length_cm": "Estimated cut length",
    "rotation_count": "Rotation count",
    "complexity": "Method complexity",
    "cutter_center_length_mm": "Actual cutter center length",
    "longest_internal_center_mm": "Longest continuous internal cutter center",
    "cutter_center_segment_count": "Disconnected cutter center segments",
    "returned": "The observed call returned.",
    "deadline": "The time budget expired.",
    "generator_exhausted": "The generator exhausted its available proposals.",
    "consumer_stopped": "The caller stopped consuming proposals.",
    "no_result": "The attempt produced no arrangement.",
    "validation_failed": "Manufacturing validation failed.",
    "duplicate_geometry": "This geometry was already observed.",
    "duplicate_raw_geometry": "This raw geometry was already observed.",
    "duplicate_preview_geometry": "This projected geometry is already in the preview.",
    "duplicate_geometry_not_better": "The same geometry has no better industrial rank.",
    "batch_shortlist_limit": "This seed was outside the batch shortlist.",
    "batch_leader_or_diverse_second": "The batch leader or diverse second seed was promoted.",
    "completion_limit": "The completion limit was reached.",
    "no_final_improvement": "The final comparison did not improve the incumbent.",
    "validation_or_permission": "Placement validation or orientation permission failed.",
    "snapshot_manufacturing_validation": "The physical snapshot failed manufacturing validation.",
    "preview_export_validation": "The preview failed export validation.",
    "repair_failed": "The repair could not complete an arrangement.",
    "remnant_regression": "The candidate worsened the protected remnant criteria.",
    "changed_board_count": "The board count violates this operator policy.",
    "changed_pinned_geometry": "The proposal changed protected geometry.",
    "organization_network_regression": "The cutter network organization regressed.",
    "accepted_final_improvement": "The proposal passed the final improvement gates.",
    "pre_refinement_validation": "Validation failed before refinement.",
    "observed": "Observed",
    "rejected": "Rejected",
    "duplicate": "Duplicate",
    "selected": "Selected",
    "not_selected": "Not selected",
    "not_promoted": "Not promoted",
    "promoted": "Promoted",
    "reserved": "Reserved for nesting coverage",
    "offered": "Offered to the portfolio",
    "improved": "Improved",
    "glass_assignment": "Glass assignment attempt",
    "glass_prepare": "Prepare a glass nesting proposal",
    "batch_seed_ranking": "Rank seeds before promotion",
    "system_portfolio_priority_limit_16": "Keep sixteen system alternatives by the existing priority policy",
    "measured_pareto_tradeoff": "Keep a measured remnant and cutter path trade-off",
    "pareto_dominated": "An existing proposal dominates these measured criteria",
    "unplaced_pieces": "Some input pieces remain unplaced",
    "partial_inventory": "This arrangement does not contain the full input inventory",
    "portfolio_capacity_or_coverage_priority": "The portfolio capacity and nesting coverage policy excluded this candidate",
    "pattern_guard": "The board pattern violates its size, capacity or resource guards",
    "unsupported_pattern_source_or_nested_geometry": "This board pattern contains unsupported source or nested geometry",
    "unproven_contour": "The actual contour could not be proven",
    "unproven_cutter_geometry": "The actual cutter network could not be proven",
    "dominated_pattern": "An existing board pattern has better measured path and remnant criteria",
    "pattern_replacement": "A better measured board pattern replaced the previous pattern",
    "pattern_limit": "The board pattern capacity was reached",
    "pattern_retained": "The board pattern entered the private pattern pool",
    "completed": "The stage completed its work",
    "neighborhoods_exhausted": "The available neighborhoods were exhausted",
    "accepted": "Accepted",
    "validate_plan": "Manufacturing validation",
    "placement_permission_errors": "Placement permission validation",
    "portfolio_offer": "Candidate offered to the portfolio",
    "raw_packer_result": "Raw packing arrangement",
    "intermediate_not_manufacturing_plan": "Intermediate scaffold, not a manufacturing plan",
    "expanded_placement_quality_lte_direct": "Expanded kerf arrangement has no worse placement key",
    "expansion_failed_or_worse_placement_quality": "Kerf expansion failed or had a worse placement key",
    "partial_board_pattern_not_a_complete_order_plan": "A board pattern is not a complete order plan",
    "duplicate_packing_order": "The same packing input order was already tried",
    "measured_cutter_center": "Measured cutter center criteria were available",
    "no_openings": "No usable openings were found",
    "no_budget": "No time budget was available",
    "portfolio_rank_before_coverage_reservation": "Industrial ranking before nesting coverage reservation",
    "unproven_machine_or_rank_or_kerf": "Machine, industrial rank or kerf evidence is unavailable",
    "first_candidate": "The first candidate has no incumbent competitor",
    "smart_search": "Smart search",
    "auto_fast": "Automatic packing",
    "deep_search": "Deep search",
    "optimize_order_plan": "Order plan optimization",
    "optimize_plan": "Domain optimization",
    "_run_engine": "Engine execution",
    "build_preview_session": "Preview generation",
    "_finish_plan_search": "Complete a seed",
    "smart_search.finish": "Complete a selected seed",
    "smart_search.finish_batch": "Select seeds from the batch",
    "run_single_method": "Packing strategy attempt",
    "_run_preordered_method": "Ordered packing attempt",
    "pack_with_stable_kerf": "Compare direct and expanded kerf",
    "expand_plan_kerf": "Expand physical kerf",
    "nest_glass_openings": "Glass opening nesting",
    "apply_shape_aware_nesting": "Shape nesting",
    "improve_plan_search": "Board cancellation and repair",
    "consolidate_nested_boards": "Consolidate nested boards",
    "improve_same_count_layout": "Improve layout on the same board count",
    "improve_fixed_board_layout": "Adaptive neighborhood search",
    "alns_operator": "Neighborhood operator attempt",
    "refine_system_layout": "System layout refinement",
    "refine_pattern_layout": "Pattern search",
    "refine_corner_layout": "Corner frame search",
    "_snapshot_outcome": "Physical snapshot and validation",
    "retain_diverse_finals": "Retain diverse finalists",
    "merge_preview_candidates": "Merge search rounds",
    "native_projection_final_sort_and_dedup": "Native gallery after projection and duplicate removal",
    "after_alns_projection": "Gallery after adaptive search",
    "after_pattern_projection": "Gallery after pattern search",
    "after_corner_projection": "Gallery after corner search",
    "published_preview": "Published preview gallery",
    "industrial_rank_with_same_board_nesting_coverage": "Industrial ranking with same-board nesting coverage",
    "continue_merge_final_sort_dedup_limit": "Continue search: merge, compare, remove duplicates and retain five",
}


def render_search_report(data, *, translate=None):
    catalog = _arabic_catalog()
    translate = translate or (lambda key: catalog.get(key, key))
    labels = {key: translate(key) for key in MESSAGES if key not in CODE_MESSAGES}
    labels.update({code: translate(message) for code, message in CODE_MESSAGES.items()})

    def script_json(value):
        return (
            json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            )
            .replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029")
        )

    template = (
        Path(__file__).with_name("search_report.html").read_text(encoding="utf-8")
    )
    # One substitution pass prevents user text from becoming a template token.
    import re

    replacements = {
        "TITLE": escape(translate("Cutting search report")),
        "DATA": script_json(data),
        "LABELS": script_json(labels),
    }
    return re.sub(
        r"@@(TITLE|DATA|LABELS)@@", lambda match: replacements[match[1]], template
    )
