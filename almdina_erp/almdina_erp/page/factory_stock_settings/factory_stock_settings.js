frappe.pages["factory-stock-settings"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Factory Stock Settings"),
        single_column: true,
    });

    const $body = $(wrapper).find(".layout-main-section");
    let current = {};

    function escape(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function yesNo(value) {
        return Number(value) ? __("Yes") : __("No");
    }

    function render(data) {
        current = data || {};
        $body.html(`
            <div class="frappe-card" style="padding:18px;max-width:980px">
                <div class="row">
                    <div class="col-md-6"><b>${__("Default Warehouse")}</b><div>${escape(current.default_warehouse || "-")}</div></div>
                    <div class="col-md-6"><b>${__("Reserve Stock On Approval")}</b><div>${yesNo(current.reserve_stock_on_approval)}</div></div>
                </div>
                <hr>
                <div class="row">
                    <div class="col-md-6"><b>${__("Stock Consumption Point")}</b><div>${escape(current.stock_consumption_point || "-")}</div></div>
                    <div class="col-md-6"><b>${__("Prefer Matching Remnants Before Full Boards")}</b><div>${yesNo(current.prefer_remnants_before_full_boards)}</div></div>
                </div>
                <hr>
                <div class="row">
                    <div class="col-md-4"><b>${__("Minimum Remnant Width MM")}</b><div>${escape(current.min_remnant_width_mm)}</div></div>
                    <div class="col-md-4"><b>${__("Minimum Remnant Length MM")}</b><div>${escape(current.min_remnant_length_mm)}</div></div>
                    <div class="col-md-4"><b>${__("Minimum Remnant Area M2")}</b><div>${escape(current.min_remnant_area_m2)}</div></div>
                </div>
                <hr>
                <div class="row">
                    <div class="col-md-6"><b>${__("Remnant Cost Policy")}</b><div>${escape(current.remnant_cost_policy || "-")}</div></div>
                    <div class="col-md-6"><b>${__("Configured Remnant Rate USD / M2")}</b><div>${escape(current.remnant_rate_usd_per_m2)}</div></div>
                </div>
                ${current.can_edit ? "" : `<hr><div class="text-muted">${__("Read-only for your current role.")}</div>`}
            </div>
        `);

        page.clear_actions();
        if (current.can_edit) {
            page.set_primary_action(__("Edit Stock Policy"), openDialog, "edit");
        }
    }

    function load() {
        return frappe.call({
            method: "almdina_erp.almdina_erp.services.settings_access_service.get_stock_settings",
            freeze: true,
        }).then(r => render(r.message || {}));
    }

    function openDialog() {
        const dialog = new frappe.ui.Dialog({
            title: __("Edit Stock Policy"),
            fields: [
                { fieldname: "default_warehouse", fieldtype: "Link", options: "Warehouse", label: __("Default Warehouse"), default: current.default_warehouse },
                { fieldname: "reserve_stock_on_approval", fieldtype: "Check", label: __("Reserve Stock On Approval"), default: Number(current.reserve_stock_on_approval || 0) },
                { fieldname: "stock_consumption_point", fieldtype: "Select", label: __("Stock Consumption Point"), options: "Cutting Start\nCutting Finish", default: current.stock_consumption_point || "Cutting Start" },
                { fieldname: "remnant_section", fieldtype: "Section Break", label: __("Board Remnants") },
                { fieldname: "prefer_remnants_before_full_boards", fieldtype: "Check", label: __("Prefer Matching Remnants Before Full Boards"), default: Number(current.prefer_remnants_before_full_boards || 0) },
                { fieldname: "min_remnant_width_mm", fieldtype: "Float", label: __("Minimum Remnant Width MM"), default: current.min_remnant_width_mm },
                { fieldname: "min_remnant_length_mm", fieldtype: "Float", label: __("Minimum Remnant Length MM"), default: current.min_remnant_length_mm },
                { fieldname: "min_remnant_area_m2", fieldtype: "Float", label: __("Minimum Remnant Area M2"), default: current.min_remnant_area_m2 },
                { fieldname: "cost_section", fieldtype: "Section Break", label: __("Remnant Cost") },
                { fieldname: "remnant_cost_policy", fieldtype: "Select", label: __("Remnant Cost Policy"), options: "Zero\nAverage Valuation\nConfigured Rate", default: current.remnant_cost_policy || "Zero" },
                { fieldname: "remnant_rate_usd_per_m2", fieldtype: "Currency", label: __("Configured Remnant Rate USD / M2"), default: current.remnant_rate_usd_per_m2 },
            ],
            primary_action_label: __("Save"),
            primary_action(values) {
                frappe.call({
                    method: "almdina_erp.almdina_erp.services.settings_access_service.update_stock_settings",
                    args: { values: JSON.stringify(values) },
                    freeze: true,
                    freeze_message: __("Saving stock policy..."),
                }).then(r => {
                    dialog.hide();
                    render(r.message || {});
                    frappe.show_alert({ message: __("Stock policy updated."), indicator: "green" });
                });
            },
        });
        dialog.show();
    }

    load();
};
