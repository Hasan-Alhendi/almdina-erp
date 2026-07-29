(() => {
    "use strict";

    function has_role(role) {
        return (frappe.user_roles || []).includes("System Manager") || (frappe.user_roles || []).includes(role);
    }

    frappe.ui.form.on("Door Cutting Order", {
        refresh(frm) {
            if (frm.is_new() || !has_role("Production Manager")) return;
            if (["Cancelled", "Completed", "Draft", "Rejected"].includes(frm.doc.status)) return;

            frm.add_custom_button(__("Cancel Order"), () => {
                frappe.prompt(
                    [
                        { fieldname: "reason", fieldtype: "Small Text", label: __("Cancellation Reason"), reqd: 1 },
                    ],
                    values => {
                        frappe.confirm(
                            __("The active production stages will be cancelled. Continue?"),
                            () => frappe.call({
                                method: "almdina_erp.almdina_erp.services.order_lifecycle_service.cancel_order",
                                args: {
                                    order_name: frm.doc.name,
                                    reason: values.reason,
                                },
                                freeze: true,
                                freeze_message: __("Cancelling order..."),
                            }).then(r => {
                                const data = r.message || {};
                                frappe.msgprint({
                                    title: __("Order Cancelled"),
                                    indicator: "orange",
                                    message: __("Order and active production stages were cancelled."),
                                });
                                frm.reload_doc();
                            })
                        );
                    },
                    __("Cancel Order"),
                    __("Continue")
                );
            }, __("Order Workflow"));
        },
    });
})();
