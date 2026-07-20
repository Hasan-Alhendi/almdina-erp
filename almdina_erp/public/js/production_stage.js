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

    function record_incident(frm) {
        frappe.prompt(
            [
                { fieldname: "piece_label", fieldtype: "Data", label: __("رقم القطعة مثل 2.3"), reqd: 1 },
                {
                    fieldname: "reason",
                    fieldtype: "Select",
                    label: __("السبب"),
                    options: ["Measurement Error", "Cutting Error", "Edge Banding Error", "Damage", "Lost Piece", "Material Defect", "Other"].join("\n"),
                    reqd: 1,
                },
                { fieldname: "description", fieldtype: "Small Text", label: __("وصف الخطأ"), reqd: 1 },
                { fieldname: "requires_replacement", fieldtype: "Check", label: __("تحتاج قطعة تعويضية"), default: 1 },
            ],
            values => {
                frappe.call({
                    method: "almdina_erp.almdina_erp.services.replacement_service.record_incident",
                    args: {
                        order_name: frm.doc.door_cutting_order,
                        production_stage: frm.doc.name,
                        piece_label: values.piece_label,
                        reason: values.reason,
                        description: values.description,
                        requires_replacement: values.requires_replacement,
                    },
                    freeze: true,
                    freeze_message: __("Recording incident..."),
                }).then(r => {
                    const result = r.message || {};
                    let message = `${__("تم تسجيل الخطأ")}: ${result.incident || ""}`;
                    if (result.replacement_piece) {
                        message += `<br>${__("تم إنشاء قطعة تعويضية")}: <b>${result.replacement_piece}</b>`;
                    }
                    frappe.msgprint({ title: __("Production Incident"), indicator: "orange", message });
                    frm.reload_doc();
                });
            },
            __("تسجيل خطأ / قطعة تالفة"),
            __("تسجيل")
        );
    }

    frappe.ui.form.on("Production Stage", {
        refresh(frm) {
            if (frm.is_new() || !can_operate(frm)) return;

            if (["In Progress", "Paused", "Completed"].includes(frm.doc.status) && ["Cutting", "Edge Banding"].includes(frm.doc.stage_type)) {
                frm.add_custom_button(__("تسجيل خطأ / قطعة تالفة"), () => record_incident(frm), __("مشاكل الإنتاج"));
            }

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
