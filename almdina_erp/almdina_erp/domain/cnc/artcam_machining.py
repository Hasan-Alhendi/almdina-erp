"""ArtCAM-style tools, profiles, vector association, and frozen toolpaths.

A tool definition is independent of every profile that copies it. A profile is
independent of every association that copies it. A calculated toolpath keeps
its own snapshot, so later edits do not rewrite it.

Vector identity is the operational path key already issued from the piece
instance and geometry fingerprint. List order, draw order, and the layer name
are not identities. Sheet perimeter uses the existing connected-perimeter path
key and is offered only when that path is in the machinable catalog.
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from almdina_erp.almdina_erp.domain.cnc.operations import SHEET_PERIMETER_OPERATION_KEY
from almdina_erp.almdina_erp.domain.cnc.perimeter import SHEET_PERIMETER_PATH_KEY
from almdina_erp.almdina_erp.domain.cnc.program import _motions, _pass_depths
from almdina_erp.almdina_erp.domain.cnc.tool_preset import (
    MAX_DEPTH_MM,
    MAX_DIAMETER_MM,
    MAX_FEED_MM_MIN,
    MAX_PLUNGE_MM_MIN,
    MAX_SPINDLE_RPM,
    ToolPresetError,
    ToolPresetValues,
    assert_single_tool_for_file,
    normalize_tool_preset,
)


BALL_NOSE = "Ball Nose"
SUPPORTED_TOOL_TYPES = (BALL_NOSE,)
TOOL_UNITS_MM = "mm"
RATE_UNITS_MM_SEC = "mm/sec"
LEGACY_RATE_UNITS_MM_MIN = "mm/min"
SAFE_Z_MAX_MM = 500.0
HOME_AXIS_LIMIT_MM = 100_000.0
_NAME_LIMIT = 140
_NOTES_LIMIT = 4000
_ID_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,79}$")
_TOOL_NUMBER = re.compile(r"^T[1-9][0-9]{0,2}$")

SELECTION_LAYER = "layer"
SELECTION_VECTORS = "vectors"
SELECTION_SHEET_PERIMETER = "sheet_perimeter"


class MachiningSetupError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ArtcamToolValues:
    description: str
    tool_type: str
    tool_number: str
    tool_number_display: int
    tool_units: str
    rate_units: str
    notes: str
    diameter_mm: float
    stepdown_mm: float
    final_tool_offset_mm: float
    stepover_size_mm: float
    stepover_percent: float
    spindle_speed_rpm: int
    feed_rate_mm_sec: float
    plunge_rate_mm_sec: float

    def public_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "tool_type": self.tool_type,
            "tool_number": self.tool_number,
            "tool_number_display": self.tool_number_display,
            "tool_units": self.tool_units,
            "rate_units": self.rate_units,
            "notes": self.notes,
            "diameter_mm": self.diameter_mm,
            "stepdown_mm": self.stepdown_mm,
            "final_tool_offset_mm": self.final_tool_offset_mm,
            "stepover_size_mm": self.stepover_size_mm,
            "stepover_percent": self.stepover_percent,
            "spindle_speed_rpm": self.spindle_speed_rpm,
            "feed_rate_mm_sec": self.feed_rate_mm_sec,
            "plunge_rate_mm_sec": self.plunge_rate_mm_sec,
        }


@dataclass(frozen=True, slots=True)
class MachinableVector:
    vector_id: str
    operation_key: str
    dxf_layer: str
    piece_instance_id: str
    label: str


def new_machining_id(prefix: str) -> str:
    token = str(prefix or "item").strip().lower() or "item"
    return f"{token}:{uuid.uuid4().hex}"


def _copy(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return deepcopy(dict(value or {}))


def _text(value: Any, code: str, *, limit: int = _NAME_LIMIT, allow_empty: bool = False) -> str:
    text = str(value if value is not None else "").strip()
    if not text and not allow_empty:
        raise MachiningSetupError(code)
    if len(text) > limit:
        raise MachiningSetupError(code)
    return text


def _finite(value: Any, code: str, *, lower: float, upper: float, inclusive_lower: bool) -> float:
    if isinstance(value, bool):
        raise MachiningSetupError(code)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MachiningSetupError(code) from exc
    if not math.isfinite(number) or number > upper:
        raise MachiningSetupError(code)
    if inclusive_lower:
        if number < lower:
            raise MachiningSetupError(code)
    elif number <= lower:
        raise MachiningSetupError(code)
    return number


def _tool_number(value: Any) -> tuple[str, int]:
    raw = str(value if value is not None else "").strip().upper()
    if raw.startswith("T"):
        token = raw
    else:
        if isinstance(value, bool):
            raise MachiningSetupError("tool_number_invalid")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise MachiningSetupError("tool_number_invalid") from exc
        if not math.isfinite(number) or not number.is_integer():
            raise MachiningSetupError("tool_number_invalid")
        token = f"T{int(number)}"
    if _TOOL_NUMBER.fullmatch(token) is None:
        raise MachiningSetupError("tool_number_invalid")
    return token, int(token[1:])


def _spindle(value: Any) -> int:
    if isinstance(value, bool):
        raise MachiningSetupError("spindle_speed_invalid")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MachiningSetupError("spindle_speed_invalid") from exc
    if (
        not math.isfinite(number)
        or not number.is_integer()
        or number <= 0
        or number > MAX_SPINDLE_RPM
    ):
        raise MachiningSetupError("spindle_speed_invalid")
    return int(number)


def normalize_artcam_tool(raw: Mapping[str, Any]) -> ArtcamToolValues:
    """Validate one Ball Nose tool using only the ArtCAM Edit Tool fields."""

    tool_type = _text(raw.get("tool_type"), "tool_type_invalid")
    if tool_type not in SUPPORTED_TOOL_TYPES:
        raise MachiningSetupError("tool_type_unsupported")
    tool_units = _text(raw.get("tool_units"), "tool_units_invalid")
    if tool_units != TOOL_UNITS_MM:
        raise MachiningSetupError("tool_units_invalid")
    rate_units = _text(raw.get("rate_units"), "rate_units_invalid")
    if rate_units != RATE_UNITS_MM_SEC:
        raise MachiningSetupError("rate_units_invalid")
    tool_number, display = _tool_number(raw.get("tool_number", raw.get("tool_number_display")))
    feed = _finite(
        raw.get("feed_rate_mm_sec", raw.get("feed_rate")),
        "feed_rate_invalid",
        lower=0,
        upper=MAX_FEED_MM_MIN / 60.0,
        inclusive_lower=False,
    )
    plunge = _finite(
        raw.get("plunge_rate_mm_sec", raw.get("plunge_rate")),
        "plunge_rate_invalid",
        lower=0,
        upper=MAX_PLUNGE_MM_MIN / 60.0,
        inclusive_lower=False,
    )
    diameter = _finite(
        raw.get("diameter_mm", raw.get("tool_diameter_mm")),
        "tool_diameter_invalid",
        lower=0,
        upper=MAX_DIAMETER_MM,
        inclusive_lower=False,
    )
    return ArtcamToolValues(
        description=_text(raw.get("description", raw.get("tool_name")), "description_required"),
        tool_type=tool_type,
        tool_number=tool_number,
        tool_number_display=display,
        tool_units=tool_units,
        rate_units=rate_units,
        notes=_text(raw.get("notes"), "notes_invalid", limit=_NOTES_LIMIT, allow_empty=True),
        diameter_mm=round(diameter, 3),
        stepdown_mm=round(
            _finite(raw.get("stepdown_mm", raw.get("stepdown")), "stepdown_invalid", lower=0, upper=MAX_DEPTH_MM, inclusive_lower=False),
            3,
        ),
        final_tool_offset_mm=round(
            _finite(
                raw.get("final_tool_offset_mm", raw.get("final_tool_offset")),
                "final_tool_offset_invalid",
                lower=0,
                upper=MAX_DIAMETER_MM,
                inclusive_lower=True,
            ),
            3,
        ),
        stepover_size_mm=round(
            _finite(
                raw.get("stepover_size_mm", raw.get("stepover_size")),
                "stepover_invalid",
                lower=0,
                upper=MAX_DIAMETER_MM,
                inclusive_lower=False,
            ),
            3,
        ),
        stepover_percent=round(
            _finite(
                raw.get("stepover_percent", raw.get("stepover_percent_of_d")),
                "stepover_invalid",
                lower=0,
                upper=100,
                inclusive_lower=False,
            ),
            3,
        ),
        spindle_speed_rpm=_spindle(raw.get("spindle_speed_rpm")),
        feed_rate_mm_sec=round(feed, 3),
        plunge_rate_mm_sec=round(plunge, 3),
    )


def artcam_tool_storage(tool: ArtcamToolValues) -> dict[str, Any]:
    """Map an ArtCAM tool onto the existing preset columns without inventing a depth."""

    return {
        "tool_name": tool.description,
        "tool_number": tool.tool_number,
        "tool_diameter_mm": tool.diameter_mm,
        "spindle_speed_rpm": tool.spindle_speed_rpm,
        "feed_rate_mm_min": round(tool.feed_rate_mm_sec * 60.0, 1),
        "plunge_rate_mm_min": round(tool.plunge_rate_mm_sec * 60.0, 1),
        "pass_depth_mm": tool.stepdown_mm,
        "tool_type": tool.tool_type,
        "tool_units": tool.tool_units,
        "rate_units": tool.rate_units,
        "notes": tool.notes,
        "stepdown_mm": tool.stepdown_mm,
        "final_tool_offset_mm": tool.final_tool_offset_mm,
        "stepover_size_mm": tool.stepover_size_mm,
        "stepover_percent": tool.stepover_percent,
        "feed_rate_mm_sec": tool.feed_rate_mm_sec,
        "plunge_rate_mm_sec": tool.plunge_rate_mm_sec,
    }


def tool_copy_from_stored(raw: Mapping[str, Any], *, tool_preset: str) -> dict[str, Any]:
    """Deep-copy the stored tool. Later edits of this copy do not write back."""

    stored = _copy(raw)
    tool_type = str(stored.get("tool_type") or "").strip()
    if tool_type == BALL_NOSE:
        tool = normalize_artcam_tool(stored)
        payload = tool.public_dict()
    else:
        payload = {
            "description": str(stored.get("tool_name") or stored.get("preset_name") or tool_preset),
            "tool_type": tool_type,
            "tool_number": str(stored.get("tool_number") or ""),
            "tool_units": TOOL_UNITS_MM,
            "rate_units": str(stored.get("rate_units") or LEGACY_RATE_UNITS_MM_MIN),
            "notes": str(stored.get("notes") or ""),
            "diameter_mm": stored.get("tool_diameter_mm"),
            "stepdown_mm": stored.get("stepdown_mm", stored.get("pass_depth_mm")),
            "final_tool_offset_mm": stored.get("final_tool_offset_mm"),
            "stepover_size_mm": stored.get("stepover_size_mm"),
            "stepover_percent": stored.get("stepover_percent"),
            "spindle_speed_rpm": stored.get("spindle_speed_rpm"),
            "feed_rate_mm_sec": stored.get("feed_rate_mm_sec"),
            "plunge_rate_mm_sec": stored.get("plunge_rate_mm_sec"),
            "feed_rate_mm_min": stored.get("feed_rate_mm_min"),
            "plunge_rate_mm_min": stored.get("plunge_rate_mm_min"),
            "pass_depth_mm": stored.get("pass_depth_mm"),
            "final_depth_mm": stored.get("final_depth_mm"),
            "enabled": bool(stored.get("enabled", True)),
        }
    payload["tool_preset"] = str(tool_preset or stored.get("preset_name") or "")
    return payload


def _stable_id(value: Any, code: str) -> str:
    token = str(value or "").strip()
    if _ID_TOKEN.fullmatch(token) is None:
        raise MachiningSetupError(code)
    return token


def _depth_mm(value: Any) -> float:
    return round(
        _finite(value, "final_depth_invalid", lower=0, upper=MAX_DEPTH_MM, inclusive_lower=False),
        3,
    )


def _safe_z(value: Any) -> float:
    return round(
        _finite(value, "safe_z_invalid", lower=0, upper=SAFE_Z_MAX_MM, inclusive_lower=True),
        3,
    )


def _home_axis(value: Any, code: str) -> float:
    return round(
        _finite(value, code, lower=-HOME_AXIS_LIMIT_MM, upper=HOME_AXIS_LIMIT_MM, inclusive_lower=True),
        3,
    )


def _home_z(value: Any) -> float:
    return round(
        _finite(value, "home_z_invalid", lower=0, upper=SAFE_Z_MAX_MM, inclusive_lower=True),
        3,
    )


def canonical_tool_copy(raw: Mapping[str, Any], *, tool_preset: str) -> dict[str, Any]:
    """Validate a stored tool copy. Ball Nose uses the same rules as the base tool."""

    stored = _copy(raw)
    tool_type = str(stored.get("tool_type") or "").strip()
    rate_units = str(stored.get("rate_units") or "").strip()
    if tool_type == BALL_NOSE or rate_units == RATE_UNITS_MM_SEC:
        payload = normalize_artcam_tool(stored).public_dict()
        payload["tool_preset"] = str(tool_preset or "")
        payload["enabled"] = True if stored.get("enabled", True) else False
        return payload
    payload = tool_copy_from_stored(stored, tool_preset=tool_preset)
    payload["tool_preset"] = str(tool_preset or payload.get("tool_preset") or "")
    return payload


def normalize_profile(
    raw: Mapping[str, Any],
    *,
    known_tools: Mapping[str, Mapping[str, Any]],
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Copy the selected tool into a profile. The stored tool is not modified."""

    name = _text(raw.get("name"), "profile_name_required")
    tool_name = _text(raw.get("tool_preset"), "tool_preset_required")
    explicit = raw.get("tool_values") if isinstance(raw.get("tool_values"), Mapping) else None
    if explicit:
        tool_values = canonical_tool_copy(explicit, tool_preset=tool_name)
    else:
        stored = known_tools.get(tool_name)
        if stored is None:
            raise MachiningSetupError("preset_not_found")
        if stored.get("enabled", True) is False:
            raise MachiningSetupError("preset_disabled")
        tool_values = tool_copy_from_stored(stored, tool_preset=tool_name)
    profile = {
        "profile_id": _stable_id(profile_id or raw.get("profile_id") or new_machining_id("profile"), "profile_id_invalid"),
        "name": name,
        "tool_preset": tool_name,
        "tool_values": tool_values,
        "final_depth_mm": _depth_mm(raw.get("final_depth_mm")),
        "safe_z_mm": _safe_z(raw.get("safe_z_mm")),
        "home_x_mm": _home_axis(raw.get("home_x_mm"), "home_x_invalid"),
        "home_y_mm": _home_axis(raw.get("home_y_mm"), "home_y_invalid"),
        "home_z_mm": _home_z(raw.get("home_z_mm")),
    }
    _preset_from_local(profile)
    return profile


def normalize_profiles(
    rows: Sequence[Mapping[str, Any]],
    *,
    known_tools: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise MachiningSetupError("profile_invalid")
        profile = normalize_profile(row, known_tools=known_tools)
        if profile["profile_id"] in seen or profile["name"] in {item["name"] for item in profiles}:
            raise MachiningSetupError("profile_duplicate")
        seen.add(profile["profile_id"])
        profiles.append(profile)
    return profiles


def _preset_from_local(local: Mapping[str, Any]) -> ToolPresetValues:
    tool_values = local.get("tool_values") if isinstance(local.get("tool_values"), Mapping) else {}
    rate_units = str(tool_values.get("rate_units") or "")
    if rate_units == RATE_UNITS_MM_SEC:
        feed = float(tool_values.get("feed_rate_mm_sec") or 0) * 60.0
        plunge = float(tool_values.get("plunge_rate_mm_sec") or 0) * 60.0
        stepdown = tool_values.get("stepdown_mm")
    else:
        feed = tool_values.get("feed_rate_mm_min")
        plunge = tool_values.get("plunge_rate_mm_min")
        stepdown = tool_values.get("stepdown_mm", tool_values.get("pass_depth_mm"))
    final_depth = _depth_mm(local.get("final_depth_mm"))
    if stepdown not in (None, ""):
        if float(stepdown) > float(final_depth) + 1e-9:
            raise MachiningSetupError("pass_depth_exceeds_final_depth")
    description = str(tool_values.get("description") or tool_values.get("tool_preset") or local.get("name") or "tool")
    raw = {
        "preset_name": str(tool_values.get("tool_preset") or description),
        "tool_name": description,
        "tool_number": tool_values.get("tool_number"),
        "tool_diameter_mm": tool_values.get("diameter_mm", tool_values.get("tool_diameter_mm")),
        "final_depth_mm": final_depth,
        "spindle_speed_rpm": tool_values.get("spindle_speed_rpm"),
        "feed_rate_mm_min": feed,
        "plunge_rate_mm_min": plunge,
        "pass_depth_mm": None if stepdown in (None, "") else stepdown,
        "enabled": True if tool_values.get("enabled", True) else False,
    }
    raw.pop("final_depth_mm", None)
    try:
        return normalize_tool_preset(raw, machining_depth_mm=final_depth)
    except ToolPresetError as exc:
        raise MachiningSetupError(exc.code) from exc


def vectors_from_paths(paths: Sequence[Mapping[str, Any]]) -> tuple[MachinableVector, ...]:
    """Keep only catalog paths. Illustrative layers never enter this catalog."""

    vectors: list[MachinableVector] = []
    seen: set[str] = set()
    for row in paths:
        if not isinstance(row, Mapping):
            continue
        vector_id = str(row.get("path_key") or row.get("vector_id") or "").strip()
        operation_key = str(row.get("operation_key") or "").strip()
        if not vector_id or not operation_key or vector_id in seen:
            continue
        if vector_id == "cut_path:internals":
            continue
        seen.add(vector_id)
        vectors.append(
            MachinableVector(
                vector_id=vector_id,
                operation_key=operation_key,
                dxf_layer=str(row.get("dxf_layer") or ""),
                piece_instance_id=str(row.get("piece_instance_id") or ""),
                label=str(row.get("piece_label") or row.get("label") or vector_id),
            )
        )
    return tuple(vectors)


def _catalog_index(catalog: Sequence[MachinableVector]) -> dict[str, MachinableVector]:
    return {vector.vector_id: vector for vector in catalog}


def selection_coverage(
    selection: Mapping[str, Any],
    catalog: Sequence[MachinableVector],
) -> tuple[str, ...]:
    """Return the path keys one association actually consumes."""

    if not isinstance(selection, Mapping):
        raise MachiningSetupError("selection_invalid")
    kind = str(selection.get("kind") or "").strip()
    index = _catalog_index(catalog)
    if kind == SELECTION_SHEET_PERIMETER:
        if SHEET_PERIMETER_PATH_KEY not in index:
            raise MachiningSetupError("sheet_perimeter_unavailable")
        return (SHEET_PERIMETER_PATH_KEY,)
    if kind == SELECTION_LAYER:
        operation_key = str(selection.get("operation_key") or "").strip()
        if not operation_key or operation_key == SHEET_PERIMETER_OPERATION_KEY:
            raise MachiningSetupError("layer_not_machinable")
        covered = tuple(
            vector.vector_id
            for vector in catalog
            if vector.operation_key == operation_key and vector.vector_id != SHEET_PERIMETER_PATH_KEY
        )
        if not covered:
            raise MachiningSetupError("layer_not_machinable")
        return covered
    if kind == SELECTION_VECTORS:
        raw_ids = selection.get("vector_ids") or ()
        if isinstance(raw_ids, (str, bytes)) or not isinstance(raw_ids, Sequence) or not raw_ids:
            raise MachiningSetupError("vector_not_machinable")
        covered: list[str] = []
        for raw_id in raw_ids:
            vector_id = str(raw_id or "").strip()
            vector = index.get(vector_id)
            if vector is None or vector.vector_id == SHEET_PERIMETER_PATH_KEY:
                raise MachiningSetupError("vector_not_machinable")
            if vector_id not in covered:
                covered.append(vector_id)
        return tuple(covered)
    raise MachiningSetupError("selection_invalid")


def _local_from_profile(profile: Mapping[str, Any], raw_local: Any) -> dict[str, Any]:
    if isinstance(raw_local, Mapping) and raw_local:
        local = _copy(raw_local)
    else:
        local = _copy(profile)
    local["profile_id"] = profile["profile_id"]
    local["tool_preset"] = profile["tool_preset"]
    if not isinstance(local.get("tool_values"), Mapping) or not local.get("tool_values"):
        local["tool_values"] = _copy(profile.get("tool_values") if isinstance(profile.get("tool_values"), Mapping) else {})
    local["tool_values"] = canonical_tool_copy(
        local["tool_values"],
        tool_preset=str(local.get("tool_preset") or ""),
    )
    local["final_depth_mm"] = _depth_mm(local.get("final_depth_mm", profile.get("final_depth_mm")))
    local["safe_z_mm"] = _safe_z(local.get("safe_z_mm", profile.get("safe_z_mm")))
    local["home_x_mm"] = _home_axis(local.get("home_x_mm", profile.get("home_x_mm")), "home_x_invalid")
    local["home_y_mm"] = _home_axis(local.get("home_y_mm", profile.get("home_y_mm")), "home_y_invalid")
    local["home_z_mm"] = _home_z(local.get("home_z_mm", profile.get("home_z_mm")))
    _preset_from_local(local)
    return local


def normalize_associations(
    rows: Sequence[Mapping[str, Any]],
    *,
    profiles: Sequence[Mapping[str, Any]],
    catalog: Sequence[MachinableVector],
) -> list[dict[str, Any]]:
    by_profile = {str(profile.get("profile_id") or ""): profile for profile in profiles}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    covered_owner: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise MachiningSetupError("association_invalid")
        association_id = _stable_id(
            row.get("association_id") or new_machining_id("association"),
            "association_id_invalid",
        )
        if association_id in seen:
            raise MachiningSetupError("association_duplicate")
        profile = by_profile.get(str(row.get("profile_id") or ""))
        if profile is None:
            raise MachiningSetupError("profile_not_found")
        selection = row.get("selection") if isinstance(row.get("selection"), Mapping) else {}
        covered = selection_coverage(selection, catalog)
        for vector_id in covered:
            owner = covered_owner.get(vector_id)
            if owner is not None:
                raise MachiningSetupError("vector_already_assigned")
            covered_owner[vector_id] = association_id
        local = _local_from_profile(profile, row.get("local_values"))
        seen.add(association_id)
        normalized.append(
            {
                "association_id": association_id,
                "selection": _copy(selection),
                "profile_id": profile["profile_id"],
                "local_values": local,
                "toolpath_name": str(row.get("toolpath_name") or "").strip(),
                "toolpath_id": str(row.get("toolpath_id") or "").strip(),
                "vector_ids": list(covered),
            }
        )
    _assert_single_physical_tool(
        [_preset_from_local(row["local_values"]) for row in normalized]
    )
    return normalized


def _assert_single_physical_tool(presets: Sequence[ToolPresetValues]) -> None:
    try:
        assert_single_tool_for_file(presets)
    except ToolPresetError as exc:
        raise MachiningSetupError(exc.code) from exc


def association_availability(
    catalog: Sequence[MachinableVector],
    associations: Sequence[Mapping[str, Any]],
    *,
    editing_id: str | None = None,
) -> dict[str, Any]:
    """Show used vectors as disabled. They stay visible."""

    owners: dict[str, str] = {}
    for association in associations:
        if str(association.get("association_id") or "") == str(editing_id or ""):
            continue
        for vector_id in association.get("vector_ids") or ():
            owners[str(vector_id)] = str(association.get("association_id") or "")
    layers: list[dict[str, Any]] = []
    grouped: dict[str, list[MachinableVector]] = {}
    for vector in catalog:
        if vector.vector_id == SHEET_PERIMETER_PATH_KEY:
            continue
        grouped.setdefault(vector.operation_key, []).append(vector)
    for operation_key, vectors in grouped.items():
        used = [vector.vector_id for vector in vectors if vector.vector_id in owners]
        layers.append(
            {
                "operation_key": operation_key,
                "dxf_layer": vectors[0].dxf_layer,
                "vector_count": len(vectors),
                "disabled": bool(used),
                "used": bool(used),
                "used_vector_ids": used,
            }
        )
    vector_rows = [
        {
            "vector_id": vector.vector_id,
            "operation_key": vector.operation_key,
            "dxf_layer": vector.dxf_layer,
            "piece_instance_id": vector.piece_instance_id,
            "label": vector.label,
            "disabled": vector.vector_id in owners,
            "used": vector.vector_id in owners,
        }
        for vector in catalog
        if vector.vector_id != SHEET_PERIMETER_PATH_KEY
    ]
    perimeter = next((vector for vector in catalog if vector.vector_id == SHEET_PERIMETER_PATH_KEY), None)
    sheet_perimeter = None
    if perimeter is not None:
        sheet_perimeter = {
            "vector_id": SHEET_PERIMETER_PATH_KEY,
            "disabled": SHEET_PERIMETER_PATH_KEY in owners,
            "used": SHEET_PERIMETER_PATH_KEY in owners,
        }
    return {
        "layers": layers,
        "vectors": vector_rows,
        "sheet_perimeter": sheet_perimeter,
    }


def _geometry_index(program: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    found: dict[str, Mapping[str, Any]] = {}
    for operation in program.get("operations") or ():
        if not isinstance(operation, Mapping):
            continue
        for path in operation.get("toolpaths") or ():
            if isinstance(path, Mapping) and path.get("path_key"):
                found[str(path.get("path_key"))] = path
    return found


def _points(path: Mapping[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for point in path.get("points") or ():
        if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) < 2:
            raise MachiningSetupError("geometry_invalid")
        x = float(point[0])
        y = float(point[1])
        if not math.isfinite(x) or not math.isfinite(y):
            raise MachiningSetupError("geometry_invalid")
        points.append((x, y))
    return points


def _motion_rows(
    points: Sequence[tuple[float, float]],
    *,
    closed: bool,
    final_depth: float,
    pass_depth: float | None,
) -> list[dict[str, Any]]:
    depths = _pass_depths(final_depth, pass_depth)
    if isinstance(depths, str):
        raise MachiningSetupError(depths)
    motions = _motions(points, closed=closed, depths=depths)
    return [
        {
            "kind": motion.kind,
            "x_mm": motion.x_mm,
            "y_mm": motion.y_mm,
            "depth_mm": motion.depth_mm,
        }
        for motion in motions
    ]


def calculate_toolpath_snapshot(
    *,
    association: Mapping[str, Any],
    toolpath_name: str,
    program: Mapping[str, Any],
    existing_snapshots: Sequence[Mapping[str, Any]] = (),
    toolpath_id: str | None = None,
) -> dict[str, Any]:
    """Freeze one calculated toolpath from the association's own values."""

    name = _text(toolpath_name or association.get("toolpath_name"), "toolpath_name_required")
    local = association.get("local_values") if isinstance(association.get("local_values"), Mapping) else {}
    preset = _preset_from_local(local)
    previous = [
        _preset_from_local(snapshot.get("local_values") or {})
        for snapshot in existing_snapshots
        if isinstance(snapshot, Mapping)
    ]
    _assert_single_physical_tool([*previous, preset])
    geometry = _geometry_index(program)
    vector_ids = [str(vector_id) for vector_id in association.get("vector_ids") or ()]
    if not vector_ids:
        raise MachiningSetupError("vector_not_machinable")
    paths: list[dict[str, Any]] = []
    for vector_id in vector_ids:
        path = geometry.get(vector_id)
        if path is None or not path.get("ready"):
            issues = list((path or {}).get("issues") or [])
            raise MachiningSetupError(str(issues[0] if issues else "vector_not_machinable"))
        points = _points(path)
        if len(points) < 2:
            raise MachiningSetupError("geometry_invalid")
        closed = bool(path.get("closed"))
        paths.append(
            {
                "path_key": vector_id,
                "operation_key": str(path.get("operation_key") or ""),
                "dxf_layer": str(path.get("dxf_layer") or ""),
                "piece_instance_id": str(path.get("piece_instance_id") or ""),
                "closed": closed,
                "points": [[point[0], point[1]] for point in points],
                "motions": _motion_rows(
                    points,
                    closed=closed,
                    final_depth=preset.final_depth_mm,
                    pass_depth=preset.pass_depth_mm,
                ),
            }
        )
    return {
        "toolpath_id": _stable_id(toolpath_id or new_machining_id("toolpath"), "toolpath_id_invalid"),
        "name": name,
        "association_id": str(association.get("association_id") or ""),
        "profile_id": str(association.get("profile_id") or ""),
        "vector_ids": vector_ids,
        "tool_values": _copy(local.get("tool_values") if isinstance(local.get("tool_values"), Mapping) else {}),
        "profile_values": {
            "final_depth_mm": local.get("final_depth_mm"),
            "safe_z_mm": local.get("safe_z_mm"),
            "home_x_mm": local.get("home_x_mm"),
            "home_y_mm": local.get("home_y_mm"),
            "home_z_mm": local.get("home_z_mm"),
        },
        "local_values": _copy(local),
        "preset": {
            "preset_name": preset.preset_name,
            "tool_name": preset.tool_name,
            "tool_number": preset.tool_number,
            "tool_diameter_mm": preset.tool_diameter_mm,
            "final_depth_mm": preset.final_depth_mm,
            "spindle_speed_rpm": preset.spindle_speed_rpm,
            "feed_rate_mm_min": preset.feed_rate_mm_min,
            "plunge_rate_mm_min": preset.plunge_rate_mm_min,
            "pass_depth_mm": preset.pass_depth_mm,
            "enabled": preset.enabled,
            "safe_z_mm": local.get("safe_z_mm"),
        },
        "safe_z_mm": local.get("safe_z_mm"),
        "home": {
            "x_mm": local.get("home_x_mm"),
            "y_mm": local.get("home_y_mm"),
            "z_mm": local.get("home_z_mm"),
        },
        "paths": paths,
    }


def append_snapshot(
    snapshots: Sequence[Mapping[str, Any]],
    snapshot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Keep calculation order. A new snapshot does not rewrite an older one."""

    stored = [_copy(row) for row in snapshots if isinstance(row, Mapping)]
    incoming = _copy(snapshot)
    if any(row.get("toolpath_id") == incoming.get("toolpath_id") for row in stored):
        raise MachiningSetupError("toolpath_duplicate")
    if any(row.get("name") == incoming.get("name") for row in stored):
        raise MachiningSetupError("toolpath_name_duplicate")
    stored.append(incoming)
    return stored


def assert_physical_tool_consistency(
    associations: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]] = (),
) -> None:
    """One file keeps one physical tool number and one diameter."""

    presets = [
        _preset_from_local(row["local_values"])
        for row in associations
        if isinstance(row, Mapping) and isinstance(row.get("local_values"), Mapping)
    ]
    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping):
            continue
        local = snapshot.get("local_values")
        if isinstance(local, Mapping):
            presets.append(_preset_from_local(local))
    _assert_single_physical_tool(presets)


def synthetic_preset_name(association_id: str) -> str:
    return f"artcam-local:{association_id}"


def local_preset_payload(local: Mapping[str, Any]) -> dict[str, Any]:
    preset = _preset_from_local(local)
    return {
        "preset_name": preset.preset_name,
        "tool_name": preset.tool_name,
        "tool_number": preset.tool_number,
        "tool_diameter_mm": preset.tool_diameter_mm,
        "final_depth_mm": preset.final_depth_mm,
        "spindle_speed_rpm": preset.spindle_speed_rpm,
        "feed_rate_mm_min": preset.feed_rate_mm_min,
        "plunge_rate_mm_min": preset.plunge_rate_mm_min,
        "pass_depth_mm": preset.pass_depth_mm,
        "enabled": True,
    }


def _canon_number(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return value
        if number.is_integer():
            return int(number)
        return round(number, 6)
    return value


def _nc_signature(local: Mapping[str, Any], vector_ids: Sequence[Any]) -> dict[str, Any]:
    preset = _preset_from_local(local)
    return {
        "vectors": [str(vector_id) for vector_id in vector_ids],
        "tool_number": preset.tool_number,
        "diameter_mm": _canon_number(preset.tool_diameter_mm),
        "final_depth_mm": _canon_number(preset.final_depth_mm),
        "pass_depth_mm": _canon_number(preset.pass_depth_mm),
        "spindle_speed_rpm": preset.spindle_speed_rpm,
        "feed_rate_mm_min": _canon_number(preset.feed_rate_mm_min),
        "plunge_rate_mm_min": _canon_number(preset.plunge_rate_mm_min),
        "safe_z_mm": _canon_number(local.get("safe_z_mm")),
        "home_x_mm": _canon_number(local.get("home_x_mm")),
        "home_y_mm": _canon_number(local.get("home_y_mm")),
        "home_z_mm": _canon_number(local.get("home_z_mm")),
    }


def release_stale_toolpath_links(
    associations: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Drop the active link when the association no longer matches its snapshot.

    The snapshot itself stays. A later calculation records the replacement.
    """

    by_id = {
        str(snapshot.get("toolpath_id") or ""): snapshot
        for snapshot in snapshots
        if isinstance(snapshot, Mapping) and snapshot.get("toolpath_id")
    }
    released: list[dict[str, Any]] = []
    for association in associations:
        row = _copy(association)
        link = str(row.get("toolpath_id") or "")
        snapshot = by_id.get(link)
        local = snapshot.get("local_values") if isinstance(snapshot, Mapping) else None
        if isinstance(snapshot, Mapping) and isinstance(local, Mapping):
            current = _nc_signature(row.get("local_values") or {}, row.get("vector_ids") or ())
            frozen = _nc_signature(local, snapshot.get("vector_ids") or ())
            if current != frozen:
                row["toolpath_id"] = ""
                row["toolpath_name"] = ""
        released.append(row)
    return released


def active_toolpath_snapshots(
    snapshots: Sequence[Mapping[str, Any]],
    associations: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return the snapshots that may enter NC.

    A linked association selects its snapshot by toolpath id. Historical
    snapshots stay stored and do not execute. Callers that do not pass
    associations keep the previous last-snapshot-per-path behavior.
    """

    rows = [_copy(snapshot) for snapshot in snapshots if isinstance(snapshot, Mapping)]
    if associations is None:
        return rows
    linked_ids: list[str] = []
    for association in associations:
        if not isinstance(association, Mapping):
            continue
        toolpath_id = str(association.get("toolpath_id") or "").strip()
        if toolpath_id and toolpath_id not in linked_ids:
            linked_ids.append(toolpath_id)
    if not linked_ids:
        return []
    by_id = {str(snapshot.get("toolpath_id") or ""): snapshot for snapshot in rows}
    return [by_id[toolpath_id] for toolpath_id in linked_ids if toolpath_id in by_id]


def nc_toolpath_fingerprint_rows(
    snapshots: Sequence[Mapping[str, Any]] | None,
    associations: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Canonical NC payload. Key order and unused snapshot fields do not matter."""

    active = active_toolpath_snapshots(list(snapshots or ()), list(associations or ()))
    rows: list[dict[str, Any]] = []
    for snapshot in active:
        preset = snapshot.get("preset") if isinstance(snapshot.get("preset"), Mapping) else {}
        home = snapshot.get("home") if isinstance(snapshot.get("home"), Mapping) else {}
        paths = []
        for path in snapshot.get("paths") or ():
            if not isinstance(path, Mapping):
                continue
            paths.append(
                {
                    "path_key": str(path.get("path_key") or ""),
                    "closed": bool(path.get("closed")),
                    "points": deepcopy(path.get("points") or []),
                    "motions": deepcopy(path.get("motions") or []),
                }
            )
        rows.append(
            {
                "toolpath_id": str(snapshot.get("toolpath_id") or ""),
                "vector_ids": [str(vector_id) for vector_id in snapshot.get("vector_ids") or ()],
                "tool_number": str(preset.get("tool_number") or ""),
                "tool_diameter_mm": _canon_number(preset.get("tool_diameter_mm")),
                "final_depth_mm": _canon_number(preset.get("final_depth_mm")),
                "pass_depth_mm": _canon_number(preset.get("pass_depth_mm")),
                "spindle_speed_rpm": _canon_number(preset.get("spindle_speed_rpm")),
                "feed_rate_mm_min": _canon_number(preset.get("feed_rate_mm_min")),
                "plunge_rate_mm_min": _canon_number(preset.get("plunge_rate_mm_min")),
                "safe_z_mm": _canon_number(snapshot.get("safe_z_mm")),
                "home": {
                    "x_mm": _canon_number(home.get("x_mm")),
                    "y_mm": _canon_number(home.get("y_mm")),
                    "z_mm": _canon_number(home.get("z_mm")),
                },
                "paths": paths,
            }
        )
    return sorted(rows, key=lambda row: str(row.get("toolpath_id") or ""))


def machining_tool_uses(
    preset_name: str,
    *,
    profiles: Sequence[Mapping[str, Any]] = (),
    associations: Sequence[Mapping[str, Any]] = (),
    snapshots: Sequence[Mapping[str, Any]] = (),
) -> dict[str, int]:
    """Count saved references. A snapshot copy is independent of a live profile."""

    name = str(preset_name or "").strip()
    profile_uses = sum(
        1
        for profile in profiles
        if isinstance(profile, Mapping) and str(profile.get("tool_preset") or "") == name
    )
    association_uses = 0
    for association in associations:
        if not isinstance(association, Mapping):
            continue
        local = association.get("local_values") if isinstance(association.get("local_values"), Mapping) else {}
        tool_values = local.get("tool_values") if isinstance(local.get("tool_values"), Mapping) else {}
        if name and name in {str(local.get("tool_preset") or ""), str(tool_values.get("tool_preset") or "")}:
            association_uses += 1
    linked_ids = {
        str(association.get("toolpath_id") or "").strip()
        for association in associations
        if isinstance(association, Mapping) and str(association.get("toolpath_id") or "").strip()
    }
    snapshot_uses = 0
    active_snapshot_uses = 0
    historical_snapshot_uses = 0
    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping):
            continue
        local = snapshot.get("local_values") if isinstance(snapshot.get("local_values"), Mapping) else {}
        tool_values = snapshot.get("tool_values") if isinstance(snapshot.get("tool_values"), Mapping) else {}
        preset = snapshot.get("preset") if isinstance(snapshot.get("preset"), Mapping) else {}
        if name and name in {
            str(local.get("tool_preset") or ""),
            str(tool_values.get("tool_preset") or ""),
            str(preset.get("preset_name") or ""),
        }:
            snapshot_uses += 1
            toolpath_id = str(snapshot.get("toolpath_id") or "").strip()
            if toolpath_id and toolpath_id in linked_ids:
                active_snapshot_uses += 1
            else:
                historical_snapshot_uses += 1
    return {
        "profiles": profile_uses,
        "associations": association_uses,
        "snapshots": snapshot_uses,
        "active_snapshots": active_snapshot_uses,
        "historical_snapshots": historical_snapshot_uses,
    }


def overlay_frozen_toolpaths(
    program: Mapping[str, Any],
    snapshots: Sequence[Mapping[str, Any]],
    associations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replace live preset motions with the active frozen snapshot for each path."""

    if not snapshots:
        return dict(program)
    selected = active_toolpath_snapshots(snapshots, associations)
    if not selected:
        return dict(program)
    by_path: dict[str, Mapping[str, Any]] = {}
    for snapshot in selected:
        if not isinstance(snapshot, Mapping):
            continue
        for path in snapshot.get("paths") or ():
            if isinstance(path, Mapping) and path.get("path_key"):
                by_path[str(path.get("path_key"))] = {
                    "path": path,
                    "snapshot": snapshot,
                }
    if not by_path:
        return dict(program)
    operations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for operation in program.get("operations") or ():
        if not isinstance(operation, Mapping):
            continue
        toolpaths: list[dict[str, Any]] = []
        for path in operation.get("toolpaths") or ():
            if not isinstance(path, Mapping):
                continue
            key = str(path.get("path_key") or "")
            frozen = by_path.get(key)
            if frozen is None:
                toolpaths.append(dict(path))
                continue
            seen.add(key)
            snapshot = frozen["snapshot"]
            frozen_path = frozen["path"]
            preset = _copy(snapshot.get("preset") if isinstance(snapshot.get("preset"), Mapping) else {})
            preset["safe_z_mm"] = snapshot.get("safe_z_mm")
            toolpaths.append(
                {
                    **dict(path),
                    "points": deepcopy(frozen_path.get("points") or []),
                    "motions": deepcopy(frozen_path.get("motions") or []),
                    "closed": bool(frozen_path.get("closed")),
                    "preset": preset,
                    "preset_name": str(preset.get("preset_name") or path.get("preset_name") or ""),
                    "ready": True,
                    "issues": [],
                    "safe_z_mm": snapshot.get("safe_z_mm"),
                    "home": _copy(snapshot.get("home") if isinstance(snapshot.get("home"), Mapping) else {}),
                }
            )
        cloned = dict(operation)
        cloned["toolpaths"] = toolpaths
        operations.append(cloned)
    missing = [key for key in by_path if key not in seen]
    if missing:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for key in missing:
            snapshot = by_path[key]["snapshot"]
            frozen_path = by_path[key]["path"]
            operation_key = str(frozen_path.get("operation_key") or "cut_path")
            preset = _copy(snapshot.get("preset") if isinstance(snapshot.get("preset"), Mapping) else {})
            grouped.setdefault(operation_key, []).append(
                {
                    "path_key": key,
                    "operation_key": operation_key,
                    "dxf_layer": frozen_path.get("dxf_layer") or "",
                    "piece_instance_id": frozen_path.get("piece_instance_id") or "",
                    "closed": bool(frozen_path.get("closed")),
                    "points": deepcopy(frozen_path.get("points") or []),
                    "motions": deepcopy(frozen_path.get("motions") or []),
                    "preset": preset,
                    "preset_name": str(preset.get("preset_name") or ""),
                    "ready": True,
                    "issues": [],
                    "safe_z_mm": snapshot.get("safe_z_mm"),
                    "home": _copy(snapshot.get("home") if isinstance(snapshot.get("home"), Mapping) else {}),
                    "sequence": 0,
                }
            )
        for operation_key, toolpaths in grouped.items():
            operations.append(
                {
                    "operation_key": operation_key,
                    "dxf_layer": str(toolpaths[0].get("dxf_layer") or ""),
                    "sequence": len(operations) + 1,
                    "toolpaths": toolpaths,
                }
            )
    payload = dict(program)
    payload["operations"] = operations
    return payload


def machining_public_view(
    *,
    profiles: Sequence[Mapping[str, Any]],
    associations: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
    catalog: Sequence[MachinableVector],
) -> dict[str, Any]:
    active_ids = {
        str(snapshot.get("toolpath_id") or "")
        for snapshot in active_toolpath_snapshots(snapshots, associations)
    }
    return {
        "profiles": [_copy(row) for row in profiles if isinstance(row, Mapping)],
        "associations": [_copy(row) for row in associations if isinstance(row, Mapping)],
        "toolpaths": [
            {
                "toolpath_id": row.get("toolpath_id"),
                "name": row.get("name"),
                "association_id": row.get("association_id"),
                "profile_id": row.get("profile_id"),
                "vector_ids": list(row.get("vector_ids") or []),
                "safe_z_mm": row.get("safe_z_mm"),
                "home": _copy(row.get("home") if isinstance(row.get("home"), Mapping) else {}),
                "preset": _copy(row.get("preset") if isinstance(row.get("preset"), Mapping) else {}),
                "active": str(row.get("toolpath_id") or "") in active_ids,
                "superseded_by": str(row.get("superseded_by") or ""),
            }
            for row in snapshots
            if isinstance(row, Mapping)
        ],
        "availability": association_availability(catalog, associations),
    }


__all__ = [
    "BALL_NOSE",
    "LEGACY_RATE_UNITS_MM_MIN",
    "RATE_UNITS_MM_SEC",
    "SELECTION_LAYER",
    "SELECTION_SHEET_PERIMETER",
    "SELECTION_VECTORS",
    "SUPPORTED_TOOL_TYPES",
    "TOOL_UNITS_MM",
    "ArtcamToolValues",
    "MachinableVector",
    "MachiningSetupError",
    "active_toolpath_snapshots",
    "append_snapshot",
    "canonical_tool_copy",
    "artcam_tool_storage",
    "assert_physical_tool_consistency",
    "association_availability",
    "calculate_toolpath_snapshot",
    "local_preset_payload",
    "machining_public_view",
    "machining_tool_uses",
    "nc_toolpath_fingerprint_rows",
    "release_stale_toolpath_links",
    "new_machining_id",
    "normalize_artcam_tool",
    "normalize_associations",
    "normalize_profile",
    "normalize_profiles",
    "overlay_frozen_toolpaths",
    "selection_coverage",
    "synthetic_preset_name",
    "tool_copy_from_stored",
    "vectors_from_paths",
]
