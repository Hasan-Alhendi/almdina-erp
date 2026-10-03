"""Structured DXF validation issues (framework-free, language-free).

Validators decide truth. Issues transport truth. Presenters explain truth.
Business logic must branch on ``code`` (and structured fields), never on
user-facing message text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


# Stable categories used for ordering and inventory.
CATEGORY_FILE = "FILE"
CATEGORY_READER = "READER"
CATEGORY_LAYER = "LAYER"
CATEGORY_SHEET = "SHEET"
CATEGORY_CONTOUR = "CONTOUR"
CATEGORY_IDENTITY = "IDENTITY"
CATEGORY_DIMENSIONS = "DIMENSIONS"
CATEGORY_TOPOLOGY = "TOPOLOGY"
CATEGORY_LAYOUT = "LAYOUT"
CATEGORY_OVERLAY = "OVERLAY"
CATEGORY_OFFCUT = "OFFCUT"
CATEGORY_PERSISTENCE = "PERSISTENCE"
CATEGORY_EXPORT = "EXPORT"
CATEGORY_WORKFLOW = "WORKFLOW"

CATEGORY_ORDER: tuple[str, ...] = (
    CATEGORY_FILE,
    CATEGORY_READER,
    CATEGORY_LAYER,
    CATEGORY_SHEET,
    CATEGORY_CONTOUR,
    CATEGORY_IDENTITY,
    CATEGORY_DIMENSIONS,
    CATEGORY_TOPOLOGY,
    CATEGORY_LAYOUT,
    CATEGORY_OVERLAY,
    CATEGORY_OFFCUT,
    CATEGORY_PERSISTENCE,
    CATEGORY_EXPORT,
    CATEGORY_WORKFLOW,
)

# Target kinds
TARGET_FILE = "file"
TARGET_SHEET = "sheet"
TARGET_PIECE = "piece"
TARGET_PIECE_COPY = "piece_copy"
TARGET_CONTOUR = "contour"
TARGET_LAYER = "layer"
TARGET_OVERLAY = "overlay"
TARGET_BLOCK = "block"
TARGET_PIECE_PAIR = "piece_pair"
TARGET_ORDER = "order"
TARGET_UNKNOWN = "unknown"

# Stable codes (only those used by runtime paths).
FILE_REQUIRED = "FILE_REQUIRED"
FILE_INVALID_EXTENSION = "FILE_INVALID_EXTENSION"
FILE_TOO_LARGE = "FILE_TOO_LARGE"
FILE_MISSING = "FILE_MISSING"
FILE_ATTACHED_ELSEWHERE = "FILE_ATTACHED_ELSEWHERE"
FILE_UNREADABLE = "FILE_UNREADABLE"
DXF_UNREADABLE = "DXF_UNREADABLE"
DXF_LIBRARY_MISSING = "DXF_LIBRARY_MISSING"
UNSUPPORTED_ENTITY = "UNSUPPORTED_ENTITY"
MINSERT_UNSUPPORTED = "MINSERT_UNSUPPORTED"
ENTITY_LIMIT_EXCEEDED = "ENTITY_LIMIT_EXCEEDED"

SHEET_LAYER_MISSING = "SHEET_LAYER_MISSING"
CUT_LAYER_MISSING = "CUT_LAYER_MISSING"
SHEET_OPEN = "SHEET_OPEN"
SHEET_BRANCHED = "SHEET_BRANCHED"
SHEET_NOT_RECTANGLE = "SHEET_NOT_RECTANGLE"
SHEET_SIZE_MISMATCH = "SHEET_SIZE_MISMATCH"

CUT_OPEN = "CUT_OPEN"
CUT_BRANCHED = "CUT_BRANCHED"
CUT_SELF_INTERSECTION = "CUT_SELF_INTERSECTION"
CUT_INVALID_GEOMETRY = "CUT_INVALID_GEOMETRY"
CUT_SIZE_MISMATCH = "CUT_SIZE_MISMATCH"
SPECIAL_SIZE_MISMATCH = "SPECIAL_SIZE_MISMATCH"
FORBIDDEN_ROTATION = "FORBIDDEN_ROTATION"
PIECE_MISSING = "PIECE_MISSING"
EXTRA_CUT_PATH = "EXTRA_CUT_PATH"
PIECE_IDENTITY_AMBIGUOUS = "PIECE_IDENTITY_AMBIGUOUS"
PIECE_IDENTITY_MISSING = "PIECE_IDENTITY_MISSING"
EXPECTED_PIECE_MISMATCH = "EXPECTED_PIECE_MISMATCH"
AMBIGUOUS_CONTOUR_OWNERSHIP = "AMBIGUOUS_CONTOUR_OWNERSHIP"
UNRESOLVED_CONTOUR_OWNERSHIP = "UNRESOLVED_CONTOUR_OWNERSHIP"
INVALID_PART_TOPOLOGY = "INVALID_PART_TOPOLOGY"
MATERIAL_OVERLAP = "MATERIAL_OVERLAP"
KERF_VIOLATION = "KERF_VIOLATION"
HOLE_CLEARANCE_VIOLATION = "HOLE_CLEARANCE_VIOLATION"
PIECE_OUTSIDE_SHEET = "PIECE_OUTSIDE_SHEET"
PIECE_INVALID_DIMENSIONS = "PIECE_INVALID_DIMENSIONS"
BOARD_INVALID = "BOARD_INVALID"
TRIM_EXCEEDS_BOARD = "TRIM_EXCEEDS_BOARD"
APPLIED_TRIM_OVERFLOW = "APPLIED_TRIM_OVERFLOW"
CUT_DIMENSIONS_MISSING = "CUT_DIMENSIONS_MISSING"
CUT_DIMENSIONS_BIND_FAILED = "CUT_DIMENSIONS_BIND_FAILED"
PERSISTED_CUT_SPECS = "PERSISTED_CUT_SPECS"
MIXED_RESOURCE_SOURCE = "MIXED_RESOURCE_SOURCE"
OFFCUT_IDENTITY_MISMATCH = "OFFCUT_IDENTITY_MISMATCH"
MANUFACTURING_REQUIREMENTS_MISSING = "MANUFACTURING_REQUIREMENTS_MISSING"
PLAN_SOURCE_MISSING = "PLAN_SOURCE_MISSING"
PLAN_LABEL_DUPLICATE = "PLAN_LABEL_DUPLICATE"
PLAN_UNPLACED_PIECES = "PLAN_UNPLACED_PIECES"
PLAN_UNKNOWN_PIECES = "PLAN_UNKNOWN_PIECES"
TOPOLOGY_VALIDATION_FAILED = "TOPOLOGY_VALIDATION_FAILED"

OVERLAY_INVALID_PATH = "OVERLAY_INVALID_PATH"
OVERLAY_SPANS_HOSTS = "OVERLAY_SPANS_HOSTS"
OVERLAY_ADDON_NOT_SELECTED = "OVERLAY_ADDON_NOT_SELECTED"
OVERLAY_ON_NON_EXTRA = "OVERLAY_ON_NON_EXTRA"
OVERLAY_FLOATING = "OVERLAY_FLOATING"
OVERLAY_ADDON_MISSING = "OVERLAY_ADDON_MISSING"
OVERLAY_ADDON_DUPLICATE = "OVERLAY_ADDON_DUPLICATE"
OVERLAY_UNKNOWN = "OVERLAY_UNKNOWN"

LEGACY_MESSAGE = "LEGACY_MESSAGE"


@dataclass(frozen=True, slots=True)
class DxfIssueTarget:
    """Where the issue applies. Contour identity is never piece identity."""

    kind: str = TARGET_UNKNOWN
    source_piece_no: int | None = None
    copy_no: int | None = None
    contour_no: int | None = None
    sheet_no: int | None = None
    pair_piece_nos: tuple[int | str, int | str] | None = None
    layer: str | None = None
    label: str | None = None
    piece_index: int | None = None


@dataclass(frozen=True, slots=True)
class DxfValidationIssue:
    """Language-free structured DXF validation issue."""

    code: str
    category: str
    target: DxfIssueTarget = field(default_factory=DxfIssueTarget)
    params: Mapping[str, Any] = field(default_factory=dict)
    debug: Mapping[str, Any] = field(default_factory=dict)

    def param(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)


def issue(
    code: str,
    category: str,
    *,
    target: DxfIssueTarget | None = None,
    params: Mapping[str, Any] | None = None,
    debug: Mapping[str, Any] | None = None,
) -> DxfValidationIssue:
    return DxfValidationIssue(
        code=code,
        category=category,
        target=target or DxfIssueTarget(),
        params=dict(params or {}),
        debug=dict(debug or {}),
    )


def piece_target(
    *,
    source_piece_no: int | None = None,
    copy_no: int | None = None,
    label: str | None = None,
    piece_index: int | None = None,
) -> DxfIssueTarget:
    if copy_no is not None and source_piece_no is not None:
        kind = TARGET_PIECE_COPY
    elif source_piece_no is not None or label is not None or piece_index is not None:
        kind = TARGET_PIECE
    else:
        kind = TARGET_UNKNOWN
    return DxfIssueTarget(
        kind=kind,
        source_piece_no=source_piece_no,
        copy_no=copy_no,
        label=label,
        piece_index=piece_index,
    )


def contour_target(contour_no: int, *, layer: str | None = None) -> DxfIssueTarget:
    return DxfIssueTarget(kind=TARGET_CONTOUR, contour_no=contour_no, layer=layer)


def sheet_target(sheet_no: int, *, layer: str | None = None) -> DxfIssueTarget:
    return DxfIssueTarget(kind=TARGET_SHEET, sheet_no=sheet_no, layer=layer)


def pair_target(
    first: int | str,
    second: int | str,
    *,
    sheet_no: int | None = None,
) -> DxfIssueTarget:
    return DxfIssueTarget(
        kind=TARGET_PIECE_PAIR,
        pair_piece_nos=(first, second),
        sheet_no=sheet_no,
    )


def layer_target(layer: str) -> DxfIssueTarget:
    return DxfIssueTarget(kind=TARGET_LAYER, layer=layer)


def file_target(*, label: str | None = None) -> DxfIssueTarget:
    return DxfIssueTarget(kind=TARGET_FILE, label=label)


def sort_issues(issues: list[DxfValidationIssue]) -> list[DxfValidationIssue]:
    order = {name: index for index, name in enumerate(CATEGORY_ORDER)}
    return sorted(
        issues,
        key=lambda item: (order.get(item.category, len(CATEGORY_ORDER)), item.code),
    )


# Codes that receive persisted cut-spec annotation after a dimension failure.
PERSISTED_CUT_CONTEXT_CODES: frozenset[str] = frozenset(
    {
        CUT_SIZE_MISMATCH,
        SPECIAL_SIZE_MISMATCH,
        FORBIDDEN_ROTATION,
        PIECE_IDENTITY_MISSING,
        PIECE_MISSING,
    }
)

# Codes that already carry a full inventory diagnosis; do not append cut specs.
SKIP_PERSISTED_CUT_CONTEXT_CODES: frozenset[str] = frozenset(
    {
        EXPECTED_PIECE_MISMATCH,
        EXTRA_CUT_PATH,
    }
)


def topology_error_to_issue(
    error: Any,
    *,
    kerf_mm: float = 0.0,
    details: str = "",
    source_piece_no: int | None = None,
    debug: Mapping[str, Any] | None = None,
) -> DxfValidationIssue:
    """Map a domain ``DxfTopologyError`` to a structured issue."""
    code = str(getattr(error, "code", "") or TOPOLOGY_VALIDATION_FAILED)
    first = getattr(error, "first_key", None)
    second = getattr(error, "second_key", None)
    expected_index = getattr(error, "expected_piece_index", None)
    params: dict[str, Any] = {"kerf_mm": kerf_mm}
    if details:
        params["details"] = details
    if getattr(error, "actual_width", None) is not None:
        params["actual_width_mm"] = error.actual_width
        params["actual_height_mm"] = error.actual_height
        params["expected_width_mm"] = error.expected_width
        params["expected_height_mm"] = error.expected_height
    if expected_index is not None:
        params["expected_piece_index"] = expected_index

    piece_no = source_piece_no
    if piece_no is None and expected_index is not None:
        piece_no = int(expected_index) + 1

    if code == "FORBIDDEN_ROTATION":
        return issue(
            FORBIDDEN_ROTATION,
            CATEGORY_DIMENSIONS,
            target=piece_target(source_piece_no=piece_no),
            params=params,
            debug=debug,
        )
    if code == "EXPECTED_PIECE_MISMATCH":
        return issue(
            EXPECTED_PIECE_MISMATCH,
            CATEGORY_IDENTITY,
            target=DxfIssueTarget(kind=TARGET_ORDER),
            params=params,
            debug=debug,
        )
    if code == "AMBIGUOUS_CONTOUR_OWNERSHIP":
        return issue(
            AMBIGUOUS_CONTOUR_OWNERSHIP,
            CATEGORY_TOPOLOGY,
            target=DxfIssueTarget(kind=TARGET_ORDER),
            params=params,
            debug=debug,
        )
    if code == "UNRESOLVED_CONTOUR_OWNERSHIP":
        return issue(
            UNRESOLVED_CONTOUR_OWNERSHIP,
            CATEGORY_TOPOLOGY,
            target=DxfIssueTarget(kind=TARGET_ORDER),
            params=params,
            debug=debug,
        )
    if code == "INVALID_PART_TOPOLOGY":
        return issue(
            INVALID_PART_TOPOLOGY,
            CATEGORY_TOPOLOGY,
            target=contour_target(int(first)) if isinstance(first, int) else DxfIssueTarget(),
            params=params,
            debug=debug,
        )
    if code == "MATERIAL_FOOTPRINT_OVERLAP":
        return issue(
            MATERIAL_OVERLAP,
            CATEGORY_LAYOUT,
            target=pair_target(first if first is not None else "؟", second if second is not None else "؟"),
            params=params,
            debug=debug,
        )
    if code == "HOLE_CLEARANCE_VIOLATION":
        return issue(
            HOLE_CLEARANCE_VIOLATION,
            CATEGORY_LAYOUT,
            target=pair_target(first if first is not None else "؟", second if second is not None else "؟"),
            params=params,
            debug=debug,
        )
    if code == "PART_CLEARANCE_VIOLATION":
        return issue(
            KERF_VIOLATION,
            CATEGORY_LAYOUT,
            target=pair_target(first if first is not None else "؟", second if second is not None else "؟"),
            params=params,
            debug=debug,
        )
    return issue(
        TOPOLOGY_VALIDATION_FAILED,
        CATEGORY_TOPOLOGY,
        target=DxfIssueTarget(kind=TARGET_ORDER),
        params={**params, "topology_code": code},
        debug=debug,
    )


_OVERLAY_CODE_MAP = {
    "extra_overlay_invalid_path": OVERLAY_INVALID_PATH,
    "extra_overlay_spans_hosts": OVERLAY_SPANS_HOSTS,
    "extra_overlay_addon_not_selected": OVERLAY_ADDON_NOT_SELECTED,
    "extra_overlay_on_non_extra": OVERLAY_ON_NON_EXTRA,
    "extra_overlay_floating": OVERLAY_FLOATING,
    "extra_overlay_addon_missing": OVERLAY_ADDON_MISSING,
    "extra_overlay_addon_duplicate": OVERLAY_ADDON_DUPLICATE,
}


def overlay_error_to_issue(error: Any) -> DxfValidationIssue:
    """Map a domain ``ExtraOverlayError`` to a structured issue."""
    raw_code = str(getattr(error, "code", "") or "")
    code = _OVERLAY_CODE_MAP.get(raw_code, OVERLAY_UNKNOWN)
    layer = str(getattr(error, "layer", "") or "")
    label = str(getattr(error, "label", "") or getattr(error, "host_key", "") or "")
    kind = str(getattr(error, "kind", "") or "")
    source_piece_no = None
    if label.isdigit():
        source_piece_no = int(label)
    return issue(
        code,
        CATEGORY_OVERLAY,
        target=DxfIssueTarget(
            kind=TARGET_OVERLAY,
            layer=layer or None,
            label=label or None,
            source_piece_no=source_piece_no,
        ),
        params={"overlay_kind": kind, "layer": layer, "label": label},
        debug={"raw_code": raw_code, "host_key": getattr(error, "host_key", None)},
    )
