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
        rolePayload: null,
        preview: null,
        roleRequest: 0,
        previewRequest: 0,
        previewTimer: null,
        saving: false,
        roleFilter: "",
    };

    frappe.ui.make_app_page({
        parent: wrapper,
        title: __("إدارة الصلاحيات"),
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

    function normalizedFingerprint(value) {
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
        return normalizedFingerprint(state.baseline) !== normalizedFingerprint(state.working);
    }

    function injectStyles() {
        if (document.getElementById("almdina-permission-console-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-permission-console-style";
        style.textContent = `
            .apc-shell{direction:rtl;padding-bottom:96px;display:grid;gap:14px}.apc-hero{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;padding:19px 20px;border:1px solid var(--border-color,#e5e7eb);border-radius:16px;background:linear-gradient(135deg,var(--fg-color,#fff),var(--subtle-fg,#f7f9fb))}.apc-hero h2{margin:0 0 6px;font-size:22px;font-weight:800}.apc-hero p{margin:0;max-width:780px;color:var(--text-muted,#6b7280);line-height:1.8}.apc-actor{min-width:190px;text-align:left;direction:ltr;font-size:12px;color:var(--text-muted,#6b7280)}
            .apc-toolbar{display:grid;grid-template-columns:minmax(320px,1.35fr) minmax(260px,.9fr) minmax(260px,.8fr);gap:12px}.apc-panel{border:1px solid var(--border-color,#e5e7eb);border-radius:14px;background:var(--fg-color,#fff);padding:14px}.apc-panel-title{font-size:12px;font-weight:800;color:var(--text-muted,#6b7280);margin-bottom:8px}.apc-role-tools{display:grid;grid-template-columns:minmax(150px,.8fr) minmax(190px,1fr);gap:8px}.apc-transfer-tools{display:grid;grid-template-columns:1fr 1fr;gap:8px}.apc-input,.apc-select{width:100%;min-height:42px;border:1px solid var(--border-color,#d8dee4);border-radius:10px;padding:8px 11px;background:var(--control-bg,#fff);color:var(--text-color,#1f2937);outline:none}.apc-input:focus,.apc-select:focus{border-color:var(--primary,#2490ef);box-shadow:0 0 0 2px rgba(36,144,239,.12)}.apc-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.apc-stat{padding:9px;border-radius:10px;background:var(--subtle-fg,#f6f8fa);text-align:center}.apc-stat strong{display:block;font-size:19px}.apc-stat span{font-size:11px;color:var(--text-muted,#6b7280)}
            .apc-content{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(300px,.72fr);gap:14px;align-items:start}.apc-groups{display:grid;gap:12px}.apc-group{border:1px solid var(--border-color,#e5e7eb);border-radius:14px;overflow:hidden;background:var(--fg-color,#fff)}.apc-group-head{display:flex;justify-content:space-between;gap:12px;padding:13px 15px;background:var(--subtle-fg,#f8fafb);border-bottom:1px solid var(--border-color,#e5e7eb)}.apc-group-head h4{margin:0 0 3px;font-size:15px;font-weight:800}.apc-group-head p{margin:0;font-size:12px;color:var(--text-muted,#6b7280);line-height:1.6}.apc-group-count{white-space:nowrap;font-size:11px;font-weight:800;color:var(--text-muted,#6b7280)}.apc-capability{display:grid;grid-template-columns:46px minmax(0,1fr) auto;gap:11px;align-items:center;padding:12px 15px;border-bottom:1px solid var(--border-color,#eef1f4)}.apc-capability:last-child{border-bottom:0}.apc-capability-title{display:block;font-size:13px;font-weight:800;margin-bottom:2px}.apc-capability-description{display:block;font-size:12px;line-height:1.6;color:var(--text-muted,#6b7280)}.apc-switch{position:relative;width:42px;height:24px;display:inline-block;margin:0}.apc-switch input{opacity:0;width:0;height:0}.apc-slider{position:absolute;inset:0;cursor:pointer;border-radius:24px;background:#c8d0d8;transition:.18s}.apc-slider:before{content:"";position:absolute;width:18px;height:18px;right:3px;top:3px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2);transition:.18s}.apc-switch input:checked+.apc-slider{background:var(--primary,#2490ef)}.apc-switch input:checked+.apc-slider:before{transform:translateX(-18px)}.apc-switch input:focus-visible+.apc-slider{outline:2px solid var(--primary,#2490ef);outline-offset:2px}.apc-badges{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}.apc-badge{border-radius:999px;padding:3px 7px;font-size:10px;font-weight:800;white-space:nowrap}.apc-badge.standard{background:#edf2f7;color:#475569}.apc-badge.sensitive{background:#fff7df;color:#8a5b00}.apc-badge.critical{background:#ffe7e7;color:#a61b1b}
            .apc-side{position:sticky;top:58px;display:grid;gap:12px}.apc-side h4{margin:0 0 9px;font-size:14px;font-weight:800}.apc-chip-row{display:flex;flex-wrap:wrap;gap:6px}.apc-chip{border-radius:999px;padding:5px 9px;background:var(--subtle-fg,#f2f5f7);font-size:11px;font-weight:700}.apc-warning{padding:10px;border-radius:10px;background:#fff5e6;border:1px solid #ffd99a;color:#704600;font-size:12px;line-height:1.7}.apc-success{padding:10px;border-radius:10px;background:#eaf8ef;border:1px solid #b9e2c7;color:#18643a;font-size:12px;line-height:1.7}.apc-source{padding:9px;border-radius:10px;background:#edf7ff;border:1px solid #b9dcf7;color:#195475;font-size:12px;line-height:1.7}.apc-change{display:flex;justify-content:space-between;gap:8px;padding:7px 0;border-bottom:1px solid var(--border-color,#eef1f4);font-size:12px}.apc-change:last-child{border-bottom:0}.apc-change .on{color:#08783e;font-weight:800}.apc-change .off{color:#a61b1b;font-weight:800}.apc-audit-list{display:grid;gap:8px;max-height:360px;overflow:auto}.apc-audit-item{padding:9px;border-radius:9px;background:var(--subtle-fg,#f8fafb);font-size:11px;line-height:1.6}.apc-empty{padding:34px 18px;text-align:center;border:1px dashed var(--border-color,#d5dce3);border-radius:14px;color:var(--text-muted,#6b7280);background:var(--subtle-fg,#fafafa)}
            .apc-savebar{position:fixed;z-index:90;right:0;left:0;bottom:0;display:flex;justify-content:center;pointer-events:none;padding:10px 16px}.apc-savebar-inner{pointer-events:auto;width:min(780px,calc(100vw - 30px));display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border:1px solid var(--border-color,#dfe3e8);border-radius:14px;background:var(--fg-color,#fff);box-shadow:0 8px 30px rgba(0,0,0,.13)}.apc-save-actions{display:flex;gap:8px}.apc-dirty{font-size:12px;font-weight:700;color:var(--text-muted,#6b7280)}.apc-dirty.is-dirty{color:#8a5b00}
            @media(max-width:1100px){.apc-toolbar{grid-template-columns:1fr 1fr}.apc-summary-panel{grid-column:1/-1}}@media(max-width:900px){.apc-content{grid-template-columns:1fr}.apc-side{position:static;grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.apc-hero{display:block;padding:16px}.apc-actor{margin-top:12px;text-align:right}.apc-toolbar,.apc-role-tools,.apc-side{grid-template-columns:1fr}.apc-transfer-tools{grid-template-columns:1fr 1fr}.apc-capability{grid-template-columns:42px minmax(0,1fr)}.apc-badges{grid-column:2;justify-content:flex-start}.apc-savebar-inner{align-items:stretch;flex-direction:column}.apc-save-actions .btn{flex:1}}
        `;
        document.head.appendChild(style);
    }

    function renderShell() {
        $main.html(`
            <div class="apc-shell">
                <section class="apc-hero">
                    <div>
                        <h2>${__("الصلاحيات تُبنى من الصفر لكل دور")}</h2>
                        <p>${__("اختر الدور ثم فعّل فقط ما يحتاجه. لا توجد قوالب صلاحيات ولا صلاحيات مخفية تُنسخ تلقائيًا؛ الصلاحيات الفعلية للمستخدم هي اتحاد صلاحيات أدواره.")}</p>
                    </div>
                    <div class="apc-actor"></div>
                </section>
                <div class="apc-toolbar">
                    <div class="apc-panel">
                        <div class="apc-panel-title">${__("الدور الذي ستعدّل صلاحياته")}</div>
                        <div class="apc-role-tools">
                            <input type="search" class="apc-input apc-role-search" placeholder="${__("ابحث عن دور...")}">
                            <select class="apc-select apc-role-select" aria-label="${__("الدور")}"></select>
                        </div>
                    </div>
                    <div class="apc-panel">
                        <div class="apc-panel-title">${__("نسخة احتياطية / نقل الإعداد")}</div>
                        <div class="apc-transfer-tools">
                            <button type="button" class="btn btn-default apc-export">${__("تصدير JSON")}</button>
                            <button type="button" class="btn btn-default apc-import">${__("استيراد JSON")}</button>
                        </div>
                        <input type="file" class="apc-import-file" accept="application/json,.json" hidden>
                    </div>
                    <div class="apc-panel apc-summary-panel">
                        <div class="apc-panel-title">${__("ملخص الدور")}</div>
                        <div class="apc-stats">
                            <div class="apc-stat"><strong class="apc-enabled-count">0</strong><span>${__("مفعلة")}</span></div>
                            <div class="apc-stat"><strong class="apc-critical-count">0</strong><span>${__("حرجة")}</span></div>
                            <div class="apc-stat"><strong class="apc-change-count">0</strong><span>${__("تغييرات")}</span></div>
                        </div>
                    </div>
                </div>
                <div class="apc-loading apc-empty">${__("جاري تحميل مصفوفة الصلاحيات...")}</div>
                <div class="apc-content" style="display:none">
                    <div class="apc-groups"></div>
                    <aside class="apc-side">
                        <div class="apc-panel apc-impact-panel"></div>
                        <div class="apc-panel apc-audit-panel"></div>
                    </aside>
                </div>
            </div>
            <div class="apc-savebar" style="display:none">
                <div class="apc-savebar-inner">
                    <div class="apc-dirty">${__("لا توجد تغييرات غير محفوظة")}</div>
                    <div class="apc-save-actions">
                        <button type="button" class="btn btn-default apc-reset">${__("تراجع")}</button>
                        <button type="button" class="btn btn-primary apc-save">${__("حفظ الصلاحيات")}</button>
                    </div>
                </div>
            </div>
        `);
    }

    function bindEvents() {
        $main.on("input", ".apc-role-search", function () {
            state.roleFilter = String($(this).val() || "").trim().toLowerCase();
            renderRoleOptions();
        });
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
        return frappe.call({method: METHODS.console, freeze: false}).then(response => {
            const data = response.message || {};
            state.catalog = Array.isArray(data.catalog) ? data.catalog : [];
            state.roles = Array.isArray(data.roles) ? data.roles : [];
            state.transfer = data.transfer || {};
            const actor = data.actor || {};
            $main.find(".apc-actor").html(`<div>${esc(actor.full_name || actor.user || "")}</div><div>${esc(actor.user || "")}</div>`);
            renderRoleOptions();
            if (!state.roles.length) return showEmpty(__("لا توجد أدوار قابلة للإدارة."));
            const initial = data.selected && data.selected.role ? String(data.selected.role) : String(state.roles[0].name || "");
            if (data.selected && data.selected.role === initial) applyRolePayload(data.selected);
            else loadRole(initial);
        }).catch(error => showError(error, __("تعذر فتح إدارة الصلاحيات.")));
    }

    function filteredRoles() {
        if (!state.roleFilter) return state.roles;
        return state.roles.filter(role => String(role.name || "").toLowerCase().includes(state.roleFilter));
    }

    function renderRoleOptions() {
        const items = filteredRoles();
        const $select = $main.find(".apc-role-select").empty();
        if (!items.length) {
            $select.append(`<option value="">${__("لا توجد نتيجة")}</option>`);
            return;
        }
        items.forEach(role => {
            const name = String(role.name || "");
            const suffix = role.desk_access ? ` · ${__("Desk")}` : "";
            $select.append(`<option value="${esc(name)}">${esc(name + suffix)}</option>`);
        });
        const selectedVisible = items.some(role => String(role.name || "") === state.selectedRole);
        $select.val(selectedVisible ? state.selectedRole : String(items[0].name || ""));
    }

    function requestRoleChange(role) {
        if (!isDirty()) return loadRole(role);
        frappe.confirm(
            __("لديك تغييرات غير محفوظة على الدور الحالي. هل تريد تجاهلها وفتح الدور الآخر؟"),
            () => loadRole(role),
            () => renderRoleOptions()
        );
    }

    function loadRole(role) {
        const request = ++state.roleRequest;
        $main.find(".apc-content").hide();
        $main.find(".apc-loading").show().text(__("جاري تحميل صلاحيات الدور...") );
        return frappe.call({method: METHODS.role, args:{role}}).then(response => {
            if (request !== state.roleRequest) return;
            applyRolePayload(response.message || {});
        }).catch(error => {
            if (request !== state.roleRequest) return;
            showError(error, __("تعذر تحميل صلاحيات الدور."));
        });
    }

    function applyRolePayload(payload) {
        state.selectedRole = String(payload.role || "");
        state.rolePayload = payload;
        state.baseline = clone(payload.capabilities || {});
        state.working = clone(payload.capabilities || {});
        state.preview = {
            role: state.selectedRole,
            capabilities: clone(state.working),
            changes: [],
            impact: payload.impact || {},
            requires_self_lockout_confirmation: false,
            has_sensitive_changes: false,
        };
        renderRoleOptions();
        renderCapabilities();
        renderSide();
        updateSaveBar();
        $main.find(".apc-loading").hide();
        $main.find(".apc-content").show();
    }

    function renderCapabilities() {
        const groups = state.catalog.map(group => {
            const capabilities = Array.isArray(group.capabilities) ? group.capabilities : [];
            const enabledInGroup = capabilities.filter(item => state.working[item.key] === true).length;
            return `
                <section class="apc-group">
                    <header class="apc-group-head">
                        <div><h4>${esc(group.label || group.key)}</h4><p>${esc(group.description || "")}</p></div>
                        <div class="apc-group-count">${enabledInGroup}/${capabilities.length}</div>
                    </header>
                    <div>${capabilities.map(capabilityHtml).join("")}</div>
                </section>
            `;
        }).join("");
        $main.find(".apc-groups").html(groups || `<div class="apc-empty">${__("لا توجد صلاحيات معرفة في النظام.")}</div>`);
    }

    function capabilityHtml(item) {
        const checked = state.working[item.key] === true ? "checked" : "";
        const badges = [];
        if (item.standard) badges.push(`<span class="apc-badge standard">${__("Frappe")}</span>`);
        if (item.risk === "critical") badges.push(`<span class="apc-badge critical">${__("حرجة")}</span>`);
        else if (item.risk === "sensitive") badges.push(`<span class="apc-badge sensitive">${__("حساسة")}</span>`);
        return `
            <div class="apc-capability" data-capability="${esc(item.key)}">
                <label class="apc-switch" title="${esc(item.label || item.key)}">
                    <input class="apc-capability-input" type="checkbox" data-key="${esc(item.key)}" ${checked}>
                    <span class="apc-slider"></span>
                </label>
                <div><span class="apc-capability-title">${esc(item.label || item.key)}</span><span class="apc-capability-description">${esc(item.description || "")}</span></div>
                <div class="apc-badges">${badges.join("")}</div>
            </div>
        `;
    }

    function onCapabilityChange(event) {
        const key = String(event.currentTarget.dataset.key || "");
        if (!key) return;
        state.working[key] = event.currentTarget.checked === true;
        renderCapabilities();
        updateSaveBar();
        schedulePreview();
    }

    function schedulePreview() {
        clearTimeout(state.previewTimer);
        state.previewTimer = setTimeout(previewWorkingState, 220);
    }

    function previewWorkingState() {
        if (!state.selectedRole) return;
        const request = ++state.previewRequest;
        return frappe.call({
            method: METHODS.preview,
            args: {role:state.selectedRole, capabilities:state.working},
        }).then(response => {
            if (request !== state.previewRequest) return;
            state.preview = response.message || null;
            if (state.preview && state.preview.capabilities) state.working = clone(state.preview.capabilities);
            renderCapabilities();
            renderSide();
            updateSaveBar();
        }).catch(error => showError(error, __("تعذر معاينة أثر الصلاحيات."), false));
    }

    function renderSide() {
        const preview = state.preview || {};
        const impact = preview.impact || state.rolePayload?.impact || {};
        const changes = Array.isArray(preview.changes) ? preview.changes : [];
        $main.find(".apc-enabled-count").text(Number(impact.enabled_count || 0));
        $main.find(".apc-critical-count").text(Number(impact.critical_count || 0));
        $main.find(".apc-change-count").text(changes.length);

        const warnings = [];
        if (preview.requires_self_lockout_confirmation) warnings.push(`<div class="apc-warning">${__("هذا التغيير سيزيل آخر صلاحية لديك لإدارة الصلاحيات. سيطلب النظام تأكيدًا صريحًا قبل الحفظ.")}</div>`);
        if (preview.has_sensitive_changes) warnings.push(`<div class="apc-warning">${__("توجد تغييرات حساسة أو حرجة. راجعها قبل الحفظ.")}</div>`);
        const changeHtml = changes.length ? changes.map(change => `
            <div class="apc-change"><span>${esc(change.label || change.key)}</span><span class="${change.after ? "on" : "off"}">${change.after ? __("تفعيل") : __("إلغاء")}</span></div>
        `).join("") : `<div class="apc-success">${__("لا توجد تغييرات غير محفوظة على هذا الدور.")}</div>`;
        const source = preview.source && preview.source.kind === "import"
            ? `<div class="apc-source">${__("المعاينة الحالية جاءت من ملف JSON للدور")}: ${esc(preview.source.role || "")}</div>`
            : "";
        $main.find(".apc-impact-panel").html(`
            <h4>${__("أثر التعديل")}</h4>
            ${warnings.join("")}${source}
            <div style="margin-top:9px">${changeHtml}</div>
        `);

        const audits = Array.isArray(state.rolePayload?.audit) ? state.rolePayload.audit : [];
        $main.find(".apc-audit-panel").html(`
            <h4>${__("آخر تغييرات الدور")}</h4>
            <div class="apc-audit-list">${audits.length ? audits.map(item => `
                <div class="apc-audit-item"><b>${esc(item.changed_on || "")}</b><div>${esc(item.changed_by || "")}</div><div>${esc(item.changed_capabilities || "")}</div></div>
            `).join("") : `<div class="text-muted">${__("لا يوجد سجل تغييرات بعد.")}</div>`}</div>
        `);
    }

    function updateSaveBar() {
        const dirty = isDirty();
        const $bar = $(wrapper).find(".apc-savebar");
        $bar.toggle(Boolean(state.selectedRole));
        const $dirty = $bar.find(".apc-dirty");
        $dirty.toggleClass("is-dirty", dirty).text(dirty ? __("لديك تغييرات غير محفوظة") : __("لا توجد تغييرات غير محفوظة"));
        $bar.find(".apc-reset,.apc-save").prop("disabled", !dirty || state.saving);
    }

    function resetWorkingState() {
        state.working = clone(state.baseline);
        state.preview = {
            role: state.selectedRole,
            capabilities: clone(state.working),
            changes: [],
            impact: state.rolePayload?.impact || {},
            requires_self_lockout_confirmation: false,
            has_sensitive_changes: false,
        };
        renderCapabilities();
        renderSide();
        updateSaveBar();
    }

    function savePermissions() {
        if (!state.selectedRole || !isDirty() || state.saving) return;
        const preview = state.preview || {};
        const proceed = () => persistPermissions(Boolean(preview.requires_self_lockout_confirmation));
        if (preview.has_sensitive_changes || preview.requires_self_lockout_confirmation) {
            frappe.confirm(
                preview.requires_self_lockout_confirmation
                    ? __("هذا الحفظ قد يمنعك من فتح إدارة الصلاحيات مرة أخرى. هل تؤكد المتابعة؟")
                    : __("توجد تغييرات حساسة أو حرجة. هل تؤكد حفظها؟"),
                proceed
            );
        } else proceed();
    }

    function persistPermissions(confirmSelfLockout) {
        state.saving = true;
        updateSaveBar();
        frappe.call({
            method: METHODS.update,
            args: {
                role: state.selectedRole,
                capabilities: state.working,
                confirm_self_lockout: confirmSelfLockout ? 1 : 0,
            },
            freeze: true,
            freeze_message: __("جاري حفظ الصلاحيات...")
        }).then(response => {
            applyRolePayload(response.message || {});
            frappe.show_alert({message:__("تم حفظ صلاحيات الدور."),indicator:"green"});
        }).catch(error => showError(error, __("تعذر حفظ الصلاحيات."), false)).finally(() => {
            state.saving = false;
            updateSaveBar();
        });
    }

    function exportSelectedRole() {
        if (!state.selectedRole) return;
        frappe.call({method:METHODS.export,args:{role:state.selectedRole},freeze:true,freeze_message:__("جاري تجهيز ملف الصلاحيات...")}).then(response => {
            const documentData = response.message || {};
            const blob = new Blob([JSON.stringify(documentData, null, 2)], {type:"application/json;charset=utf-8"});
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = `almdina-permissions-${state.selectedRole.replace(/[^\w\u0600-\u06FF-]+/g,"-")}.json`;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(url);
        }).catch(error => showError(error, __("تعذر تصدير الصلاحيات."), false));
    }

    function importPermissionFile(event) {
        const input = event.currentTarget;
        const file = input.files && input.files[0];
        input.value = "";
        if (!file || !state.selectedRole) return;
        const maxBytes = Number(state.transfer.max_bytes || 131072);
        if (file.size > maxBytes) {
            frappe.msgprint(__("ملف الصلاحيات أكبر من الحد المسموح."));
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            let payload;
            try { payload = JSON.parse(String(reader.result || "")); }
            catch (_) { frappe.msgprint(__("ملف JSON غير صالح.")); return; }
            frappe.call({
                method: METHODS.import,
                args:{role:state.selectedRole,payload},
                freeze:true,
                freeze_message:__("جاري التحقق من ملف الصلاحيات...")
            }).then(response => {
                state.preview = response.message || null;
                state.working = clone(state.preview?.capabilities || {});
                renderCapabilities();
                renderSide();
                updateSaveBar();
                frappe.show_alert({message:__("تم تحميل الملف للمعاينة فقط. اضغط حفظ لتطبيقه."),indicator:"blue"});
            }).catch(error => showError(error, __("تعذر استيراد ملف الصلاحيات."), false));
        };
        reader.readAsText(file, "utf-8");
    }

    function showEmpty(message) {
        $main.find(".apc-loading").show().text(message);
        $main.find(".apc-content").hide();
        $(wrapper).find(".apc-savebar").hide();
    }

    function showError(error, fallback, replacePage = true) {
        const message = error && error.message ? error.message : fallback;
        if (replacePage) showEmpty(message);
        else frappe.msgprint({title:__("إدارة الصلاحيات"),message:esc(message),indicator:"red"});
    }
}
