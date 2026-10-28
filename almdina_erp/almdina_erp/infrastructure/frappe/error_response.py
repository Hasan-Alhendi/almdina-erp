"""Additive public diagnostics. Exceptions and transaction ownership stay in Frappe.

Callers supply presentation projections, never exception dictionaries or snapshots.
Only the explicitly listed fields cross the public boundary. Logging uses the
site's file logger so rollback cannot remove the support reference.
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4
from functools import wraps

import frappe

from almdina_erp.almdina_erp.domain.cutting.layout_diagnostics import public_layout_preview

MAX_PUBLIC_ISSUES = 100
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")


def _text(value: Any, limit: int = 2000) -> str:
    return value[:limit] if isinstance(value, str) else ""


def attach_error_response(
    *, operation: str, title: str, issues: Sequence[Mapping[str, Any]],
    outcome: str = "unknown",
    exception: Exception | None = None,
) -> None:
    """Attach safe JSON before raising the original Frappe exception.

    A reference is public only after the corresponding log write succeeds.
    Neither this helper nor its logging commits, rolls back, or swallows the
    caller's exception. A logging outage must not change business behavior.
    """
    response = getattr(getattr(frappe, "local", None), "response", None)
    if not isinstance(response, dict):
        return
    public = []
    truncated = len(issues) > MAX_PUBLIC_ISSUES
    for item in issues[:MAX_PUBLIC_ISSUES]:
        code = item.get("code")
        if not isinstance(code, str) or not _CODE.fullmatch(code):
            continue
        truncated = truncated or len(item.get("details") or ()) > 20 or len(item.get("table") or ()) > 100
        truncated = truncated or any(isinstance(line, str) and len(line) > 2000 for line in item.get("details") or ())
        truncated = truncated or any(
            len(row) > 20 or any(isinstance(cell, str) and len(cell) > 200 for cell in row)
            for row in item.get("table") or () if isinstance(row, (list, tuple))
        )
        truncated = truncated or any(
            isinstance(item.get(key), str) and len(item[key]) > 2000
            for key in ("problem", "target", "action", "highlight")
        )
        public.append({
            "code": code,
            **{key: _text(item.get(key)) for key in ("category", "problem", "target", "action", "highlight")},
            "details": [_text(line) for line in (item.get("details") or ())[:20] if isinstance(line, str)],
            "table": [
                [_text(cell, 200) for cell in row[:20]]
                for row in (item.get("table") or ())[:100] if isinstance(row, (list, tuple))
            ],
            "preview": public_layout_preview(item.get("preview")),
        })
    reference = uuid4().hex
    event = {
        "request_reference": reference,
        "operation": _text(operation, 80),
        "codes": [item["code"] for item in public],
    }
    if exception is not None:
        # Keep reproducible locations, not exception values, locals, SQL, or
        # source lines that could contain secrets. This stays in the site log.
        event["exception_type"] = type(exception).__name__
        event["frames"] = [
            {"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
            for frame in traceback.extract_tb(exception.__traceback__)[-20:]
        ]
    try:
        logger = frappe.logger("almdina_errors", allow_site=True)
        # Frappe defaults to ERROR. This dedicated, rotating diagnostic channel
        # records expected validation rejections at INFO without changing other logs.
        logger.setLevel(logging.INFO)
        logger.info(json.dumps(event))
    except Exception:
        reference = None
    response["almdina_error"] = {
        "schema_version": 1,
        "operation": _text(operation, 80),
        "title": _text(title, 200),
        "outcome": outcome if outcome in {"rejected", "unknown", "partial"} else "unknown",
        "issues": public,
        "has_more": truncated,
        "validation_coverage": "partial",
        "request_reference": reference,
    }


def record_unexpected_errors(operation: str):
    """Opt-in endpoint boundary: safe feedback, then re-raise for native rollback."""
    def decorate(function):
        @wraps(function)
        def execute(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except Exception as error:
                expected = tuple(
                    kind for name in ("ValidationError", "PermissionError", "AuthenticationError", "DoesNotExistError")
                    if isinstance(kind := getattr(frappe, name, None), type)
                )
                response = getattr(getattr(frappe, "local", None), "response", {})
                if not isinstance(error, expected) and isinstance(response, dict) and "almdina_error" not in response:
                    try:
                        attach_error_response(
                            operation=operation,
                            exception=error,
                            title=frappe._("The operation could not be completed"),
                            issues=[{
                                "code": "UNEXPECTED_ERROR",
                                "problem": frappe._("An unexpected system error prevented completion. Contact support."),
                                "target": "", "action": "",
                            }],
                        )
                    except Exception:
                        # Diagnostics are optional. Preserve the original exception
                        # even if serialization/log infrastructure is unavailable.
                        pass
                raise
        return execute
    return decorate
