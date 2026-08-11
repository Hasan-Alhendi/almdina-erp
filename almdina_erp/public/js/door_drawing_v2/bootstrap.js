(() => {
    "use strict";

    const SCRIPTS = Object.freeze([
        "/assets/almdina_erp/js/door_drawing_v2/domain/precision_policy.js",
        "/assets/almdina_erp/js/door_drawing_v2/domain/geometry_engine.js",
        "/assets/almdina_erp/js/door_drawing_v2/domain/document_model.js",
        "/assets/almdina_erp/js/door_drawing_v2/interaction/workspace_policy.js",
        "/assets/almdina_erp/js/door_drawing_v2/application/selection_manager.js",
        "/assets/almdina_erp/js/door_drawing_v2/application/transform_manager.js",
        "/assets/almdina_erp/js/door_drawing_v2/infrastructure/legacy_adapter.js",
        "/assets/almdina_erp/js/door_drawing_v2/infrastructure/legacy_runtime_bridge.js",
        "/assets/almdina_erp/js/door_drawing_v2/presentation/viewport_model.js",
        "/assets/almdina_erp/js/door_drawing_v2/presentation/editor_shell_ux.js",
        "/assets/almdina_erp/js/door_drawing_v2/presentation/selection_overlay_ux.js",
    ]);

    function alreadyLoaded(src) {
        return Boolean(document.querySelector(`script[data-dco-v2-src="${src}"]`));
    }

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            if (alreadyLoaded(src)) {
                resolve();
                return;
            }
            const script = document.createElement("script");
            script.src = src;
            script.async = false;
            script.dataset.dcoV2Src = src;
            script.onload = () => resolve();
            script.onerror = () => reject(new Error(`Failed to load ${src}`));
            document.head.appendChild(script);
        });
    }

    function boot() {
        if (window.__almdinaDoorDrawingV2BootPromise) return window.__almdinaDoorDrawingV2BootPromise;
        window.__almdinaDoorDrawingV2BootPromise = SCRIPTS.reduce(
            (promise, src) => promise.then(() => loadScript(src)),
            Promise.resolve()
        ).catch(error => {
            window.__almdinaDoorDrawingV2BootPromise = null;
            console.error("Door Drawing V2 bootstrap failed", error);
            throw error;
        });
        return window.__almdinaDoorDrawingV2BootPromise;
    }

    window.AlmdinaDoorDrawingV2Bootstrap = Object.freeze({ SCRIPTS, boot });
    boot();
})();
