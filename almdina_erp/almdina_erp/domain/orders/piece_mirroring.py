"""Order-level permission to mirror pieces when nesting.

The stored values are stable identifiers. Missing and blank values mean the
historical rule: mirroring is not allowed. This module does not transform
geometry; placement code must keep ignoring the policy until a later phase.
"""

from __future__ import annotations

from typing import Any


NOT_ALLOWED = "not_allowed"
ALLOWED = "allowed"
_CANONICAL = frozenset({NOT_ALLOWED, ALLOWED})


class PieceMirroringPolicyError(ValueError):
    """The order carried a piece-mirroring value outside the product contract."""

    def __init__(self) -> None:
        super().__init__("invalid_allow_piece_mirroring")


def normalize_allow_piece_mirroring(value: Any) -> str:
    """Return the canonical stored value, or reject anything else.

    ``None`` and blank text are the legacy absence of the field and stay
    ``not_allowed``. Booleans, numbers, and unknown text are invalid.
    """

    if value is None:
        return NOT_ALLOWED
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return NOT_ALLOWED
        if text in _CANONICAL:
            return text
    raise PieceMirroringPolicyError()


def piece_mirroring_allowed(value: Any) -> bool:
    """True only for the canonical allowed value."""

    return normalize_allow_piece_mirroring(value) == ALLOWED


__all__ = [
    "ALLOWED",
    "NOT_ALLOWED",
    "PieceMirroringPolicyError",
    "normalize_allow_piece_mirroring",
    "piece_mirroring_allowed",
]
