(() => {
    "use strict";

    const BOOTSTRAP_SRC = "/assets/almdina_erp/js/door_drawing_v4/bootstrap.js";
    const WORKSPACE_ROUTE = "door-drawing";

    function loadBootstrap() {
        if (window.AlmdinaDoorDrawingV4Bootstrap && window.AlmdinaDoorDrawingV4Bootstrap.boot) {
            return Promise.resolve(window.AlmdinaDoorDrawingV4Bootstrap);
        }
        if (window.__almdinaDoorDrawingV4BootstrapPromise) {
            return window.__almdinaDoorDrawingV4BootstrapPromise;
        }

        window.__almdinaDoorDrawingV4BootstrapPromise = new Promise((resolve, reject) => {
            const existing = document.querySelector(`script[data-door-drawing-bootstrap="${BOOTSTRAP_SRC}"]`);
            const finish = () => {
                const bootstrap = window.AlmdinaDoorDrawingV4Bootstrap;
                if (!bootstrap || typeof bootstrap.boot !== "function") {
                    reject(new Error("Door Drawing V4 bootstrap did not initialize"));
                    return;
                }
                resolve(bootstrap);
            };
            if (existing) {
                if (window.AlmdinaDoorDrawingV4Bootstrap) finish();
                else {
                    existing.addEventListener("load", finish, { once: true });
                    existing.addEventListener("error", () => reject(new Error("Failed to load Door Drawing V4 bootstrap")), { once: true });
                }
                return;
            }

            const script = document.createElement("script");
            script.src = BOOTSTRAP_SRC;
            script.async = false;
            script.dataset.doorDrawingBootstrap = BOOTSTRAP_SRC;
            script.addEventListener("load", finish, { once: true });
            script.addEventListener("error", () => reject(new Error("Failed to load Door Drawing V4 bootstrap")), { once: true });
            document.head.appendChild(script);
        }).catch(error => {
            window.__almdinaDoorDrawingV4BootstrapPromise = null;
            throw error;
        });
        return window.__almdinaDoorDrawingV4BootstrapPromise;
    }

    function boot() {
        return loadBootstrap().then(bootstrap => bootstrap.boot());
    }

    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        return typeof permissions.canDocument === "function"
            ? Boolean(permissions.canDocument(frm, capability))
            : typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }

    function formIsDirty(frm) {
        if (!frm) return false;
        if (typeof frm.is_dirty === "function") return Boolean(frm.is_dirty());
        return Boolean(frm.doc && frm.doc.__unsaved);
    }

    function rowIsLocal(row) {
        if (!row || !row.name) return true;
        return Boolean(row.__islocal || String(row.name).startsWith("new-"));
    }

    function resolveSavedRow(frm, originalRow) {
        const rows = (frm.doc && frm.doc.pieces) || [];
        const byName = rows.find(row => row.name && originalRow.name && row.name === originalRow.name);
        if (byName && !rowIsLocal(byName)) return byName;
        const originalIndex = Number(originalRow.idx || originalRow.piece_no || 0);
        const byIndex = rows.find(row => Number(row.idx || row.piece_no || 0) === originalIndex);
        return byIndex && !rowIsLocal(byIndex) ? byIndex : null;
    }

    function ensurePersisted(frm, row) {
        if (!frm || !frm.doc || !row) return Promise.reject(new Error("Door drawing requires a form and piece row"));
        const needsSave = !frm.doc.name || (typeof frm.is_new === "function" && frm.is_new()) || formIsDirty(frm) || rowIsLocal(row);
        if (!needsSave) return Promise.resolve({ orderName: frm.doc.name, row });

        if (window.frappe) {
            frappe.show_alert({ message: "يتم حفظ مسودة الطلب قبل فتح مساحة الرسم…", indicator: "blue" }, 3);
        }
        return Promise.resolve(frm.save()).then(() => {
            const savedRow = resolveSavedRow(frm, row);
            if (!frm.doc.name || !savedRow) {
                throw new Error("Could not resolve persisted special-door row after saving the order");
            }
            return { orderName: frm.doc.name, row: savedRow };
        });
    }

    function navigate(orderName, row, readOnly) {
        if (!window.frappe || typeof frappe.set_route !== "function") {
            throw new Error("Frappe router is required for the standalone drawing workspace");
        }
        frappe.set_route(WORKSPACE_ROUTE, orderName, row.name, readOnly ? "view" : "edit");
        return { orderName, pieceName: row.name, readOnly };
    }

    function open(frm, row, options = {}) {
        if ((row && row.piece_type || "Regular") !== "Special") {
            if (window.frappe) frappe.msgprint("حوّل نوع الدرفة إلى «خاصة» أولًا.");
            return Promise.resolve(null);
        }

        let readOnly = Boolean(options && options.readOnly);
        if (!readOnly && !can(frm, "edit_special_drawing")) {
            if (can(frm, "view_drawing_workspace")) readOnly = true;
            else {
                if (window.frappe) frappe.msgprint("ليس لديك صلاحية فتح مساحة رسم الدرفة الخاصة.");
                return Promise.resolve(null);
            }
        }

        return ensurePersisted(frm, row)
            .then(context => navigate(context.orderName, context.row, readOnly))
            .catch(error => {
                console.error("Failed to open standalone door drawing workspace", error);
                if (window.frappe) frappe.msgprint("تعذر فتح مساحة رسم الدرفة. تأكد من حفظ الطلب ثم حاول مرة أخرى.");
                return null;
            });
    }

    function view(frm, row) {
        return open(frm, row, { readOnly: true });
    }

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
        open,
        view,
        boot,
        parseDrawing,
        workspaceRoute: WORKSPACE_ROUTE,
        __doorDrawingV4: true,
        __standaloneWorkspace: true,
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
    };

    window.AlmdinaSpecialShapeEditor = Object.freeze(facade);
})();
