"""Explicit compatibility boundary for physical-execution plan snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .offcut_policy import PhysicalExecutionProjection, physical_execution_projection


PHYSICAL_EXECUTION_CONTRACT = "physical_execution_contract"
PHYSICAL_EXECUTION_CONTRACT_VERSION = 1


class PhysicalExecutionContractError(ValueError):
    pass


def snapshot_pieces(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(piece)
        for sheet in (snapshot.get("sheets") or [])
        if isinstance(sheet, Mapping)
        for piece in (sheet.get("pieces") or [])
        if isinstance(piece, Mapping)
    ]


def is_legacy_physical_execution_snapshot(snapshot: Mapping[str, Any]) -> bool:
    """Identify only pre-contract snapshots whose physical identities are absent.

    A partial set of identities is corruption, not legacy. New snapshots always
    carry the marker, so absence is never used to weaken their validation.
    """

    marker = snapshot.get(PHYSICAL_EXECUTION_CONTRACT)
    if marker is not None:
        if marker != PHYSICAL_EXECUTION_CONTRACT_VERSION:
            raise PhysicalExecutionContractError("unsupported_physical_execution_contract")
        return False
    pieces = snapshot_pieces(snapshot)
    identities = [str(piece.get("piece_instance_id") or "").strip() for piece in pieces]
    return bool(pieces) and not any(identities)


def physical_execution_for_snapshot(
    snapshot: Mapping[str, Any],
) -> PhysicalExecutionProjection | None:
    """Return strict execution facts, or ``None`` for an immutable legacy plan."""

    if is_legacy_physical_execution_snapshot(snapshot):
        return None
    pieces = snapshot_pieces(snapshot)
    if not pieces:
        return None
    return physical_execution_projection(pieces)


def with_physical_execution_contract(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Mark a newly created snapshot without mutating a caller-owned object."""

    result = dict(snapshot)
    result[PHYSICAL_EXECUTION_CONTRACT] = PHYSICAL_EXECUTION_CONTRACT_VERSION
    return result


__all__ = [
    "PHYSICAL_EXECUTION_CONTRACT",
    "PHYSICAL_EXECUTION_CONTRACT_VERSION",
    "PhysicalExecutionContractError",
    "is_legacy_physical_execution_snapshot",
    "physical_execution_for_snapshot",
    "with_physical_execution_contract",
]
