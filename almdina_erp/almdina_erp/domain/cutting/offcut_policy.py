"""Canonical OFFCUT classification and costing policy.

The policy is deliberately framework independent. Frappe documents, DXF
importers, presenters and print builders consume its projections instead of
re-implementing the customer/factory matrix in each surface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ResourceKind(StrEnum):
    FULL_BOARD = "FULL_BOARD"
    OFFCUT = "OFFCUT"


class Party(StrEnum):
    CUSTOMER = "CUSTOMER"
    FACTORY = "FACTORY"
    UNASSIGNED = "UNASSIGNED"


class OffcutBusinessState(StrEnum):
    UNASSIGNED = "UNASSIGNED"
    CUSTOMER_FACTORY = "CUSTOMER_FACTORY"
    CUSTOMER_CUSTOMER = "CUSTOMER_CUSTOMER"
    FACTORY_FACTORY = "FACTORY_FACTORY"


class OffcutPolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OffcutDecision:
    resource_kind: ResourceKind
    source_party: Party
    execution_party: Party

    @property
    def is_offcut(self) -> bool:
        return self.resource_kind is ResourceKind.OFFCUT

    @property
    def is_resolved(self) -> bool:
        return (
            self.is_offcut
            and self.source_party is not Party.UNASSIGNED
            and self.execution_party is not Party.UNASSIGNED
        )

    @property
    def enters_worker_queues(self) -> bool:
        return self.execution_party is Party.FACTORY

    @property
    def consumes_full_board(self) -> bool:
        return self.resource_kind is ResourceKind.FULL_BOARD


RESOLVED_OFFCUT_STATES = frozenset(
    {
        (Party.CUSTOMER, Party.FACTORY),
        (Party.CUSTOMER, Party.CUSTOMER),
        (Party.FACTORY, Party.FACTORY),
    }
)

_DECISION_BY_BUSINESS_STATE = {
    OffcutBusinessState.UNASSIGNED: (Party.UNASSIGNED, Party.UNASSIGNED),
    OffcutBusinessState.CUSTOMER_FACTORY: (Party.CUSTOMER, Party.FACTORY),
    OffcutBusinessState.CUSTOMER_CUSTOMER: (Party.CUSTOMER, Party.CUSTOMER),
    OffcutBusinessState.FACTORY_FACTORY: (Party.FACTORY, Party.FACTORY),
}
_BUSINESS_STATE_BY_DECISION = {
    decision: state for state, decision in _DECISION_BY_BUSINESS_STATE.items()
}
_BUSINESS_STATE_LABELS = {
    OffcutBusinessState.UNASSIGNED: "غير محدد",
    OffcutBusinessState.CUSTOMER_FACTORY: "فضلة من الزبون — تنفيذ في المعمل",
    OffcutBusinessState.CUSTOMER_CUSTOMER: "فضلة من الزبون — تنفيذ عند الزبون",
    OffcutBusinessState.FACTORY_FACTORY: "فضلة من المعمل — تنفيذ في المعمل",
}
_SUMMARY_LABELS = {
    OffcutBusinessState.CUSTOMER_FACTORY: "من الزبون / في المعمل",
    OffcutBusinessState.CUSTOMER_CUSTOMER: "من الزبون / عند الزبون",
    OffcutBusinessState.FACTORY_FACTORY: "من المعمل / في المعمل",
    OffcutBusinessState.UNASSIGNED: "غير محدد",
}


def _party(value: Any, *, default: Party = Party.UNASSIGNED) -> Party:
    text = str(value or "").strip().upper()
    if not text:
        return default
    try:
        return Party(text)
    except ValueError as exc:
        raise OffcutPolicyError(f"unsupported_offcut_party:{text}") from exc


def resource_kind_from_value(value: Any = ResourceKind.FULL_BOARD) -> ResourceKind:
    """Return the explicit resource kind; legacy absence means FULL_BOARD."""

    text = str(value or ResourceKind.FULL_BOARD).strip().upper()
    try:
        return ResourceKind(text)
    except ValueError as exc:
        raise OffcutPolicyError(f"unsupported_resource_kind:{value}") from exc


def decision_from_values(
    resource_kind: Any = ResourceKind.FULL_BOARD,
    source_party: Any = Party.UNASSIGNED,
    execution_party: Any = Party.UNASSIGNED,
) -> OffcutDecision:
    kind = resource_kind_from_value(resource_kind)

    source = _party(source_party)
    execution = _party(execution_party)
    if kind is ResourceKind.FULL_BOARD:
        # Legacy rows may still contain stale OFFCUT metadata. FULL_BOARD owns no
        # OFFCUT business state, so canonical reads/saves neutralize it instead
        # of carrying an invalid combination forward.
        return OffcutDecision(kind, Party.UNASSIGNED, Party.UNASSIGNED)
    if source is Party.UNASSIGNED or execution is Party.UNASSIGNED:
        return OffcutDecision(kind, Party.UNASSIGNED, Party.UNASSIGNED)
    decision = OffcutDecision(kind, source, execution)
    if (source, execution) not in RESOLVED_OFFCUT_STATES:
        raise OffcutPolicyError("factory_source_customer_execution_forbidden")
    return decision


def decision_from_business_state(
    resource_kind: Any,
    business_state: Any,
) -> OffcutDecision:
    try:
        state = OffcutBusinessState(
            str(business_state or OffcutBusinessState.UNASSIGNED).strip().upper()
        )
    except ValueError as exc:
        raise OffcutPolicyError(
            f"unsupported_offcut_business_state:{business_state}"
        ) from exc

    decision = decision_from_values(
        resource_kind,
        *_DECISION_BY_BUSINESS_STATE[state],
    )
    if not decision.is_offcut and state is not OffcutBusinessState.UNASSIGNED:
        raise OffcutPolicyError("full_board_offcut_classification_forbidden")
    return decision


def business_state_from_decision(decision: OffcutDecision) -> OffcutBusinessState:
    if not decision.is_offcut or not decision.is_resolved:
        return OffcutBusinessState.UNASSIGNED
    try:
        return _BUSINESS_STATE_BY_DECISION[
            (decision.source_party, decision.execution_party)
        ]
    except KeyError as exc:
        raise OffcutPolicyError("unsupported_offcut_business_state") from exc


def business_state_from_values(
    resource_kind: Any,
    source_party: Any = Party.UNASSIGNED,
    execution_party: Any = Party.UNASSIGNED,
) -> OffcutBusinessState:
    return business_state_from_decision(
        decision_from_values(resource_kind, source_party, execution_party)
    )


def business_state_options() -> list[dict[str, str]]:
    return [
        {"value": state.value, "label": _BUSINESS_STATE_LABELS[state]}
        for state in OffcutBusinessState
    ]


def offcut_assignment_projection(piece: dict[str, Any]) -> dict[str, Any]:
    decision = decision_from_piece(piece)
    if not decision.is_offcut:
        raise OffcutPolicyError("offcut_assignment_requires_offcut_piece")
    state = business_state_from_decision(decision)
    return {
        "piece_instance_id": str(piece.get("piece_instance_id") or "").strip(),
        "piece_label": str(
            piece.get("label") or piece.get("piece_label") or ""
        ).strip(),
        "business_state": state.value,
        "business_state_label": _BUSINESS_STATE_LABELS[state],
        "source_party": decision.source_party.value,
        "execution_party": decision.execution_party.value,
    }


def offcut_summary(pieces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = {state: 0 for state in OffcutBusinessState}
    for piece in pieces:
        decision = decision_from_piece(piece)
        if decision.is_offcut:
            counts[business_state_from_decision(decision)] += 1
    order = (
        OffcutBusinessState.CUSTOMER_FACTORY,
        OffcutBusinessState.CUSTOMER_CUSTOMER,
        OffcutBusinessState.FACTORY_FACTORY,
        OffcutBusinessState.UNASSIGNED,
    )
    return [
        {
            "business_state": state.value,
            "label": _SUMMARY_LABELS[state],
            "count": counts[state],
        }
        for state in order
    ]


def decision_from_piece(piece: dict[str, Any]) -> OffcutDecision:
    return decision_from_values(
        piece.get("resource_kind"),
        piece.get("offcut_source_party"),
        piece.get("offcut_execution_party"),
    )


def validate_source_resource_homogeneity(
    sources: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> None:
    """Reject a physical source that mixes full-board and OFFCUT pieces."""
    for source in sources:
        pieces = list(source.get("pieces") or [])
        kinds = {decision_from_piece(piece).resource_kind for piece in pieces}
        if len(kinds) > 1:
            raise OffcutPolicyError("mixed_full_board_offcut_source")


def canonicalize_snapshot_sources(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Backfill source projections for snapshots created before OFFCUT fields.

    Piece classification is authoritative. A source containing only OFFCUT
    pieces is an OFFCUT projection; mixed/empty sources remain full-board
    projections for legacy compatibility.
    """
    for sheet in snapshot.get("sheets") or []:
        pieces = list(sheet.get("pieces") or [])
        if not pieces:
            continue
        decisions = [decision_from_piece(piece) for piece in pieces]
        if not all(decision.is_offcut for decision in decisions):
            sheet["offcut_source_party"] = Party.UNASSIGNED.value
            sheet["offcut_execution_party"] = Party.UNASSIGNED.value
            continue
        sheet["resource_kind"] = ResourceKind.OFFCUT.value
        source_projection = (
            decisions[0]
            if all(decision == decisions[0] for decision in decisions)
            else OffcutDecision(
                ResourceKind.OFFCUT,
                Party.UNASSIGNED,
                Party.UNASSIGNED,
            )
        )
        sheet["offcut_source_party"] = source_projection.source_party.value
        sheet["offcut_execution_party"] = source_projection.execution_party.value
    return snapshot


def _nonnegative_number(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, number)


def canonicalize_snapshot_allocation(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Project new-board allocation independently from physical-source identity.

    ``sheet_no`` remains the stable physical source reference used to associate
    pieces with their source. ``full_board_no`` is a separate semantic sequence
    assigned only to resources that actually consume a new full board. OFFCUT
    therefore never needs a magic sheet number and never creates a numbering gap.

    ``used_area_m2`` keeps its existing meaning (all physical pieces). The
    additional ``full_board_used_area_m2`` isolates material cut from new boards
    so OFFCUT area cannot reduce new-board waste.
    """

    canonicalize_snapshot_sources(snapshot)
    sheets = list(snapshot.get("sheets") or [])

    full_board_count = 0
    full_board_used_area_m2 = 0.0
    full_board_piece_areas_complete = True

    for sheet in sheets:
        kind = resource_kind_from_value(sheet.get("resource_kind"))
        if kind is ResourceKind.FULL_BOARD:
            full_board_count += 1
            sheet["full_board_no"] = full_board_count
            for piece in sheet.get("pieces") or []:
                if "area_m2" not in piece or piece.get("area_m2") is None:
                    full_board_piece_areas_complete = False
                    continue
                full_board_used_area_m2 += _nonnegative_number(piece.get("area_m2"))
        else:
            sheet["full_board_no"] = None

    snapshot["required_full_boards"] = full_board_count

    # The imported/system snapshots normally carry piece areas. Fail closed for
    # legacy snapshots that do not: preserve their historical waste instead of
    # inventing an area from dimensions or bounding boxes.
    if full_board_count == 0:
        snapshot["full_board_used_area_m2"] = 0.0
        if "total_board_area_m2" in snapshot:
            snapshot["total_board_area_m2"] = 0.0
        if "waste_area_m2" in snapshot:
            snapshot["waste_area_m2"] = 0.0
    elif full_board_piece_areas_complete:
        snapshot["full_board_used_area_m2"] = full_board_used_area_m2
        if "total_board_area_m2" in snapshot:
            total_board_area_m2 = _nonnegative_number(
                snapshot.get("total_board_area_m2")
            )
            snapshot["waste_area_m2"] = max(
                0.0,
                total_board_area_m2 - full_board_used_area_m2,
            )

    return snapshot


def preserve_offcut_classification(
    snapshot: dict[str, Any],
    previous_pieces: list[dict[str, Any]],
) -> dict[str, Any]:
    """Preserve business state only for the same confidently matched identity."""

    previous = {
        str(piece.get("piece_instance_id") or "").strip(): decision_from_piece(piece)
        for piece in previous_pieces
        if str(piece.get("piece_instance_id") or "").strip()
    }
    for sheet in snapshot.get("sheets") or []:
        for piece in sheet.get("pieces") or []:
            current = decision_from_piece(piece)
            if not current.is_offcut:
                piece["offcut_source_party"] = Party.UNASSIGNED.value
                piece["offcut_execution_party"] = Party.UNASSIGNED.value
                continue
            identity = str(piece.get("piece_instance_id") or "").strip()
            old = previous.get(identity)
            preserved = (
                old
                if old and old.is_offcut
                else OffcutDecision(
                    ResourceKind.OFFCUT,
                    Party.UNASSIGNED,
                    Party.UNASSIGNED,
                )
            )
            piece["offcut_source_party"] = preserved.source_party.value
            piece["offcut_execution_party"] = preserved.execution_party.value
    return canonicalize_snapshot_sources(snapshot)


def validate_piece_collection(pieces: list[dict[str, Any]]) -> None:
    identities: set[str] = set()
    for piece in pieces:
        identity = str(piece.get("piece_instance_id") or "").strip()
        if not identity:
            raise OffcutPolicyError("piece_instance_id_required")
        if identity in identities:
            raise OffcutPolicyError(f"duplicate_piece_instance_id:{identity}")
        identities.add(identity)
        decision_from_piece(piece)


def source_summary(pieces: list[dict[str, Any]]) -> dict[str, int]:
    """Return board/queue counts from the same policy used by costing/UI."""
    validate_piece_collection(pieces)
    return {
        "piece_count": len(pieces),
        "full_board_piece_count": sum(
            decision_from_piece(piece).consumes_full_board for piece in pieces
        ),
        "offcut_piece_count": sum(
            decision_from_piece(piece).is_offcut for piece in pieces
        ),
        "factory_execution_piece_count": sum(
            decision_from_piece(piece).enters_worker_queues for piece in pieces
        ),
    }


def presentation_label(
    decision: OffcutDecision, *, full_board_number: int | None = None
) -> str:
    if decision.is_offcut:
        return "نقص"
    return f"لوح {full_board_number}" if full_board_number is not None else "لوح"


__all__ = [
    "canonicalize_snapshot_allocation",
    "canonicalize_snapshot_sources",
    "business_state_from_decision",
    "business_state_from_values",
    "business_state_options",
    "decision_from_business_state",
    "OffcutDecision",
    "OffcutBusinessState",
    "OffcutPolicyError",
    "offcut_assignment_projection",
    "offcut_summary",
    "Party",
    "RESOLVED_OFFCUT_STATES",
    "ResourceKind",
    "decision_from_piece",
    "decision_from_values",
    "presentation_label",
    "preserve_offcut_classification",
    "resource_kind_from_value",
    "source_summary",
    "validate_source_resource_homogeneity",
    "validate_piece_collection",
]
