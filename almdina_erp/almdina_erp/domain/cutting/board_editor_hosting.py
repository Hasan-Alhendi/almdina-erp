"""Hosting tree helpers for the board editor sidebar.

Uses the existing Glass opening host link ``glass_host_piece_id``. Host
identity is the placed piece ``id`` already proven by nesting/import — never
row order and never layer-name inference.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
    GLASS_HOST_PIECE_ID,
    MAX_NESTING_DEPTH,
)


def piece_placement_id(piece: Mapping[str, Any]) -> int | None:
    """Return the stable-within-plan placement id, or None when absent/invalid."""

    try:
        return int(piece["id"])
    except (KeyError, TypeError, ValueError):
        return None


def declared_host_piece_id(piece: Mapping[str, Any]) -> int | None:
    """Return the declared Glass host placement id when present and valid."""

    raw = piece.get(GLASS_HOST_PIECE_ID)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _would_create_cycle(
    proposed_host_by_guest: Mapping[int, int],
    *,
    guest_id: int,
    host_id: int,
) -> bool:
    """True when adding guest→host closes a cycle in the proposed parent map."""

    current: int | None = host_id
    seen: set[int] = set()
    while current is not None:
        if current == guest_id:
            return True
        if current in seen:
            return True
        seen.add(current)
        current = proposed_host_by_guest.get(current)
    return False


def hosting_forest_for_pieces(
    pieces: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a hosting forest and report unresolved host links without guessing.

    Roots are pieces without a host. Guests nest under the host whose placement
    ``id`` matches ``glass_host_piece_id``. Missing hosts, self-hosts, and cycles
    stay unresolved; they are never attached by label, layer, or row position.
    """

    by_id: dict[int, Mapping[str, Any]] = {}
    order: list[int] = []
    for piece in pieces:
        piece_id = piece_placement_id(piece)
        if piece_id is None or piece_id in by_id:
            continue
        by_id[piece_id] = piece
        order.append(piece_id)

    proposed_host_by_guest: dict[int, int] = {}
    unresolved: list[dict[str, Any]] = []

    for piece_id in order:
        piece = by_id[piece_id]
        host_id = declared_host_piece_id(piece)
        if host_id is None:
            continue
        if host_id not in by_id:
            unresolved.append(
                {
                    "piece_id": piece_id,
                    "declared_host_piece_id": host_id,
                    "reason": "missing_host",
                }
            )
            continue
        if host_id == piece_id:
            unresolved.append(
                {
                    "piece_id": piece_id,
                    "declared_host_piece_id": host_id,
                    "reason": "self_host",
                }
            )
            continue
        if _would_create_cycle(
            proposed_host_by_guest,
            guest_id=piece_id,
            host_id=host_id,
        ):
            unresolved.append(
                {
                    "piece_id": piece_id,
                    "declared_host_piece_id": host_id,
                    "reason": "host_cycle",
                }
            )
            continue
        proposed_host_by_guest[piece_id] = host_id

    children: dict[int, list[int]] = {piece_id: [] for piece_id in order}
    roots: list[int] = []
    for piece_id in order:
        host_id = proposed_host_by_guest.get(piece_id)
        if host_id is None:
            roots.append(piece_id)
            continue
        children[host_id].append(piece_id)

    def build_node(piece_id: int, *, depth: int, trail: frozenset[int]) -> dict[str, Any]:
        piece = by_id[piece_id]
        guests: list[dict[str, Any]] = []
        for guest_id in children.get(piece_id, []):
            if guest_id in trail:
                unresolved.append(
                    {
                        "piece_id": guest_id,
                        "declared_host_piece_id": piece_id,
                        "reason": "host_cycle",
                    }
                )
                continue
            guests.append(
                build_node(guest_id, depth=depth + 1, trail=trail | {piece_id})
            )
        return {
            "piece_id": piece_id,
            "piece_instance_id": str(piece.get("piece_instance_id") or "").strip()
            or None,
            "label": str(piece.get("label") or ""),
            "depth": depth,
            "glass_host_piece_id": declared_host_piece_id(piece),
            "within_max_depth": depth <= MAX_NESTING_DEPTH,
            "guests": guests,
        }

    return {
        "roots": [
            build_node(piece_id, depth=0, trail=frozenset()) for piece_id in roots
        ],
        "unresolved_host_links": unresolved,
        "max_nesting_depth": MAX_NESTING_DEPTH,
        "host_field": GLASS_HOST_PIECE_ID,
    }


__all__ = [
    "declared_host_piece_id",
    "hosting_forest_for_pieces",
    "piece_placement_id",
]
