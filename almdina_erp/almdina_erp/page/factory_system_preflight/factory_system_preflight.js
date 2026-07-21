frappe.pages["factory-system-preflight"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Factory System Preflight"),
        single_column: true,
    });
    const $body = $(wrapper).find(".layout-main-section");

    const checkLabels = {
        default_warehouse: __("Default Warehouse Check"),
        production_routing: __("Production Routing Check"),
        routing_core_stages: __("Required Production Stages Check"),
        roles: __("Factory User Roles Check"),
        mdf_items: __("MDF Board Items Check"),
        edge_master_structure: __("Edge Banding Master Data Check"),
        edge_stock_mapping: __("Edge Stock Mapping Check"),
        print_formats: __("Production Print Formats Check"),
        reports: __("Operational Reports Check"),
    };

    const detailLabels = {
        warehouse: __("Warehouse"),
        company: __("Company"),
        routing: __("Production Routing"),
        stages: __("Stages"),
        missing: __("Missing"),
        count: __("Count"),
        invalid: __("Incomplete Records"),
        unmapped: __("Unmapped Stock Items"),
        item: __("Item"),
        problems: __("Problems"),
        edge_type: __("Edge Type"),
    };

    function escape(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function localizeDetails(value) {
        if (Array.isArray(value)) return value.map(localizeDetails);
        if (value && typeof value === "object") {
            const result = {};
            Object.entries(value).forEach(([key, child]) => {
                result[detailLabels[key] || __(key)] = localizeDetails(child);
            });
            return result;
        }
        return typeof value === "string" ? __(value) : value;
    }

    function render(data) {
        const checks = data.checks || [];
        const statusClass = data.ready_for_controlled_uat ? "alert-success" : "alert-danger";
        const statusText = data.ready_for_controlled_uat
            ? __("No configuration blockers were found. Controlled UAT may proceed.")
            : __("Configuration blockers exist. Do not start controlled UAT yet.");

        let html = `
            <div class="alert ${statusClass}">
                <b>${statusText}</b><br>
                ${__("Blockers")}: ${data.blocker_count || 0} &nbsp; | &nbsp; ${__("Warnings")}: ${data.warning_count || 0}
            </div>
            <div class="frappe-card" style="padding:0;overflow:auto">
                <table class="table table-bordered" style="margin:0;min-width:900px">
                    <thead><tr><th>${__("Status")}</th><th>${__("Check")}</th><th>${__("Message")}</th><th>${__("Details")}</th></tr></thead><tbody>`;

        checks.forEach(row => {
            const indicator = row.ok ? "green" : (row.severity === "BLOCKER" ? "red" : "orange");
            const label = row.ok ? __("OK") : __(row.severity || "WARNING");
            const checkLabel = checkLabels[row.key] || __(row.key || "");
            const details = localizeDetails(row.details || {});
            html += `
                <tr>
                    <td><span class="indicator-pill ${indicator}">${escape(label)}</span></td>
                    <td>${escape(checkLabel)}</td>
                    <td>${escape(__(row.message || ""))}</td>
                    <td><pre style="white-space:pre-wrap;margin:0;font-size:11px">${escape(JSON.stringify(details, null, 2))}</pre></td>
                </tr>`;
        });
        html += "</tbody></table></div>";
        $body.html(html);
    }

    function run() {
        $body.html(`<div class="text-muted" style="padding:20px">${__("Running factory preflight checks...")}</div>`);
        return frappe.call({
            method: "almdina_erp.almdina_erp.services.preflight_service.run_factory_preflight",
            freeze: true,
            freeze_message: __("Running preflight..."),
        }).then(r => render(r.message || {}));
    }

    page.set_primary_action(__("Run Preflight Again"), run, "refresh");
    run();
};
