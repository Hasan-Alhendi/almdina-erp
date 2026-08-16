(() => {
    "use strict";

    const ViewModel = window.AlmdinaShopFloorInboxViewModel;

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function statusLabel(status) {
        const labels = {
            Pending: __("بحاجة للعمل"),
            "In Progress": __("قيد العمل"),
            Paused: __("متوقف"),
            Completed: __("مكتمل"),
        };
        return labels[status] || __(status || "");
    }

    function createShell(wrapper) {
        const page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("صالة الإنتاج"),
            single_column: true,
        });
        const $section = $(wrapper).find(".layout-main-section");
        $section.html(`
            <div class="almdina-sf-tabs">
                <button type="button" class="almdina-sf-tab is-active" data-sf-mode="board">${__("لوحة الإنتاج")}</button>
                <button type="button" class="almdina-sf-tab" data-sf-mode="inbox">${__("قائمة الطلبات")}</button>
                <button type="button" class="almdina-sf-tab" data-sf-mode="account">${__("الحساب")}</button>
                <button type="button" class="btn btn-default almdina-sf-refresh">${__("تحديث")}</button>
            </div>
            <div class="almdina-sf-content"></div>
        `);
        try {
            page.clear_primary_action();
            page.clear_inner_toolbar();
        } catch (error) {
            // Older Frappe versions can safely keep the empty toolbar.
        }
        return Object.freeze({
            page,
            $section,
            $tabs: $section.find(".almdina-sf-tabs"),
            $content: $section.find(".almdina-sf-content"),
        });
    }

    function syncTabs(shell, mode) {
        shell.$tabs.find(".almdina-sf-tab").each(function () {
            $(this).toggleClass("is-active", $(this).attr("data-sf-mode") === mode);
        });
        shell.$tabs.find(".almdina-sf-refresh").toggle(mode !== "account");
    }

    function loading(shell, message) {
        shell.$content.html(`<div class="almdina-sf-shell"><div class="text-muted">${esc(message)}</div></div>`);
    }

    function renderError(shell, message) {
        shell.$content.html(`
            <div class="almdina-sf-shell">
                <div class="almdina-sf-empty">${esc(message || __("تعذر تحميل البيانات."))}</div>
            </div>
        `);
    }

    function quickActionHtml(row, mode) {
        const controller = window.AlmdinaShopFloorQuickActions;
        const action = controller && controller.actionFor(ViewModel.quickActionContext(row, mode));
        if (!action) return "";
        const buttonClass = action.indicator === "success" ? "btn-success" : "btn-primary";
        return `<button type="button" class="btn ${buttonClass} sf-quick-action" style="flex:1;min-height:44px;font-weight:750;border-radius:10px">${esc(action.label)}</button>`;
    }

    function orderCardHtml(row, mode, { compact = false, terminal = false, completed = false } = {}) {
        const canDrag = compact && !terminal && row.can_handoff_stage === true;
        const cardClasses = `${compact ? " almdina-sf-kanban-card" : ""}${completed ? " is-completed" : ""}`;
        const stageLabel = completed && row.current_department
            ? row.current_department
            : (row.department_label || row.stage_type);
        const statusText = terminal
            ? __("جاهز للتسليم")
            : (completed && row.current_stage_type
                ? statusLabel(row.status === "Completed" ? "Completed" : row.status)
                : statusLabel(row.status));
        return `
            <div class="frappe-card almdina-sf-order-card shop-floor-order-card${cardClasses}"
                data-order="${esc(row.door_cutting_order)}"
                data-stage="${esc(row.name)}"
                data-status="${esc(row.status)}"
                data-stage-type="${esc(row.stage_type)}"
                data-next="${esc(row.can_handoff_to || "")}"
                data-can-start="${row.can_start_stage === true ? "1" : "0"}"
                data-can-handoff="${row.can_handoff_stage === true ? "1" : "0"}"
                data-terminal="${terminal ? "1" : "0"}"
                data-completed="${completed ? "1" : "0"}"
                draggable="${canDrag ? "true" : "false"}">
                <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">
                    <div style="min-width:0;flex:1">
                        <div style="font-size:${compact ? ".96" : "1.05"}rem;font-weight:800">${esc(row.door_cutting_order)}</div>
                        <div class="text-muted" style="font-size:12px;margin:4px 0">${esc(row.customer || "")} ${row.order_date ? `· ${esc(row.order_date)}` : ""}</div>
                        ${compact ? "" : `<div style="font-size:13px">${__("القسم")}: <b>${esc(stageLabel)}</b></div>`}
                        <div style="font-size:12px">${__("الحالة")}: <b>${esc(statusText)}</b></div>
                        ${row.assigned_to ? `<div class="text-muted" style="font-size:11px;margin-top:3px">${__("العامل")}: ${esc(row.assigned_to)}</div>` : ""}
                    </div>
                    <span class="indicator-pill ${terminal || completed ? "green" : "blue"}">${esc(terminal ? __("جاهز") : statusLabel(row.status))}</span>
                </div>
                <div class="almdina-sf-card-meta" style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px">
                    <div style="background:var(--subtle-fg,#f7f8fa);padding:9px 10px;border-radius:10px;min-width:0">
                        <span class="text-muted" style="display:block;font-size:11px">${__("لون القشاط")}</span>
                        <b style="display:block;font-size:12px;overflow-wrap:anywhere">${esc(row.edge_color || "—")}</b>
                    </div>
                    <div style="background:var(--subtle-fg,#f7f8fa);padding:9px 10px;border-radius:10px;min-width:0">
                        <span class="text-muted" style="display:block;font-size:11px">${__("اللوح")}</span>
                        <b style="display:block;font-size:12px;overflow-wrap:anywhere">${esc(row.board_description || "—")}</b>
                    </div>
                </div>
                <div class="almdina-sf-card-actions" style="display:flex;gap:8px;margin-top:12px">
                    ${terminal || completed ? "" : quickActionHtml(row, mode)}
                    <button type="button" class="btn btn-default sf-open-btn" style="flex:1">${__("فتح الطلب")}</button>
                </div>
                ${canDrag ? `<div class="almdina-sf-drag-hint">${__("اسحب للمرحلة التالية")}</div>` : ""}
            </div>`;
    }

    function boardMetric(label, value, tone) {
        return `<div class="almdina-sf-board-metric" data-tone="${esc(tone)}"><span>${esc(label)}</span><b>${value}</b></div>`;
    }

    function kanbanColumn(route, stage, rows, mode, { ready = false } = {}) {
        const stageType = ready ? "__ready__" : stage.stage_type;
        const label = ready ? __("جاهز للتسليم") : (stage.department || stage.stage_type);
        const cards = rows.length
            ? rows.map(row => orderCardHtml(row, mode, { compact: true, terminal: ready })).join("")
            : `<div class="almdina-sf-kanban-empty">${__("لا توجد طلبات")}</div>`;
        return `
            <section class="almdina-sf-kanban-column${ready ? " is-ready" : ""}"
                data-route="${esc(route.name)}" data-drop-stage="${esc(stageType)}">
                <header class="almdina-sf-kanban-column-header">
                    <div><b>${esc(label)}</b>${stage && stage.is_planning_stage ? `<span>${__("تخطيط")}</span>` : ""}</div>
                    <span class="almdina-sf-column-count">${rows.length}</span>
                </header>
                <div class="almdina-sf-kanban-cards">${cards}</div>
            </section>`;
    }

    function routeBoardHtml(model, mode) {
        const { route, routeRows, readyRows } = model;
        const columns = route.stages.map(stage => kanbanColumn(
            route,
            stage,
            routeRows.filter(row => row.stage_type === stage.stage_type),
            mode
        ));
        columns.push(kanbanColumn(route, null, readyRows, mode, { ready: true }));
        return `
            <section class="almdina-sf-route-board" data-board-route="${esc(route.name)}">
                <div class="almdina-sf-route-heading">
                    <div><h3>${esc(route.label || __("مسار غير محدد"))}</h3><span>${routeRows.length + readyRows.length} ${__("طلب")}</span></div>
                    <small>${__("يتم الانتقال فقط حسب ترتيب المسار وصلاحيات المستخدم.")}</small>
                </div>
                <div class="almdina-sf-kanban">${columns.join("")}</div>
            </section>`;
    }

    function renderBoard(shell, model, search, mode = "board") {
        const routeOptions = model.routes.map(route => `<option value="${esc(route.name)}" ${model.routeFilter === route.name ? "selected" : ""}>${esc(route.label || __("مسار غير محدد"))}</option>`).join("");
        const boards = model.routeModels.length
            ? model.routeModels.map(item => routeBoardHtml(item, mode)).join("")
            : `<div class="almdina-sf-empty">${__("لا يوجد مسار إنتاج مفعّل. فعّل مسارًا من إعدادات الإنتاج أولًا.")}</div>`;
        shell.$content.html(`
            <div class="almdina-sf-shell almdina-sf-board-shell">
                <div class="almdina-sf-overview">
                    <div class="almdina-sf-board-toolbar">
                        <div>
                            <label for="almdina-sf-route-filter">${__("مسار الإنتاج")}</label>
                            <select id="almdina-sf-route-filter" class="form-control"><option value="">${__("كل المسارات")}</option>${routeOptions}</select>
                        </div>
                        <div>
                            <label for="almdina-sf-board-search">${__("بحث سريع")}</label>
                            <input id="almdina-sf-board-search" class="form-control" type="search" value="${esc(search)}" placeholder="${__("رقم الطلب، الزبون، العامل...")}">
                        </div>
                        <div class="almdina-sf-board-metrics">
                            ${boardMetric(__("بحاجة للعمل"), model.counts.pending, "pending")}
                            ${boardMetric(__("قيد العمل"), model.counts.progress, "progress")}
                            ${boardMetric(__("متوقف"), model.counts.paused, "paused")}
                            ${boardMetric(__("جاهز"), model.counts.ready, "ready")}
                        </div>
                    </div>
                    <div class="almdina-sf-board-help">${__("استخدم الزر داخل البطاقة، أو اسحب بطاقة قيد العمل إلى المرحلة التالية. سيطلب النظام تحديد العامل التالي ويعيد التحقق من الصلاحيات على الخادم.")}</div>
                    <div class="almdina-sf-boards">${boards}</div>
                </div>
            </div>`);
    }

    function listSection(title, rows, mode, { completed = false } = {}) {
        if (!rows.length) return "";
        const cards = rows.map(row => orderCardHtml(row, mode, { completed })).join("");
        return `
            <div class="almdina-sf-list-title${completed ? " is-completed" : ""}">${esc(title)}<span class="almdina-sf-list-count">${rows.length}</span></div>
            <div class="almdina-sf-list${completed ? " is-completed" : ""}">${cards}</div>`;
    }

    function renderList(shell, model, mode = "inbox") {
        let sections = "";
        const title = __("الطلبات المسندة");
        if (model.assigned.length || model.completed.length) {
            sections = model.assigned.length
                ? listSection(title, model.assigned, mode)
                : `<div class="almdina-sf-list-title">${esc(title)}</div><div class="almdina-sf-empty">${__("لا توجد طلبات مسندة حاليًا.")}</div>`;
            sections += listSection(__("الطلبات المنتهية"), model.completed, mode, { completed: true });
        }
        shell.$content.html(`
            <div class="almdina-sf-shell"><div class="almdina-sf-overview">
                ${sections || `<div class="almdina-sf-empty">${__("لا توجد طلبات في هذا القسم حاليًا.")}</div>`}
            </div></div>`);
    }

    const SECTION_LABELS = Object.freeze({
        orders: "الطلبات",
        costing: "التكلفة",
        planning: "خطة القص",
        drawing: "الرسم وDXF",
        production: "الإنتاج",
        administration: "الإدارة",
        reports: "التقارير",
    });

    function renderAccount(shell, model) {
        const enabledSections = model.enabledSections.map(name => SECTION_LABELS[name] ? __(SECTION_LABELS[name]) : name);
        shell.$content.html(`
            <div class="almdina-sf-shell">
                <div class="almdina-sf-account-card">
                    <h4 style="margin:0 0 12px">${__("معلومات الحساب")}</h4>
                    <div class="almdina-sf-account-row"><span class="text-muted">${__("الاسم")}</span><b>${esc(model.fullName)}</b></div>
                    <div class="almdina-sf-account-row"><span class="text-muted">${__("المستخدم")}</span><b dir="ltr">${esc(model.user)}</b></div>
                    <div class="almdina-sf-account-row"><span class="text-muted">${__("الأقسام المؤهل لها")}</span><b>${esc(model.departments.join(" · ") || "—")}</b></div>
                    <div class="almdina-sf-account-row"><span class="text-muted">${__("أقسام النظام المتاحة")}</span><b>${esc(enabledSections.join(" · ") || "—")}</b></div>
                    <button type="button" class="btn btn-danger almdina-sf-logout" style="width:100%;min-height:46px;margin-top:16px">${__("تسجيل الخروج")}</button>
                </div>
            </div>`);
    }

    function focusSearch(shell) {
        const input = shell.$content.find("#almdina-sf-board-search").get(0);
        if (!input) return;
        input.focus();
        if (typeof input.setSelectionRange === "function") input.setSelectionRange(input.value.length, input.value.length);
    }

    window.AlmdinaShopFloorInboxRenderer = Object.freeze({
        createShell,
        syncTabs,
        loading,
        error: renderError,
        renderBoard,
        renderList,
        renderAccount,
        focusSearch,
    });
})();
