from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any


_EXTRA_ADDON_TYPE = "extra_addon"
_LEAF_SUFFIX_RE = re.compile(r"\s*[—-]\s*درفة\s+رقم\s+\d+\s*$")
_ADDON_ALIASES = {
    "liner": "لاينر",
    "لاينر": "لاينر",
    "حفر مسكة غطس": "مسكة غطس",
    "تفريغ مسكة مخفية": "مسكة غطس",
    "مسكة غطس": "مسكة غطس",
}


def _number(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _money(value: Any) -> float:
    return round(_number(value), 2)


def _addon_label(description: Any) -> str:
    text = str(description or "").strip()
    if text.startswith("إضافة "):
        text = text[len("إضافة ") :].strip()
    text = _LEAF_SUFFIX_RE.sub("", text).strip()
    return _ADDON_ALIASES.get(text.casefold(), _ADDON_ALIASES.get(text, text)) or "إضافة"


def summarize_extra_addon_lines(
    lines: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse customer-facing Extra add-ons to one line per add-on type.

    Stored piece-level prices and notes remain untouched.  Only the customer
    document projection is summarized, and the grouped amount is always the sum
    of the original persisted line amounts.
    """

    result: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}

    for source in lines:
        line = dict(source)
        if str(line.get("type") or "").strip() != _EXTRA_ADDON_TYPE:
            result.append(line)
            continue

        label = _addon_label(line.get("description"))
        group = groups.get(label)
        if group is None:
            group = {
                "type": _EXTRA_ADDON_TYPE,
                "description": label,
                "quantity": 0.0,
                "unit": str(line.get("unit") or "درفة").strip() or "درفة",
                "rate_usd": 0.0,
                "amount_usd": 0.0,
                "note": "",
            }
            groups[label] = group
            result.append(group)

        group["quantity"] += _number(line.get("quantity"))
        group["amount_usd"] += _number(line.get("amount_usd"))

    for group in groups.values():
        quantity = _number(group["quantity"])
        amount = _money(group["amount_usd"])
        group["quantity"] = quantity
        group["amount_usd"] = amount
        group["rate_usd"] = _money(amount / quantity) if quantity else 0.0

    return result


__all__ = ["summarize_extra_addon_lines"]
