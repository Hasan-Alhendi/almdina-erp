"""Order-level permission to mirror pieces when nesting.

The checkbox stores ``0`` when mirroring is not allowed and ``1`` when it is.
Missing and blank values stay ``0``, which is the historical rule. This module
does not transform geometry; placement code must keep ignoring the policy
until a later phase.
"""

from __future__ import annotations

from typing import Any


NOT_ALLOWED = 0
ALLOWED = 1
_UNCHECKED = frozenset({"", "0", "false", "not_allowed"})
_CHECKED = frozenset({"1", "true", "allowed"})


class PieceMirroringPolicyError(ValueError):
    """The order carried a piece-mirroring value outside the product contract."""

    def __init__(self) -> None:
        super().__init__("invalid_allow_piece_mirroring")


def normalize_allow_piece_mirroring(value: Any) -> int:
    """Return ``0`` or ``1``, or reject anything else.

    ``None`` and blank text are the legacy absence of the field and stay
    unchecked. The earlier text tokens are accepted only so a value saved
    before the checkbox still means the same permission, then stored as ``0``
    or ``1``.
    """

    if value is None:
        return NOT_ALLOWED
    if isinstance(value, bool):
        return ALLOWED if value else NOT_ALLOWED
    if isinstance(value, int):
        if value in (NOT_ALLOWED, ALLOWED):
            return value
        raise PieceMirroringPolicyError()
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _UNCHECKED:
            return NOT_ALLOWED
        if text in _CHECKED:
            return ALLOWED
    raise PieceMirroringPolicyError()


def piece_mirroring_allowed(value: Any) -> bool:
    """True only when the checkbox is checked."""

    return normalize_allow_piece_mirroring(value) == ALLOWED


__all__ = [
    "ALLOWED",
    "NOT_ALLOWED",
    "PieceMirroringPolicyError",
    "normalize_allow_piece_mirroring",
    "piece_mirroring_allowed",
]
