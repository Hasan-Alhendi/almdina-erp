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
                frm.add_custom_button(__("Open Replacement Cutting Plan"), () => {
                    frappe.set_route("Form", "Cutting Plan", frm.doc.cutting_plan);
                }, __("Replacement"));
            }

            if (frm.doc.status === "Pending Approval" && has_role("Production Manager")) {
                frm.add_custom_button(__("Approve Replacement"), () => {
                    frappe.confirm(
                        __("A valid source will be selected, reserved when needed, and an approved Mini Cutting Plan will be created with material validation. Continue?"),
                        () => call_action(frm, "approve_replacement").then(data => {
                            frappe.msgprint({
                                title: __("Replacement Approved"),
                                indicator: "green",
                                message: `${__("Cutting Plan")}: <b>${data.cutting_plan || ""}</b><br>${__("Remnant")}: ${data.selected_remnant || __("Full Board")}`,
                            });
                        })
                    );
                }, __("Replacement"));
            }

            if (frm.doc.status === "Approved" && (has_role("Cutting Operator") || has_role("Production Manager"))) {
                frm.add_custom_button(__("Start Replacement Cutting"), () => {
                    frappe.confirm(
                        __("Reserved materials will be consumed and the selected source will be marked as physically used. Continue?"),
                        () => call_action(frm, "start_replacement")
                    );
                }, __("Replacement"));
            }

            if (frm.doc.status === "In Progress" && (has_role("Cutting Operator") || has_role("Production Manager"))) {
                frm.add_custom_button(__("Complete Replacement"), () => {
                    const fields = [];
                    if (has_role("Production Manager")) {
                        fields.push({
                            fieldname: "internal_loss_cost_usd",
                            fieldtype: "Currency",
                            label: __("Actual Internal Loss USD"),
                            description: __("Leave blank to use the planned cost frozen at approval."),
                        });
                    }
                    frappe.prompt(
                        fields,
                        values => call_action(frm, "complete_replacement", {
                            internal_loss_cost_usd: values.internal_loss_cost_usd || null,
                        }).then(data => {
                            frappe.msgprint({
                                title: __("Replacement Completed"),
                                indicator: "green",
                                message: `${__("Generated Remnants")}: ${(data.generated_remnants || []).join(", ") || "-"}`,
                            });
                        }),
                        __("Complete Replacement Piece"),
                        __("Finish")
                    );
                }, __("Replacement"));
            }

            if (["Pending Approval", "Approved"].includes(frm.doc.status) && has_role("Production Manager")) {
                frm.add_custom_button(__("Cancel Replacement"), () => {
                    frappe.prompt(
                        [{ fieldname: "reason", fieldtype: "Small Text", label: __("Cancellation Reason"), reqd: 1 }],
                        values => call_action(frm, "cancel_replacement", { reason: values.reason }),
                        __("Cancel Replacement"),
                        __("Confirm")
                    );
                }, __("Replacement"));
            }
        },
    });
})();
