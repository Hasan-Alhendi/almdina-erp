frappe.pages["factory-plan-archive"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Factory Plan Archive"),
        single_column: true,
    });
    const $body = $(wrapper).find(".layout-main-section");

    $body.html(`
        <div class="frappe-card" style="padding:20px;max-width:760px">
            <p>${__("Generate and attach an immutable official PDF for an approved production cutting plan.")}</p>
            <div id="plan-archive-order"></div>
            <div style="margin-top:14px"><button class="btn btn-primary" id="archive-plan-pdf">${__("Archive Approved Plan PDF")}</button></div>
            <div id="archive-result" style="margin-top:14px"></div>
        </div>
    `);

    const control = frappe.ui.form.make_control({
        parent: $body.find("#plan-archive-order"),
        df: {
            fieldname: "order_name",
            fieldtype: "Link",
            options: "Door Cutting Order",
            label: __("Door Cutting Order"),
            reqd: 1,
            get_query: () => ({ filters: { status: ["not in", ["Draft", "Rejected", "Cancelled"]] } }),
        },
        render_input: true,
    });

    $body.find("#archive-plan-pdf").on("click", () => {
        const orderName = control.get_value();
        if (!orderName) {
            frappe.msgprint(__("Select a Door Cutting Order first."));
            return;
        }
        frappe.call({
            method: "almdina_erp.almdina_erp.services.archive_service.archive_approved_plan_pdf",
            args: { order_name: orderName },
            freeze: true,
            freeze_message: __("Generating official PDF..."),
        }).then(r => {
            const data = r.message || {};
            const fileUrl = data.file_url || "";
            const link = fileUrl
                ? `<a class="btn btn-default" href="${frappe.utils.escape_html(fileUrl)}" target="_blank" rel="noopener">${__("Open Archived PDF")}</a>`
                : "";
            $body.find("#archive-result").html(`
                <div class="alert alert-success">
                    <b>${data.already_archived ? __("PDF was already archived.") : __("PDF archived successfully.")}</b><br>
                    ${__("Plan")}: ${frappe.utils.escape_html(data.cutting_plan || "")} | ${__("Revision")}: ${frappe.utils.escape_html(String(data.revision || ""))}<br><br>${link}
                </div>
            `);
        });
    });
};
