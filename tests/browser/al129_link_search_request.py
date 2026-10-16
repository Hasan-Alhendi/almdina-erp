"""Decode the request payload formats Frappe uses for ControlLink searches."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit
from typing import Any


def _decode_nested_payload(value: Any) -> Any:
    if isinstance(value, dict):
        decoded = {}
        for key, item in value.items():
            if key in {"args", "filters"} and isinstance(item, str):
                try:
                    item = json.loads(item)
                except json.JSONDecodeError:
                    pass
            decoded[key] = _decode_nested_payload(item)
        return decoded
    if isinstance(value, list):
        return [_decode_nested_payload(item) for item in value]
    return value


def _parse_form_fields(value: str) -> dict[str, Any]:
    return {
        key: values[0] if len(values) == 1 else values
        for key, values in parse_qs(value, keep_blank_values=True).items()
    }


def _unwrap_args(payload: Any) -> dict[str, Any]:
    for _ in range(4):
        payload = _decode_nested_payload(payload)
        if isinstance(payload, dict) and "args" in payload:
            nested = payload["args"]
            if isinstance(nested, str) and "=" in nested and not nested.lstrip().startswith(("{", "[", '"')):
                nested = _parse_form_fields(nested)
            payload = nested
            continue
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, str) and "=" in payload:
            payload = _parse_form_fields(payload)
            continue
        break
    raise ValueError("Frappe search request does not contain an args mapping")


def normalize_search_link_args(args: dict[str, Any]) -> dict[str, Any]:
    """Normalize JSON/form values while keeping search criteria exact."""
    normalized = _decode_nested_payload(args)
    if not isinstance(normalized, dict):
        raise ValueError("Frappe search args must be a mapping")

    for key, value in tuple(normalized.items()):
        if key == "page_length" and isinstance(value, str) and value.isdecimal():
            normalized[key] = int(value)
        elif key == "ignore_user_permissions" and isinstance(value, str):
            if value.lower() == "true":
                normalized[key] = True
            elif value.lower() == "false":
                normalized[key] = False
    return normalized


def decode_search_link_request_args(url: str, post_data: str | None) -> dict[str, Any]:
    """Decode a Frappe Link request, including encoded/nested RPC ``args``."""
    if post_data:
        try:
            payload = json.loads(post_data)
        except json.JSONDecodeError:
            payload = _parse_form_fields(post_data)
    else:
        payload = _parse_form_fields(urlsplit(url).query)
    return normalize_search_link_args(_unwrap_args(payload))
