"""Canonical multi-liner payload for one door piece.

Legacy rows store a single liner as scalar fields. New rows keep those scalars
in sync with the first liner and persist the full list in ``liner_specs_json``.
Pricing still keys off the ``extra_liner`` checkbox once per door.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

LINER_SPECS_FIELD = "liner_specs_json"
LEGACY_LINER_ID = "liner_1"
_LINER_ID_PATTERN = re.compile(r"^liner_(\d+)$")


class DoorLinerError(ValueError):
    """Raised when stored liner list/width data cannot be used."""

    def __init__(self, code: str, liner_id: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.liner_id = liner_id


@dataclass(frozen=True, slots=True)
class DoorLinerSpec:
    liner_id: str
    side: str
    offset_cm: float
    start_cm: float
    length_cm: float


@dataclass(frozen=True, slots=True)
class DoorLinerSet:
    enabled: bool
    width_cm: float
    liners: tuple[DoorLinerSpec, ...]

    @property
    def first(self) -> DoorLinerSpec | None:
        return self.liners[0] if self.liners else None


def empty_door_liners() -> DoorLinerSet:
    return DoorLinerSet(enabled=False, width_cm=0.0, liners=())


def allocate_liner_id(existing: Sequence[str]) -> str:
    """Return a stable unused id. Display numbers are assigned separately."""

    used = 0
    for raw in existing:
        match = _LINER_ID_PATTERN.match(str(raw or "").strip())
        if match:
            used = max(used, int(match.group(1)))
    return f"liner_{used + 1}"


def serialize_door_liners(payload: DoorLinerSet) -> str:
    """Persist a compact JSON object. Empty when the add-on is off."""

    if not payload.enabled or not payload.liners:
        return ""
    body = {
        "width_cm": _finite_number(payload.width_cm, "liner_width_invalid"),
        "liners": [
            {
                "id": spec.liner_id,
                "side": spec.side,
                "offset_cm": spec.offset_cm,
                "start_cm": spec.start_cm,
                "length_cm": spec.length_cm,
            }
            for spec in payload.liners
        ],
    }
    return json.dumps(body, separators=(",", ":"), ensure_ascii=True)


def door_liners_from_source(source: Any) -> DoorLinerSet:
    """Read JSON when present, otherwise the historical single-liner fields."""

    enabled = _truthy(_field(source, "extra_liner", 0))
    raw_json = _field(source, LINER_SPECS_FIELD, "")
    parsed = _parse_specs_json(raw_json) if _has_text(raw_json) else None
    if parsed is not None:
        width_cm, liners = parsed
        if not enabled:
            return empty_door_liners()
        if not liners:
            raise DoorLinerError("liner_parameters_required")
        shared = width_cm
        if shared is None:
            shared = _optional_number(_field(source, "liner_width_cm", 0), "liner_width_invalid")
        if shared is None or shared <= 0:
            raise DoorLinerError("liner_width_invalid")
        return DoorLinerSet(enabled=True, width_cm=shared, liners=liners)

    if not enabled:
        return empty_door_liners()
    side = str(_field(source, "liner_reference_side", "") or "").strip()
    offset = _optional_number(_field(source, "liner_offset_cm", 0), "offset_invalid") or 0.0
    width = _optional_number(_field(source, "liner_width_cm", 0), "liner_width_invalid") or 0.0
    start = _optional_number(_field(source, "liner_start_cm", 0), "liner_start_invalid") or 0.0
    length = _optional_number(_field(source, "liner_length_cm", 0), "liner_length_invalid") or 0.0
    if not side and offset <= 0 and width <= 0:
        return DoorLinerSet(enabled=True, width_cm=0.0, liners=())
    return DoorLinerSet(
        enabled=True,
        width_cm=width,
        liners=(
            DoorLinerSpec(
                liner_id=LEGACY_LINER_ID,
                side=side,
                offset_cm=offset,
                start_cm=start,
                length_cm=length,
            ),
        ),
    )


def door_liner_fields(payload: DoorLinerSet) -> dict[str, Any]:
    """Scalar legacy fields plus JSON. Always mirrors liner 1 when enabled."""

    first = payload.first
    enabled = bool(payload.enabled and first is not None)
    return {
        "extra_liner": 1 if enabled else 0,
        "liner_reference_side": first.side if enabled and first else "",
        "liner_offset_cm": first.offset_cm if enabled and first else 0,
        "liner_width_cm": payload.width_cm if enabled else 0,
        "liner_start_cm": first.start_cm if enabled and first else 0,
        "liner_length_cm": first.length_cm if enabled and first else 0,
        LINER_SPECS_FIELD: serialize_door_liners(payload) if enabled else "",
    }


def normalized_door_liners(
    source: Any,
    *,
    enabled: bool | None = None,
) -> DoorLinerSet:
    """Re-read after optional enable override, then re-serialize consistently."""

    current = door_liners_from_source(source)
    if enabled is False:
        return empty_door_liners()
    if enabled is True and not current.enabled:
        current = DoorLinerSet(
            enabled=True,
            width_cm=current.width_cm,
            liners=current.liners,
        )
    return current


def _parse_specs_json(raw: Any) -> tuple[float | None, tuple[DoorLinerSpec, ...]]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise DoorLinerError("liner_specs_invalid") from error
    if not isinstance(data, Mapping):
        raise DoorLinerError("liner_specs_invalid")
    width_raw = data.get("width_cm", data.get("widthCm"))
    width_cm = None if width_raw in (None, "") else _finite_number(width_raw, "liner_width_invalid")
    items = data.get("liners")
    if items is None:
        raise DoorLinerError("liner_specs_invalid")
    if not isinstance(items, (list, tuple)):
        raise DoorLinerError("liner_specs_invalid")
    liners: list[DoorLinerSpec] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise DoorLinerError("liner_specs_invalid")
        liner_id = str(item.get("id") or item.get("liner_id") or "").strip()
        if not liner_id:
            liner_id = allocate_liner_id([spec.liner_id for spec in liners] or [LEGACY_LINER_ID])
            if index == 0 and not liners:
                liner_id = LEGACY_LINER_ID
        if liner_id in seen:
            raise DoorLinerError("liner_id_duplicate", liner_id)
        seen.add(liner_id)
        side = str(item.get("side") or item.get("reference_side") or "").strip()
        liners.append(
            DoorLinerSpec(
                liner_id=liner_id,
                side=side,
                offset_cm=_finite_number(item.get("offset_cm", item.get("offsetCm", 0)), "offset_invalid", liner_id),
                start_cm=_finite_number(item.get("start_cm", item.get("startCm", 0)), "liner_start_invalid", liner_id),
                length_cm=_finite_number(
                    item.get("length_cm", item.get("lengthCm", 0)),
                    "liner_length_invalid",
                    liner_id,
                ),
            )
        )
    return width_cm, tuple(liners)


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _has_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _truthy(value: Any) -> bool:
    if value in (None, "", False):
        return False
    try:
        return int(value) != 0
    except (TypeError, ValueError):
        return bool(value)


def _optional_number(value: Any, code: str) -> float | None:
    if value in (None, ""):
        return None
    return _finite_number(value, code)


def _finite_number(value: Any, code: str, liner_id: str = "") -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise DoorLinerError(code, liner_id) from error
    if not math.isfinite(number):
        raise DoorLinerError(code, liner_id)
    return number


__all__ = [
    "DoorLinerError",
    "DoorLinerSet",
    "DoorLinerSpec",
    "LEGACY_LINER_ID",
    "LINER_SPECS_FIELD",
    "allocate_liner_id",
    "door_liner_fields",
    "door_liners_from_source",
    "empty_door_liners",
    "normalized_door_liners",
    "serialize_door_liners",
]
