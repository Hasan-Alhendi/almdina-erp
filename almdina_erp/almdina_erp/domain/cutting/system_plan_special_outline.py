"""System-plan approval gate for Special door cut outlines.

System nesting may place undrawn Special doors as CNC-raw stock rectangles.
That placeholder is valid for calculation and review, but it is not a Special
cut outline. Approval of a System plan requires either a non-rectangular
proven cut outline or a rectangular outline that owns at least one internal
through-cut opening. Liners, handles, rear grooves, and guide lines are not
openings. Uploaded DXF and Board Editor approval stay outside this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.dxf_geometry import (
    is_rectangle,
    validate_polygon,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    DxfGeometrySnapshotError,
    GEOMETRY_TOLERANCE_MM,
    parse_geometry_mm,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_issue import (
    CATEGORY_DIMENSIONS,
    SPECIAL_OUTLINE_IS_RECTANGLE,
    TARGET_PIECE,
    DxfIssueTarget,
    DxfValidationIssue,
    issue,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_topology import PartGeometry
from almdina_erp.almdina_erp.domain.cutting.glass_opening_nesting import (
    material_outline_cm,
)

_GEOMETRY_TOLERANCE_MM = GEOMETRY_TOLERANCE_MM


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cut_geometry_mm(piece: Mapping[str, Any]) -> PartGeometry | None:
    """Return proven cut outer/holes in millimetres, or None when unproven.

    Persisted ``geometry.holes`` are the only internal through-cut openings.
    Add-on overlays and liner metadata are ignored here on purpose.
    """

    raw = piece.get("geometry")
    if isinstance(raw, Mapping):
        try:
            return parse_geometry_mm(raw)
        except DxfGeometrySnapshotError:
            # Fall through to the Special JSON contour when the stored DXF
            # contract is incomplete or corrupt.
            pass

    outline_cm = material_outline_cm(piece)
    if outline_cm is None or len(outline_cm) < 3:
        return None
    outer = tuple((float(point[0]) * 10.0, float(point[1]) * 10.0) for point in outline_cm)
    if validate_polygon(outer, _GEOMETRY_TOLERANCE_MM):
        return None
    return PartGeometry(outer=outer, holes=())


def _has_valid_internal_openings(geometry: PartGeometry) -> bool:
    if not geometry.holes:
        return False
    if validate_polygon(geometry.outer, _GEOMETRY_TOLERANCE_MM):
        return False
    for hole in geometry.holes:
        if validate_polygon(hole, _GEOMETRY_TOLERANCE_MM):
            return False
    return True


def special_outline_blocks_system_plan_approval(piece: Mapping[str, Any]) -> bool:
    """True when a Special piece must block System plan approval."""

    if str(piece.get("piece_type") or "") != "Special":
        return False
    geometry = _cut_geometry_mm(piece)
    if geometry is None:
        # CNC-raw stock rectangle / missing exact cut outline.
        return True
    if validate_polygon(geometry.outer, _GEOMETRY_TOLERANCE_MM):
        return True
    if not is_rectangle(geometry.outer, _GEOMETRY_TOLERANCE_MM):
        return False
    return not _has_valid_internal_openings(geometry)


def _piece_issue(
    piece: Mapping[str, Any],
    *,
    sheet_no: int | None,
) -> DxfValidationIssue:
    return issue(
        SPECIAL_OUTLINE_IS_RECTANGLE,
        CATEGORY_DIMENSIONS,
        target=DxfIssueTarget(
            kind=TARGET_PIECE,
            source_piece_no=_optional_int(piece.get("source_piece_no")),
            copy_no=_optional_int(piece.get("copy_no")),
            sheet_no=sheet_no,
            label=str(piece.get("label") or "").strip() or None,
        ),
        params={"system_plan_approval": True},
    )


def collect_system_plan_special_outline_issues(
    snapshot: Mapping[str, Any] | None,
) -> list[DxfValidationIssue]:
    """Collect every Special piece that blocks System plan approval."""

    if not isinstance(snapshot, Mapping):
        return []
    sheets = snapshot.get("sheets")
    if not isinstance(sheets, Sequence) or isinstance(sheets, (str, bytes)):
        return []

    issues: list[DxfValidationIssue] = []
    for sheet in sheets:
        if not isinstance(sheet, Mapping):
            continue
        sheet_no = _optional_int(sheet.get("sheet_no"))
        pieces = sheet.get("pieces")
        if not isinstance(pieces, Sequence) or isinstance(pieces, (str, bytes)):
            continue
        for piece in pieces:
            if not isinstance(piece, Mapping):
                continue
            if special_outline_blocks_system_plan_approval(piece):
                issues.append(_piece_issue(piece, sheet_no=sheet_no))

    issues.sort(
        key=lambda item: (
            item.target.sheet_no is None,
            item.target.sheet_no or 0,
            item.target.source_piece_no is None,
            item.target.source_piece_no or 0,
            item.target.copy_no is None,
            item.target.copy_no or 0,
            str(item.target.label or ""),
        )
    )
    return issues


__all__ = [
    "collect_system_plan_special_outline_issues",
    "special_outline_blocks_system_plan_approval",
]
