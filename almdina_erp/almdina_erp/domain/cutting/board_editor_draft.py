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
    """

    if request_source_revision != live_source_revision:
        return "source_conflict"
    if stored_version is not None and stored_source_revision != live_source_revision:
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
        if abs(rotation) > ANGLE_EPS and not trusted[instance]["allow_rotation"]:
            raise DraftLayoutError("rotation_forbidden")
        row = {
            "piece_instance_id": instance,
            "sheet_no": sheet_no,
            "local_x_mm": _finite_mm(raw.get("local_x_mm")),
            "local_y_mm": _finite_mm(raw.get("local_y_mm")),
            "rotation_deg": rotation,
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
