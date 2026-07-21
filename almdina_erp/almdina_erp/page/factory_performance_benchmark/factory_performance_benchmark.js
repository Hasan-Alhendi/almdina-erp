frappe.pages["factory-performance-benchmark"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Factory Performance Benchmark"),
        single_column: true,
    });
    const $body = $(wrapper).find(".layout-main-section");

    $body.html(`
        <div class="frappe-card" style="padding:20px;max-width:900px">
            <div class="row">
                <div class="col-md-6" id="benchmark-order"></div>
                <div class="col-md-3" id="benchmark-repeats"></div>
                <div class="col-md-3" id="benchmark-mode"></div>
            </div>
            <div style="margin-top:16px">
                <button class="btn btn-primary" id="run-benchmark">${__("Run Benchmark")}</button>
            </div>
            <div id="benchmark-result" style="margin-top:18px"></div>
        </div>
    `);

    const order = frappe.ui.form.make_control({
        parent: $body.find("#benchmark-order"),
        df: { fieldname: "order", fieldtype: "Link", options: "Door Cutting Order", label: __("Door Cutting Order"), reqd: 1 },
        render_input: true,
    });
    const repeats = frappe.ui.form.make_control({
        parent: $body.find("#benchmark-repeats"),
        df: { fieldname: "repeats", fieldtype: "Int", label: __("Repeats"), default: 3 },
        render_input: true,
    });
    const mode = frappe.ui.form.make_control({
        parent: $body.find("#benchmark-mode"),
        df: { fieldname: "packing_mode", fieldtype: "Data", label: __("Packing Mode Override"), description: __("Leave empty to use the order mode.") },
        render_input: true,
    });

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    $body.find("#run-benchmark").on("click", () => {
        if (!order.get_value()) {
            frappe.msgprint(__("Select a Door Cutting Order first."));
            return;
        }
        frappe.call({
            method: "almdina_erp.almdina_erp.services.performance_service.benchmark_order_cutting_engine",
            args: {
                order_name: order.get_value(),
                repeats: repeats.get_value() || 3,
                packing_mode: mode.get_value() || null,
            },
            freeze: true,
            freeze_message: __("Running cutting engine benchmark..."),
        }).then(r => {
            const data = r.message || {};
            const indicator = data.meets_target_on_this_run ? "green" : "red";
            const verdict = data.meets_target_on_this_run ? __("Target met on this run") : __("Target NOT met on this run");
            $body.find("#benchmark-result").html(`
                <div class="alert ${data.meets_target_on_this_run ? "alert-success" : "alert-danger"}">
                    <span class="indicator-pill ${indicator}">${esc(verdict)}</span>
                    <hr>
                    <b>${__("Expanded Pieces")}</b>: ${esc(data.expanded_pieces)}<br>
                    <b>${__("Requested Mode")}</b>: ${esc(__(data.packing_mode_requested || ""))}<br>
                    <b>${__("Selected Method")}</b>: ${esc(__(data.method_selected || ""))}<br>
                    <b>${__("Runs ms")}</b>: ${esc((data.elapsed_ms || []).join(", "))}<br>
                    <b>${__("Average ms")}</b>: ${esc(data.average_ms)}<br>
                    <b>${__("Worst ms")}</b>: ${esc(data.worst_ms)} / ${esc(data.target_ms)} ${__("Target ms")}<br>
                    <b>${__("Required Boards")}</b>: ${esc(data.required_boards)}<br>
                    <b>${__("Unplaced")}</b>: ${esc(data.unplaced_count)}<br>
                    <b>${__("Waste Area M2")}</b>: ${esc(data.waste_area_m2)}
                </div>
                <div class="text-muted">${__("This benchmark is read-only and creates no stock movement or document changes. Record server specs, app commit SHA, result and evidence in UAT.")}</div>
            `);
        });
    });
};
