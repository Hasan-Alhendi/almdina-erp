"""Bounded evidence collector; JSON is the canonical report, never a plan."""

from __future__ import annotations

from copy import deepcopy
from collections import Counter
from dataclasses import asdict, is_dataclass
import hashlib
import json
import math
import time
import uuid
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.plan_portfolio import (
    geometry_signature,
    _GEOMETRY_FIELDS,
    _PREFIXES,
)
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
    finished_part_geometry_cm,
)

SCHEMA_VERSION = "1.0"
INDUSTRIAL_CRITERIA = [
    "unplaced_count",
    "board_count",
    "panel_saw_penalty",
    "largest_eligible_remnant_area_m2",
    "estimated_cut_count",
    "estimated_cut_length_cm",
    "rotation_count",
    "complexity",
]
FINAL_CRITERIA = [
    *INDUSTRIAL_CRITERIA[:4],
    "cutter_center_length_mm",
    "longest_internal_center_mm",
    "cutter_center_segment_count",
    *INDUSTRIAL_CRITERIA[4:],
]


def json_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return [json_value(v) for v in sorted(value, key=str)]
    return type(value).__name__


def canonical_json(data) -> str:
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def fingerprint(data) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def _flat(key):
    return [
        x
        for part in key
        for x in (_flat(part) if isinstance(part, (tuple, list)) else [part])
    ]


def _piece_details(piece):
    return {
        k: json_value(v)
        for k, v in piece.items()
        if (
            k in _GEOMETRY_FIELDS
            or k.startswith(_PREFIXES)
            or k in {"qty", "allow_rotation", "deduct_edge_thickness"}
        )
        and not k.endswith(("_usd", "_label"))
        and not any(word in k for word in ("cost", "price", "rate"))
    }


class SearchReport:
    def __init__(
        self,
        *,
        max_events=30000,
        max_geometry_bytes=16 * 1024 * 1024,
        parent_run_id=None,
        round_id=0,
        **metadata,
    ):
        self.metadata = dict(
            run_id=uuid.uuid4().hex,
            report_id=uuid.uuid4().hex,
            round_id=round_id,
            parent_run_id=parent_run_id,
            preview_id=None,
            schema_version=SCHEMA_VERSION,
            engine_version="",
            git_sha="",
            input_fingerprint="",
            settings_fingerprint="",
        )
        self.metadata.update(metadata)
        self.events = []
        self.spans = []
        self.attempts = []
        self.candidates = {}
        self.geometries = {}
        self.decisions = []
        self.gallery_history = []
        self.final_gallery = []
        self.coverage = dict(
            status="PARTIAL",
            dropped_events=0,
            omitted_geometries=0,
            observer_errors=[],
            observed_boundaries=[],
            limitations=[
                "Coordinate probes and uninstrumented inner solver states are not captured."
            ],
        )
        self._max_events = max(1, max_events)
        self._max_geometry_bytes = max(0, max_geometry_bytes)
        self._geometry_bytes = 0
        self._omitted = set()
        self._started = time.monotonic()
        self._span_index = {}
        self._expected_ids = None

    def failure(self, boundary, error):
        self.coverage["observer_error_count"] = (
            self.coverage.get("observer_error_count", 0) + 1
        )
        if len(self.coverage["observer_errors"]) < 100:
            self.coverage["observer_errors"].append(
                dict(boundary=boundary, error_type=type(error).__name__)
            )

    def candidate(self, plan, *, source=None, parent_candidate_id=None):
        if not isinstance(plan, dict) or "sheets" not in plan:
            return None
        signature = geometry_signature(plan)
        # Candidate identity includes the actual evaluation at this observation;
        # geometry is stored once even when method/rank/validation changes.
        rank = json_value(plan.get("industrial_rank") or [])
        candidate_id = fingerprint(
            [signature, rank, str(plan.get("method_key") or "")]
        )[:24]
        if candidate_id not in self.candidates:
            actual = Counter(
                str(p.get("piece_instance_id") or p.get("id"))
                for sheet in plan.get("sheets") or []
                for p in sheet.get("pieces") or []
            )
            self.candidates[candidate_id] = dict(
                candidate_id=candidate_id,
                geometry_fingerprint=signature,
                complete=not bool(plan.get("unplaced"))
                and bool(plan.get("sheets"))
                and (self._expected_ids is None or actual == self._expected_ids),
                unplaced_ids=[
                    p.get("piece_instance_id", p.get("id"))
                    for p in plan.get("unplaced") or []
                ],
                board_count=len(plan.get("sheets") or []),
                industrial_rank=rank,
                source=source,
                method_key=str(plan.get("method_key") or ""),
                ordering_strategy=str(plan.get("ordering_strategy") or ""),
                parent_candidate_id=parent_candidate_id,
                status="observed",
                reasons=[],
            )
            self.candidates[candidate_id]["incomplete_reason"] = (
                ("unplaced_pieces" if plan.get("unplaced") else "partial_inventory")
                if not self.candidates[candidate_id]["complete"]
                else None
            )
            self.candidates[candidate_id]["validation_status"] = json_value(
                plan.get("validation")
            )
        if signature not in self.geometries and signature not in self._omitted:
            sheets = []
            for sheet in plan.get("sheets") or []:
                drawing = {
                    k: json_value(sheet[k])
                    for k in (
                        "sheet_no",
                        "w",
                        "h",
                        "full_width_cm",
                        "full_length_cm",
                        "applied_trim_width_cm",
                        "applied_trim_length_cm",
                        "usable_width_cm",
                        "usable_length_cm",
                    )
                    if k in sheet
                }
                pieces = []
                for piece in sheet.get("pieces") or []:
                    item = _piece_details(piece)
                    shape = finished_part_geometry_cm(piece)
                    item["outline_cm"] = json_value(shape.outer) if shape else None
                    item["holes_cm"] = json_value(shape.holes) if shape else []
                    if shape is None:
                        self.coverage["limitations"] = list(
                            dict.fromkeys(
                                [
                                    *self.coverage["limitations"],
                                    "Some recorded pieces have unproven contours; no bounding-box substitute is drawn.",
                                ]
                            )
                        )
                    pieces.append(item)
                drawing["pieces"] = pieces
                sheets.append(drawing)
            geometry = dict(signature=signature, units="cm", sheets=sheets)
            size = len(canonical_json(geometry).encode("utf-8"))
            if self._geometry_bytes + size > self._max_geometry_bytes:
                self._omitted.add(signature)
                self.coverage["omitted_geometries"] += 1
            else:
                self.geometries[signature] = geometry
                self._geometry_bytes += size
        return candidate_id

    def _plans(self, result, source):
        if isinstance(result, dict):
            key = self.candidate(result, source=source)
            return [key] if key else []
        if hasattr(result, "snapshot"):
            return self._plans(result.snapshot, source)
        if isinstance(result, (list, tuple)):
            return [key for value in result for key in self._plans(value, source)]
        return []

    def emit(self, kind, **data):
        # Quota applies before candidate collection, bounding both memory and CPU.
        final_publication = (
            kind == "gallery" and data.get("reason") == "published_preview"
        )
        if len(self.events) >= self._max_events and not final_publication:
            self.coverage["dropped_events"] += 1
            return None
        seq = len(self.events) + 1
        span_id = data.pop("span_id", None)
        event = dict(
            seq=seq,
            elapsed_sec=round(time.monotonic() - self._started, 6),
            kind=kind,
            span_id=span_id,
        )
        if kind == "span_start":
            span_id = f"s{seq}"
            inputs = data.pop("inputs", {})
            command = inputs.get("command")
            if is_dataclass(command) and "input_specification" not in self.metadata:
                self.metadata["input_specification"] = dict(
                    board=json_value(asdict(command.board)),
                    optimizer=json_value(asdict(command.optimizer)),
                    piece_rows=[_piece_details(row) for row in command.piece_rows],
                    allow_piece_mirroring=command.allow_piece_mirroring,
                    search_round=command.search_round,
                )
            plan_inputs = []
            for name, value in inputs.items():
                if isinstance(value, dict) and "sheets" in value:
                    plan_inputs.extend(self._plans(value, data["name"]))
            safe = {
                k: json_value(v)
                for k, v in inputs.items()
                if k
                in (
                    "method_key",
                    "ordering_label",
                    "machine_type",
                    "time_limit_sec",
                    "max_attempts",
                    "search_round",
                    "width",
                    "height",
                    "kerf",
                    "board_w_cm",
                    "board_h_cm",
                    "kerf_cm",
                    "corner_only",
                    "operator",
                    "ordering",
                    "method",
                    "origin",
                    "validated",
                    "already_validated",
                    "assignment_options",
                )
            }
            for name in ("ordered_pieces", "pieces", "sources"):
                if name in inputs and isinstance(inputs[name], (list, tuple)):
                    safe[name + "_order"] = [
                        p.get("piece_instance_id") or p.get("id") for p in inputs[name]
                    ]
                    if self._expected_ids is None:
                        self._expected_ids = Counter(map(str, safe[name + "_order"]))
                    break
            entry = dict(
                span_id=span_id,
                start_seq=seq,
                end_seq=None,
                stop_reason=None,
                parent_span_id=data.get("parent_span_id"),
                name=data["name"],
                kind=data["span_kind"],
                inputs=safe,
                input_candidates=plan_inputs,
                output_candidates=[],
            )
            self.spans.append(entry)
            self._span_index[span_id] = entry
            event.update(
                span_id=span_id, **data, inputs=safe, candidate_ids=plan_inputs
            )
            if data["span_kind"] == "attempt":
                self.attempts.append(entry)
            if data["name"] not in self.coverage["observed_boundaries"]:
                self.coverage["observed_boundaries"].append(data["name"])
        elif kind == "span_end":
            entry = self._span_index.get(span_id)
            if entry:
                if data["stop_reason"] == "returned" and entry.get(
                    "reported_stop_reason"
                ):
                    data["stop_reason"] = entry["reported_stop_reason"]
                entry.update(
                    end_seq=seq,
                    stop_reason=data["stop_reason"],
                    elapsed_sec=round(
                        event["elapsed_sec"]
                        - self.events[entry["start_seq"] - 1]["elapsed_sec"],
                        6,
                    ),
                )
            event.update(json_value(data))
        elif kind in {"result", "generated"}:
            result = data.pop("result", None)
            ids = self._plans(result, data.get("name"))
            event.update(json_value(data), candidate_ids=ids)
            entry = self._span_index.get(span_id)
            if entry:
                entry["output_candidates"].extend(
                    k for k in ids if k not in entry["output_candidates"]
                )
                parent = next(iter(entry["input_candidates"]), None)
                for key in ids:
                    if (
                        key != parent
                        and not self.candidates[key]["parent_candidate_id"]
                    ):
                        self.candidates[key]["parent_candidate_id"] = parent
            if (
                isinstance(result, tuple)
                and len(result) == 2
                and isinstance(result[1], dict)
            ):
                event["diagnostics"] = json_value(result[1])
            elif (
                isinstance(result, tuple)
                and len(result) == 2
                and isinstance(result[1], str)
            ):
                event["reason"] = result[1]
                for key in ids:
                    self.candidates[key]["reasons"].append(
                        dict(seq=seq, reason=result[1], span_id=span_id)
                    )
            elif isinstance(result, dict):
                event["diagnostics"] = {
                    k: json_value(v)
                    for k, v in result.items()
                    if k.endswith("_diagnostics")
                }
            elif result is None:
                event["reason"] = "no_result"
            if data.get("name") in {
                "validate_plan",
                "placement_permission_errors",
                "manufacturing_export_rejection",
            }:
                event["validation_result"] = json_value(result)
        elif kind == "comparison":
            plans = data.pop("plans")
            ids = [self.candidate(p, source="comparison") for p in plans]
            keys = json_value(data.pop("keys"))
            flat = [_flat(k) for k in keys]
            order = sorted(range(len(keys)), key=lambda i: keys[i])
            criteria = (
                FINAL_CRITERIA
                if data.get("cutter_center_available")
                else INDUSTRIAL_CRITERIA
            )
            decisive = None
            if len(order) > 1:
                a, b = (flat[i] for i in order[:2])
                index = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
                decisive = (
                    criteria[index]
                    if index is not None and index < len(criteria)
                    else None
                )
            event.update(
                json_value(data),
                candidate_ids=ids,
                keys=keys,
                decisive_criterion=decisive,
                criteria=criteria,
                tie=decisive is None,
                ranked_candidate_ids=[ids[i] for i in order],
                adjacent_comparisons=[
                    dict(
                        winner=ids[a],
                        other=ids[b],
                        decisive_criterion=next(
                            (
                                criteria[i]
                                for i, (x, y) in enumerate(zip(flat[a], flat[b]))
                                if x != y and i < len(criteria)
                            ),
                            None,
                        ),
                    )
                    for a, b in zip(order, order[1:])
                ],
            )
            self.decisions.append(event)
        elif kind == "gallery":
            before = data.pop("before")
            after = data.pop("after")
            event.update(
                json_value(data),
                before=self._plans(before, "gallery"),
                after=self._plans(after, "gallery"),
            )
            event["removed"] = [k for k in event["before"] if k not in event["after"]]
            last_seq = self.gallery_history[-1]["seq"] if self.gallery_history else 0
            event["comparison_seqs"] = [
                e["seq"]
                for e in self.decisions
                if e["seq"] > last_seq
                and set(e["candidate_ids"]) & set(event["before"] + event["after"])
            ]
            self.gallery_history.append(event)
            self.final_gallery = [
                dict(
                    candidate_id=k,
                    geometry_fingerprint=self.candidates[k]["geometry_fingerprint"],
                )
                for k in event["after"]
            ]
        else:
            if kind == "stage_stop" and span_id in self._span_index:
                self._span_index[span_id]["reported_stop_reason"] = data.get("reason")
            plan = data.pop("plan", None)
            candidate_id = (
                self.candidate(plan, source=data.get("source"))
                if plan is not None
                else None
            )
            event.update(json_value(data))
            if candidate_id:
                event["candidate_id"] = candidate_id
                entry = self.candidates[candidate_id]
                if data.get("reason"):
                    entry["reasons"].append(
                        dict(seq=seq, reason=data["reason"], span_id=span_id)
                    )
                if data.get("status"):
                    entry["status"] = data["status"]
        self.events.append(event)
        return span_id if kind == "span_start" else seq

    def gallery(self, before, after, reason, **data):
        return self.emit("gallery", before=before, after=after, reason=reason, **data)

    def export(self):
        data = deepcopy(
            dict(
                **self.metadata,
                events=self.events,
                spans=self.spans,
                attempts=self.attempts,
                candidates=self.candidates,
                geometries=self.geometries,
                decisions=self.decisions,
                gallery_history=self.gallery_history,
                final_gallery=self.final_gallery,
                coverage_manifest=self.coverage,
            )
        )
        coverage = data["coverage_manifest"]
        open_spans = [s["span_id"] for s in data["spans"] if s["end_seq"] is None]
        coverage["unclosed_spans"] = open_spans
        if coverage["dropped_events"] or coverage["omitted_geometries"]:
            coverage["status"] = "TRUNCATED"
        elif coverage["observer_errors"] or open_spans or coverage["limitations"]:
            coverage["status"] = "PARTIAL"
        else:
            coverage["status"] = "COMPLETE"
        if coverage["status"] != "COMPLETE":
            data["events"].append(
                dict(
                    seq=len(data["events"]) + 1,
                    kind="evidence_loss",
                    span_id=None,
                    reason=coverage["status"],
                    dropped_events=coverage["dropped_events"],
                    omitted_geometries=coverage["omitted_geometries"],
                )
            )
        data = json_value(data)
        data["data_fingerprint"] = fingerprint(data)
        return data
