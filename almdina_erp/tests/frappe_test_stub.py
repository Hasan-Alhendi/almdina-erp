from __future__ import annotations

import json
import sys
import types
from datetime import datetime
from typing import Any, Callable


def _number(value: Any, cast: Callable[[float], Any], default: Any) -> Any:
    try:
        return cast(float(value or 0))
    except (TypeError, ValueError):
        return default


def install_if_unavailable() -> None:
    """Provide the import surface used by framework-free service tests."""

    try:
        __import__("frappe")
        return
    except ModuleNotFoundError:
        pass

    frappe = types.ModuleType("frappe")
    frappe._ = lambda message: message
    frappe.ValidationError = ValueError
    frappe.PermissionError = PermissionError
    frappe.session = types.SimpleNamespace(user="")
    frappe.local = types.SimpleNamespace(response={})
    frappe.db = types.SimpleNamespace()
    frappe.parse_json = json.loads
    frappe.get_site_path = lambda *parts: "/".join(str(part) for part in parts)

    def throw(message, *_args, **_kwargs):
        raise frappe.ValidationError(str(message))

    frappe.throw = throw

    def whitelist(function=None, **_kwargs):
        if callable(function):
            return function
        return lambda decorated: decorated

    frappe.whitelist = whitelist

    utils = types.ModuleType("frappe.utils")
    utils.flt = lambda value: _number(value, float, 0.0)
    utils.cint = lambda value: _number(value, int, 0)
    utils.get_datetime = lambda value=None: (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value))
        if value
        else datetime.now()
    )
    utils.now_datetime = datetime.now
    frappe.utils = utils

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils


__all__ = ["install_if_unavailable"]
