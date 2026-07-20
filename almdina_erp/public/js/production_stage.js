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
                { fieldname: "piece_label", fieldtype: "Data", label: __("Piece number such as 2.3"), reqd: 1 },
                {
                    fieldname: "reason",
                    fieldtype: "Select",
                    label: __("Reason"),
                    options: ["Measurement Error", "Cutting Error", "Edge Banding Error", "Damage", "Lost Piece", "Material Defect", "Other"].join("\n"),
                    reqd: 1,
                },
                { fieldname: "description", fieldtype: "Small Text", label: __("Incident Description"), reqd: 1 },
                { fieldname: "requires_replacement", fieldtype: "Check", label: __("Requires Replacement Piece"), default: 1 },
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
                    let message = `${__("Incident recorded")}: ${result.incident || ""}`;
                    if (result.replacement_piece) {
                        message += `<br>${__("Replacement piece created")}: <b>${result.replacement_piece}</b>`;
                    }
                    frappe.msgprint({ title: __("Production Incident"), indicator: "orange", message });
                    frm.reload_doc();
                });
            },
            __("Record Incident / Damaged Piece"),
            __("Record")
        );
    }

    frappe.ui.form.on("Production Stage", {
        refresh(frm) {
            if (frm.is_new() || !can_operate(frm)) return;

            if (["In Progress", "Paused", "Completed"].includes(frm.doc.status) && ["Cutting", "Edge Banding"].includes(frm.doc.stage_type)) {
                frm.add_custom_button(__("Record Incident / Damaged Piece"), () => record_incident(frm), __("Production Problems"));
            }

            if (frm.doc.status === "Pending") {
                frm.add_custom_button(__("Start Stage"), () => {
                    frappe.confirm(
                        __("The start time and current worker will be recorded. Continue?"),
                        () => invoke(frm, "start_stage")
                    );
                });
            }

            if (frm.doc.status === "In Progress") {
                frm.add_custom_button(__("Pause"), () => {
                    frappe.prompt(
                        [{ fieldname: "reason", fieldtype: "Small Text", label: __("Pause Reason") }],
                        values => invoke(frm, "pause_stage", { reason: values.reason || "" }),
                        __("Pause Stage"),
                        __("Pause")
                    );
                });

                frm.add_custom_button(__("Finish Stage"), () => {
                    frappe.prompt(
                        [
                            { fieldname: "completed_qty", fieldtype: "Int", label: __("Completed Quantity") },
                            { fieldname: "notes", fieldtype: "Small Text", label: __("Notes") },
                        ],
                        values => invoke(frm, "finish_stage", values),
                        __("Finish Stage"),
                        __("Finish")
                    );
                });
            }

            if (frm.doc.status === "Paused") {
                frm.add_custom_button(__("Resume"), () => invoke(frm, "resume_stage"));
                frm.add_custom_button(__("Finish Stage"), () => {
                    frappe.prompt(
                        [
                            { fieldname: "completed_qty", fieldtype: "Int", label: __("Completed Quantity") },
                            { fieldname: "notes", fieldtype: "Small Text", label: __("Notes") },
                        ],
                        values => invoke(frm, "finish_stage", values),
                        __("Finish Stage"),
                        __("Finish")
                    );
                });
            }
        },
    });
})();
