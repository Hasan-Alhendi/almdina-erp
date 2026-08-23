(() => {
    "use strict";

    if (window.AlmdinaFactoryPermissionsState) return;

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

    function clone(value) {
        return JSON.parse(JSON.stringify(value || {}));
    }

    function stable(value) {
        return JSON.stringify(
            Object.keys(value || {}).sort().reduce((result, key) => {
                result[key] = value[key] === true;
                return result;
            }, {})
        );
    }

    function unique(values) {
        return [...new Set((values || []).map(value => String(value || "")).filter(Boolean))];
    }

    function create() {
        const frontend = foundation();
        const data = {
            catalog: [],
            roles: [],
            transfer: {},
            selectedRole: "",
            baseline: {},
            working: {},
            preview: null,
            saving: false,
        };
        const requests = Object.freeze({
            console: frontend.createLatestRequestGate(),
            role: frontend.createLatestRequestGate(),
            preview: frontend.createLatestRequestGate(),
            transfer: frontend.createLatestRequestGate(),
        });
        const lifecycle = frontend.createLifecycleScope();

        function isDirty() {
            return stable(data.baseline) !== stable(data.working);
        }

        function invalidatePending() {
            requests.preview.invalidate();
            requests.transfer.invalidate();
        }

        function invalidateReads() {
            requests.console.invalidate();
            requests.role.invalidate();
            invalidatePending();
        }

        function deactivate() {
            invalidateReads();
        }

        function dispose() {
            deactivate();
            lifecycle.dispose();
        }

        return Object.freeze({
            data,
            requests,
            lifecycle,
            clone,
            stable,
            unique,
            isDirty,
            invalidatePending,
            invalidateReads,
            deactivate,
            dispose,
        });
    }

    window.AlmdinaFactoryPermissionsState = Object.freeze({
        create,
        clone,
        stable,
        unique,
    });
})();
