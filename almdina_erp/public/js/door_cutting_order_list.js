(() => {
    "use strict";

    frappe.listview_settings = frappe.listview_settings || {};
    const existing = frappe.listview_settings["Door Cutting Order"] || {};
    const originalOnload = existing.onload;
    const originalRefresh = existing.refresh;

    function rootNode(listview) {
        const wrapper = listview && listview.page && listview.page.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function searchField(listview) {
        return listview && listview.page && listview.page.fields_dict
            ? listview.page.fields_dict.name
            : null;
    }

    function searchInputs(listview) {
        const root = rootNode(listview);
        if (!root) return [];
        return [...root.querySelectorAll(
            ".list-search input, .list-search .form-control, input[data-fieldname='name'], input[placeholder*='ID']"
        )];
    }

    function normalizedTerm(value) {
        return String(value || "")
            .trim()
            .replace(/^%+/, "")
            .replace(/%+$/, "");
    }

    function isNameFilter(filter, doctype) {
        return Array.isArray(filter)
            && filter.length >= 4
            && filter[0] === doctype
            && filter[1] === "name";
    }

    function installCombinedSearch(listview) {
        if (!listview || listview._dcoCombinedSearchInstalled || typeof listview.get_args !== "function") return;
        const originalGetArgs = listview.get_args.bind(listview);

        listview.get_args = function dcoCombinedSearchArgs() {
            const args = originalGetArgs();
            const field = searchField(this);
            const term = normalizedTerm(field && typeof field.get_value === "function" ? field.get_value() : "");
            if (!term) return args;

            // Frappe's standard ID search produces a name filter. Replace only that
            // filter with an OR group while leaving every other list filter as AND.
            args.filters = (args.filters || []).filter(filter => !isNameFilter(filter, this.doctype));
            const pattern = `%${term}%`;
            args.or_filters = [
                [this.doctype, "name", "like", pattern],
                [this.doctype, "customer", "like", pattern],
            ];
            return args;
        };

        listview._dcoCombinedSearchInstalled = true;
    }

    function applySearchHint(listview) {
        const field = searchField(listview);
        if (field && field.df) {
            field.df.label = "اسم العميل أو رقم الطلب";
            field.df.description = "ابحث باسم العميل أو رقم الطلب مثل DCO-2026-00004";
        }
        if (field && typeof field.set_label === "function") {
            field.set_label("اسم العميل أو رقم الطلب");
        }

        const root = rootNode(listview);
        if (root) {
            const wrapper = field && field.wrapper ? (field.wrapper.nodeType ? field.wrapper : field.wrapper[0]) : null;
            const label = wrapper && wrapper.querySelector(".control-label");
            if (label) label.textContent = "اسم العميل أو رقم الطلب";
        }

        searchInputs(listview).forEach(input => {
            input.placeholder = "ابحث باسم العميل أو رقم الطلب (ID)";
            input.setAttribute("aria-label", "البحث باسم العميل أو رقم الطلب");
            input.title = "يمكن البحث باسم العميل أو رقم الطلب مثل DCO-2026-00004";
        });
    }

    function patchDepartmentColumn(listview) {
        if (!listview || listview.__almdina_dept_patch) return;
        listview.__almdina_dept_patch = true;
    }

    function schedule(listview) {
        const root = rootNode(listview);
        if (root) root.classList.add("dco-order-list");
        installCombinedSearch(listview);
        applySearchHint(listview);
        patchDepartmentColumn(listview);
        requestAnimationFrame(() => applySearchHint(listview));
        setTimeout(() => applySearchHint(listview), 180);
        setTimeout(() => applySearchHint(listview), 600);
    }

    frappe.listview_settings["Door Cutting Order"] = Object.assign({}, existing, {
        add_fields: [...new Set([...(existing.add_fields || []), "customer", "order_date", "status"])],
        formatters: Object.assign({}, existing.formatters || {}, {
            current_department(value, df, doc) {
                if (doc.status === "Ready for Delivery") return __("جاهز للتسليم");
                if (doc.status === "Delivered") return __("تم التسليم");
                if (value === "تسليم") {
                    // Legacy rows that still store the vague label.
                    if (doc.status === "Ready for Delivery") return __("جاهز للتسليم");
                    if (doc.status === "Delivered") return __("تم التسليم");
                }
                return value || "";
            },
        }),
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
