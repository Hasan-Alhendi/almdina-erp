from __future__ import annotations

from copy import deepcopy
from html import unescape
import json
import re
from typing import Any, Mapping

from almdina_erp.almdina_erp.application.security.surface_access import Surface


# Workspace labels are presentation identifiers only. Authorization always comes
# from the server-built surface map; these mappings only tell the projector which
# surface owns a standard Almdina widget or v16 sidebar Link workspace.
WORKSPACE_ENTRY_SURFACES: dict[str, str] = {
    "أنواع القشاط وأسعاره": Surface.EDGE_BANDING_TYPES,
    "الزبائن": Surface.CUSTOMER_ADMIN,
    "إعدادات المعمل": Surface.FACTORY_SETTINGS,
    "Production Defaults": Surface.FACTORY_SETTINGS,
    "Plan PDF Archive": Surface.PLAN_ARCHIVE,
    "Approved Plan PDF Archive": Surface.PLAN_ARCHIVE,
    "إدارة الأدوار": Surface.ROLE_ADMIN,
    "إدارة الصلاحيات": Surface.PERMISSIONS,
    "إدارة المستخدمين": Surface.WORKFORCE,
    "إدارة مسارات الإنتاج": Surface.FACTORY_MASTER_DATA,
    "طلبات قص الدرف": Surface.ORDERS,
    "مراحل الإنتاج": Surface.PRODUCTION_STAGES,
    "القطع التعويضية": Surface.REPLACEMENTS,
    "أخطاء الإنتاج": Surface.PRODUCTION_INCIDENTS,
    "ملخص عمليات المعمل": Surface.REPORT_FACTORY_OPERATIONS_SUMMARY,
    "تحليل طلبات القص": Surface.REPORT_FACTORY_ORDER_ANALYSIS,
    "تحليل استخدام الألواح": Surface.REPORT_BOARD_USAGE,
    "تحليل قياسات الدرف": Surface.REPORT_PIECE_SIZE_USAGE,
    "أداء مراحل الإنتاج": Surface.REPORT_PRODUCTION_STAGE_PERFORMANCE,
    "أخطاء الإنتاج والقطع التعويضية": Surface.REPORT_PRODUCTION_INCIDENTS,
    # v16 sidebar/desktop records can expose link_to instead of the translated label.
    "Door Cutting Order": Surface.ORDERS,
    "Customer": Surface.CUSTOMER_ADMIN,
    "Cutting Plan": Surface.CUTTING_PLANS,
    "Production Stage": Surface.PRODUCTION_STAGES,
    "shop-floor-inbox": Surface.PRODUCTION_STAGES,
    "Production Incident": Surface.PRODUCTION_INCIDENTS,
    "Replacement Piece": Surface.REPLACEMENTS,
    "factory-plan-archive": Surface.PLAN_ARCHIVE,
    "factory-master-data": Surface.FACTORY_MASTER_DATA,
    "Production Routing": Surface.PRODUCTION_ROUTINGS,
    "Edge Banding Type": Surface.EDGE_BANDING_TYPES,
    "Almdina ERP Settings": Surface.FACTORY_SETTINGS,
    "factory-production-settings": Surface.FACTORY_SETTINGS,
    "factory-workforce": Surface.WORKFORCE,
    "factory-permissions": Surface.PERMISSIONS,
    "Role": Surface.ROLE_ADMIN,
    "User": Surface.ROLE_ADMIN,
    # Secondary reports workspace uses untranslated standard labels.
    "Factory Operations Summary": Surface.REPORT_FACTORY_OPERATIONS_SUMMARY,
    "Factory Order Analysis": Surface.REPORT_FACTORY_ORDER_ANALYSIS,
    "Board Usage Analysis": Surface.REPORT_BOARD_USAGE,
    "Piece Size Usage Analysis": Surface.REPORT_PIECE_SIZE_USAGE,
    "Production Stage Performance": Surface.REPORT_PRODUCTION_STAGE_PERFORMANCE,
    "Production Incidents and Replacements": Surface.REPORT_PRODUCTION_INCIDENTS,
}

WORKSPACE_SECTION_SURFACES: dict[str, tuple[str, ...]] = {
    "الإعدادات الأساسية": (
        Surface.CUSTOMER_ADMIN,
        Surface.EDGE_BANDING_TYPES,
        Surface.FACTORY_SETTINGS,
    ),
    "إدارة النظام ومسارات العمل": (
        Surface.ROLE_ADMIN,
        Surface.PERMISSIONS,
        Surface.WORKFORCE,
        Surface.FACTORY_MASTER_DATA,
    ),
    "التشغيل اليومي": (
        Surface.ORDERS,
        Surface.PRODUCTION_STAGES,
        Surface.REPLACEMENTS,
        Surface.PRODUCTION_INCIDENTS,
    ),
    "التقارير التشغيلية والتكلفة": (
        Surface.REPORT_FACTORY_OPERATIONS_SUMMARY,
        Surface.REPORT_FACTORY_ORDER_ANALYSIS,
        Surface.REPORT_BOARD_USAGE,
        Surface.REPORT_PIECE_SIZE_USAGE,
        Surface.REPORT_PRODUCTION_STAGE_PERFORMANCE,
        Surface.REPORT_PRODUCTION_INCIDENTS,
    ),
    "Factory Reports": (
        Surface.REPORT_FACTORY_OPERATIONS_SUMMARY,
        Surface.REPORT_FACTORY_ORDER_ANALYSIS,
        Surface.REPORT_BOARD_USAGE,
        Surface.REPORT_PIECE_SIZE_USAGE,
        Surface.REPORT_PRODUCTION_STAGE_PERFORMANCE,
        Surface.REPORT_PRODUCTION_INCIDENTS,
    ),
}

_TAG_RE = re.compile(r"<[^>]+>")


def _allowed(surface_flags: Mapping[str, Any], surface: str | None) -> bool:
    return bool(surface and surface_flags.get(surface) is True)


def _plain_text(value: Any) -> str:
    text = unescape(str(value or ""))
    text = _TAG_RE.sub(" ", text)
    return " ".join(text.split())


def workspace_surface(item: Mapping[str, Any] | None) -> str | None:
    """Resolve an Almdina Workspace widget/sidebar record to its business surface."""

    if not isinstance(item, Mapping):
        return None
    for key in ("label", "shortcut_name", "link_to", "name", "title"):
        value = str(item.get(key) or "").strip()
        if value in WORKSPACE_ENTRY_SURFACES:
            return WORKSPACE_ENTRY_SURFACES[value]
    return None


def workspace_item_allowed(
    item: Mapping[str, Any] | None,
    surface_flags: Mapping[str, Any],
) -> bool | None:
    """Return True/False for known Almdina entries, None for unknown entries."""

    surface = workspace_surface(item)
    if not surface:
        return None
    return _allowed(surface_flags, surface)


def _section_for_header(block: Mapping[str, Any]) -> tuple[str, ...] | None:
    data = block.get("data") if isinstance(block, Mapping) else None
    if not isinstance(data, Mapping):
        return None
    text = _plain_text(data.get("text"))
    return WORKSPACE_SECTION_SURFACES.get(text)


def filter_workspace_content(content: Any, surface_flags: Mapping[str, Any]) -> Any:
    """Remove denied Almdina blocks before Frappe's editor.js renderer sees them.

    Unknown blocks are preserved; standard Almdina shortcuts are covered by tests.
    Invalid/non-string content is returned unchanged so boot cannot be broken by a
    custom workspace payload.
    """

    if not isinstance(content, str) or not content.strip():
        return content
    try:
        blocks = json.loads(content)
    except (TypeError, ValueError):
        return content
    if not isinstance(blocks, list):
        return content

    filtered: list[Any] = []
    for block in blocks:
        if not isinstance(block, Mapping):
            filtered.append(block)
            continue

        block_type = str(block.get("type") or "").strip().lower()
        data = block.get("data") if isinstance(block.get("data"), Mapping) else {}

        if block_type == "shortcut":
            decision = workspace_item_allowed(data, surface_flags)
            if decision is False:
                continue
        elif block_type == "header":
            section_surfaces = _section_for_header(block)
            if section_surfaces and not any(_allowed(surface_flags, surface) for surface in section_surfaces):
                continue

        filtered.append(block)

    return json.dumps(filtered, ensure_ascii=False, separators=(",", ":"))


def _filter_items(items: Any, surface_flags: Mapping[str, Any]) -> Any:
    if not isinstance(items, list):
        return items
    result: list[Any] = []
    for item in items:
        decision = workspace_item_allowed(
            item if isinstance(item, Mapping) else None,
            surface_flags,
        )
        if decision is False:
            continue
        result.append(item)
    return result


def filter_desktop_page_payload(payload: Any, surface_flags: Mapping[str, Any]) -> Any:
    """Filter Frappe get_desktop_page output using Almdina business surfaces."""

    if not isinstance(payload, dict):
        return payload
    projected = deepcopy(payload)

    shortcuts = projected.get("shortcuts")
    if isinstance(shortcuts, dict):
        shortcuts["items"] = _filter_items(shortcuts.get("items"), surface_flags)

    cards = projected.get("cards")
    if isinstance(cards, dict) and isinstance(cards.get("items"), list):
        kept_cards: list[Any] = []
        for card in cards["items"]:
            if not isinstance(card, dict):
                kept_cards.append(card)
                continue
            original_links = card.get("links")
            links = _filter_items(original_links, surface_flags)
            card["links"] = links
            if links or not isinstance(original_links, list):
                kept_cards.append(card)
        cards["items"] = kept_cards

    return projected


def project_workspace_page(page: Any, surface_flags: Mapping[str, Any]) -> Any:
    """Project one boot workspace metadata record without mutating shared boot data."""

    if not isinstance(page, dict):
        return page
    projected = dict(page)
    if "content" in projected:
        projected["content"] = filter_workspace_content(projected.get("content"), surface_flags)
    return projected


__all__ = [
    "WORKSPACE_ENTRY_SURFACES",
    "WORKSPACE_SECTION_SURFACES",
    "filter_desktop_page_payload",
    "filter_workspace_content",
    "project_workspace_page",
    "workspace_item_allowed",
    "workspace_surface",
]
