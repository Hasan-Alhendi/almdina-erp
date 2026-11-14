"""ArtCAM-style tools, profiles, vector association, and frozen toolpaths.

A tool definition is independent of every profile that copies it. A profile is
independent of every association that copies it. A calculated toolpath keeps
its own snapshot, so later edits do not rewrite it.

A selectable vector is one machined shape. A path key with a single shape
keeps that key. Shapes that share a path key are distinct, and depth passes
of one shape stay together. List order and SVG order are not identities.
Sheet perimeter uses the existing connected-perimeter path key and is offered
only when that path is in the machinable catalog.
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
from almdina_erp.almdina_erp.domain.cnc.program import (
    CHAIN_TOLERANCE_MM,
    _identity,
    _motions,
    _pass_depths,
    direction_invariant_identity,
    selectable_vector_id,
    stamp_selectable_vector_ids,
)
from almdina_erp.almdina_erp.domain.cnc.tool_preset import (
    MAX_DEPTH_MM,
    MAX_DIAMETER_MM,
    MAX_FEED_MM_MIN,
    MAX_PLUNGE_MM_MIN,
    MAX_SPINDLE_RPM,
    ToolPresetError,
    ToolPresetValues,
    assert_single_tool_for_file,
    mm_per_min_from_sec,
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

SELECTION_LAYER = "layer"
SELECTION_VECTORS = "vectors"
SELECTION_SELECTED_VECTORS = "selected_vectors"
SELECTION_SHEET_PERIMETER = "sheet_perimeter"
_UNRESOLVED_SELECTION = frozenset({"selected_vectors_pending", "sheet_perimeter_unavailable"})


class MachiningSetupError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}:{detail}")
        self.code = code
        self.detail = detail


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
    from almdina_erp.almdina_erp.domain.cnc.tool_preset import (
        ToolPresetError,
        catalog_tool_number,
    )

    try:
        return catalog_tool_number(value)
    except ToolPresetError as exc:
        raise MachiningSetupError("tool_number_invalid") from exc


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
    raw_tool_number = raw.get("tool_number")
    if raw_tool_number in (None, ""):
        raw_tool_number = raw.get("tool_number_display")
    tool_number, display = _tool_number(raw_tool_number)
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
    stepover_size = _finite(
        raw.get("stepover_size_mm", raw.get("stepover_size")),
        "stepover_invalid",
        lower=0,
        upper=MAX_DIAMETER_MM,
        inclusive_lower=False,
    )
    if stepover_size > diameter + 1e-9:
        raise MachiningSetupError("stepover_invalid")
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
        stepover_size_mm=round(stepover_size, 3),
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
        "tool_number": str(tool.tool_number_display),
        "tool_diameter_mm": tool.diameter_mm,
        "spindle_speed_rpm": tool.spindle_speed_rpm,
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
            "diameter_mm": stored.get("tool_diameter_mm", stored.get("diameter_mm")),
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
        feed = mm_per_min_from_sec(tool_values.get("feed_rate_mm_sec") or 0)
        plunge = mm_per_min_from_sec(tool_values.get("plunge_rate_mm_sec") or 0)
        stepdown = tool_values.get("stepdown_mm")
    else:
        feed = tool_values.get("feed_rate_mm_min")
        plunge = tool_values.get("plunge_rate_mm_min")
        stepdown = tool_values.get("stepdown_mm", tool_values.get("pass_depth_mm"))
    final_depth = _depth_mm(local.get("final_depth_mm"))
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
        vector_id = str(row.get("vector_id") or row.get("path_key") or "").strip()
        operation_key = str(row.get("operation_key") or "").strip()
        if not vector_id or not operation_key or vector_id in seen:
            continue
        if vector_id == "cut_path:internals":
            continue
        seen.add(vector_id)
        layer_name = str(row.get("dxf_layer") or "")
        if vector_id == SHEET_PERIMETER_PATH_KEY:
            layer_name = "SHEET_PERIMETER"
        vectors.append(
            MachinableVector(
                vector_id=vector_id,
                operation_key=operation_key,
                dxf_layer=layer_name,
                piece_instance_id=str(row.get("piece_instance_id") or ""),
                label=str(row.get("piece_label") or row.get("label") or vector_id),
            )
        )
    return tuple(vectors)


def _retain_saved_perimeter(
    selection: Mapping[str, Any],
    stored_ids: Any,
    covered: tuple[str, ...],
    index: Mapping[str, MachinableVector],
) -> tuple[str, ...]:
    """Keep a perimeter that an older CUT_PATH association already owns.

    New layer selections do not include the connected perimeter. A saved row
    that already lists it keeps that ownership until the user edits it.
    """

    if str(selection.get("kind") or "") != SELECTION_LAYER:
        return covered
    if str(selection.get("operation_key") or "") != "cut_path":
        return covered
    if isinstance(stored_ids, (str, bytes)) or not isinstance(stored_ids, Sequence):
        return covered
    if SHEET_PERIMETER_PATH_KEY not in {str(item or "") for item in stored_ids}:
        return covered
    if SHEET_PERIMETER_PATH_KEY not in index or SHEET_PERIMETER_PATH_KEY in covered:
        return covered
    return tuple(covered) + (SHEET_PERIMETER_PATH_KEY,)


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
            if vector is None:
                raise MachiningSetupError("vector_not_machinable")
            if vector_id not in covered:
                covered.append(vector_id)
        return tuple(covered)
    if kind == SELECTION_SELECTED_VECTORS:
        raw_ids = selection.get("vector_ids") or ()
        if isinstance(raw_ids, (str, bytes)) or not isinstance(raw_ids, Sequence) or not raw_ids:
            raise MachiningSetupError("selected_vectors_pending")
        return selection_coverage({**dict(selection), "kind": SELECTION_VECTORS}, catalog)
    raise MachiningSetupError("selection_invalid")


def _local_from_profile(profile: Mapping[str, Any], raw_local: Any) -> dict[str, Any]:
    if isinstance(raw_local, Mapping) and raw_local:
        local = _copy(raw_local)
    else:
        local = _copy(profile)
    local["profile_id"] = profile["profile_id"]
    explicit_tool = ""
    if isinstance(raw_local, Mapping):
        explicit_tool = str(raw_local.get("tool_preset") or "").strip()
        supplied = raw_local.get("tool_values") if isinstance(raw_local.get("tool_values"), Mapping) else {}
        explicit_tool = explicit_tool or str(supplied.get("tool_preset") or supplied.get("description") or "").strip()
    local["tool_preset"] = explicit_tool or str(profile.get("tool_preset") or "")
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
    keep_unresolved: bool = False,
) -> list[dict[str, Any]]:
    by_profile = {str(profile.get("profile_id") or ""): profile for profile in profiles}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    covered_owner: dict[str, str] = {}
    owner_names: dict[str, str] = {}
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
        try:
            covered = selection_coverage(selection, catalog)
            conflict = ""
        except MachiningSetupError as exc:
            if keep_unresolved and exc.code in _UNRESOLVED_SELECTION:
                covered = ()
                conflict = exc.code
            else:
                raise
        covered = _retain_saved_perimeter(
            selection,
            row.get("vector_ids"),
            covered,
            _catalog_index(catalog),
        )
        association_name = str(row.get("name") or "").strip()[:_NAME_LIMIT]
        for vector_id in covered:
            owner = covered_owner.get(vector_id)
            if owner is not None:
                if vector_id == SHEET_PERIMETER_PATH_KEY:
                    raise MachiningSetupError(
                        "sheet_perimeter_already_assigned",
                        owner_names.get(vector_id) or owner,
                    )
                raise MachiningSetupError("vector_already_assigned")
            covered_owner[vector_id] = association_id
            owner_names[vector_id] = association_name or association_id
        local = _local_from_profile(profile, row.get("local_values"))
        seen.add(association_id)
        normalized.append(
            {
                "association_id": association_id,
                "name": str(row.get("name") or "").strip()[:_NAME_LIMIT],
                "selection": _copy(selection),
                "profile_id": profile["profile_id"],
                "local_values": local,
                "toolpath_name": str(row.get("toolpath_name") or "").strip(),
                "toolpath_id": str(row.get("toolpath_id") or "").strip(),
                "vector_ids": list(covered),
                "conflict": conflict,
                "geometry_ready": not conflict,
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

    from almdina_erp.almdina_erp.domain.cnc.operations import ILLUSTRATIVE_DXF_LAYERS

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
        if str(vectors[0].dxf_layer or "").strip().upper() in {name.upper() for name in ILLUSTRATIVE_DXF_LAYERS}:
            continue
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
    """Last toolpath for each path key. Prefer geometry_groups for selection."""

    found: dict[str, Mapping[str, Any]] = {}
    for operation in program.get("operations") or ():
        if not isinstance(operation, Mapping):
            continue
        for path in operation.get("toolpaths") or ():
            if isinstance(path, Mapping) and path.get("path_key"):
                found[str(path.get("path_key"))] = path
    return found


def geometry_groups(program: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One group per machined shape. Depth-pass copies of that shape stay together."""

    buckets: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    order: list[tuple[str, str]] = []
    for operation in program.get("operations") or ():
        if not isinstance(operation, Mapping):
            continue
        for path in operation.get("toolpaths") or ():
            if not isinstance(path, Mapping) or not path.get("path_key"):
                continue
            key = str(path.get("path_key") or "")
            try:
                shape = shape_id(path)
            except MachiningSetupError:
                shape = str(path.get("shape_id") or "")
            token = (key, shape)
            if token not in buckets:
                buckets[token] = []
                order.append(token)
            buckets[token].append(path)
    shapes_for_key: dict[str, set[str]] = {}
    for key, shape in order:
        shapes_for_key.setdefault(key, set()).add(shape)
    groups: list[dict[str, Any]] = []
    for key, shape in order:
        paths = buckets[(key, shape)]
        issues: list[str] = []
        for path in paths:
            for code in path.get("issues") or ():
                text = str(code or "")
                if text and text not in issues:
                    issues.append(text)
        ready = all(bool(path.get("ready")) for path in paths) and any(
            len(path.get("points") or ()) >= 2 for path in paths
        )
        groups.append(
            {
                "path_key": key,
                "shape_id": shape,
                "vector_id": selectable_vector_id(
                    key,
                    shape,
                    shared=len(shapes_for_key.get(key) or ()) > 1,
                ),
                "paths": paths,
                "ready": ready,
                "issues": issues,
            }
        )
    return groups


def resolve_geometry_group(program: Mapping[str, Any], vector_id: str) -> dict[str, Any]:
    """Find the shape a saved or selected vector id refers to.

    A legacy path key still selects its shape when that key has only one shape.
    It does not select every shape that happens to share the key.
    """

    wanted = str(vector_id or "").strip()
    if not wanted:
        raise MachiningSetupError("vector_not_machinable")
    groups = geometry_groups(program)
    exact = [group for group in groups if group["vector_id"] == wanted]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise MachiningSetupError("vector_identity_ambiguous")
    legacy = [group for group in groups if group["path_key"] == wanted]
    if len(legacy) == 1:
        return legacy[0]
    if len(legacy) > 1:
        raise MachiningSetupError("vector_identity_ambiguous")
    raise MachiningSetupError("vector_not_machinable")


def catalog_rows_from_program(program: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Selectable vectors taken from the compiled program, not from draw order."""

    rows: list[dict[str, Any]] = []
    for group in geometry_groups(program):
        first = group["paths"][0]
        layer = str(first.get("operational_layer") or first.get("dxf_layer") or "")
        rows.append(
            {
                "vector_id": group["vector_id"],
                "path_key": group["path_key"],
                "shape_id": group["shape_id"],
                "operation_key": str(first.get("operation_key") or ""),
                "dxf_layer": layer,
                "piece_instance_id": str(first.get("piece_instance_id") or ""),
                "label": str(first.get("piece_label") or group["vector_id"]),
                "ready": group["ready"],
                "issues": list(group["issues"]),
            }
        )
    return rows


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
    request_id: str | None = None,
) -> dict[str, Any]:
    """Freeze one calculated toolpath from the association's own values."""

    name = _text(toolpath_name or association.get("toolpath_name") or association.get("name"), "toolpath_name_required")
    if association.get("conflict"):
        raise MachiningSetupError(str(association.get("conflict")))
    selection = association.get("selection") if isinstance(association.get("selection"), Mapping) else {}
    if str(selection.get("kind") or "") == SELECTION_SELECTED_VECTORS and not association.get("vector_ids"):
        raise MachiningSetupError("selected_vectors_pending")
    local = association.get("local_values") if isinstance(association.get("local_values"), Mapping) else {}
    preset = _preset_from_local(local)
    current_association = str(association.get("association_id") or "")
    previous = [
        _preset_from_local(snapshot.get("local_values") or {})
        for snapshot in existing_snapshots
        if isinstance(snapshot, Mapping)
        and not snapshot.get("archived")
        and not snapshot.get("superseded_by")
        and str(snapshot.get("association_id") or "") not in {"", current_association}
    ]
    _assert_single_physical_tool([*previous, preset])
    vector_ids = [str(vector_id) for vector_id in association.get("vector_ids") or ()]
    if not vector_ids:
        raise MachiningSetupError("vector_not_machinable")
    paths: list[dict[str, Any]] = []
    resolved_ids: list[str] = []
    for vector_id in vector_ids:
        group = resolve_geometry_group(program, vector_id)
        if not group["ready"]:
            issues = list(group.get("issues") or [])
            raise MachiningSetupError(str(issues[0] if issues else "vector_not_machinable"))
        path = next(item for item in group["paths"] if len(item.get("points") or ()) >= 2)
        points = _points(path)
        if len(points) < 2:
            raise MachiningSetupError("geometry_invalid")
        closed = bool(path.get("closed"))
        resolved = str(group["vector_id"])
        if resolved not in resolved_ids:
            resolved_ids.append(resolved)
        paths.append(
            {
                "path_key": str(group["path_key"]),
                "vector_id": resolved,
                "shape_id": str(group["shape_id"] or ""),
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
        "request_id": str(request_id or "").strip(),
        "name": name,
        "association_id": str(association.get("association_id") or ""),
        "profile_id": str(association.get("profile_id") or ""),
        "vector_ids": resolved_ids,
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
    *,
    live_association_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Keep calculation order. A new snapshot does not rewrite an older one.

    A historical or superseded name does not block a new calculation. Recalculating
    the same association may keep its name. Another live association may not.
    """

    stored = [_copy(row) for row in snapshots if isinstance(row, Mapping)]
    incoming = _copy(snapshot)
    if any(row.get("toolpath_id") == incoming.get("toolpath_id") for row in stored):
        raise MachiningSetupError("toolpath_duplicate")
    live = None if live_association_ids is None else {str(item) for item in live_association_ids}
    incoming_association = str(incoming.get("association_id") or "")
    for row in stored:
        if row.get("name") != incoming.get("name") or not incoming.get("name"):
            continue
        if row.get("superseded_by") or row.get("archived"):
            continue
        if str(row.get("association_id") or "") == incoming_association:
            continue
        if live is not None and str(row.get("association_id") or "") not in live:
            continue
        raise MachiningSetupError("toolpath_name_duplicate")
    stored.append(incoming)
    return stored


def assert_physical_tool_consistency(
    associations: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]] = (),
) -> None:
    """One file keeps one physical tool number; diameter may vary by profile."""

    linked = {
        str(row.get("toolpath_id") or "").strip()
        for row in associations
        if isinstance(row, Mapping) and str(row.get("toolpath_id") or "").strip()
    }
    presets = [
        _preset_from_local(row["local_values"])
        for row in associations
        if isinstance(row, Mapping) and isinstance(row.get("local_values"), Mapping)
    ]
    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping) or snapshot.get("archived") or snapshot.get("superseded_by"):
            continue
        toolpath_id = str(snapshot.get("toolpath_id") or "").strip()
        if not toolpath_id or toolpath_id not in linked:
            continue
        local = snapshot.get("local_values")
        if isinstance(local, Mapping):
            presets.append(_preset_from_local(local))
    _assert_single_physical_tool(presets)


def synthetic_preset_name(association_id: str) -> str:
    return f"artcam-local:{association_id}"


def local_preset_payload(local: Mapping[str, Any]) -> dict[str, Any]:
    preset = _preset_from_local(local)
    tool_values = local.get("tool_values") if isinstance(local.get("tool_values"), Mapping) else {}
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
        "stepover_size_mm": tool_values.get("stepover_size_mm"),
        "stepover_percent": tool_values.get("stepover_percent"),
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
    tool_values = local.get("tool_values") if isinstance(local.get("tool_values"), Mapping) else {}
    return {
        "vectors": [str(vector_id) for vector_id in vector_ids],
        "tool_number": preset.tool_number,
        "diameter_mm": _canon_number(preset.tool_diameter_mm),
        "final_depth_mm": _canon_number(preset.final_depth_mm),
        "pass_depth_mm": _canon_number(preset.pass_depth_mm),
        "stepover_size_mm": _canon_number(tool_values.get("stepover_size_mm")),
        "stepover_percent": _canon_number(tool_values.get("stepover_percent")),
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
    by_id = {
        str(snapshot.get("toolpath_id") or ""): snapshot
        for snapshot in rows
        if not snapshot.get("archived")
    }
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
    groups = geometry_groups(program)
    shared_keys = {
        group["path_key"]
        for group in groups
        if sum(1 for other in groups if other["path_key"] == group["path_key"]) > 1
    }
    vector_by_object = {id(path): group["vector_id"] for group in groups for path in group["paths"]}
    by_path: dict[str, Mapping[str, Any]] = {}
    for snapshot in selected:
        if not isinstance(snapshot, Mapping) or snapshot.get("archived"):
            continue
        for path in snapshot.get("paths") or ():
            if not isinstance(path, Mapping) or not path.get("path_key"):
                continue
            key = str(path.get("path_key") or "")
            vector = str(path.get("vector_id") or "")
            shape = str(path.get("shape_id") or "")
            if not vector and shape and key in shared_keys:
                vector = selectable_vector_id(key, shape, shared=True)
            if not vector and key in shared_keys:
                continue
            by_path[vector or key] = {"path": path, "snapshot": snapshot}
    if not by_path:
        return dict(program)
    operations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for operation in program.get("operations") or ():
        if not isinstance(operation, Mapping):
            continue
        toolpaths: list[dict[str, Any]] = []
        emitted: set[str] = set()
        for path in operation.get("toolpaths") or ():
            if not isinstance(path, Mapping):
                continue
            key = vector_by_object.get(id(path)) or str(path.get("vector_id") or path.get("path_key") or "")
            frozen = by_path.get(key)
            if frozen is not None and key in emitted:
                continue
            if frozen is None:
                toolpaths.append(dict(path))
                continue
            emitted.add(key)
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
                    "path_key": str(frozen_path.get("path_key") or key),
                    "vector_id": str(frozen_path.get("vector_id") or key),
                    "shape_id": str(frozen_path.get("shape_id") or ""),
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


def order_program_by_associations(
    program: Mapping[str, Any],
    associations: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Order posted paths by association identity, even when a layer repeats."""

    payload = dict(program)
    rows = [row for row in (associations or ()) if isinstance(row, Mapping)]
    if not rows:
        return payload
    owner: dict[str, int] = {}
    for index, association in enumerate(rows):
        for vector_id in association.get("vector_ids") or ():
            owner.setdefault(str(vector_id), index)
    buckets: dict[int, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {index: [] for index in range(len(rows))}
    leftovers: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for operation in payload.get("operations") or ():
        if not isinstance(operation, Mapping):
            continue
        for path in operation.get("toolpaths") or ():
            if not isinstance(path, Mapping):
                continue
            index = owner.get(str(path.get("path_key") or ""))
            if index is None:
                leftovers.append((operation, path))
            else:
                buckets[index].append((operation, path))

    def emit(items: list[tuple[Mapping[str, Any], Mapping[str, Any]]]) -> None:
        grouped: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for operation, path in items:
            key = str(operation.get("operation_key") or "")
            if key not in grouped:
                grouped[key] = {"operation": operation, "paths": []}
                order.append(key)
            grouped[key]["paths"].append(dict(path))
        for key in order:
            cloned = dict(grouped[key]["operation"])
            cloned["toolpaths"] = grouped[key]["paths"]
            cloned["sequence"] = len(operations) + 1
            operations.append(cloned)

    operations: list[dict[str, Any]] = []
    for index in range(len(rows)):
        if buckets[index]:
            emit(buckets[index])
    if leftovers:
        emit(leftovers)
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


_MOTION_KINDS = frozenset({"travel", "plunge", "cut", "retract"})


def path_geometry_id(path: Mapping[str, Any]) -> str:
    """Directed identity of the unreversed polyline. A new plan must not inherit an old reverse."""

    points = tuple(_points(path))
    return _identity(points, bool(path.get("closed")))


def shape_id(path: Mapping[str, Any]) -> str:
    """Direction-invariant identity of one machined shape.

    Depth passes of the same toolpath share it. A different polyline that only
    shares the source vector key does not.
    """

    return direction_invariant_identity(_points(path), bool(path.get("closed")))


def normalize_reversed_paths(rows: Sequence[Any] | None) -> list[dict[str, str]]:
    """Stable reverse records. A legacy row has no shape id and stays one per path key."""

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows or ():
        if isinstance(row, str):
            key = row.strip()
            geometry_id = ""
            shape = ""
        elif isinstance(row, Mapping):
            key = str(row.get("path_key") or "").strip()
            geometry_id = str(row.get("geometry_id") or "").strip()
            shape = str(row.get("shape_id") or "").strip()
        else:
            continue
        token = f"{key}\n{shape}" if shape else key
        if not key or token in seen:
            continue
        seen.add(token)
        item = {"path_key": key, "geometry_id": geometry_id}
        if shape:
            item["shape_id"] = shape
        normalized.append(item)
    normalized.sort(key=lambda item: (item["path_key"], item.get("shape_id", "")))
    return normalized


def _same_point(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return math.hypot(left[0] - right[0], left[1] - right[1]) <= CHAIN_TOLERANCE_MM


def reverse_operational_points(
    points: Sequence[tuple[float, float]],
    *,
    closed: bool,
) -> list[tuple[float, float]]:
    """Reverse travel direction without moving the geometric vertices."""

    sequence = [(float(point[0]), float(point[1])) for point in points]
    if len(sequence) < 2:
        raise MachiningSetupError("path_reverse_unsupported")
    if closed and len(sequence) > 2 and _same_point(sequence[0], sequence[-1]):
        sequence = sequence[:-1]
    if len(sequence) < 2:
        raise MachiningSetupError("path_reverse_unsupported")
    return list(reversed(sequence))


def _motion_sequences(path: Mapping[str, Any]) -> tuple[list[float], list[list[tuple[float, float]]]]:
    depths: list[float] = []
    sequences: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] | None = None
    for motion in path.get("motions") or ():
        if not isinstance(motion, Mapping):
            raise MachiningSetupError("path_reverse_unsupported")
        kind = str(motion.get("kind") or "")
        if kind not in _MOTION_KINDS:
            raise MachiningSetupError("path_reverse_unsupported")
        if kind == "plunge":
            current = [(_finite_motion_point(motion))]
            sequences.append(current)
            depth = motion.get("depth_mm")
            depths.append(float(depth) if depth not in (None, "") else 0.0)
            continue
        if kind == "cut":
            if current is None:
                raise MachiningSetupError("path_reverse_unsupported")
            current.append(_finite_motion_point(motion))
    return depths, sequences


def _finite_motion_point(motion: Mapping[str, Any]) -> tuple[float, float]:
    try:
        x = float(motion.get("x_mm"))
        y = float(motion.get("y_mm"))
    except (TypeError, ValueError) as exc:
        raise MachiningSetupError("path_reverse_unsupported") from exc
    if not math.isfinite(x) or not math.isfinite(y):
        raise MachiningSetupError("path_reverse_unsupported")
    return (x, y)


def _sequences_match(sequences: Sequence[Sequence[tuple[float, float]]]) -> bool:
    if len(sequences) < 2:
        return True
    first = sequences[0]
    for other in sequences[1:]:
        if len(other) != len(first):
            return False
        if any(not _same_point(left, right) for left, right in zip(first, other, strict=True)):
            return False
    return True


def _reverse_one_path(path: Mapping[str, Any], geometry_id: str) -> dict[str, Any]:
    if any(
        isinstance(point, Sequence)
        and not isinstance(point, (str, bytes))
        and len(point) != 2
        for point in path.get("points") or ()
    ):
        raise MachiningSetupError("path_reverse_unsupported")
    current_id = path_geometry_id(path)
    if geometry_id and geometry_id != current_id:
        raise MachiningSetupError("path_reverse_stale")
    points = _points(path)
    reversed_points = reverse_operational_points(points, closed=bool(path.get("closed")))
    updated = dict(path)
    updated["points"] = [[point[0], point[1]] for point in reversed_points]
    updated["reversed"] = True
    motions = path.get("motions") or ()
    if not motions:
        return updated
    depths, sequences = _motion_sequences(path)
    if not depths or not _sequences_match(sequences):
        raise MachiningSetupError("path_reverse_unsupported")
    updated["motions"] = _motions_for_depths(
        reversed_points,
        bool(path.get("closed")),
        depths,
    )
    return updated


def _motions_for_depths(
    points: Sequence[tuple[float, float]],
    closed: bool,
    depths: Sequence[float],
) -> list[dict[str, Any]]:
    motions = _motions(points, closed=closed, depths=tuple(depths))
    return [
        {
            "kind": motion.kind,
            "x_mm": motion.x_mm,
            "y_mm": motion.y_mm,
            "depth_mm": motion.depth_mm,
        }
        for motion in motions
    ]


_DIRECTION_BLOCK_CODES = frozenset({
    "path_reverse_unsupported",
    "path_reverse_stale",
    "path_reverse_missing",
    "path_reverse_ambiguous",
})


def reversed_direction_block(program: Mapping[str, Any] | None) -> str:
    """Return the first saved-direction failure, or an empty string."""

    if not isinstance(program, Mapping):
        return ""
    if program.get("direction_blocked"):
        for issue in program.get("issues") or ():
            if isinstance(issue, Mapping) and str(issue.get("code") or "") in _DIRECTION_BLOCK_CODES:
                return str(issue.get("code") or "")
        return "path_reverse_unsupported"
    for issue in program.get("issues") or ():
        if isinstance(issue, Mapping) and str(issue.get("code") or "") in _DIRECTION_BLOCK_CODES:
            return str(issue.get("code") or "")
    return ""


def apply_reversed_directions(
    program: Mapping[str, Any],
    records: Sequence[Any] | None,
) -> dict[str, Any]:
    """Reverse saved path directions. A record that cannot be applied blocks NC."""

    payload = deepcopy(dict(program))
    saved = normalize_reversed_paths(records)
    if not saved:
        return payload
    by_key: dict[str, list[dict[str, str]]] = {}
    for row in saved:
        by_key.setdefault(row["path_key"], []).append(row)
    catalog: dict[str, list[Mapping[str, Any]]] = {}
    for operation in payload.get("operations") or ():
        if not isinstance(operation, Mapping):
            continue
        for path in operation.get("toolpaths") or ():
            if isinstance(path, Mapping):
                catalog.setdefault(str(path.get("path_key") or ""), []).append(path)
    ambiguous = {
        key
        for key, rows in by_key.items()
        if any(not row.get("shape_id") for row in rows)
        and len({shape_id(path) for path in catalog.get(key, ())}) > 1
    }
    issues = [
        dict(issue)
        for issue in payload.get("issues") or ()
        if isinstance(issue, Mapping)
        and str(issue.get("code") or "") not in _DIRECTION_BLOCK_CODES
    ]
    matched: set[tuple[str, str]] = set()
    blocked = False
    operations: list[dict[str, Any]] = []
    for operation in payload.get("operations") or ():
        if not isinstance(operation, Mapping):
            continue
        cloned = dict(operation)
        toolpaths: list[dict[str, Any]] = []
        for path in operation.get("toolpaths") or ():
            if not isinstance(path, Mapping):
                toolpaths.append(path)
                continue
            key = str(path.get("path_key") or "")
            rows = by_key.get(key) or []
            if not rows or key in ambiguous:
                toolpaths.append(dict(path))
                continue
            current_shape = shape_id(path)
            chosen = next((row for row in rows if row.get("shape_id") == current_shape), None)
            if chosen is None:
                chosen = next((row for row in rows if not row.get("shape_id")), None)
            if chosen is None:
                toolpaths.append(dict(path))
                continue
            matched.add((key, str(chosen.get("shape_id") or "")))
            try:
                toolpaths.append(_reverse_one_path(path, chosen.get("geometry_id") or ""))
            except MachiningSetupError as exc:
                blocked = True
                issues.append({"code": exc.code, "path_key": key, "shape_id": current_shape})
                failed = dict(path)
                failed["issues"] = [*(failed.get("issues") or ()), exc.code]
                failed["ready"] = False
                toolpaths.append(failed)
        cloned["toolpaths"] = toolpaths
        operations.append(cloned)
    for key in ambiguous:
        blocked = True
        issues.append({"code": "path_reverse_ambiguous", "path_key": key})
        matched.add((key, ""))
    for row in saved:
        token = (row["path_key"], str(row.get("shape_id") or ""))
        if token in matched or (row["path_key"], "") in matched:
            continue
        if row["path_key"] in ambiguous:
            continue
        blocked = True
        issues.append({
            "code": "path_reverse_missing",
            "path_key": row["path_key"],
            "shape_id": str(row.get("shape_id") or ""),
        })
    payload["operations"] = operations
    payload["issues"] = issues
    if blocked:
        payload["direction_blocked"] = True
        payload["nc_export_ready"] = False
        payload["ready"] = False
    return payload


def _toolpaths_for_key(program: Mapping[str, Any], path_key: str) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = []
    for operation in program.get("operations") or ():
        if not isinstance(operation, Mapping):
            continue
        for path in operation.get("toolpaths") or ():
            if isinstance(path, Mapping) and str(path.get("path_key") or "") == path_key:
                found.append(path)
    return found


def toggle_reversed_path(
    records: Sequence[Any] | None,
    program: Mapping[str, Any],
    path_key: str,
    shape: str = "",
    *,
    clear: bool = False,
) -> list[dict[str, str]]:
    """Add or remove one saved direction. An ambiguous legacy row is not guessed."""

    key = str(path_key or "").strip()
    wanted_shape = str(shape or "").strip()
    if not key:
        raise MachiningSetupError("path_reverse_unsupported")
    current = normalize_reversed_paths(records)

    def without(predicate) -> list[dict[str, str]]:
        return [row for row in current if not predicate(row)]

    exact = [
        row for row in current
        if row["path_key"] == key and wanted_shape and row.get("shape_id") == wanted_shape
    ]
    legacy = [row for row in current if row["path_key"] == key and not row.get("shape_id")]
    if clear:
        if wanted_shape:
            return without(
                lambda row: row["path_key"] == key and row.get("shape_id", "") in {"", wanted_shape}
            )
        return without(lambda row: row["path_key"] == key)
    if exact:
        return without(lambda row: row["path_key"] == key and row.get("shape_id") == wanted_shape)
    paths = _toolpaths_for_key(program, key)
    if not paths:
        raise MachiningSetupError("path_reverse_missing")
    shapes: list[str] = []
    for path in paths:
        current_shape = shape_id(path)
        if current_shape not in shapes:
            shapes.append(current_shape)
    if legacy:
        if len(shapes) > 1:
            raise MachiningSetupError("path_reverse_ambiguous")
        return without(lambda row: row["path_key"] == key and not row.get("shape_id"))
    if not wanted_shape:
        if len(shapes) != 1:
            raise MachiningSetupError("path_reverse_ambiguous")
        wanted_shape = shapes[0]
    targets = [path for path in paths if shape_id(path) == wanted_shape]
    if not targets:
        raise MachiningSetupError("path_reverse_missing")
    geometry = path_geometry_id(targets[0])
    probe = apply_reversed_directions(
        {"operations": [{"toolpaths": [dict(path) for path in targets]}], "issues": []},
        [{"path_key": key, "geometry_id": geometry, "shape_id": wanted_shape}],
    )
    blocked = reversed_direction_block(probe)
    if blocked:
        raise MachiningSetupError(blocked)
    current.append({"path_key": key, "geometry_id": geometry, "shape_id": wanted_shape})
    return normalize_reversed_paths(current)


def _stamp_shape_ids(program: Mapping[str, Any]) -> dict[str, Any]:
    """Publish the identity of the geometry that will actually be machined."""

    payload = deepcopy(dict(program))
    operations: list[dict[str, Any]] = []
    for operation in payload.get("operations") or ():
        if not isinstance(operation, Mapping):
            operations.append(operation)
            continue
        cloned = dict(operation)
        toolpaths: list[Any] = []
        for path in operation.get("toolpaths") or ():
            if not isinstance(path, Mapping):
                toolpaths.append(path)
                continue
            updated = dict(path)
            try:
                updated["shape_id"] = shape_id(updated)
            except MachiningSetupError:
                updated["shape_id"] = ""
            toolpaths.append(updated)
        cloned["toolpaths"] = toolpaths
        operations.append(cloned)
    payload["operations"] = operations
    return stamp_selectable_vector_ids(payload)


def archive_association(
    associations: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
    association_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove one association from the active set and archive its snapshots.

    Archived snapshots stay for audit. They do not execute, reserve a name,
    or constrain the next physical tool. Historical NC files are untouched.
    """

    target = str(association_id or "").strip()
    if not target:
        raise MachiningSetupError("association_id_invalid")
    kept = [
        _copy(row)
        for row in associations
        if isinstance(row, Mapping) and str(row.get("association_id") or "") != target
    ]
    archived: list[dict[str, Any]] = []
    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping):
            continue
        row = _copy(snapshot)
        if str(row.get("association_id") or "") == target:
            row["archived"] = True
            if not row.get("superseded_by"):
                row["superseded_by"] = "archived"
        archived.append(row)
    return kept, archived


def drop_resurrected_associations(
    existing: Sequence[Mapping[str, Any]],
    incoming: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Ignore a stale save that tries to restore an association already removed."""

    live = {
        str(row.get("association_id") or "")
        for row in existing
        if isinstance(row, Mapping)
    }
    archived_ids = {
        str(snapshot.get("association_id") or "")
        for snapshot in snapshots
        if isinstance(snapshot, Mapping) and snapshot.get("archived")
    }
    blocked = archived_ids - live
    return [
        _copy(row)
        for row in incoming
        if isinstance(row, Mapping) and str(row.get("association_id") or "") not in blocked
    ]


def unreversed_operational_program(
    program: Mapping[str, Any],
    *,
    snapshots: Sequence[Mapping[str, Any]] | None = None,
    associations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Overlay and order the program before any saved direction is applied."""

    current = overlay_frozen_toolpaths(
        program,
        snapshots or (),
        associations=associations,
    )
    current = order_program_by_associations(current, associations)
    current = _refresh_effective_readiness(current)
    return _stamp_shape_ids(current)


def _refresh_effective_readiness(program: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute board readiness after frozen calculated paths replace live placeholders."""

    payload = deepcopy(dict(program))
    paths = [
        path
        for operation in payload.get("operations") or ()
        if isinstance(operation, Mapping)
        for path in operation.get("toolpaths") or ()
        if isinstance(path, Mapping)
    ]

    def executable(path: Mapping[str, Any]) -> bool:
        return bool(
            path.get("ready")
            and isinstance(path.get("points"), Sequence)
            and len(path.get("points") or ()) >= 2
            and isinstance(path.get("motions"), Sequence)
            and len(path.get("motions") or ()) > 0
            and not (path.get("issues") or ())
        )

    readiness_by_key: dict[str, list[bool]] = {}
    for path in paths:
        readiness_by_key.setdefault(str(path.get("path_key") or ""), []).append(executable(path))
    resolved_keys = {
        key for key, readiness in readiness_by_key.items()
        if key and readiness and all(readiness)
    }
    issues = [
        deepcopy(issue)
        for issue in payload.get("issues") or ()
        if not (
            isinstance(issue, Mapping)
            and str(issue.get("path_key") or "") in resolved_keys
        )
    ]
    ready = bool(paths) and not issues and all(executable(path) for path in paths)
    payload["issues"] = issues
    payload["geometry_ready"] = ready
    payload["ready"] = ready
    payload["nc_export_ready"] = ready
    return payload


def effective_operational_program(
    program: Mapping[str, Any],
    *,
    snapshots: Sequence[Mapping[str, Any]] | None = None,
    associations: Sequence[Mapping[str, Any]] | None = None,
    reversed_path_keys: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """One machining program for preview, reverse checks, and NC export."""

    current = unreversed_operational_program(
        program,
        snapshots=snapshots,
        associations=associations,
    )
    return apply_reversed_directions(current, reversed_path_keys)


__all__ = [
    "BALL_NOSE",
    "LEGACY_RATE_UNITS_MM_MIN",
    "RATE_UNITS_MM_SEC",
    "SELECTION_LAYER",
    "SELECTION_SELECTED_VECTORS",
    "SELECTION_SHEET_PERIMETER",
    "SELECTION_VECTORS",
    "SUPPORTED_TOOL_TYPES",
    "TOOL_UNITS_MM",
    "ArtcamToolValues",
    "MachinableVector",
    "MachiningSetupError",
    "apply_reversed_directions",
    "effective_operational_program",
    "normalize_reversed_paths",
    "reversed_direction_block",
    "path_geometry_id",
    "reverse_operational_points",
    "archive_association",
    "catalog_rows_from_program",
    "drop_resurrected_associations",
    "geometry_groups",
    "resolve_geometry_group",
    "shape_id",
    "toggle_reversed_path",
    "unreversed_operational_program",
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
    "order_program_by_associations",
    "overlay_frozen_toolpaths",
    "selection_coverage",
    "synthetic_preset_name",
    "tool_copy_from_stored",
    "vectors_from_paths",
]
