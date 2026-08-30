from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any


MANUFACTURING_REQUIREMENTS_SCHEMA_VERSION = 1
MANUFACTURING_REQUIREMENTS_UNIT = "cm"
_CUT_DIMENSION_QUANTUM = Decimal("0.001")


class ManufacturingRequirementsError(ValueError):
    """Raised when manufacturing cut requirements cannot be trusted."""


def require_cut_dimension_cm(value: Any, *, fieldname: str) -> float:
    """Return one persisted manufacturing dimension, failing closed if invalid."""

    if value is None or isinstance(value, bool):
        raise ManufacturingRequirementsError(
            f"{fieldname} must contain a persisted positive cut dimension."
        )
    text = str(value).strip()
    if not text:
        raise ManufacturingRequirementsError(
            f"{fieldname} must contain a persisted positive cut dimension."
        )
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ManufacturingRequirementsError(
            f"{fieldname} must contain a persisted positive cut dimension."
        ) from exc
    if not number.is_finite() or number <= 0:
        raise ManufacturingRequirementsError(
            f"{fieldname} must contain a persisted positive cut dimension."
        )
    return float(number.quantize(_CUT_DIMENSION_QUANTUM))


def _positive_int(value: Any, *, fieldname: str) -> int:
    if value is None or isinstance(value, bool):
        raise ManufacturingRequirementsError(f"{fieldname} must be a positive integer.")
    text = str(value).strip()
    if not text:
        raise ManufacturingRequirementsError(f"{fieldname} must be a positive integer.")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ManufacturingRequirementsError(f"{fieldname} must be a positive integer.") from exc
    if (
        not number.is_finite()
        or number <= 0
        or number != number.to_integral_value()
    ):
        raise ManufacturingRequirementsError(f"{fieldname} must be a positive integer.")
    return int(number)


def _canonical_bool(value: Any, *, fieldname: str) -> bool:
    if isinstance(value, bool):
        return value
    if type(value) is int and value in {0, 1}:
        return bool(value)
    raise ManufacturingRequirementsError(f"{fieldname} must be a boolean.")


def _canonical_dimension(value: Any, *, fieldname: str) -> str:
    number = require_cut_dimension_cm(value, fieldname=fieldname)
    return format(Decimal(str(number)).quantize(_CUT_DIMENSION_QUANTUM), ".3f")


def build_manufacturing_requirements(
    pieces: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the immutable manufacturing requirements captured by one plan revision."""

    canonical_pieces: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for raw in pieces:
        if not isinstance(raw, Mapping):
            raise ManufacturingRequirementsError(
                "manufacturing requirement pieces must be objects."
            )
        label = str(raw.get("label") or "").strip()
        if not label or label in seen_labels:
            raise ManufacturingRequirementsError(
                "manufacturing requirement labels must be present and unique."
            )
        seen_labels.add(label)
        source_piece_no = _positive_int(
            raw.get("source_piece_no"), fieldname="source_piece_no"
        )
        copy_no = _positive_int(raw.get("copy_no"), fieldname="copy_no")
        canonical_pieces.append(
            {
                "label": label,
                "source_piece_no": source_piece_no,
                "copy_no": copy_no,
                "cut_width_cm": _canonical_dimension(
                    raw.get("cut_width_cm"), fieldname="cut_width_cm"
                ),
                "cut_length_cm": _canonical_dimension(
                    raw.get("cut_length_cm"), fieldname="cut_length_cm"
                ),
                "allow_rotation": _canonical_bool(
                    raw.get("allow_rotation"), fieldname="allow_rotation"
                ),
                "piece_type": str(raw.get("piece_type") or "Regular"),
            }
        )

    if not canonical_pieces:
        raise ManufacturingRequirementsError(
            "manufacturing requirements must contain at least one piece."
        )

    return {
        "schema_version": MANUFACTURING_REQUIREMENTS_SCHEMA_VERSION,
        "unit": MANUFACTURING_REQUIREMENTS_UNIT,
        "pieces": canonical_pieces,
    }


def canonicalize_manufacturing_requirements(value: Any) -> dict[str, Any]:
    """Validate and canonicalize one declared manufacturing requirement payload."""

    if not isinstance(value, Mapping):
        raise ManufacturingRequirementsError(
            "manufacturing requirements must be an object."
        )
    schema_version = value.get("schema_version")
    if (
        type(schema_version) is not int
        or schema_version != MANUFACTURING_REQUIREMENTS_SCHEMA_VERSION
    ):
        raise ManufacturingRequirementsError(
            "unsupported manufacturing requirements schema version."
        )
    if value.get("unit") != MANUFACTURING_REQUIREMENTS_UNIT:
        raise ManufacturingRequirementsError(
            "manufacturing requirements must use cm units."
        )
    pieces = value.get("pieces")
    if not isinstance(pieces, list):
        raise ManufacturingRequirementsError(
            "manufacturing requirements pieces must be an array."
        )
    return build_manufacturing_requirements(pieces)


def canonicalize_snapshot_manufacturing_requirements(snapshot: Any) -> Any:
    """Canonicalize a declared snapshot contract while preserving legacy absence."""

    if not isinstance(snapshot, Mapping) or "manufacturing_requirements" not in snapshot:
        return snapshot
    canonical = dict(snapshot)
    canonical["manufacturing_requirements"] = canonicalize_manufacturing_requirements(
        snapshot.get("manufacturing_requirements")
    )
    return canonical


def snapshot_manufacturing_requirement_index(
    snapshot: Mapping[str, Any], *, require: bool = False
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Return requirements keyed by stable piece label.

    Legacy absence is reported as ``({}, False)`` unless ``require`` is true.
    """

    raw = snapshot.get("manufacturing_requirements")
    if raw is None:
        if require:
            raise ManufacturingRequirementsError(
                "saved cutting plan has no captured manufacturing requirements."
            )
        return {}, False
    canonical = canonicalize_manufacturing_requirements(raw)
    return {
        str(piece["label"]): piece for piece in canonical["pieces"]
    }, True


__all__ = [
    "MANUFACTURING_REQUIREMENTS_SCHEMA_VERSION",
    "MANUFACTURING_REQUIREMENTS_UNIT",
    "ManufacturingRequirementsError",
    "build_manufacturing_requirements",
    "canonicalize_manufacturing_requirements",
    "canonicalize_snapshot_manufacturing_requirements",
    "require_cut_dimension_cm",
    "snapshot_manufacturing_requirement_index",
]
