(() => {
    "use strict";

    const PAGE_ROUTE = "cnc-sheet-settings";
    const STYLE = "/assets/almdina_erp/css/door_cutting_order_operational_files.css?v=19";
    // frappe.require reads the extension before the query string. A "?v="
    // suffix makes the loader throw before the script request is sent.
    const ASSETS = Object.freeze([
        "/assets/almdina_erp/js/almdina_ui.js",
        "/assets/almdina_erp/js/cnc/artcam_machining_ux.js",
        "/assets/almdina_erp/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js",
    ]);

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
                text = text.split(`{${index}}`).join(String(value));
            });
        }
        return text;
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function scaffold(wrapper) {
        if (wrapper.querySelector(".layout-main-section")) return;
        frappe.ui.make_app_page({
            parent: wrapper,
            title: translate("CNC sheet settings"),
            single_column: true,
        });
        if (!wrapper.querySelector(".layout-main-section")) {
            throw new Error("CNC sheet settings page scaffold is unavailable");
        }
    }

    function mainSection(wrapper) {
        return wrapper.querySelector(".layout-main-section");
    }

    function ensureStyle() {
        const frontend = window.AlmdinaFrontend;
        if (frontend && typeof frontend.ensureStylesheet === "function") {
            return frontend.ensureStylesheet(STYLE, { id: "almdina-cnc-sheet-settings-css" });
        }
        return frappe.require(STYLE);
    }

    function loadAssets() {
        return Promise.all(ASSETS.map(asset => frappe.require(asset)));
    }

    function pageModule() {
        const page = window.locals && locals.Page && locals.Page[PAGE_ROUTE];
        return String((page && page.module) || "Almdina ERP").trim() || "Almdina ERP";
    }

    function deskNavItemCount() {
        const root = document.querySelector(".body-sidebar-top .sidebar-items");
        if (!root) return 0;
        return root.querySelectorAll(
            ".sidebar-item-container:not(.section-item), .standard-sidebar-item"
        ).length;
    }

    // Frappe resolves the workspace sidebar from the route entity. This page's
    // entity is the order id, which is not a sidebar link, so a cold open keeps
    // the dark shell and user footer while .sidebar-items stays empty.
    // Reuse the module sidebar owner. Do not build a second navigation list.
    function ensureDeskNavigationSidebar() {
        const sidebar = window.frappe && frappe.app && frappe.app.sidebar;
        if (!sidebar) return { applied: false, reason: "missing-sidebar" };
        const moduleName = pageModule();
        const existing = deskNavItemCount();
        if (
            existing > 0
            && sidebar.sidebar_title
            && String(sidebar.sidebar_title).toLowerCase() === moduleName.toLowerCase()
        ) {
            return { applied: false, reason: "already-populated", count: existing, moduleName };
        }
        if (typeof sidebar.show_sidebar_for_module === "function") {
            sidebar.show_sidebar_for_module(moduleName);
        } else if (typeof sidebar.setup === "function") {
            sidebar.setup(moduleName);
        } else {
            return { applied: false, reason: "no-api", moduleName };
        }
        return { applied: true, reason: "module-sidebar", count: deskNavItemCount(), moduleName };
    }

    window.AlmdinaCncSheetSettings = window.AlmdinaCncSheetSettings || {};
    window.AlmdinaCncSheetSettings.ensureDeskNavigationSidebar = ensureDeskNavigationSidebar;
    window.AlmdinaCncSheetSettings.pageModule = pageModule;

    function routeContext() {
        const value = typeof frappe.get_route === "function" ? frappe.get_route() : [];
        return {
            orderName: String(value[1] || "").trim(),
            sheetNo: String(value[2] || "").trim(),
        };
    }

    function bootMessage(wrapper, message, isError) {
        scaffold(wrapper);
        const main = mainSection(wrapper);
        if (!main) return;
        main.innerHTML = `<div class="dco-cnc-sheet-page" role="${isError ? "alert" : "status"}"><p>${esc(message)}</p></div>`;
    }

    function mount(wrapper) {
        scaffold(wrapper);
        const main = mainSection(wrapper);
        if (!main) throw new Error("CNC sheet settings main section is missing");
        const context = routeContext();
        if (!context.orderName || !context.sheetNo) {
            bootMessage(wrapper, translate("The sheet settings link is incomplete."), true);
            return;
        }
        const ux = window.AlmdinaOperationalFilesUX;
        if (!ux || typeof ux.mountSheetSettingsPage !== "function") {
            throw new Error("AlmdinaOperationalFilesUX.mountSheetSettingsPage is required");
        }
        document.body.classList.add("dco-cnc-sheet-settings-active");
        ux.mountSheetSettingsPage(main, {
            orderName: context.orderName,
            sheetNo: context.sheetNo,
        });
    }

    function bootstrap(wrapper) {
        if (wrapper.__almdinaCncSheetBoot) return wrapper.__almdinaCncSheetBoot;
        bootMessage(wrapper, translate("Loading sheet settings..."), false);
        wrapper.__almdinaCncSheetBoot = Promise.all([ensureStyle(), loadAssets()]).catch(error => {
            wrapper.__almdinaCncSheetBoot = null;
            throw error;
        });
        return wrapper.__almdinaCncSheetBoot;
    }

    frappe.pages[PAGE_ROUTE].on_page_load = function onPageLoad(wrapper) {
        scaffold(wrapper);
        $(wrapper).off("hide.almdinaCncSheet").on("hide.almdinaCncSheet", () => {
            document.body.classList.remove("dco-cnc-sheet-settings-active");
        });
        bootstrap(wrapper).catch(error => {
            console.error("CNC sheet settings bootstrap failed", error);
            bootMessage(wrapper, translate("Sheet settings could not be loaded."), true);
        });
    };

    frappe.pages[PAGE_ROUTE].on_page_show = function onPageShow(wrapper) {
        ensureDeskNavigationSidebar();
        bootstrap(wrapper)
            .then(() => {
                ensureDeskNavigationSidebar();
                mount(wrapper);
            })
            .catch(error => {
                console.error("CNC sheet settings open failed", error);
                bootMessage(wrapper, translate("Sheet settings could not be loaded."), true);
            });
    };
})();
