(() => {
    "use strict";

    function validPieces(frm) {
        return (frm.doc.pieces || []).filter(row => (
            Number(row.width_cm || 0) > 0
            && Number(row.length_cm || 0) > 0
            && Number(row.qty || 0) > 0
        ));
    }

    function validatePlanInputs(frm) {
        if (!String(frm.doc.board_description || "").trim()) {
            frappe.msgprint("أدخل صنف اللوح أولًا، مثال: MDF أبيض 18 مم.");
            return false;
        }
        if (Number(frm.doc.board_length_cm || 0) <= 0 || Number(frm.doc.board_width_cm || 0) <= 0) {
            frappe.msgprint("أدخل طول اللوح وعرضه بقيم أكبر من الصفر قبل حساب خطة القص.");
            return false;
        }
        if (!validPieces(frm).length) {
            frappe.msgprint("أدخل قياسًا واحدًا صحيحًا على الأقل قبل حساب خطة القص.");
            return false;
        }
        return true;
    }

    async function preparePlanInputs(frm) {
        const boardUX = window.AlmdinaBoardTextUX;
        if (boardUX && typeof boardUX.syncInputs === "function") {
            await boardUX.syncInputs(frm);
        }
        if (!validatePlanInputs(frm)) return false;
        return true;
    }

    // Compatibility/validation layer only. Cutting-plan commands are owned by
    // door_cutting_order_plan_controls_ux.js so permissions, lifecycle checks,
    // and server calls have exactly one browser controller.
    window.AlmdinaTextBoardPlanUX = Object.freeze({
        validPieces,
        validatePlanInputs,
        preparePlanInputs,
    });
})();
