(() => {
    "use strict";
    function can(frm, capability) {
        const permissions = window.AlmdinaPermissions; if (!permissions) return false;
        return typeof permissions.canDocument === "function" ? Boolean(permissions.canDocument(frm, capability)) : typeof permissions.can === "function" && Boolean(permissions.can(capability));
    }
    function blankDimension(value) {
        const result = Number(String(value ?? "").replace(",", "."));
        return Number.isFinite(result) ? result : 0;
    }
    function hasBlankDimensions(row) {
        return Boolean(row) && blankDimension(row.width_cm) > 0 && blankDimension(row.length_cm) > 0;
    }
    async function persistedRow(frm, row, readOnly) {
        if (!frm || !row) return null; const local = Boolean(frm.is_new && frm.is_new()) || Boolean(row.__islocal); const dirty = Boolean(frm.is_dirty && frm.is_dirty());
        if ((local || dirty) && !readOnly) { const idx = Number(row.idx || row.piece_no || 0); await frm.save(); return (frm.doc.pieces || []).find(candidate => Number(candidate.idx || candidate.piece_no || 0) === idx) || row; }
        if (local) { frappe.msgprint("احفظ الطلب أولًا قبل فتح التوثيق."); return null; } return row;
    }
    function documentationUrl(orderName, pieceName) {
        if (frappe.router && typeof frappe.router.make_url === "function") return frappe.router.make_url(["door-drawing", orderName, pieceName]);
        return `/desk/door-drawing/${encodeURIComponent(orderName)}/${encodeURIComponent(pieceName)}`;
    }
    function closePopup(popup) { if (popup && typeof popup.close === "function") popup.close(); }
    async function open(frm, row, options = {}) {
        if (!hasBlankDimensions(row)) {
            frappe.msgprint({ title: "أدخل المقاس أولًا", message: "أدخل عرض الدرفة وطولها أولًا، ثم افتح توثيق الشكل.", indicator: "orange" });
            return null;
        }
        let readOnly = Boolean(options.readOnly); if (!readOnly && !can(frm, "edit_special_drawing")) { if (can(frm, "view_drawing_workspace")) readOnly = true; else { frappe.msgprint("ليس لديك صلاحية فتح توثيق الدرفة الخاصة."); return null; } }
        const popup = window.open("about:blank", "_blank");
        try {
            const saved = await persistedRow(frm, row, readOnly);
            if (!saved) { closePopup(popup); return null; }
            if (popup) popup.location.replace(documentationUrl(frm.doc.name, saved.name));
            else frappe.set_route("door-drawing", frm.doc.name, saved.name);
            return Object.freeze({ orderName: frm.doc.name, pieceName: saved.name, readOnly });
        }
        catch (error) { closePopup(popup); console.error("Failed to open special-shape documentation", error); frappe.msgprint("تعذر فتح التوثيق. احفظ الطلب ثم حاول مرة أخرى."); return null; }
    }
    function parseDocumentation(raw) { if (!raw) return null; try { const value = typeof raw === "string" ? JSON.parse(raw) : raw; return value && value.schema === "almdina.special-shape-documentation" && Number(value.version) === 1 ? value : null; } catch (error) { return null; } }
    const facade = { open, view: (frm, row) => open(frm, row, { readOnly: true }), parseDocumentation, __documentationOnly: true, __manufacturingGeometrySeparated: true };
    window.AlmdinaSpecialShapeEditor = Object.freeze(facade);
})();
