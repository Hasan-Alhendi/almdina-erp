(() => {
    "use strict";
    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions; if (!permissions) return false;
        return typeof permissions.canDocument === "function" ? Boolean(permissions.canDocument(frm, capability)) : typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }
    async function persistedRow(frm, row, readOnly) {
        if (!frm || !row) return null; const local = Boolean(frm.is_new && frm.is_new()) || Boolean(row.__islocal); const dirty = Boolean(frm.is_dirty && frm.is_dirty());
        if ((local || dirty) && !readOnly) { const idx = Number(row.idx || row.piece_no || 0); await frm.save(); return (frm.doc.pieces || []).find(candidate => Number(candidate.idx || candidate.piece_no || 0) === idx) || row; }
        if (local) { frappe.msgprint("احفظ الطلب أولًا قبل فتح التوثيق."); return null; } return row;
    }
    async function open(frm, row, options = {}) {
        let readOnly = Boolean(options.readOnly); if (!readOnly && !can(frm, "edit_special_drawing")) { if (can(frm, "view_drawing_workspace")) readOnly = true; else { frappe.msgprint("ليس لديك صلاحية فتح توثيق الدرفة الخاصة."); return null; } }
        try { const saved = await persistedRow(frm, row, readOnly); if (!saved) return null; frappe.set_route("door-drawing", frm.doc.name, saved.name); return Object.freeze({ orderName: frm.doc.name, pieceName: saved.name, readOnly }); }
        catch (error) { console.error("Failed to open special-shape documentation", error); frappe.msgprint("تعذر فتح التوثيق. احفظ الطلب ثم حاول مرة أخرى."); return null; }
    }
    function parseDocumentation(raw) { if (!raw) return null; try { const value = typeof raw === "string" ? JSON.parse(raw) : raw; return value && value.schema === "almdina.special-shape-documentation" && Number(value.version) === 1 ? value : null; } catch (error) { return null; } }
    const facade = { open, view: (frm, row) => open(frm, row, { readOnly: true }), parseDocumentation, __documentationOnly: true, __manufacturingGeometrySeparated: true };
    window.AlmdinaSpecialShapeEditor = Object.freeze(facade);
})();
