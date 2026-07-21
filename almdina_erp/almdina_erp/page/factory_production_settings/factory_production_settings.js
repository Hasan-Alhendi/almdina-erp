frappe.pages["factory-production-settings"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Factory Production Settings"),
        single_column: true,
    });

    const $body = $(wrapper).find(".layout-main-section");
    let current = {};

    function escape(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function render(data) {
        current = data || {};
        $body.html(`
            <div class="frappe-card" style="padding:18px;max-width:920px">
                <div class="row">
                    <div class="col-md-6"><b>${__("Default Production Routing")}</b><div>${escape(current.default_production_routing || "-")}</div></div>
                    <div class="col-md-6"><b>${__("Default Packing Mode")}</b><div>${escape(__(current.default_packing_mode || "-"))}</div></div>
                </div>
                <hr>
                <div class="row">
                    <div class="col-md-4"><b>${__("Default Kerf MM")}</b><div>${escape(current.default_kerf_mm)}</div></div>
                    <div class="col-md-4"><b>${__("Default Trim Margin MM")}</b><div>${escape(current.default_trim_margin_mm)}</div></div>
                    <div class="col-md-4"><b>${__("Default Cutting Cost / Board USD")}</b><div>${escape(current.default_cutting_cost_per_board_usd)}</div></div>
                </div>
                <hr>
                <div class="text-muted">${__("Stage override policy is intentionally not editable from this limited Production Manager page.")}</div>
            </div>
        `);
        page.clear_actions();
        page.set_primary_action(__("Edit Production Defaults"), openDialog, "edit");
    }

    function load() {
        return frappe.call({
            method: "almdina_erp.almdina_erp.services.production_settings_service.get_production_settings",
            freeze: true,
        }).then(r => render(r.message || {}));
    }

    function openDialog() {
        const options = (current.packing_options || ["Auto"]).join("\n");
        const dialog = new frappe.ui.Dialog({
            title: __("Edit Production Defaults"),
            fields: [
                { fieldname: "default_production_routing", fieldtype: "Link", options: "Production Routing", label: __("Default Production Routing"), reqd: 1, default: current.default_production_routing },
                { fieldname: "default_packing_mode", fieldtype: "Select", options, label: __("Default Packing Mode"), reqd: 1, default: current.default_packing_mode || "Auto" },
                { fieldname: "dimensions_section", fieldtype: "Section Break", label: __("Cutting Defaults") },
                { fieldname: "default_kerf_mm", fieldtype: "Float", label: __("Default Kerf MM"), reqd: 1, default: current.default_kerf_mm },
                { fieldname: "default_trim_margin_mm", fieldtype: "Float", label: __("Default Trim Margin MM"), reqd: 1, default: current.default_trim_margin_mm },
                { fieldname: "default_cutting_cost_per_board_usd", fieldtype: "Currency", label: __("Default Cutting Cost / Board USD"), reqd: 1, default: current.default_cutting_cost_per_board_usd },
            ],
            primary_action_label: __("Save"),
            primary_action(values) {
                frappe.call({
                    method: "almdina_erp.almdina_erp.services.production_settings_service.update_production_settings",
                    args: { values: JSON.stringify(values) },
                    freeze: true,
                    freeze_message: __("Saving production defaults..."),
                }).then(r => {
                    dialog.hide();
                    render(r.message || {});
                    frappe.show_alert({ message: __("Production defaults updated."), indicator: "green" });
                });
            },
        });
        dialog.show();
    }

    load();
};
