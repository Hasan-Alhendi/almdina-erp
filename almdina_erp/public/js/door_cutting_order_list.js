(() => {
    "use strict";

    frappe.listview_settings = frappe.listview_settings || {};
    const existing = frappe.listview_settings["Door Cutting Order"] || {};
    const originalOnload = existing.onload;
    const originalRefresh = existing.refresh;

    function searchInputs(listview) {
        const page = listview && listview.page;
        const wrapper = page && page.wrapper;
        const root = wrapper && (wrapper[0] || wrapper);
        if (!root) return [];
        return [...root.querySelectorAll(
            ".list-search input, .list-search .form-control, input[data-fieldname='_search'], input[placeholder*='ID']"
        )];
    }

    function applySearchHint(listview) {
        searchInputs(listview).forEach(input => {
            input.placeholder = "ابحث باسم العميل أو رقم الطلب (ID)";
            input.setAttribute("aria-label", "البحث باسم العميل أو رقم الطلب");
            input.title = "يمكن البحث باسم العميل أو رقم الطلب مثل DCO-2026-00004";
        });
    }

    function schedule(listview) {
        applySearchHint(listview);
        requestAnimationFrame(() => applySearchHint(listview));
        setTimeout(() => applySearchHint(listview), 180);
        setTimeout(() => applySearchHint(listview), 600);
    }

    frappe.listview_settings["Door Cutting Order"] = Object.assign({}, existing, {
        add_fields: [...new Set([...(existing.add_fields || []), "customer", "order_date", "status"])],
        onload(listview) {
            if (typeof originalOnload === "function") originalOnload(listview);
            schedule(listview);
        },
        refresh(listview) {
            if (typeof originalRefresh === "function") originalRefresh(listview);
            schedule(listview);
        },
    });
})();
