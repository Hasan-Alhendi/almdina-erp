"""Safety review for small pieces on a generated or uploaded plan.

Blocking stays off until an approved size limit and a support distance are
both supplied. Distance from the board edge is not, by itself, a reason to
reject a placement: a piece against the edge can still be supported by the
board or by a neighbour. No measurement is invented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .primitives import num


@dataclass(frozen=True, slots=True)
class SmallPieceSafetyPolicy:
    """Approved criteria. ``enabled`` alone does not block production."""

    enabled: bool = False
    max_area_m2: float | None = None
    support_gap_cm: float | None = None


def blocking_active(policy: SmallPieceSafetyPolicy) -> bool:
    """True only when production blocking has a complete approved rule."""

    return bool(
        policy.enabled
        and policy.max_area_m2 is not None
        and policy.max_area_m2 > 0
        and policy.support_gap_cm is not None
        and policy.support_gap_cm > 0
    )


def safety_issues(
    plan: Mapping[str, Any],
    policy: SmallPieceSafetyPolicy,
) -> list[str]:
    """Review a generated plan and an uploaded plan with the same rule.

    An inactive policy returns no issues, including for a piece that touches
    the board edge.
    """

    if not blocking_active(policy):
        return []
    limit = float(policy.max_area_m2 or 0)
    support = float(policy.support_gap_cm or 0)
    issues: list[str] = []
    for sheet in plan.get("sheets") or []:
        pieces = list(sheet.get("pieces") or [])
        for piece in pieces:
            area = num(piece.get("w")) * num(piece.get("h")) / 10000
            if area <= 0 or area > limit:
                continue
            if _has_support(piece, pieces, support):
                continue
            issues.append(
                f"Piece {piece.get('label') or piece.get('id')} on sheet "
                f"{sheet.get('sheet_no')} has no approved support within "
                f"{support:g} cm."
            )
    return issues


def _has_support(
    piece: Mapping[str, Any],
    pieces: list[Mapping[str, Any]],
    support_gap_cm: float,
) -> bool:
    own_id = piece.get("id")
    rect = _rect(piece)
    for other in pieces:
        if other.get("id") == own_id:
            continue
        if _separated_by_at_most(_rect(other), rect, support_gap_cm):
            return True
    return False


def _rect(piece: Mapping[str, Any]) -> dict[str, float]:
    return {
        "x": num(piece.get("x")),
        "y": num(piece.get("y")),
        "w": num(piece.get("w")),
        "h": num(piece.get("h")),
    }


def _separated_by_at_most(
    first: Mapping[str, float],
    second: Mapping[str, float],
    limit: float,
) -> bool:
    gap_x = max(
        0.0,
        max(first["x"], second["x"])
        - min(first["x"] + first["w"], second["x"] + second["w"]),
    )
    gap_y = max(
        0.0,
        max(first["y"], second["y"])
        - min(first["y"] + first["h"], second["y"] + second["h"]),
    )
    if gap_x > 1e-6 and gap_y > 1e-6:
        return False
    return max(gap_x, gap_y) <= limit


__all__ = [
    "SmallPieceSafetyPolicy",
    "blocking_active",
    "safety_issues",
]
