(() => {
    "use strict";

    function has_role(role) {
        return (frappe.user_roles || []).includes("System Manager") || (frappe.user_roles || []).includes(role);
    }

    function planned_rows(frm) {
        try {
            const payload = typeof frm.doc.details_json === "string"
                ? JSON.parse(frm.doc.details_json || "{}")
                : (frm.doc.details_json || {});
            return payload.stock_materials || [];
        } catch (error) {
            console.error("Invalid Material Consumption Log details_json", error);
            return [];
        }
    }

    frappe.ui.form.on("Material Consumption Log", {
        refresh(frm) {
            if (frm.is_new() || frm.doc.status !== "Submitted" || frm.doc.actual_recorded) return;
            if (!(has_role("Production Manager") || has_role("Stock Manager"))) return;

            frm.add_custom_button(__("Record Actual Consumption"), () => {
                const rows = planned_rows(frm);
                if (!rows.length) {
                    frappe.msgprint(__("No planned stock materials are available for reconciliation."));
                    return;
                }

                const fields = [];
                rows.forEach((row, index) => {
                    fields.push({
                        fieldname: `actual_${index}`,
                        fieldtype: "Float",
                        label: `${row.item_code} — ${__("Actual Stock Qty")}`,
                        default: Number(row.required_qty ?? row.qty ?? 0),
                        reqd: 1,
                        description: `${__("Planned")}: ${row.required_qty ?? row.qty ?? 0} ${row.stock_uom || ""} | ${row.planned_unit || ""}: ${row.planned_qty ?? ""}`,
                    });
                });

                frappe.prompt(
                    fields,
                    values => {
                        const actual_materials = rows.map((row, index) => ({
                            item_code: row.item_code,
                            actual_qty: Number(values[`actual_${index}`] ?? 0),
                        }));
                        frappe.confirm(
                            __("Differences above plan will issue extra stock; differences below plan will return stock to the warehouse. Continue?"),
                            () => frappe.call({
                                method: "almdina_erp.almdina_erp.services.actual_consumption_service.record_actual_consumption",
                                args: {
                                    consumption_log: frm.doc.name,
                                    actual_materials: JSON.stringify(actual_materials),
                                },
                                freeze: true,
                                freeze_message: __("Reconciling actual consumption..."),
                            }).then(r => {
                                const data = r.message || {};
                                frappe.msgprint({
                                    title: __("Actual Consumption Recorded"),
                                    indicator: "green",
                                    message: [
                                        `${__("Additional Material Issue")}: ${data.additional_issue_stock_entry || "-"}`,
                                        `${__("Material Return Receipt")}: ${data.return_receipt_stock_entry || "-"}`,
                                        `${__("Material Variance Cost USD")}: ${data.material_variance_cost_usd || 0}`,
                                    ].join("<br>"),
                                });
                                frm.reload_doc();
                            })
                        );
                    },
                    __("Record Actual Consumption"),
                    __("Reconcile")
                );
            }, __("Stock"));
        },
    });
})();
