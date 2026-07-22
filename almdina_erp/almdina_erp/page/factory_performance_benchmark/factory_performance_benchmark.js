frappe.pages["factory-performance-benchmark"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Factory Performance Benchmark"),
        single_column: true,
    });
    const $body = $(wrapper).find(".layout-main-section");

    $body.html(`
        <div class="frappe-card" style="padding:20px;max-width:1100px">
            <div class="row">
                <div class="col-md-5" id="benchmark-order"></div>
                <div class="col-md-2" id="benchmark-repeats"></div>
                <div class="col-md-5" id="benchmark-mode"></div>
            </div>
            <div style="margin-top:16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <button class="btn btn-primary" id="run-benchmark">${__("Run Benchmark")}</button>
                <span class="text-muted" style="font-size:12px">يقيس السرعة وجودة الخطة دون حفظ أي تغيير أو حركة مخزون.</span>
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
        df: {
            fieldname: "packing_mode",
            fieldtype: "Select",
            label: __("Packing Mode Override"),
            options: [
                "",
                "Auto",
                "Auto Pro",
                "Deep Search",
                "Optimal Search",
                "MaxRects Best Short Side",
                "MaxRects Best Area",
                "MaxRects Bottom Left",
                "MaxRects Contact Point",
                "MaxRects Width",
                "MaxRects Length",
                "Shelf Horizontal",
                "Shelf Vertical",
                "Shelf First Fit",
                "Shelf Next Fit",
                "Guillotine Short Axis",
                "Guillotine Long Axis",
                "Guillotine Best Area Fit",
                "Guillotine Best Short Side Fit",
                "Guillotine Best Long Side Fit",
                "Skyline Bottom Left",
                "Skyline Best Fit",
            ].join("\n"),
            description: __("Leave empty to use the order mode."),
        },
        render_input: true,
    });

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function statusLabel(value) {
        const labels = {
            OPTIMAL: "مثبت كأفضل حل ضمن النموذج",
            FEASIBLE: "حل صالح وجيد ضمن المهلة",
            HEURISTIC_FALLBACK: "أفضل حل تجريبي ضمن المهلة",
            GUILLOTINE_DEEP_SEARCH: "بحث معمق مناسب لمنشار الألواح",
            OPTIMAL_FULL_BOARD_REMAINDER: "حل أمثل للألواح الجديدة بعد استخدام البقايا",
        };
        return labels[value] || value || "-";
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
            const verdict = data.meets_target_on_this_run ? "ضمن هدف الزمن المحدد" : "تجاوز هدف الزمن المحدد";
            $body.find("#benchmark-result").html(`
                <div class="alert ${data.meets_target_on_this_run ? "alert-success" : "alert-warning"}">
                    <span class="indicator-pill ${indicator}">${esc(verdict)}</span>
                    <hr>
                    <div class="row" style="line-height:1.9">
                        <div class="col-md-6">
                            <b>عدد القطع بعد التوسيع:</b> ${esc(data.expanded_pieces)}<br>
                            <b>مستوى التحسين المطلوب:</b> ${esc(__(data.packing_mode_requested || ""))}<br>
                            <b>نوع الماكينة:</b> ${esc(__(data.machine_type || "Auto"))}<br>
                            <b>الطريقة المختارة:</b> ${esc(__(data.method_selected || ""))}<br>
                            <b>حالة البحث:</b> ${esc(statusLabel(data.solver_status))}<br>
                            <b>عدد محاولات التحسين:</b> ${esc(data.optimization_attempts || 0)}
                        </div>
                        <div class="col-md-6">
                            <b>عدد الألواح:</b> ${esc(data.required_boards)}<br>
                            <b>القطع غير الموزعة:</b> ${esc(data.unplaced_count)}<br>
                            <b>مساحة الهدر:</b> ${esc(data.waste_area_m2)} م²<br>
                            <b>أكبر بقايا مفيدة:</b> ${esc(data.largest_reusable_free_area_m2)} م²<br>
                            <b>عدد خطوط القص التقديري:</b> ${esc(data.estimated_cut_count)}<br>
                            <b>طول القص التقديري:</b> ${esc(data.estimated_cut_length_m)} متر<br>
                            <b>عدد التدويرات:</b> ${esc(data.rotation_count)}
                        </div>
                    </div>
                    <hr>
                    <b>أزمنة التشغيل (ms):</b> ${esc((data.elapsed_ms || []).join(", "))}<br>
                    <b>المتوسط:</b> ${esc(data.average_ms)} ms &nbsp; | &nbsp;
                    <b>الأسوأ:</b> ${esc(data.worst_ms)} / ${esc(data.target_ms)} ms
                </div>
                <div class="text-muted">هذا الاختبار للقراءة فقط؛ لا ينشئ حركة مخزون ولا يغيّر الطلب. سجّل مواصفات السيرفر ونسخة التطبيق والنتيجة ضمن UAT.</div>
            `);
        });
    });
};
