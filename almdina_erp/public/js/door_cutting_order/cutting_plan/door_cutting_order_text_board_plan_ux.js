(() => {
    "use strict";

    function validPieces(frm) {
        return (frm.doc.pieces || []).filter(row => (
            Number(row.width_cm || 0) > 0
            && Number(row.length_cm || 0) > 0
            && Number(row.qty || 0) > 0
        ));
    }

    function translate(message) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") return locale.translate(message);
        if (typeof __ === "function") return __(message);
        return String(message == null ? "" : message);
    }

    function validatePlanInputs(frm) {
        if (!String(frm.doc.board_description || "").trim()) {
            frappe.msgprint(translate("Enter the board item first, for example: MDF white 18 mm."));
            return false;
        }
        if (Number(frm.doc.board_length_cm || 0) <= 0 || Number(frm.doc.board_width_cm || 0) <= 0) {
            frappe.msgprint(translate("Enter a board length and width greater than zero before calculating the cutting plan."));
            return false;
        }
        if (!validPieces(frm).length) {
            frappe.msgprint(translate("Enter at least one valid measurement before calculating the cutting plan."));
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
