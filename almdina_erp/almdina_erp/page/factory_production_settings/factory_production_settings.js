frappe.pages["factory-production-settings"].on_page_load = function (wrapper) {
    "use strict";

    const METHODS = Object.freeze({
        get: "almdina_erp.almdina_erp.services.production_settings_service.get_production_settings",
        update: "almdina_erp.almdina_erp.services.production_settings_service.update_production_settings",
        audit: "almdina_erp.almdina_erp.services.production_settings_service.get_factory_settings_audit",
    });
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("إعدادات المعمل"),
        single_column: true,
    });
    const $body = $(wrapper).find(".layout-main-section");
    let current = {};
    let requestId = 0;

    injectStyles();
    page.add_inner_button(__("سجل التغييرات"), openAudit, null, "history");
    page.add_inner_button(__("تحديث"), load, null, "refresh");
    load();

    function esc(value) {
        const text = value === null || value === undefined ? "" : String(value);
        return frappe.utils && frappe.utils.escape_html
            ? frappe.utils.escape_html(text)
            : $("<div>").text(text).html();
    }

    function call(method, args = {}, freezeMessage = "") {
        return frappe.call({
            method,
            args,
            freeze: Boolean(freezeMessage),
            freeze_message: freezeMessage,
        }).then(response => response.message || {});
    }

    function injectStyles() {
        if (document.getElementById("almdina-production-settings-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-production-settings-style";
        style.textContent = `
            .aps-shell{direction:rtl;display:grid;gap:14px;max-width:1120px;padding-bottom:30px}.aps-hero{padding:20px;border:1px solid var(--border-color,#e5e7eb);border-radius:16px;background:linear-gradient(135deg,var(--fg-color,#fff),var(--subtle-fg,#f7f9fb))}.aps-hero h2{margin:0 0 6px;font-size:21px;font-weight:800}.aps-hero p{margin:0;color:var(--text-muted,#6b7280);line-height:1.8}.aps-sections{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.aps-section{display:flex;flex-direction:column;padding:16px;border:1px solid var(--border-color,#e5e7eb);border-radius:15px;background:var(--fg-color,#fff);box-shadow:0 2px 8px rgba(0,0,0,.035)}.aps-section-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.aps-section h3{margin:0;font-size:17px;font-weight:800}.aps-section-desc{margin:5px 0 13px;color:var(--text-muted,#6b7280);font-size:12px;line-height:1.7}.aps-permission{display:inline-flex;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:700;background:#eef5ff;color:#285f9e}.aps-permission.readonly{background:#f2f3f5;color:#5b6570}.aps-values{display:grid;gap:8px;flex:1}.aps-value{padding:9px;border-radius:10px;background:var(--subtle-fg,#f7f8fa)}.aps-value span{display:block;color:var(--text-muted,#6b7280);font-size:10px;font-weight:700}.aps-value b{display:block;margin-top:4px;font-size:13px;overflow-wrap:anywhere}.aps-actions{display:flex;gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid var(--border-color,#edf0f2)}.aps-actions .btn{min-height:39px;border-radius:9px;font-weight:700}.aps-note{padding:12px 14px;border-radius:12px;background:#f1f7ff;border:1px solid #cfe3ff;color:#28527a;font-size:12px;line-height:1.8}.aps-empty,.aps-error{padding:38px 18px;text-align:center;border:1px dashed var(--border-color,#d5dce3);border-radius:14px;color:var(--text-muted,#6b7280);background:var(--subtle-fg,#fafafa)}.aps-error{border-style:solid;border-color:#f5b7b1;background:#fff5f4;color:#9f2d20}.aps-audit{display:grid;gap:8px;max-height:480px;overflow:auto}.aps-audit-item{padding:11px;border:1px solid var(--border-color,#e5e7eb);border-radius:11px}.aps-audit-head{display:flex;justify-content:space-between;gap:8px;font-weight:800}.aps-audit-meta{margin-top:5px;color:var(--text-muted,#6b7280);font-size:12px}
            @media(max-width:950px){.aps-sections{grid-template-columns:1fr 1fr}.aps-section:last-child{grid-column:span 2}}
            @media(max-width:620px){.aps-sections{grid-template-columns:1fr}.aps-section:last-child{grid-column:span 1}.aps-section-head{display:block}.aps-permission{margin-top:8px}.aps-actions .btn{width:100%}}
        `;
        document.head.appendChild(style);
    }

    function load() {
        const currentRequest = ++requestId;
        $body.html(`<div class="aps-empty">${__("جاري تحميل إعدادات المعمل...")}</div>`);
        return call(METHODS.get).then(data => {
            if (currentRequest !== requestId) return;
            current = data || {};
            render();
        }).catch(error => {
            if (currentRequest !== requestId) return;
            $body.html(`<div class="aps-error">${esc(error && error.message ? error.message : __("تعذر تحميل إعدادات المعمل."))}</div>`);
        });
    }

    function sectionEditable(section) {
        return Boolean(
            current.permissions &&
            current.permissions.sections &&
            current.permissions.sections[section] &&
            current.permissions.sections[section].editable
        );
    }

    function render() {
        const values = current.values || current;
        $body.html(`
            <div class="aps-shell">
                <section class="aps-hero">
                    <h2>${__("الإعدادات الافتراضية للمعمل")}</h2>
                    <p>${__("تُطبق القيم على الطلبات الجديدة. كل قسم له صلاحية مستقلة، وكل تعديل يُسجل مع المستخدم والحقول المتغيرة.")}</p>
                </section>
                <section class="aps-sections">
                    ${sectionCard("cutting", __("القص والمحسّن"), __("الهندسة الافتراضية وخوارزمية التوزيع وحدود البحث."), [
                        [__("Kerf الافتراضي (مم)"), values.default_kerf_mm],
                        [__("هامش التشذيب (مم)"), values.default_trim_margin_mm],
                        [__("الخوارزمية"), __(values.default_packing_mode || "—")],
                        [__("نوع آلة القص"), __(values.default_cutting_machine_type || "—")],
                        [__("مهلة التحسين (ث)"), values.default_optimization_time_limit_sec],
                        [__("حد القطع للبحث الأمثل"), values.optimal_search_piece_limit],
                    ])}
                    ${sectionCard("costing", __("التكلفة الافتراضية"), __("أجرة القص ورسوم الدرف الخاصة وهوامشها الافتراضية."), [
                        [__("أجرة القص / لوح"), `${esc(values.default_cutting_cost_per_board_usd)} USD`],
                        [__("رسم التصميم الخاص"), `${esc(values.default_special_design_fee_usd)} USD`],
                        [__("رسم CNC الخاص"), `${esc(values.default_special_cnc_fee_usd)} USD`],
                        [__("رسم القشاط اليدوي"), `${esc(values.default_special_manual_edge_fee_usd)} USD`],
                        [__("هامش الدرف الخاصة"), `${esc(values.default_special_margin_percent)}%`],
                    ])}
                    ${sectionCard("production", __("ضوابط الإنتاج"), __("المسار الافتراضي والاستثناءات التشغيلية الحساسة."), [
                        [__("مسار الإنتاج الافتراضي"), values.default_production_routing || "—"],
                        [__("تجاوز تسلسل المراحل"), values.allow_stage_override ? __("مسموح") : __("غير مسموح")],
                        [__("اعتماد قطع غير موزعة"), values.allow_unplaced_approval ? __("مسموح") : __("غير مسموح")],
                    ])}
                </section>
                <div class="aps-note">${__("لا يمكن تعديل سجل الإعدادات مباشرة من Form. جميع التغييرات تمر عبر هذه الواجهة وسياسة الصلاحيات وسجل التدقيق.")}</div>
            </div>
        `);
        $body.find(".aps-edit").on("click", event => openSectionDialog(event.currentTarget.dataset.section));
    }

    function sectionCard(key, title, description, rows) {
        const editable = sectionEditable(key);
        return `
            <article class="aps-section">
                <div class="aps-section-head">
                    <div><h3>${title}</h3><div class="aps-section-desc">${description}</div></div>
                    <span class="aps-permission ${editable ? "" : "readonly"}">${editable ? __("قابل للتعديل") : __("عرض فقط")}</span>
                </div>
                <div class="aps-values">${rows.map(row => `<div class="aps-value"><span>${row[0]}</span><b>${row[1] === undefined || row[1] === null ? "—" : row[1]}</b></div>`).join("")}</div>
                ${editable ? `<div class="aps-actions"><button class="btn btn-primary aps-edit" data-section="${key}">${__("تعديل هذا القسم")}</button></div>` : ""}
            </article>
        `;
    }

    function openSectionDialog(section) {
        if (!sectionEditable(section)) return;
        const values = current.values || current;
        const fields = section === "cutting" ? [
            {fieldname:"default_packing_mode",fieldtype:"Select",label:__("خوارزمية التوزيع"),options:(current.packing_options || []).join("\n"),default:values.default_packing_mode,reqd:1},
            {fieldname:"default_cutting_machine_type",fieldtype:"Select",label:__("نوع آلة القص"),options:(current.machine_options || []).join("\n"),default:values.default_cutting_machine_type,reqd:1},
            {fieldname:"default_kerf_mm",fieldtype:"Float",label:__("Kerf الافتراضي (مم)"),default:values.default_kerf_mm,reqd:1},
            {fieldname:"default_trim_margin_mm",fieldtype:"Float",label:__("هامش التشذيب (مم)"),default:values.default_trim_margin_mm,reqd:1},
            {fieldname:"default_optimization_time_limit_sec",fieldtype:"Float",label:__("مهلة التحسين (ثانية)"),default:values.default_optimization_time_limit_sec,reqd:1},
            {fieldname:"optimal_search_piece_limit",fieldtype:"Int",label:__("حد القطع للبحث الأمثل"),default:values.optimal_search_piece_limit,reqd:1},
        ] : section === "costing" ? [
            {fieldname:"default_cutting_cost_per_board_usd",fieldtype:"Currency",label:__("أجرة القص لكل لوح (USD)"),default:values.default_cutting_cost_per_board_usd,reqd:1},
            {fieldname:"default_special_design_fee_usd",fieldtype:"Currency",label:__("رسم التصميم الخاص / قطعة"),default:values.default_special_design_fee_usd,reqd:1},
            {fieldname:"default_special_cnc_fee_usd",fieldtype:"Currency",label:__("رسم CNC الخاص / قطعة"),default:values.default_special_cnc_fee_usd,reqd:1},
            {fieldname:"default_special_manual_edge_fee_usd",fieldtype:"Currency",label:__("رسم القشاط اليدوي / قطعة"),default:values.default_special_manual_edge_fee_usd,reqd:1},
            {fieldname:"default_special_margin_percent",fieldtype:"Percent",label:__("هامش الدرف الخاصة"),default:values.default_special_margin_percent,reqd:1},
        ] : [
            {fieldname:"default_production_routing",fieldtype:"Select",label:__("مسار الإنتاج الافتراضي"),options:(current.routing_options || []).join("\n"),default:values.default_production_routing,reqd:1},
            {fieldname:"allow_stage_override",fieldtype:"Check",label:__("السماح بتجاوز تسلسل المراحل"),default:values.allow_stage_override},
            {fieldname:"allow_unplaced_approval",fieldtype:"Check",label:__("السماح الاستثنائي باعتماد قطع غير موزعة"),default:values.allow_unplaced_approval},
        ];
        const dialog = new frappe.ui.Dialog({
            title: section === "cutting" ? __("تعديل القص والمحسّن") : section === "costing" ? __("تعديل التكلفة الافتراضية") : __("تعديل ضوابط الإنتاج"),
            fields,
            primary_action_label: __("حفظ التغييرات"),
            primary_action(payload) {
                dialog.get_primary_btn().prop("disabled", true);
                call(METHODS.update, {values: JSON.stringify(payload)}, __("جاري حفظ الإعدادات...")).then(data => {
                    current = data || {};
                    dialog.hide();
                    render();
                    frappe.show_alert({message:__("تم تحديث إعدادات المعمل."),indicator:"green"});
                }).catch(error => {
                    frappe.msgprint({title:__("تعذر الحفظ"),message:esc(error && error.message ? error.message : __("حدث خطأ غير متوقع.")),indicator:"red"});
                }).finally(() => dialog.get_primary_btn().prop("disabled", false));
            },
        });
        dialog.show();
    }

    function openAudit() {
        const dialog = new frappe.ui.Dialog({
            title: __("سجل تغييرات إعدادات المعمل"),
            size: "large",
            fields: [{fieldname:"audit_html",fieldtype:"HTML"}],
        });
        dialog.fields_dict.audit_html.$wrapper.html(`<div class="aps-empty">${__("جاري تحميل السجل...")}</div>`);
        dialog.show();
        call(METHODS.audit, {limit:50}).then(rows => {
            const records = Array.isArray(rows) ? rows : [];
            const html = records.length ? `<div class="aps-audit">${records.map(row => `
                <div class="aps-audit-item">
                    <div class="aps-audit-head"><span>${esc(row.action)}</span><span>${esc(row.changed_on)}</span></div>
                    <div class="aps-audit-meta">${__("بواسطة")}: ${esc(row.changed_by)} · ${esc(row.source || "")}</div>
                    ${row.changed_fields ? `<div class="aps-audit-meta">${__("الحقول")}: ${esc(row.changed_fields)}</div>` : ""}
                </div>
            `).join("")}</div>` : `<div class="aps-empty">${__("لا توجد تغييرات مسجلة.")}</div>`;
            dialog.fields_dict.audit_html.$wrapper.html(html);
        }).catch(error => {
            dialog.fields_dict.audit_html.$wrapper.html(`<div class="aps-error">${esc(error && error.message ? error.message : __("تعذر تحميل السجل."))}</div>`);
        });
    }
};
