from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

TEXT_LABEL_LAYER = "text"
TEXT_LABEL_LAYER_KEY = "TEXT"


class DxfTextLabelError(ValueError):
    """Raised when a persisted DXF door-number annotation is malformed."""


def matches_text_label_layer(layer: Any) -> bool:
    """True when a DXF layer is the door-number annotation layer."""

    return str(layer or "").strip().upper() == TEXT_LABEL_LAYER_KEY


def _finite_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DxfTextLabelError(f"{field} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise DxfTextLabelError(f"{field} must be a finite number.")
    return number


def serialize_text_label(
    *,
    text: str,
    x_mm: float,
    y_mm: float,
    height_mm: float,
    rotation_deg: float = 0.0,
) -> dict[str, Any]:
    """Serialize one door-number annotation in usable-sheet millimetres."""

    content = str(text or "").strip()
    if not content:
        raise DxfTextLabelError("text_labels text must be a non-empty string.")
    return {
        "text": content,
        "x_mm": float(x_mm),
        "y_mm": float(y_mm),
        "height_mm": float(height_mm),
        "rotation_deg": float(rotation_deg),
        "layer": TEXT_LABEL_LAYER,
    }


def parse_text_label(value: Any, *, field: str = "text_labels") -> dict[str, Any]:
    """Parse one door-number annotation without treating it as cut geometry."""

    if not isinstance(value, Mapping):
        raise DxfTextLabelError(f"{field} must be an object.")
    content = str(value.get("text") or "").strip()
    if not content:
        raise DxfTextLabelError(f"{field}.text must be a non-empty string.")
    layer = str(value.get("layer") or TEXT_LABEL_LAYER).strip()
    if layer and not matches_text_label_layer(layer):
        raise DxfTextLabelError(f"{field}.layer must be {TEXT_LABEL_LAYER}.")
    return serialize_text_label(
        text=content,
        x_mm=_finite_number(value.get("x_mm"), field=f"{field}.x_mm"),
        y_mm=_finite_number(value.get("y_mm"), field=f"{field}.y_mm"),
        height_mm=_finite_number(value.get("height_mm"), field=f"{field}.height_mm"),
        rotation_deg=_finite_number(
            0.0 if value.get("rotation_deg") is None else value.get("rotation_deg"),
            field=f"{field}.rotation_deg",
        ),
    )


def canonicalize_text_labels(value: Any, *, field: str = "text_labels") -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, list):
        raise DxfTextLabelError(f"{field} must be an array.")
    return [
        parse_text_label(item, field=f"{field}[{index}]")
        for index, item in enumerate(value)
    ]


__all__ = [
    "DxfTextLabelError",
    "TEXT_LABEL_LAYER",
    "TEXT_LABEL_LAYER_KEY",
    "canonicalize_text_labels",
    "matches_text_label_layer",
    "parse_text_label",
    "serialize_text_label",
]
