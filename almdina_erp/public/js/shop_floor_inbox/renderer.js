(() => {
    "use strict";


    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split("{" + index + "}").join(String(value));
            });
        }
        return text;
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const dir = root && root.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }

    const ViewModel = window.AlmdinaShopFloorInboxViewModel;

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function uiButton(options) {
        const ui = window.AlmdinaUi;
        if (!ui || typeof ui.button !== "function") {
            throw new Error("AlmdinaUi.button is required for Shop Floor Inbox rendering");
        }
        return ui.button(options);
    }

    function statusLabel(status) {
        const labels = {
            Pending: translate("Needs work"),
            "In Progress": translate("In progress"),
            Paused: translate("Paused"),
            Completed: translate("Completed"),
        };
        return labels[status] || translate(status || "");
    }

    function createShell(wrapper, page) {
        if (!page) throw new Error("Shop Floor Inbox page shell is unavailable");
        const $section = $(wrapper).find(".layout-main-section");
        let $content = $section.children(".almdina-sf-content").first();
        if (!$content.length) {
            $content = $('<div class="almdina-sf-content"></div>');
            $section.append($content);
        }
        const pageDir = uiDirection();
        $section.attr("dir", pageDir);
        $content.attr("dir", pageDir);
        if (!$section.children(".almdina-sf-nav").length) {
            $content.before(`
            <div class="almdina-ui almdina-sf-nav" dir="${pageDir}" aria-label="${translate("Shop floor navigation")}">
                <div class="almdina-sf-tabs" role="tablist" aria-label="${translate("Shop floor sections")}">
                    <button type="button" class="almdina-sf-tab is-active" role="tab" aria-selected="true" data-sf-mode="board">${translate("Production board")}</button>
                    <button type="button" class="almdina-sf-tab" role="tab" aria-selected="false" data-sf-mode="inbox">${translate("Order list")}</button>
                    <button type="button" class="almdina-sf-tab" role="tab" aria-selected="false" data-sf-mode="account">${translate("Account")}</button>
                </div>
            </div>
            `);
        }
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
            $content,
            hasBootstrapLoading: () => $content.find('[data-almdina-loading-owner="shop-floor-bootstrap"]').length > 0,
        });
    }

    function syncTabs(shell, mode) {
        shell.$tabs.find(".almdina-sf-tab").each(function () {
            const active = $(this).attr("data-sf-mode") === mode;
            $(this).toggleClass("is-active", active);
            $(this).attr("aria-selected", active ? "true" : "false");
        });
    }

    function pageHero(kicker, title, description, stats = "") {
        return `
            <header class="almdina-sf-hero alm-page-intro alm-page-intro--accented">
                <div class="almdina-sf-hero-copy alm-page-intro__copy">
                    <span class="almdina-sf-eyebrow alm-page-intro__eyebrow">${esc(kicker)}</span>
                    <h2 class="alm-page-intro__title">${esc(title)}</h2>
                    <p class="alm-page-intro__description">${esc(description)}</p>
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
            <div class="almdina-ui almdina-sf-shell alm-page alm-page--workbench">
                <div class="almdina-sf-state almdina-sf-loading" role="status" aria-live="polite">
                    <span class="almdina-sf-spinner" aria-hidden="true"></span>
                    <div><b>${translate("Loading")}</b><span>${esc(message)}</span></div>
                </div>
            </div>`);
    }

    function renderError(shell, message) {
        shell.$content.html(`
            <div class="almdina-ui almdina-sf-shell alm-page alm-page--workbench">
                <div class="almdina-sf-state is-error" role="alert">
                    <span class="almdina-sf-state-icon" aria-hidden="true">!</span>
                    <div><b>${translate("Could not refresh the shop floor")}</b><span>${esc(message || translate("Could not load the data."))}</span></div>
                </div>
            </div>
        `);
    }

    function quickActionHtml(row, mode) {
        const controller = window.AlmdinaShopFloorQuickActions;
        const action = controller && controller.actionFor(ViewModel.quickActionContext(row, mode));
        if (!action) return "";
        const variant = action.indicator === "success" ? "success" : "primary";
        return uiButton({
            label: action.label,
            variant,
            className: "sf-quick-action",
            attrs: { "aria-label": `${action.label} — ${row.door_cutting_order || ""}` },
        });
    }

    function orderCardHtml(row, mode, { compact = false, terminal = false, completed = false } = {}) {
        const canDrag = compact && !terminal && row.can_handoff_stage === true;
        const cardClasses = `${compact ? " almdina-sf-kanban-card" : ""}${completed ? " is-completed" : ""}`;
        const stageLabel = completed && row.current_department
            ? row.current_department
            : (row.department_label || row.stage_type);
        const statusText = terminal
            ? translate("Ready for delivery")
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
                aria-label="${esc(`${translate("Order")} ${row.door_cutting_order || ""} — ${statusText}`)}"
                draggable="${canDrag ? "true" : "false"}">
                <div class="almdina-sf-card-head">
                    <div class="almdina-sf-card-identity">
                        <span class="almdina-sf-order-number">${esc(row.door_cutting_order)}</span>
                        <span class="almdina-sf-card-subtitle">${esc(customerLine || translate("No customer details"))}</span>
                    </div>
                    <span class="indicator-pill ${terminal || completed ? "green" : "blue"}">${esc(terminal ? translate("Ready") : statusLabel(row.status))}</span>
                </div>
                <div class="almdina-sf-card-context">
                    ${compact ? "" : `<div><span>${translate("Department")}</span><b>${esc(stageLabel)}</b></div>`}
                    <div><span>${translate("Status")}</span><b>${esc(statusText)}</b></div>
                    ${row.assigned_to ? `<div><span>${translate("Worker")}</span><b dir="auto">${esc(row.assigned_to)}</b></div>` : ""}
                </div>
                <div class="almdina-sf-card-meta">
                    <div class="almdina-sf-meta-item">
                        <span>${translate("Edge color")}</span>
                        <b>${esc(row.edge_color || "—")}</b>
                    </div>
                    <div class="almdina-sf-meta-item">
                        <span>${translate("Board")}</span>
                        <b>${esc(row.board_description || "—")}</b>
                    </div>
                </div>
                <div class="almdina-sf-card-actions">
                    ${terminal || completed ? "" : quickActionHtml(row, mode)}
                    ${uiButton({
                        label: translate("Open the order"),
                        variant: "secondary",
                        className: "sf-open-btn",
                        attrs: { "aria-label": `${translate("Open the order")} ${row.door_cutting_order || ""}` },
                    })}
                </div>
                ${canDrag ? `<div class="almdina-sf-drag-hint"><span aria-hidden="true">↔</span>${translate("Drag to the next stage")}</div>` : ""}
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
        const label = ready ? translate("Ready for delivery") : (stage.department || stage.stage_type);
        const cards = rows.length
            ? rows.map(row => orderCardHtml(row, mode, { compact: true, terminal: ready })).join("")
            : `<div class="almdina-sf-kanban-empty" role="status"><span aria-hidden="true">◇</span>${translate("No orders")}</div>`;
        return `
            <section class="almdina-sf-kanban-column${ready ? " is-ready" : ""}"
                aria-label="${esc(`${label} — ${rows.length} ${translate("Order")}`)}"
                data-route="${esc(route.name)}" data-drop-stage="${esc(stageType)}">
                <header class="almdina-sf-kanban-column-header">
                    <div><b>${esc(label)}</b>${stage && stage.is_planning_stage ? `<span>${translate("Planning")}</span>` : ""}</div>
                    <span class="almdina-sf-column-count" aria-label="${esc(`${rows.length} ${translate("Order")}`)}">${rows.length}</span>
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
            <section class="almdina-sf-route-board" data-board-route="${esc(route.name)}" aria-label="${esc(route.label || translate("Unspecified route"))}">
                <div class="almdina-sf-route-heading">
                    <div class="almdina-sf-route-title">
                        <span class="almdina-sf-route-icon" aria-hidden="true">⇢</span>
                        <div><h3>${esc(route.label || translate("Unspecified route"))}</h3><span>${routeRows.length + readyRows.length} ${translate("Order")}</span></div>
                    </div>
                    <small>${translate("Movement follows the route order and the user's permissions.")}</small>
                </div>
                <div class="almdina-sf-kanban" aria-label="${esc(`${translate("Stages")} ${route.label || translate("Unspecified route")}`)}">${columns.join("")}</div>
            </section>`;
    }

    function updateBoardContent(shell, model, mode = "board") {
        const activeCount = model.counts.pending + model.counts.progress + model.counts.paused;
        shell.$content.find(".almdina-sf-hero-stats").html([
            heroStat(translate("In follow-up"), activeCount, "active"),
            heroStat(translate("Ready for delivery"), model.counts.ready, "ready"),
            heroStat(translate("Routes"), model.routes.length, "neutral"),
        ].join(""));
        shell.$content.find(".almdina-sf-board-metrics").html([
            boardMetric(translate("Needs work"), model.counts.pending, "pending"),
            boardMetric(translate("In progress"), model.counts.progress, "progress"),
            boardMetric(translate("Paused"), model.counts.paused, "paused"),
            boardMetric(translate("Ready"), model.counts.ready, "ready"),
        ].join(""));
        const boards = model.routeModels.length
            ? model.routeModels.map(item => routeBoardHtml(item, mode)).join("")
            : emptyState(translate("No production route is enabled"), translate("Enable a route from production settings to show it here."));
        shell.$content.find(".almdina-sf-boards").html(boards);
    }

    function renderBoard(shell, model, mode = "board", options = {}) {
        if (options.preserveToolbar === true) {
            updateBoardContent(shell, model, mode);
            return;
        }
        const boards = model.routeModels.length
            ? model.routeModels.map(item => routeBoardHtml(item, mode)).join("")
            : emptyState(translate("No production route is enabled"), translate("Enable a route from production settings to show it here."));
        const activeCount = model.counts.pending + model.counts.progress + model.counts.paused;
        shell.$content.html(`
            <div class="almdina-ui almdina-sf-shell almdina-sf-board-shell alm-page alm-page--workbench">
                ${pageHero(
                    translate("Production floor"),
                    translate("Follow production stages"),
                    translate("View orders by route and run the available action without leaving the board."),
                    `<div class="almdina-sf-hero-stats">${[
                        heroStat(translate("In follow-up"), activeCount, "active"),
                        heroStat(translate("Ready for delivery"), model.counts.ready, "ready"),
                        heroStat(translate("Routes"), model.routes.length, "neutral"),
                    ].join("")}</div>`
                )}
                <div class="almdina-sf-overview">
                    <div class="almdina-sf-board-toolbar alm-toolbar" aria-label="${translate("Filter the production board")}">
                        <div class="almdina-sf-filter-field">
                            <span class="almdina-sf-field-label">${translate("Production route")}</span>
                            <div class="almdina-sf-route-mount"></div>
                        </div>
                        <div class="almdina-sf-filter-field almdina-sf-search-field">
                            <span class="almdina-sf-field-label">${translate("Quick search")}</span>
                            <div class="almdina-sf-search-mount"></div>
                        </div>
                        <div class="almdina-sf-board-metrics" aria-label="${translate("Order status summary")}">
                            ${boardMetric(translate("Needs work"), model.counts.pending, "pending")}
                            ${boardMetric(translate("In progress"), model.counts.progress, "progress")}
                            ${boardMetric(translate("Paused"), model.counts.paused, "paused")}
                            ${boardMetric(translate("Ready"), model.counts.ready, "ready")}
                        </div>
                    </div>
                    <div class="almdina-sf-board-help" role="note"><span aria-hidden="true">i</span><p>${translate("Use the action button on the card. On desktop you can also drag an in-progress card to the next stage; the server re-checks permissions before running the action.")}</p></div>
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
        const title = translate("Assigned orders");
        const canViewHistory = model.canViewHistory === true;
        if (model.assigned.length || (canViewHistory && model.completed.length)) {
            sections = model.assigned.length
                ? listSection(title, model.assigned, mode)
                : `<section class="almdina-sf-list-section"><div class="almdina-sf-list-title"><div><span class="almdina-sf-list-dot" aria-hidden="true"></span>${esc(title)}</div></div>${emptyState(translate("There are no assigned orders"), translate("Orders that enter your operational role will appear here."))}</section>`;
            if (canViewHistory) {
                sections += listSection(translate("Completed orders"), model.completed, mode, { completed: true });
            }
        }
        const description = canViewHistory
            ? translate("Start with assigned orders, then review completed work in the lower section.")
            : translate("Follow the orders assigned to you and run the available action for each order.");
        const stats = [heroStat(translate("Assigned"), model.assigned.length, "active")];
        if (canViewHistory) {
            stats.push(heroStat(translate("Completed"), model.completed.length, "ready"));
        }
        const emptyDescription = canViewHistory
            ? translate("There is no assigned work or completed history in this section.")
            : translate("There is no work assigned to you right now.");
        shell.$content.html(`
            <div class="almdina-ui almdina-sf-shell alm-page alm-page--workbench">
                ${pageHero(
                    translate("Work list"),
                    translate("Your operational orders"),
                    description,
                    stats.join("")
                )}
                <div class="almdina-sf-overview">
                    ${sections || emptyState(translate("There are no orders right now"), emptyDescription)}
                </div>
            </div>`);
    }

    const SECTION_LABELS = Object.freeze({
        orders: "Orders",
        costing: "Costing",
        planning: "Cutting plan",
        drawing: "Drawing and DXF",
        production: "Production",
        administration: "Administration",
        reports: "Reports",
    });

    function renderAccount(shell, model) {
        const enabledSections = model.enabledSections.map(name => SECTION_LABELS[name] ? translate(SECTION_LABELS[name]) : name);
        const departmentText = model.departments.join(" · ") || "—";
        const sectionText = enabledSections.join(" · ") || "—";
        shell.$content.html(`
            <div class="almdina-ui almdina-sf-shell alm-page alm-page--workbench">
                ${pageHero(
                    translate("Account"),
                    translate("User information"),
                    translate("Review your operational identity and the departments available to you in the system."),
                    heroStat(translate("Operational departments"), model.departments.length, "neutral")
                )}
                <div class="almdina-sf-account-card">
                    <div class="almdina-sf-account-heading">
                        <span class="almdina-sf-account-avatar" aria-hidden="true">${esc((model.fullName || model.user || "?").trim().charAt(0) || "?")}</span>
                        <div><h4>${esc(model.fullName)}</h4><span dir="ltr">${esc(model.user)}</span></div>
                    </div>
                    <div class="almdina-sf-account-details">
                        <div class="almdina-sf-account-row"><span>${translate("Name")}</span><b>${esc(model.fullName)}</b></div>
                        <div class="almdina-sf-account-row"><span>${translate("User")}</span><b dir="ltr">${esc(model.user)}</b></div>
                        <div class="almdina-sf-account-row"><span>${translate("Qualified departments")}</span><b>${esc(departmentText)}</b></div>
                        <div class="almdina-sf-account-row"><span>${translate("Available system sections")}</span><b>${esc(sectionText)}</b></div>
                    </div>
                    <div class="almdina-sf-account-footer">
                        <span>${translate("Signing out ends the current work session on this device.")}</span>
                        ${uiButton({ label: translate("Sign out"), variant: "danger", className: "almdina-sf-logout" })}
                    </div>
                </div>
            </div>`);
    }

    function focusSearch(shell, searchControl) {
        if (searchControl && typeof searchControl.focus === "function") {
            searchControl.focus();
            return;
        }
        const input = shell.$content.find(".almdina-sf-search-control-mount input").get(0);
        if (!input) return;
        input.focus();
        if (typeof input.setSelectionRange === "function") {
            input.setSelectionRange(input.value.length, input.value.length);
        }
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