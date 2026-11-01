"""Canonical DXF layer catalog for cutting plans and the board editor.

A DXF layer is a display/export grouping. It is never a move group, board, or
door. Door affiliation is proven by geometry ownership or explicit snapshot
links, never by layer name alone.

CUT_PATH may contain manufacturing paths derived from several pieces; one path
must not be assumed to belong to one door. OFFCUT keeps its operational meaning
(deficient-board classification) and is not a name for pieces parked outside
boards.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.dxf_default_layer import DESIGNER_DEFAULT_LAYER
from almdina_erp.almdina_erp.domain.cutting.dxf_text_labels import (
    TEXT_LABEL_LAYER,
    TEXT_LABEL_LAYER_KEY,
)
from almdina_erp.almdina_erp.domain.orders.extra_addons import EXTRA_OVERLAY_LAYER_BY_KIND

BOARD_EDITOR_LAYER_SCHEMA_VERSION = 1

SHEET_OUTLINE_LAYER = "SHEET_OUTLINE"
CUT_PATH_LAYER = "CUT_PATH"
OFFCUT_LAYER = "OFFCUT"
GEOMETRY_LAYER = "GEOMETRY"
LINER_LAYER = EXTRA_OVERLAY_LAYER_BY_KIND["liner"]
REAR_GROOVE_LAYER = EXTRA_OVERLAY_LAYER_BY_KIND["back_groove"]
HANDLE_RECESS_LAYER = EXTRA_OVERLAY_LAYER_BY_KIND["recessed_handle_cutout"]
TEXT_LAYER_EXPORT_NAME = TEXT_LABEL_LAYER_KEY

# Roles describe manufacturing/display duty. They are not UI visibility flags.
LAYER_ROLE_SHEET_OUTLINE = "sheet_outline"
LAYER_ROLE_SAW_CENTER = "saw_center"
LAYER_ROLE_FINISHED_OUTLINE = "finished_outline"
LAYER_ROLE_OFFCUT_CLASSIFICATION = "offcut_classification"
LAYER_ROLE_ADDON_OVERLAY = "addon_overlay"
LAYER_ROLE_TEXT_ANNOTATION = "text_annotation"
LAYER_ROLE_DESIGNER_DEFAULT = "designer_default"
LAYER_ROLE_REFERENCE = "reference"

COLOR_SOURCE_BYLAYER = "BYLAYER"
COLOR_SOURCE_BYENTITY = "BYENTITY"
COLOR_SOURCE_CATALOG_DEFAULT = "CATALOG_DEFAULT"
LINETYPE_SOURCE_BYLAYER = "BYLAYER"
LINETYPE_SOURCE_BYENTITY = "BYENTITY"
LINETYPE_SOURCE_CATALOG_DEFAULT = "CATALOG_DEFAULT"

# Affiliation policies for drawing elements that land on a layer.
AFFILIATION_SINGLE_PIECE_WHEN_OWNED = "single_piece_when_owned"
AFFILIATION_MAY_SPAN_MULTIPLE_PIECES = "may_span_multiple_pieces"
AFFILIATION_SHEET_SCOPED = "sheet_scoped"
AFFILIATION_NEVER_INFER_FROM_LAYER = "never_infer_from_layer"

# Export ACI colours / linetypes mirrored from secure_dxf_export.js defaults.
_CANONICAL_LAYER_SPECS: tuple[dict[str, Any], ...] = (
    {
        "original_name": SHEET_OUTLINE_LAYER,
        "role": LAYER_ROLE_SHEET_OUTLINE,
        "manufacturing": False,
        "default_aci_color": 8,
        "default_linetype": "CONTINUOUS",
        "affiliation_policy": AFFILIATION_SHEET_SCOPED,
    },
    {
        "original_name": CUT_PATH_LAYER,
        "role": LAYER_ROLE_SAW_CENTER,
        "manufacturing": True,
        "default_aci_color": 1,
        "default_linetype": "CONTINUOUS",
        "affiliation_policy": AFFILIATION_MAY_SPAN_MULTIPLE_PIECES,
    },
    {
        "original_name": GEOMETRY_LAYER,
        "role": LAYER_ROLE_FINISHED_OUTLINE,
        "manufacturing": False,
        "default_aci_color": 4,
        "default_linetype": "CONTINUOUS",
        "affiliation_policy": AFFILIATION_SINGLE_PIECE_WHEN_OWNED,
    },
    {
        "original_name": OFFCUT_LAYER,
        "role": LAYER_ROLE_OFFCUT_CLASSIFICATION,
        "manufacturing": False,
        "default_aci_color": 2,
        "default_linetype": "CONTINUOUS",
        "affiliation_policy": AFFILIATION_SINGLE_PIECE_WHEN_OWNED,
    },
    {
        "original_name": LINER_LAYER,
        "role": LAYER_ROLE_ADDON_OVERLAY,
        "manufacturing": True,
        "default_aci_color": 5,
        "default_linetype": "CONTINUOUS",
        "affiliation_policy": AFFILIATION_SINGLE_PIECE_WHEN_OWNED,
    },
    {
        "original_name": REAR_GROOVE_LAYER,
        "role": LAYER_ROLE_ADDON_OVERLAY,
        "manufacturing": True,
        "default_aci_color": 3,
        "default_linetype": "CONTINUOUS",
        "affiliation_policy": AFFILIATION_SINGLE_PIECE_WHEN_OWNED,
    },
    {
        "original_name": HANDLE_RECESS_LAYER,
        "role": LAYER_ROLE_ADDON_OVERLAY,
        "manufacturing": True,
        "default_aci_color": 6,
        "default_linetype": "CONTINUOUS",
        "affiliation_policy": AFFILIATION_SINGLE_PIECE_WHEN_OWNED,
    },
    {
        # Export writes TEXT; import also accepts the legacy lowercase layer.
        "original_name": TEXT_LAYER_EXPORT_NAME,
        "role": LAYER_ROLE_TEXT_ANNOTATION,
        "manufacturing": False,
        "default_aci_color": 7,
        "default_linetype": "CONTINUOUS",
        "affiliation_policy": AFFILIATION_NEVER_INFER_FROM_LAYER,
        "legacy_original_names": (TEXT_LABEL_LAYER,),
    },
)


def layer_match_key(original_name: Any) -> str:
    """Normalize only case and surrounding whitespace for matching.

    The original spelling is preserved separately for display and DXF export.
    Aliases are never invented here.
    """

    return str(original_name or "").strip().upper()


def canonical_layer_specs() -> tuple[dict[str, Any], ...]:
    """Return the frozen manufacturing/display layer catalog used by export."""

    return tuple(dict(spec) for spec in _CANONICAL_LAYER_SPECS)


def canonical_layer_match_keys() -> frozenset[str]:
    keys: set[str] = set()
    for spec in _CANONICAL_LAYER_SPECS:
        keys.add(layer_match_key(spec["original_name"]))
        for legacy in spec.get("legacy_original_names") or ():
            keys.add(layer_match_key(legacy))
    return frozenset(keys)


def _spec_for_match_key(match_key: str) -> dict[str, Any] | None:
    wanted = layer_match_key(match_key)
    for spec in _CANONICAL_LAYER_SPECS:
        if layer_match_key(spec["original_name"]) == wanted:
            return dict(spec)
        for legacy in spec.get("legacy_original_names") or ():
            if layer_match_key(legacy) == wanted:
                return dict(spec)
    if wanted == DESIGNER_DEFAULT_LAYER:
        return {
            "original_name": DESIGNER_DEFAULT_LAYER,
            "role": LAYER_ROLE_DESIGNER_DEFAULT,
            "manufacturing": False,
            "default_aci_color": 7,
            "default_linetype": "CONTINUOUS",
            "affiliation_policy": AFFILIATION_NEVER_INFER_FROM_LAYER,
        }
    return None


def build_layer_registry(
    *,
    layer_table: Sequence[Mapping[str, Any]] | None = None,
    detected_layer_names: Iterable[Any] | None = None,
    include_canonical_empty: bool = True,
) -> list[dict[str, Any]]:
    """Build a dynamic layer registry with original names and display properties.

    ``layer_table`` entries may include empty defined layers from a DXF LAYER
    table. Canonical export layers are always present for system plans so the
    editor can check/uncheck them without inventing manufacturing geometry.
    """

    by_key: dict[str, dict[str, Any]] = {}

    def upsert(
        *,
        original_name: str,
        match_key: str | None = None,
        role: str | None = None,
        manufacturing: bool | None = None,
        aci_color: int | None = None,
        linetype: str | None = None,
        color_source: str | None = None,
        linetype_source: str | None = None,
        is_defined_empty: bool = False,
        is_canonical: bool = False,
        affiliation_policy: str | None = None,
        source: str = "catalog",
    ) -> None:
        key = layer_match_key(match_key or original_name)
        if not key:
            return
        existing = by_key.get(key)
        spec = _spec_for_match_key(key)
        if existing is None:
            by_key[key] = {
                "original_name": str(original_name),
                "match_key": key,
                "role": role
                or (spec or {}).get("role")
                or LAYER_ROLE_REFERENCE,
                "manufacturing": bool(
                    manufacturing
                    if manufacturing is not None
                    else (spec or {}).get("manufacturing", False)
                ),
                "aci_color": aci_color
                if aci_color is not None
                else (spec or {}).get("default_aci_color"),
                "linetype": linetype
                or (spec or {}).get("default_linetype")
                or "CONTINUOUS",
                "color_source": color_source
                or (
                    COLOR_SOURCE_CATALOG_DEFAULT
                    if spec is not None
                    else COLOR_SOURCE_BYLAYER
                ),
                "linetype_source": linetype_source
                or (
                    LINETYPE_SOURCE_CATALOG_DEFAULT
                    if spec is not None
                    else LINETYPE_SOURCE_BYLAYER
                ),
                "is_defined_empty": bool(is_defined_empty),
                "is_canonical": bool(is_canonical or spec is not None),
                "affiliation_policy": affiliation_policy
                or (spec or {}).get("affiliation_policy")
                or AFFILIATION_NEVER_INFER_FROM_LAYER,
                "source": source,
            }
            return

        # Prefer a concrete table spelling and properties over catalog defaults.
        if source == "layer_table":
            existing["original_name"] = str(original_name)
            existing["source"] = source
            if aci_color is not None:
                existing["aci_color"] = aci_color
                existing["color_source"] = color_source or COLOR_SOURCE_BYLAYER
            if linetype:
                existing["linetype"] = linetype
                existing["linetype_source"] = (
                    linetype_source or LINETYPE_SOURCE_BYLAYER
                )
        existing["is_defined_empty"] = bool(
            existing.get("is_defined_empty") and is_defined_empty
        )
        if is_canonical:
            existing["is_canonical"] = True

    if include_canonical_empty:
        for spec in _CANONICAL_LAYER_SPECS:
            upsert(
                original_name=str(spec["original_name"]),
                role=str(spec["role"]),
                manufacturing=bool(spec["manufacturing"]),
                aci_color=int(spec["default_aci_color"]),
                linetype=str(spec["default_linetype"]),
                color_source=COLOR_SOURCE_CATALOG_DEFAULT,
                linetype_source=LINETYPE_SOURCE_CATALOG_DEFAULT,
                is_defined_empty=True,
                is_canonical=True,
                affiliation_policy=str(spec["affiliation_policy"]),
                source="catalog",
            )

    for row in layer_table or ():
        if not isinstance(row, Mapping):
            continue
        original = str(row.get("original_name") or row.get("name") or "").strip()
        if not original:
            continue
        color = row.get("aci_color")
        if color is None:
            color = row.get("color")
        try:
            aci = int(color) if color is not None else None
        except (TypeError, ValueError):
            aci = None
        linetype = str(row.get("linetype") or "").strip() or None
        upsert(
            original_name=original,
            match_key=str(row.get("match_key") or layer_match_key(original)),
            aci_color=aci,
            linetype=linetype,
            color_source=str(row.get("color_source") or COLOR_SOURCE_BYLAYER),
            linetype_source=str(
                row.get("linetype_source") or LINETYPE_SOURCE_BYLAYER
            ),
            is_defined_empty=bool(row.get("is_empty", row.get("is_defined_empty"))),
            source="layer_table",
        )

    for name in detected_layer_names or ():
        original = str(name or "").strip()
        if not original:
            continue
        upsert(
            original_name=original,
            is_defined_empty=False,
            source="detected",
        )
        entry = by_key.get(layer_match_key(original))
        if entry is not None:
            entry["is_defined_empty"] = False

    # Stable order: canonical export order first, then remaining by match_key.
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spec in _CANONICAL_LAYER_SPECS:
        key = layer_match_key(spec["original_name"])
        entry = by_key.get(key)
        if entry is not None:
            ordered.append(entry)
            seen.add(key)
    for key in sorted(by_key):
        if key in seen:
            continue
        ordered.append(by_key[key])
    return ordered


__all__ = [
    "AFFILIATION_MAY_SPAN_MULTIPLE_PIECES",
    "AFFILIATION_NEVER_INFER_FROM_LAYER",
    "AFFILIATION_SHEET_SCOPED",
    "AFFILIATION_SINGLE_PIECE_WHEN_OWNED",
    "BOARD_EDITOR_LAYER_SCHEMA_VERSION",
    "COLOR_SOURCE_BYENTITY",
    "COLOR_SOURCE_BYLAYER",
    "COLOR_SOURCE_CATALOG_DEFAULT",
    "CUT_PATH_LAYER",
    "GEOMETRY_LAYER",
    "HANDLE_RECESS_LAYER",
    "LAYER_ROLE_ADDON_OVERLAY",
    "LAYER_ROLE_DESIGNER_DEFAULT",
    "LAYER_ROLE_FINISHED_OUTLINE",
    "LAYER_ROLE_OFFCUT_CLASSIFICATION",
    "LAYER_ROLE_REFERENCE",
    "LAYER_ROLE_SAW_CENTER",
    "LAYER_ROLE_SHEET_OUTLINE",
    "LAYER_ROLE_TEXT_ANNOTATION",
    "LINER_LAYER",
    "LINETYPE_SOURCE_BYENTITY",
    "LINETYPE_SOURCE_BYLAYER",
    "LINETYPE_SOURCE_CATALOG_DEFAULT",
    "OFFCUT_LAYER",
    "REAR_GROOVE_LAYER",
    "SHEET_OUTLINE_LAYER",
    "TEXT_LAYER_EXPORT_NAME",
    "build_layer_registry",
    "canonical_layer_match_keys",
    "canonical_layer_specs",
    "layer_match_key",
]
