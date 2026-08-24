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
        const page = wrapper.page;
        if (!page) throw new Error("Shop Floor Inbox page shell is unavailable");
        const $section = $(wrapper).find(".layout-main-section");
        $section.html(`
            <div class="almdina-sf-nav" aria-label="${__("التنقل في صالة الإنتاج")}">
                <div class="almdina-sf-tabs" role="tablist" aria-label="${__("أقسام صالة الإنتاج")}">
                    <button type="button" class="almdina-sf-tab is-active" role="tab" aria-selected="true" data-sf-mode="board">${__("لوحة الإنتاج")}</button>
                    <button type="button" class="almdina-sf-tab" role="tab" aria-selected="false" data-sf-mode="inbox">${__("قائمة الطلبات")}</button>
                    <button type="button" class="almdina-sf-tab" role="tab" aria-selected="false" data-sf-mode="account">${__("الحساب")}</button>
                    <button type="button" class="btn btn-default almdina-sf-refresh" aria-label="${__("تحديث بيانات صالة الإنتاج")}">
                        <span aria-hidden="true">↻</span><span>${__("تحديث")}</span>
                    </button>
                </div>
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
            const active = $(this).attr("data-sf-mode") === mode;
            $(this).toggleClass("is-active", active);
            $(this).attr("aria-selected", active ? "true" : "false");
        });
        shell.$tabs.find(".almdina-sf-refresh").toggle(mode !== "account");
    }

    function pageHero(kicker, title, description, stats = "") {
        return `
            <header class="almdina-sf-hero">
                <div class="almdina-sf-hero-copy">
                    <span class="almdina-sf-eyebrow">${esc(kicker)}</span>
                    <h2>${esc(title)}</h2>
                    <p>${esc(description)}</p>
                </div>
                ${stats ? `<div class="almdina-sf-hero-stats">${stats}</div>` : ""}
            </header>`;
    }

    function heroStat(label, value, tone = "neutral") {
        return `
            <div class="almdina-sf-hero-stat" data-tone="${esc(tone)}">
                <b>${esc(value)}</b><span>${esc(label)}</span>
            </div>`;
    }

    function emptyState(title, description, tone = "neutral") {
        return `
            <div class="almdina-sf-empty" data-tone="${esc(tone)}" role="status">
                <span class="almdina-sf-empty-icon" aria-hidden="true">${tone === "ready" ? "✓" : "◇"}</span>
                <div><b>${esc(title)}</b><p>${esc(description)}</p></div>
            </div>`;
    }

    function loading(shell, message) {
        shell.$content.html(`
            <div class="almdina-sf-shell">
                <div class="almdina-sf-state almdina-sf-loading" role="status" aria-live="polite">
                    <span class="almdina-sf-spinner" aria-hidden="true"></span>
                    <div><b>${__("جاري التحميل")}</b><span>${esc(message)}</span></div>
                </div>
            </div>`);
    }

    function renderError(shell, message) {
        shell.$content.html(`
            <div class="almdina-sf-shell">
                <div class="almdina-sf-state is-error" role="alert">
                    <span class="almdina-sf-state-icon" aria-hidden="true">!</span>
                    <div><b>${__("تعذر تحديث صالة الإنتاج")}</b><span>${esc(message || __("تعذر تحميل البيانات."))}</span></div>
                </div>
            </div>
        `);
    }

    function quickActionHtml(row, mode) {
        const controller = window.AlmdinaShopFloorQuickActions;
        const action = controller && controller.actionFor(ViewModel.quickActionContext(row, mode));
        if (!action) return "";
        const buttonClass = action.indicator === "success" ? "btn-success" : "btn-primary";
        return `<button type="button" class="btn ${buttonClass} sf-quick-action" aria-label="${esc(`${action.label} — ${row.door_cutting_order || ""}`)}">${esc(action.label)}</button>`;
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
        const customerLine = [row.customer || "", row.order_date || ""].filter(Boolean).join(" · ");
        return `
            <article class="frappe-card almdina-sf-order-card shop-floor-order-card${cardClasses}"
                data-order="${esc(row.door_cutting_order)}"
                data-stage="${esc(row.name)}"
                data-status="${esc(row.status)}"
                data-stage-type="${esc(row.stage_type)}"
                data-next="${esc(row.can_handoff_to || "")}"
                data-can-start="${row.can_start_stage === true ? "1" : "0"}"
                data-can-handoff="${row.can_handoff_stage === true ? "1" : "0"}"
                data-terminal="${terminal ? "1" : "0"}"
                data-completed="${completed ? "1" : "0"}"
                aria-label="${esc(`${__("طلب")} ${row.door_cutting_order || ""} — ${statusText}`)}"
                draggable="${canDrag ? "true" : "false"}">
                <div class="almdina-sf-card-head">
                    <div class="almdina-sf-card-identity">
                        <span class="almdina-sf-order-number">${esc(row.door_cutting_order)}</span>
                        <span class="almdina-sf-card-subtitle">${esc(customerLine || __("بدون بيانات زبون"))}</span>
                    </div>
                    <span class="indicator-pill ${terminal || completed ? "green" : "blue"}">${esc(terminal ? __("جاهز") : statusLabel(row.status))}</span>
                </div>
                <div class="almdina-sf-card-context">
                    ${compact ? "" : `<div><span>${__("القسم")}</span><b>${esc(stageLabel)}</b></div>`}
                    <div><span>${__("الحالة")}</span><b>${esc(statusText)}</b></div>
                    ${row.assigned_to ? `<div><span>${__("العامل")}</span><b dir="auto">${esc(row.assigned_to)}</b></div>` : ""}
                </div>
                <div class="almdina-sf-card-meta">
                    <div class="almdina-sf-meta-item">
                        <span>${__("لون القشاط")}</span>
                        <b>${esc(row.edge_color || "—")}</b>
                    </div>
                    <div class="almdina-sf-meta-item">
                        <span>${__("اللوح")}</span>
                        <b>${esc(row.board_description || "—")}</b>
                    </div>
                </div>
                <div class="almdina-sf-card-actions">
                    ${terminal || completed ? "" : quickActionHtml(row, mode)}
                    <button type="button" class="btn btn-default sf-open-btn" aria-label="${esc(`${__("فتح الطلب")} ${row.door_cutting_order || ""}`)}">${__("فتح الطلب")}</button>
                </div>
                ${canDrag ? `<div class="almdina-sf-drag-hint"><span aria-hidden="true">↔</span>${__("اسحب للمرحلة التالية")}</div>` : ""}
            </article>`;
    }

    function boardMetric(label, value, tone) {
        return `
            <div class="almdina-sf-board-metric" data-tone="${esc(tone)}" aria-label="${esc(`${label}: ${value}`)}">
                <span>${esc(label)}</span><b>${value}</b>
            </div>`;
    }

    function kanbanColumn(route, stage, rows, mode, { ready = false } = {}) {
        const stageType = ready ? "__ready__" : stage.stage_type;
        const label = ready ? __("جاهز للتسليم") : (stage.department || stage.stage_type);
        const cards = rows.length
            ? rows.map(row => orderCardHtml(row, mode, { compact: true, terminal: ready })).join("")
            : `<div class="almdina-sf-kanban-empty" role="status"><span aria-hidden="true">◇</span>${__("لا توجد طلبات")}</div>`;
        return `
            <section class="almdina-sf-kanban-column${ready ? " is-ready" : ""}"
                aria-label="${esc(`${label} — ${rows.length} ${__("طلب")}`)}"
                data-route="${esc(route.name)}" data-drop-stage="${esc(stageType)}">
                <header class="almdina-sf-kanban-column-header">
                    <div><b>${esc(label)}</b>${stage && stage.is_planning_stage ? `<span>${__("تخطيط")}</span>` : ""}</div>
                    <span class="almdina-sf-column-count" aria-label="${esc(`${rows.length} ${__("طلب")}`)}">${rows.length}</span>
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
            <section class="almdina-sf-route-board" data-board-route="${esc(route.name)}" aria-label="${esc(route.label || __("مسار غير محدد"))}">
                <div class="almdina-sf-route-heading">
                    <div class="almdina-sf-route-title">
                        <span class="almdina-sf-route-icon" aria-hidden="true">⇢</span>
                        <div><h3>${esc(route.label || __("مسار غير محدد"))}</h3><span>${routeRows.length + readyRows.length} ${__("طلب")}</span></div>
                    </div>
                    <small>${__("الانتقال يتبع ترتيب المسار وصلاحيات المستخدم.")}</small>
                </div>
                <div class="almdina-sf-kanban" aria-label="${esc(`${__("مراحل")} ${route.label || __("مسار غير محدد")}`)}">${columns.join("")}</div>
            </section>`;
    }

    function renderBoard(shell, model, search, mode = "board") {
        const routeOptions = model.routes.map(route => `<option value="${esc(route.name)}" ${model.routeFilter === route.name ? "selected" : ""}>${esc(route.label || __("مسار غير محدد"))}</option>`).join("");
        const boards = model.routeModels.length
            ? model.routeModels.map(item => routeBoardHtml(item, mode)).join("")
            : emptyState(__("لا يوجد مسار إنتاج مفعّل"), __("فعّل مسارًا من إعدادات الإنتاج ليظهر هنا."));
        const activeCount = model.counts.pending + model.counts.progress + model.counts.paused;
        shell.$content.html(`
            <div class="almdina-sf-shell almdina-sf-board-shell">
                ${pageHero(
                    __("صالة الإنتاج"),
                    __("متابعة مراحل الإنتاج"),
                    __("شاهد الطلبات حسب مسارها، ونفّذ الإجراء المتاح دون مغادرة اللوحة."),
                    [
                        heroStat(__("قيد المتابعة"), activeCount, "active"),
                        heroStat(__("جاهز للتسليم"), model.counts.ready, "ready"),
                        heroStat(__("المسارات"), model.routes.length, "neutral"),
                    ].join("")
                )}
                <div class="almdina-sf-overview">
                    <div class="almdina-sf-board-toolbar" aria-label="${__("تصفية لوحة الإنتاج")}">
                        <div class="almdina-sf-filter-field">
                            <label for="almdina-sf-route-filter">${__("مسار الإنتاج")}</label>
                            <select id="almdina-sf-route-filter" class="form-control"><option value="">${__("كل المسارات")}</option>${routeOptions}</select>
                        </div>
                        <div class="almdina-sf-filter-field almdina-sf-search-field">
                            <label for="almdina-sf-board-search">${__("بحث سريع")}</label>
                            <input id="almdina-sf-board-search" class="form-control" type="search" value="${esc(search)}" placeholder="${__("رقم الطلب، الزبون، العامل...")}" autocomplete="off">
                        </div>
                        <div class="almdina-sf-board-metrics" aria-label="${__("ملخص حالات الطلبات")}">
                            ${boardMetric(__("بحاجة للعمل"), model.counts.pending, "pending")}
                            ${boardMetric(__("قيد العمل"), model.counts.progress, "progress")}
                            ${boardMetric(__("متوقف"), model.counts.paused, "paused")}
                            ${boardMetric(__("جاهز"), model.counts.ready, "ready")}
                        </div>
                    </div>
                    <div class="almdina-sf-board-help" role="note"><span aria-hidden="true">i</span><p>${__("استخدم زر الإجراء داخل البطاقة. على الكمبيوتر يمكنك أيضًا سحب بطاقة قيد العمل إلى المرحلة التالية؛ الخادم يعيد التحقق من الصلاحيات قبل التنفيذ.")}</p></div>
                    <div class="almdina-sf-boards">${boards}</div>
                </div>
            </div>`);
    }

    function listSection(title, rows, mode, { completed = false } = {}) {
        if (!rows.length) return "";
        const cards = rows.map(row => orderCardHtml(row, mode, { completed })).join("");
        return `
            <section class="almdina-sf-list-section${completed ? " is-completed" : ""}">
                <div class="almdina-sf-list-title${completed ? " is-completed" : ""}">
                    <div><span class="almdina-sf-list-dot" aria-hidden="true"></span>${esc(title)}</div>
                    <span class="almdina-sf-list-count">${rows.length}</span>
                </div>
                <div class="almdina-sf-list${completed ? " is-completed" : ""}">${cards}</div>
            </section>`;
    }

    function renderList(shell, model, mode = "inbox") {
        let sections = "";
        const title = __("الطلبات المسندة");
        if (model.assigned.length || model.completed.length) {
            sections = model.assigned.length
                ? listSection(title, model.assigned, mode)
                : `<section class="almdina-sf-list-section"><div class="almdina-sf-list-title"><div><span class="almdina-sf-list-dot" aria-hidden="true"></span>${esc(title)}</div></div>${emptyState(__("لا توجد طلبات مسندة"), __("ستظهر هنا الطلبات التي أصبحت ضمن دورك التشغيلي."))}</section>`;
            sections += listSection(__("الطلبات المنتهية"), model.completed, mode, { completed: true });
        }
        shell.$content.html(`
            <div class="almdina-sf-shell">
                ${pageHero(
                    __("قائمة العمل"),
                    __("طلباتك التشغيلية"),
                    __("ابدأ بالطلبات المسندة، ثم راجع ما أنهيته في القسم السفلي."),
                    [
                        heroStat(__("مسندة"), model.assigned.length, "active"),
                        heroStat(__("منتهية"), model.completed.length, "ready"),
                    ].join("")
                )}
                <div class="almdina-sf-overview">
                    ${sections || emptyState(__("لا توجد طلبات حاليًا"), __("لا يوجد عمل مسند أو سجل منتهٍ ضمن هذا القسم."))}
                </div>
            </div>`);
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
        const departmentText = model.departments.join(" · ") || "—";
        const sectionText = enabledSections.join(" · ") || "—";
        shell.$content.html(`
            <div class="almdina-sf-shell">
                ${pageHero(
                    __("الحساب"),
                    __("معلومات المستخدم"),
                    __("راجع هويتك التشغيلية والأقسام المتاحة لك في النظام."),
                    heroStat(__("الأقسام التشغيلية"), model.departments.length, "neutral")
                )}
                <div class="almdina-sf-account-card">
                    <div class="almdina-sf-account-heading">
                        <span class="almdina-sf-account-avatar" aria-hidden="true">${esc((model.fullName || model.user || "؟").trim().charAt(0) || "؟")}</span>
                        <div><h4>${esc(model.fullName)}</h4><span dir="ltr">${esc(model.user)}</span></div>
                    </div>
                    <div class="almdina-sf-account-details">
                        <div class="almdina-sf-account-row"><span>${__("الاسم")}</span><b>${esc(model.fullName)}</b></div>
                        <div class="almdina-sf-account-row"><span>${__("المستخدم")}</span><b dir="ltr">${esc(model.user)}</b></div>
                        <div class="almdina-sf-account-row"><span>${__("الأقسام المؤهل لها")}</span><b>${esc(departmentText)}</b></div>
                        <div class="almdina-sf-account-row"><span>${__("أقسام النظام المتاحة")}</span><b>${esc(sectionText)}</b></div>
                    </div>
                    <div class="almdina-sf-account-footer">
                        <span>${__("تسجيل الخروج ينهي جلسة العمل الحالية على هذا الجهاز.")}</span>
                        <button type="button" class="btn btn-danger almdina-sf-logout">${__("تسجيل الخروج")}</button>
                    </div>
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
