(() => {
    "use strict";

    function has_role(role) {
        return (frappe.user_roles || []).includes("System Manager") || (frappe.user_roles || []).includes(role);
    }

    function can_operate(frm) {
        if (has_role("Production Manager")) return true;
        if (frm.doc.stage_type === "Cutting") return has_role("Cutting Operator");
        if (frm.doc.stage_type === "Edge Banding") return has_role("Edge Operator");
        return false;
    }

    function invoke(frm, method, args = {}) {
        return frappe.call({
            method: `almdina_erp.almdina_erp.services.production_service.${method}`,
            args: { stage_name: frm.doc.name, ...args },
            freeze: true,
            freeze_message: __("Processing..."),
        }).then(() => frm.reload_doc());
    }

    frappe.ui.form.on("Production Stage", {
        refresh(frm) {
            if (frm.is_new() || !can_operate(frm)) return;

            if (frm.doc.status === "Pending") {
                frm.add_custom_button(__("بدء المرحلة"), () => {
                    frappe.confirm(
                        __("سيتم تسجيل وقت البدء والعامل الحالي. هل تريد المتابعة؟"),
                        () => invoke(frm, "start_stage")
                    );
                });
            }

            if (frm.doc.status === "In Progress") {
                frm.add_custom_button(__("إيقاف مؤقت"), () => {
                    frappe.prompt(
                        [{ fieldname: "reason", fieldtype: "Small Text", label: __("سبب التوقف") }],
                        values => invoke(frm, "pause_stage", { reason: values.reason || "" }),
                        __("إيقاف المرحلة مؤقتًا"),
                        __("إيقاف")
                    );
                });

                frm.add_custom_button(__("إنهاء المرحلة"), () => {
                    frappe.prompt(
                        [
                            { fieldname: "completed_qty", fieldtype: "Int", label: __("الكمية المكتملة") },
                            { fieldname: "notes", fieldtype: "Small Text", label: __("ملاحظات") },
                        ],
                        values => invoke(frm, "finish_stage", values),
                        __("إنهاء المرحلة"),
                        __("إنهاء")
                    );
                });
            }

            if (frm.doc.status === "Paused") {
                frm.add_custom_button(__("استئناف"), () => invoke(frm, "resume_stage"));
                frm.add_custom_button(__("إنهاء المرحلة"), () => {
                    frappe.prompt(
                        [
                            { fieldname: "completed_qty", fieldtype: "Int", label: __("الكمية المكتملة") },
                            { fieldname: "notes", fieldtype: "Small Text", label: __("ملاحظات") },
                        ],
                        values => invoke(frm, "finish_stage", values),
                        __("إنهاء المرحلة"),
                        __("إنهاء")
                    );
                });
            }
        },
    });
})();
