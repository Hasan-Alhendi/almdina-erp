frappe.pages["shop-floor-inbox"].on_page_load = function (wrapper) {
    "use strict";

    const METHODS = Object.freeze({
        context: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_shop_floor_context",
        inbox: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_my_inbox",
        archive: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_my_archive",
        detail: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_order_shop_floor_detail",
        start: "almdina_erp.almdina_erp.services.shop_floor_commands.start_my_stage",
        handoffContext: "almdina_erp.almdina_erp.services.shop_floor_commands.get_handoff_context",
        handoff: "almdina_erp.almdina_erp.services.shop_floor_commands.handoff_to_next",
        reassignmentWorkers: "almdina_erp.almdina_erp.services.production_worker_service.get_reassignment_workers",
        reassign: "almdina_erp.almdina_erp.services.shop_floor_commands.reassign_worker",
    });

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
            <button type="button" class="almdina-sf-tab" data-sf-mode="archive">${__("الطلبات المؤرشفة")}</button>
            <button type="button" class="almdina-sf-tab" data-sf-mode="account">${__("الحساب")}</button>
            <button type="button" class="btn btn-default almdina-sf-refresh">${__("تحديث")}</button>
        </div>
        <div class="almdina-sf-content"></div>
    `);

    const $tabs = $section.find(".almdina-sf-tabs");
    const $content = $section.find(".almdina-sf-content");
    let mode = "board";
    let selected = null;
    let sessionContext = null;
    let boardRows = [];
    let boardArchiveRows = [];
    let boardRouteFilter = "";
    let boardSearch = "";
    let listRequest = 0;
    let detailRequest = 0;

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

    function documentCan(detail, capability) {
        return Boolean(detail && detail.document_capabilities && detail.document_capabilities[capability] === true);
    }

    function loading(message) {
        $content.html(`<div class="almdina-sf-shell"><div class="text-muted">${esc(message)}</div></div>`);
    }

    function renderError(message) {
        $content.html(`
            <div class="almdina-sf-shell">
                <div class="almdina-sf-empty">${esc(message || __("تعذر تحميل البيانات."))}</div>
            </div>
        `);
    }

    function syncTabs() {
        $tabs.find(".almdina-sf-tab").each(function () {
            $(this).toggleClass("is-active", $(this).attr("data-sf-mode") === mode);
        });
        $tabs.find(".almdina-sf-refresh").toggle(mode !== "account");
    }

    function setMode(nextMode) {
        mode = String(nextMode || "board");
        selected = null;
        detailRequest += 1;
        syncTabs();
        if (mode === "account") {
            renderAccount();
            return;
        }
        loadList();
    }

    function loadSessionContext() {
        if (sessionContext) return Promise.resolve(sessionContext);
        return frappe.call({ method: METHODS.context }).then(response => {
            sessionContext = response.message || {};
            return sessionContext;
        });
    }

    // A worker's inbox is already scoped to their own stages, so it can also
    // show orders they previously touched that have moved to other roles. Those
    // sit after the actionable queue and are painted green. Supervisors keep the
    // active-only list.
    function showsPersonalHistory() {
        return Boolean(sessionContext && sessionContext.personal_inbox);
    }

    function isMyOperationalStage(row) {
        return Boolean(row && row.actor_holds_current_stage_role === true);
    }

    function mergePersonalList(activeRows, historyRows) {
        const mine = (activeRows || []).filter(isMyOperationalStage);
        const seen = new Set(mine.map(row => row && row.door_cutting_order).filter(Boolean));
        const other = [];
        (historyRows || []).forEach(row => {
            if (!row || !row.door_cutting_order || seen.has(row.door_cutting_order)) return;
            if (isMyOperationalStage(row)) return;
            seen.add(row.door_cutting_order);
            other.push(row);
        });
        return { mine, other };
    }

    function workerBoardRows(activeRows) {
        if (!showsPersonalHistory()) return activeRows || [];
        return (activeRows || []).filter(isMyOperationalStage);
    }

    function loadList() {
        const requestId = ++listRequest;
        const requestedMode = mode;
        selected = null;
        loading(__("جاري التحميل..."));
        const primaryMethod = requestedMode === "archive" ? METHODS.archive : METHODS.inbox;
        return loadSessionContext()
            .then(() => {
                if (requestId !== listRequest || requestedMode !== mode) return null;
                const withArchive = requestedMode === "board"
                    || (requestedMode === "inbox" && showsPersonalHistory());
                const requests = [frappe.call({ method: primaryMethod, freeze: false })];
                if (withArchive) {
                    requests.push(frappe.call({ method: METHODS.archive, freeze: false }));
                }
                return Promise.all(requests);
            })
            .then(responses => {
                if (!responses || requestId !== listRequest || requestedMode !== mode) return;
                const [response, archiveResponse] = responses;
                boardRows = response.message || [];
                boardArchiveRows = archiveResponse ? (archiveResponse.message || []) : [];
                renderList(boardRows);
            })
            .catch(error => {
                if (requestId !== listRequest || requestedMode !== mode) return;
                renderError(error && error.message ? error.message : __("تعذر تحميل طلبات الإنتاج."));
            });
    }

    function quickActionContext(row) {
        const activeMode = mode === "board" || mode === "inbox";
        return {
            order: row.door_cutting_order,
            stage: row.name,
            stageType: row.stage_type,
            canStart: activeMode && row.can_start_stage === true,
            canHandoff: activeMode && row.can_handoff_stage === true,
        };
    }

    function quickActionHtml(row) {
        const controller = window.AlmdinaShopFloorQuickActions;
        const action = controller && controller.actionFor(quickActionContext(row));
        if (!action) return "";
        const buttonClass = action.indicator === "success" ? "btn-success" : "btn-primary";
        return `<button type="button" class="btn ${buttonClass} sf-quick-action" style="flex:1;min-height:44px;font-weight:750;border-radius:10px">${esc(action.label)}</button>`;
    }

    function cardContext($card) {
        return {
            order: String($card.data("order") || ""),
            stage: String($card.data("stage") || ""),
            status: String($card.data("status") || ""),
            stageType: String($card.data("stage-type") || ""),
            next: String($card.data("next") || ""),
            canStart: String($card.attr("data-can-start") || "") === "1",
            canHandoff: String($card.attr("data-can-handoff") || "") === "1",
        };
    }

    function orderCardHtml(row, { compact = false, terminal = false, otherRole = false } = {}) {
        const canDrag = compact && !terminal && row.can_handoff_stage === true;
        const cardClasses = `${compact ? " almdina-sf-kanban-card" : ""}${otherRole ? " is-other-role" : ""}`;
        const stageLabel = otherRole && row.current_department
            ? row.current_department
            : (row.department_label || row.stage_type);
        const statusText = terminal
            ? __("جاهز للتسليم")
            : (otherRole && row.current_stage_type
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
                data-other-role="${otherRole ? "1" : "0"}"
                draggable="${canDrag ? "true" : "false"}">
                <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">
                    <div style="min-width:0;flex:1">
                        <div style="font-size:${compact ? ".96" : "1.05"}rem;font-weight:800">${esc(row.door_cutting_order)}</div>
                        <div class="text-muted" style="font-size:12px;margin:4px 0">${esc(row.customer || "")} ${row.order_date ? `· ${esc(row.order_date)}` : ""}</div>
                        ${compact ? "" : `<div style="font-size:13px">${__("القسم")}: <b>${esc(stageLabel)}</b></div>`}
                        <div style="font-size:12px">${__("الحالة")}: <b>${esc(statusText)}</b></div>
                        ${row.assigned_to ? `<div class="text-muted" style="font-size:11px;margin-top:3px">${__("العامل")}: ${esc(row.assigned_to)}</div>` : ""}
                    </div>
                    <span class="indicator-pill ${terminal || otherRole ? "green" : "blue"}">${esc(terminal ? __("جاهز") : statusLabel(row.status))}</span>
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
                    ${terminal || otherRole ? "" : quickActionHtml(row)}
                    <button type="button" class="btn btn-default sf-open-btn open-detail" style="flex:1">${__("التفاصيل")}</button>
                </div>
                ${canDrag ? `<div class="almdina-sf-drag-hint">${__("اسحب للمرحلة التالية")}</div>` : ""}
            </div>`;
    }

    function bindCardActions($scope) {
        $scope.find(".shop-floor-order-card").on("click", function (event) {
            if ($(event.target).closest(".sf-quick-action").length) return;
            openDetail(cardContext($(this)));
        });
        $scope.find(".sf-quick-action").on("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            const $card = $(this).closest(".shop-floor-order-card");
            if (!window.AlmdinaShopFloorQuickActions) return;
            window.AlmdinaShopFloorQuickActions.perform(cardContext($card), {
                button: this,
                onSuccess: loadList,
            });
        });
    }

    function matchesBoardSearch(row) {
        if (!boardSearch) return true;
        const haystack = [
            row.door_cutting_order,
            row.customer,
            row.board_description,
            row.edge_color,
            row.assigned_to,
            row.department_label,
        ].join(" ").toLocaleLowerCase();
        return haystack.includes(boardSearch);
    }

    function routeKey(row) {
        return String(row.production_path || "") || "__unconfigured__";
    }

    function boardRoutes(rows) {
        const configured = Array.isArray(sessionContext && sessionContext.production_routes)
            ? sessionContext.production_routes.map(route => ({
                name: String(route.name || ""),
                label: route.label || route.name,
                stages: Array.isArray(route.stages) ? route.stages.slice() : [],
            }))
            : [];
        const known = new Set(configured.map(route => route.name));
        const unknown = new Map();
        rows.forEach(row => {
            const path = String(row.production_path || "");
            if (known.has(path)) return;
            const key = path || "__unconfigured__";
            if (!unknown.has(key)) {
                unknown.set(key, {
                    name: key,
                    label: path || __("مسار غير محدد"),
                    stages: [],
                });
            }
            const route = unknown.get(key);
            if (!route.stages.some(stage => stage.stage_type === row.stage_type)) {
                route.stages.push({
                    sequence: Number(row.sequence || route.stages.length + 1),
                    stage_type: row.stage_type,
                    department: row.department_label || row.stage_type,
                    is_planning_stage: false,
                });
            }
        });
        unknown.forEach(route => route.stages.sort((left, right) => Number(left.sequence || 0) - Number(right.sequence || 0)));
        return configured.concat(Array.from(unknown.values()));
    }

    function terminalRows(route) {
        const last = route.stages[route.stages.length - 1];
        if (!last) return [];
        const seen = new Set();
        return boardArchiveRows.filter(row => {
            const matchesRoute = routeKey(row) === route.name;
            const ready = row.order_status === "Ready for Delivery";
            const isLastStage = row.stage_type === last.stage_type;
            const unique = !seen.has(row.door_cutting_order);
            if (matchesRoute && ready && isLastStage && unique) {
                seen.add(row.door_cutting_order);
                return matchesBoardSearch(row);
            }
            return false;
        });
    }

    function boardMetric(label, value, tone) {
        return `<div class="almdina-sf-board-metric" data-tone="${esc(tone)}"><span>${esc(label)}</span><b>${value}</b></div>`;
    }

    function kanbanColumn(route, stage, rows, { ready = false } = {}) {
        const stageType = ready ? "__ready__" : stage.stage_type;
        const label = ready ? __("جاهز للتسليم") : (stage.department || stage.stage_type);
        const cards = rows.length
            ? rows.map(row => orderCardHtml(row, { compact: true, terminal: ready })).join("")
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

    function routeBoardHtml(route, activeRows) {
        const routeRows = activeRows.filter(row => {
            return routeKey(row) === route.name;
        });
        const columns = route.stages.map(stage => kanbanColumn(
            route,
            stage,
            routeRows.filter(row => row.stage_type === stage.stage_type)
        ));
        columns.push(kanbanColumn(route, null, terminalRows(route), { ready: true }));
        return `
            <section class="almdina-sf-route-board" data-board-route="${esc(route.name)}">
                <div class="almdina-sf-route-heading">
                    <div><h3>${esc(route.label || route.name)}</h3><span>${routeRows.length + terminalRows(route).length} ${__("طلب")}</span></div>
                    <small>${__("يتم الانتقال فقط حسب ترتيب المسار وصلاحيات المستخدم.")}</small>
                </div>
                <div class="almdina-sf-kanban">${columns.join("")}</div>
            </section>`;
    }

    function renderBoard(rows) {
        const routes = boardRoutes(rows);
        if (boardRouteFilter && !routes.some(route => route.name === boardRouteFilter)) {
            boardRouteFilter = "";
        }
        const visibleRoutes = routes.filter(route => !boardRouteFilter || route.name === boardRouteFilter);
        const activeRows = rows.filter(row => matchesBoardSearch(row));
        const filteredRows = boardRouteFilter
            ? activeRows.filter(row => routeKey(row) === boardRouteFilter)
            : activeRows;
        const readyCount = visibleRoutes.reduce((total, route) => total + terminalRows(route).length, 0);
        const routeOptions = routes.map(route => `<option value="${esc(route.name)}" ${boardRouteFilter === route.name ? "selected" : ""}>${esc(route.label || route.name)}</option>`).join("");
        const boards = visibleRoutes.length
            ? visibleRoutes.map(route => routeBoardHtml(route, filteredRows)).join("")
            : `<div class="almdina-sf-empty">${__("لا يوجد مسار إنتاج مفعّل. فعّل مسارًا من إعدادات الإنتاج أولًا.")}</div>`;

        $content.html(`
            <div class="almdina-sf-shell almdina-sf-board-shell">
                <div class="almdina-sf-overview">
                    <div class="almdina-sf-board-toolbar">
                        <div>
                            <label for="almdina-sf-route-filter">${__("مسار الإنتاج")}</label>
                            <select id="almdina-sf-route-filter" class="form-control">
                                <option value="">${__("كل المسارات")}</option>${routeOptions}
                            </select>
                        </div>
                        <div>
                            <label for="almdina-sf-board-search">${__("بحث سريع")}</label>
                            <input id="almdina-sf-board-search" class="form-control" type="search" value="${esc(boardSearch)}" placeholder="${__("رقم الطلب، الزبون، العامل...")}">
                        </div>
                        <div class="almdina-sf-board-metrics">
                            ${boardMetric(__("بحاجة للعمل"), filteredRows.filter(row => row.status === "Pending").length, "pending")}
                            ${boardMetric(__("قيد العمل"), filteredRows.filter(row => row.status === "In Progress").length, "progress")}
                            ${boardMetric(__("متوقف"), filteredRows.filter(row => row.status === "Paused").length, "paused")}
                            ${boardMetric(__("جاهز"), readyCount, "ready")}
                        </div>
                    </div>
                    <div class="almdina-sf-board-help">${__("استخدم الزر داخل البطاقة، أو اسحب بطاقة قيد العمل إلى المرحلة التالية. سيطلب النظام تحديد العامل التالي ويعيد التحقق من الصلاحيات على الخادم.")}</div>
                    <div class="almdina-sf-boards">${boards}</div>
                </div>
                <div class="shop-floor-detail" style="display:none"></div>
            </div>`);

        const $overview = $content.find(".almdina-sf-overview");
        bindCardActions($overview);
        bindBoardDragAndDrop($overview);
        $overview.find("#almdina-sf-route-filter").on("change", function () {
            boardRouteFilter = String($(this).val() || "");
            renderBoard(workerBoardRows(boardRows));
        });
        $overview.find("#almdina-sf-board-search").on("input", function () {
            boardSearch = String($(this).val() || "").trim().toLocaleLowerCase();
            renderBoard(workerBoardRows(boardRows));
            const input = document.getElementById("almdina-sf-board-search");
            if (input) {
                input.focus();
                input.setSelectionRange(input.value.length, input.value.length);
            }
        });
    }

    function bindBoardDragAndDrop($scope) {
        let $dragged = null;
        $scope.find('.almdina-sf-kanban-card[draggable="true"]').on("dragstart", function (event) {
            $dragged = $(this);
            $dragged.addClass("is-dragging");
            const transfer = event.originalEvent && event.originalEvent.dataTransfer;
            if (transfer) {
                transfer.effectAllowed = "move";
                transfer.setData("text/plain", String($dragged.data("stage") || ""));
            }
        }).on("dragend", function () {
            $(this).removeClass("is-dragging");
            $scope.find(".almdina-sf-kanban-column").removeClass("is-drag-over");
            $dragged = null;
        });

        $scope.find(".almdina-sf-kanban-column").on("dragover", function (event) {
            if (!$dragged) return;
            const target = String($(this).attr("data-drop-stage") || "");
            const next = String($dragged.data("next") || "");
            if (target !== (next || "__ready__")) return;
            event.preventDefault();
            $(this).addClass("is-drag-over");
            const transfer = event.originalEvent && event.originalEvent.dataTransfer;
            if (transfer) transfer.dropEffect = "move";
        }).on("dragleave", function () {
            $(this).removeClass("is-drag-over");
        }).on("drop", function (event) {
            event.preventDefault();
            $(this).removeClass("is-drag-over");
            if (!$dragged) return;
            const target = String($(this).attr("data-drop-stage") || "");
            const context = cardContext($dragged);
            if (target !== (context.next || "__ready__")) return;
            handoffStage(context);
        });
    }

    function listSection(title, rows, { otherRole = false } = {}) {
        if (!rows.length) return "";
        const cards = rows.map(row => orderCardHtml(row, { otherRole })).join("");
        return `
            <div class="almdina-sf-list-title${otherRole ? " is-other-role" : ""}">${esc(title)}
                <span class="almdina-sf-list-count">${rows.length}</span>
            </div>
            <div class="almdina-sf-list${otherRole ? " is-other-role" : ""}">${cards}</div>`;
    }

    function renderList(rows) {
        if (mode === "board") {
            renderBoard(workerBoardRows(rows));
            return;
        }
        let sections = "";
        if (mode === "archive") {
            sections = listSection(__("الطلبات المؤرشفة"), rows, { otherRole: true });
        } else if (showsPersonalHistory()) {
            const { mine, other } = mergePersonalList(rows, boardArchiveRows);
            const title = __("قائمة الطلبات الحالية");
            if (mine.length || other.length) {
                sections = mine.length
                    ? listSection(title, mine)
                    : `<div class="almdina-sf-list-title">${esc(title)}</div>
                       <div class="almdina-sf-empty">${__("لا توجد طلبات في مرحلة ضمن أدوارك التشغيلية حاليًا.")}</div>`;
                sections += listSection(__("طلبات في مراحل أخرى"), other, { otherRole: true });
            }
        } else {
            sections = listSection(__("قائمة الطلبات الحالية"), rows);
        }
        $content.html(`
            <div class="almdina-sf-shell">
                <div class="almdina-sf-overview">
                    ${sections || `<div class="almdina-sf-empty">${__("لا توجد طلبات في هذا القسم حاليًا.")}</div>`}
                </div>
                <div class="shop-floor-detail" style="display:none"></div>
            </div>`);
        bindCardActions($content.find(".almdina-sf-overview"));
    }

    function renderAccount() {
        loading(__("جاري تحميل معلومات الحساب..."));
        loadSessionContext()
            .then(context => {
                if (mode !== "account") return;
                const identity = context.identity || {};
                const departments = Array.isArray(identity.departments) ? identity.departments : [];
                const sections = context.navigation && context.navigation.sections ? context.navigation.sections : {};
                const enabledSections = Object.keys(sections)
                    .filter(name => sections[name] === true)
                    .map(name => ({
                        orders: __("الطلبات"),
                        costing: __("التكلفة"),
                        planning: __("خطة القص"),
                        drawing: __("الرسم وDXF"),
                        production: __("الإنتاج"),
                        administration: __("الإدارة"),
                        reports: __("التقارير"),
                    })[name] || name);
                $content.html(`
                    <div class="almdina-sf-shell">
                        <div class="almdina-sf-account-card">
                            <h4 style="margin:0 0 12px">${__("معلومات الحساب")}</h4>
                            <div class="almdina-sf-account-row"><span class="text-muted">${__("الاسم")}</span><b>${esc(identity.full_name || identity.user || "")}</b></div>
                            <div class="almdina-sf-account-row"><span class="text-muted">${__("المستخدم")}</span><b dir="ltr">${esc(identity.user || "")}</b></div>
                            <div class="almdina-sf-account-row"><span class="text-muted">${__("الأقسام المؤهل لها")}</span><b>${esc(departments.join(" · ") || "—")}</b></div>
                            <div class="almdina-sf-account-row"><span class="text-muted">${__("أقسام النظام المتاحة")}</span><b>${esc(enabledSections.join(" · ") || "—")}</b></div>
                            <button type="button" class="btn btn-danger almdina-sf-logout" style="width:100%;min-height:46px;margin-top:16px">${__("تسجيل الخروج")}</button>
                        </div>
                    </div>
                `);
                $content.find(".almdina-sf-logout").on("click", confirmLogout);
            })
            .catch(error => renderError(error && error.message ? error.message : __("تعذر تحميل معلومات الحساب.")));
    }

    function confirmLogout() {
        frappe.confirm(__("تأكيد تسجيل الخروج؟"), () => {
            frappe.call({
                method: "logout",
                freeze: true,
                freeze_message: __("جاري تسجيل الخروج..."),
                always() {
                    window.location.href = "/login";
                },
            });
        });
    }

    function hasCustomPlan(detail) {
        if (!detail || !detail.custom_plan_json) return false;
        try {
            const plan = typeof detail.custom_plan_json === "object"
                ? detail.custom_plan_json
                : JSON.parse(detail.custom_plan_json);
            return Boolean(plan && Array.isArray(plan.sheets) && plan.sheets.length);
        } catch (error) {
            return false;
        }
    }

    function emptyPlanHtml(message) {
        return `<div class="almdina-sf-empty">${esc(message)}</div>`;
    }

    function buildPlanTabsHtml(detail) {
        const tabs = Array.isArray(detail.visible_plan_tabs) && detail.visible_plan_tabs.length
            ? detail.visible_plan_tabs
            : (
                documentCan(detail, "view_cutting_plan")
                    ? ["System", "Custom", "Approved"].filter(tab => {
                        if (tab === "System") return documentCan(detail, "view_system_cutting_plan");
                        if (tab === "Custom") return documentCan(detail, "view_uploaded_cutting_plan");
                        return documentCan(detail, "view_approved_cutting_plan");
                    })
                    : []
            );
        if (!tabs.length) return "";

        if (tabs.length === 1 && !detail.show_dual_tabs) {
            const only = tabs[0];
            const html = planHtmlForTab(detail, only);
            return html || emptyPlanHtml(__("لا توجد خطة قص للعرض."));
        }

        const preferred = detail.active_plan_source;
        const active = tabs.includes(preferred) ? preferred : tabs[0];
        const approvedSource = detail.approved_plan_source || "System";
        const badge = source => {
            if (source === "Approved" && detail.approved_plan) {
                return `<span class="indicator-pill green" style="margin-inline-start:6px">${__("معتمدة")}</span>`;
            }
            if (detail.approved_plan && approvedSource === source) {
                return `<span class="indicator-pill green" style="margin-inline-start:6px">${__("مصدر الاعتماد")}</span>`;
            }
            return "";
        };
        const labels = {
            System: __("خطة النظام"),
            Custom: __("الخطة المرفوعة"),
            Approved: __("الخطة المعتمدة"),
        };
        const buttons = tabs.map(tab => (
            `<button type="button" class="btn btn-sm sf-plan-tab ${active === tab ? "btn-primary" : "btn-default"}" data-plan-tab="${esc(tab)}">${labels[tab] || tab}${badge(tab)}</button>`
        )).join("");
        const panels = tabs.map(tab => (
            `<div class="sf-plan-tab-panel" data-plan-panel="${esc(tab)}" style="${active === tab ? "" : "display:none"}">${planHtmlForTab(detail, tab) || emptyPlanHtml(emptyMessageForTab(tab))}</div>`
        )).join("");

        return `
            <div class="dco-drawing-plan-inbox-host"></div>
            <div class="almdina-sf-plan-tabs" data-active-tab="${esc(active)}">
                <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">${buttons}</div>
                ${panels}
            </div>
        `;
    }

    function planHtmlForTab(detail, tab) {
        if (tab === "Custom") {
            return hasCustomPlan(detail) ? detail.custom_plan_html : "";
        }
        if (tab === "Approved") {
            return detail.approved_plan_html || "";
        }
        return detail.system_plan_html || "";
    }

    function emptyMessageForTab(tab) {
        if (tab === "Custom") return __("لا توجد خطة مرفوعة.");
        if (tab === "Approved") return __("لا توجد خطة معتمدة.");
        return __("لا توجد خطة نظام.");
    }

    function bindPlanTabs($detail) {
        $detail.find(".sf-plan-tab").on("click", function () {
            const tab = $(this).attr("data-plan-tab");
            $detail.find(".sf-plan-tab").removeClass("btn-primary").addClass("btn-default");
            $(this).removeClass("btn-default").addClass("btn-primary");
            $detail.find(".sf-plan-tab-panel").hide();
            $detail.find(`[data-plan-panel="${tab}"]`).show();
            $detail.find(".almdina-sf-plan-tabs").attr("data-active-tab", tab);
        });
    }

    function resolveStageContext(detail, meta) {
        return {
            order: detail.name || meta.order,
            stage: detail.active_stage_name || detail.current_production_stage || meta.stage,
            status: detail.active_stage_status || meta.status,
            stageType: detail.current_stage_type || meta.stageType,
            next: detail.can_handoff_to || meta.next,
        };
    }

    function holdsStageOperationalRole(detail) {
        return Boolean(detail && detail.actor_holds_operational_role);
    }

    function canUploadDxf(detail, meta) {
        if (!detail || !holdsStageOperationalRole(detail)) return false;
        const capability = detail.production_dxf ? "replace_dxf" : "upload_dxf";
        return documentCan(detail, capability);
    }

    function buildActionsHtml(detail, meta) {
        const context = resolveStageContext(detail, meta);
        const actions = [`<button type="button" class="btn btn-default back-to-list">${__("رجوع")}</button>`];
        const activeMode = mode === "board" || mode === "inbox";
        if (activeMode && detail.can_start_stage) {
            actions.push(`<button type="button" class="btn btn-primary start-stage">${__("بدء العمل")}</button>`);
        }
        if (activeMode && detail.can_handoff_stage) {
            actions.push(`<button type="button" class="btn btn-success handoff-stage">${!context.next ? __("جاهزة للتسليم") : __("إرسال للقسم التالي")}</button>`);
        }
        if (activeMode && detail.can_reassign_worker) {
            actions.push(`<button type="button" class="btn btn-default reassign-worker">${__("تغيير العامل")}</button>`);
        }
        if (canUploadDxf(detail, meta)) {
            actions.push(
                `<button type="button" class="btn btn-default upload-dxf-plan">${detail.production_dxf ? __("استبدال خطة DXF") : __("رفع خطة DXF")}</button>`
            );
        }
        if (documentCan(detail, "print_cutting_plan")) {
            actions.push(`<button type="button" class="btn btn-default print-plan">${__("طباعة خطة القص")}</button>`);
        }
        return actions.join(" ");
    }

    function stageStatusLabel(detail, meta) {
        const context = resolveStageContext(detail, meta);
        return detail.department_status || statusLabel(context.status);
    }

    function openDetail(meta) {
        selected = { ...meta };
        const requestId = ++detailRequest;
        const requestedOrder = meta.order;
        const $detail = $content.find(".shop-floor-detail");
        $content.find(".almdina-sf-overview").hide();
        $detail.html(`<div class="text-muted">${__("جاري تحميل تفاصيل الطلب...")}</div>`).show();

        return frappe
            .call({ method: METHODS.detail, args: { order_name: requestedOrder } })
            .then(response => {
                if (requestId !== detailRequest || !selected || selected.order !== requestedOrder) return;
                renderDetail($detail, response.message || {}, meta, requestId);
            })
            .catch(error => {
                if (requestId !== detailRequest) return;
                $detail.html(`<div class="almdina-sf-empty">${esc(error && error.message ? error.message : __("تعذر تحميل تفاصيل الطلب."))}</div>`);
            });
    }

    function renderDetail($detail, detail, meta, requestId) {
        const context = resolveStageContext(detail, meta);
        selected = { ...meta, ...context };
        const showDxf = Boolean(detail.production_dxf) && documentCan(detail, "view_cutting_plan");
        const showPlan = Boolean(
            (Array.isArray(detail.visible_plan_tabs) && detail.visible_plan_tabs.length) ||
            documentCan(detail, "view_cutting_plan") ||
            documentCan(detail, "view_system_cutting_plan") ||
            documentCan(detail, "view_uploaded_cutting_plan") ||
            documentCan(detail, "view_approved_cutting_plan")
        );
        $detail.html(`
            <div class="frappe-card" style="padding:14px;border-radius:14px">
                <div style="margin-bottom:12px">
                    <h3 class="almdina-sf-detail-title">${esc(detail.name || context.order)}</h3>
                    <div class="text-muted">${esc(detail.customer || "")}</div>
                    <div style="font-size:13px;margin-top:4px">${__("القسم")}: <b>${esc(detail.current_department || context.stageType || "")}</b> · ${__("الحالة")}: <b>${esc(stageStatusLabel(detail, context))}</b></div>
                    ${detail.active_stage_assigned_to ? `<div class="text-muted" style="font-size:12px;margin-top:3px">${__("العامل الحالي")}: ${esc(detail.active_stage_assigned_to)}</div>` : ""}
                </div>
                <div class="almdina-sf-actions">${buildActionsHtml(detail, context)}</div>
                ${!holdsStageOperationalRole(detail) && detail.current_stage_type
                    ? `<div class="text-muted" style="font-size:12px;margin:8px 0 12px">${__(
                        "يمكنك عرض هذا الطلب فقط. مرحلته الحالية ليست ضمن أدوارك التشغيلية."
                    )}</div>`
                    : ""}
                ${showDxf ? `<div style="margin-bottom:10px"><a class="btn btn-default" href="${esc(detail.production_dxf)}" target="_blank" rel="noopener">${__("تنزيل DXF الإنتاج")}</a><span class="text-muted"> · ${esc(__(detail.drawing_dxf_status || ""))}</span></div>` : ""}
                ${detail.pieces_html ? `<div class="almdina-sf-pieces-wrap" style="margin:8px 0 14px">${detail.pieces_html}</div>` : `<div class="almdina-sf-empty" style="margin:8px 0 14px">${__("لا توجد قطع مسجّلة.")}</div>`}
                ${showPlan ? `<div style="margin:8px 0 10px"><b>${__("خطة القص والرسومات")}</b></div><div class="almdina-sf-plan-wrap cutting-plan-wrap">${buildPlanTabsHtml(detail)}</div>` : ""}
            </div>
        `);

        $detail.find(".back-to-list").on("click", backToList);
        $detail.find(".start-stage").on("click", () => startStage(context));
        $detail.find(".handoff-stage").on("click", () => handoffStage(context));
        $detail.find(".reassign-worker").on("click", () => reassignWorker(context));
        $detail.find(".upload-dxf-plan").on("click", () => uploadDxfPlan(detail, context));
        $detail.find(".print-plan").on("click", () => printPlan($detail, detail));
        bindPlanTabs($detail);
        renderDrawingPanel($detail, detail, context, requestId);
    }

    function uploadDxfPlan(detail, meta) {
        if (!canUploadDxf(detail, meta)) {
            frappe.msgprint(__("ليست لديك صلاحية رفع خطة القص كملف DXF في المرحلة الحالية."));
            return;
        }
        const orderName = detail.name || meta.order;
        const replacing = Boolean(detail.production_dxf);
        new frappe.ui.FileUploader({
            doctype: "Door Cutting Order",
            docname: orderName,
            folder: "Home/Attachments",
            is_private: 1,
            restrictions: { allowed_file_types: [".dxf"], max_file_size: 10 * 1024 * 1024 },
            on_success(file) {
                frappe.call({
                    method: "almdina_erp.almdina_erp.services.shop_floor_service.upload_production_dxf",
                    args: { order_name: orderName, file_url: file.file_url },
                    freeze: true,
                    freeze_message: __("جاري التحقق من ملف DXF وتطبيق الخطة..."),
                }).then(() => {
                    frappe.show_alert({
                        message: replacing
                            ? __("تم استبدال ملف DXF والتحقق منه.")
                            : __("تم رفع ملف DXF والتحقق منه."),
                        indicator: "green",
                    }, 5);
                    return openDetail({ ...meta, order: orderName });
                });
            },
        });
    }

    function drawingPlanModule() {
        if (window.AlmdinaDrawingPlanUX) return Promise.resolve(window.AlmdinaDrawingPlanUX);
        if (!frappe.require) return Promise.resolve(null);
        return Promise.resolve(
            frappe.require("/assets/almdina_erp/js/door_cutting_order_drawing_plan_ux.js")
        )
            .then(() => window.AlmdinaDrawingPlanUX || null)
            .catch(error => {
                console.error("Failed to load the drawing plan panel", error);
                return null;
            });
    }

    function renderDrawingPanel($detail, detail, context, requestId) {
        const $host = $detail.find(".dco-drawing-plan-inbox-host");
        if (!$host.length) return;
        const refresh = preview => {
            if (requestId !== detailRequest || !selected || selected.order !== context.order) return Promise.resolve();
            if (preview && preview.system_plan_json) detail.system_plan_json = preview.system_plan_json;
            return openDetail({ ...context });
        };
        // The panel module is shipped app-wide but can still be pending when the
        // detail renders. Wait for it instead of leaving an empty placeholder
        // that only a page reload would fill.
        drawingPlanModule().then(module => {
            if (!module || typeof module.renderInboxPanel !== "function") return;
            if (requestId !== detailRequest || !$host.closest("body").length) return;
            module.renderInboxPanel($host, context, detail, refresh);
        });
    }

    function backToList() {
        detailRequest += 1;
        selected = null;
        $content.find(".shop-floor-detail").hide().empty();
        $content.find(".almdina-sf-overview").show();
    }

    function startStage(context) {
        return frappe.call({
            method: METHODS.start,
            args: { stage_name: context.stage },
            freeze: true,
            freeze_message: __("بدء العمل..."),
        }).then(() => {
            frappe.show_alert({ message: __("تم بدء العمل."), indicator: "green" });
            loadList();
        });
    }

    function workerOptions(workers) {
        return workers.map(worker => ({
            label: worker.full_name && worker.full_name !== worker.name
                ? `${worker.full_name} (${worker.name})`
                : worker.name,
            value: worker.name,
        }));
    }

    function handoffStage(context) {
        if (!context.next) {
            frappe.confirm(__("تأكيد إنهاء آخر مرحلة واعتبار الطلب جاهزًا للتسليم؟"), () => {
                frappe.call({
                    method: METHODS.handoff,
                    args: { stage_name: context.stage },
                    freeze: true,
                }).then(() => {
                    frappe.show_alert({ message: __("الطلب جاهز للتسليم."), indicator: "green" });
                    loadList();
                });
            });
            return;
        }

        frappe.call({ method: METHODS.handoffContext, args: { stage_name: context.stage } }).then(response => {
            const handoff = response.message || {};
            const workers = handoff.workers || [];
            if (!workers.length) {
                frappe.msgprint(__("لا يوجد عمال متاحون للدور {0} في القسم التالي.", [handoff.operational_role || ""]));
                return;
            }
            frappe.prompt(
                [{
                    fieldname: "next_assignee",
                    fieldtype: "Select",
                    label: `${__("العامل التالي")} — ${handoff.next_department || handoff.next_stage_type || ""}`,
                    options: workerOptions(workers),
                    reqd: 1,
                }],
                values => frappe.call({
                    method: METHODS.handoff,
                    args: { stage_name: context.stage, next_assignee: values.next_assignee },
                    freeze: true,
                }).then(() => {
                    frappe.show_alert({ message: __("تم إرسال الطلب للقسم التالي."), indicator: "green" });
                    loadList();
                }),
                __("إرسال للقسم التالي"),
                __("إرسال")
            );
        });
    }

    function reassignWorker(context) {
        frappe.call({ method: METHODS.reassignmentWorkers, args: { stage_name: context.stage } }).then(response => {
            const workers = response.message || [];
            if (!workers.length) {
                frappe.msgprint(__("لا يوجد عمال مؤهلون لهذا القسم."));
                return;
            }
            frappe.prompt(
                [{
                    fieldname: "assignee",
                    fieldtype: "Select",
                    label: __("العامل الجديد"),
                    options: workerOptions(workers),
                    reqd: 1,
                }],
                values => frappe.call({
                    method: METHODS.reassign,
                    args: { stage_name: context.stage, assignee: values.assignee },
                    freeze: true,
                }).then(() => {
                    frappe.show_alert({ message: __("تم تغيير العامل."), indicator: "green" });
                    loadList();
                }),
                __("تغيير العامل"),
                __("حفظ")
            );
        });
    }

    function printPlan($detail, detail) {
        if (!documentCan(detail, "print_cutting_plan")) return;
        const tab = $detail.find(".almdina-sf-plan-tabs").attr("data-active-tab")
            || detail.active_plan_source
            || "System";
        const html = tab === "Custom"
            ? detail.custom_plan_html
            : tab === "Approved"
                ? detail.approved_plan_html
                : (detail.system_plan_html || detail.cutting_plan_html);
        if (!html) {
            frappe.msgprint(__("لا يوجد مخطط قص للطباعة."));
            return;
        }
        const printWindow = window.open("", "_blank");
        if (!printWindow) {
            frappe.msgprint(__("المتصفح منع فتح نافذة الطباعة."));
            return;
        }
        printWindow.document.open();
        printWindow.document.write(`<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>${esc(__("خطة قص"))}</title><style>@page{size:A4 portrait;margin:6mm}body{font-family:Arial,Tahoma,sans-serif;direction:rtl;padding:5mm}</style></head><body>${html}<script>window.onload=function(){setTimeout(function(){window.focus();window.print();},500);};<\/script></body></html>`);
        printWindow.document.close();
    }

    $tabs.on("click", ".almdina-sf-tab", function () {
        setMode($(this).attr("data-sf-mode"));
    });
    $tabs.on("click", ".almdina-sf-refresh", () => loadList());

    try {
        page.clear_primary_action();
        page.clear_inner_toolbar();
    } catch (error) {
        // Frappe versions without these helpers can safely keep the empty toolbar.
    }

    function reload() {
        return loadSessionContext().then(loadList).catch(error => {
            renderError(error && error.message ? error.message : __("لا تملك صلاحية الدخول إلى صالة الإنتاج."));
        });
    }

    if (window.AlmdinaPageRevisit) {
        window.AlmdinaPageRevisit.refreshOnRevisit(wrapper, reload);
    }

    syncTabs();
    reload();
};
