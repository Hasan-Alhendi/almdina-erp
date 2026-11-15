"""Pure helpers for on-demand NC export metadata."""

from __future__ import annotations

import hashlib
import re
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
    """Build a deterministic on-demand NC download filename."""

    digest = str(content_sha256 or "")[:12] or "empty"
    parts = [
        _safe_token(order_name, "order"),
        _safe_token(cutting_plan, "plan"),
        f"r{int(plan_revision)}",
        f"sheet{int(sheet_no)}",
        digest,
    ]
    return f"{'_'.join(parts)}.nc"


def _safe_token(value: Any, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    text = text.strip("-._")
    return text[:48] or fallback


__all__ = [
    "nc_export_filename",
    "nc_content_sha256",
]
