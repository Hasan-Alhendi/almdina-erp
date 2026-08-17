(() => {
    "use strict";

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

    function loaded(src) {
        return Boolean(document.querySelector(`script[data-door-drawing-v4="${src}"]`));
    }

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            if (loaded(src)) return resolve();
            const script = document.createElement("script");
            script.src = src;
            script.async = false;
            script.dataset.doorDrawingV4 = src;
            script.onload = resolve;
            script.onerror = () => reject(new Error(`Failed to load Door Drawing V4 module: ${src}`));
            document.head.appendChild(script);
        });
    }

    function boot() {
        ensureStyles();
        if (window.__almdinaDoorDrawingV4BootPromise) return window.__almdinaDoorDrawingV4BootPromise;
        window.__almdinaDoorDrawingV4BootPromise = SCRIPTS.reduce((promise, src) => promise.then(() => loadScript(src)), Promise.resolve()).catch(error => {
            window.__almdinaDoorDrawingV4BootPromise = null;
            console.error("Door Drawing V4 bootstrap failed", error);
            throw error;
        });
        return window.__almdinaDoorDrawingV4BootPromise;
    }

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        return typeof permissions.canDocument === "function"
            ? Boolean(permissions.canDocument(frm, capability))
            : typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    async function persistedRow(frm, row, readOnly) {
        if (!frm || !row) return null;
        const isLocal = Boolean(frm.is_new && frm.is_new()) || Boolean(row.__islocal);
        const isDirty = Boolean(frm.is_dirty && frm.is_dirty());
        if ((isLocal || isDirty) && !readOnly) {
            const idx = Number(row.idx || row.piece_no || 0);
            await frm.save();
            return (frm.doc.pieces || []).find(candidate => Number(candidate.idx || candidate.piece_no || 0) === idx) || row;
        }
        if (isLocal) {
            if (window.frappe) frappe.msgprint("احفظ الطلب أولًا قبل فتح الرسم بوضع العرض فقط.");
            return null;
        }
        return row;
    }

    async function open(frm, row, options = {}) {
        let readOnly = Boolean(options && options.readOnly);
        if (!readOnly && !can(frm, "edit_special_drawing")) {
            if (can(frm, "view_drawing_workspace")) readOnly = true;
            else {
                if (window.frappe) frappe.msgprint("ليس لديك صلاحية فتح مساحة رسم الدرفة الخاصة.");
                return null;
            }
        }
        try {
            const savedRow = await persistedRow(frm, row, readOnly);
            if (!savedRow) return null;
            if (!frm.doc.name || !savedRow.name) throw new Error("Saved order and piece identifiers are required");
            frappe.set_route("door-drawing", frm.doc.name, savedRow.name);
            return Object.freeze({ orderName: frm.doc.name, pieceName: savedRow.name, readOnly });
        } catch (error) {
            console.error("Failed to open professional door drawing workspace", error);
            if (window.frappe) frappe.msgprint("تعذر فتح مساحة الرسم. احفظ الطلب ثم حاول مرة أخرى.");
            return null;
        }
    }

    function view(frm, row) { return open(frm, row, { readOnly: true }); }
    function parseJson(raw) {
        if (!raw) return null;
        if (typeof raw === "object") return raw;
        try { return JSON.parse(String(raw)); } catch (error) { return null; }
    }
    function parseDrawing(raw) {
        const document = parseJson(raw);
        if (!document || document.schema !== "almdina.door-drawing" || Number(document.version) !== 4) return [];
        const nodes = new Map((Array.isArray(document.nodes) ? document.nodes : []).map(node => [String(node.id), node]));
        return (Array.isArray(document.segments) ? document.segments : []).map(segment => {
            const start = nodes.get(String(segment.startNodeId));
            const end = nodes.get(String(segment.endNodeId));
            if (!start || !end) return null;
            return Object.freeze({
                id: String(segment.id),
                type: "line",
                start: Object.freeze({ xMm: Number(start.xMm), yMm: Number(start.yMm) }),
                end: Object.freeze({ xMm: Number(end.xMm), yMm: Number(end.yMm) }),
            });
        }).filter(Boolean);
    }

    const facade = {
        open, view, parseDrawing,
        __doorDrawingV4: true,
        __canonicalMmGeometry: true,
        __sharedNodeTopology: true,
        __singleInteractionOwner: true,
        __screenSpaceSnapTolerance: true,
        __highDpiCanvas: true,
        __smartPenPointToPoint: true,
        __readOnlyMutationBoundary: true,
        __semanticUndoRedo: true,
        __nodeEditing: true,
        __manufacturingProjection: true,
        __segmentDimensions: true,
        __constraintFoundation: true,
        __transactionalConstraintSolver: true,
        __drivingDimensions: true,
        __standaloneProfessionalWorkspace: true,
    };

    window.AlmdinaSpecialShapeEditor = Object.freeze(facade);
    window.AlmdinaDoorDrawingV4Bootstrap = Object.freeze({ STYLE_LINKS, SCRIPTS, boot });
})();
