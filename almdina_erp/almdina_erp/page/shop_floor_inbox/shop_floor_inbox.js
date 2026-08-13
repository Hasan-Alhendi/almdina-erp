frappe.pages["shop-floor-inbox"].on_page_load = function (wrapper) {
    "use strict";

    const METHODS = Object.freeze({
        context: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_shop_floor_context",
        inbox: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_my_inbox",
        archive: "almdina_erp.almdina_erp.services.shop_floor_query_service.get_my_archive",
        handoffContext: "almdina_erp.almdina_erp.services.shop_floor_commands.get_handoff_context",
        handoff: "almdina_erp.almdina_erp.services.shop_floor_commands.handoff_to_next",
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
    let sessionContext = null;
    let boardRows = [];
    let boardArchiveRows = [];
    let boardRouteFilter = "";
    let boardSearch = "";
    let listRequest = 0;

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
                    <button type="button" class="btn btn-default sf-open-btn" style="flex:1">${__("فتح الطلب")}</button>
                </div>
                ${canDrag ? `<div class="almdina-sf-drag-hint">${__("اسحب للمرحلة التالية")}</div>` : ""}
            </div>`;
    }

    function bindCardActions($scope) {
        $scope.find(".shop-floor-order-card").on("click", function (event) {
            if ($(event.target).closest(".sf-quick-action").length) return;
            const context = cardContext($(this));
            if (context.order) frappe.set_route("Form", "Door Cutting Order", context.order);
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
