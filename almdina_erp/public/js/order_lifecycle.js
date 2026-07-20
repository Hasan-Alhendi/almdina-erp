(() => {
    "use strict";

    function has_role(role) {
        return (frappe.user_roles || []).includes("System Manager") || (frappe.user_roles || []).includes(role);
    }

    frappe.ui.form.on("Door Cutting Order", {
        refresh(frm) {
            if (frm.is_new() || !has_role("Production Manager")) return;
            if (["Cancelled", "Completed", "Draft", "Rejected"].includes(frm.doc.status)) return;

            frm.add_custom_button(__("إلغاء الطلب"), () => {
                frappe.prompt(
                    [
                        { fieldname: "reason", fieldtype: "Small Text", label: __("سبب الإلغاء"), reqd: 1 },
                        {
                            fieldname: "reverse_stock",
                            fieldtype: "Check",
                            label: __("عكس الحركات المخزنية المرسلة إن وجدت"),
                            default: 0,
                            description: __("لا تفعل هذا الخيار إلا إذا كانت المواد قابلة للإرجاع فعليًا ولم يكتمل القص."),
                        },
                    ],
                    values => {
                        frappe.confirm(
                            __("الإلغاء عملية حساسة وقد تعكس حركة مخزون وتحرر حجوزات. هل تريد المتابعة؟"),
                            () => frappe.call({
                                method: "almdina_erp.almdina_erp.services.order_lifecycle_service.cancel_order",
                                args: {
                                    order_name: frm.doc.name,
                                    reason: values.reason,
                                    reverse_stock: values.reverse_stock,
                                },
                                freeze: true,
                                freeze_message: __("Cancelling order..."),
                            }).then(r => {
                                const data = r.message || {};
                                frappe.msgprint({
                                    title: __("تم إلغاء الطلب"),
                                    indicator: "orange",
                                    message: `${__("Reversed Stock Entries")}: ${(data.reversed_stock_entries || []).join(", ") || "-"}<br>${__("Released Remnants")}: ${(data.released_remnants || []).join(", ") || "-"}`,
                                });
                                frm.reload_doc();
                            })
                        );
                    },
                    __("إلغاء الطلب"),
                    __("متابعة")
                );
            }, __("دورة الطلب"));
        },
    });
})();
