(() => {
    "use strict";

    const METHODS = Object.freeze({
        doctype: "Door Cutting Order",
        roleFlags: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_order_operational_role_flags",
    });
    const KANBAN_CARD_FIELDS = Object.freeze([
        "customer",
        "board_description",
        "edge_color",
    ]);
    const KANBAN_VIEW_PATCH_KEY = "__almdinaDcoCardPresentationInstalled";
    const MOBILE_CARD_STYLESHEET_ID = "almdina-dco-mobile-list-css";
    const MOBILE_CARD_STYLESHEET_HREF = "/assets/almdina_erp/css/door_cutting_order_mobile_list.css?v=8";
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
    const MOBILE_CARD_STATES = Object.freeze({
        in_progress: Object.freeze({
            label: "قيد التنفيذ",
            cardClass: "is-in-progress",
            icon: "activity",
            history: false,
        }),
        ready: Object.freeze({
            label: "جاهز للبدء",
            cardClass: "is-ready",
            icon: "play",
            history: false,
        }),
        ready_for_delivery: Object.freeze({
            label: "جاهز للتسليم",
            cardClass: "is-ready-for-delivery",
            icon: "package",
            history: false,
        }),
        completed: Object.freeze({
            label: "تم الإنجاز",
            cardClass: "is-completed",
            icon: "circle-check",
            history: true,
        }),
        delivered: Object.freeze({
            label: "تم التسليم",
            cardClass: "is-delivered",
            icon: "truck",
            history: true,
        }),
    });
    const MOBILE_ACTION_PRESENTATION = Object.freeze({
        start: Object.freeze({
            label: "بدء العمل",
            className: "is-start",
            icon: "play",
        }),
        handoff: Object.freeze({
            label: "إنهاء العمل",
            className: "is-finish",
            icon: "check",
        }),
        deliver: Object.freeze({
            label: "تم التسليم",
            className: "is-deliver",
            icon: "package-check",
        }),
    });
    const PERSONAL_QUEUE_SORT_RULES = Object.freeze({
        in_progress: Object.freeze({ rank: 0, field: "start_time", direction: -1 }),
        ready: Object.freeze({ rank: 1, field: "assignment_time", direction: 1 }),
        ready_for_delivery: Object.freeze({ rank: 2, field: "ready_for_delivery_time", direction: -1 }),
        completed: Object.freeze({ rank: 3, field: "completion_time", direction: -1 }),
        delivered: Object.freeze({ rank: 4, field: "modified", direction: -1 }),
    });
    const DESKTOP_QUEUE_SORT_RULES = Object.freeze({
        in_progress: Object.freeze({ rank: 0, field: "assignment_time", direction: 1 }),
        ready: Object.freeze({ rank: 1, field: "assignment_time", direction: 1 }),
        completed: Object.freeze({ rank: 2, field: "completion_time", direction: -1 }),
    });
    const DESKTOP_DELIVERY_ROW_CLASS = Object.freeze({
        ready_for_delivery: "dco-list-row-ready-for-delivery",
        delivered: "dco-list-row-delivered",
    });
    const DESKTOP_DELIVERY_ROW_CLASSES = Object.freeze([
        DESKTOP_DELIVERY_ROW_CLASS.ready_for_delivery,
        DESKTOP_DELIVERY_ROW_CLASS.delivered,
    ]);
    const STATUS_FILTER_SLOT_CLASS = "dco-status-filter-slot";
    const STATUS_FILTER_FIELDNAME = "current_department";
    const STATUS_FILTER_ALL_LABEL = "كل الأقسام";
    const DEPARTMENT_FILTER_VALUES = Object.freeze([
        ...Object.keys(STAGE_BY_DEPARTMENT),
        "جاهز للتسليم",
        "تم التسليم",
    ]);

    frappe.listview_settings = frappe.listview_settings || {};
    const existing = frappe.listview_settings[METHODS.doctype] || {};
    const originalOnload = existing.onload;
    const originalRefresh = existing.refresh;

    function kanbanCardFields(fields) {
        const configured = Array.isArray(fields) ? fields : [];
        return [...new Set([...KANBAN_CARD_FIELDS, ...configured]
            .map(field => typeof field === "string" ? field : field && field.fieldname)
            .map(fieldname => String(fieldname || "").trim())
            .filter(fieldname => fieldname && fieldname !== "name"))];
    }

    function kanbanNameField() {
        if (frappe.model && typeof frappe.model.get_std_field === "function") {
            const field = frappe.model.get_std_field("name");
            if (field) return field;
        }
        return {
            fieldname: "name",
            fieldtype: "Data",
            label: "ID",
            parent: METHODS.doctype,
        };
    }

    function applyKanbanCardPresentation(view) {
        if (!view || view.doctype !== METHODS.doctype) return view;

        view.card_meta = Object.assign({}, view.card_meta || {}, {
            title_field: kanbanNameField(),
        });
        if (view.board) {
            view.board.fields = kanbanCardFields(view.board.fields);
            view.board.show_labels = 1;
        }
        return view;
    }

    function installKanbanCardPresentation() {
        // Frappe v16 otherwise selects the first visible text field as the card
        // title. For DCO that is optional order_notes, which renders as `null`.
        // Keep the correction Kanban-scoped so Form/List document titles stay intact.
        const prototype = frappe.views
            && frappe.views.KanbanView
            && frappe.views.KanbanView.prototype;
        if (!prototype || prototype[KANBAN_VIEW_PATCH_KEY]) return;

        const originalSetupDefaults = prototype.setup_defaults;
        if (typeof originalSetupDefaults !== "function") return;

        prototype.setup_defaults = function dcoKanbanSetupDefaults(...args) {
            return Promise.resolve(originalSetupDefaults.apply(this, args)).then(result => {
                applyKanbanCardPresentation(this);
                return result;
            });
        };
        prototype[KANBAN_VIEW_PATCH_KEY] = true;
    }

    installKanbanCardPresentation();

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

    function isEmailLike(value) {
        return String(value || "").includes("@");
    }

    function assigneeLabel(userId) {
        const id = String(userId || "").trim();
        if (!id) return "";
        let name = "";
        if (frappe.user && typeof frappe.user.full_name === "function") {
            name = String(frappe.user.full_name(id) || "").trim();
        }
        if (!name && typeof frappe.user_info === "function") {
            const info = frappe.user_info(id) || {};
            name = String(info.fullname || info.full_name || "").trim();
        }
        if (!name || name === id || isEmailLike(name)) return "";
        return name;
    }

    function rememberAssigneeNames(rows) {
        const map = {};
        (rows || []).forEach((row) => {
            const id = String(row && row.name || "").trim();
            const fullname = String(row && row.full_name || "").trim();
            if (!id || !fullname || fullname === id || isEmailLike(fullname)) return;
            map[id] = { fullname, email: id };
        });
        if (!Object.keys(map).length) return;
        if (typeof frappe.update_user_info === "function") {
            frappe.update_user_info(map);
            return;
        }
        frappe.boot = frappe.boot || {};
        frappe.boot.user_info = Object.assign({}, frappe.boot.user_info || {}, map);
    }

    function resolveAssigneeNames(listview) {
        if (!listview || !frappe.db || typeof frappe.db.get_list !== "function") return;
        const missing = [...new Set(
            (listview.data || [])
                .map(doc => String(doc && doc.current_assignee || "").trim())
                .filter(Boolean)
        )].filter(id => !assigneeLabel(id));
        if (!missing.length) return;
        if (listview._dcoAssigneeNamesKey === missing.join("\u001f")) return;
        listview._dcoAssigneeNamesKey = missing.join("\u001f");
        frappe.db.get_list("User", {
            filters: { name: ["in", missing] },
            fields: ["name", "full_name"],
            limit: missing.length,
        }).then((rows) => {
            rememberAssigneeNames(rows);
            if (typeof listview.render_list === "function") listview.render_list();
        }).catch(() => {
            listview._dcoAssigneeNamesKey = null;
        });
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

    function isDepartmentFilter(filter, doctype) {
        return Array.isArray(filter)
            && filter.length >= 4
            && filter[0] === doctype
            && filter[1] === STATUS_FILTER_FIELDNAME;
    }

    function departmentColumnQueryFilter(value, doctype) {
        const selected = String(value || "").trim();
        if (selected === "جاهز للتسليم") return [doctype, "status", "=", "Ready for Delivery"];
        if (selected === "تم التسليم") return [doctype, "status", "=", "Delivered"];
        return [doctype, STATUS_FILTER_FIELDNAME, "=", selected];
    }

    function rewriteDepartmentColumnFilters(args, doctype) {
        if (!args) return args;
        args.filters = (args.filters || []).map(filter => (
            isDepartmentFilter(filter, doctype)
                ? departmentColumnQueryFilter(filter[3], doctype)
                : filter
        ));
        return args;
    }

    function installCombinedSearch(listview) {
        if (!listview || listview._dcoCombinedSearchInstalled || typeof listview.get_args !== "function") return;
        const originalGetArgs = listview.get_args.bind(listview);

        listview.get_args = function dcoCombinedSearchArgs() {
            const args = rewriteDepartmentColumnFilters(originalGetArgs(), this.doctype);
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

    function statusFilterOptions() {
        return [
            { value: "", label: __(STATUS_FILTER_ALL_LABEL) },
            ...DEPARTMENT_FILTER_VALUES,
        ];
    }

    function statusFilterConfig() {
        return {
            fieldtype: "Select",
            fieldname: STATUS_FILTER_FIELDNAME,
            label: __("Current Department"),
            options: statusFilterOptions(),
            condition: "=",
        };
    }

    function statusFilterField(listview) {
        return listview && listview.page && listview.page.fields_dict
            ? listview.page.fields_dict[STATUS_FILTER_FIELDNAME]
            : null;
    }

    function controlWrapper(field) {
        if (!field) return null;
        if (field.$wrapper) {
            if (field.$wrapper.nodeType) return field.$wrapper;
            if (field.$wrapper[0]) return field.$wrapper[0];
        }
        const wrapper = field.wrapper;
        if (!wrapper) return null;
        return wrapper.nodeType ? wrapper : wrapper[0];
    }

    function insertAfter(reference, node) {
        if (!reference || !node) return false;
        const parent = reference.parentNode;
        if (!parent) return false;
        if (reference.nextSibling) parent.insertBefore(node, reference.nextSibling);
        else parent.appendChild(node);
        return true;
    }

    function ensureStatusFilterSlot(root) {
        if (!root || typeof root.querySelector !== "function") return null;
        const existingSlot = root.querySelector(`.${STATUS_FILTER_SLOT_CLASS}`);
        if (existingSlot) return existingSlot;
        if (typeof document === "undefined" || typeof document.createElement !== "function") {
            return null;
        }

        const slot = document.createElement("div");
        slot.className = `${STATUS_FILTER_SLOT_CLASS} standard-filter-section flex`;
        const filterSection = root.querySelector(".filter-section");
        const filterSelector = filterSection && filterSection.querySelector(".filter-selector");
        if (insertAfter(filterSelector, slot)) return slot;
        if (filterSection) {
            filterSection.appendChild(slot);
            return slot;
        }
        const pageForm = root.querySelector(".page-form");
        if (pageForm) {
            pageForm.appendChild(slot);
            return slot;
        }
        return null;
    }

    function applyStatusFilterHint(listview) {
        const field = statusFilterField(listview);
        const wrapper = controlWrapper(field);
        if (!wrapper || typeof wrapper.querySelector !== "function") return;
        const select = wrapper.querySelector("select");
        if (!select) return;
        select.setAttribute("aria-label", __("Current Department"));
        select.setAttribute("title", __(STATUS_FILTER_ALL_LABEL));
    }

    function reconcileStatusFilterLayout(listview) {
        const root = rootNode(listview);
        const wrapper = controlWrapper(statusFilterField(listview));
        if (!root || !wrapper) return false;

        const target = ensureStatusFilterSlot(root);
        if (!target) return false;
        if (wrapper.parentNode !== target) target.appendChild(wrapper);
        applyStatusFilterHint(listview);
        return true;
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

    function columnFieldname(column) {
        return String(column && column.df && column.df.fieldname || "").trim();
    }

    function applyOrderNotesColumnOrder(listview) {
        const columns = listview && listview.columns;
        if (!Array.isArray(columns) || !columns.length) return false;
        const notesIdx = columns.findIndex(column => columnFieldname(column) === "order_notes");
        const edgeIdx = columns.findIndex(column => columnFieldname(column) === "edge_color");
        if (notesIdx < 0 || edgeIdx < 0 || notesIdx === edgeIdx + 1) return false;
        const [notes] = columns.splice(notesIdx, 1);
        const nextEdgeIdx = columns.findIndex(column => columnFieldname(column) === "edge_color");
        columns.splice(nextEdgeIdx + 1, 0, notes);
        return true;
    }

    function installOrderNotesColumnOrder(listview) {
        if (!listview || listview._dcoOrderNotesColumnInstalled) return;
        if (typeof listview.setup_columns !== "function") return;
        listview._dcoOrderNotesColumnInstalled = true;
        const originalSetup = listview.setup_columns.bind(listview);
        listview.setup_columns = function dcoSetupColumns() {
            originalSetup();
            applyOrderNotesColumnOrder(this);
        };
        if (applyOrderNotesColumnOrder(listview) && typeof listview.render_header === "function") {
            listview.render_header();
        }
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
            canDeliver: authorized.canDeliver === true,
            assignmentState: authorized.assignmentState || "",
            queueState: authorized.queueState || "",
            overview: authorized.overview === true,
        };
    }

    function actionPresentation(action) {
        if (!action) return null;
        return MOBILE_ACTION_PRESENTATION[action.kind] || null;
    }

    function mobileActionLabel(action) {
        const presentation = actionPresentation(action);
        return presentation ? __(presentation.label) : (action && action.label || "");
    }

    function mobileActionClass(action) {
        const presentation = actionPresentation(action);
        return presentation ? presentation.className : "";
    }

    function mobileActionIcon(action) {
        const presentation = actionPresentation(action);
        return presentation ? presentation.icon : "check";
    }

    function mobileActionConfirmation(action, doc) {
        const orderName = displayValue(doc && doc.name);
        if (action && action.kind === "deliver") {
            return `${__("هل تؤكد تسليم الطلب للعميل؟")} ${orderName}`;
        }
        if (action && action.kind === "handoff") {
            return `${__("هل تريد تأكيد إنهاء العمل على الطلب؟")} ${orderName}`;
        }
        return `${__("هل تريد بدء العمل على الطلب؟")} ${orderName}`;
    }

    function fallbackStatusLabel(doc) {
        return __(STATUS_LABELS[doc.status] || doc.status || "غير محدد");
    }

    function productionStageLabel(doc) {
        const status = String(doc && doc.status || "").trim();
        if (status === "Delivered" || status === "Ready for Delivery") {
            return "";
        }
        return String(doc && doc.current_department || "").trim();
    }

    function overviewStageLabel(doc) {
        const status = String(doc && doc.status || "").trim();
        if (status === "Delivered" || status === "Ready for Delivery") {
            return __(STATUS_LABELS[status] || status);
        }
        const department = productionStageLabel(doc);
        if (department) return department;
        return fallbackStatusLabel(doc);
    }

    function cardStateDefinition(key) {
        const definition = MOBILE_CARD_STATES[key];
        if (!definition) return null;
        return Object.freeze({
            key,
            label: __(definition.label),
            cardClass: definition.cardClass,
            icon: definition.icon,
            history: definition.history === true,
        });
    }

    function cardState(doc, context, action) {
        const status = String(doc.status || "").trim();
        if (status === "Delivered") return cardStateDefinition("delivered");
        if (status === "Ready for Delivery") return cardStateDefinition("ready_for_delivery");

        const completed = context.overview
            ? status === "Completed"
            : context.queueState === "completed"
                || context.assignmentState === "completed"
                || status === "Completed";
        if (completed) return cardStateDefinition("completed");

        const inProgress = context.queueState === "in_progress"
            || String(doc.department_status || "").trim() === "قيد العمل"
            || (action && action.kind === "handoff");
        if (inProgress) return cardStateDefinition("in_progress");

        const hasProductionContext = Boolean(
            context.queueState === "ready"
            || String(doc.current_production_stage || "").trim()
            || String(doc.current_department || "").trim()
            || String(doc.current_assignee || "").trim()
            || context.assignmentState === "assigned"
            || (action && action.kind === "start")
        );
        if (hasProductionContext) return cardStateDefinition("ready");

        return Object.freeze({
            key: "neutral",
            label: fallbackStatusLabel(doc),
            cardClass: "is-neutral",
            icon: "activity",
            history: false,
        });
    }

    function cardViewModel(doc) {
        const context = quickActionContext(doc);
        const quickActions = window.AlmdinaShopFloorQuickActions;
        const candidateAction = quickActions && quickActions.actionFor(context);
        const state = cardState(doc, context, candidateAction);
        const action = state.history ? null : candidateAction;
        const overview = context.overview === true;
        const productionStage = productionStageLabel(doc);
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
            history: state.history,
            overview,
            productionStageLabel: productionStage,
            stageLabel: overview ? overviewStageLabel(doc) : productionStage,
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
            activity: '<path d="M3 12h4l2.2-5 4.1 10 2.2-5H21"/>',
            check: '<path d="m7.5 12.5 3 3 6-7"/>',
            "circle-check": '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/>',
            package: '<path d="m12 3 8 4-8 4-8-4 8-4Z"/><path d="M4 7v10l8 4 8-4V7M12 11v10"/>',
            "package-check": '<path d="m12 3 8 4-8 4-8-4 8-4Z"/><path d="M4 7v10l8 4 8-4V7M12 11v4"/><path d="m9 16 2 2 4-4"/>',
            truck: '<path d="M3 6h11v10H3z"/><path d="M14 10h4l3 3v3h-7z"/><circle cx="7" cy="18" r="2"/><circle cx="18" cy="18" r="2"/>',
            chevron: '<path d="m10 7 5 5-5 5"/>',
        };
        const body = paths[name] || "";
        return `<svg class="dco-card-icon ${escapeHtml(className)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
    }

    function renderStatusPill(state) {
        return `
            <span class="dco-card-state-pill" role="status">
                <span class="dco-card-state-dot" aria-hidden="true"></span>
                <span class="dco-card-state-icon" aria-hidden="true">${iconSvg(state.icon)}</span>
                <span>${escapeHtml(state.label)}</span>
            </span>
        `;
    }

    function renderStageChip(model) {
        const label = String(model && model.productionStageLabel || "").trim();
        if (!label) return "";
        return `<span class="dco-card-stage">${escapeHtml(label)}</span>`;
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
            return `
                <footer class="dco-card-actions">
                    <button
                        type="button"
                        class="btn dco-card-production-action ${mobileActionClass(model.action)}"
                        data-action-kind="${escapeHtml(model.action.kind)}"
                    >
                        <span>${escapeHtml(mobileActionLabel(model.action))}</span>
                        <span class="dco-card-action-icon" aria-hidden="true">${iconSvg(mobileActionIcon(model.action))}</span>
                    </button>
                </footer>
            `;
        }
        if (model.overview) {
            return `
                <div class="dco-card-complete-state" role="status">
                    <span>${escapeHtml(model.stageLabel)}</span>
                    <span class="dco-card-complete-icon" aria-hidden="true">${iconSvg(model.state.icon)}</span>
                </div>
            `;
        }
        if (model.history) {
            return `
                <div class="dco-card-complete-state" role="status">
                    <span>${escapeHtml(model.state.label)}</span>
                    <span class="dco-card-complete-icon" aria-hidden="true">${iconSvg(model.state.icon)}</span>
                </div>
            `;
        }
        return "";
    }

    function buildCard(doc, hasSelection, preparedModel = null) {
        const model = preparedModel || cardViewModel(doc);
        return `
            <article
                class="dco-mobile-order-card ${model.state.cardClass}"
                data-order-name="${escapeHtml(doc.name)}"
                data-card-state="${escapeHtml(model.state.key)}"
                data-selectable="${hasSelection ? "1" : "0"}"
                dir="rtl"
            >
                <header class="dco-card-header">
                    ${renderCustomer(model)}
                    <div class="dco-card-header-meta">
                        ${renderStageChip(model)}
                        ${renderStatusPill(model.state)}
                    </div>
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
            model.state.icon,
            action.kind || "",
            mobileActionLabel(model.action),
            model.context.stage || "",
            model.context.assignmentState || "",
            model.context.queueState || "",
            model.overview ? 1 : 0,
            model.stageLabel || "",
            model.productionStageLabel || "",
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
            reconcileStatusFilterLayout(listview);
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
        root.querySelectorAll(
            ".dco-list-row-other-role,.dco-list-row-completed,.dco-list-row-ready-for-delivery,.dco-list-row-delivered"
        ).forEach(node => {
            node.classList.remove("dco-list-row-other-role");
            node.classList.remove("dco-list-row-completed");
            DESKTOP_DELIVERY_ROW_CLASSES.forEach(className => node.classList.remove(className));
        });
    }

    function desktopDeliveryRowState(doc) {
        const status = String(doc && doc.status || "").trim();
        if (status === "Delivered") return "delivered";
        if (status === "Ready for Delivery") return "ready_for_delivery";
        const department = String(doc && doc.current_department || "").trim();
        if (department === "تم التسليم") return "delivered";
        if (department === "جاهز للتسليم") return "ready_for_delivery";
        return "";
    }

    function applyDesktopDeliveryRowColors(listview) {
        const root = rootNode(listview);
        if (!root) return;

        const result = root.querySelector(".result") || root;
        const mobileLayout = root.classList.contains("dco-order-card-layout");
        const docs = orderDocuments(listview);
        [...result.querySelectorAll(".list-row-container")].forEach(container => {
            const name = rowDocumentName(container);
            const state = name && !mobileLayout
                ? desktopDeliveryRowState(docs.get(name) || {})
                : "";
            container.classList.toggle(
                DESKTOP_DELIVERY_ROW_CLASS.ready_for_delivery,
                state === "ready_for_delivery"
            );
            container.classList.toggle(
                DESKTOP_DELIVERY_ROW_CLASS.delivered,
                state === "delivered"
            );
            if (state) {
                container.classList.remove("dco-list-row-completed");
            }
            const card = container.querySelector(".dco-mobile-order-card");
            if (card) {
                DESKTOP_DELIVERY_ROW_CLASSES.forEach(className => card.classList.remove(className));
            }
        });
    }

    function queueTimeValue(item, fieldname) {
        if (fieldname === "modified") {
            return String(item.doc && item.doc.modified || item.flag && item.flag.completion_time || "");
        }
        return String(item.flag && item.flag[fieldname] || "");
    }

    function compareQueueTimes(left, right, rule) {
        const leftValue = queueTimeValue(left, rule.field);
        const rightValue = queueTimeValue(right, rule.field);
        if (!leftValue && !rightValue) return left.name.localeCompare(right.name);
        if (!leftValue) return 1;
        if (!rightValue) return -1;
        const compared = leftValue.localeCompare(rightValue);
        return compared ? compared * rule.direction : left.name.localeCompare(right.name);
    }

    function personalQueueState(doc, flag = {}) {
        const status = String(doc && doc.status || "").trim();
        if (status === "Delivered") return "delivered";
        if (status === "Ready for Delivery") return "ready_for_delivery";
        if (flag.assignment_state === "completed" || status === "Completed") return "completed";
        if (String(doc && doc.department_status || "").trim() === "قيد العمل") {
            return "in_progress";
        }
        return "ready";
    }

    function desktopQueueState(doc, flag = {}) {
        if (flag.assignment_state === "completed") return "completed";
        if (String(doc && doc.department_status || "").trim() === "قيد العمل") {
            return "in_progress";
        }
        return "ready";
    }

    function sortQueueItemsByRules(items, stateResolver, rules, fallbackState) {
        return [...items].sort((left, right) => {
            const leftState = stateResolver(left.doc, left.flag);
            const rightState = stateResolver(right.doc, right.flag);
            const leftRule = rules[leftState] || rules[fallbackState];
            const rightRule = rules[rightState] || rules[fallbackState];
            if (leftRule.rank !== rightRule.rank) return leftRule.rank - rightRule.rank;
            return compareQueueTimes(left, right, leftRule);
        });
    }

    function sortPersonalQueueItems(items) {
        return sortQueueItemsByRules(
            items,
            personalQueueState,
            PERSONAL_QUEUE_SORT_RULES,
            "ready"
        );
    }

    function sortDesktopQueueItems(items) {
        return sortQueueItemsByRules(
            items,
            desktopQueueState,
            DESKTOP_QUEUE_SORT_RULES,
            "ready"
        );
    }

    function isHistoryQueueState(state) {
        return state === "completed" || state === "delivered";
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
                canDeliver: flag.can_mark_delivered === true,
                assignmentState: flag.assignment_state || "",
                queueState: personalQueueState(doc, flag),
                overview: !personalView,
            };
        });
        renderMobileCards(listview);
        if (!personalView) {
            clearOperationalRoleRows(listview);
            applyDesktopDeliveryRowColors(listview);
            return;
        }

        const mobileLayout = root.classList.contains("dco-order-card-layout");
        const queueItems = [];
        [...result.querySelectorAll(".list-row-container")].forEach(container => {
            const name = rowDocumentName(container);
            if (!name) return;
            const flag = flags[name] || {};
            const doc = docs.get(name) || {};
            const queueState = personalQueueState(doc, flag);
            const isHistory = mobileLayout
                ? isHistoryQueueState(queueState)
                : desktopQueueState(doc, flag) === "completed";
            container.classList.remove("dco-list-row-other-role");
            container.classList.toggle("dco-list-row-completed", isHistory);
            const card = container.querySelector(".dco-mobile-order-card");
            if (card) {
                card.classList.remove("dco-list-row-other-role");
                card.classList.remove("dco-list-row-completed");
            }
            queueItems.push({ container, flag, name, doc });
        });
        applyDesktopDeliveryRowColors(listview);

        const orderedItems = mobileLayout
            ? sortPersonalQueueItems(queueItems)
            : sortDesktopQueueItems(queueItems);
        const ordered = orderedItems.map(item => item.container);
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
                applyDesktopDeliveryRowColors(listview);
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
        applyStatusFilterHint(listview);
        resolveAssigneeNames(listview);
        if (refreshRoleFlags) {
            invalidateRoleFlags(listview);
            renderMobileCards(listview);
            applyDesktopDeliveryRowColors(listview);
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
        applyDesktopDeliveryRowColors(listview);
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
        applyCardLayoutClass(listview);
        installOrderNotesColumnOrder(listview);
        installCombinedSearch(listview);
        installResponsiveObserver(listview);
        installRowsObserver(listview);
        reconcileStatusFilterLayout(listview);
    }

    frappe.listview_settings[METHODS.doctype] = Object.assign({}, existing, {
        add_fields: [...new Set([
            ...(existing.add_fields || []),
            "customer", "order_date", "status",
            "board_description", "edge_color", "default_edge_type", "production_path",
            "order_notes",
            "current_department", "current_assignee",
            "current_production_stage",
        ])],
        custom_filter_configs: [
            ...(Array.isArray(existing.custom_filter_configs) ? existing.custom_filter_configs : []),
            statusFilterConfig(),
        ],
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
            current_assignee(value) {
                const label = assigneeLabel(value);
                return label ? escapeHtml(label) : "";
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
        applyDesktopDeliveryRowColors,
        applyKanbanCardPresentation,
        buildCard,
        cardViewModel,
        desktopDeliveryRowState,
        isPhoneLayout,
        kanbanCardFields,
        overviewStageLabel,
        productionStageLabel,
        personalQueueState,
        quickActionContext,
        reconcileStatusFilterLayout,
        renderMobileCards,
        rewriteDepartmentColumnFilters,
        sortDesktopQueueItems,
        sortPersonalQueueItems,
        statusFilterConfig,
        statusFilterOptions,
    });
})();
