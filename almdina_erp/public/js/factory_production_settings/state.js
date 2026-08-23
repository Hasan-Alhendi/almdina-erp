(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsState) return;

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
        const data = { current: {} };
        const requests = Object.freeze({
            settings: frontend.createLatestRequestGate(),
            audit: frontend.createLatestRequestGate(),
        });
        const lifecycle = frontend.createLifecycleScope();

        function apply(payload = {}) {
            data.current = payload || {};
            return data.current;
        }

        function deactivate() {
            requests.settings.invalidate();
            requests.audit.invalidate();
        }

        function dispose() {
            deactivate();
            lifecycle.dispose();
        }

        return Object.freeze({ data, requests, lifecycle, apply, deactivate, dispose });
    }

    window.AlmdinaFactoryProductionSettingsState = Object.freeze({ create });
})();
