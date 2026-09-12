"""Canonical OFFCUT classification and costing policy.

The policy is deliberately framework independent. Frappe documents, DXF
importers, presenters and print builders consume its projections instead of
re-implementing the customer/factory matrix in each surface.
"""

from __future__ import annotations

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
        return self.is_offcut and self.source_party is not Party.UNASSIGNED and self.execution_party is not Party.UNASSIGNED

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


def _party(value: Any, *, default: Party = Party.UNASSIGNED) -> Party:
    text = str(value or "").strip().upper()
    if not text:
        return default
    try:
        return Party(text)
    except ValueError as exc:
        raise OffcutPolicyError(f"unsupported_offcut_party:{text}") from exc


def decision_from_values(
    resource_kind: Any = ResourceKind.FULL_BOARD,
    source_party: Any = Party.UNASSIGNED,
    execution_party: Any = Party.UNASSIGNED,
) -> OffcutDecision:
    try:
        kind = ResourceKind(str(resource_kind or ResourceKind.FULL_BOARD).strip().upper())
    except ValueError as exc:
        raise OffcutPolicyError(f"unsupported_resource_kind:{resource_kind}") from exc

    source = _party(source_party)
    execution = _party(execution_party)
    decision = OffcutDecision(kind, source, execution)
    if not decision.is_offcut:
        return decision
    if (source, execution) not in RESOLVED_OFFCUT_STATES and not (
        source is Party.UNASSIGNED or execution is Party.UNASSIGNED
    ):
        raise OffcutPolicyError("factory_source_customer_execution_forbidden")
    return decision


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
        kinds = {
            decision_from_piece(piece).resource_kind
            for piece in pieces
        }
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
        if not pieces or not all(decision_from_piece(piece).is_offcut for piece in pieces):
            continue
        sheet["resource_kind"] = ResourceKind.OFFCUT.value
        sources = {str(piece.get("offcut_source_party") or Party.UNASSIGNED.value).upper() for piece in pieces}
        executions = {str(piece.get("offcut_execution_party") or Party.UNASSIGNED.value).upper() for piece in pieces}
        sheet["offcut_source_party"] = next(iter(sources)) if len(sources) == 1 else Party.UNASSIGNED.value
        sheet["offcut_execution_party"] = next(iter(executions)) if len(executions) == 1 else Party.UNASSIGNED.value
    return snapshot


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


def presentation_label(decision: OffcutDecision, *, full_board_number: int | None = None) -> str:
    if decision.is_offcut:
        return "نقص"
    return f"لوح {full_board_number}" if full_board_number is not None else "لوح"


__all__ = [
    "canonicalize_snapshot_sources",
    "OffcutDecision",
    "OffcutPolicyError",
    "Party",
    "RESOLVED_OFFCUT_STATES",
    "ResourceKind",
    "decision_from_piece",
    "decision_from_values",
    "presentation_label",
    "source_summary",
    "validate_source_resource_homogeneity",
    "validate_piece_collection",
]
