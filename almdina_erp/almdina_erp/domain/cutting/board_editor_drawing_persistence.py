"""Persistence rules for one drawing document per piece.

This module does not store rows and does not compile manufacturing geometry.
A drawing fingerprint identifies the saved vector document, including reference
placement. It is not a cutting-plan geometry identity.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import decide_draft_write

DRAWABLE_PIECE_TYPE = "Special"
BLANK_MATCH_TOLERANCE_MM = 0.05
MAX_DRAWING_ARCHIVES = 20
# Twenty maximum-size drawing documents plus archive metadata. Exceeding this
# refuses the new archive instead of dropping an older entry.
MAX_ARCHIVE_UTF8_BYTES = 21_000_000


def drawing_key(order_name: str, plan_name: str, piece_instance_id: str) -> str:
    """Stable row identity. Knowing the key is not authorization."""

    raw = (
        f"{str(order_name).strip()}\n{str(plan_name).strip()}\n{str(piece_instance_id).strip()}"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def drawing_catalog_from_pieces(pieces: Sequence[Mapping[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """Trusted piece facts copied from a server projection, never from the drawing."""

    catalog: dict[str, dict[str, Any]] = {}
    for piece in pieces or []:
        if not isinstance(piece, Mapping):
            continue
        instance = str(piece.get("piece_instance_id") or "").strip()
        if not instance or instance in catalog:
            continue
        catalog[instance] = {
            "piece_type": str(piece.get("piece_type") or ""),
            "blank_width_mm": _cm_to_mm(_first_present(piece, ("original_w", "width_cm"))),
            "blank_length_mm": _cm_to_mm(_first_present(piece, ("original_h", "length_cm"))),
        }
        outline = piece.get("editable_outline_mm")
        if isinstance(outline, list) and len(outline) >= 3:
            catalog[instance]["editable_outline_mm"] = outline
    return catalog


def blank_matches(
    width_mm: float,
    length_mm: float,
    *,
    trusted_width_mm: float,
    trusted_length_mm: float,
) -> bool:
    return (
        abs(float(width_mm) - float(trusted_width_mm)) <= BLANK_MATCH_TOLERANCE_MM
        and abs(float(length_mm) - float(trusted_length_mm)) <= BLANK_MATCH_TOLERANCE_MM
    )


def untrusted_reference_ids(
    document: Mapping[str, Any],
    trusted_file_ids: Sequence[str] | None,
) -> list[str]:
    """File ids the server has not proven for this piece.

    An empty trusted set rejects every reference. Client file ids are never
    looked up from the document alone.
    """

    trusted = {str(item) for item in (trusted_file_ids or []) if str(item or "").strip()}
    found: list[str] = []
    for reference in document.get("references") or []:
        if not isinstance(reference, Mapping):
            continue
        file_id = str(reference.get("file_id") or "")
        if file_id not in trusted:
            found.append(file_id)
    return found


def decide_drawing_write(
    *,
    stored_version: int | None,
    stored_fingerprint: str | None,
    stored_source_revision: str | None,
    expected_version: int,
    document_fingerprint: str,
    live_source_revision: str,
    request_source_revision: str,
) -> str:
    """Same create/update/idempotent/conflict rules as a board-editor draft.

    The fingerprint compared here is the drawing document fingerprint, not the
    distribution fingerprint.
    """

    return decide_draft_write(
        stored_version=stored_version,
        stored_fingerprint=stored_fingerprint,
        stored_source_revision=stored_source_revision,
        expected_version=expected_version,
        layout_fingerprint=document_fingerprint,
        live_source_revision=live_source_revision,
        request_source_revision=request_source_revision,
    )


def build_prior_drawing_archive(row: Mapping[str, Any]) -> dict[str, Any]:
    """Retain one superseded drawing. This does not make it active again."""

    drawing = row.get("drawing_json")
    return {
        "archived_drawing_version": int(row.get("drawing_version") or 0),
        "source_content_revision": str(row.get("source_content_revision") or ""),
        "source_input_fingerprint": str(row.get("source_input_fingerprint") or ""),
        "document_fingerprint": str(row.get("document_fingerprint") or ""),
        "piece_instance_id": str(row.get("piece_instance_id") or ""),
        "drawing": drawing if isinstance(drawing, Mapping) else None,
    }


def archive_stack_exceeds_limit(stack: Sequence[Mapping[str, Any]]) -> bool:
    if len(stack) > MAX_DRAWING_ARCHIVES:
        return True
    encoded = json.dumps(list(stack), separators=(",", ":"), sort_keys=True).encode("utf-8")
    return len(encoded) > MAX_ARCHIVE_UTF8_BYTES


def _first_present(piece: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        value = piece.get(name)
        if value not in (None, ""):
            return value
    return None


def _cm_to_mm(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return round(number * 10.0, 3)


__all__ = [
    "BLANK_MATCH_TOLERANCE_MM",
    "DRAWABLE_PIECE_TYPE",
    "MAX_ARCHIVE_UTF8_BYTES",
    "MAX_DRAWING_ARCHIVES",
    "archive_stack_exceeds_limit",
    "blank_matches",
    "build_prior_drawing_archive",
    "decide_drawing_write",
    "drawing_catalog_from_pieces",
    "drawing_key",
    "untrusted_reference_ids",
]
