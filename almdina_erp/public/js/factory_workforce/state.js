(() => {
    "use strict";

    if (window.AlmdinaFactoryWorkforceState) return;

    function foundation() {
        const api = window.AlmdinaFrontend;
        if (
            !api
            || typeof api.createLatestRequestGate !== "function"
            || typeof api.createLifecycleScope !== "function"
        ) {
            throw new Error("Almdina frontend foundation is unavailable");
        }
        return api;
    }

    function create() {
        const frontend = foundation();
        const data = {
            users: [],
            availableUsers: [],
            roles: [],
            permissions: {},
            summary: {},
            search: "",
            enabled: "all",
        };
        const requests = Object.freeze({
            console: frontend.createLatestRequestGate(),
            audit: frontend.createLatestRequestGate(),
        });
        const lifecycle = frontend.createLifecycleScope();

        function applyConsole(payload = {}) {
            data.users = Array.isArray(payload.users) ? payload.users : [];
            data.availableUsers = Array.isArray(payload.available_users) ? payload.available_users : [];
            data.roles = Array.isArray(payload.roles) ? payload.roles : [];
            data.permissions = payload.permissions || {};
            data.summary = payload.summary || {};
        }

        function hasRows() {
            return Boolean(data.users.length || data.availableUsers.length);
        }

        function deactivate() {
            requests.console.invalidate();
            requests.audit.invalidate();
        }

        function dispose() {
            deactivate();
            lifecycle.dispose();
        }

        return Object.freeze({
            data,
            requests,
            lifecycle,
            applyConsole,
            hasRows,
            deactivate,
            dispose,
        });
    }

    window.AlmdinaFactoryWorkforceState = Object.freeze({ create });
})();
