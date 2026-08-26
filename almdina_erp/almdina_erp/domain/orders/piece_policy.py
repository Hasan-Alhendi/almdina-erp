from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping


PIECE_TYPES = frozenset({"Regular", "Clipped Corner", "Special", "Extra"})
CLIPPED_CORNER_POSITIONS = frozenset(
    {"Top Right", "Top Left", "Bottom Right", "Bottom Left"}
)


class PiecePolicyError(ValueError):
    """Raised when a door-piece rule is violated."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ClippedCorner:
    position: str
    width_cm: float
    length_cm: float


@dataclass(frozen=True, slots=True)
class PieceGeometry:
    piece_type: str = "Regular"
    width_cm: float = 0
    length_cm: float = 0
    qty: int = 0
    allow_rotation: int = 0
    clipped_corner_position: str = ""
    clipped_corner_width_cm: float = 0
    clipped_corner_length_cm: float = 0
    edge_long_right: int = 0
    edge_long_left: int = 0
    edge_width_top: int = 0
    edge_width_bottom: int = 0
    edge_type: str = ""


@dataclass(frozen=True, slots=True)
class SpecialPrice:
    unit_price_usd: float = 0
    status: str = ""
    note: str = ""
    approved_by: str = ""
    approved_on: Any | None = None


@dataclass(frozen=True, slots=True)
class SpecialShapeDecision:
    documentation_status: str
    geometry_changed: bool
    pricing_basis_changed: bool
    protected_price_changed: bool
    safe_geometry_invalidation: bool
    requires_price_permission: bool
    reset_price: bool


def drawing_token(raw: Any) -> str:
    if raw in (None, ""):
        return ""
    if isinstance(raw, str):
        return raw
    return json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def resolve_clipped_corner(
    *,
    position: str | None,
    piece_width_cm: float,
    piece_length_cm: float,
    cut_width_cm: float,
    cut_length_cm: float,
) -> ClippedCorner:
    resolved_position = position or "Top Right"
    if resolved_position not in CLIPPED_CORNER_POSITIONS:
        raise PiecePolicyError("invalid_clipped_corner_position")

    width = float(cut_width_cm or 0)
    length = float(cut_length_cm or 0)
    piece_width = float(piece_width_cm or 0)
    piece_length = float(piece_length_cm or 0)

    if piece_width > 0 and piece_length > 0:
        if width <= 0:
            width = min(max(piece_width * 0.2, 1), piece_width * 0.45)
        if length <= 0:
            length = min(max(piece_length * 0.2, 1), piece_length * 0.45)
        if width >= piece_width:
            raise PiecePolicyError("clipped_corner_width_too_large")
        if length >= piece_length:
            raise PiecePolicyError("clipped_corner_length_too_large")

    return ClippedCorner(
        position=resolved_position,
        width_cm=width,
        length_cm=length,
    )


def geometry_changed(
    old: PieceGeometry | None,
    current: PieceGeometry,
    *,
    drawing_changed: bool,
) -> bool:
    if old is None:
        return False
    return bool(
        old.piece_type != current.piece_type
        or not _same_number(old.width_cm, current.width_cm)
        or not _same_number(old.length_cm, current.length_cm)
        or old.qty != current.qty
        or old.allow_rotation != current.allow_rotation
        or old.clipped_corner_position != current.clipped_corner_position
        or not _same_number(
            old.clipped_corner_width_cm,
            current.clipped_corner_width_cm,
        )
        or not _same_number(
            old.clipped_corner_length_cm,
            current.clipped_corner_length_cm,
        )
        or old.edge_long_right != current.edge_long_right
        or old.edge_long_left != current.edge_long_left
        or old.edge_width_top != current.edge_width_top
        or old.edge_width_bottom != current.edge_width_bottom
        or old.edge_type != current.edge_type
        or drawing_changed
    )


def pricing_basis_changed(
    old: PieceGeometry | None,
    current: PieceGeometry,
) -> bool:
    """Return whether fields that define the reviewed piece price changed.

    Drawing/documentation, edge banding and other geometric details are deliberately
    excluded. A reviewed price is invalidated only when the piece type, overall
    width, overall length or quantity changes.
    """

    if old is None:
        return False
    return bool(
        old.piece_type != current.piece_type
        or not _same_number(old.width_cm, current.width_cm)
        or not _same_number(old.length_cm, current.length_cm)
        or old.qty != current.qty
    )


def protected_price_changed(
    old: SpecialPrice | None,
    current: SpecialPrice,
) -> bool:
    if old is None:
        return bool(
            current.unit_price_usd
            or current.status == "Approved"
            or current.note
            or current.approved_by
            or current.approved_on
        )
    return bool(
        not _same_number(old.unit_price_usd, current.unit_price_usd)
        or old.status != current.status
        or old.note != current.note
        or old.approved_by != current.approved_by
        or old.approved_on != current.approved_on
    )


def evaluate_special_shape(
    *,
    old_geometry: PieceGeometry | None,
    current_geometry: PieceGeometry,
    old_price: SpecialPrice | None,
    current_price: SpecialPrice,
    drawing_changed: bool,
    drawing_has_elements: bool,
    default_edge_changed: bool,
    approval_action: bool,
) -> SpecialShapeDecision:
    changed_geometry = geometry_changed(
        old_geometry,
        current_geometry,
        drawing_changed=drawing_changed,
    )
    # Keep the legacy input in the policy boundary because callers may still need to
    # report header edge changes as geometry context. It must not invalidate price.
    _ = default_edge_changed
    changed_pricing_basis = pricing_basis_changed(
        old_geometry,
        current_geometry,
    )
    changed_protected_price = protected_price_changed(old_price, current_price)
    safe_invalidation = bool(
        changed_pricing_basis
        and current_price.status in {"", "Estimated", "Not Applicable"}
        and not current_price.unit_price_usd
        and not current_price.note
        and not current_price.approved_by
        and not current_price.approved_on
    )
    documentation_status = (
        "Documented"
        if current_geometry.piece_type == "Special" and drawing_has_elements
        else (
            "Needs Documentation"
            if current_geometry.piece_type == "Special"
            else "Not Required"
        )
    )
    return SpecialShapeDecision(
        documentation_status=documentation_status,
        geometry_changed=changed_geometry,
        pricing_basis_changed=changed_pricing_basis,
        protected_price_changed=changed_protected_price,
        safe_geometry_invalidation=safe_invalidation,
        requires_price_permission=bool(
            changed_protected_price
            and not approval_action
            and not safe_invalidation
        ),
        reset_price=bool(changed_pricing_basis and not approval_action),
    )


def reset_price_values(piece_type: str) -> dict[str, Any]:
    return {
        "special_shape_custom_unit_price_usd": 0,
        "special_shape_price_status": (
            "Estimated" if piece_type == "Special" else "Not Applicable"
        ),
        "special_shape_price_note": "",
        "special_shape_price_approved_by": "",
        "special_shape_price_approved_on": None,
        "clipped_corner_edge_price_usd": 0,
        "clipped_corner_edge_price_status": (
            "Unpriced" if piece_type == "Clipped Corner" else "Unpriced"
        ),
        "clipped_corner_edge_price_note": "",
        "clipped_corner_edge_price_set_by": "",
        "clipped_corner_edge_price_set_on": None,
    }


def pending_custom_edge_price_labels(pieces: Any) -> tuple[str, ...]:
    """Return Arabic labels for special/cut-corner rows still missing edge prices."""

    pending: list[str] = []
    for index, piece in enumerate(pieces or [], start=1):
        if isinstance(piece, Mapping):
            piece_type = str(piece.get("piece_type") or "Regular")
            special_status = str(piece.get("special_shape_price_status") or "")
            clipped_status = str(piece.get("clipped_corner_edge_price_status") or "Unpriced")
        else:
            piece_type = str(getattr(piece, "piece_type", None) or "Regular")
            special_status = str(getattr(piece, "special_shape_price_status", None) or "")
            clipped_status = str(
                getattr(piece, "clipped_corner_edge_price_status", None) or "Unpriced"
            )
        if piece_type == "Special" and special_status != "Approved":
            pending.append(f"درفة خاصة رقم {index}")
        elif piece_type == "Clipped Corner" and clipped_status != "Priced":
            pending.append(f"درفة زاوية مقصوصة {index}")
    return tuple(pending)


def _same_number(first: float, second: float) -> bool:
    return math.isclose(
        float(first or 0),
        float(second or 0),
        rel_tol=0,
        abs_tol=1e-9,
    )


__all__ = [
    "CLIPPED_CORNER_POSITIONS",
    "PIECE_TYPES",
    "ClippedCorner",
    "PieceGeometry",
    "PiecePolicyError",
    "SpecialPrice",
    "SpecialShapeDecision",
    "drawing_token",
    "evaluate_special_shape",
    "geometry_changed",
    "pricing_basis_changed",
    "protected_price_changed",
    "pending_custom_edge_price_labels",
    "reset_price_values",
    "resolve_clipped_corner",
]
