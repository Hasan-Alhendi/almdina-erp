"""Small constructors checks shared by customer-bot values."""

from __future__ import annotations


def required_token(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    token = value.strip()
    if not token:
        raise ValueError(f"{field_name} is required")
    return token


def required_bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field_name} must be a bool")
    return value
