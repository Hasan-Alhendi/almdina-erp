(() => {
    "use strict";

    if (window.AlmdinaDoorDrawingV4Bootstrap && window.AlmdinaDoorDrawingV4Bootstrap.boot) return;

    const STYLE_LINKS = Object.freeze([
        Object.freeze({ id: "almdina-door-drawing-v4-css", href: "/assets/almdina_erp/css/door_drawing_v4.css" }),
    ]);

    const SCRIPTS = Object.freeze([
        "/assets/almdina_erp/js/door_drawing_v4/domain/geometry.js",
        "/assets/almdina_erp/js/door_drawing_v4/domain/document.js",
        "/assets/almdina_erp/js/door_drawing_v4/domain/dimension.js",
        "/assets/almdina_erp/js/door_drawing_v4/domain/constraint.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/geometry_commands.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/dimension_commands.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/constraint_commands.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/constraint_solver.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/constraint_inference.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/driving_dimension_commands.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/manufacturing_projection.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/snap_resolver.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/hit_test.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/command_history.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/tool_state_machine.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/interaction_engine.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/viewport.js",
        "/assets/almdina_erp/js/door_drawing_v4/infrastructure/persistence_adapter.js",
        "/assets/almdina_erp/js/door_drawing_v4/presentation/canvas_renderer.js",
        "/assets/almdina_erp/js/door_drawing_v4/presentation/editor_shell.js",
        "/assets/almdina_erp/js/door_drawing_v4/presentation/editor_controller.js",
        "/assets/almdina_erp/js/door_drawing_v4/presentation/frappe_editor.js",
    ]);

    function ensureStyles() {
        STYLE_LINKS.forEach(item => {
            if (document.getElementById(item.id)) return;
            const link = document.createElement("link");
            link.id = item.id;
            link.rel = "stylesheet";
            link.href = item.href;
            document.head.appendChild(link);
        });
    }

    function scriptNode(src) {
        return document.querySelector(`script[data-door-drawing-v4="${src}"]`);
    }

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const existing = scriptNode(src);
            if (existing) {
                if (existing.dataset.loaded === "1") resolve();
                else {
                    existing.addEventListener("load", resolve, { once: true });
                    existing.addEventListener("error", () => reject(new Error(`Failed to load Door Drawing V4 module: ${src}`)), { once: true });
                }
                return;
            }

            const script = document.createElement("script");
            script.src = src;
            script.async = false;
            script.dataset.doorDrawingV4 = src;
            script.addEventListener("load", () => {
                script.dataset.loaded = "1";
                resolve();
            }, { once: true });
            script.addEventListener("error", () => reject(new Error(`Failed to load Door Drawing V4 module: ${src}`)), { once: true });
            document.head.appendChild(script);
        });
    }

    function boot() {
        ensureStyles();
        if (window.__almdinaDoorDrawingV4BootPromise) return window.__almdinaDoorDrawingV4BootPromise;
        window.__almdinaDoorDrawingV4BootPromise = SCRIPTS.reduce(
            (promise, src) => promise.then(() => loadScript(src)),
            Promise.resolve()
        ).catch(error => {
            window.__almdinaDoorDrawingV4BootPromise = null;
            console.error("Door Drawing V4 bootstrap failed", error);
            throw error;
        });
        return window.__almdinaDoorDrawingV4BootPromise;
    }

    window.AlmdinaDoorDrawingV4Bootstrap = Object.freeze({ STYLE_LINKS, SCRIPTS, boot });
})();
