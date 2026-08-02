frappe.pages["factory-master-data"].on_page_load = function (wrapper) {
    "use strict";

    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("البيانات الأساسية للمعمل"),
        single_column: true,
    });
    const $main = $(wrapper).find(".layout-main-section");
    const state = {
        data: null,
        tab: "routings",
        search: "",
        requestId: 0,
    };
    const METHODS = Object.freeze({
        load: "almdina_erp.almdina_erp.services.master_data_service.get_master_data_console",
        toggle: "almdina_erp.almdina_erp.services.master_data_service.set_master_data_disabled",
        remove: "almdina_erp.almdina_erp.services.master_data_service.delete_master_data_record",
    });

    injectStyles();
    page.add_inner_button(__("تحديث"), load, null, "refresh");
    load();

    function esc(value) {
        const text = value === null || value === undefined ? "" : String(value);
        return frappe.utils && frappe.utils.escape_html
            ? frappe.utils.escape_html(text)
            : $("<div>").text(text).html();
    }

    function can(capability) {
        return Boolean(state.data && state.data.permissions && state.data.permissions[capability]);
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
        if (document.getElementById("almdina-master-data-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-master-data-style";
        style.textContent = `
            .amd-shell{direction:rtl;display:grid;gap:14px;padding-bottom:32px}
            .amd-hero{padding:18px;border:1px solid var(--border-color,#e5e7eb);border-radius:16px;background:linear-gradient(135deg,var(--fg-color,#fff),var(--subtle-fg,#f7f9fb))}.amd-hero h2{margin:0 0 6px;font-size:21px;font-weight:800}.amd-hero p{margin:0;color:var(--text-muted,#6b7280);line-height:1.8}
            .amd-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.amd-stat{padding:13px;border:1px solid var(--border-color,#e5e7eb);border-radius:13px;background:var(--fg-color,#fff)}.amd-stat span{display:block;font-size:11px;font-weight:700;color:var(--text-muted,#6b7280)}.amd-stat b{display:block;font-size:24px;margin-top:5px}
            .amd-toolbar{position:sticky;top:58px;z-index:12;display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px;border:1px solid var(--border-color,#e5e7eb);border-radius:13px;background:var(--fg-color,#fff);box-shadow:0 4px 16px rgba(0,0,0,.04)}.amd-tabs{display:flex;gap:7px;flex-wrap:wrap}.amd-tab{min-height:40px;border:1px solid var(--border-color,#dfe3e8);border-radius:9px;background:var(--control-bg,#fff);padding:7px 13px;font-weight:700}.amd-tab.is-active{background:var(--primary,#2490ef);color:#fff;border-color:var(--primary,#2490ef)}.amd-search{margin-inline-start:auto;min-width:240px;min-height:40px;border:1px solid var(--border-color,#dfe3e8);border-radius:9px;padding:7px 11px;background:var(--control-bg,#fff)}
            .amd-actions{display:flex;flex-wrap:wrap;gap:8px}.amd-actions .btn{min-height:38px;border-radius:9px;font-weight:700}.amd-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.amd-card{padding:15px;border:1px solid var(--border-color,#e5e7eb);border-radius:15px;background:var(--fg-color,#fff);box-shadow:0 2px 8px rgba(0,0,0,.035)}.amd-card-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.amd-card h3{margin:0;font-size:17px;font-weight:800}.amd-sub{margin-top:4px;color:var(--text-muted,#6b7280);font-size:12px}.amd-badges{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.amd-badge{display:inline-flex;padding:4px 9px;border-radius:999px;background:var(--subtle-fg,#f3f5f7);font-size:11px;font-weight:700}.amd-badge.ok{background:#e8f7ee;color:#18794e}.amd-badge.off{background:#fdecec;color:#b42318}.amd-stages{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.amd-stage{padding:5px 8px;border-radius:8px;border:1px solid var(--border-color,#e5e7eb);font-size:11px}.amd-meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:12px}.amd-meta div{padding:8px;border-radius:9px;background:var(--subtle-fg,#f7f8fa)}.amd-meta span{display:block;font-size:10px;color:var(--text-muted,#6b7280)}.amd-meta b{display:block;margin-top:3px;font-size:12px;overflow-wrap:anywhere}.amd-card .amd-actions{margin-top:13px;padding-top:12px;border-top:1px solid var(--border-color,#edf0f2)}
            .amd-audit{display:grid;gap:8px}.amd-audit-item{padding:11px;border:1px solid var(--border-color,#e5e7eb);border-radius:11px;background:var(--fg-color,#fff)}.amd-audit-head{display:flex;justify-content:space-between;gap:8px;font-weight:800}.amd-audit-meta{margin-top:5px;color:var(--text-muted,#6b7280);font-size:12px}.amd-empty,.amd-loading,.amd-error{padding:36px 18px;text-align:center;border:1px dashed var(--border-color,#d7dde3);border-radius:14px;color:var(--text-muted,#6b7280);background:var(--subtle-fg,#fafafa)}.amd-error{border-style:solid;border-color:#f5b7b1;background:#fff5f4;color:#9f2d20}
            @media(max-width:900px){.amd-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.amd-grid{grid-template-columns:1fr}.amd-meta{grid-template-columns:repeat(2,minmax(0,1fr))}}
            @media(max-width:600px){.amd-toolbar{position:static}.amd-search{order:3;width:100%;min-width:0;margin-inline-start:0}.amd-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.amd-actions .btn{flex:1 1 calc(50% - 8px)}}
        `;
        document.head.appendChild(style);
    }

    function load() {
        const requestId = ++state.requestId;
        $main.html(`<div class="amd-loading">${__("جاري تحميل البيانات الأساسية...")}</div>`);
        return call(METHODS.load).then(data => {
            if (requestId !== state.requestId) return;
            state.data = data || {};
            if (!can("view_production_routings")) state.tab = "edges";
            if (!can("view_edge_banding_types") && state.tab === "edges") state.tab = "routings";
            render();
        }).catch(error => {
            if (requestId !== state.requestId) return;
            $main.html(`<div class="amd-error">${esc(error && error.message ? error.message : __("تعذر تحميل البيانات الأساسية."))}</div>`);
        });
    }

    function render() {
        const summary = state.data.summary || {};
        $main.html(`
            <div class="amd-shell">
                <section class="amd-hero">
                    <h2>${__("إدارة بيانات المعمل الأساسية")}</h2>
                    <p>${__("المسارات وأنواع القشاط محمية بصلاحيات مستقلة، وكل تغيير يُسجل في سجل تدقيق غير قابل للتعديل.")}</p>
                </section>
                <section class="amd-summary">
                    ${stat(__("مسارات الإنتاج"), summary.routings || 0)}
                    ${stat(__("المسارات المفعلة"), summary.active_routings || 0)}
                    ${stat(__("أنواع القشاط"), summary.edge_types || 0)}
                    ${stat(__("الأنواع المفعلة"), summary.active_edge_types || 0)}
                </section>
                ${toolbarHtml()}
                <section>${contentHtml()}</section>
            </div>
        `);
        bind();
    }

    function stat(label, value) {
        return `<div class="amd-stat"><span>${label}</span><b>${esc(value)}</b></div>`;
    }

    function toolbarHtml() {
        const tabs = [];
        if (can("view_production_routings")) tabs.push(`<button class="amd-tab ${state.tab === "routings" ? "is-active" : ""}" data-tab="routings">${__("مسارات الإنتاج")}</button>`);
        if (can("view_edge_banding_types")) tabs.push(`<button class="amd-tab ${state.tab === "edges" ? "is-active" : ""}" data-tab="edges">${__("أنواع القشاط")}</button>`);
        tabs.push(`<button class="amd-tab ${state.tab === "audit" ? "is-active" : ""}" data-tab="audit">${__("سجل التغييرات")}</button>`);
        const create = state.tab === "routings" && can("create_production_routings")
            ? `<button class="btn btn-primary amd-create" data-doctype="Production Routing">${__("إضافة مسار")}</button>`
            : state.tab === "edges" && can("create_edge_banding_types")
                ? `<button class="btn btn-primary amd-create" data-doctype="Edge Banding Type">${__("إضافة نوع قشاط")}</button>`
                : "";
        return `
            <div class="amd-toolbar">
                <div class="amd-tabs">${tabs.join("")}</div>
                <input class="amd-search" type="search" value="${esc(state.search)}" placeholder="${__("بحث في القسم الحالي...")}">
                <div class="amd-actions">${create}</div>
            </div>
        `;
    }

    function contentHtml() {
        if (state.tab === "audit") return auditHtml();
        const rows = state.tab === "routings" ? (state.data.routings || []) : (state.data.edge_types || []);
        const query = state.search.toLowerCase();
        const filtered = rows.filter(row => JSON.stringify(row).toLowerCase().includes(query));
        if (!filtered.length) return `<div class="amd-empty">${__("لا توجد بيانات مطابقة.")}</div>`;
        return `<div class="amd-grid">${filtered.map(row => state.tab === "routings" ? routingCard(row) : edgeCard(row)).join("")}</div>`;
    }

    function statusBadge(disabled) {
        return `<span class="amd-badge ${disabled ? "off" : "ok"}">${disabled ? __("معطّل") : __("مفعّل")}</span>`;
    }

    function routingCard(row) {
        const stages = (row.stages || []).map(stage => `<span class="amd-stage">${esc(stage.sequence)} · ${esc(__(stage.stage_type || ""))}</span>`).join("");
        return `
            <article class="amd-card">
                <div class="amd-card-head"><div><h3>${esc(row.label)}</h3><div class="amd-sub">${esc(row.name)}</div></div>${statusBadge(row.disabled)}</div>
                <div class="amd-stages">${stages || `<span class="text-muted">${__("لا توجد مراحل")}</span>`}</div>
                <div class="amd-meta">
                    <div><span>${__("عدد المراحل")}</span><b>${esc((row.stages || []).length)}</b></div>
                    <div><span>${__("آخر تعديل")}</span><b>${esc(row.modified || "—")}</b></div>
                    <div><span>${__("بواسطة")}</span><b>${esc(row.modified_by || "—")}</b></div>
                </div>
                ${recordActions("Production Routing", row, "edit_production_routings", "delete_production_routings")}
            </article>
        `;
    }

    function edgeCard(row) {
        return `
            <article class="amd-card">
                <div class="amd-card-head"><div><h3>${esc(row.label)}</h3><div class="amd-sub">${esc(row.english_name || row.name)}</div></div>${statusBadge(row.disabled)}</div>
                <div class="amd-badges">
                    ${row.edge_color ? `<span class="amd-badge">${esc(row.edge_color)}</span>` : ""}
                    ${row.finish_type ? `<span class="amd-badge">${esc(__(row.finish_type))}</span>` : ""}
                    ${row.application_method ? `<span class="amd-badge">${esc(__(row.application_method))}</span>` : ""}
                </div>
                <div class="amd-meta">
                    <div><span>${__("العرض (سم)")}</span><b>${esc(row.width_cm)}</b></div>
                    <div><span>${__("السماكة (مم)")}</span><b>${esc(row.thickness_mm)}</b></div>
                    <div><span>${__("السعر / متر")}</span><b>${esc(row.rate_usd_per_meter)} USD</b></div>
                </div>
                ${recordActions("Edge Banding Type", row, "edit_edge_banding_types", "delete_edge_banding_types")}
            </article>
        `;
    }

    function recordActions(doctype, row, editCapability, deleteCapability) {
        const buttons = [`<button class="btn btn-default amd-open" data-doctype="${doctype}" data-name="${esc(row.name)}">${__("فتح")}</button>`];
        if (can(editCapability)) {
            buttons.push(`<button class="btn btn-default amd-toggle" data-doctype="${doctype}" data-name="${esc(row.name)}" data-disabled="${row.disabled ? 0 : 1}">${row.disabled ? __("تفعيل") : __("تعطيل")}</button>`);
        }
        if (can(deleteCapability)) {
            buttons.push(`<button class="btn btn-danger amd-delete" data-doctype="${doctype}" data-name="${esc(row.name)}">${__("حذف")}</button>`);
        }
        return `<div class="amd-actions">${buttons.join("")}</div>`;
    }

    function auditHtml() {
        const query = state.search.toLowerCase();
        const rows = (state.data.audit || []).filter(row => JSON.stringify(row).toLowerCase().includes(query));
        if (!rows.length) return `<div class="amd-empty">${__("لا توجد تغييرات مسجلة.")}</div>`;
        return `<div class="amd-audit">${rows.map(row => `
            <div class="amd-audit-item">
                <div class="amd-audit-head"><span>${esc(row.target_name)}</span><span>${esc(row.changed_on)}</span></div>
                <div class="amd-audit-meta">${esc(row.target_doctype)} · ${esc(row.action)} · ${__("بواسطة")}: ${esc(row.changed_by)}</div>
                ${row.changed_fields ? `<div class="amd-audit-meta">${__("الحقول")}: ${esc(row.changed_fields)}</div>` : ""}
            </div>
        `).join("")}</div>`;
    }

    function bind() {
        $main.find(".amd-tab").on("click", event => {
            state.tab = event.currentTarget.dataset.tab;
            state.search = "";
            render();
        });
        $main.find(".amd-search").on("input", event => {
            state.search = String(event.target.value || "").trim();
            const cursor = event.target.selectionStart;
            render();
            const input = $main.find(".amd-search").get(0);
            if (input) {
                input.focus();
                input.setSelectionRange(cursor, cursor);
            }
        });
        $main.find(".amd-create").on("click", event => frappe.new_doc(event.currentTarget.dataset.doctype));
        $main.find(".amd-open").on("click", event => frappe.set_route("Form", event.currentTarget.dataset.doctype, event.currentTarget.dataset.name));
        $main.find(".amd-toggle").on("click", event => toggleRecord(event.currentTarget.dataset));
        $main.find(".amd-delete").on("click", event => deleteRecord(event.currentTarget.dataset));
    }

    function toggleRecord(dataset) {
        const disabled = Number(dataset.disabled || 0);
        const message = disabled ? __("هل تريد تعطيل هذا السجل؟") : __("هل تريد تفعيل هذا السجل؟");
        frappe.confirm(message, () => {
            call(METHODS.toggle, {
                doctype: dataset.doctype,
                name: dataset.name,
                disabled,
            }, __("جاري حفظ الحالة...")).then(() => {
                frappe.show_alert({message:__("تم تحديث الحالة."),indicator:"green"});
                load();
            });
        });
    }

    function deleteRecord(dataset) {
        frappe.confirm(__("سيُرفض الحذف إذا كان السجل مستخدمًا في طلب أو إعداد. هل تريد المتابعة؟"), () => {
            call(METHODS.remove, {
                doctype: dataset.doctype,
                name: dataset.name,
            }, __("جاري التحقق والحذف...")).then(() => {
                frappe.show_alert({message:__("تم حذف السجل."),indicator:"green"});
                load();
            });
        });
    }
};
