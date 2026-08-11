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
    if (window.AlmdinaPageRevisit) {
        // Unsaved matrix edits outrank freshness: only reload a clean console.
        window.AlmdinaPageRevisit.refreshOnRevisit(wrapper, () => (
            state.saving || isDirty() ? null : loadConsole()
        ));
    }
    loadConsole();

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value || {}));
    }

    function stable(value) {
        return JSON.stringify(
            Object.keys(value || {}).sort().reduce((result, key) => {
                result[key] = value[key] === true;
                return result;
            }, {})
        );
    }

    function isDirty() {
        return stable(state.baseline) !== stable(state.working);
    }

    function unique(values) {
        return [...new Set((values || []).map(value => String(value || "")).filter(Boolean))];
    }

    function injectStyles() {
        if (document.getElementById("almdina-permission-console-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-permission-console-style";
        style.textContent = `
            .apc-shell{direction:rtl;padding-bottom:92px}
            .apc-hero{display:flex;justify-content:space-between;gap:20px;padding:20px;margin-bottom:14px;border:1px solid var(--border-color,#e5e7eb);border-radius:16px;background:linear-gradient(135deg,var(--fg-color,#fff),var(--subtle-fg,#f7f9fb))}
            .apc-hero h2{margin:0 0 6px;font-size:22px;font-weight:800}.apc-hero p{margin:0;max-width:780px;color:var(--text-muted,#6b7280);line-height:1.8}.apc-actor{min-width:210px;text-align:left;direction:ltr;font-size:12px}
            .apc-toolbar{display:grid;grid-template-columns:minmax(300px,1.1fr) minmax(300px,1fr) minmax(270px,.85fr);gap:12px;margin-bottom:14px}.apc-panel{border:1px solid var(--border-color,#e5e7eb);border-radius:14px;background:var(--fg-color,#fff);padding:15px}.apc-panel-title-row{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.apc-panel-title{font-size:13px;font-weight:800;margin:0}
            .apc-role-combo{position:relative;width:100%}.apc-role-combo-control{display:flex;align-items:center;width:100%;min-height:44px;border:1px solid var(--border-color,#d8dee4);border-radius:11px;background:var(--control-bg,#fff);transition:.15s;overflow:hidden}.apc-role-combo-control:focus-within{border-color:var(--primary,#2490ef);box-shadow:0 0 0 2px rgba(36,144,239,.12)}.apc-role-picker{flex:1;min-width:0;height:42px;border:0!important;background:transparent!important;box-shadow:none!important;outline:none!important;padding:8px 12px;color:var(--text-color,#1f2937);font-size:13px}.apc-role-toggle{width:42px;height:42px;border:0;background:transparent;color:var(--text-muted,#6b7280);font-size:18px;line-height:1;cursor:pointer}.apc-role-menu{position:absolute;z-index:120;top:calc(100% + 5px);right:0;left:0;max-height:285px;overflow:auto;padding:5px;border:1px solid var(--border-color,#d8dee4);border-radius:11px;background:var(--fg-color,#fff);box-shadow:0 12px 35px rgba(0,0,0,.16)}.apc-role-option{display:flex;align-items:center;justify-content:space-between;gap:10px;width:100%;padding:9px 10px;border:0;border-radius:8px;background:transparent;color:var(--text-color,#1f2937);text-align:right;cursor:pointer;font-size:13px}.apc-role-option:hover,.apc-role-option:focus,.apc-role-option.is-active{background:var(--subtle-fg,#f1f5f9);outline:none}.apc-role-option.is-selected{font-weight:900;color:var(--primary,#2490ef)}.apc-role-option small{color:var(--text-muted,#6b7280);font-size:10px}.apc-role-no-results{padding:18px 10px;text-align:center;color:var(--text-muted,#6b7280);font-size:12px}
            .apc-transfer-tools{display:flex;gap:8px}.apc-transfer-tools .btn{flex:1}.apc-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.apc-stat{padding:10px 6px;border-radius:10px;background:var(--subtle-fg,#f6f8fa);text-align:center}.apc-stat strong{display:block;font-size:19px}.apc-stat span{font-size:11px}
            .apc-content{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(290px,.7fr);gap:14px;align-items:start}.apc-groups{display:grid;gap:12px}.apc-group{border:1px solid var(--border-color,#e5e7eb);border-radius:14px;overflow:hidden;background:var(--fg-color,#fff)}.apc-group-head{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 15px;background:var(--subtle-fg,#f8fafb);border-bottom:1px solid var(--border-color,#e5e7eb)}.apc-group-copy{min-width:0}.apc-group-head h4{margin:0 0 3px;font-size:15px;font-weight:800}.apc-group-head p{margin:0;font-size:12px;color:var(--text-muted,#6b7280)}.apc-group-count{display:inline-flex;margin-inline-start:6px;padding:2px 7px;border-radius:999px;background:var(--control-bg,#fff);border:1px solid var(--border-color,#dfe3e8);font-size:10px;font-weight:800;color:var(--text-muted,#6b7280)}
            .apc-bulk-toggle{flex:0 0 auto;min-height:32px;border-radius:9px!important;font-size:11px!important;font-weight:800!important;white-space:nowrap}.apc-bulk-toggle.is-all{background:rgba(36,144,239,.1)!important;border-color:rgba(36,144,239,.35)!important;color:var(--primary,#2490ef)!important}
            .apc-capability{display:grid;grid-template-columns:46px minmax(0,1fr) auto;gap:11px;align-items:center;padding:12px 15px;border-bottom:1px solid var(--border-color,#eef1f4)}.apc-capability:last-child{border-bottom:0}.apc-capability-title{display:block;font-size:13px;font-weight:800;margin-bottom:2px}.apc-capability-description{display:block;font-size:12px;line-height:1.6;color:var(--text-muted,#6b7280)}.apc-switch{position:relative;width:42px;height:24px;display:inline-block;margin:0}.apc-switch input{opacity:0;width:0;height:0}.apc-slider{position:absolute;inset:0;cursor:pointer;border-radius:24px;background:#c8d0d8;transition:.18s}.apc-slider:before{content:"";position:absolute;width:18px;height:18px;right:3px;top:3px;border-radius:50%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2);transition:.18s}.apc-switch input:checked+.apc-slider{background:var(--primary,#2490ef)}.apc-switch input:checked+.apc-slider:before{transform:translateX(-18px)}.apc-switch input:focus-visible+.apc-slider{outline:2px solid var(--primary,#2490ef);outline-offset:2px}
            .apc-badges{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}.apc-badge{border-radius:999px;padding:3px 7px;font-size:10px;font-weight:800;white-space:nowrap}.apc-badge.standard{background:#edf2f7;color:#475569}.apc-badge.permission{background:#eef7ff;color:#245a7a}.apc-badge.sensitive{background:#fff7df;color:#8a5b00}.apc-badge.critical{background:#ffe7e7;color:#a61b1b}
            .apc-side{position:sticky;top:58px;display:grid;gap:12px}.apc-chip-row{display:flex;flex-wrap:wrap;gap:6px}.apc-chip{border-radius:999px;padding:5px 9px;background:var(--subtle-fg,#f2f5f7);font-size:11px;font-weight:700}.apc-warning{padding:10px;border-radius:10px;background:#fff5e6;border:1px solid #ffd99a;color:#704600;font-size:12px;line-height:1.7}.apc-source{padding:9px;border-radius:10px;background:#edf7ff;border:1px solid #b9dcf7;color:#195475;font-size:12px;line-height:1.7}.apc-change{display:flex;justify-content:space-between;gap:8px;padding:7px 0;border-bottom:1px solid var(--border-color,#eef1f4);font-size:12px}.apc-change:last-child{border-bottom:0}.apc-audit-list{display:grid;gap:8px}.apc-audit-item{padding:9px;border-radius:9px;background:var(--subtle-fg,#f8fafb);font-size:11px;line-height:1.6}.apc-empty{padding:34px 18px;text-align:center;border:1px dashed var(--border-color,#d5dce3);border-radius:14px;color:var(--text-muted,#6b7280);background:var(--subtle-fg,#fafafa)}
            .apc-savebar{position:fixed;z-index:90;right:0;left:0;bottom:0;display:flex;justify-content:center;pointer-events:none;padding:10px 16px}.apc-savebar-inner{pointer-events:auto;width:min(760px,calc(100vw - 30px));display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border:1px solid var(--border-color,#dfe3e8);border-radius:14px;background:var(--fg-color,#fff);box-shadow:0 8px 30px rgba(0,0,0,.13)}.apc-save-actions{display:flex;gap:8px}.apc-dirty{font-size:12px;font-weight:700;color:var(--text-muted,#6b7280)}.apc-dirty.is-dirty{color:#8a5b00}
            @media(max-width:1100px){.apc-toolbar{grid-template-columns:1fr 1fr}.apc-toolbar .apc-summary-panel{grid-column:1/-1}}
            @media(max-width:900px){.apc-content{grid-template-columns:1fr}.apc-side{position:static;grid-template-columns:repeat(2,minmax(0,1fr))}}
            @media(max-width:650px){.apc-hero{display:block;padding:16px}.apc-actor{margin-top:12px;text-align:right}.apc-toolbar,.apc-side{grid-template-columns:1fr}.apc-transfer-tools{flex-direction:column}.apc-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.apc-group-head{align-items:flex-start}.apc-capability{grid-template-columns:42px minmax(0,1fr)}.apc-badges{grid-column:2;justify-content:flex-start}.apc-savebar-inner{align-items:stretch;flex-direction:column}.apc-save-actions .btn{flex:1}}
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
                    <div class="apc-panel apc-role-panel">
                        <div class="apc-panel-title-row"><div class="apc-panel-title">${__("اختر الدور")}</div></div>
                        <div class="apc-role-combo">
                            <div class="apc-role-combo-control">
                                <input type="text" class="apc-role-picker" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="apc-role-menu" autocomplete="off" placeholder="${__("ابحث واختر دورًا...")}">
                                <button type="button" class="apc-role-toggle" aria-label="${__("فتح قائمة الأدوار")}" tabindex="-1">⌄</button>
                            </div>
                            <div class="apc-role-menu" id="apc-role-menu" role="listbox" hidden></div>
                        </div>
                    </div>
                    <div class="apc-panel">
                        <div class="apc-panel-title-row"><div class="apc-panel-title">${__("نقل مصفوفة الصلاحيات")}</div></div>
                        <div class="apc-transfer-tools"><button type="button" class="btn btn-default apc-export">${__("تصدير JSON")}</button><button type="button" class="btn btn-default apc-import">${__("استيراد JSON")}</button></div>
                        <div class="text-muted small mt-2">${__("الاستيراد يحمّل الصلاحيات للمعاينة فقط؛ الحفظ يبقى خطوة مستقلة.")}</div>
                        <input type="file" class="apc-import-file" accept="application/json,.json" hidden>
                    </div>
                    <div class="apc-panel apc-summary-panel">
                        <div class="apc-panel-title-row"><div class="apc-panel-title">${__("ملخص الصلاحيات")}</div><button type="button" class="btn btn-default apc-bulk-toggle apc-select-all-global">${__("تحديد الكل للكل")}</button></div>
                        <div class="apc-stats"><div class="apc-stat"><strong class="apc-total-count">0</strong><span>${__("إجمالي")}</span></div><div class="apc-stat"><strong class="apc-enabled-count">0</strong><span>${__("مفعلة")}</span></div><div class="apc-stat"><strong class="apc-critical-count">0</strong><span>${__("حرجة")}</span></div><div class="apc-stat"><strong class="apc-change-count">0</strong><span>${__("تغييرات")}</span></div></div>
                    </div>
                </div>
                <div class="apc-loading apc-empty">${__("جاري تحميل مصفوفة الصلاحيات...")}</div>
                <div class="apc-content" style="display:none"><div class="apc-groups"></div><aside class="apc-side"><div class="apc-panel apc-impact-panel"></div><div class="apc-panel apc-audit-panel"></div></aside></div>
            </div>
            <div class="apc-savebar" style="display:none"><div class="apc-savebar-inner"><div class="apc-dirty">${__("لا توجد تغييرات غير محفوظة")}</div><div class="apc-save-actions"><button type="button" class="btn btn-default apc-reset">${__("تراجع")}</button><button type="button" class="btn btn-primary apc-save">${__("حفظ الصلاحيات")}</button></div></div></div>
        `);
    }

    function bindEvents() {
        $main.on("focus input", ".apc-role-picker", function () {
            renderRoleMenu(String($(this).val() || ""));
            openRoleMenu();
        });
        $main.on("keydown", ".apc-role-picker", handleRolePickerKeydown);
        $main.on("click", ".apc-role-toggle", function () {
            const $menu = $main.find(".apc-role-menu");
            if ($menu.prop("hidden")) {
                renderRoleMenu("");
                openRoleMenu();
                $main.find(".apc-role-picker").trigger("focus");
            } else {
                closeRoleMenu(true);
            }
        });
        $main.on("click", ".apc-role-option", function () {
            chooseRole(String($(this).attr("data-role") || ""));
        });
        $(document).off("mousedown.apc-role-picker").on("mousedown.apc-role-picker", event => {
            if (!$(event.target).closest(".apc-role-combo").length) closeRoleMenu(true);
        });
        $main.on("change", ".apc-capability-input", onCapabilityChange);
        $main.on("click", ".apc-select-all-group", onGroupBulkToggle);
        $main.on("click", ".apc-select-all-global", onGlobalBulkToggle);
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
                renderRoleMenu("");
                if (!state.roles.length) return showEmpty(__("لا توجد أدوار قابلة للإدارة."));
                return loadRole(String(state.roles[0].name || ""));
            },
            error => showError(error, __("تعذر فتح إدارة الصلاحيات."))
        );
    }

    function roleMatches(role, query) {
        const needle = String(query || "").trim().toLowerCase();
        return !needle || String(role.name || "").toLowerCase().includes(needle);
    }

    function renderRoleMenu(query) {
        const roles = state.roles.filter(role => roleMatches(role, query));
        const $menu = $main.find(".apc-role-menu");
        if (!roles.length) {
            $menu.html(`<div class="apc-role-no-results">${__("لا يوجد دور مطابق للبحث.")}</div>`);
            return;
        }
        $menu.html(roles.map(role => {
            const selected = String(role.name || "") === state.selectedRole;
            return `<button type="button" class="apc-role-option ${selected ? "is-selected" : ""}" role="option" aria-selected="${selected ? "true" : "false"}" data-role="${esc(role.name)}"><span>${esc(role.name)}</span>${role.desk_access ? "" : `<small>${__("بدون Desk")}</small>`}</button>`;
        }).join(""));
    }

    function openRoleMenu() {
        $main.find(".apc-role-menu").prop("hidden", false);
        $main.find(".apc-role-picker").attr("aria-expanded", "true");
    }

    function closeRoleMenu(restoreSelection = false) {
        $main.find(".apc-role-menu").prop("hidden", true);
        $main.find(".apc-role-picker").attr("aria-expanded", "false");
        if (restoreSelection && state.selectedRole) $main.find(".apc-role-picker").val(state.selectedRole);
    }

    function handleRolePickerKeydown(event) {
        const $options = $main.find(".apc-role-option");
        if (event.key === "Escape") {
            closeRoleMenu(true);
            return;
        }
        if (event.key === "Enter") {
            const $active = $options.filter(".is-active").first();
            const $target = $active.length ? $active : $options.first();
            if ($target.length) {
                event.preventDefault();
                chooseRole(String($target.attr("data-role") || ""));
            }
            return;
        }
        if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
        event.preventDefault();
        if (!$options.length) return;
        let index = $options.index($options.filter(".is-active").first());
        if (event.key === "ArrowDown") index = Math.min($options.length - 1, index + 1);
        else index = index <= 0 ? 0 : index - 1;
        $options.removeClass("is-active").eq(index).addClass("is-active").get(0).scrollIntoView({ block: "nearest" });
    }

    function chooseRole(role) {
        if (!role) return;
        $main.find(".apc-role-picker").val(role);
        closeRoleMenu(false);
        if (role !== state.selectedRole) requestRoleChange(role);
    }

    function requestRoleChange(role) {
        if (!isDirty()) return loadRole(role);
        frappe.confirm(
            __("لديك تغييرات غير محفوظة. هل تريد تجاهلها؟"),
            () => loadRole(role),
            () => $main.find(".apc-role-picker").val(state.selectedRole)
        );
    }

    function loadRole(role) {
        const requestId = ++state.roleRequest;
        state.selectedRole = role;
        state.transferRequest += 1;
        $main.find(".apc-role-picker").val(role);
        renderRoleMenu("");
        closeRoleMenu(false);
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

    function completeCatalog() {
        const groups = (state.catalog || []).map(group => ({
            ...group,
            capabilities: Array.isArray(group.capabilities) ? group.capabilities.slice() : [],
        }));
        const presented = new Set(groups.flatMap(group => group.capabilities.map(item => String(item.key || "")).filter(Boolean)));
        const missing = Object.keys(state.working || {}).filter(key => !presented.has(key));
        if (missing.length) {
            groups.push({
                key: "unclassified",
                label: __("صلاحيات أخرى"),
                description: __("صلاحيات موجودة في الخادم ولم تكن مصنفة في واجهة الإدارة. تظهر هنا تلقائيًا حتى لا تُحجب أي صلاحية قابلة للإسناد."),
                capabilities: missing.sort().map(key => ({
                    key,
                    label: key,
                    description: __("صلاحية نظام مسجلة في مصفوفة الدور."),
                    risk: "normal",
                    standard: false,
                    permission_type: key,
                })),
            });
        }
        return groups.filter(group => group.capabilities.length);
    }

    function allCapabilityKeys() {
        return unique(completeCatalog().flatMap(group => group.capabilities.map(item => item.key)));
    }

    function groupCapabilityKeys(groupKey) {
        const group = completeCatalog().find(item => String(item.key || "") === String(groupKey || ""));
        return group ? unique(group.capabilities.map(item => item.key)) : [];
    }

    function renderPermissionGroups() {
        const groups = completeCatalog();
        $main.find(".apc-groups").html(groups.map(group => `
            <section class="apc-group" data-group="${esc(group.key)}">
                <div class="apc-group-head">
                    <div class="apc-group-copy"><h4>${esc(group.label)}<span class="apc-group-count">${group.capabilities.length}</span></h4><p>${esc(group.description)}</p></div>
                    <button type="button" class="btn btn-default apc-bulk-toggle apc-select-all-group" data-group="${esc(group.key)}">${__("تحديد الكل")}</button>
                </div>
                <div>${group.capabilities.map(renderCapability).join("")}</div>
            </section>
        `).join("") || `<div class="apc-empty">${__("لا توجد صلاحيات مسجلة.")}</div>`);
        syncBulkControls();
    }

    function permissionBadge(capability) {
        if (!capability.standard) return "";
        const labels = { read: __("قراءة + اختيار"), create: __("إنشاء"), write: __("تعديل"), delete: __("حذف") };
        const permission = labels[String(capability.permission_type || "")] || String(capability.permission_type || "");
        return `<span class="apc-badge permission">${__("Frappe: {0}", [esc(permission)])}</span>`;
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
        return `<label class="apc-capability"><span class="apc-switch"><input type="checkbox" class="apc-capability-input" data-capability="${esc(capability.key)}" ${state.working[capability.key] === true ? "checked" : ""}><span class="apc-slider"></span></span><span><span class="apc-capability-title">${esc(capability.label)}</span><span class="apc-capability-description">${esc(capability.description)}</span></span><span class="apc-badges">${permissionBadge(capability)}${standard}${risk}</span></label>`;
    }

    function queuePreview() {
        syncDirtyState();
        clearTimeout(state.previewTimer);
        state.previewTimer = setTimeout(() => {
            loadPreview().then(() => syncDirtyState());
        }, 180);
    }

    function onCapabilityChange() {
        const key = String($(this).attr("data-capability") || "");
        state.working[key] = $(this).is(":checked");
        syncBulkControls();
        queuePreview();
    }

    function setCapabilities(keys, enabled) {
        unique(keys).forEach(key => { state.working[key] = enabled === true; });
        syncCheckboxes();
        syncBulkControls();
        queuePreview();
    }

    function onGroupBulkToggle() {
        const keys = groupCapabilityKeys(String($(this).attr("data-group") || ""));
        if (!keys.length) return;
        setCapabilities(keys, !keys.every(key => state.working[key] === true));
    }

    function onGlobalBulkToggle() {
        const keys = allCapabilityKeys();
        if (!keys.length) return;
        setCapabilities(keys, !keys.every(key => state.working[key] === true));
    }

    function syncBulkControls() {
        $main.find(".apc-select-all-group").each(function () {
            const keys = groupCapabilityKeys(String($(this).attr("data-group") || ""));
            const allEnabled = keys.length > 0 && keys.every(key => state.working[key] === true);
            $(this).toggleClass("is-all", allEnabled).attr("aria-pressed", allEnabled ? "true" : "false").text(allEnabled ? __("إلغاء تحديد الكل") : __("تحديد الكل"));
        });
        const keys = allCapabilityKeys();
        const allEnabled = keys.length > 0 && keys.every(key => state.working[key] === true);
        $main.find(".apc-select-all-global").toggleClass("is-all", allEnabled).attr("aria-pressed", allEnabled ? "true" : "false").text(allEnabled ? __("إلغاء تحديد الكل للكل") : __("تحديد الكل للكل"));
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
                if (requestId === state.previewRequest) frappe.show_alert({ message: error && error.message ? error.message : __("تعذر حساب أثر الصلاحيات."), indicator: "red" });
                return null;
            }
        );
    }

    function applyPreview(data) {
        state.preview = data || {};
        state.working = clone(state.preview.capabilities || state.working);
        syncCheckboxes();
        syncBulkControls();
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
            error => {
                frappe.msgprint({ title: __("تعذر تحميل الصلاحيات"), message: esc(error && error.message ? error.message : __("حدث خطأ غير متوقع.")), indicator: "red" });
                return null;
            }
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
                window.setTimeout(() => URL.revokeObjectURL(url), 1000);
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
        reader.onload = () => {
            const payload = String(reader.result || "");
            try {
                const parsed = JSON.parse(payload);
                if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("not-object");
            } catch (error) {
                frappe.msgprint({ title: __("ملف JSON غير صالح"), message: __("تعذر قراءة الملف ككائن JSON صحيح. لم يتم تغيير أي صلاحية."), indicator: "red" });
                return;
            }
            previewExternal(
                METHODS.import,
                { role: state.selectedRole, payload },
                __("تم التحقق من الملف وتحميله للمعاينة فقط. لن يتغير الدور قبل الحفظ.")
            );
        };
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
            orders: __("الطلبات"), costing: __("التكلفة"), planning: __("خطة القص"), drawing: __("الرسم"),
            production: __("الإنتاج"), quality: __("الجودة"), workforce: __("المستخدمون"), factory_settings: __("الإعدادات"),
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
            <div class="apc-panel-title-row"><div class="apc-panel-title">${__("أثر الصلاحيات")}</div></div>${warning}${source}
            <div class="mb-2"><strong>${__("الواجهة الافتراضية")}</strong><div class="text-muted small">${esc(home)}</div></div>
            <div class="mb-2"><strong>${__("مساحات العمل")}</strong><div class="apc-chip-row">${workspaces.map(item => `<span class="apc-chip">${esc(item)}</span>`).join("") || `<span class="text-muted small">${__("لا شيء")}</span>`}</div></div>
            <div class="mb-2"><strong>${__("الأقسام الظاهرة")}</strong><div class="apc-chip-row">${enabledSections.map(key => `<span class="apc-chip">${esc(labels[key] || key)}</span>`).join("") || `<span class="text-muted small">${__("لا شيء")}</span>`}</div></div>
            <div><strong>${__("التغييرات")}</strong><div>${changes.slice(0, 12).map(change => `<div class="apc-change"><span>${esc(change.label || change.key)}</span><span>${change.after ? __("منح") : __("إلغاء")}</span></div>`).join("") || `<div class="text-muted small mt-2">${__("لا توجد تغييرات.")}</div>`}</div></div>
        `);
        updateStats(changes);
    }

    function updateStats(changes) {
        const keys = allCapabilityKeys();
        const enabled = keys.filter(key => state.working[key] === true).length;
        const criticalKeys = new Set(completeCatalog().flatMap(group => group.capabilities || []).filter(item => item.risk === "critical").map(item => item.key));
        const critical = keys.filter(key => state.working[key] === true && criticalKeys.has(key)).length;
        $main.find(".apc-total-count").text(keys.length);
        $main.find(".apc-enabled-count").text(enabled);
        $main.find(".apc-critical-count").text(critical);
        $main.find(".apc-change-count").text((changes || []).length);
    }

    function renderAudit(rows) {
        $main.find(".apc-audit-panel").html(`
            <div class="apc-panel-title-row"><div class="apc-panel-title">${__("آخر التغييرات المحفوظة")}</div></div>
            <div class="apc-audit-list">${(rows || []).slice(0, 10).map(row => `<div class="apc-audit-item"><strong>${esc(row.changed_by || "")}</strong><div>${esc(row.changed_on || "")}</div><div>${esc(row.changed_capabilities || "")}</div></div>`).join("") || `<div class="text-muted small">${__("لا يوجد سجل بعد.")}</div>`}</div>
        `);
    }

    function syncDirtyState() {
        const dirty = isDirty();
        $main.find(".apc-dirty").toggleClass("is-dirty", dirty).text(dirty ? __("لديك تغييرات غير محفوظة") : __("لا توجد تغييرات غير محفوظة"));
        $main.find(".apc-save").prop("disabled", !dirty || state.saving);
        $main.find(".apc-reset").prop("disabled", !dirty || state.saving);
        $main.find(".apc-capability-input,.apc-role-picker,.apc-role-toggle,.apc-bulk-toggle,.apc-export,.apc-import").prop("disabled", state.saving);
        if (!state.preview) updateStats([]);
    }

    function resetWorkingState() {
        state.previewRequest += 1;
        state.transferRequest += 1;
        state.working = clone(state.baseline);
        state.preview = { capabilities: clone(state.working), changes: [], impact: (state.preview && state.preview.impact) || {} };
        syncCheckboxes();
        syncBulkControls();
        loadPreview();
        syncDirtyState();
    }

    function refreshRuntimePermissions() {
        const permissions = window.AlmdinaPermissions;
        if (!permissions || typeof permissions.refresh !== "function") return Promise.resolve();
        return Promise.resolve().then(() => permissions.refresh()).catch(error => console.error("Failed to refresh runtime permissions after save", error));
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
