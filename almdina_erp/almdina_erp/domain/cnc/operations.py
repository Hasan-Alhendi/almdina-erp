"""Operational CNC layers taken from the current DXF contract.

Illustrative layers are not toolpaths. Names match the layers the DXF
exporter and importer already use; this module does not invent aliases.
"""

from __future__ import annotations

from dataclasses import dataclass

from almdina_erp.almdina_erp.domain.cutting.machining_overlay import MACHINING_ADDONS


# Same literal as ``services.dxf_import_service.CUT_PATH_LAYER``.
CUT_PATH_LAYER = "CUT_PATH"

_ILLUSTRATIVE_LAYERS = frozenset(
    {
        "GEOMETRY",
        "SHEET_OUTLINE",
        "TEXT",
        "OFFCUT",
        "text",
        "0",
    }
)


@dataclass(frozen=True, slots=True)
class CncOperationType:
    key: str
    dxf_layer: str
    sequence: int
    default_preset_field: str


def _addon_layer(kind: str) -> str:
    for addon in MACHINING_ADDONS:
        if addon.kind == kind:
            return addon.layer
    raise ValueError(f"Unknown machining add-on: {kind}")


# ``sequence`` is the default machining order for a sheet: liner, handle recess,
# rear groove, then the cut that separates the pieces. The tuple order above
# the sequence stays the DXF layer contract and is not a machining order.
CNC_OPERATION_TYPES: tuple[CncOperationType, ...] = (
    CncOperationType("cut_path", CUT_PATH_LAYER, 4, "cnc_default_preset_cut_path"),
    CncOperationType("liner", _addon_layer("liner"), 1, "cnc_default_preset_liner"),
    CncOperationType(
        "back_groove",
        _addon_layer("back_groove"),
        3,
        "cnc_default_preset_rear_groove",
    ),
    CncOperationType(
        "recessed_handle_cutout",
        _addon_layer("recessed_handle_cutout"),
        2,
        "cnc_default_preset_handle_recess",
    ),
)
CNC_OPERATIONS_BY_KEY = {operation.key: operation for operation in CNC_OPERATION_TYPES}
DEFAULT_MACHINING_ORDER = tuple(
    operation.key
    for operation in sorted(CNC_OPERATION_TYPES, key=lambda item: item.sequence)
)
OPERATIONAL_DXF_LAYERS = frozenset(
    operation.dxf_layer for operation in CNC_OPERATION_TYPES
)
ILLUSTRATIVE_DXF_LAYERS = _ILLUSTRATIVE_LAYERS


def is_operational_layer(layer: str) -> bool:
    return str(layer or "").strip() in OPERATIONAL_DXF_LAYERS


def operation_for_key(key: str) -> CncOperationType:
    try:
        return CNC_OPERATIONS_BY_KEY[str(key or "").strip()]
    except KeyError as exc:
        raise ValueError(f"Unknown CNC operation: {key}") from exc


__all__ = [
    "CNC_OPERATIONS_BY_KEY",
    "CNC_OPERATION_TYPES",
    "DEFAULT_MACHINING_ORDER",
    "CUT_PATH_LAYER",
    "ILLUSTRATIVE_DXF_LAYERS",
    "OPERATIONAL_DXF_LAYERS",
    "CncOperationType",
    "is_operational_layer",
    "operation_for_key",
]
