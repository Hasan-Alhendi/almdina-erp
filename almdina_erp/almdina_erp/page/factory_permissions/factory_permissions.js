frappe.pages["factory-permissions"].on_page_load = function (wrapper) {
    "use strict";

    const METHODS = Object.freeze({
        console: "almdina_erp.almdina_erp.services.permission_management_service.get_permission_console",
        role: "almdina_erp.almdina_erp.services.permission_management_service.get_role_permissions",
        preview: "almdina_erp.almdina_erp.services.permission_management_service.preview_role_permissions",
        export: "almdina_erp.almdina_erp.services.permission_management_service.export_role_permissions",
        import: "almdina_erp.almdina_erp.services.permission_management_service.preview_permission_import",
        update: "almdina_erp.almdina_erp.services.permission_management_service.update_role_permissions",
    });

    const state = {
        catalog: [],
        roles: [],
        transfer: {},
        selectedRole: "",
        baseline: {},
        working: {},
        preview: null,
        roleRequest: 0,
        previewRequest: 0,
        transferRequest: 0,
        previewTimer: null,
        saving: false,
    };

    frappe.ui.make_app_page({
        parent: wrapper,
        title: __("إدارة صلاحيات المعمل"),
        single_column: true,
    });

    const $main = $(wrapper).find(".layout-main-section");
    injectStyles();
    renderShell();
    bindEvents();
    loadConsole();

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value || {}));
    }

    function stable(value) {
        return JSON.stringify(
            Object.keys(value || {})
                .sort()
                .reduce((result, key) => {
                    result[key] = value[key] === true;
                    return result;
                }, {})
        );
    }

    function isDirty() {
        return stable(state.baseline) !== stable(state.working);
    }

    function injectStyles() {
        if (document.getElementById("almdina-permission-console-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-permission-console-style";
        style.textContent = `
            .apc-shell{direction:rtl;padding-bottom:92px}.apc-hero{display:flex;justify-content:space-between;gap:20px;padding:20px;margin-bottom:14px;border:1px solid var(--border-color,#e5e7eb);border-radius:16px;background:linear-gradient(135deg,var(--fg-color,#fff),var(--subtle-fg,#f7f9fb))}.apc-hero h2{margin:0 0 6px;font-size:22px;font-weight:800}.apc-hero p{margin:0;max-width:780px;color:var(--text-muted,#6b7280);line-height:1.8}.apc-actor{min-width:210px;text-align:left;direction:ltr;font-size:12px}.apc-toolbar{display:grid;grid-template-columns:minmax(280px,1.1fr) minmax(300px,1fr) minmax(230px,.8fr);gap:12px;margin-bottom:14px}.apc-panel{border:1px solid var(--border-color,#e5e7eb);border-radius:14px;background:var(--fg-color,#fff);padding:15px}.apc-panel-title{font-size:13px;font-weight:800;margin-bottom:8px}.apc-role-tools{display:grid;grid-template-columns:minmax(150px,.7fr) minmax(190px,1fr);gap:8px}.apc-transfer-tools{display:flex;gap:8px}.apc-transfer-tools .btn{flex:1}.apc-input,.apc-select{width:100%;min-height:42px;border:1px solid var(--border-color,#d8dee4);border-radius:10px;padding:8px 11px;background:var(--control-bg,#fff);color:var(--text-color,#1f2937);outline:none}.apc-input:focus,.apc-select:focus{border-color:var(--primary,#2490ef);box-shadow:0 0 0 2px rgba(36,144,239,.12)}.apc-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.apc-stat{padding:10px;border-radius:10px;background:var(--subtle-fg,#f6f8fa);text-align:center}.apc-stat strong{display:block;font-size:19px}.apc-content{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(290px,.7fr);gap:14px;align-items:start}.apc-groups{display:grid;gap:12px}.apc-group{border:1px solid var(--border-color,#e5e7eb);border-radius:14px;overflow:hidden;background:var(--fg-color,#fff)}.apc-group-head{padding:13px 15px;background:var(--subtle-fg,#f8fafb);border-bottom:1px solid var(--border-color,#e5e7eb)}.apc-group-head h4{margin:0 0 3px;font-size:15px;font-weight:800}.apc-group-head p{margin:0;font-size:12px;color:var(--text-muted,#6b7280)}.apc-capability{display:grid;grid-template-columns:46px minmax(0,1fr) auto;gap:11px;align-items:center;padding:12px 15px;border-bottom:1px solid var(--border-color,#eef1f4)}.apc-capability:last-child{border-bottom:0}.apc-capability-title{display:block;font-size:13px;font-weight:800;margin-bottom:2px}.apc-capability-description{display:block;font-size:12px;line-height:1.6;color:var(--text-muted,#6b7280)}.apc-switch{position:relative;width:42px;height:24px;display:inline-block;margin:0}.apc-switch input{opacity:0;width:0;height:0}.apc-slider{position:absolute;inset:0;cursor:pointer;border-radius:24px;background:#c8d0d8;transition:.18s}.apc-slider:before{content:"";position:absolute;width:18px;height:18px;right:3px;top:3px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2);transition:.18s}.apc-switch input:checked+.apc-slider{background:var(--primary,#2490ef)}.apc-switch input:checked+.apc-slider:before{transform:translateX(-18px)}.apc-switch input:focus-visible+.apc-slider{outline:2px solid var(--primary,#2490ef);outline-offset:2px}.apc-badges{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}.apc-badge{border-radius:999px;padding:3px 7px;font-size:10px;font-weight:800;white-space:nowrap}.apc-badge.standard{background:#edf2f7;color:#475569}.apc-badge.sensitive{background:#fff7df;color:#8a5b00}.apc-badge.critical{background:#ffe7e7;color:#a61b1b}.apc-side{position:sticky;top:58px;display:grid;gap:12px}.apc-chip-row{display:flex;flex-wrap:wrap;gap:6px}.apc-chip{border-radius:999px;padding:5px 9px;background:var(--subtle-fg,#f2f5f7);font-size:11px;font-weight:700}.apc-warning{padding:10px;border-radius:10px;background:#fff5e6;border:1px solid #ffd99a;color:#704600;font-size:12px;line-height:1.7}.apc-source{padding:9px;border-radius:10px;background:#edf7ff;border:1px solid #b9dcf7;color:#195475;font-size:12px;line-height:1.7}.apc-change{display:flex;justify-content:space-between;gap:8px;padding:7px 0;border-bottom:1px solid var(--border-color,#eef1f4);font-size:12px}.apc-change:last-child{border-bottom:0}.apc-audit-list{display:grid;gap:8px}.apc-audit-item{padding:9px;border-radius:9px;background:var(--subtle-fg,#f8fafb);font-size:11px;line-height:1.6}.apc-empty{padding:34px 18px;text-align:center;border:1px dashed var(--border-color,#d5dce3);border-radius:14px;color:var(--text-muted,#6b7280);background:var(--subtle-fg,#fafafa)}.apc-savebar{position:fixed;z-index:90;right:0;left:0;bottom:0;display:flex;justify-content:center;pointer-events:none;padding:10px 16px}.apc-savebar-inner{pointer-events:auto;width:min(760px,calc(100vw - 30px));display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border:1px solid var(--border-color,#dfe3e8);border-radius:14px;background:var(--fg-color,#fff);box-shadow:0 8px 30px rgba(0,0,0,.13)}.apc-save-actions{display:flex;gap:8px}.apc-dirty{font-size:12px;font-weight:700;color:var(--text-muted,#6b7280)}.apc-dirty.is-dirty{color:#8a5b00}@media(max-width:1100px){.apc-toolbar{grid-template-columns:1fr 1fr}.apc-toolbar .apc-summary-panel{grid-column:1/-1}}@media(max-width:900px){.apc-content{grid-template-columns:1fr}.apc-side{position:static;grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.apc-hero{display:block;padding:16px}.apc-actor{margin-top:12px;text-align:right}.apc-toolbar,.apc-role-tools,.apc-side{grid-template-columns:1fr}.apc-transfer-tools{flex-direction:column}.apc-capability{grid-template-columns:42px minmax(0,1fr)}.apc-badges{grid-column:2;justify-content:flex-start}.apc-savebar-inner{align-items:stretch;flex-direction:column}.apc-save-actions .btn{flex:1}}
        `;
        document.head.appendChild(style);
    }

    function renderShell() {
        $main.html(`
            <div class="apc-shell">
                <div class="apc-hero">
                    <div><h2>${__("مصفوفة صلاحيات Almdina")}</h2><p>${__("اختر الدور ثم امنحه الصلاحيات يدويًا من الصفر. لا توجد قوالب جاهزة ولا صلاحيات تلقائية. يمكن نقل مصفوفة موجودة عبر JSON بعد معاينتها، ولن يتم الحفظ تلقائيًا.")}</p></div>
                    <div class="apc-actor text-muted"></div>
                </div>
                <div class="apc-toolbar">
                    <div class="apc-panel"><div class="apc-panel-title">${__("اختر الدور")}</div><div class="apc-role-tools"><input type="search" class="apc-input apc-role-search" placeholder="${__("ابحث عن دور...")}"><select class="apc-select apc-role-select" aria-label="${__("الدور")}"></select></div></div>
                    <div class="apc-panel"><div class="apc-panel-title">${__("نقل مصفوفة الصلاحيات")}</div><div class="apc-transfer-tools"><button type="button" class="btn btn-default apc-export">${__("تصدير JSON")}</button><button type="button" class="btn btn-default apc-import">${__("استيراد JSON")}</button></div><div class="text-muted small mt-2">${__("الاستيراد يحمّل الصلاحيات للمعاينة فقط؛ الحفظ يبقى خطوة مستقلة.")}</div><input type="file" class="apc-import-file" accept="application/json,.json" hidden></div>
                    <div class="apc-panel apc-summary-panel"><div class="apc-panel-title">${__("ملخص الصلاحيات")}</div><div class="apc-stats"><div class="apc-stat"><strong class="apc-enabled-count">0</strong><span>${__("مفعلة")}</span></div><div class="apc-stat"><strong class="apc-critical-count">0</strong><span>${__("حرجة")}</span></div><div class="apc-stat"><strong class="apc-change-count">0</strong><span>${__("تغييرات")}</span></div></div></div>
                </div>
                <div class="apc-loading apc-empty">${__("جاري تحميل مصفوفة الصلاحيات...")}</div>
                <div class="apc-content" style="display:none"><div class="apc-groups"></div><aside class="apc-side"><div class="apc-panel apc-impact-panel"></div><div class="apc-panel apc-audit-panel"></div></aside></div>
            </div>
            <div class="apc-savebar" style="display:none"><div class="apc-savebar-inner"><div class="apc-dirty">${__("لا توجد تغييرات غير محفوظة")}</div><div class="apc-save-actions"><button type="button" class="btn btn-default apc-reset">${__("تراجع")}</button><button type="button" class="btn btn-primary apc-save">${__("حفظ الصلاحيات")}</button></div></div></div>
        `);
    }

    function bindEvents() {
        $main.on("input", ".apc-role-search", filterRoles);
        $main.on("change", ".apc-role-select", function () {
            const role = String($(this).val() || "");
            if (role && role !== state.selectedRole) requestRoleChange(role);
        });
        $main.on("change", ".apc-capability-input", onCapabilityChange);
        $main.on("click", ".apc-export", exportSelectedRole);
        $main.on("click", ".apc-import", () => $main.find(".apc-import-file").trigger("click"));
        $main.on("change", ".apc-import-file", importPermissionFile);
        $main.on("click", ".apc-reset", resetWorkingState);
        $main.on("click", ".apc-save", savePermissions);
    }

    function loadConsole() {
        return frappe.call({ method: METHODS.console, freeze: false }).then(
            response => {
                const data = response.message || {};
                state.catalog = Array.isArray(data.catalog) ? data.catalog : [];
                state.roles = Array.isArray(data.roles) ? data.roles : [];
                state.transfer = data.transfer || {};
                const actor = data.actor || {};
                $main.find(".apc-actor").html(`<div>${esc(actor.full_name || actor.user || "")}</div><div>${esc(actor.user || "")}</div>`);
                renderRoleOptions(state.roles);
                if (!state.roles.length) return showEmpty(__("لا توجد أدوار قابلة للإدارة."));
                loadRole(String(state.roles[0].name || ""));
            },
            error => showError(error, __("تعذر فتح إدارة الصلاحيات."))
        );
    }

    function renderRoleOptions(items) {
        const $select = $main.find(".apc-role-select").empty();
        items.forEach(role => {
            const suffix = role.desk_access ? "" : ` · ${__("بدون Desk")}`;
            $("<option>").attr("value", role.name).text(`${role.name}${suffix}`).appendTo($select);
        });
        if (state.selectedRole && items.some(role => role.name === state.selectedRole)) {
            $select.val(state.selectedRole);
        }
    }

    function filterRoles() {
        const query = String($(this).val() || "").trim().toLowerCase();
        renderRoleOptions(state.roles.filter(role => String(role.name || "").toLowerCase().includes(query)));
    }

    function requestRoleChange(role) {
        if (!isDirty()) return loadRole(role);
        frappe.confirm(
            __("لديك تغييرات غير محفوظة. هل تريد تجاهلها؟"),
            () => loadRole(role),
            () => $main.find(".apc-role-select").val(state.selectedRole)
        );
    }

    function loadRole(role) {
        const requestId = ++state.roleRequest;
        state.selectedRole = role;
        state.transferRequest += 1;
        $main.find(".apc-role-select").val(role);
        $main.find(".apc-content,.apc-savebar").hide();
        $main.find(".apc-loading").show().text(__("جاري تحميل صلاحيات الدور..."));
        return frappe.call({ method: METHODS.role, args: { role }, freeze: false }).then(
            response => {
                if (requestId !== state.roleRequest || role !== state.selectedRole) return;
                const data = response.message || {};
                state.baseline = clone(data.capabilities);
                state.working = clone(data.capabilities);
                state.preview = { capabilities: clone(state.working), changes: [], impact: data.impact || {} };
                renderPermissionGroups();
                renderImpact(state.preview);
                renderAudit(data.audit || []);
                syncDirtyState();
                $main.find(".apc-loading").hide();
                $main.find(".apc-content,.apc-savebar").show();
            },
            error => {
                if (requestId === state.roleRequest) showError(error, __("تعذر تحميل صلاحيات الدور."));
            }
        );
    }

    function renderPermissionGroups() {
        $main.find(".apc-groups").html(state.catalog.map(group => `
            <section class="apc-group"><div class="apc-group-head"><h4>${esc(group.label)}</h4><p>${esc(group.description)}</p></div><div>${(group.capabilities || []).map(renderCapability).join("")}</div></section>
        `).join("") || `<div class="apc-empty">${__("لا توجد صلاحيات مسجلة.")}</div>`);
    }

    function renderCapability(capability) {
        const risk = capability.risk === "critical"
            ? `<span class="apc-badge critical">${__("حرجة")}</span>`
            : capability.risk === "sensitive"
                ? `<span class="apc-badge sensitive">${__("حساسة")}</span>`
                : "";
        const standard = capability.standard
            ? `<span class="apc-badge standard">${__("صلاحية Frappe أساسية")}</span>`
            : "";
        return `<label class="apc-capability"><span class="apc-switch"><input type="checkbox" class="apc-capability-input" data-capability="${esc(capability.key)}" ${state.working[capability.key] === true ? "checked" : ""}><span class="apc-slider"></span></span><span><span class="apc-capability-title">${esc(capability.label)}</span><span class="apc-capability-description">${esc(capability.description)}</span></span><span class="apc-badges">${standard}${risk}</span></label>`;
    }

    function onCapabilityChange() {
        const key = String($(this).attr("data-capability") || "");
        state.working[key] = $(this).is(":checked");
        syncDirtyState();
        clearTimeout(state.previewTimer);
        state.previewTimer = setTimeout(() => {
            loadPreview().then(() => syncDirtyState());
        }, 180);
    }

    function loadPreview() {
        if (!state.selectedRole) return Promise.resolve(null);
        const requestId = ++state.previewRequest;
        const requestedRole = state.selectedRole;
        const requestedState = clone(state.working);
        return frappe.call({
            method: METHODS.preview,
            args: { role: requestedRole, capabilities: JSON.stringify(requestedState) },
            freeze: false,
        }).then(
            response => {
                if (requestId !== state.previewRequest || requestedRole !== state.selectedRole || stable(requestedState) !== stable(state.working)) return null;
                return applyPreview(response.message || {});
            },
            error => {
                if (requestId === state.previewRequest) {
                    frappe.show_alert({ message: error && error.message ? error.message : __("تعذر حساب أثر الصلاحيات."), indicator: "red" });
                }
                return null;
            }
        );
    }

    function applyPreview(data) {
        state.preview = data || {};
        state.working = clone(state.preview.capabilities || state.working);
        syncCheckboxes();
        renderImpact(state.preview);
        syncDirtyState();
        return state.preview;
    }

    function syncCheckboxes() {
        $main.find(".apc-capability-input").each(function () {
            const key = String($(this).attr("data-capability") || "");
            $(this).prop("checked", state.working[key] === true);
        });
    }

    function previewExternal(method, args, successMessage) {
        const requestId = ++state.transferRequest;
        const requestedRole = state.selectedRole;
        return frappe.call({ method, args, freeze: true, freeze_message: __("جاري التحقق من الصلاحيات...") }).then(
            response => {
                if (requestId !== state.transferRequest || requestedRole !== state.selectedRole) return null;
                const preview = applyPreview(response.message || {});
                frappe.show_alert({ message: successMessage, indicator: "green" }, 6);
                return preview;
            },
            error => frappe.msgprint({ title: __("تعذر تحميل الصلاحيات"), message: esc(error && error.message ? error.message : __("حدث خطأ غير متوقع.")), indicator: "red" })
        );
    }

    function exportSelectedRole() {
        if (!state.selectedRole) return;
        const requestedRole = state.selectedRole;
        frappe.call({ method: METHODS.export, args: { role: requestedRole }, freeze: true, freeze_message: __("جاري تجهيز ملف الصلاحيات...") }).then(
            response => {
                if (requestedRole !== state.selectedRole) return;
                const documentData = response.message || {};
                const blob = new Blob([JSON.stringify(documentData, null, 2)], { type: "application/json;charset=utf-8" });
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = `almdina-permissions-${requestedRole.replace(/[^a-zA-Z0-9_-]+/g, "-")}.json`;
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(url);
                frappe.show_alert({ message: __("تم تصدير ملف الصلاحيات."), indicator: "green" });
            },
            error => frappe.msgprint({ title: __("تعذر التصدير"), message: esc(error && error.message ? error.message : __("حدث خطأ غير متوقع.")), indicator: "red" })
        );
    }

    function importPermissionFile(event) {
        const input = event.currentTarget;
        const file = input.files && input.files[0];
        input.value = "";
        if (!file || !state.selectedRole) return;
        const maxBytes = Number(state.transfer.max_bytes || 131072);
        if (file.size > maxBytes) {
            frappe.msgprint({ title: __("ملف كبير جدًا"), message: __("حجم ملف الصلاحيات يتجاوز الحد المسموح."), indicator: "red" });
            return;
        }
        const reader = new FileReader();
        reader.onload = () => previewExternal(
            METHODS.import,
            { role: state.selectedRole, payload: String(reader.result || "") },
            __("تم التحقق من الملف وتحميله للمعاينة فقط. لن يتغير الدور قبل الحفظ.")
        );
        reader.onerror = () => frappe.msgprint({ title: __("تعذر قراءة الملف"), message: __("لم يتمكن المتصفح من قراءة ملف الصلاحيات."), indicator: "red" });
        reader.readAsText(file, "utf-8");
    }

    function renderImpact(data) {
        const impact = (data && data.impact) || {};
        const navigation = impact.navigation || {};
        const changes = Array.isArray(data && data.changes) ? data.changes : [];
        const workspaces = Array.isArray(navigation.workspaces) ? navigation.workspaces : [];
        const sections = navigation.sections || {};
        const labels = {
            orders: __("الطلبات"), costing: __("التكلفة"), planning: __("خطة القص"),
            drawing: __("الرسم"), production: __("الإنتاج"), quality: __("الجودة"),
            workforce: __("المستخدمون"), factory_settings: __("الإعدادات"),
            master_data: __("البيانات الأساسية"), administration: __("الإدارة"), reports: __("التقارير"),
        };
        const enabledSections = Object.keys(sections).filter(key => sections[key] === true);
        const home = navigation.home_page === "shop-floor-inbox"
            ? __("صالة الإنتاج")
            : navigation.home_page === "almdina-erp"
                ? __("واجهة Almdina الرئيسية")
                : __("لا يغيّر الصفحة الرئيسية");
        const warning = data && data.requires_self_lockout_confirmation
            ? `<div class="apc-warning">${__("هذا التغيير يزيل آخر صلاحية لديك لإدارة الصلاحيات. بعد الحفظ قد لا تستطيع العودة إلى الصفحة.")}</div>`
            : "";
        const source = data && data.source
            ? `<div class="apc-source">${data.source.kind === "import" ? __("المصدر: ملف JSON من الدور {0}", [esc(data.source.role || "")]) : __("مصدر خارجي للمعاينة")}</div>`
            : "";
        $main.find(".apc-impact-panel").html(`
            <div class="apc-panel-title">${__("أثر الصلاحيات")}</div>${warning}${source}
            <div class="mb-2"><strong>${__("الواجهة الافتراضية")}</strong><div class="text-muted small">${esc(home)}</div></div>
            <div class="mb-2"><strong>${__("مساحات العمل")}</strong><div class="apc-chip-row">${workspaces.map(item => `<span class="apc-chip">${esc(item)}</span>`).join("") || `<span class="text-muted small">${__("لا شيء")}</span>`}</div></div>
            <div class="mb-2"><strong>${__("الأقسام الظاهرة")}</strong><div class="apc-chip-row">${enabledSections.map(key => `<span class="apc-chip">${esc(labels[key] || key)}</span>`).join("") || `<span class="text-muted small">${__("لا شيء")}</span>`}</div></div>
            <div><strong>${__("التغييرات")}</strong><div>${changes.slice(0, 12).map(change => `<div class="apc-change"><span>${esc(change.label || change.key)}</span><span class="${change.after ? "on" : "off"}">${change.after ? __("منح") : __("إلغاء")}</span></div>`).join("") || `<div class="text-muted small mt-2">${__("لا توجد تغييرات.")}</div>`}</div></div>
        `);
        updateStats(changes);
    }

    function updateStats(changes) {
        const enabled = Object.values(state.working || {}).filter(Boolean).length;
        const criticalKeys = new Set(state.catalog.flatMap(group => group.capabilities || []).filter(item => item.risk === "critical").map(item => item.key));
        const critical = Object.keys(state.working || {}).filter(key => state.working[key] === true && criticalKeys.has(key)).length;
        $main.find(".apc-enabled-count").text(enabled);
        $main.find(".apc-critical-count").text(critical);
        $main.find(".apc-change-count").text((changes || []).length);
    }

    function renderAudit(rows) {
        $main.find(".apc-audit-panel").html(`
            <div class="apc-panel-title">${__("آخر التغييرات المحفوظة")}</div>
            <div class="apc-audit-list">${(rows || []).slice(0, 10).map(row => `<div class="apc-audit-item"><strong>${esc(row.changed_by || "")}</strong><div>${esc(row.changed_on || "")}</div><div>${esc(row.changed_capabilities || "")}</div></div>`).join("") || `<div class="text-muted small">${__("لا يوجد سجل بعد.")}</div>`}</div>
        `);
    }

    function syncDirtyState() {
        const dirty = isDirty();
        $main.find(".apc-dirty").toggleClass("is-dirty", dirty).text(dirty ? __("لديك تغييرات غير محفوظة") : __("لا توجد تغييرات غير محفوظة"));
        $main.find(".apc-save").prop("disabled", !dirty || state.saving);
        $main.find(".apc-reset").prop("disabled", !dirty || state.saving);
        $main.find(".apc-capability-input,.apc-role-select,.apc-role-search,.apc-export,.apc-import")
            .prop("disabled", state.saving);
        if (!state.preview) updateStats([]);
    }

    function resetWorkingState() {
        state.previewRequest += 1;
        state.transferRequest += 1;
        state.working = clone(state.baseline);
        state.preview = { capabilities: clone(state.working), changes: [], impact: (state.preview && state.preview.impact) || {} };
        syncCheckboxes();
        loadPreview();
        syncDirtyState();
    }

    function refreshRuntimePermissions() {
        const permissions = window.AlmdinaPermissions;
        if (!permissions || typeof permissions.refresh !== "function") {
            return Promise.resolve();
        }
        return Promise.resolve()
            .then(() => permissions.refresh())
            .catch(error => {
                console.error("Failed to refresh runtime permissions after save", error);
            });
    }

    function showOperationError(error, fallback) {
        const message = error && error.message ? error.message : fallback;
        frappe.show_alert({ message, indicator: "red" }, 7);
    }

    function savePermissions() {
        if (!state.selectedRole || !isDirty() || state.saving) return;
        const executeSave = async confirmSelfLockout => {
            const requestedRole = state.selectedRole;
            const requestedState = clone(state.working);
            state.saving = true;
            state.previewRequest += 1;
            state.transferRequest += 1;
            clearTimeout(state.previewTimer);
            state.previewTimer = null;
            syncDirtyState();
            try {
                const response = await frappe.call({
                    method: METHODS.update,
                    args: {
                        role: requestedRole,
                        capabilities: JSON.stringify(requestedState),
                        confirm_self_lockout: confirmSelfLockout ? 1 : 0,
                    },
                    freeze: true,
                    freeze_message: __("جاري حفظ الصلاحيات..."),
                });
                if (requestedRole !== state.selectedRole) return false;

                const data = response.message || {};
                state.baseline = clone(data.capabilities || requestedState);
                state.working = clone(state.baseline);
                state.preview = { capabilities: clone(state.working), changes: [], impact: data.impact || {} };
                renderPermissionGroups();
                renderImpact(state.preview);
                renderAudit(data.audit || []);
                syncDirtyState();
                await refreshRuntimePermissions();
                frappe.show_alert({ message: __("تم حفظ صلاحيات الدور."), indicator: "green" });
                return true;
            } catch (error) {
                showOperationError(error, __("تعذر حفظ الصلاحيات."));
                return false;
            } finally {
                state.saving = false;
                syncDirtyState();
            }
        };

        Promise.resolve(loadPreview()).then(preview => {
            if (!preview || !isDirty()) return;
            if (preview.requires_self_lockout_confirmation) {
                frappe.confirm(
                    __("سيؤدي هذا الحفظ إلى إزالة آخر صلاحية لديك لإدارة الصلاحيات. هل تريد المتابعة؟"),
                    () => executeSave(true)
                );
                return;
            }
            executeSave(false);
        });
    }

    function showEmpty(message) {
        $main.find(".apc-loading").show().text(message);
        $main.find(".apc-content,.apc-savebar").hide();
    }

    function showError(error, fallback) {
        const message = error && error.message ? error.message : fallback;
        showEmpty(message);
        frappe.show_alert({ message, indicator: "red" }, 7);
    }
};
