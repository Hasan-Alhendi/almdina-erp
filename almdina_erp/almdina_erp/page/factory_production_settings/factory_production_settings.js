frappe.pages["factory-production-settings"].on_page_load = function (wrapper) {
    "use strict";

    const METHODS = Object.freeze({
        get: "almdina_erp.almdina_erp.services.production_settings_service.get_production_settings",
        update: "almdina_erp.almdina_erp.services.production_settings_service.update_production_settings",
    });
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("إعدادات الإنتاج"),
        single_column: true,
    });
    const $body = $(wrapper).find(".layout-main-section");
    let current = {};
    let requestId = 0;

    injectStyles();
    load();

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function injectStyles() {
        if (document.getElementById("almdina-production-settings-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-production-settings-style";
        style.textContent = `
            .aps-shell{direction:rtl;max-width:980px}.aps-hero{padding:20px;border:1px solid var(--border-color,#e5e7eb);border-radius:16px;background:linear-gradient(135deg,var(--fg-color,#fff),var(--subtle-fg,#f7f9fb));margin-bottom:14px}.aps-hero h2{margin:0 0 5px;font-size:21px;font-weight:800}.aps-hero p{margin:0;color:var(--text-muted,#6b7280);line-height:1.8}.aps-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.aps-card{padding:15px;border:1px solid var(--border-color,#e5e7eb);border-radius:13px;background:var(--fg-color,#fff)}.aps-card.wide{grid-column:span 2}.aps-label{font-size:11px;color:var(--text-muted,#6b7280);margin-bottom:5px}.aps-value{font-size:16px;font-weight:800;overflow-wrap:anywhere}.aps-note{margin-top:14px;padding:11px 13px;border-radius:11px;background:#f1f7ff;border:1px solid #cfe3ff;color:#28527a;font-size:12px;line-height:1.7}.aps-empty{padding:36px 18px;text-align:center;border:1px dashed var(--border-color,#d5dce3);border-radius:14px;color:var(--text-muted,#6b7280);background:var(--subtle-fg,#fafafa)}@media(max-width:700px){.aps-grid{grid-template-columns:1fr 1fr}.aps-card.wide{grid-column:span 2}}@media(max-width:480px){.aps-grid{grid-template-columns:1fr}.aps-card.wide{grid-column:span 1}}
        `;
        document.head.appendChild(style);
    }

    function render(data) {
        current = data || {};
        $body.html(`
            <div class="aps-shell">
                <div class="aps-hero"><h2>${__("الإعدادات الافتراضية للإنتاج")}</h2><p>${__("تُطبّق هذه القيم على الطلبات الجديدة، ويمكن تعديلها فقط لمن يملك صلاحية إدارة إعدادات المعمل.")}</p></div>
                <div class="aps-grid">
                    <div class="aps-card wide"><div class="aps-label">${__("مسار الإنتاج الافتراضي")}</div><div class="aps-value">${esc(current.default_production_routing || "—")}</div></div>
                    <div class="aps-card"><div class="aps-label">${__("خوارزمية التوزيع")}</div><div class="aps-value">${esc(__(current.default_packing_mode || "—"))}</div></div>
                    <div class="aps-card"><div class="aps-label">${__("Kerf الافتراضي (مم)")}</div><div class="aps-value">${esc(current.default_kerf_mm)}</div></div>
                    <div class="aps-card"><div class="aps-label">${__("هامش التشذيب (مم)")}</div><div class="aps-value">${esc(current.default_trim_margin_mm)}</div></div>
                    <div class="aps-card"><div class="aps-label">${__("أجرة القص لكل لوح (USD)")}</div><div class="aps-value">${esc(current.default_cutting_cost_per_board_usd)}</div></div>
                </div>
                <div class="aps-note">${__("تجاوز تسلسل المراحل إعداد حساس ولا يُعدّل من هذه الشاشة المختصرة.")}</div>
            </div>
        `);
        page.clear_actions();
        page.set_primary_action(__("تعديل الإعدادات"), openDialog, "edit");
    }

    function renderError(error) {
        page.clear_actions();
        $body.html(`<div class="aps-shell"><div class="aps-empty">${esc(error && error.message ? error.message : __("تعذر تحميل إعدادات الإنتاج."))}</div></div>`);
    }

    function load() {
        const currentRequest = ++requestId;
        $body.html(`<div class="aps-shell"><div class="aps-empty">${__("جاري تحميل الإعدادات...")}</div></div>`);
        return frappe.call({ method: METHODS.get, freeze: false }).then(
            response => {
                if (currentRequest !== requestId) return;
                render(response.message || {});
            },
            error => {
                if (currentRequest !== requestId) return;
                renderError(error);
            }
        );
    }

    function openDialog() {
        const dialog = new frappe.ui.Dialog({
            title: __("تعديل إعدادات الإنتاج"),
            fields: [
                { fieldname: "default_production_routing", fieldtype: "Link", options: "Production Routing", label: __("مسار الإنتاج الافتراضي"), reqd: 1, default: current.default_production_routing },
                { fieldname: "default_packing_mode", fieldtype: "Select", options: (current.packing_options || ["Auto"]).join("\n"), label: __("خوارزمية التوزيع"), reqd: 1, default: current.default_packing_mode || "Auto" },
                { fieldname: "dimensions_section", fieldtype: "Section Break", label: __("إعدادات القص") },
                { fieldname: "default_kerf_mm", fieldtype: "Float", label: __("Kerf الافتراضي (مم)"), reqd: 1, default: current.default_kerf_mm },
                { fieldname: "default_trim_margin_mm", fieldtype: "Float", label: __("هامش التشذيب (مم)"), reqd: 1, default: current.default_trim_margin_mm },
                { fieldname: "default_cutting_cost_per_board_usd", fieldtype: "Currency", label: __("أجرة القص لكل لوح (USD)"), reqd: 1, default: current.default_cutting_cost_per_board_usd },
            ],
            primary_action_label: __("حفظ"),
            primary_action(values) {
                dialog.get_primary_btn().prop("disabled", true);
                frappe.call({
                    method: METHODS.update,
                    args: { values: JSON.stringify(values) },
                    freeze: true,
                    freeze_message: __("جاري حفظ إعدادات الإنتاج..."),
                }).then(
                    response => {
                        dialog.hide();
                        render(response.message || {});
                        frappe.show_alert({ message: __("تم تحديث إعدادات الإنتاج."), indicator: "green" });
                    },
                    error => {
                        dialog.get_primary_btn().prop("disabled", false);
                        frappe.msgprint({ title: __("تعذر الحفظ"), message: esc(error && error.message ? error.message : __("حدث خطأ غير متوقع.")), indicator: "red" });
                    }
                );
            },
        });
        dialog.show();
    }
};
