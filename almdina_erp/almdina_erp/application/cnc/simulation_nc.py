"""Pure helpers for on-demand NC export metadata."""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Mapping
from typing import Any


def nc_content_sha256(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def nc_export_filename(
    *,
    order_name: str,
    cutting_plan: str,
    plan_revision: int,
    sheet_no: int,
    content_sha256: str,
) -> str:
    """Build the on-demand NC download filename ``{order}({board}).nc``.

    ``cutting_plan``, ``plan_revision``, and ``content_sha256`` remain in the
    signature for existing callers; they do not appear in the download name.
    """

    _ = (cutting_plan, plan_revision, content_sha256)
    order = _safe_token(order_name, "order")
    board = int(sheet_no)
    return f"{order}({board}).nc"


def nc_download_payload(
    *,
    filename: str,
    text: str,
    verification: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Encode the already verified NC text once for a Desk JSON download."""

    verdict = dict(verification or {})
    if verdict.get("ok") is not True:
        raise ValueError("nc_verification_failed")
    raw = str(text or "").encode("utf-8")
    encoded = base64.standard_b64encode(raw).decode("ascii")
    if base64.standard_b64decode(encoded) != raw:
        raise ValueError("nc_verification_failed")
    return {
        "filename": str(filename or ""),
        "content_b64": encoded,
        "verification": verdict,
    }


def _safe_token(value: Any, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    text = text.strip("-._")
    return text[:48] or fallback


__all__ = [
    "nc_content_sha256",
    "nc_download_payload",
    "nc_export_filename",
]
