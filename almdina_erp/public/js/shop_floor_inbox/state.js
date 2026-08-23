(() => {
    "use strict";

    const Frontend = window.AlmdinaFrontend;
    if (!Frontend || typeof Frontend.createLatestRequestGate !== "function" || typeof Frontend.createLifecycleScope !== "function") {
        throw new Error("AlmdinaFrontend request/lifecycle helpers are required");
    }

    function create() {
        const contextGate = Frontend.createLatestRequestGate();
        const listGate = Frontend.createLatestRequestGate();
        const lifecycle = Frontend.createLifecycleScope();
        const current = {
            mode: "board",
            sessionContext: null,
            boardRows: [],
            archiveRows: [],
            routeFilter: "",
            search: "",
        };

        function deactivate() {
            contextGate.invalidate();
            listGate.invalidate();
            current.sessionContext = null;
        }

        return Object.freeze({
            mode: () => current.mode,
            setMode(value) {
                const mode = String(value || "board");
                current.mode = ["board", "inbox", "account"].includes(mode) ? mode : "board";
                listGate.invalidate();
                return current.mode;
            },
            context: () => current.sessionContext,
            setContext(value) {
                current.sessionContext = value && typeof value === "object" ? value : {};
                return current.sessionContext;
            },
            setRows(activeRows, archiveRows) {
                current.boardRows = Array.isArray(activeRows) ? activeRows : [];
                current.archiveRows = Array.isArray(archiveRows) ? archiveRows : [];
            },
            setRouteFilter(value) {
                current.routeFilter = String(value || "");
                return current.routeFilter;
            },
            setSearch(value) {
                current.search = String(value || "").trim().toLocaleLowerCase();
                return current.search;
            },
            beginContextRequest: meta => contextGate.begin(meta),
            isCurrentContextRequest: token => contextGate.isCurrent(token),
            beginListRequest: meta => listGate.begin(meta),
            isCurrentListRequest: token => listGate.isCurrent(token),
            lifecycle,
            snapshot() {
                return Object.freeze({
                    mode: current.mode,
                    sessionContext: current.sessionContext,
                    boardRows: current.boardRows.slice(),
                    archiveRows: current.archiveRows.slice(),
                    routeFilter: current.routeFilter,
                    search: current.search,
                });
            },
            deactivate,
            dispose() {
                deactivate();
                lifecycle.dispose();
            },
        });
    }

    window.AlmdinaShopFloorInboxState = Object.freeze({ create });
})();
