from __future__ import annotations

import math
from copy import deepcopy
import time
from dataclasses import dataclass, replace
from typing import Any, Protocol

from almdina_erp.almdina_erp.application.cutting.execution_trace import (
    build_cutting_execution_trace,
)
from almdina_erp.almdina_erp.domain.cutting.adaptive_trim import (
    AdaptiveTrimDecision,
    AppliedTrim,
    PlanQuality,
    TRIM_PRECISION_CM,
)
from almdina_erp.almdina_erp.domain.cutting.sheet_edge_trim import (
    realize_sheet_edge_trim,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    PlanSettings,
    normalize_plan_settings,
)
from almdina_erp.almdina_erp.domain.cutting.evaluation import placement_permission_errors
from almdina_erp.almdina_erp.domain.cutting.optimizer import enrich_plan_metrics
from almdina_erp.almdina_erp.domain.cutting.abc_search import ABCSearchPolicy
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import polygon_area
from almdina_erp.almdina_erp.domain.cutting.glass_opening_dxf import placed_glass_hole_mm
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import material_outline_cm
from almdina_erp.almdina_erp.domain.orders.costing import round_value
from almdina_erp.almdina_erp.domain.orders.piece_mirroring import piece_mirroring_allowed


class CuttingPlanEngine(Protocol):
    """Port implemented by the current optimization-engine adapter."""

    def expand_pieces(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    def optimize(
        self,
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
        kerf_cm: float,
        *,
        selected_mode: str,
        machine_type: str,
        time_limit_sec: float,
        exact_piece_limit: int,
        min_remnant_width_cm: float,
        min_remnant_length_cm: float,
        min_remnant_area_m2: float,
        mirroring_allowed: bool = False,
        research_abc: ABCSearchPolicy | None = None,
    ) -> dict[str, Any]: ...

    def validate(
        self,
        plan: dict[str, Any],
        pieces: list[dict[str, Any]],
        board_width_cm: float,
        board_length_cm: float,
    ) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class BoardGeometry:
    full_width_cm: float
    full_length_cm: float
    trim_cm: float
    kerf_cm: float

    @property
    def usable_width_cm(self) -> float:
        return self.full_width_cm - (self.trim_cm * 2)

    @property
    def usable_length_cm(self) -> float:
        return self.full_length_cm - (self.trim_cm * 2)


@dataclass(frozen=True, slots=True)
class AppliedMargins(AppliedTrim):
    """Compatibility surface for callers using the pre-ALMADINA-138 API."""

    def usable_width_cm(self, board: BoardGeometry) -> float:
        return super().usable_width_cm(full_width_cm=board.full_width_cm)

    def usable_length_cm(self, board: BoardGeometry) -> float:
        return super().usable_length_cm(full_length_cm=board.full_length_cm)


@dataclass(frozen=True, slots=True)
class OptimizerOptions:
    selected_mode: str
    machine_type: str
    time_limit_sec: float
    exact_piece_limit: int
    min_remnant_width_cm: float
    min_remnant_length_cm: float
    min_remnant_area_m2: float
    max_centerable_edge_gap_cm: float = 5.0
    alignment_search_budget_sec: float = 1.0
    research_abc: ABCSearchPolicy | None = None
    alns_search_budget_sec: float = 0.0
    pattern_search_budget_sec: float = 0.0
    corner_search_budget_sec: float = 0.0


@dataclass(frozen=True, slots=True)
class OptimizeOrderPlanCommand:
    engine_version: str
    input_fingerprint: str
    board: BoardGeometry
    optimizer: OptimizerOptions
    piece_rows: tuple[dict[str, Any], ...]
    plan_settings: PlanSettings | None = None
    allow_piece_mirroring: bool = False
    seed_plans: tuple[dict[str, Any], ...] = ()
    search_round: int = 0


@dataclass(frozen=True, slots=True)
class OptimizationOutcome:
    snapshot: dict[str, Any]
    packing_score: str
    required_boards: int
    method_label: str
    expanded_pieces: tuple[dict[str, Any], ...]
    candidate_snapshots: tuple[dict[str, Any], ...] = ()
    search_seeds: tuple[dict[str, Any], ...] = ()


def optimize_order_plan(
    command: OptimizeOrderPlanCommand,
    *,
    engine: CuttingPlanEngine,
) -> OptimizationOutcome:
    """Expand pieces, resolve Adaptive Trim, optimize, validate, and snapshot."""

    started = time.monotonic()
    board = command.board
    plan_settings = _canonical_trace_settings(command)
    smart = plan_settings.optimization_mode == "smart"
    deadline = started + command.optimizer.time_limit_sec
    rows = [dict(row) for row in command.piece_rows]
    expanded = engine.expand_pieces(rows)
    preferred_trim = AppliedTrim(
        width_trim_cm=max(0.0, board.trim_cm),
        length_trim_cm=max(0.0, board.trim_cm),
    )

    def run_for_trim(trim: AppliedTrim) -> dict[str, Any]:
        return _run_engine(
            command, engine=engine, pieces=expanded, trim=trim,
            time_limit_sec=max(0.0, deadline - time.monotonic()) if smart else None,
        )

    preferred_plan = run_for_trim(preferred_trim)
    # New plans use the requested trim as a mandatory physical inset.
    # Do not spend the search budget probing smaller margins.
    preferred_quality = _plan_quality(preferred_plan)
    trim_decision = AdaptiveTrimDecision(
        preferred=preferred_trim,
        applied=preferred_trim,
        preferred_quality=preferred_quality,
        applied_quality=preferred_quality,
    )
    applied_trim = trim_decision.applied
    plan = preferred_plan

    raw_candidates = plan.pop('smart_candidates', []) if smart else []
    # Internal research nominees never replace native warm finalists before
    # real Application projection. No RPC/settings surface enables this path.
    research_candidates = plan.pop('smart_research_candidates', []) if smart else []
    native_count = len(raw_candidates)
    if command.optimizer.research_abc is not None and command.optimizer.research_abc.retention:
        raw_candidates = [*raw_candidates, *research_candidates[:1]]
    # A shared, finite allowance across the gallery; never extend native search.
    # Begin the shared tail allowance when the first alignment actually starts.
    alignment_budget = {"deadline": None}
    raw_seeds = []
    outcome = None
    snapshots = []
    for candidate_index, raw in enumerate(raw_candidates):
        # Reserve a fair portion of the shared tail allowance for every
        # displayed candidate, without extending the total elapsed deadline.
        alignment_budget["remaining_candidates"] = max(1, native_count - candidate_index)
        result = _snapshot_outcome(command,engine,deepcopy(raw),expanded,applied_trim,trim_decision,plan_settings,
                                   alignment_budget=alignment_budget)
        if result.snapshot['validation']['is_valid']:
            if outcome is None:
                outcome = result
            snapshots.append(result.snapshot)
            raw_seeds.append(deepcopy(raw))
    if outcome is None:
        # Smart alternatives already own the result when any is valid. Avoid
        # projecting an unused fallback, while still validating every candidate.
        outcome = _snapshot_outcome(command, engine, deepcopy(plan), expanded, applied_trim, trim_decision, plan_settings,
                                    alignment_budget=alignment_budget)
    if smart:
        # Native search uses a cheap placement estimate to bound exploration.
        # Final System ranking must instead agree with the authoritative real
        # cutter-center topology used by Final Alignment. Otherwise a border
        # placement can outrank an equivalent continuous *internal* cutter
        # path merely because estimated _cut_metrics ignores sheet edges.
        # Never mix unproven special geometry with exact scores.
        from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys
        keys = final_system_sort_keys(snapshots)
        ranked = [(snapshot, seed) for _, snapshot, seed in
                  sorted(zip(keys, snapshots, raw_seeds), key=lambda item: item[0])]
        snapshots = [snapshot for snapshot, _ in ranked]
        raw_seeds = [seed for _, seed in ranked]
        # Final compaction can make two raw alternatives identical. Keep the
        # best visible copy while retaining every raw warm seed for continuation.
        from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import geometry_signature
        seen = set()
        unique = []
        for snapshot in snapshots:
            signature = geometry_signature(snapshot)
            if signature not in seen:
                seen.add(signature)
                unique.append(snapshot)
        snapshots = unique[:5]
        # Preserve the completed native gallery, including its full alignment
        # allowance. Refinement has its own *additional*, bounded stage; it
        # never steals discoveries or alignment time from this incumbent.
        configured_alns = command.optimizer.alns_search_budget_sec
        alns_seconds = (min(10.0, configured_alns, max(0.0, command.optimizer.time_limit_sec))
                        if math.isfinite(configured_alns) and configured_alns > 0 else 0.0)
        alns_trace = None
        extra_records = []
        configured_patterns = command.optimizer.pattern_search_budget_sec
        pattern_seconds = (min(10.0, configured_patterns, max(0.0,command.optimizer.time_limit_sec))
            if math.isfinite(configured_patterns) and configured_patterns>0 else 0.0)
        formation_seeds = []
        if snapshots and raw_seeds and alns_seconds > 0:
            additions, alns_trace = _refine_smart_gallery(command, engine, expanded,
                raw_seeds[0], snapshots[0], applied_trim, trim_decision, plan_settings, alns_seconds,
                formation_seeds=formation_seeds if pattern_seconds>0 else None)
            if additions:
                extra_records.extend(additions)
                native_by_signature = {geometry_signature(snapshot): seed for snapshot, seed in reversed(ranked)}
                records = [(snapshot, native_by_signature[geometry_signature(snapshot)]) for snapshot in snapshots]
                records.extend(additions)
                keys = final_system_sort_keys([snapshot for snapshot, _ in records])
                ordered = [record for _, record in sorted(zip(keys, records), key=lambda item: item[0])]
                seen = set()
                selected = []
                for snapshot, seed in ordered:
                    signature = geometry_signature(snapshot)
                    if signature not in seen:
                        seen.add(signature)
                        selected.append((snapshot, seed))
                snapshots = [snapshot for snapshot, _ in selected[:5]]
                # Keep visible seed correspondence first, then remaining native
                # warm discoveries. Continuation still receives at most five.
                raw_seeds = [seed for _, seed in selected[:5]] + raw_seeds
        pattern_trace = None
        if snapshots and raw_seeds and pattern_seconds>0:
            additions,pattern_trace = _refine_pattern_gallery(command,engine,expanded,raw_seeds,
                snapshots[0],applied_trim,trim_decision,plan_settings,pattern_seconds,formation_seeds)
            if additions:
                extra_records.extend(additions)
                seed_by_signature = {geometry_signature(s):r for s,r in [*ranked,*extra_records]}
                records = [(s,seed_by_signature[geometry_signature(s)]) for s in snapshots]
                records.extend(additions)
                keys = final_system_sort_keys([s for s,_ in records])
                selected,seen = [],set()
                for _,record in sorted(zip(keys,records),key=lambda item:item[0]):
                    signature = geometry_signature(record[0])
                    if signature not in seen:
                        seen.add(signature)
                        selected.append(record)
                snapshots = [s for s,_ in selected[:5]]
                raw_seeds = [r for _,r in selected[:5]] + raw_seeds
        corner_trace = None
        configured_corners=command.optimizer.corner_search_budget_sec
        corner_seconds=(min(10.0,configured_corners,max(0.,command.optimizer.time_limit_sec))
            if math.isfinite(configured_corners) and configured_corners>0 else 0.)
        if (snapshots and raw_seeds and corner_seconds>0
                and any(p.get('piece_type') in {'L-Shaped Corner','Clipped Corner'} for p in expanded)):
            additions,corner_trace=_refine_pattern_gallery(command,engine,expanded,raw_seeds,
                snapshots[0],applied_trim,trim_decision,plan_settings,corner_seconds,corner_only=True)
            if additions:
                seed_by_signature={geometry_signature(s):r for s,r in [*ranked,*extra_records]}
                records=[(s,seed_by_signature[geometry_signature(s)]) for s in snapshots]+additions
                keys=final_system_sort_keys([s for s,_ in records])
                selected,seen=[],set()
                for _,record in sorted(zip(keys,records),key=lambda item:item[0]):
                    signature=geometry_signature(record[0])
                    if signature not in seen:
                        seen.add(signature)
                        selected.append(record)
                snapshots=[s for s,_ in selected[:5]]
                raw_seeds=[r for _,r in selected[:5]]+raw_seeds
        if snapshots:
            outcome = replace(
                outcome,
                snapshot=snapshots[0],
                required_boards=len(snapshots[0].get("sheets") or []),
                method_label=str(snapshots[0].get("method_label") or ""),
                packing_score=_packing_score_for_snapshot(snapshots[0]),
            )
        outcome.snapshot['smart_search'] = dict(plan.get('smart_search') or {})
        outcome.snapshot['search_time_limit_sec'] = command.optimizer.time_limit_sec
        outcome.snapshot['total_elapsed_sec'] = round(time.monotonic()-started,3)
        outcome.snapshot['smart_search']['trim_evaluations'] = 1
        if alns_trace is not None:
            outcome.snapshot['smart_search']['alns'] = alns_trace
        if pattern_trace is not None:
            outcome.snapshot['smart_search']['pattern_search'] = pattern_trace
        if corner_trace is not None:
            outcome.snapshot['smart_search']['corner_search'] = corner_trace
    return replace(outcome,candidate_snapshots=tuple(snapshots),search_seeds=tuple(raw_seeds))


def _refine_smart_gallery(command, engine, expanded, raw, incumbent, applied_trim,
                          trim_decision, plan_settings, seconds, *, formation_seeds=None):
    """One shared refinement deadline, then the existing snapshot/validation port.

    Called for a new System calculation only. Saved/uploaded snapshots are never
    loaded here. A proposal that projects worse cannot remove the native winner.
    """
    from almdina_erp.almdina_erp.domain.cutting.same_count_layout_search import material_signature
    from almdina_erp.almdina_erp.domain.cutting.system_layout_refinement import refine_system_layout
    from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys
    board = command.board
    started = time.monotonic()
    deadline = started + seconds
    width = applied_trim.usable_width_cm(full_width_cm=board.full_width_cm)
    height = applied_trim.usable_length_cm(full_length_cm=board.full_length_cm)
    projection_reserve = min(1.5, seconds*.15)
    def collect(skeleton):
        if len(formation_seeds)<12:
            formation_seeds.append(skeleton)
    proposals, trace = refine_system_layout(raw, expanded, width, height, board.kerf_cm,
        deadline=deadline-projection_reserve, machine_type=command.optimizer.machine_type,
        mirroring_allowed=piece_mirroring_allowed(command.allow_piece_mirroring),
        metric_kwargs=dict(min_remnant_width_cm=command.optimizer.min_remnant_width_cm,
            min_remnant_length_cm=command.optimizer.min_remnant_length_cm,
            min_remnant_area_m2=command.optimizer.min_remnant_area_m2),
        **({'pattern_sink':collect} if formation_seeds is not None else {}))
    original = material_signature(raw)
    # Reserve projection time cooperatively within the same stage deadline.
    # Completed Domain improvements remain available at expiry: validation is
    # atomic and may finish after the cooperative deadline, as in native search.
    additions = []
    for index, proposal in enumerate(proposals[1:]):
        if index and time.monotonic() >= deadline:
            break
        if material_signature(proposal) == original:
            continue
        configured_alignment = command.optimizer.alignment_search_budget_sec
        alignment_share = (min(.15, configured_alignment) if math.isfinite(configured_alignment)
                           and configured_alignment > 0 else 0.0)
        result = _snapshot_outcome(command, engine, deepcopy(proposal), expanded,
            applied_trim, trim_decision, plan_settings,
            alignment_budget={"deadline": min(deadline,time.monotonic()+alignment_share),
                              "remaining_candidates": 1})
        if result.snapshot['validation']['is_valid']:
            before, after = final_system_sort_keys([incumbent, result.snapshot])
            if after < before:
                additions.append((result.snapshot, proposal))
    summary = {key: trace[key] for key in (
        'attempts', 'stop', 'operators', 'weights', 'movable_pieces', 'pinned_pieces',
        'skeletons', 'compound_attempts', 'compound_improvements') if key in trace}
    summary.update(budget_sec=seconds, elapsed_sec=round(time.monotonic()-started, 3),
        projected_improvements=len(additions), additional_to_native_search=True)
    return additions, summary


def _refine_pattern_gallery(command,engine,expanded,seeds,incumbent,applied_trim,
                            trim_decision,plan_settings,seconds,formation_seeds=(),*,corner_only=False):
    from almdina_erp.almdina_erp.domain.cutting.pattern_layout_search import refine_pattern_layout
    from almdina_erp.almdina_erp.domain.cutting.cut_line_quality import final_system_sort_keys
    started = time.monotonic()
    deadline = started+seconds
    board = command.board
    # All raw proposals use usable coordinates. Supply the physical frame for
    # actual cutter metrics too; usable borders are not original board edges.
    def physical_frames(plans):
        copies = deepcopy(plans)
        for plan in copies:
            for sheet in plan['sheets']:
                sheet.update(full_width_cm=board.full_width_cm,full_length_cm=board.full_length_cm,
                    applied_trim_width_cm=applied_trim.width_trim_cm,
                    applied_trim_length_cm=applied_trim.length_trim_cm,
                    usable_width_cm=sheet['w'],usable_length_cm=sheet['h'])
        return copies
    seeds = physical_frames(seeds[:5])
    formation_seeds = physical_frames(formation_seeds)
    try:
        refiner=refine_pattern_layout
        if corner_only:
            from almdina_erp.almdina_erp.domain.cutting.corner_frame_search import refine_corner_layout
            refiner=refine_corner_layout
        proposals,trace = refiner(seeds[0],seeds,expanded,
            applied_trim.usable_width_cm(full_width_cm=board.full_width_cm),
            applied_trim.usable_length_cm(full_length_cm=board.full_length_cm),board.kerf_cm,
            deadline=deadline-min(1.5,seconds*.15),machine_type=command.optimizer.machine_type,
            mirroring_allowed=piece_mirroring_allowed(command.allow_piece_mirroring),
            metric_kwargs=dict(min_remnant_width_cm=command.optimizer.min_remnant_width_cm,
                min_remnant_length_cm=command.optimizer.min_remnant_length_cm,
                min_remnant_area_m2=command.optimizer.min_remnant_area_m2),
            solver=getattr(engine,'solve_pattern_master',None),formation_seeds=formation_seeds,
            row_solver=getattr(engine,'solve_shelf_master',None))
    except Exception as error:
        return [],dict(stop='refinement_error',error_type=type(error).__name__,budget_sec=seconds,
            elapsed_sec=round(time.monotonic()-started,3),additional_to_completed_alns=True)
    additions = []
    for index,proposal in enumerate(proposals[1:]):
        if index and time.monotonic()>=deadline:
            break
        configured = command.optimizer.alignment_search_budget_sec
        share = min(.15,configured) if math.isfinite(configured) and configured>0 else 0.
        try:
            result = _snapshot_outcome(command,engine,deepcopy(proposal),expanded,applied_trim,
                trim_decision,plan_settings,alignment_budget=dict(deadline=min(deadline,time.monotonic()+share),
                                                               remaining_candidates=1))
        except Exception as error:
            trace.setdefault('projection_errors',[]).append(type(error).__name__)
            continue
        if result.snapshot['validation']['is_valid']:
            before,after = final_system_sort_keys([incumbent,result.snapshot])
            if after<before:
                additions.append((result.snapshot,proposal))
    trace.update(budget_sec=seconds,elapsed_sec=round(time.monotonic()-started,3),
        projected_improvements=len(additions),additional_to_completed_alns=True)
    if corner_only:
        trace['additional_to_completed_patterns']=True
    return additions,trace


def _snapshot_outcome(command, engine, plan, expanded, applied_trim, trim_decision, plan_settings, *,
                      alignment_budget=None):
    """One manufacturing snapshot projection for the default and every alternative."""
    board = command.board
    plan["kerf_cm"] = board.kerf_cm
    usable_width_cm = applied_trim.usable_width_cm(
        full_width_cm=board.full_width_cm
    )
    usable_length_cm = applied_trim.usable_length_cm(
        full_length_cm=board.full_length_cm
    )
    margin_notes = _build_margin_notes(board, applied_trim)

    method_label = str(plan.get("method_label") or "")

    sheets = [dict(sheet) for sheet in (plan.get("sheets") or [])]
    for sheet in sheets:
        sheet.setdefault("full_width_cm", board.full_width_cm)
        sheet.setdefault("full_length_cm", board.full_length_cm)
        sheet.setdefault("usable_width_cm", usable_width_cm)
        sheet.setdefault("usable_length_cm", usable_length_cm)
        sheet["applied_trim_width_cm"] = applied_trim.width_trim_cm
        sheet["applied_trim_length_cm"] = applied_trim.length_trim_cm
    machine_type = command.optimizer.machine_type or "Auto"
    metric_options = {
        "machine_type": machine_type,
        "min_remnant_width_cm": command.optimizer.min_remnant_width_cm,
        "min_remnant_length_cm": command.optimizer.min_remnant_length_cm,
        "min_remnant_area_m2": command.optimizer.min_remnant_area_m2,
    }
    original_sheets = deepcopy(sheets)
    original_metrics = _enrich_final_geometry_metrics(
        {**plan, "sheets": original_sheets}, metric_options
    )
    realize_sheet_edge_trim(
        sheets,
        full_width_cm=board.full_width_cm,
        full_length_cm=board.full_length_cm,
        preferred_width_trim_cm=trim_decision.preferred.width_trim_cm,
        preferred_length_trim_cm=trim_decision.preferred.length_trim_cm,
        balance_existing_applied=True,
        max_centerable_edge_gap_cm=command.optimizer.max_centerable_edge_gap_cm,
        **metric_options,
    )
    plan["sheets"] = sheets
    plan = _enrich_final_geometry_metrics(plan, metric_options)
    if _centering_worsens_industrial_quality(
        original_metrics.get("industrial_rank") or (),
        plan.get("industrial_rank") or (),
        machine_type=machine_type,
    ):
        plan["sheets"] = original_sheets
        plan = _enrich_final_geometry_metrics(plan, metric_options)

    if plan_settings.optimization_mode == "smart":
        # An invalid centering proposal must not make alignment a no-op and
        # then be rolled back only *after* the refinement opportunity is gone.
        # Use the same independent geometry/permission gates as the final gate.
        from almdina_erp.almdina_erp.domain.cutting.final_cut_line_alignment import (
            align_regular_cut_lines, validate_alignment_baseline, has_regular_alignment_candidates,
        )
        configured = command.optimizer.alignment_search_budget_sec
        allowed = (max(0.0, min(configured, command.optimizer.time_limit_sec))
                   if math.isfinite(configured) and configured >= 0 else 0.0)
        baseline_proof = None
        if allowed > 0 and has_regular_alignment_candidates(plan, expanded, machine_type):
            baseline_proof = validate_alignment_baseline(plan, expanded, usable_width_cm, usable_length_cm,
                board.kerf_cm, mirroring_allowed=piece_mirroring_allowed(command.allow_piece_mirroring))
            if baseline_proof is None:
                plan["sheets"] = original_sheets
                plan = _enrich_final_geometry_metrics(plan, metric_options)
                baseline_proof = validate_alignment_baseline(plan, expanded, usable_width_cm, usable_length_cm,
                    board.kerf_cm, mirroring_allowed=piece_mirroring_allowed(command.allow_piece_mirroring))
        from almdina_erp.almdina_erp.domain.cutting.plan_search import compact_regular_final
        plan = compact_regular_final(plan, expanded, usable_width_cm, usable_length_cm, board.kerf_cm,
            machine_type=machine_type,
            mirroring_allowed=piece_mirroring_allowed(command.allow_piece_mirroring),
            metric_kwargs={key: value for key, value in metric_options.items() if key != "machine_type"})
        # Shared budget is not consumed by unrelated snapshot preparation.
        if alignment_budget is None:
            alignment_budget = {"deadline": None}
        if alignment_budget["deadline"] is None:
            # Invalid direct callers fail closed; authoritative factory
            # settings already reject NaN/Infinity and negative values.
            alignment_budget["deadline"] = time.monotonic() + allowed
        # Every gallery candidate gets a bounded share of the *remaining*
        # shared tail; unused capacity automatically returns to later plans.
        # A lone fallback uses the full remaining allowance.
        now = time.monotonic()
        remaining = max(1, int(alignment_budget.get("remaining_candidates") or 1))
        remaining_seconds = max(0.0, alignment_budget["deadline"] - now)
        candidate_deadline = now + remaining_seconds / remaining
        # Post-search placement refinement only; never import/approve uploaded DXF.
        plan = align_regular_cut_lines(
            plan, expanded, usable_width_cm, usable_length_cm, board.kerf_cm,
            machine_type=machine_type,
            mirroring_allowed=piece_mirroring_allowed(command.allow_piece_mirroring),
            metric_kwargs={key: value for key, value in metric_options.items() if key != "machine_type"},
            deadline_monotonic=candidate_deadline,
            baseline_proof=baseline_proof,
        )

    def validate_snapshot_plan() -> list[str]:
        errors = list(
            engine.validate(plan, expanded, usable_width_cm, usable_length_cm)
        )
        errors.extend(
            placement_permission_errors(
                plan,
                expanded,
                mirroring_allowed=piece_mirroring_allowed(
                    command.allow_piece_mirroring
                ),
            )
        )
        if plan.get("unplaced"):
            errors.append(
                "تعذر وضع جميع القطع ضمن أبعاد اللوح والهامش الأدنى المحددين."
            )
        return errors

    validation_errors = validate_snapshot_plan()
    if validation_errors and plan.get("sheets") != original_sheets:
        plan["sheets"] = original_sheets
        plan = _enrich_final_geometry_metrics(plan, metric_options)
        validation_errors = validate_snapshot_plan()

    metrics = dict(plan.get("industrial_metrics") or {})
    required_boards = len(plan.get("sheets") or [])

    trim_policy = _trim_policy_metadata(
        board=board,
        decision=trim_decision,
    )
    execution_trace = build_cutting_execution_trace(
        plan_settings=plan_settings,
        trim_decision=trim_decision,
        optimizer_outcome=plan,
        engine_version=command.engine_version,
    )
    snapshot = {
        "engine_version": command.engine_version,
        "input_fingerprint": command.input_fingerprint,
        "optimization_mode": (
            plan.get("optimization_mode")
            or command.optimizer.selected_mode
            or "Auto Pro"
        ),
        "machine_type": command.optimizer.machine_type or "Auto",
        "method_key": plan.get("method_key") or "",
        "method_label": method_label,
        "ordering_strategy": plan.get("ordering_strategy") or "",
        "score": plan.get("score"),
        "industrial_metrics": metrics,
        "industrial_rank": list(plan.get("industrial_rank") or []),
        "attempts": _integer(plan.get("attempts")),
        "search_elapsed_sec": _number(plan.get("search_elapsed_sec")),
        "search_time_limit_sec": _number(plan.get("search_time_limit_sec")),
        "solver_status": plan.get("solver_status") or "",
        "solver_wall_time_sec": _number(plan.get("solver_wall_time_sec")),
        "full_board_width_cm": board.full_width_cm,
        "full_board_length_cm": board.full_length_cm,
        "usable_board_width_cm": usable_width_cm,
        "usable_board_length_cm": usable_length_cm,
        "kerf_cm": board.kerf_cm,
        "max_centerable_edge_gap_cm": command.optimizer.max_centerable_edge_gap_cm,
        "trim_cm": board.trim_cm,
        "allow_piece_mirroring": piece_mirroring_allowed(command.allow_piece_mirroring),
        "applied_trim_width_cm": applied_trim.width_trim_cm,
        "applied_trim_length_cm": applied_trim.length_trim_cm,
        "trim_policy": trim_policy,
        "execution_trace": execution_trace.to_snapshot(),
        # Compatibility metadata retained for print/DXF/readers that still use
        # the pre-ALMADINA-138 margin vocabulary.
        "margin_policy": {
            "mode": trim_decision.mode,
            "preferred_margin_mm": trim_policy["preferred_trim_mm"],
            "left_mm": trim_policy["applied_width_trim_mm"],
            "right_mm": trim_policy["applied_width_trim_mm"],
            "top_mm": trim_policy["applied_length_trim_mm"],
            "bottom_mm": trim_policy["applied_length_trim_mm"],
            "notes": margin_notes,
        },
        "margin_notes": margin_notes,
        "used_area_m2": plan.get("used_area_m2"),
        "total_board_area_m2": plan.get("total_board_area_m2"),
        "waste_area_m2": plan.get("waste_area_m2"),
        "special_shape_raw_summary": summarize_special_shapes(expanded, plan),
        "sheets": plan["sheets"],
        "unplaced": plan.get("unplaced") or [],
        "validation": {
            "is_valid": not validation_errors,
            "errors": list(validation_errors),
        },
    }

    return OptimizationOutcome(
        snapshot=snapshot,
        packing_score=_packing_score_for_snapshot(snapshot),
        required_boards=required_boards,
        method_label=method_label,
        expanded_pieces=tuple(expanded),
    )


def _packing_score_for_snapshot(snapshot: dict[str, Any]) -> str:
    metrics = dict(snapshot.get("industrial_metrics") or {})
    waste_area = max(0.0, _number(snapshot.get("waste_area_m2")))
    total_board_area = _number(snapshot.get("total_board_area_m2"))
    waste_percent = round_value(
        (waste_area / total_board_area * 100) if total_board_area else 0,
        2,
    )
    score = (
        f"ألواح: {len(snapshot.get('sheets') or [])} | هدر: {waste_percent}% | "
        f"قصات تقديرية: {_integer(metrics.get('estimated_cut_count'))} | "
        "أكبر بقايا مفيدة: "
        f"{round_value(metrics.get('largest_reusable_free_area_m2') or 0, 3)} م² | "
        f"محاولات: {_integer(snapshot.get('attempts'))} | "
        f"الخوارزمية: {snapshot.get('method_label') or ''}"
    )
    notes = snapshot.get("margin_notes") or []
    return score + (" | ⚠ " + " ".join(notes) if notes else "")


def _enrich_final_geometry_metrics(
    plan: dict[str, Any], metric_options: dict[str, Any]
) -> dict[str, Any]:
    """Refresh quality only when the snapshot has complete placed geometry."""
    for sheet in plan.get("sheets") or []:
        if _number(sheet.get("w")) <= 0 or _number(sheet.get("h")) <= 0:
            return plan
        for piece in sheet.get("pieces") or []:
            if any(piece.get(key) is None for key in ("x", "y", "w", "h")):
                return plan
    return enrich_plan_metrics(
        plan, str(plan.get("method_key") or ""), **metric_options
    )


def _centering_worsens_industrial_quality(
    original_rank: list[Any] | tuple[Any, ...],
    centered_rank: list[Any] | tuple[Any, ...],
    *,
    machine_type: str,
) -> bool:
    """Protect manufacturing priorities while centering final geometry.

    CNC Router contour estimates count a newly interior edge as another line,
    although the exported operation still cuts the same door contour. Keep
    board, panel, remnant, rotation, and complexity priorities authoritative;
    Auto uses the same contour/separability rules as Router. Panel Saw and
    unknown machine types retain the conservative complete-rank comparison.
    """

    before, after = tuple(original_rank), tuple(centered_rank)
    if len(before) != 8 or len(after) != 8 or machine_type not in {"Auto", "CNC Router"}:
        return after > before
    protected_indices = (0, 1, 2, 3, 6, 7)
    return any(after[index] > before[index] for index in protected_indices)


def _canonical_trace_settings(command: OptimizeOrderPlanCommand) -> PlanSettings:
    """Return the canonical settings object used as execution-trace input.

    Frappe production callers pass their already-normalized PlanSettings object.
    The fallback preserves compatibility for application callers that predate
    ALMADINA-139 while still constructing the trace from a canonical contract.
    """

    if command.plan_settings is not None:
        return command.plan_settings
    return normalize_plan_settings(
        optimization_mode=command.optimizer.selected_mode,
        machine_type=command.optimizer.machine_type,
        optimization_time_limit_sec=command.optimizer.time_limit_sec,
        kerf_mm=command.board.kerf_cm * 10,
        preferred_trim_mm=command.board.trim_cm * 10,
    )


def _run_engine(
    command: OptimizeOrderPlanCommand,
    *,
    engine: CuttingPlanEngine,
    pieces: list[dict[str, Any]],
    trim: AppliedTrim,
    time_limit_sec: float | None = None,
) -> dict[str, Any]:
    board = command.board
    return engine.optimize(
        pieces,
        trim.usable_width_cm(full_width_cm=board.full_width_cm),
        trim.usable_length_cm(full_length_cm=board.full_length_cm),
        board.kerf_cm,
        selected_mode=command.optimizer.selected_mode,
        machine_type=command.optimizer.machine_type,
        time_limit_sec=(command.optimizer.time_limit_sec if time_limit_sec is None else time_limit_sec),
        exact_piece_limit=command.optimizer.exact_piece_limit,
        min_remnant_width_cm=command.optimizer.min_remnant_width_cm,
        min_remnant_length_cm=command.optimizer.min_remnant_length_cm,
        min_remnant_area_m2=command.optimizer.min_remnant_area_m2,
        mirroring_allowed=piece_mirroring_allowed(command.allow_piece_mirroring),
        **({'research_abc': command.optimizer.research_abc}
           if command.optimizer.research_abc is not None else {}),
        **({'seed_plans':command.seed_plans,'search_round':command.search_round}
           if command.seed_plans or command.search_round else {}),
    )


def _physical_board_lower_bound(
    pieces: list[dict[str, Any]],
    board: BoardGeometry,
) -> int:
    board_area = max(0.0, board.full_width_cm * board.full_length_cm)
    if board_area <= 0:
        return 0
    areas = []
    for piece in pieces:
        kind = str(piece.get("piece_type") or "Regular")
        if kind == "Regular":
            areas.append(
                max(0.0, _number(piece.get("width_cm")))
                * max(0.0, _number(piece.get("length_cm")))
            )
            continue
        # Special source outlines do not certify net material including all
        # structural holes. Unknown geometry contributes zero, never its box.
        if kind not in {"L-Shaped Corner", "Clipped Corner", "Glass"}:
            continue
        try:
            outline = material_outline_cm(piece)
            if outline is None:
                continue
            area = polygon_area(outline)
            if kind == "Glass":
                hole_mm = placed_glass_hole_mm(piece, rotated=False)
                if hole_mm is None:
                    continue
                area -= polygon_area(hole_mm) / 100  # mm² -> cm²
            if math.isfinite(area):
                areas.append(max(0.0, area))
        except (TypeError, ValueError, OverflowError):
            continue
    piece_area = sum(areas)
    if piece_area:
        return max(1, math.ceil(piece_area / board_area))
    return int(any((piece.get("piece_type") or "Regular") != "Regular" for piece in pieces))


def _plan_quality(plan: dict[str, Any]) -> PlanQuality:
    return PlanQuality(
        unplaced_count=len(plan.get("unplaced") or []),
        board_count=len(plan.get("sheets") or []),
    )


def _trim_policy_metadata(
    *,
    board: BoardGeometry,
    decision: AdaptiveTrimDecision,
) -> dict[str, Any]:
    return {
        "mode": decision.mode,
        "policy": "mandatory_minimum_v1",
        "preferred_trim_mm": round_value(max(0.0, board.trim_cm) * 10, 2),
        "applied_width_trim_mm": round_value(
            max(0.0, decision.applied.width_trim_cm) * 10,
            2,
        ),
        "applied_length_trim_mm": round_value(
            max(0.0, decision.applied.length_trim_cm) * 10,
            2,
        ),
        "relaxed_axes": list(decision.relaxed_axes),
        "precision_mm": round_value(TRIM_PRECISION_CM * 10, 2),
        "preferred_quality": {
            "unplaced_count": decision.preferred_quality.unplaced_count,
            "board_count": decision.preferred_quality.board_count,
        },
        "applied_quality": {
            "unplaced_count": decision.applied_quality.unplaced_count,
            "board_count": decision.applied_quality.board_count,
        },
    }


def _build_margin_notes(
    board: BoardGeometry,
    margins: AppliedTrim,
) -> list[str]:
    preferred_mm = round_value(max(0.0, board.trim_cm) * 10, 2)
    width_mm = round_value(max(0.0, margins.width_trim_cm) * 10, 2)
    length_mm = round_value(max(0.0, margins.length_trim_cm) * 10, 2)
    notes: list[str] = []

    if length_mm < preferred_mm:
        if length_mm <= 0:
            notes.append(
                "تم إلغاء هامش التشذيب العلوي والسفلي واستخدام طول اللوح الكامل؛ "
                "يجب التأكد من استقامة الحافتين قبل التنفيذ."
            )
        else:
            notes.append(
                f"تم تخفيض هامش التشذيب العلوي والسفلي من {preferred_mm:g} مم "
                f"إلى {length_mm:g} مم لكل جهة للحفاظ على قياسات القطع المطلوبة."
            )

    if width_mm < preferred_mm:
        if width_mm <= 0:
            notes.append(
                "تم إلغاء هامش التشذيب الأيمن والأيسر واستخدام عرض اللوح الكامل؛ "
                "يجب التأكد من استقامة الحافتين قبل التنفيذ."
            )
        else:
            notes.append(
                f"تم تخفيض هامش التشذيب الأيمن والأيسر من {preferred_mm:g} مم "
                f"إلى {width_mm:g} مم لكل جهة للحفاظ على قياسات القطع المطلوبة."
            )

    return notes


def summarize_special_shapes(
    expanded_pieces: list[dict[str, Any]],
    plan: dict[str, Any],
) -> dict[str, int | bool]:
    requested_ids = {
        _integer(piece.get("id"))
        for piece in expanded_pieces
        if (piece.get("piece_type") or "Regular") == "Special"
    }
    placed_ids = {
        _integer(piece.get("id"))
        for sheet in (plan.get("sheets") or [])
        for piece in (sheet.get("pieces") or [])
        if (piece.get("piece_type") or "Regular") == "Special"
    }
    unplaced_ids = {
        _integer(piece.get("id"))
        for piece in (plan.get("unplaced") or [])
        if (piece.get("piece_type") or "Regular") == "Special"
    }
    return {
        "requested": len(requested_ids),
        "placed": len(requested_ids.intersection(placed_ids)),
        "unplaced": len(requested_ids.intersection(unplaced_ids)),
        "complete": requested_ids.issubset(placed_ids) and not unplaced_ids,
    }


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


__all__ = [
    "AppliedMargins",
    "BoardGeometry",
    "CuttingPlanEngine",
    "OptimizationOutcome",
    "OptimizeOrderPlanCommand",
    "OptimizerOptions",
    "optimize_order_plan",
    "summarize_special_shapes",
]
