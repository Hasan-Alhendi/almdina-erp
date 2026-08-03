(() => {
    "use strict";

    const CARD_MAX_WIDTH = 900;
    const METHODS = Object.freeze({
        doctype: "Door Cutting Order",
    });
    const STATUS_LABELS = Object.freeze({
        Draft: "مسودة",
        "Pending Review": "بانتظار المراجعة",
        Approved: "معتمد",
        "At Sharyoun": "عند الشريون",
        "At Drawing": "عند الرسم",
        "At CNC": "عند CNC",
        "At Sanding": "عند التقشيط",
        "Ready for Delivery": "جاهز للتسليم",
        Delivered: "تم التسليم",
        Rejected: "مرفوض",
        "On Hold": "متوقف",
        Cancelled: "ملغى",
    });
    const STAGE_BY_DEPARTMENT = Object.freeze({
        "شريون": "Sharyoun",
        "رسم": "Drawing",
        CNC: "CNC",
        "تقشيط": "Sanding",
    });

    frappe.listview_settings = frappe.listview_settings || {};
    const existing = frappe.listview_settings[METHODS.doctype] || {};
    const originalOnload = existing.onload;
    const originalRefresh = existing.refresh;

    function rootNode(listview) {
        const wrapper = listview && listview.page && listview.page.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function escapeHtml(value) {
        if (frappe.utils && typeof frappe.utils.escape_html === "function") {
            return frappe.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function displayValue(value) {
        const normalized = String(value ?? "").trim();
        return normalized || "—";
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

            // Replace only Frappe's standard ID filter. All other filters remain AND.
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

    function availableWidth(root) {
        const widths = [
            root && root.getBoundingClientRect ? root.getBoundingClientRect().width : 0,
            document.documentElement && document.documentElement.clientWidth,
            window.innerWidth,
            window.screen && window.screen.width,
        ].filter(width => Number.isFinite(width) && width >= 280);
        return widths.length ? Math.min(...widths) : Number.POSITIVE_INFINITY;
    }

    function applyCardLayoutClass(listview) {
        const root = rootNode(listview);
        if (!root) return;
        root.classList.add("dco-order-list");
        root.classList.toggle("dco-order-card-layout", availableWidth(root) <= CARD_MAX_WIDTH);
    }

    function orderDocuments(listview) {
        return new Map((listview.data || []).map(doc => [String(doc.name || ""), doc]));
    }

    function rowDocumentName(container, fallback) {
        const named = [container, container.querySelector("[data-name]")]
            .find(element => element && element.dataset && element.dataset.name);
        if (named) return String(named.dataset.name);

        const link = container.querySelector("a[href*='/door-cutting-order/']");
        if (link) {
            const segment = String(link.getAttribute("href") || "").split("/").filter(Boolean).pop();
            if (segment) return decodeURIComponent(segment);
        }
        return String((fallback && fallback.name) || "");
    }

    function dateLabel(value) {
        if (!value) return "—";
        if (frappe.datetime && typeof frappe.datetime.str_to_user === "function") {
            return frappe.datetime.str_to_user(value);
        }
        return String(value);
    }

    function statusLabel(doc) {
        if (doc.status === "Ready for Delivery") return __("جاهز للتسليم");
        if (doc.status === "Delivered") return __("تم التسليم");
        return __(STATUS_LABELS[doc.status] || doc.status || "غير محدد");
    }

    function statusTone(status) {
        if (["Ready for Delivery", "Delivered"].includes(status)) return "is-success";
        if (["Rejected", "Cancelled", "On Hold"].includes(status)) return "is-danger";
        if (["At Sharyoun", "At Drawing", "At CNC", "At Sanding"].includes(status)) return "is-active";
        return "is-neutral";
    }

    function productionPathLabel(path) {
        if (path === "Sharyoun") return __("شريون ثم تقشيط");
        if (path === "Drawing") return __("رسم ثم CNC ثم تقشيط");
        return displayValue(path);
    }

    function quickActionContext(doc) {
        const assignedToCurrentUser = Boolean(
            doc.current_assignee
            && frappe.session
            && doc.current_assignee === frappe.session.user
        );
        return {
            order: doc.name,
            stage: doc.current_production_stage,
            stageType: STAGE_BY_DEPARTMENT[doc.current_department] || doc.current_department,
            canStart: assignedToCurrentUser && doc.department_status === "بحاجة للعمل",
            canHandoff: assignedToCurrentUser && doc.department_status === "قيد العمل",
        };
    }

    function field(label, value, className = "") {
        return `
            <div class="dco-card-field ${className}">
                <span>${escapeHtml(__(label))}</span>
                <b>${escapeHtml(displayValue(value))}</b>
            </div>
        `;
    }

    function buildCard(doc, hasSelection) {
        const context = quickActionContext(doc);
        const quickActions = window.AlmdinaShopFloorQuickActions;
        const action = quickActions && quickActions.actionFor(context);
        const actionClass = action && action.indicator === "success" ? "btn-success" : "btn-primary";
        return `
            <article class="dco-mobile-order-card" data-order-name="${escapeHtml(doc.name)}">
                <header class="dco-card-header">
                    <div class="dco-card-identity">
                        <button type="button" class="dco-card-order-link" aria-label="${escapeHtml(__("فتح الطلب"))} ${escapeHtml(doc.name)}">
                            ${escapeHtml(doc.name)}
                        </button>
                        <span class="dco-card-customer">${escapeHtml(displayValue(doc.customer))}</span>
                    </div>
                    <div class="dco-card-header-actions">
                        <span class="dco-card-status ${statusTone(doc.status)}">${escapeHtml(statusLabel(doc))}</span>
                        ${hasSelection ? `<input type="checkbox" class="dco-card-select" aria-label="${escapeHtml(__("تحديد الطلب"))} ${escapeHtml(doc.name)}">` : ""}
                    </div>
                </header>
                <div class="dco-card-fields">
                    ${field("لون القشاط", doc.edge_color, "dco-card-edge-color")}
                    ${field("صنف اللوح", doc.board_description)}
                    ${field("القسم الحالي", doc.current_department)}
                    ${field("حالة المرحلة", doc.department_status)}
                    ${field("العامل", doc.current_assignee)}
                    ${field("تاريخ الطلب", dateLabel(doc.order_date))}
                    ${field("مسار الإنتاج", productionPathLabel(doc.production_path), "dco-card-wide-field")}
                </div>
                <footer class="dco-card-actions">
                    ${action ? `<button type="button" class="btn ${actionClass} dco-card-production-action">${escapeHtml(action.label)}</button>` : ""}
                    <button type="button" class="btn btn-default dco-card-open">${escapeHtml(__("فتح الطلب"))}</button>
                </footer>
            </article>
        `;
    }

    function bindCard(listview, container, card, doc, originalCheckbox) {
        const open = event => {
            event.preventDefault();
            event.stopPropagation();
            frappe.set_route("Form", METHODS.doctype, doc.name);
        };
        card.querySelector(".dco-card-order-link").addEventListener("click", open);
        card.querySelector(".dco-card-open").addEventListener("click", open);

        const mobileCheckbox = card.querySelector(".dco-card-select");
        if (mobileCheckbox && originalCheckbox) {
            mobileCheckbox.checked = Boolean(originalCheckbox.checked);
            mobileCheckbox.addEventListener("click", event => event.stopPropagation());
            mobileCheckbox.addEventListener("change", event => {
                event.stopPropagation();
                if (Boolean(originalCheckbox.checked) !== Boolean(mobileCheckbox.checked)) {
                    originalCheckbox.click();
                }
                mobileCheckbox.checked = Boolean(originalCheckbox.checked);
            });
        }

        const actionButton = card.querySelector(".dco-card-production-action");
        if (actionButton && window.AlmdinaShopFloorQuickActions) {
            actionButton.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                window.AlmdinaShopFloorQuickActions.perform(quickActionContext(doc), {
                    button: actionButton,
                    onSuccess: () => listview.refresh(),
                });
            });
        }
        container.classList.add("dco-order-card-container");
    }

    function renderMobileCards(listview) {
        const root = rootNode(listview);
        if (!root) return;
        applyCardLayoutClass(listview);
        const docs = orderDocuments(listview);
        const containers = [...root.querySelectorAll(".list-row-container")];
        containers.forEach((container, index) => {
            container.classList.remove("dco-order-card-container");
            const previous = [...container.children]
                .find(child => child.classList.contains("dco-mobile-order-card"));
            if (previous) previous.remove();
            const fallback = (listview.data || [])[index];
            const name = rowDocumentName(container, fallback);
            const doc = docs.get(name) || fallback;
            if (!doc || !doc.name) return;
            const originalCheckbox = container.querySelector("input.list-row-checkbox, input[type='checkbox']");
            const holder = document.createElement("div");
            holder.innerHTML = buildCard(doc, Boolean(originalCheckbox)).trim();
            const card = holder.firstElementChild;
            if (!card) return;
            container.appendChild(card);
            bindCard(listview, container, card, doc, originalCheckbox);
        });
    }

    function installResponsiveObserver(listview) {
        const root = rootNode(listview);
        if (!root || listview._dcoResponsiveObserverInstalled) return;
        const refreshLayout = () => applyCardLayoutClass(listview);
        if (typeof ResizeObserver === "function") {
            listview._dcoResponsiveObserver = new ResizeObserver(refreshLayout);
            listview._dcoResponsiveObserver.observe(root);
        }
        window.addEventListener("resize", refreshLayout, { passive: true });
        listview._dcoResponsiveObserverInstalled = true;
    }

    function schedule(listview) {
        const root = rootNode(listview);
        if (root) root.classList.add("dco-order-list");
        installCombinedSearch(listview);
        installResponsiveObserver(listview);
        applySearchHint(listview);
        renderMobileCards(listview);
        requestAnimationFrame(() => {
            applySearchHint(listview);
            renderMobileCards(listview);
        });
        setTimeout(() => renderMobileCards(listview), 100);
        setTimeout(() => {
            applySearchHint(listview);
            renderMobileCards(listview);
        }, 350);
    }

    frappe.listview_settings[METHODS.doctype] = Object.assign({}, existing, {
        add_fields: [...new Set([
            ...(existing.add_fields || []),
            "customer", "order_date", "status",
            "board_description", "edge_color", "production_path",
            "current_department", "current_assignee", "department_status",
            "current_production_stage",
        ])],
        formatters: Object.assign({}, existing.formatters || {}, {
            current_department(value, df, doc) {
                if (doc.status === "Ready for Delivery") return __("جاهز للتسليم");
                if (doc.status === "Delivered") return __("تم التسليم");
                if (value === "تسليم") {
                    if (doc.status === "Ready for Delivery") return __("جاهز للتسليم");
                    if (doc.status === "Delivered") return __("تم التسليم");
                }
                return value || "";
            },
            edge_color(value) {
                return value ? `<span class="dco-list-edge-color">${escapeHtml(value)}</span>` : "";
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

    window.AlmdinaDoorCuttingOrderListUX = Object.freeze({
        buildCard,
        quickActionContext,
        renderMobileCards,
    });
})();
