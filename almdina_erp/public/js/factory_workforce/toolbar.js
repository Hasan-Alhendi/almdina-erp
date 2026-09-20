(() => {
    "use strict";

    if (window.AlmdinaFactoryWorkforceToolbar) return;

    function create(options = {}) {
        const $main = options.$main;
        const state = options.state;
        const lifecycle = options.lifecycle;
        const load = options.load;
        const t = typeof options.translate === "function" ? options.translate : value => value;
        let controls = null;
        let mounted = false;

        function enabledFilterLabel(value) {
            const labels = {
                all: t("الكل"),
                "1": t("مفعّل"),
                "0": t("معطّل"),
            };
            return labels[String(value || "all")] || labels.all;
        }

        function enabledFilterValue(label) {
            const entries = [
                ["all", t("الكل")],
                ["1", t("مفعّل")],
                ["0", t("معطّل")],
            ];
            const match = entries.find(([, text]) => text === label);
            return match ? match[0] : "all";
        }

        function enabledFilterOptions() {
            return [t("الكل"), t("مفعّل"), t("معطّل")].join("\n");
        }

        function dispose() {
            if (!controls) {
                mounted = false;
                return false;
            }
            controls.search.dispose();
            controls.enabled.dispose();
            controls = null;
            mounted = false;
            return true;
        }

        function mount() {
            dispose();
            const ui = window.AlmdinaUi;
            if (!ui || typeof ui.control !== "function") {
                throw new Error("AlmdinaUi.control is required for Factory Workforce toolbar");
            }
            const $searchMount = $main.find(".aw-search-mount");
            const $enabledMount = $main.find(".aw-enabled-mount");
            if (!$searchMount.length || !$enabledMount.length) return false;

            const search = ui.control({
                parent: $searchMount,
                fieldname: "search",
                fieldtype: "Data",
                placeholder: t("اكتب للبحث..."),
                value: state.search || "",
                className: "aw-search-control-mount",
                onlyInput: true,
                onChange: value => {
                    lifecycle.timeout(() => {
                        const next = String(value || "").trim();
                        if (next === state.search) return;
                        state.search = next;
                        load();
                    }, 350, "workforce-search");
                },
            });
            const enabled = ui.control({
                parent: $enabledMount,
                fieldname: "enabled",
                fieldtype: "Select",
                options: enabledFilterOptions(),
                value: enabledFilterLabel(state.enabled),
                className: "aw-enabled-control-mount",
                onlyInput: true,
                onChange: value => {
                    const next = enabledFilterValue(String(value || ""));
                    if (next === state.enabled) return;
                    state.enabled = next;
                    load();
                },
            });
            controls = { search, enabled };
            mounted = true;
            return true;
        }

        lifecycle.track(() => dispose(), "workforce-toolbar-owner");

        return Object.freeze({
            mount,
            dispose,
            isMounted: () => mounted,
        });
    }

    window.AlmdinaFactoryWorkforceToolbar = Object.freeze({ create });
})();
