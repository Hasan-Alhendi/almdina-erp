from __future__ import annotations

from typing import Any, Mapping


REPORTS_SECTION_ICON = "es-line-reports"

SHORTCUT_ICONS_BY_LABEL: dict[str, str] = {
    "الزبائن": "users",
    "أنواع القشاط وأسعاره": "tool",
    "إعدادات المعمل": "setting",
    "إدارة الأدوار": "shield",
    "إدارة الصلاحيات": "lock",
    "إدارة المستخدمين": "hr",
    "إدارة مسارات الإنتاج": "branch",
    "طلبات قص الدرف": "clipboard",
    "مراحل الإنتاج": "organization",
    "القطع التعويضية": "duplicate",
    "أخطاء الإنتاج": "close",
    "ملخص عمليات المعمل": "es-line-chart",
    "تحليل طلبات القص": "es-line-reports",
    "تحليل استخدام الألواح": "table",
    "تحليل قياسات الدرف": "small-file",
    "أداء مراحل الإنتاج": "timer",
    "أخطاء الإنتاج والقطع التعويضية": "es-line-reports",
}

LABEL_ICON_ALIASES: dict[str, str] = {
    "الرئيسية": "home",
    "Home": "home",
    "إدارة المعمل": "tool",
    "Almdina ERP": "tool",
    "Customers": "users",
    "Customer": "users",
    "Edge Banding Types": "tool",
    "Edge Banding Type": "tool",
    "Factory Settings": "setting",
    "Role Management": "shield",
    "Role": "shield",
    "Permission Management": "lock",
    "Permissions": "lock",
    "User Management": "hr",
    "Workforce": "hr",
    "Production Routing": "branch",
    "Factory Master Data": "branch",
    "Door Cutting Orders": "clipboard",
    "Door Cutting Order": "clipboard",
    "Production Orders": "clipboard",
    "Production Stages": "organization",
    "Shop Floor": "organization",
    "shop-floor-inbox": "organization",
    "Replacement Parts": "duplicate",
    "Production Errors": "close",
    "Production Error": "close",
    "Factory Operations Summary": "es-line-chart",
    "Cutting Order Analysis": "es-line-reports",
    "Board Usage Analysis": "table",
    "Door Measurement Analysis": "small-file",
    "Production Stage Performance": "timer",
}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def icon_for_label(label: Any) -> str | None:
    normalized = _normalize_text(label)
    if not normalized:
        return None
    if normalized in SHORTCUT_ICONS_BY_LABEL:
        return SHORTCUT_ICONS_BY_LABEL[normalized]
    for candidate, icon in SHORTCUT_ICONS_BY_LABEL.items():
        if candidate in normalized or normalized in candidate:
            return icon
    return LABEL_ICON_ALIASES.get(normalized)


def icon_for_sidebar_item(item: Mapping[str, Any]) -> str | None:
    for key in ("label", "link_to", "name", "title"):
        icon = icon_for_label(item.get(key))
        if icon:
            return icon
    return None


def apply_sidebar_icon_catalog(bootinfo: dict[str, Any]) -> None:
    """Align v16 sidebar item icons with the Almdina workspace home catalog."""

    container = bootinfo.get("workspace_sidebar_item")
    if not isinstance(container, dict):
        return

    for sidebar in container.values():
        if not isinstance(sidebar, dict):
            continue
        items = sidebar.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip() in {"Section Break", "Spacer"}:
                continue
            icon = icon_for_sidebar_item(item)
            if icon:
                item["icon"] = icon


__all__ = [
    "REPORTS_SECTION_ICON",
    "SHORTCUT_ICONS_BY_LABEL",
    "LABEL_ICON_ALIASES",
    "apply_sidebar_icon_catalog",
    "icon_for_label",
    "icon_for_sidebar_item",
]
