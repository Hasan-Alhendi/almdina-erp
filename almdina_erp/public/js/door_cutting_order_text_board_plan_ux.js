(() => {
    "use strict";

    const EDITABLE_STATUSES = new Set(["Draft", "Pending Review", "Rejected"]);
    const PLAN_BUTTONS = [
        ".dco-recalculate-plan",
        ".dco-auto-pro-plan",
        ".dco-deep-plan",
        ".dco-optimal-plan",
    ].join(",");

    function editable(frm) {
        if (window.frappe && frappe.almdina && frappe.almdina.orderCanEdit) {
            return frappe.almdina.orderCanEdit(frm);
        }
        return frm.doc.docstatus === 0 && EDITABLE_STATUSES.has(frm.doc.status || "Draft");
    }

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

    async function recalculate(frm) {
        if (!editable(frm)) {
            frappe.msgprint("لا يمكن إعادة حساب طلب معتمد أو دخل الإنتاج. يجب الحفاظ على الخطة المعتمدة كنسخة تاريخية ثابتة.");
            return;
        }
        if (!validatePlanInputs(frm) || frm._dcoTextBoardPlanBusy) return;

        frm._dcoTextBoardPlanBusy = true;
        const buttons = $(frm.wrapper).find(PLAN_BUTTONS);
        buttons.prop("disabled", true);

        const mode = frm.doc.packing_mode || "Auto Pro";
        const message = mode === "Optimal Search"
            ? "جاري البحث الأمثل عن أقل عدد ألواح..."
            : mode === "Deep Search"
                ? "جاري البحث المعمق عن أفضل توزيع..."
                : "جاري إعادة حساب أفضل توزيع للقطع...";

        frappe.dom.freeze(message);
        try {
            await frm.save();
            frappe.show_alert({ message: "تم تحديث خطة القص والنتائج", indicator: "green" }, 3);
        } catch (error) {
            console.error("Failed to recalculate cutting plan", error);
            throw error;
        } finally {
            frm._dcoTextBoardPlanBusy = false;
            frappe.dom.unfreeze();
            requestAnimationFrame(() => bindPlanButtons(frm));
        }
    }

    function bindPlanButtons(frm) {
        const field = frm.fields_dict && frm.fields_dict.plan_control_actions;
        if (!field || !field.$wrapper) return;

        const buttons = field.$wrapper.find(PLAN_BUTTONS);
        if (!buttons.length) return;

        // door_cutting_order_plan_ux.js still owns rendering. This free-text layer
        // replaces only its obsolete Item-based click validation.
        buttons.off("click");
        buttons.prop("disabled", !editable(frm));

        field.$wrapper.find(".dco-recalculate-plan").on("click.dcoTextBoardPlan", () => recalculate(frm));
        field.$wrapper.find(".dco-auto-pro-plan").on("click.dcoTextBoardPlan", async () => {
            if (!editable(frm)) return;
            await frm.set_value("packing_mode", "Auto Pro");
            await recalculate(frm);
        });
        field.$wrapper.find(".dco-deep-plan").on("click.dcoTextBoardPlan", async () => {
            if (!editable(frm)) return;
            await frm.set_value("packing_mode", "Deep Search");
            await recalculate(frm);
        });
        field.$wrapper.find(".dco-optimal-plan").on("click.dcoTextBoardPlan", async () => {
            if (!editable(frm)) return;
            await frm.set_value("packing_mode", "Optimal Search");
            await recalculate(frm);
        });
    }

    function refresh(frm) {
        bindPlanButtons(frm);
        requestAnimationFrame(() => bindPlanButtons(frm));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
        packing_mode(frm) { refresh(frm); },
        board_description(frm) { refresh(frm); },
        board_length_cm(frm) { refresh(frm); },
        board_width_cm(frm) { refresh(frm); },
    });
})();
