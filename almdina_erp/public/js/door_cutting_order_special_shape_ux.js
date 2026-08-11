(() => {
    "use strict";

    const STYLE_LINKS = Object.freeze([
        Object.freeze({ id: "almdina-door-drawing-v3-css", href: "/assets/almdina_erp/css/door_drawing_v3.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-precision-css", href: "/assets/almdina_erp/css/door_drawing_v3_precision.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-magnetic-css", href: "/assets/almdina_erp/css/door_drawing_v3_magnetic.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-smart-pen-css", href: "/assets/almdina_erp/css/door_drawing_v3_smart_pen.css" }),
    ]);
    const SCRIPTS = Object.freeze([
        "/assets/almdina_erp/js/door_drawing_v3/domain/geometry.js",
        "/assets/almdina_erp/js/door_drawing_v3/domain/document.js",
        "/assets/almdina_erp/js/door_drawing_v3/domain/smart_path_domain.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/history.js",
        "/assets/almdina_erp/js/door_drawing_v3/infrastructure/persistence_adapter.js",
        "/assets/almdina_erp/js/door_drawing_v3/infrastructure/smart_path_persistence.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/snapping.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/smart_path_snapping.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/move_snap_policy.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/shape_handles.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/precision_input.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/canvas_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/canvas_policy.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/smart_path_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/editor_stage2.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/magnetic_connection.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/smart_pen.js",
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
    function loaded(src) { return Boolean(document.querySelector(`script[data-door-drawing-v3="${src}"]`)); }
    function loadScript(src) { return new Promise((resolve, reject) => { if (loaded(src)) return resolve(); const script = document.createElement("script"); script.src = src; script.async = false; script.dataset.doorDrawingV3 = src; script.onload = resolve; script.onerror = () => reject(new Error(`Failed to load Door Drawing V3 module: ${src}`)); document.head.appendChild(script); }); }
    function boot() {
        ensureStyles();
        if (window.__almdinaDoorDrawingV3BootPromise) return window.__almdinaDoorDrawingV3BootPromise;
        window.__almdinaDoorDrawingV3BootPromise = SCRIPTS.reduce((promise, src) => promise.then(() => loadScript(src)), Promise.resolve()).catch(error => { window.__almdinaDoorDrawingV3BootPromise = null; console.error("Door Drawing V3 bootstrap failed", error); throw error; });
        return window.__almdinaDoorDrawingV3BootPromise;
    }
    function editor() { const instance = window.AlmdinaDoorDrawingV3 && window.AlmdinaDoorDrawingV3.Editor; if (!instance) throw new Error("Door Drawing V3 editor is not ready"); return instance; }
    function open(frm, row, options = {}) { return boot().then(() => editor().open(frm, row, options)).catch(error => { console.error(error); if (window.frappe) frappe.msgprint("تعذر تحميل محرر رسم الدرفة الجديد. أعد تحميل الصفحة ثم حاول مرة أخرى."); return null; }); }
    function view(frm, row) { return open(frm, row, { readOnly: true }); }
    function parseDrawing(raw) { try { const parsed = typeof raw === "string" ? JSON.parse(raw) : raw; const document = parsed && parsed.meta && parsed.meta.door_drawing_v3; return document && Array.isArray(document.objects) ? document.objects : []; } catch (error) { return []; } }

    const facade = {
        open, view, parseDrawing,
        __doorDrawingV3: true,
        __doorDrawingV3Shapes: true,
        __doorDrawingV3Snapping: true,
        __doorDrawingV3Handles: true,
        __doorDrawingV3PrecisionInput: true,
        __doorDrawingV3MagneticConnection: true,
        __doorDrawingV3EasyMoveSnap: true,
        __doorDrawingV3CanvasPolicy: true,
        __doorDrawingV3SmartPen: true,
        __doorDrawingV3SmartPath: true,
        __doorDrawingV3NodeEditing: true,
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
    window.AlmdinaDoorDrawingV3Bootstrap = Object.freeze({ STYLE_LINKS, SCRIPTS, boot });
    window.AlmdinaDoorDrawingV2Bootstrap = Object.freeze({ SCRIPTS: Object.freeze([]), boot: () => Promise.resolve() });
})();
