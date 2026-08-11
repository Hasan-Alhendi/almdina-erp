(() => {
    "use strict";

    const STYLE_ID = "almdina-door-drawing-v3-css";
    const STYLE_HREF = "/assets/almdina_erp/css/door_drawing_v3.css";
    const SCRIPTS = Object.freeze([
        "/assets/almdina_erp/js/door_drawing_v3/domain/geometry.js",
        "/assets/almdina_erp/js/door_drawing_v3/domain/document.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/history.js",
        "/assets/almdina_erp/js/door_drawing_v3/infrastructure/persistence_adapter.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/editor.js",
    ]);

    function ensureStyle() {
        if (document.getElementById(STYLE_ID)) return;
        const link = document.createElement("link");
        link.id = STYLE_ID;
        link.rel = "stylesheet";
        link.href = STYLE_HREF;
        document.head.appendChild(link);
    }

    function scriptLoaded(src) {
        return Boolean(document.querySelector(`script[data-door-drawing-v3="${src}"]`));
    }

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            if (scriptLoaded(src)) {
                resolve();
                return;
            }
            const script = document.createElement("script");
            script.src = src;
            script.async = false;
            script.dataset.doorDrawingV3 = src;
            script.onload = resolve;
            script.onerror = () => reject(new Error(`Failed to load Door Drawing V3 module: ${src}`));
            document.head.appendChild(script);
        });
    }

    function boot() {
        ensureStyle();
        if (window.__almdinaDoorDrawingV3BootPromise) return window.__almdinaDoorDrawingV3BootPromise;
        window.__almdinaDoorDrawingV3BootPromise = SCRIPTS.reduce(
            (promise, src) => promise.then(() => loadScript(src)),
            Promise.resolve()
        ).catch(error => {
            window.__almdinaDoorDrawingV3BootPromise = null;
            console.error("Door Drawing V3 bootstrap failed", error);
            throw error;
        });
        return window.__almdinaDoorDrawingV3BootPromise;
    }

    function editor() {
        const instance = window.AlmdinaDoorDrawingV3 && window.AlmdinaDoorDrawingV3.Editor;
        if (!instance) throw new Error("Door Drawing V3 editor is not ready");
        return instance;
    }

    function open(frm, row, options = {}) {
        return boot()
            .then(() => editor().open(frm, row, options))
            .catch(error => {
                console.error(error);
                if (window.frappe) frappe.msgprint("تعذر تحميل محرر رسم الدرفة الجديد. أعد تحميل الصفحة ثم حاول مرة أخرى.");
                return null;
            });
    }

    function view(frm, row) {
        return open(frm, row, { readOnly: true });
    }

    function parseDrawing(raw) {
        try {
            const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
            const document = parsed && parsed.meta && parsed.meta.door_drawing_v3;
            return document && Array.isArray(document.objects) ? document.objects : [];
        } catch (error) {
            return [];
        }
    }

    // The previous editor accumulated multiple wrapper integrations. They remain
    // on old deployments for cache compatibility, but V3 is the sole runtime
    // editor and intentionally opts out of every legacy wrapper.
    const facade = {
        open,
        view,
        parseDrawing,
        __doorDrawingV3: true,
        __referenceImageIntegrated: true,
        __smartTemplatePaletteIntegrated: true,
        __templateSilhouettePreviewIntegrated: true,
        __smartTemplateEdgesIntegrated: true,
        __smartEdgeFeaturesIntegrated: true,
        __exactLineIntegrated: true,
        __exactLineInspectorIntegrated: true,
        __exactArcIntegrated: true,
        __exactSegmentDimensionsIntegrated: true,
        __exactShapeChainIntegrated: true,
        __drawingWorkspaceIntegrated: true,
        __figmaEditorIntegrated: true,
        __figmaGenericHandlesIntegrated: true,
        __doorDrawingV2ShellIntegrated: true,
        __doorDrawingV2SelectionIntegrated: true,
        __doorDrawingV2LineUXIntegrated: true,
        __doorDrawingV2FigmaExactIntegrated: true,
    };

    window.AlmdinaSpecialShapeEditor = Object.freeze(facade);
    window.AlmdinaDoorDrawingV3Bootstrap = Object.freeze({ SCRIPTS, boot });

    // Prevent the retired V2 bootstrap from mounting after the V3 entry point.
    window.AlmdinaDoorDrawingV2Bootstrap = Object.freeze({
        SCRIPTS: Object.freeze([]),
        boot: () => Promise.resolve(),
    });
})();
