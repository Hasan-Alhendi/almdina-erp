frappe.pages["factory-approval-queue"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Factory Approval Queue"),
        single_column: true,
    });
    const $body = $(wrapper).find(".layout-main-section");

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function load() {
        $body.html(`<div class="text-muted" style="padding:18px">${__("Loading pending review orders...")}</div>`);
        return frappe.call({
            method: "almdina_erp.almdina_erp.services.approval_queue_service.get_pending_review_orders",
            freeze: false,
        }).then(r => render(r.message || []));
    }

    function render(rows) {
        if (!rows.length) {
            $body.html(`<div class="frappe-card" style="padding:24px"><h4>${__("No orders are waiting for review.")}</h4></div>`);
            return;
        }
        let html = `
            <div class="frappe-card" style="padding:0;overflow:auto">
                <table class="table table-bordered" style="margin:0;min-width:1050px">
                    <thead><tr>
                        <th>${__("Order")}</th><th>${__("Customer")}</th><th>${__("Date")}</th><th>${__("Revision")}</th>
                        <th>${__("Board Item")}</th><th>${__("Material / Color / Thickness")}</th>
                        <th>${__("Boards")}</th><th>${__("Waste %")}</th><th>${__("Method")}</th><th>${__("Actions")}</th>
                    </tr></thead><tbody>`;
        rows.forEach(row => {
            html += `
                <tr data-order="${esc(row.name)}">
                    <td><a class="order-link" href="/app/door-cutting-order/${encodeURIComponent(row.name)}">${esc(row.name)}</a></td>
                    <td>${esc(row.customer || "")}</td>
                    <td>${esc(row.order_date || "")}</td>
                    <td>${esc(row.revision || 1)}</td>
                    <td>${esc(row.board_item || "")}</td>
                    <td>${esc(row.board_material || "")} / ${esc(row.board_color || "")} / ${esc(row.board_thickness_mm || "")} ${__("MM")}</td>
                    <td>${esc(row.required_boards || 0)}</td>
                    <td>${esc(row.waste_percent || 0)}</td>
                    <td>${esc(__(row.packing_method || ""))}</td>
                    <td style="white-space:nowrap">
                        <button class="btn btn-sm btn-primary approve-order">${__("Approve")}</button>
                        <button class="btn btn-sm btn-default reject-order">${__("Reject")}</button>
                    </td>
                </tr>`;
        });
        html += "</tbody></table></div>";
        $body.html(html);

        $body.find(".approve-order").on("click", function () {
            const orderName = $(this).closest("tr").data("order");
            frappe.confirm(
                __("Approve this order using a database row lock and create its immutable production plan?"),
                () => frappe.call({
                    method: "almdina_erp.almdina_erp.services.approval_queue_service.approve_order_safely",
                    args: { order_name: orderName },
                    freeze: true,
                    freeze_message: __("Approving order safely..."),
                }).then(() => {
                    frappe.show_alert({ message: __("Order approved."), indicator: "green" });
                    load();
                })
            );
        });

        $body.find(".reject-order").on("click", function () {
            const orderName = $(this).closest("tr").data("order");
            frappe.prompt(
                [{ fieldname: "reason", fieldtype: "Small Text", label: __("Rejection Reason"), reqd: 1 }],
                values => frappe.call({
                    method: "almdina_erp.almdina_erp.services.approval_queue_service.reject_order_safely",
                    args: { order_name: orderName, reason: values.reason },
                    freeze: true,
                }).then(() => {
                    frappe.show_alert({ message: __("Order rejected and returned for revision."), indicator: "orange" });
                    load();
                }),
                __("Reject Order"),
                __("Reject")
            );
        });
    }

    page.set_primary_action(__("Refresh"), load, "refresh");
    load();
};
