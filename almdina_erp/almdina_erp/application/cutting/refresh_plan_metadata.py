from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


PLACED_PIECE_METADATA_FIELDS = (
    "label",
    "source_piece_no",
    "copy_no",
    "group_qty",
    "original_w",
    "original_h",
    "area_m2",
    "notes",
    "piece_type",
    "clipped_corner_position",
    "clipped_corner_width_cm",
    "clipped_corner_length_cm",
    "special_shape_geometry_json",
    "edge_long_right",
    "edge_long_left",
    "edge_width_top",
    "edge_width_bottom",
    "edge_type",
    "edge_rate_usd",
    "edge_cost_usd",
)


def refresh_plan_metadata(
    snapshot: dict[str, Any],
    *,
    expanded_pieces: Iterable[dict[str, Any]],
    input_fingerprint: str,
    metadata_fingerprint: str,
) -> dict[str, Any]:
    """Return a refreshed snapshot without rerunning placement or mutating the input."""

    refreshed = deepcopy(snapshot)
    current_by_id = {
        _integer(piece.get("id")): dict(piece)
        for piece in expanded_pieces
    }

    for sheet in refreshed.get("sheets") or []:
        for placed in sheet.get("pieces") or []:
            current = current_by_id.get(_integer(placed.get("id")))
            if not current:
                continue
            for fieldname in PLACED_PIECE_METADATA_FIELDS:
                if fieldname in current:
                    placed[fieldname] = current[fieldname]

    refreshed["input_fingerprint"] = str(input_fingerprint or "")
    refreshed["metadata_fingerprint"] = str(metadata_fingerprint or "")
    return refreshed


def _integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


__all__ = ["PLACED_PIECE_METADATA_FIELDS", "refresh_plan_metadata"]
