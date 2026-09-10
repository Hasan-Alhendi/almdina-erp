(() => {
    "use strict";

    const DOCTYPE = "Door Cutting Order";
    const MAX_TEXT_CHARACTERS = 22;
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

    frappe.listview_settings = frappe.listview_settings || {};
    const existing = frappe.listview_settings[DOCTYPE] || {};
    const formatters = Object.assign({}, existing.formatters || {}, {
        name: compactOrderId,
    });

    TRUNCATED_TEXT_FIELDS.forEach(fieldname => {
        formatters[fieldname] = compactListTextFormatter;
    });

    frappe.listview_settings[DOCTYPE] = Object.assign({}, existing, {
        formatters,
    });

    window.AlmdinaDcoCompactListUX = Object.freeze({
        MAX_TEXT_CHARACTERS,
        compactListTextFormatter,
        compactOrderId,
        truncateListText,
    });
})();
