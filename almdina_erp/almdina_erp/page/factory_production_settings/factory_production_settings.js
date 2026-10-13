frappe.pages["factory-production-settings"].on_page_load = function (wrapper) {
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


    const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";
    const PAGE_LIFECYCLE = "/assets/almdina_erp/js/page_revisit_refresh.js";
    const MODULES = Object.freeze([
        "/assets/almdina_erp/js/almdina_ui.js",
        "/assets/almdina_erp/js/factory_production_settings/api.js",
        "/assets/almdina_erp/js/factory_production_settings/state.js",
        "/assets/almdina_erp/js/factory_production_settings/catalog_labels.js",
        "/assets/almdina_erp/js/factory_production_settings/view_model.js",
        "/assets/almdina_erp/js/factory_production_settings/renderer.js",
        "/assets/almdina_erp/js/factory_production_settings/interactions.js",
        "/assets/almdina_erp/js/factory_production_settings/dialogs.js",
        "/assets/almdina_erp/js/factory_production_settings/whatsapp_panel.js",
        "/assets/almdina_erp/js/factory_production_settings/backup_panel.js",
        "/assets/almdina_erp/js/factory_production_settings/controller.js",
    ]);
    const STYLESHEET = "/assets/almdina_erp/css/factory_production_settings.css";

    frappe.ui.make_app_page({
        parent: wrapper,
        title: translate("Factory settings"),
        single_column: true,
    });
    const $main = $(wrapper).find(".layout-main-section");
    const ui = window.AlmdinaUi;

    function paintState(kind, title, message) {
        const body = ui && typeof ui.state === "function"
            ? ui.state({ kind, title, message })
            : `<div class="alm-state alm-state--${kind}" role="${kind === "error" ? "alert" : "status"}"><strong class="alm-state__title">${frappe.utils.escape_html(title || "")}</strong>${message ? `<span class="alm-state__message">${frappe.utils.escape_html(String(message))}</span>` : ""}</div>`;
        $main.html(`<div class="almdina-ui">${body}</div>`);
    }

    paintState(
        "loading",
        translate("Loading factory settings"),
        translate("Preparing current values and permissions...")
    );

    function showBootstrapError(error) {
        const fallback = translate("Could not load factory settings.");
        const frontend = window.AlmdinaFrontend;
        const message = frontend && typeof frontend.errorMessage === "function"
            ? frontend.errorMessage(error, fallback)
            : String((error && error.message) || fallback);
        paintState("error", fallback, message);
        frappe.show_alert({ message, indicator: "red" }, 7);
    }

    function resolveCore() {
        const frontend = window.AlmdinaFrontend;
        const lifecycle = window.AlmdinaPageRevisit;
        if (!frontend || typeof frontend.ensureStylesheet !== "function") {
            throw new Error("Almdina frontend foundation did not initialize");
        }
        if (!lifecycle || typeof lifecycle.bindActivationLifecycle !== "function") {
            throw new Error("Almdina page lifecycle did not initialize");
        }
        return frontend;
    }

    function ensureCore() {
        const frontend = window.AlmdinaFrontend;
        const assets = [];
        if (!frontend || typeof frontend.ensureStylesheet !== "function") assets.push(FOUNDATION);
        if (!window.AlmdinaPageRevisit || typeof window.AlmdinaPageRevisit.bindActivationLifecycle !== "function") {
            assets.push(PAGE_LIFECYCLE);
        }
        if (!assets.length) return Promise.resolve(resolveCore());
        const pending = frontend && typeof frontend.requireAssets === "function"
            ? frontend.requireAssets(assets)
            : frappe.require(assets);
        return Promise.resolve(pending).then(resolveCore);
    }

    return ensureCore()
        .then(frontend => {
            // Page scripts can win the race against app-level include evaluation on
            // a cold Desk load. Resolve the shared foundation first, then keep the
            // existing batched feature-module and stylesheet ownership unchanged.
            const moduleLoad = typeof frontend.requireAssets === "function"
                ? frontend.requireAssets(MODULES)
                : Promise.resolve(frappe.require(MODULES));
            const styleLoad = frontend.ensureStylesheet(STYLESHEET, {
                id: "almdina-production-settings-style",
            });
            return Promise.all([moduleLoad, styleLoad]);
        })
        .then(() => {
            const controller = window.AlmdinaFactoryProductionSettingsController;
            if (!controller || typeof controller.mount !== "function") {
                throw new Error("Production Settings controller did not initialize");
            }
            return controller.mount(wrapper);
        })
        .catch(showBootstrapError);
};
