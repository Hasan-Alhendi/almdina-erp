(() => {
    "use strict";

    const PAGE_ROUTE = "board-editor";
    const STYLE = "/assets/almdina_erp/css/board_editor.css?v=33";
    const ASSET_ROOT = "/assets/almdina_erp/js/board_editor";
    const PREREQUISITES = Object.freeze([
        "/assets/almdina_erp/js/almdina_ui.js",
        "/assets/almdina_erp/js/frontend_foundation.js",
    ]);
    const MODULES = Object.freeze([
        `${ASSET_ROOT}/api.js?v=19`,
        `${ASSET_ROOT}/history.js?v=18`,
        `${ASSET_ROOT}/session_document.js?v=21`,
        `${ASSET_ROOT}/distribution.js?v=18`,
        `${ASSET_ROOT}/move_geometry.js?v=19`,
        `${ASSET_ROOT}/snap_geometry.js?v=18`,
        `${ASSET_ROOT}/rotation_geometry.js?v=19`,
        `${ASSET_ROOT}/transform_geometry.js?v=2`,
        `${ASSET_ROOT}/measure_geometry.js?v=1`,
        `${ASSET_ROOT}/position_geometry.js?v=2`,
        `${ASSET_ROOT}/move_interaction.js?v=20`,
        `${ASSET_ROOT}/rotation_interaction.js?v=19`,
        `${ASSET_ROOT}/measure_interaction.js?v=4`,
        "/assets/almdina_erp/js/door_cutting_order/cutting_plan/door_cutting_order_edge_display.js?v=18",
        "/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js?v=18",
        `${ASSET_ROOT}/plan_display_style.js?v=18`,
        `${ASSET_ROOT}/plan_edge_marks.js?v=18`,
        `${ASSET_ROOT}/store.js?v=20`,
        `${ASSET_ROOT}/canvas_renderer.js?v=33`,
        `${ASSET_ROOT}/sidebar_renderer.js?v=18`,
        `${ASSET_ROOT}/controller.js?v=30`,
    ]);

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

    // Frappe resolves workspace sidebars by route entity. board-editor/order/plan
    // uses the order id as entity, which is not a sidebar link_to, so a cold open
    // leaves .sidebar-items empty while the dark shell and user footer remain.
    // Reuse Frappe's module owner; do not invent a second navigation list.
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

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.ensureDeskNavigationSidebar = ensureDeskNavigationSidebar;
    window.AlmdinaBoardEditor.pageModule = pageModule;

    function scaffold(wrapper) {
        if (wrapper.querySelector(".layout-main-section")) return;
        frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Board layout editor"),
            single_column: true,
        });
        if (!wrapper.querySelector(".layout-main-section")) {
            throw new Error("Board editor page scaffold is unavailable");
        }
    }

    function requireAsset(asset) {
        const raw = String(asset || "");
        const splitAt = raw.indexOf("?");
        const path = splitAt === -1 ? raw : raw.slice(0, splitAt);
        // AssetManager.extn() treats the query string as the file extension.
        // `api.js?v=2` becomes handler key "v=2", so frappe.require throws
        // TypeError: handler is not a function before any script request.
        // Keep the cache token on the request URL and pass a clean path.
        if (splitAt === -1) return frappe.require(path);
        const url = new URL(raw, window.location.origin).toString();
        return frappe.assets.load_asset(path, url);
    }

    function ensureStyle() {
        const frontend = window.AlmdinaFrontend;
        return frontend && typeof frontend.ensureStylesheet === "function"
            ? frontend.ensureStylesheet(STYLE, { id: "almdina-board-editor-css" })
            : requireAsset(STYLE);
    }

    function loadCornerGeometry(asset) {
        if (window.AlmdinaClippedCornerGeometry) return Promise.resolve();
        const form = frappe.ui && frappe.ui.form;
        const previous = form && form.on;
        if (form && typeof previous === "function") {
            form.on = function cornerGeometryLoadGuard(doctype) {
                if (doctype === "Door Cutting Order") return undefined;
                return previous.apply(this, arguments);
            };
        }
        return requireAsset(asset).finally(() => {
            if (form && previous) form.on = previous;
        });
    }

    function loadModules() {
        return Promise.all([...PREREQUISITES, ...MODULES].map((asset) => (
            String(asset).includes("door_cutting_order_clipped_corner_ux.js")
                ? loadCornerGeometry(asset)
                : requireAsset(asset)
        )));
    }

    function bootstrap(wrapper) {
        scaffold(wrapper);
        if (wrapper.__almdinaBoardEditorBoot) return wrapper.__almdinaBoardEditorBoot;
        wrapper.__almdinaBoardEditorBoot = Promise.all([ensureStyle(), loadModules()]).catch((error) => {
            wrapper.__almdinaBoardEditorBoot = null;
            throw error;
        });
        return wrapper.__almdinaBoardEditorBoot;
    }

    function controller(wrapper) {
        return bootstrap(wrapper).then(() => {
            if (wrapper.__almdinaBoardEditorController) {
                return wrapper.__almdinaBoardEditorController;
            }
            const factory = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.WorkspaceController;
            if (!factory) throw new Error("Board editor workspace did not initialize");
            wrapper.__almdinaBoardEditorController = factory.mount(wrapper);
            return wrapper.__almdinaBoardEditorController;
        });
    }

    function route() {
        const value = frappe.get_route();
        return {
            orderName: String(value[1] || "").trim(),
            planName: String(value[2] || "").trim(),
            applySavedDraft: String(value[3] || "") !== "source",
        };
    }

    function fail(wrapper, error, stage) {
        const phase = stage || "bootstrap";
        console.error(`Board editor bootstrap failed during ${phase}`, error);
        scaffold(wrapper);
        wrapper.querySelector(".layout-main-section").innerHTML =
            `<div class="abe-state is-error">${frappe.utils.escape_html(__("Could not load the board editor. Reload the page and try again."))}</div>`;
    }

    frappe.pages[PAGE_ROUTE].on_page_load = (wrapper) => {
        scaffold(wrapper);
        $(wrapper).off("hide.abeBoardEditor").on("hide.abeBoardEditor", () => {
            const active = wrapper.__almdinaBoardEditorController;
            if (active) active.suspend();
        });
        controller(wrapper).catch((error) => fail(wrapper, error, "page-load"));
    };

    frappe.pages[PAGE_ROUTE].on_page_show = (wrapper) => {
        ensureDeskNavigationSidebar();
        controller(wrapper)
            .then((active) => {
                ensureDeskNavigationSidebar();
                const context = route();
                if (!context.orderName || !context.planName) {
                    active.showRouteError(
                        __("Open the board editor from a cutting plan tab on the order.")
                    );
                } else {
                    active.open(context);
                }
            })
            .catch((error) => fail(wrapper, error, "page-show"));
    };
})();
