(() => {
    "use strict";

    const METHODS = Object.freeze({
        doctype: "Door Cutting Order",
        roleFlags: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_order_operational_role_flags",
    });
    const MOBILE_CARD_STYLESHEET_ID = "almdina-dco-mobile-list-css";
    const MOBILE_CARD_STYLESHEET_HREF = "/assets/almdina_erp/css/door_cutting_order_mobile_list.css?v=5";
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
        Completed: "تم الإنجاز",
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
    const COMPLETED_ORDER_STATUSES = new Set([
        "Ready for Delivery",
        "Delivered",
        "Completed",
    ]);

    frappe.listview_settings = frappe.listview_settings || {};
    const existing = frappe.listview_settings[METHODS.doctype] || {};
    const originalOnload = existing.onload;
    const originalRefresh = existing.refresh;

    function rootNode(listview) {
        const wrapper = listview && listview.page && listview.page.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function ensureMobileCardStylesheet() {
        if (typeof document === "undefined" || !document.head) return;
        if (document.getElementById(MOBILE_CARD_STYLESHEET_ID)) return;
        const link = document.createElement("link");
        link.id = MOBILE_CARD_STYLESHEET_ID;
        link.rel = "stylesheet";
        link.href = MOBILE_CARD_STYLESHEET_HREF;
        document.head.appendChild(link);
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
        if (responsiveDevice && typeof responsiveDevice.usesCardLayout === "function") {
            return responsiveDevice.usesCardLayout(root);
        }
        if (responsiveDevice && typeof responsiveDevice.isPhoneLayout === "function") {
            return responsiveDevice.isPhoneLayout(root);
        }
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
        listview._dcoLastCardLayout = enabled;
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

    function quickActionContext(doc) {
        const authorized = doc.__almdinaProductionActionContext || {};
        return {
            order: doc.name,
            stage: authorized.stage || doc.current_production_stage,
            stageType: STAGE_BY_DEPARTMENT[doc.current_department] || doc.current_department,
            canStart: authorized.canStart === true,
            canHandoff: authorized.canHandoff === true,
            assignmentState: authorized.assignmentState || "",
            queueState: authorized.queueState || "",
        };
    }

    function mobileActionLabel(action) {
        if (!action) return "";
        if (action.kind === "start") return __("بدء العمل");
        if (action.kind === "handoff") return __("إنهاء العمل");
        return action.label || "";
    }

    function mobileActionClass(action) {
        if (!action) return "";
        return action.kind === "handoff" ? "is-finish" : "is-start";
    }

    function mobileActionConfirmation(action, doc) {
        const orderName = displayValue(doc && doc.name);
        if (action && action.kind === "handoff") {
            return `${__("هل تريد تأكيد إنهاء العمل على الطلب؟")} ${orderName}`;
        }
        return `${__("هل تريد بدء العمل على الطلب؟")} ${orderName}`;
    }

    function fallbackStatusLabel(doc) {
        return __(STATUS_LABELS[doc.status] || doc.status || "غير محدد");
    }

    function cardState(doc, context, action) {
        const completed = context.queueState === "completed"
            || context.assignmentState === "completed"
            || COMPLETED_ORDER_STATUSES.has(String(doc.status || ""));
        if (completed) {
            return Object.freeze({
                key: "completed",
                label: __("تم الإنجاز"),
                cardClass: "is-completed",
            });
        }

        const inProgress = context.queueState === "in_progress"
            || String(doc.department_status || "").trim() === "قيد العمل"
            || (action && action.kind === "handoff");
        if (inProgress) {
            return Object.freeze({
                key: "progress",
                label: __("قيد التنفيذ"),
                cardClass: "is-progress",
            });
        }

        const hasProductionContext = Boolean(
            context.queueState === "ready"
            || String(doc.current_production_stage || "").trim()
            || String(doc.current_department || "").trim()
            || String(doc.current_assignee || "").trim()
            || context.assignmentState === "assigned"
            || (action && action.kind === "start")
        );
        if (hasProductionContext) {
            return Object.freeze({
                key: "ready",
                label: __("جاهز للبدء"),
                cardClass: "is-ready",
            });
        }

        return Object.freeze({
            key: "neutral",
            label: fallbackStatusLabel(doc),
            cardClass: "is-neutral",
        });
    }

    function cardViewModel(doc) {
        const context = quickActionContext(doc);
        const quickActions = window.AlmdinaShopFloorQuickActions;
        const action = quickActions && quickActions.actionFor(context);
        const state = cardState(doc, context, action);
        return Object.freeze({
            orderId: displayValue(doc.name),
            customer: displayValue(doc.customer),
            boardColor: displayValue(doc.board_description),
            edgeColor: displayValue(doc.edge_color),
            edgeType: displayValue(doc.default_edge_type),
            date: dateLabel(doc.order_date),
            context,
            action,
            state,
            completed: state.key === "completed",
        });
    }

    function iconSvg(name, className = "") {
        const paths = {
            user: '<path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"/><path d="M4.5 20a7.5 7.5 0 0 1 15 0"/>',
            board: '<path d="M5 5.5h14v13H5z"/><path d="M8 8.5h8M8 12h8M8 15.5h5"/>',
            droplet: '<path d="M12 3s-5 5.2-5 10a5 5 0 0 0 10 0c0-4.8-5-10-5-10Z"/>',
            layers: '<path d="m12 3 8 4-8 4-8-4 8-4Z"/><path d="m4 12 8 4 8-4M4 17l8 4 8-4"/>',
            calendar: '<path d="M5 5h14v15H5z"/><path d="M8 3v4M16 3v4M5 9h14"/>',
            play: '<path d="m10 8 6 4-6 4V8Z"/>',
            check: '<path d="m7.5 12.5 3 3 6-7"/>',
            chevron: '<path d="m10 7 5 5-5 5"/>',
        };
        const body = paths[name] || "";
        return `<svg class="dco-card-icon ${escapeHtml(className)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
    }

    function renderStatusPill(state) {
        return `
            <span class="dco-card-state-pill" role="status">
                <span class="dco-card-state-dot" aria-hidden="true"></span>
                <span>${escapeHtml(state.label)}</span>
            </span>
        `;
    }

    function renderCustomer(model) {
        return `
            <div class="dco-card-customer-block">
                <span class="dco-card-customer-avatar" aria-hidden="true">${iconSvg("user")}</span>
                <div class="dco-card-customer-copy">
                    <span class="dco-card-eyebrow">${escapeHtml(__("اسم العميل"))}</span>
                    <strong class="dco-card-customer-name">${escapeHtml(model.customer)}</strong>
                </div>
            </div>
        `;
    }

    function renderOrderLink(model) {
        return `
            <div class="dco-card-order-row">
                <span class="dco-card-order-label">${escapeHtml(__("ID الطلب"))}</span>
                <button
                    type="button"
                    class="dco-card-order-link"
                    aria-label="${escapeHtml(__("فتح الطلب"))} ${escapeHtml(model.orderId)}"
                    title="${escapeHtml(__("فتح الطلب"))}"
                >
                    <span>${escapeHtml(model.orderId)}</span>
                    ${iconSvg("chevron", "dco-card-order-chevron")}
                </button>
            </div>
        `;
    }

    function renderInfoTile(label, value, iconName, className) {
        return `
            <div class="dco-card-info-tile ${escapeHtml(className || "")}">
                <span class="dco-card-info-icon" aria-hidden="true">${iconSvg(iconName)}</span>
                <div class="dco-card-info-copy">
                    <span>${escapeHtml(__(label))}</span>
                    <strong>${escapeHtml(value)}</strong>
                </div>
            </div>
        `;
    }

    function renderDate(model) {
        return `
            <div class="dco-card-date-row">
                ${iconSvg("calendar", "dco-card-date-icon")}
                <strong>${escapeHtml(model.date)}</strong>
            </div>
        `;
    }

    function renderAction(model) {
        if (model.action) {
            const icon = model.action.kind === "handoff" ? "check" : "play";
            return `
                <footer class="dco-card-actions">
                    <button
                        type="button"
                        class="btn dco-card-production-action ${mobileActionClass(model.action)}"
                        data-action-kind="${escapeHtml(model.action.kind)}"
                    >
                        <span>${escapeHtml(mobileActionLabel(model.action))}</span>
                        <span class="dco-card-action-icon" aria-hidden="true">${iconSvg(icon)}</span>
                    </button>
                </footer>
            `;
        }
        if (model.completed) {
            return `
                <div class="dco-card-complete-state" role="status">
                    <span>${escapeHtml(__("تم الإنجاز"))}</span>
                    <span class="dco-card-complete-icon" aria-hidden="true">${iconSvg("check")}</span>
                </div>
            `;
        }
        return "";
    }

    function buildCard(doc, hasSelection, preparedModel = null) {
        const model = preparedModel || cardViewModel(doc);
        const completedClass = model.completed ? " dco-list-row-completed" : "";
        return `
            <article
                class="dco-mobile-order-card ${model.state.cardClass}${completedClass}"
                data-order-name="${escapeHtml(doc.name)}"
                data-card-state="${escapeHtml(model.state.key)}"
                data-selectable="${hasSelection ? "1" : "0"}"
                dir="rtl"
            >
                <header class="dco-card-header">
                    ${renderCustomer(model)}
                    ${renderStatusPill(model.state)}
                </header>
                ${renderOrderLink(model)}
                <section class="dco-card-info-grid" aria-label="${escapeHtml(__("بيانات الطلب"))}">
                    ${renderInfoTile("لون اللوح", model.boardColor, "board", "is-board")}
                    ${renderInfoTile("لون القشاط", model.edgeColor, "droplet", "is-edge-color")}
                    ${renderInfoTile("نوع القشاط", model.edgeType, "layers", "is-edge-type")}
                </section>
                ${renderDate(model)}
                ${renderAction(model)}
            </article>
        `;
    }

    function cardRenderSignature(doc, hasSelection, model) {
        const action = model.action || {};
        return JSON.stringify([
            model.orderId,
            model.customer,
            model.boardColor,
            model.edgeColor,
            model.edgeType,
            model.date,
            model.state.key,
            model.state.label,
            action.kind || "",
            mobileActionLabel(model.action),
            model.context.stage || "",
            model.context.assignmentState || "",
            model.context.queueState || "",
            hasSelection ? 1 : 0,
            String(doc.department_status || ""),
        ]);
    }

    function bindCard(listview, container, card, doc) {
        const open = event => {
            event.preventDefault();
            event.stopPropagation();
            frappe.set_route("Form", METHODS.doctype, doc.name);
        };
        const orderLink = card.querySelector(".dco-card-order-link");
        if (orderLink) orderLink.addEventListener("click", open);

        const actionButton = card.querySelector(".dco-card-production-action");
        const quickActions = window.AlmdinaShopFloorQuickActions;
        if (actionButton && quickActions) {
            actionButton.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                const context = quickActionContext(doc);
                const action = quickActions.actionFor(context);
                if (!action) return;
                frappe.confirm(
                    mobileActionConfirmation(action, doc),
                    () => quickActions.perform(context, {
                        button: actionButton,
                        onSuccess: () => listview.refresh(),
                        skipFinalConfirmation: action.kind === "handoff",
                    })
                );
            });
        }
        container.classList.add("dco-order-card-container");
    }

    function removeMobileCard(container) {
        container.classList.remove("dco-order-card-container");
        const card = [...container.children]
            .find(child => child.classList.contains("dco-mobile-order-card"));
        if (card) card.remove();
    }

    function renderMobileCards(listview) {
        const root = rootNode(listview);
        if (!root) return;

        const docs = orderDocuments(listview);
        const containers = [...root.querySelectorAll(".list-row-container")];
        if (!applyCardLayoutClass(listview)) {
            containers.forEach(removeMobileCard);
            return;
        }
        ensureMobileCardStylesheet();

        containers.forEach(container => {
            const name = rowDocumentName(container);
            const doc = name && docs.get(name);
            if (!doc) {
                removeMobileCard(container);
                return;
            }

            const originalCheckbox = container.querySelector("input.list-row-checkbox, input[type='checkbox']");
            const hasSelection = Boolean(originalCheckbox);
            const model = cardViewModel(doc);
            const signature = cardRenderSignature(doc, hasSelection, model);
            const previous = [...container.children]
                .find(child => child.classList.contains("dco-mobile-order-card"));
            if (previous && previous.dataset.dcoRenderSignature === signature) {
                container.classList.add("dco-order-card-container");
                return;
            }
            if (previous) previous.remove();

            const holder = document.createElement("div");
            holder.innerHTML = buildCard(doc, hasSelection, model).trim();
            const card = holder.firstElementChild;
            if (!card) return;
            card.dataset.dcoRenderSignature = signature;
            container.appendChild(card);
            bindCard(listview, container, card, doc);
        });
    }

    function installResponsiveObserver(listview) {
        const root = rootNode(listview);
        if (!root || listview._dcoResponsiveObserverInstalled) return;

        listview._dcoLastCardLayout = isPhoneLayout(root);
        const refreshLayout = () => {
            const next = isPhoneLayout(root);
            if (next === listview._dcoLastCardLayout) return;
            listview._dcoLastCardLayout = next;
            renderMobileCards(listview);
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

    function personalQueueState(doc, flag = {}) {
        if (flag.assignment_state === "completed") return "completed";
        if (String(doc && doc.department_status || "").trim() === "قيد العمل") {
            return "in_progress";
        }
        return "ready";
    }

    function sortPersonalQueueItems(items) {
        const inProgress = [];
        const ready = [];
        const completed = [];

        items.forEach(item => {
            const state = personalQueueState(item.doc, item.flag);
            if (state === "completed") {
                completed.push(item);
            } else if (state === "in_progress") {
                inProgress.push(item);
            } else {
                ready.push(item);
            }
        });

        inProgress.sort((left, right) => compareServerTimes(
            left,
            right,
            "assignment_time",
            1
        ));
        ready.sort((left, right) => compareServerTimes(
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

        return [...inProgress, ...ready, ...completed];
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
                assignmentState: flag.assignment_state || "",
                queueState: personalQueueState(doc, flag),
            };
        });
        renderMobileCards(listview);
        if (!personalView) {
            clearOperationalRoleRows(listview);
            return;
        }

        const queueItems = [];
        [...result.querySelectorAll(".list-row-container")].forEach(container => {
            const name = rowDocumentName(container);
            if (!name) return;
            const flag = flags[name] || {};
            const doc = docs.get(name) || {};
            const isCompleted = personalQueueState(doc, flag) === "completed";
            container.classList.remove("dco-list-row-other-role");
            container.classList.toggle("dco-list-row-completed", isCompleted);
            const card = container.querySelector(".dco-mobile-order-card");
            if (card) {
                card.classList.remove("dco-list-row-other-role");
                card.classList.toggle("dco-list-row-completed", isCompleted);
            }
            queueItems.push({ container, flag, name, doc });
        });

        const ordered = sortPersonalQueueItems(queueItems).map(item => item.container);
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

    function roleFlagNames(listview) {
        return (listview.data || [])
            .map(doc => String(doc && doc.name || "").trim())
            .filter(Boolean);
    }

    function invalidateRoleFlags(listview) {
        listview._dcoRoleFlagGeneration = Number(listview._dcoRoleFlagGeneration || 0) + 1;
        listview._dcoRoleFlagsPayload = null;
        listview._dcoRoleFlagsPayloadGeneration = null;
        (listview.data || []).forEach(doc => {
            if (doc) doc.__almdinaProductionActionContext = null;
        });
    }

    function requestOperationalRoleFlags(listview) {
        if (!listview || !window.frappe || typeof frappe.call !== "function") return Promise.resolve(null);
        const names = roleFlagNames(listview);
        if (!names.length) {
            clearOperationalRoleRows(listview);
            return Promise.resolve(null);
        }

        const generation = Number(listview._dcoRoleFlagGeneration || 0);
        const key = `${generation}:${names.join("\u001f")}`;
        if (listview._dcoRoleFlagsPendingKey === key && listview._dcoRoleFlagsPendingPromise) {
            return listview._dcoRoleFlagsPendingPromise;
        }

        const request = frappe.call({
            method: METHODS.roleFlags,
            args: { order_names: names },
            freeze: false,
        }).then(response => {
            if (Number(listview._dcoRoleFlagGeneration || 0) !== generation) return null;
            const payload = response && response.message;
            listview._dcoRoleFlagsPayload = payload || { personal_view: false, orders: {} };
            listview._dcoRoleFlagsPayloadGeneration = generation;
            applyOperationalRolePresentation(listview, listview._dcoRoleFlagsPayload);
            return listview._dcoRoleFlagsPayload;
        }).catch(error => {
            if (Number(listview._dcoRoleFlagGeneration || 0) === generation) {
                console.debug("Could not classify Door Cutting Order list rows by operational role", error);
            }
            return null;
        }).finally(() => {
            if (listview._dcoRoleFlagsPendingKey === key) {
                listview._dcoRoleFlagsPendingKey = null;
                listview._dcoRoleFlagsPendingPromise = null;
            }
        });
        listview._dcoRoleFlagsPendingKey = key;
        listview._dcoRoleFlagsPendingPromise = request;
        return request;
    }

    function applyOperationalRoleRows(listview) {
        return requestOperationalRoleFlags(listview);
    }

    function runScheduledPresentation(listview) {
        listview._dcoPresentationFrame = null;
        const refreshRoleFlags = listview._dcoPresentationNeedsRoleRefresh === true;
        listview._dcoPresentationNeedsRoleRefresh = false;

        applySearchHint(listview);
        if (refreshRoleFlags) {
            invalidateRoleFlags(listview);
            renderMobileCards(listview);
            applyOperationalRoleRows(listview);
            return;
        }

        const generation = Number(listview._dcoRoleFlagGeneration || 0);
        if (
            listview._dcoRoleFlagsPayload
            && listview._dcoRoleFlagsPayloadGeneration === generation
        ) {
            applyOperationalRolePresentation(listview, listview._dcoRoleFlagsPayload);
            return;
        }
        renderMobileCards(listview);
    }

    function schedulePresentation(listview, { refreshRoleFlags = false } = {}) {
        if (!listview) return;
        if (refreshRoleFlags) listview._dcoPresentationNeedsRoleRefresh = true;
        if (listview._dcoPresentationFrame != null) return;
        const schedule = window.requestAnimationFrame || (callback => window.setTimeout(callback, 16));
        listview._dcoPresentationFrame = schedule(() => runScheduledPresentation(listview));
    }

    function installRowsObserver(listview) {
        if (listview._dcoRowsObserverInstalled || typeof MutationObserver !== "function") return;
        const root = rootNode(listview);
        const result = root && root.querySelector(".result");
        if (!result) return;

        const observer = new MutationObserver(mutations => {
            if (listview._dcoApplyingRolePresentation) return;
            const frappeRowsAdded = mutations.some(mutation =>
                [...mutation.addedNodes].some(node =>
                    node.nodeType === 1
                    && (node.matches(".list-row-container") || node.querySelector(".list-row-container"))
                )
            );
            if (frappeRowsAdded) schedulePresentation(listview);
        });
        observer.observe(result, { childList: true, subtree: true });
        listview._dcoRowsObserver = observer;
        listview._dcoRowsObserverInstalled = true;
    }

    function installListRuntime(listview) {
        const root = rootNode(listview);
        if (root) root.classList.add("dco-order-list");
        installCombinedSearch(listview);
        installResponsiveObserver(listview);
        installRowsObserver(listview);
    }

    frappe.listview_settings[METHODS.doctype] = Object.assign({}, existing, {
        add_fields: [...new Set([
            ...(existing.add_fields || []),
            "customer", "order_date", "status",
            "board_description", "edge_color", "default_edge_type", "production_path",
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
            installListRuntime(listview);
            schedulePresentation(listview);
        },
        refresh(listview) {
            if (typeof originalRefresh === "function") originalRefresh(listview);
            installListRuntime(listview);
            schedulePresentation(listview, { refreshRoleFlags: true });
        },
    });

    window.AlmdinaDoorCuttingOrderListUX = Object.freeze({
        buildCard,
        cardViewModel,
        isPhoneLayout,
        personalQueueState,
        quickActionContext,
        renderMobileCards,
        sortPersonalQueueItems,
    });
})();