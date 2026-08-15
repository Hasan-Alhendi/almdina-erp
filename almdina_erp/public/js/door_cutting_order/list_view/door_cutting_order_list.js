(() => {
    "use strict";

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
                ...(args.or_filters || []),
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

    function isPhoneLayout(root) {
        const responsiveDevice = window.AlmdinaResponsiveDevice;
        if (
            responsiveDevice
            && typeof responsiveDevice.usesCardLayout === "function"
        ) {
            return responsiveDevice.usesCardLayout(root);
        }
        if (
            responsiveDevice
            && typeof responsiveDevice.isPhoneLayout === "function"
        ) {
            return responsiveDevice.isPhoneLayout(root);
        }
        // Last-resort fallback when the shared detector is unavailable.
        try {
            return Boolean(
                window.matchMedia
                && window.matchMedia("(max-width: 600px)").matches
            );
        } catch (error) {
            return false;
        }
    }

    function applyCardLayoutClass(listview) {
        const root = rootNode(listview);
        if (!root) return false;
        const enabled = isPhoneLayout(root);
        root.classList.add("dco-order-list");
        root.classList.toggle("dco-order-card-layout", enabled);
        return enabled;
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
        const authorized = doc.__almdinaProductionActionContext || {};
        return {
            order: doc.name,
            stage: authorized.stage || doc.current_production_stage,
            stageType: STAGE_BY_DEPARTMENT[doc.current_department] || doc.current_department,
            canStart: authorized.canStart === true,
            canHandoff: authorized.canHandoff === true,
        };
    }

    function field(label, value, className = "") {
        if (!String(value ?? "").trim()) return "";
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
        const department = String(doc.current_department || "").trim() || __("لم يبدأ الإنتاج");
        const departmentStatus = String(doc.department_status || "").trim() || __("غير مسند");
        const assignee = String(doc.current_assignee || "").trim();
        return `
            <article class="dco-mobile-order-card" data-order-name="${escapeHtml(doc.name)}">
                <header class="dco-card-header">
                    <div class="dco-card-leading">
                        ${hasSelection ? `<input type="checkbox" class="dco-card-select" aria-label="${escapeHtml(__("تحديد الطلب"))} ${escapeHtml(doc.name)}">` : ""}
                        <div class="dco-card-identity">
                            <button type="button" class="dco-card-order-link" aria-label="${escapeHtml(__("فتح الطلب"))} ${escapeHtml(doc.name)}">
                                ${escapeHtml(doc.name)}
                            </button>
                            <span class="dco-card-customer">${escapeHtml(displayValue(doc.customer))}</span>
                        </div>
                    </div>
                    <div class="dco-card-header-actions">
                        <span class="dco-card-status ${statusTone(doc.status)}">${escapeHtml(statusLabel(doc))}</span>
                    </div>
                </header>
                <section class="dco-card-workflow" aria-label="${escapeHtml(__("حالة الإنتاج"))}">
                    <div class="dco-card-workflow-main">
                        <span class="dco-card-workflow-label">${escapeHtml(__("المرحلة الحالية"))}</span>
                        <b class="dco-card-workflow-value">${escapeHtml(department)}</b>
                    </div>
                    <span class="dco-card-stage-status">${escapeHtml(departmentStatus)}</span>
                    ${assignee ? `
                        <div class="dco-card-assignee">
                            <span class="dco-card-assignee-label">${escapeHtml(__("العامل"))}</span>
                            <b class="dco-card-assignee-value">${escapeHtml(assignee)}</b>
                        </div>
                    ` : ""}
                </section>
                <div class="dco-card-fields">
                    ${field("صنف اللوح", doc.board_description, "dco-card-wide-field")}
                    ${field("لون القشاط", doc.edge_color, "dco-card-edge-color")}
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
        const docs = orderDocuments(listview);
        const allContainers = [...root.querySelectorAll(".list-row-container")];
        allContainers.forEach(container => {
            container.classList.remove("dco-order-card-container");
            const previous = [...container.children]
                .find(child => child.classList.contains("dco-mobile-order-card"));
            if (previous) previous.remove();
        });
        // The list header uses the same .list-row-container class in Frappe.
        // Only containers that resolve to an actual document may receive cards.
        const containers = allContainers
            .map(container => ({ container, name: rowDocumentName(container) }))
            .filter(item => item.name && docs.has(item.name));
        if (!applyCardLayoutClass(listview)) return;

        containers.forEach(({ container, name }) => {
            const doc = docs.get(name);
            if (!doc) return;
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
        const refreshLayout = () => {
            const wasPhoneLayout = root.classList.contains("dco-order-card-layout");
            const needsPhoneLayout = isPhoneLayout(root);
            if (wasPhoneLayout !== needsPhoneLayout) {
                renderMobileCards(listview);
                return;
            }
            // Keep cards in sync when the list reflows while already in card mode.
            if (needsPhoneLayout) renderMobileCards(listview);
        };
        if (typeof ResizeObserver === "function") {
            listview._dcoResponsiveObserver = new ResizeObserver(refreshLayout);
            listview._dcoResponsiveObserver.observe(root);
        }
        window.addEventListener("resize", refreshLayout, { passive: true });
        if (window.matchMedia) {
            try {
                const media = window.matchMedia("(max-width: 600px)");
                const onMedia = () => refreshLayout();
                if (typeof media.addEventListener === "function") {
                    media.addEventListener("change", onMedia);
                } else if (typeof media.addListener === "function") {
                    media.addListener(onMedia);
                }
                listview._dcoCardMediaQuery = media;
                listview._dcoCardMediaHandler = onMedia;
            } catch (error) {
                /* matchMedia unavailable */
            }
        }
        listview._dcoResponsiveObserverInstalled = true;
    }

    function installRowsObserver(listview) {
        if (listview._dcoRowsObserverInstalled || typeof MutationObserver !== "function") return;
        const root = rootNode(listview);
        const result = root && root.querySelector(".result");
        if (!result) return;

        let scheduled = false;
        const observer = new MutationObserver(mutations => {
            if (listview._dcoApplyingRolePresentation) return;
            const frappeRowsAdded = mutations.some(mutation =>
                [...mutation.addedNodes].some(node =>
                    node.nodeType === 1
                    && (node.matches(".list-row-container") || node.querySelector(".list-row-container"))
                )
            );
            if (!frappeRowsAdded || scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                renderMobileCards(listview);
                applyOperationalRoleRows(listview);
            });
        });
        observer.observe(result, { childList: true, subtree: true });
        listview._dcoRowsObserver = observer;
        listview._dcoRowsObserverInstalled = true;
    }

    function clearOperationalRoleRows(listview) {
        const root = rootNode(listview);
        if (!root) return;
        root.querySelectorAll(".dco-list-row-other-role,.dco-list-row-completed").forEach(node => {
            node.classList.remove("dco-list-row-other-role");
            node.classList.remove("dco-list-row-completed");
        });
    }

    function compareServerTimes(left, right, fieldname, direction) {
        const leftValue = String(left.flag && left.flag[fieldname] || "");
        const rightValue = String(right.flag && right.flag[fieldname] || "");
        if (!leftValue && !rightValue) return left.name.localeCompare(right.name);
        if (!leftValue) return 1;
        if (!rightValue) return -1;
        const compared = leftValue.localeCompare(rightValue);
        return compared ? compared * direction : left.name.localeCompare(right.name);
    }

    function applyOperationalRolePresentation(listview, payload) {
        const root = rootNode(listview);
        const result = root && root.querySelector(".result");
        if (!root || !result) return;

        const personalView = Boolean(payload && payload.personal_view);
        const flags = payload && payload.orders && typeof payload.orders === "object"
            ? payload.orders
            : {};
        const docs = orderDocuments(listview);
        docs.forEach((doc, name) => {
            const flag = flags[name] || {};
            doc.__almdinaProductionActionContext = {
                stage: flag.active_stage_name || doc.current_production_stage || "",
                canStart: flag.can_start_stage === true,
                canHandoff: flag.can_handoff_stage === true,
            };
        });
        // The first paint intentionally has no guessed action. Rebuild phone
        // cards only after the server-authorized action context arrives.
        renderMobileCards(listview);
        if (!personalView) {
            clearOperationalRoleRows(listview);
            return;
        }

        const assigned = [];
        const completed = [];
        [...result.querySelectorAll(".list-row-container")].forEach(container => {
            const name = rowDocumentName(container);
            if (!name) return;
            const flag = flags[name] || {};
            const isCompleted = flag.assignment_state === "completed";
            container.classList.remove("dco-list-row-other-role");
            container.classList.toggle("dco-list-row-completed", isCompleted);
            const card = container.querySelector(".dco-mobile-order-card");
            if (card) {
                card.classList.remove("dco-list-row-other-role");
                card.classList.toggle("dco-list-row-completed", isCompleted);
            }
            (isCompleted ? completed : assigned).push({ container, flag, name });
        });

        // Current assignments: oldest assignment first. Completed work follows:
        // newest finish first. Order creation time is deliberately irrelevant.
        assigned.sort((left, right) => compareServerTimes(
            left,
            right,
            "assignment_time",
            1
        ));
        completed.sort((left, right) => compareServerTimes(
            left,
            right,
            "completion_time",
            -1
        ));
        const ordered = [...assigned, ...completed].map(item => item.container);
        // Do not move nodes when they are already ordered: moving a node triggers
        // Frappe's mutation observer and used to start another request/reorder loop.
        const current = [...result.querySelectorAll(".list-row-container")]
            .filter(container => Boolean(rowDocumentName(container)));
        const needsReorder = ordered.some((container, index) => current[index] !== container);
        if (needsReorder) {
            listview._dcoApplyingRolePresentation = true;
            ordered.forEach(container => result.appendChild(container));
            requestAnimationFrame(() => {
                listview._dcoApplyingRolePresentation = false;
            });
        }
    }

    function applyOperationalRoleRows(listview) {
        if (!listview || !window.frappe || typeof frappe.call !== "function") return;
        const names = (listview.data || [])
            .map(doc => String(doc && doc.name || "").trim())
            .filter(Boolean);
        if (!names.length) {
            clearOperationalRoleRows(listview);
            return;
        }

        const requestId = Number(listview._dcoRoleFlagRequestId || 0) + 1;
        listview._dcoRoleFlagRequestId = requestId;
        frappe.call({
            method: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_order_operational_role_flags",
            args: { order_names: names },
            freeze: false,
        }).then(response => {
            if (listview._dcoRoleFlagRequestId !== requestId) return;
            applyOperationalRolePresentation(listview, response && response.message);
        }).catch(error => {
            if (listview._dcoRoleFlagRequestId !== requestId) return;
            console.debug("Could not classify Door Cutting Order list rows by operational role", error);
        });
    }

    function schedule(listview) {
        const root = rootNode(listview);
        if (root) root.classList.add("dco-order-list");
        (listview.data || []).forEach(doc => {
            if (doc) doc.__almdinaProductionActionContext = null;
        });
        installCombinedSearch(listview);
        installResponsiveObserver(listview);
        installRowsObserver(listview);
        applySearchHint(listview);
        renderMobileCards(listview);
        applyOperationalRoleRows(listview);
        requestAnimationFrame(() => {
            applySearchHint(listview);
            renderMobileCards(listview);
        });
        setTimeout(() => {
            renderMobileCards(listview);
        }, 100);
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
        isPhoneLayout,
        quickActionContext,
        renderMobileCards,
    });
})();
