(() => {
    "use strict";

    const PAGE_ROUTE = "door-drawing";
    const BOOTSTRAP_SRC = "/assets/almdina_erp/js/door_drawing_v4/bootstrap.js";
    const WORKSPACE_STYLES = Object.freeze([
        Object.freeze({ id: "almdina-door-drawing-workspace-css", href: "/assets/almdina_erp/css/door_drawing_workspace.css" }),
        Object.freeze({ id: "almdina-door-drawing-reference-css", href: "/assets/almdina_erp/css/door_drawing_reference.css" }),
    ]);
    const WORKSPACE_SCRIPTS = Object.freeze([
        "/assets/almdina_erp/js/door_drawing_v4/reference/domain.js",
        "/assets/almdina_erp/js/door_drawing_v4/reference/device_source.js",
        "/assets/almdina_erp/js/door_drawing_v4/reference/scanner_bridge.js",
        "/assets/almdina_erp/js/door_drawing_v4/reference/cropper.js",
        "/assets/almdina_erp/js/door_drawing_v4/reference/reference_view.js",
        "/assets/almdina_erp/js/door_drawing_v4/workspace/api.js",
        "/assets/almdina_erp/js/door_drawing_v4/workspace/shell.js",
        "/assets/almdina_erp/js/door_drawing_v4/workspace/reference_controller.js",
        "/assets/almdina_erp/js/door_drawing_v4/workspace/session_controller.js",
    ]);

    function ensureStyles() {
        WORKSPACE_STYLES.forEach(item => {
            if (document.getElementById(item.id)) return;
            const link = document.createElement("link");
            link.id = item.id;
            link.rel = "stylesheet";
            link.href = item.href;
            document.head.appendChild(link);
        });
    }

    function scriptNode(src) {
        return document.querySelector(`script[data-door-drawing-workspace-asset="${src}"]`);
    }

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const existing = scriptNode(src);
            if (existing) {
                if (existing.dataset.loaded === "1") resolve();
                else {
                    existing.addEventListener("load", resolve, { once: true });
                    existing.addEventListener("error", () => reject(new Error(`Failed to load drawing workspace asset: ${src}`)), { once: true });
                }
                return;
            }
            const script = document.createElement("script");
            script.src = src;
            script.async = false;
            script.dataset.doorDrawingWorkspaceAsset = src;
            script.addEventListener("load", () => {
                script.dataset.loaded = "1";
                resolve();
            }, { once: true });
            script.addEventListener("error", () => reject(new Error(`Failed to load drawing workspace asset: ${src}`)), { once: true });
            document.head.appendChild(script);
        });
    }

    function ensureBootstrap() {
        if (window.AlmdinaDoorDrawingV4Bootstrap && typeof window.AlmdinaDoorDrawingV4Bootstrap.boot === "function") {
            return Promise.resolve(window.AlmdinaDoorDrawingV4Bootstrap);
        }
        return loadScript(BOOTSTRAP_SRC).then(() => {
            const bootstrap = window.AlmdinaDoorDrawingV4Bootstrap;
            if (!bootstrap || typeof bootstrap.boot !== "function") {
                throw new Error("Door Drawing V4 bootstrap is unavailable");
            }
            return bootstrap;
        });
    }

    function bootRuntime() {
        if (window.__almdinaStandaloneDrawingWorkspaceBoot) {
            return window.__almdinaStandaloneDrawingWorkspaceBoot;
        }
        ensureStyles();
        window.__almdinaStandaloneDrawingWorkspaceBoot = ensureBootstrap()
            .then(bootstrap => bootstrap.boot())
            .then(() => WORKSPACE_SCRIPTS.reduce(
                (promise, src) => promise.then(() => loadScript(src)),
                Promise.resolve()
            ))
            .catch(error => {
                window.__almdinaStandaloneDrawingWorkspaceBoot = null;
                throw error;
            });
        return window.__almdinaStandaloneDrawingWorkspaceBoot;
    }

    function routeContext() {
        const route = frappe.get_route ? frappe.get_route() : [];
        return {
            orderName: route[1] || "",
            pieceName: route[2] || "",
            mode: route[3] === "view" ? "view" : "edit",
        };
    }

    function createPageController(wrapper) {
        frappe.ui.make_app_page({
            parent: wrapper,
            title: __("Special Door Drawing"),
            single_column: true,
        });
        wrapper.classList.add("ald-door-drawing-page");
        const body = $(wrapper).find(".layout-main-section").get(0);
        if (!body) throw new Error("Standalone door drawing page body is unavailable");
        body.innerHTML = '<div data-door-drawing-page-mount style="min-height:520px;display:grid;place-items:center;color:#64748b">يتم تحميل مساحة الرسم…</div>';
        const mount = body.querySelector("[data-door-drawing-page-mount]");

        let session = null;
        let loadSequence = 0;

        async function ensureSession() {
            if (session) return session;
            await bootRuntime();
            const factory = window.AlmdinaDoorDrawingWorkspace && window.AlmdinaDoorDrawingWorkspace.SessionController;
            if (!factory || typeof factory.create !== "function") {
                throw new Error("Door drawing workspace session controller is unavailable");
            }
            session = factory.create({ container: mount });
            return session;
        }

        async function loadRoute() {
            const sequence = ++loadSequence;
            const route = routeContext();
            try {
                const current = await ensureSession();
                if (sequence !== loadSequence || current !== session) return;
                await current.load(route.orderName, route.pieceName, route.mode);
            } catch (error) {
                console.error("Standalone door drawing workspace failed to initialize", error);
                if (sequence !== loadSequence) return;
                mount.innerHTML = '<div style="padding:30px;text-align:center;color:#991b1b">تعذر تحميل مساحة الرسم. أعد تحميل الصفحة ثم حاول مرة أخرى.</div>';
            }
        }

        function hide() {
            loadSequence += 1;
            if (session) {
                try { session.destroy(); } catch (error) { console.warn("Door drawing workspace cleanup failed", error); }
                session = null;
            }
        }

        function beforeUnload(event) {
            if (!session || !session.state().dirty) return;
            event.preventDefault();
            event.returnValue = "";
        }
        window.addEventListener("beforeunload", beforeUnload);

        $(wrapper)
            .off("hide.aldDoorDrawingWorkspace")
            .on("hide.aldDoorDrawingWorkspace", hide);

        return Object.freeze({
            loadRoute,
            hide,
            destroy() {
                hide();
                $(wrapper).off("hide.aldDoorDrawingWorkspace");
                window.removeEventListener("beforeunload", beforeUnload);
            },
        });
    }

    frappe.pages[PAGE_ROUTE].on_page_load = function (wrapper) {
        if (wrapper._almdinaDoorDrawingPageController) return;
        wrapper._almdinaDoorDrawingPageController = createPageController(wrapper);
    };

    frappe.pages[PAGE_ROUTE].on_page_show = function (wrapper) {
        const controller = wrapper._almdinaDoorDrawingPageController;
        if (controller) controller.loadRoute();
    };
})();