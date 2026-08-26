(() => {
    "use strict";

    const UNCONFIGURED_ROUTE = "__unconfigured__";

    function asRows(value) {
        return Array.isArray(value) ? value : [];
    }

    function showsPersonalHistory(context) {
        return Boolean(context && context.personal_inbox);
    }

    function canViewHistory(context) {
        return Boolean(context && context.can_view_history === true);
    }

    function isMyOperationalStage(row) {
        return Boolean(row && row.actor_holds_current_stage_role === true);
    }

    function workerBoardRows(activeRows, context) {
        const source = asRows(activeRows);
        return showsPersonalHistory(context) ? source.filter(isMyOperationalStage) : source.slice();
    }

    function mergeVisibleList(activeRows, historyRows, context) {
        const assigned = showsPersonalHistory(context)
            ? asRows(activeRows).filter(isMyOperationalStage)
            : asRows(activeRows).slice();
        const completed = [];
        if (canViewHistory(context)) {
            const seen = new Set(assigned.map(row => row && row.door_cutting_order).filter(Boolean));
            asRows(historyRows).forEach(row => {
                const order = row && row.door_cutting_order;
                if (!order || seen.has(order)) return;
                seen.add(order);
                completed.push(row);
            });
        }
        return { assigned, completed, canViewHistory: canViewHistory(context) };
    }

    function routeKey(row) {
        return String((row && row.production_path) || "") || UNCONFIGURED_ROUTE;
    }

    function matchesBoardSearch(row, search) {
        const query = String(search || "").trim().toLocaleLowerCase();
        if (!query) return true;
        const haystack = [
            row && row.door_cutting_order,
            row && row.customer,
            row && row.board_description,
            row && row.edge_color,
            row && row.assigned_to,
            row && row.department_label,
        ].join(" ").toLocaleLowerCase();
        return haystack.includes(query);
    }

    function boardRoutes(activeRows, context) {
        const configured = Array.isArray(context && context.production_routes)
            ? context.production_routes.map(route => ({
                name: String(route.name || ""),
                label: route.label || route.name,
                stages: Array.isArray(route.stages) ? route.stages.slice() : [],
            }))
            : [];
        const known = new Set(configured.map(route => route.name));
        const unknown = new Map();
        asRows(activeRows).forEach(row => {
            const path = String((row && row.production_path) || "");
            if (known.has(path)) return;
            const key = path || UNCONFIGURED_ROUTE;
            if (!unknown.has(key)) {
                unknown.set(key, { name: key, label: path || "", stages: [], unconfigured: !path });
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
        unknown.forEach(route => route.stages.sort(
            (left, right) => Number(left.sequence || 0) - Number(right.sequence || 0)
        ));
        return configured.concat(Array.from(unknown.values()));
    }

    function terminalRows(route, archiveRows, search) {
        const stages = Array.isArray(route && route.stages) ? route.stages : [];
        const last = stages[stages.length - 1];
        if (!last) return [];
        const seen = new Set();
        return asRows(archiveRows).filter(row => {
            const matchesRoute = routeKey(row) === route.name;
            const ready = row.order_status === "Ready for Delivery";
            const isLastStage = row.stage_type === last.stage_type;
            const unique = !seen.has(row.door_cutting_order);
            if (matchesRoute && ready && isLastStage && unique) {
                seen.add(row.door_cutting_order);
                return matchesBoardSearch(row, search);
            }
            return false;
        });
    }

    function board(snapshot) {
        const context = snapshot.sessionContext || {};
        const activeSource = workerBoardRows(snapshot.boardRows, context);
        const routes = boardRoutes(activeSource, context);
        const routeFilter = routes.some(route => route.name === snapshot.routeFilter)
            ? snapshot.routeFilter
            : "";
        const visibleRoutes = routes.filter(route => !routeFilter || route.name === routeFilter);
        const searchedRows = activeSource.filter(row => matchesBoardSearch(row, snapshot.search));
        const filteredRows = routeFilter
            ? searchedRows.filter(row => routeKey(row) === routeFilter)
            : searchedRows;
        const routeModels = visibleRoutes.map(route => {
            const routeRows = filteredRows.filter(row => routeKey(row) === route.name);
            return {
                route,
                routeRows,
                readyRows: terminalRows(route, snapshot.archiveRows, snapshot.search),
            };
        });
        const readyCount = routeModels.reduce((total, item) => total + item.readyRows.length, 0);
        return {
            routes,
            routeFilter,
            routeModels,
            counts: {
                pending: filteredRows.filter(row => row.status === "Pending").length,
                progress: filteredRows.filter(row => row.status === "In Progress").length,
                paused: filteredRows.filter(row => row.status === "Paused").length,
                ready: readyCount,
            },
        };
    }

    function list(snapshot) {
        return mergeVisibleList(snapshot.boardRows, snapshot.archiveRows, snapshot.sessionContext || {});
    }

    function account(context) {
        const identity = (context && context.identity) || {};
        const sections = context && context.navigation && context.navigation.sections
            ? context.navigation.sections
            : {};
        return {
            fullName: identity.full_name || identity.user || "",
            user: identity.user || "",
            departments: Array.isArray(identity.departments) ? identity.departments.slice() : [],
            enabledSections: Object.keys(sections).filter(name => sections[name] === true),
        };
    }

    function quickActionContext(row, mode) {
        const activeMode = mode === "board" || mode === "inbox";
        return {
            order: row.door_cutting_order,
            stage: row.name,
            stageType: row.stage_type,
            canStart: activeMode && row.can_start_stage === true,
            canHandoff: activeMode && row.can_handoff_stage === true,
        };
    }

    const exported = Object.freeze({
        UNCONFIGURED_ROUTE,
        showsPersonalHistory,
        canViewHistory,
        isMyOperationalStage,
        workerBoardRows,
        mergeVisibleList,
        routeKey,
        matchesBoardSearch,
        boardRoutes,
        terminalRows,
        board,
        list,
        account,
        quickActionContext,
    });
    window.AlmdinaShopFloorInboxViewModel = exported;
    if (typeof module !== "undefined" && module.exports) module.exports = exported;
})();
