"""Editor working-copy contract.

A draft is not a Cutting Plan. It stores only the edit fields needed to
rebuild a session on top of a trusted projection: membership, pose, hosting,
exclusion, and remaining board origins. Geometry, allow_rotation, kerf,
financials, camera, selection, and history are not part of this document.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.board_editor_hosting import (
    hosting_link_creates_cycle,
)
from almdina_erp.almdina_erp.domain.orders.piece_policy import is_corner_cut

SCHEMA = 1
MAX_ABS_MM = 1_000_000.0
MAX_ABS_DEG = 3600.0
ANGLE_EPS = 1e-4

DISTRIBUTION_ACTIVE = "active"
DISTRIBUTION_EXCLUDED = "excluded"
EXCLUSION_REASONS = frozenset({"removed_from_distribution", "removed_with_host"})

PIECE_FIELDS = frozenset(
    {
        "piece_instance_id",
        "sheet_no",
        "local_x_mm",
        "local_y_mm",
        "rotation_deg",
        # Transform parity only — geometry is re-derived from the trusted source.
        "flip_h",
        "flip_v",
        "mirrored",
        "distribution",
        "exclusion_reason",
        "glass_host_piece_id",
    }
)
BOARD_FIELDS = frozenset({"sheet_no", "origin_x_mm", "origin_y_mm", "user_moved"})
TOP_FIELDS = frozenset({"schema", "pieces", "boards"})
FORBIDDEN_FIELDS = frozenset(
    {
        "allow_rotation",
        "allow_rotation_proven",
        "outline",
        "outline_mm",
        "base_outline_mm",
        "geometry",
        "scale",
        "scale_x",
        "scale_y",
        # Legacy/ambiguous aliases stay forbidden; use flip_h / flip_v / mirrored.
        "flip",
        "flip_x",
        "flip_y",
        "mirror",
        "kerf",
        "kerf_mm",
        "width_mm",
        "height_mm",
        "snapshot",
        "snapshot_json",
        "cost",
        "amount",
        "rate",
        "placement_cm",
    }
)


class DraftLayoutError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def draft_key(order_name: str, plan_name: str) -> str:
    raw = f"{str(order_name).strip()}\n{str(plan_name).strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# Last token segment used to be the raw background job status ("idle",
# "completed", "queued", …). That flipped the revision when a finished job
# moved idle↔completed without any plan content change. The live token now
# stores a stable active-job bit ("0"|"1"). Normalize both sides so drafts
# saved under the old label stay comparable when the plan itself is unchanged.
#
# Field layout (6 parts):
#   name | layout_or_clock | revision | input_fingerprint | needs_recalc | job
# New tokens store saved_layout_sha256 in slot 1 (geometry/distribution of the
# persisted snapshot). Legacy tokens stored Cutting Plan.modified there; that
# row-touch clock is blanked on compare so it cannot fake a source change.
# Input fingerprint covers manufacturing requirements (edges, addons, constraints).
_JOB_ACTIVE_LABELS = frozenset({"1", "queued", "running", "enqueue"})
_JOB_IDLE_LABELS = frozenset({"0", "idle", "completed", ""})


def _is_legacy_modified_clock(value: str) -> bool:
    """True when slot 1 looks like a Frappe/ISO datetime, not a layout digest."""

    text = str(value or "").strip()
    if not text:
        return False
    # "YYYY-MM-DD ..." or "YYYY-MM-DDTHH:MM:SS"
    return len(text) >= 10 and text[4] == "-" and text[7] == "-"


def _slot1_is_absent_layout_digest(value: str) -> bool:
    """Empty or legacy datetime — not a saved_layout_sha256 digest."""

    text = str(value or "").strip()
    return (not text) or _is_legacy_modified_clock(text)


def normalize_content_revision_token(token: str) -> str:
    """Canonicalize a content revision token for equality checks.

    Keeps name/revision/input fingerprint/needs_recalc and any non-datetime
    layout digest in slot 1. Rewrites a recognized job-status label into the
    stable active bit. Blanks a legacy modified clock in slot 1. Unknown shapes
    are returned unchanged so real mismatches fail closed.
    """

    text = str(token or "")
    if not text:
        return ""
    parts = text.split("|")
    if len(parts) < 6:
        return text
    job = str(parts[-1] or "").strip().lower()
    if job in _JOB_ACTIVE_LABELS:
        parts[-1] = "1"
    elif job in _JOB_IDLE_LABELS:
        parts[-1] = "0"
    else:
        return text
    if _is_legacy_modified_clock(parts[1]):
        parts[1] = ""
    return "|".join(parts)


def tokens_operationally_equivalent(left: str, right: str) -> bool:
    """True when two source tokens bind the same operational plan content.

    Exact normalized equality wins. A legacy/empty layout slot versus a live
    ``saved_layout_sha256`` is accepted only when name, revision, input
    fingerprint, needs_recalc, and job bits already match — fingerprint+revision
    are the trusted manufacturing/plan identity; missing digest alone is never
    treated as proof of equal geometry.
    """

    a = normalize_content_revision_token(left)
    b = normalize_content_revision_token(right)
    if a == b:
        return True
    pa = a.split("|")
    pb = b.split("|")
    if len(pa) < 6 or len(pb) < 6:
        return False
    if (pa[0], pa[2], pa[3], pa[4], pa[5]) != (pb[0], pb[2], pb[3], pb[4], pb[5]):
        return False
    sa = pa[1]
    sb = pb[1]
    if sa == sb:
        return True
    # Format migration only: one side lacks a layout digest, the other has one.
    if _slot1_is_absent_layout_digest(sa) and sb and not _slot1_is_absent_layout_digest(sb):
        return True
    if _slot1_is_absent_layout_digest(sb) and sa and not _slot1_is_absent_layout_digest(sa):
        return True
    return False


def catalog_from_projection(projection: Mapping[str, Any]) -> dict[str, Any]:
    """Trusted piece and sheet identities taken from the server projection."""

    pieces: dict[str, dict[str, Any]] = {}
    for piece in projection.get("pieces") or []:
        if not isinstance(piece, Mapping):
            continue
        instance = str(piece.get("piece_instance_id") or "").strip()
        if not instance or instance in pieces:
            continue
        pieces[instance] = {
            "piece_id": _optional_int(piece.get("piece_id")),
            "allow_rotation": piece.get("allow_rotation") is True
            and piece.get("allow_rotation_proven") is True,
            "glass_host_piece_id": _optional_int(piece.get("glass_host_piece_id")),
            "piece_type": str(piece.get("piece_type") or ""),
        }
    sheets: list[int] = []
    for sheet in projection.get("sheets") or []:
        if not isinstance(sheet, Mapping):
            continue
        number = _optional_int(sheet.get("sheet_no"))
        if number is None or number in sheets:
            continue
        sheets.append(number)
    return {"pieces": pieces, "source_sheet_nos": sheets}


def normalize_layout(layout: Any, catalog: Mapping[str, Any]) -> dict[str, Any]:
    """Accept only edit fields and bind them to the trusted catalog.

    Raises DraftLayoutError. Does not invent hosting or geometry.
    """

    if not isinstance(layout, Mapping):
        raise DraftLayoutError("invalid_layout")
    _reject_forbidden(layout)
    unknown = set(layout) - TOP_FIELDS
    if unknown:
        raise DraftLayoutError("forbidden_field")
    if layout.get("schema") != SCHEMA:
        raise DraftLayoutError("schema")
    raw_pieces = layout.get("pieces")
    raw_boards = layout.get("boards")
    if not isinstance(raw_pieces, Sequence) or isinstance(raw_pieces, (str, bytes)):
        raise DraftLayoutError("invalid_layout")
    if not isinstance(raw_boards, Sequence) or isinstance(raw_boards, (str, bytes)):
        raise DraftLayoutError("invalid_layout")

    trusted: Mapping[str, Mapping[str, Any]] = catalog.get("pieces") or {}
    source_sheets = {int(number) for number in (catalog.get("source_sheet_nos") or [])}
    boards = _normalize_boards(raw_boards, source_sheets)
    kept_sheets = {row["sheet_no"] for row in boards}
    pieces = _normalize_pieces(raw_pieces, trusted, kept_sheets)
    _normalize_hosting(pieces, trusted)
    pieces.sort(key=lambda row: row["piece_instance_id"])
    boards.sort(key=lambda row: row["sheet_no"])
    return {"schema": SCHEMA, "pieces": pieces, "boards": boards}


def distribution_fingerprint(layout: Mapping[str, Any]) -> str:
    payload = json.dumps(layout, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


TITLE_BAND_MM = 36.0
# Match CanvasRenderer.sheetLayout — editor workspace only, not piece locals.
BOARD_GAP_MM = 48.0
DEFAULT_BOARD_COLUMNS = 2


def _sheet_size_mm(sheet: Mapping[str, Any]) -> tuple[float, float]:
    width = float(sheet.get("full_width_cm") or sheet.get("w") or 122) * 10.0
    height = float(sheet.get("full_length_cm") or sheet.get("h") or 244) * 10.0
    return max(1.0, width), max(1.0, height)


def workspace_board_origins(
    sheets: Sequence[Mapping[str, Any]],
    *,
    columns: int = DEFAULT_BOARD_COLUMNS,
) -> dict[int, tuple[float, float]]:
    """2×N workspace origins matching the board-editor sheet grid.

    Piece local coordinates stay in usable-sheet millimetres; these origins only
    place boards in the editor workspace (including the title band).
    """

    cols = 1 if int(columns) == 1 else 2
    ordered: list[tuple[int, Mapping[str, Any]]] = []
    seen: set[int] = set()
    for sheet in sheets or []:
        if not isinstance(sheet, Mapping):
            continue
        number = _optional_int(sheet.get("sheet_no"))
        if number is None or number in seen:
            continue
        seen.add(number)
        ordered.append((number, sheet))
    if not ordered:
        return {}
    sizes = [_sheet_size_mm(sheet) for _number, sheet in ordered]
    max_width = max(width for width, _height in sizes)
    stride = max_width + BOARD_GAP_MM
    row_count = max(1, (len(ordered) + cols - 1) // cols)
    row_height: list[float] = []
    for row in range(row_count):
        height = 1.0
        for col in range(cols):
            index = row * cols + col
            if index < len(sizes):
                height = max(height, sizes[index][1])
        row_height.append(height)

    def row_origin_y(row: int) -> float:
        y = 0.0
        for index in range(row):
            y += TITLE_BAND_MM + row_height[index] + BOARD_GAP_MM
        return y

    origins: dict[int, tuple[float, float]] = {}
    for index, (number, _sheet) in enumerate(ordered):
        row = index // cols
        top = row_origin_y(row)
        origins[number] = ((index % cols) * stride, top + TITLE_BAND_MM)
    return origins


def boards_share_collapsed_default_origin(boards: Sequence[Mapping[str, Any]]) -> bool:
    """True when every board shares one origin and none were user-moved.

    That pattern is the defective begin-from-source initializer (all at 0,
    TITLE_BAND), not a deliberate operator arrangement.
    """

    rows = [board for board in (boards or []) if isinstance(board, Mapping)]
    if len(rows) < 2:
        return False
    if any(board.get("user_moved") is True for board in rows):
        return False
    first_x = float(rows[0].get("origin_x_mm") or 0)
    first_y = float(rows[0].get("origin_y_mm") or 0)
    for board in rows[1:]:
        if abs(float(board.get("origin_x_mm") or 0) - first_x) > 1e-6:
            return False
        if abs(float(board.get("origin_y_mm") or 0) - first_y) > 1e-6:
            return False
    return True


def identity_layout_from_projection(projection: Mapping[str, Any]) -> dict[str, Any]:
    """Build an edit layout that mirrors the trusted projection poses.

    Rotation starts at 0 (as-loaded). Does not copy a previous draft's poses.
    Board workspace origins use the same 2×N grid as a normal editor open.
    """

    pieces: list[dict[str, Any]] = []
    seen: set[str] = set()
    for piece in projection.get("pieces") or []:
        if not isinstance(piece, Mapping):
            continue
        instance = str(piece.get("piece_instance_id") or "").strip()
        if not instance or instance in seen:
            continue
        seen.add(instance)
        placement = piece.get("placement_cm")
        if not isinstance(placement, Mapping):
            placement = {}
        sheet_no = _optional_int(piece.get("sheet_no"))
        host = _optional_int(piece.get("glass_host_piece_id"))
        pieces.append(
            {
                "piece_instance_id": instance,
                "sheet_no": sheet_no,
                "local_x_mm": float(placement.get("x") or 0) * 10.0,
                "local_y_mm": float(placement.get("y") or 0) * 10.0,
                "rotation_deg": 0.0,
                "flip_h": False,
                "flip_v": False,
                "mirrored": False,
                "distribution": DISTRIBUTION_ACTIVE,
                "exclusion_reason": None,
                "glass_host_piece_id": host,
            }
        )
    sheet_rows = [
        sheet
        for sheet in (projection.get("sheets") or [])
        if isinstance(sheet, Mapping)
    ]
    origins = workspace_board_origins(sheet_rows, columns=DEFAULT_BOARD_COLUMNS)
    boards: list[dict[str, Any]] = []
    for number, (origin_x, origin_y) in origins.items():
        boards.append(
            {
                "sheet_no": number,
                "origin_x_mm": float(origin_x),
                "origin_y_mm": float(origin_y),
                "user_moved": False,
            }
        )
    return {"schema": SCHEMA, "pieces": pieces, "boards": boards}


def build_prior_draft_archive(row: Mapping[str, Any]) -> dict[str, Any]:
    """Snapshot one superseded draft for retention (not auto-restored)."""

    layout = row.get("layout_json")
    return {
        "archived_draft_version": int(row.get("draft_version") or 0),
        "source_content_revision": str(row.get("source_content_revision") or ""),
        "source_input_fingerprint": str(row.get("source_input_fingerprint") or ""),
        "distribution_fingerprint": str(row.get("distribution_fingerprint") or ""),
        "layout": layout if isinstance(layout, Mapping) else None,
    }


def decide_draft_write(
    *,
    stored_version: int | None,
    stored_fingerprint: str | None,
    stored_source_revision: str | None,
    expected_version: int,
    layout_fingerprint: str,
    live_source_revision: str,
    request_source_revision: str,
) -> str:
    """Return create, update, idempotent, version_conflict, or source_conflict.

    expected_version 0 creates only when no row exists. A second create with
    the same layout is idempotent and does not insert another row.

    A real source mismatch (after normalization) never rebases or replaces the
    stored draft — neither request==live nor expected==0 is enough. Only the
    request token being stale relative to live, or the stored row binding a
    different operational source than live, yields source_conflict.
    """

    if not tokens_operationally_equivalent(request_source_revision, live_source_revision):
        return "source_conflict"
    if stored_version is not None and not tokens_operationally_equivalent(
        stored_source_revision or "",
        live_source_revision,
    ):
        return "source_conflict"
    if stored_version is None:
        if int(expected_version) != 0:
            return "version_conflict"
        return "create"
    if stored_fingerprint == layout_fingerprint and (
        int(expected_version) in (0, int(stored_version))
    ):
        return "idempotent"
    if int(expected_version) != int(stored_version):
        return "version_conflict"
    return "update"


def _normalize_boards(
    raw_boards: Sequence[Any],
    source_sheets: set[int],
) -> list[dict[str, Any]]:
    boards: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw in raw_boards:
        if not isinstance(raw, Mapping):
            raise DraftLayoutError("invalid_layout")
        _reject_forbidden(raw)
        if set(raw) - BOARD_FIELDS:
            raise DraftLayoutError("forbidden_field")
        sheet_no = _required_int(raw.get("sheet_no"))
        if sheet_no not in source_sheets:
            raise DraftLayoutError("unknown_sheet")
        if sheet_no in seen:
            raise DraftLayoutError("duplicate_sheet")
        seen.add(sheet_no)
        boards.append(
            {
                "sheet_no": sheet_no,
                "origin_x_mm": _finite_mm(raw.get("origin_x_mm")),
                "origin_y_mm": _finite_mm(raw.get("origin_y_mm")),
                "user_moved": _required_bool(raw.get("user_moved", False)),
            }
        )
    return boards


def _normalize_pieces(
    raw_pieces: Sequence[Any],
    trusted: Mapping[str, Mapping[str, Any]],
    kept_sheets: set[int],
) -> list[dict[str, Any]]:
    pieces: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_pieces:
        if not isinstance(raw, Mapping):
            raise DraftLayoutError("invalid_layout")
        _reject_forbidden(raw)
        if set(raw) - PIECE_FIELDS:
            raise DraftLayoutError("forbidden_field")
        instance = str(raw.get("piece_instance_id") or "").strip()
        if not instance or instance not in trusted:
            raise DraftLayoutError("unknown_piece")
        if instance in seen:
            raise DraftLayoutError("duplicate_piece")
        seen.add(instance)
        sheet_no = _optional_int(raw.get("sheet_no")) if raw.get("sheet_no") not in (None, "") else None
        if raw.get("sheet_no") not in (None, "") and sheet_no is None:
            raise DraftLayoutError("invalid_number")
        if sheet_no is not None and sheet_no not in kept_sheets:
            raise DraftLayoutError("unknown_sheet")
        distribution = raw.get("distribution")
        if distribution not in (DISTRIBUTION_ACTIVE, DISTRIBUTION_EXCLUDED):
            raise DraftLayoutError("invalid_distribution")
        reason = raw.get("exclusion_reason")
        if distribution == DISTRIBUTION_ACTIVE:
            if reason not in (None, ""):
                raise DraftLayoutError("invalid_exclusion")
            reason = None
        else:
            if reason not in EXCLUSION_REASONS:
                raise DraftLayoutError("invalid_exclusion")
        rotation = _finite_deg(raw.get("rotation_deg"))
        flip_h = _optional_bool(raw.get("flip_h"), default=False)
        flip_v = _optional_bool(raw.get("flip_v"), default=False)
        mirrored = _optional_bool(raw.get("mirrored"), default=False)
        if abs(rotation) > ANGLE_EPS and not trusted[instance]["allow_rotation"]:
            raise DraftLayoutError("rotation_forbidden")
        if (flip_h or flip_v) and not trusted[instance]["allow_rotation"]:
            raise DraftLayoutError("rotation_forbidden")
        if mirrored and not is_corner_cut(str(trusted[instance].get("piece_type") or "")):
            raise DraftLayoutError("mirror_forbidden")
        if mirrored and not trusted[instance]["allow_rotation"]:
            raise DraftLayoutError("rotation_forbidden")
        row = {
            "piece_instance_id": instance,
            "sheet_no": sheet_no,
            "local_x_mm": _finite_mm(raw.get("local_x_mm")),
            "local_y_mm": _finite_mm(raw.get("local_y_mm")),
            "rotation_deg": rotation,
            "flip_h": flip_h,
            "flip_v": flip_v,
            "mirrored": mirrored,
            "distribution": distribution,
            "exclusion_reason": reason,
            "glass_host_piece_id": None,
        }
        _capture_requested_host(raw, row)
        pieces.append(row)
    if seen != set(trusted):
        raise DraftLayoutError("missing_piece")
    return pieces


def _normalize_hosting(
    pieces: list[dict[str, Any]],
    trusted: Mapping[str, Mapping[str, Any]],
) -> None:
    by_instance = {row["piece_instance_id"]: row for row in pieces}
    piece_id_owner: dict[int, str] = {}
    for instance, info in trusted.items():
        piece_id = info.get("piece_id")
        if piece_id is None:
            continue
        piece_id_owner[int(piece_id)] = instance
    proposed: dict[int, int] = {}
    for row in pieces:
        raw_host = trusted[row["piece_instance_id"]].get("glass_host_piece_id")
        requested = row.pop("_requested_host", None)
        if requested is not None and requested != raw_host:
            raise DraftLayoutError("forged_host")
        if requested is None:
            continue
        guest_id = trusted[row["piece_instance_id"]].get("piece_id")
        if guest_id is None or int(requested) not in piece_id_owner:
            raise DraftLayoutError("forged_host")
        if int(requested) == int(guest_id):
            raise DraftLayoutError("forged_host")
        if hosting_link_creates_cycle(proposed, guest_id=int(guest_id), host_id=int(requested)):
            raise DraftLayoutError("hosting_cycle")
        proposed[int(guest_id)] = int(requested)
        row["glass_host_piece_id"] = int(requested)
        host_instance = piece_id_owner[int(requested)]
        if by_instance[host_instance]["sheet_no"] != row["sheet_no"]:
            raise DraftLayoutError("forged_host")


def _capture_requested_host(raw: Mapping[str, Any], row: dict[str, Any]) -> None:
    if raw.get("glass_host_piece_id") in (None, ""):
        row["_requested_host"] = None
        return
    host = _optional_int(raw.get("glass_host_piece_id"))
    if host is None:
        raise DraftLayoutError("forged_host")
    row["_requested_host"] = host


def contains_forbidden_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        if FORBIDDEN_FIELDS.intersection(value):
            return True
        return any(contains_forbidden_field(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(contains_forbidden_field(item) for item in value)
    return False


def _reject_forbidden(value: Mapping[str, Any]) -> None:
    if contains_forbidden_field(value):
        raise DraftLayoutError("forbidden_field")


def _required_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise DraftLayoutError("invalid_layout")
    return value


def _optional_bool(value: Any, *, default: bool = False) -> bool:
    """Absent transform flags default false so legacy drafts stay readable."""

    if value in (None, ""):
        return bool(default)
    if not isinstance(value, bool):
        raise DraftLayoutError("invalid_layout")
    return value


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _required_int(value: Any) -> int:
    number = _optional_int(value)
    if number is None:
        raise DraftLayoutError("invalid_number")
    return number


def _finite_mm(value: Any) -> float:
    number = _finite_number(value)
    if abs(number) > MAX_ABS_MM:
        raise DraftLayoutError("unbounded")
    return round(number, 4)


def _finite_deg(value: Any) -> float:
    number = _finite_number(value)
    if abs(number) > MAX_ABS_DEG:
        raise DraftLayoutError("unbounded")
    return round(number, 4)


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DraftLayoutError("invalid_number")
    number = float(value)
    if not math.isfinite(number):
        raise DraftLayoutError("unbounded")
    return number
