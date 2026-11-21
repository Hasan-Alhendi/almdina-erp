"""Manufacturing readiness checks for Board Editor Cutting Plan copies.

Pose is already baked into usable-sheet geometry at materialize time. Approval
and export re-validate that frozen geometry; they never snap angles or rebuild
unrotated order AABB outlines.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Mapping

from almdina_erp.almdina_erp.domain.cutting.board_editor_rotation import (
    angles_equivalent,
    machine_accepts_rotation,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    DxfGeometrySnapshotError,
    DxfTopologyError,
    validate_snapshot_material_layout,
)
from almdina_erp.almdina_erp.domain.cutting.primitives import num


class BoardEditorManufacturingError(ValueError):
    def __init__(self, code: str, *, detail: Any = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


_APPROVE_MISSING_GEOMETRY = (
    "The cutting plan cannot be approved because the finished outline is incomplete for these doors:"
)
_EXPORT_MISSING_GEOMETRY = (
    "The cutting plan cannot be exported because the finished outline is incomplete for these doors:"
)
_MISSING_GEOMETRY_DOOR = "- Door {0} — sheet {1}."
_MISSING_GEOMETRY_NEXT = (
    "Finish and approve the cut outline in the editor then create a new plan copy."
)


def format_missing_geometry_message(
    detail: Any,
    *,
    action: str,
    translate: Callable[[str], str],
) -> str:
    """Name the doors and sheets already listed on the manufacturing error.

    ``translate`` is the caller's localization function. This module stays
    framework-free and does not choose a language.
    """

    pieces: Sequence[Any] = ()
    if isinstance(detail, Mapping):
        raw = detail.get("pieces")
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            pieces = raw
    bullets: list[str] = []
    for row in pieces:
        if not isinstance(row, Mapping):
            continue
        label = str(row.get("label") or row.get("piece_instance_id") or "").strip()
        sheet_no = row.get("sheet_no")
        if isinstance(sheet_no, bool) or not isinstance(sheet_no, (int, float)):
            sheet = str(sheet_no or "").strip()
        else:
            sheet = str(int(sheet_no))
        bullets.append(translate(_MISSING_GEOMETRY_DOOR).format(label, sheet))
    intro = _EXPORT_MISSING_GEOMETRY if action == "export" else _APPROVE_MISSING_GEOMETRY
    return "\n".join([translate(intro), *bullets, translate(_MISSING_GEOMETRY_NEXT)])


def _piece_rows(snapshot: Mapping[str, Any]) -> list[tuple[int, Mapping[str, Any]]]:
    rows: list[tuple[int, Mapping[str, Any]]] = []
    for sheet in snapshot.get("sheets") or []:
        if not isinstance(sheet, Mapping):
            continue
        sheet_no = int(num(sheet.get("sheet_no")) or 0)
        for piece in sheet.get("pieces") or []:
            if isinstance(piece, Mapping):
                rows.append((sheet_no, piece))
    return rows


def assert_board_editor_manufacturing_ready(
    snapshot: Mapping[str, Any] | None,
    *,
    machine_type: str,
    kerf_mm: float,
) -> None:
    """Fail closed when a Board Editor plan cannot safely feed approve/export.

    Rejected cases raise ``BoardEditorManufacturingError`` with a stable code:
    - ``missing_geometry``: a placed piece lacks usable-sheet topology
    - ``machine_rotation_forbidden``: angle not accepted by the plan machine
    - ``material_layout_invalid``: topology/kerf collision in the frozen layout
    - ``empty_plan``: no sheets/pieces to manufacture
    """

    payload = snapshot if isinstance(snapshot, Mapping) else {}
    pieces = _piece_rows(payload)
    if not pieces:
        raise BoardEditorManufacturingError("empty_plan")

    machine = str(machine_type or "").strip()
    unsupported: list[dict[str, Any]] = []
    missing_geometry: list[dict[str, Any]] = []
    for sheet_no, piece in pieces:
        identity = {
            "sheet_no": sheet_no,
            "piece_instance_id": str(piece.get("piece_instance_id") or ""),
            "label": str(piece.get("label") or piece.get("id") or ""),
            "rotation_deg": num(piece.get("rotation_deg")),
        }
        geometry = piece.get("geometry")
        outer = geometry.get("outer") if isinstance(geometry, Mapping) else None
        if not isinstance(outer, Sequence) or len(outer) < 3:
            missing_geometry.append(identity)
            continue
        angle = num(piece.get("rotation_deg"))
        if not machine_accepts_rotation(machine, angle):
            unsupported.append(identity)

    if missing_geometry:
        raise BoardEditorManufacturingError(
            "missing_geometry",
            detail={"pieces": missing_geometry},
        )
    if unsupported:
        raise BoardEditorManufacturingError(
            "machine_rotation_forbidden",
            detail={
                "machine_type": machine,
                "pieces": unsupported,
            },
        )

    try:
        validate_snapshot_material_layout(
            payload,
            required_clearance_mm=max(0.0, float(kerf_mm or 0.0)),
        )
    except (DxfGeometrySnapshotError, DxfTopologyError) as exc:
        raise BoardEditorManufacturingError(
            "material_layout_invalid",
            detail={"exception": str(exc), "code": getattr(exc, "code", None)},
        ) from exc


def piece_uses_posed_geometry(piece: Mapping[str, Any] | None) -> bool:
    """Whether export must trust baked geometry instead of AABB/rotated rebuild."""

    if not isinstance(piece, Mapping):
        return False
    if piece.get("apply_rotated_to_geometry") is False:
        return True
    angle = num(piece.get("rotation_deg"))
    if not angles_equivalent(angle, 0) and not angles_equivalent(angle, 90):
        geometry = piece.get("geometry")
        outer = geometry.get("outer") if isinstance(geometry, Mapping) else None
        return isinstance(outer, Sequence) and len(outer) >= 3
    return False


__all__ = [
    "BoardEditorManufacturingError",
    "assert_board_editor_manufacturing_ready",
    "piece_uses_posed_geometry",
]
