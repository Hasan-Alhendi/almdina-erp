(() => {
    "use strict";

    const DOCTYPE = "Door Cutting Order";
    const MAX_TEXT_CHARACTERS = 22;
    const DEFAULT_DESKTOP_PAGE_LENGTH = 500;
    const TRUNCATED_TEXT_FIELDS = Object.freeze([
        "board_description",
        "order_notes",
    ]);

    function escapeHtml(value) {
        if (window.frappe && frappe.utils && typeof frappe.utils.escape_html === "function") {
            return frappe.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function compactOrderId(value) {
        const text = String(value ?? "").trim();
        const match = /^DCO-(\d{4})-(.+)$/.exec(text);
        return match ? `${match[1].slice(-2)}-${match[2]}` : text;
    }

    function truncateListText(value, limit = MAX_TEXT_CHARACTERS) {
        const text = String(value ?? "").trim();
        const characters = Array.from(text);
        if (characters.length <= limit) return text;
        return `${characters.slice(0, limit).join("").trimEnd()}…`;
    }

    function compactListTextFormatter(value, df) {
        const fullText = String(value ?? "").trim();
        if (!fullText) return "";

        const shortText = truncateListText(fullText);
        const fieldname = String(df && df.fieldname || "").trim();
        if (!fieldname) {
            return `<span class="dco-list-compact-text ellipsis" title="${escapeHtml(fullText)}">${escapeHtml(shortText)}</span>`;
        }

        return `<button type="button" class="filterable dco-list-compact-text dco-list-filterable-text ellipsis" data-filter="${escapeHtml(fieldname)},=,${escapeHtml(fullText)}" title="${escapeHtml(fullText)}" aria-label="${escapeHtml(fullText)}">${escapeHtml(shortText)}</button>`;
    }

    function applyDefaultDesktopPageLength(listview) {
        if (!listview || listview._dcoDefaultPageLengthApplied) return;
        const isMobile = typeof frappe.is_mobile === "function" && frappe.is_mobile();
        if (isMobile) return;

        listview.start = 0;
        listview.page_length = DEFAULT_DESKTOP_PAGE_LENGTH;
        listview.selected_page_count = DEFAULT_DESKTOP_PAGE_LENGTH;
        listview._dcoDefaultPageLengthApplied = true;

        const pagingArea = listview.$paging_area;
        if (!pagingArea || typeof pagingArea.find !== "function") return;
        pagingArea.find(".btn-paging").removeClass("btn-info").prop("disabled", false);
        pagingArea
            .find(`.btn-paging[data-value="${DEFAULT_DESKTOP_PAGE_LENGTH}"]`)
            .addClass("btn-info")
            .prop("disabled", true);
    }

    frappe.listview_settings = frappe.listview_settings || {};
    const existing = frappe.listview_settings[DOCTYPE] || {};
    const originalOnload = existing.onload;
    const formatters = Object.assign({}, existing.formatters || {}, {
        name: compactOrderId,
    });

    TRUNCATED_TEXT_FIELDS.forEach(fieldname => {
        formatters[fieldname] = compactListTextFormatter;
    });

    frappe.listview_settings[DOCTYPE] = Object.assign({}, existing, {
        formatters,
        onload(listview) {
            if (typeof originalOnload === "function") originalOnload(listview);
            applyDefaultDesktopPageLength(listview);
        },
    });

    window.AlmdinaDcoCompactListUX = Object.freeze({
        DEFAULT_DESKTOP_PAGE_LENGTH,
        MAX_TEXT_CHARACTERS,
        applyDefaultDesktopPageLength,
        compactListTextFormatter,
        compactOrderId,
        truncateListText,
    });
})();
