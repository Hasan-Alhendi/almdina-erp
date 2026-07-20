(() => {
    "use strict";

    function has_role(role) {
        return (frappe.user_roles || []).includes("System Manager") || (frappe.user_roles || []).includes(role);
    }

    function call_action(frm, method, args = {}) {
        return frappe.call({
            method: `almdina_erp.almdina_erp.services.replacement_service.${method}`,
            args: { replacement_name: frm.doc.name, ...args },
            freeze: true,
            freeze_message: __("Processing replacement..."),
        }).then(r => frm.reload_doc().then(() => r.message || {}));
    }

    frappe.ui.form.on("Replacement Piece", {
        refresh(frm) {
            if (frm.is_new()) return;

            if (frm.doc.cutting_plan) {
                frm.add_custom_button(__("فتح خطة القص التعويضية"), () => {
                    frappe.set_route("Form", "Cutting Plan", frm.doc.cutting_plan);
                }, __("التعويض"));
            }

            if (frm.doc.status === "Pending Approval" && has_role("Production Manager")) {
                frm.add_custom_button(__("اعتماد التعويض"), () => {
                    frappe.confirm(
                        __("سيتم اختيار مصدر صالح، حجزه عند الحاجة، إنشاء Mini Cutting Plan معتمدة، وفحص المواد المخزنية. هل تريد المتابعة؟"),
                        () => call_action(frm, "approve_replacement").then(data => {
                            frappe.msgprint({
                                title: __("تم اعتماد التعويض"),
                                indicator: "green",
                                message: `${__("Cutting Plan")}: <b>${data.cutting_plan || ""}</b><br>${__("Remnant")}: ${data.selected_remnant || __("Full Board")}`,
                            });
                        })
                    );
                }, __("التعويض"));
            }

            if (frm.doc.status === "Approved" && (has_role("Cutting Operator") || has_role("Production Manager"))) {
                frm.add_custom_button(__("بدء قص التعويض"), () => {
                    frappe.confirm(
                        __("سيتم استهلاك المواد المحجوزة واعتبار المصدر مستخدمًا فعليًا. هل تريد البدء؟"),
                        () => call_action(frm, "start_replacement")
                    );
                }, __("التعويض"));
            }

            if (frm.doc.status === "In Progress" && (has_role("Cutting Operator") || has_role("Production Manager"))) {
                frm.add_custom_button(__("إنهاء التعويض"), () => {
                    const fields = [];
                    if (has_role("Production Manager")) {
                        fields.push({
                            fieldname: "internal_loss_cost_usd",
                            fieldtype: "Currency",
                            label: __("Actual Internal Loss USD"),
                            description: __("اتركه فارغًا لاستخدام التكلفة المخططة المثبتة عند الاعتماد."),
                        });
                    }
                    frappe.prompt(
                        fields,
                        values => call_action(frm, "complete_replacement", {
                            internal_loss_cost_usd: values.internal_loss_cost_usd || null,
                        }).then(data => {
                            frappe.msgprint({
                                title: __("اكتمل التعويض"),
                                indicator: "green",
                                message: `${__("Generated Remnants")}: ${(data.generated_remnants || []).join(", ") || "-"}`,
                            });
                        }),
                        __("إنهاء القطعة التعويضية"),
                        __("إنهاء")
                    );
                }, __("التعويض"));
            }

            if (["Pending Approval", "Approved"].includes(frm.doc.status) && has_role("Production Manager")) {
                frm.add_custom_button(__("إلغاء التعويض"), () => {
                    frappe.prompt(
                        [{ fieldname: "reason", fieldtype: "Small Text", label: __("سبب الإلغاء"), reqd: 1 }],
                        values => call_action(frm, "cancel_replacement", { reason: values.reason }),
                        __("إلغاء التعويض"),
                        __("تأكيد")
                    );
                }, __("التعويض"));
            }
        },
    });
})();
