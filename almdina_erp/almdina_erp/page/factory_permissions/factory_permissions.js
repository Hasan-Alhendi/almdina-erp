frappe.pages["factory-permissions"].on_page_load = function (wrapper) {
    "use strict";

    const METHODS = Object.freeze({
        console: "almdina_erp.almdina_erp.services.permission_management_service.get_permission_console",
        role: "almdina_erp.almdina_erp.services.permission_management_service.get_role_permissions",
        preview: "almdina_erp.almdina_erp.services.permission_management_service.preview_role_permissions",
        update: "almdina_erp.almdina_erp.services.permission_management_service.update_role_permissions",
    });

    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("إدارة صلاحيات المعمل"),
        single_column: true,
    });
    const $main = $(wrapper).find(".layout-main-section");
    let catalog = [];
    let roles = [];
    let selectedRole = "";
    let baseline = {};
    let working = {};
    let preview = null;
    let roleRequest = 0;
    let previewRequest = 0;
    let previewTimer = null;
    let saving = false;

    injectStyles();
    renderShell();

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
        return stable(baseline) !== stable(working);
    }

    function injectStyles() {
        if (document.getElementById("almdina-permission-console-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-permission-console-style";
        style.textContent = `
            .apc-shell { direction: rtl; padding-bottom: 92px; }
            .apc-hero {
                display: flex; justify-content: space-between; align-items: flex-start;
                gap: 20px; padding: 20px; margin-bottom: 14px;
                border: 1px solid var(--border-color, #e5e7eb); border-radius: 16px;
                background: linear-gradient(135deg, var(--fg-color, #fff), var(--subtle-fg, #f7f9fb));
            }
            .apc-hero h2 { margin: 0 0 6px; font-size: 22px; font-weight: 800; }
            .apc-hero p { margin: 0; max-width: 720px; color: var(--text-muted, #6b7280); line-height: 1.8; }
            .apc-actor { min-width: 220px; text-align: left; direction: ltr; font-size: 12px; }
            .apc-toolbar {
                display: grid; grid-template-columns: minmax(250px, 1.2fr) minmax(220px, .8fr);
                gap: 12px; margin-bottom: 14px;
            }
            .apc-panel {
                border: 1px solid var(--border-color, #e5e7eb); border-radius: 14px;
                background: var(--fg-color, #fff); padding: 15px;
            }
            .apc-panel-title { font-size: 13px; font-weight: 800; margin-bottom: 8px; }
            .apc-role-tools { display: grid; grid-template-columns: minmax(180px, .65fr) minmax(220px, 1fr); gap: 8px; }
            .apc-input, .apc-select {
                width: 100%; min-height: 42px; border: 1px solid var(--border-color, #d8dee4);
                border-radius: 10px; padding: 8px 11px; background: var(--control-bg, #fff);
                color: var(--text-color, #1f2937); outline: none;
            }
            .apc-input:focus, .apc-select:focus { border-color: var(--primary, #2490ef); box-shadow: 0 0 0 2px rgba(36,144,239,.12); }
            .apc-stats { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px; }
            .apc-stat { padding: 10px; border-radius: 10px; background: var(--subtle-fg, #f6f8fa); text-align: center; }
            .apc-stat strong { display: block; font-size: 19px; }
            .apc-content { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(290px, .7fr); gap: 14px; align-items: start; }
            .apc-groups { display: grid; gap: 12px; }
            .apc-group { border: 1px solid var(--border-color, #e5e7eb); border-radius: 14px; overflow: hidden; background: var(--fg-color, #fff); }
            .apc-group-head { padding: 13px 15px; background: var(--subtle-fg, #f8fafb); border-bottom: 1px solid var(--border-color, #e5e7eb); }
            .apc-group-head h4 { margin: 0 0 3px; font-size: 15px; font-weight: 800; }
            .apc-group-head p { margin: 0; font-size: 12px; color: var(--text-muted, #6b7280); }
            .apc-capability { display: grid; grid-template-columns: 46px minmax(0,1fr) auto; gap: 11px; align-items: center; padding: 12px 15px; border-bottom: 1px solid var(--border-color, #eef1f4); }
            .apc-capability:last-child { border-bottom: 0; }
            .apc-capability.is-disabled { opacity: .6; }
            .apc-capability-title { font-size: 13px; font-weight: 800; margin-bottom: 2px; }
            .apc-capability-description { font-size: 12px; line-height: 1.6; color: var(--text-muted, #6b7280); }
            .apc-switch { position: relative; width: 42px; height: 24px; display: inline-block; margin: 0; }
            .apc-switch input { opacity: 0; width: 0; height: 0; }
            .apc-slider { position: absolute; inset: 0; cursor: pointer; border-radius: 24px; background: #c8d0d8; transition: .18s ease; }
            .apc-slider:before { content: ""; position: absolute; width: 18px; height: 18px; right: 3px; top: 3px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.2); transition: .18s ease; }
            .apc-switch input:checked + .apc-slider { background: var(--primary, #2490ef); }
            .apc-switch input:checked + .apc-slider:before { transform: translateX(-18px); }
            .apc-switch input:focus-visible + .apc-slider { outline: 2px solid var(--primary, #2490ef); outline-offset: 2px; }
            .apc-badges { display: flex; gap: 5px; flex-wrap: wrap; justify-content: flex-end; }
            .apc-badge { border-radius: 999px; padding: 3px 7px; font-size: 10px; font-weight: 800; white-space: nowrap; }
            .apc-badge.standard { background: #edf2f7; color: #475569; }
            .apc-badge.sensitive { background: #fff7df; color: #8a5b00; }
            .apc-badge.critical { background: #ffe7e7; color: #a61b1b; }
            .apc-side { position: sticky; top: 58px; display: grid; gap: 12px; }
            .apc-impact-list, .apc-audit-list { display: grid; gap: 8px; }
            .apc-chip-row { display: flex; flex-wrap: wrap; gap: 6px; }
            .apc-chip { border-radius: 999px; padding: 5px 9px; background: var(--subtle-fg, #f2f5f7); font-size: 11px; font-weight: 700; }
            .apc-warning { padding: 10px; border-radius: 10px; background: #fff5e6; border: 1px solid #ffd99a; color: #704600; font-size: 12px; line-height: 1.7; }
            .apc-change { display: flex; justify-content: space-between; gap: 8px; padding: 7px 0; border-bottom: 1px solid var(--border-color, #eef1f4); font-size: 12px; }
            .apc-change:last-child { border-bottom: 0; }
            .apc-change .on { color: #08783e; font-weight: 800; }
            .apc-change .off { color: #a61b1b; font-weight: 800; }
            .apc-audit-item { padding: 9px; border-radius: 9px; background: var(--subtle-fg, #f8fafb); font-size: 11px; line-height: 1.6; }
            .apc-empty { padding: 34px 18px; text-align: center; border: 1px dashed var(--border-color, #d5dce3); border-radius: 14px; color: var(--text-muted, #6b7280); background: var(--subtle-fg, #fafafa); }
            .apc-savebar {
                position: fixed; z-index: 90; right: 0; left: 0; bottom: 0;
                display: flex; align-items: center; justify-content: center; pointer-events: none;
                padding: 10px 16px;
            }
            .apc-savebar-inner {
                pointer-events: auto; width: min(760px, calc(100vw - 30px)); display: flex;
                align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px;
                border: 1px solid var(--border-color, #dfe3e8); border-radius: 14px;
                background: color-mix(in srgb, var(--fg-color, #fff) 94%, transparent);
                backdrop-filter: blur(10px); box-shadow: 0 8px 30px rgba(0,0,0,.13);
            }
            .apc-save-actions { display: flex; gap: 8px; }
            .apc-dirty { font-size: 12px; font-weight: 700; color: var(--text-muted, #6b7280); }
            .apc-dirty.is-dirty { color: #8a5b00; }
            @media (max-width: 900px) {
                .apc-content { grid-template-columns: 1fr; }
                .apc-side { position: static; grid-template-columns: repeat(2, minmax(0,1fr)); }
            }
            @media (max-width: 650px) {
                .apc-hero { display: block; padding: 16px; }
                .apc-actor { margin-top: 12px; text-align: right; }
                .apc-toolbar, .apc-role-tools, .apc-side { grid-template-columns: 1fr; }
                .apc-stats { grid-template-columns: repeat(3, minmax(0,1fr)); }
                .apc-capability { grid-template-columns: 42px minmax(0,1fr); }
                .apc-badges { grid-column: 2; justify-content: flex-start; }
                .apc-savebar-inner { align-items: stretch; flex-direction: column; }
                .apc-save-actions .btn { flex: 1; }
            }
        `;
        document.head.appendChild(style);
    }

    function renderShell() {
        $main.html(`
            <div class="apc-shell">
                <div class="apc-hero">
                    <div>
                        <h2>${__("مصفوفة صلاحيات Almdina")}</h2>
                        <p>${__("امنح كل دور ما يحتاجه فقط. تعتمد الواجهة والخدمات وبيانات الطلب على هذه الصلاحيات، بينما تبقى أدوار الأقسام التشغيلية مخصصة لأهلية الإسناد.")}</p>
                    </div>
                    <div class="apc-actor text-muted"></div>
                </div>
                <div class="apc-toolbar">
                    <div class="apc-panel">
                        <div class="apc-panel-title">${__("اختر الدور")}</div>
                        <div class="apc-role-tools">
                            <input type="search" class="apc-input apc-role-search" placeholder="${__("ابحث عن دور...")}">
                            <select class="apc-select apc-role-select" aria-label="${__("الدور")}"></select>
                        </div>
                    </div>
                    <div class="apc-panel">
                        <div class="apc-panel-title">${__("ملخص الصلاحيات")}</div>
                        <div class="apc-stats">
                            <div class="apc-stat"><strong class="apc-enabled-count">0</strong><span>${__("مفعلة")}</span></div>
                            <div class="apc-stat"><strong class="apc-critical-count">0</strong><span>${__("حساسة")}</span></div>
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

        $main.on("input", ".apc-role-search", filterRoles);
        $main.on("change", ".apc-role-select", function () {
            const role = String($(this).val() || "");
            if (role && role !== selectedRole) loadRole(role);
        });
        $main.on("change", ".apc-capability-input", onCapabilityChange);
        $main.on("click", ".apc-reset", resetWorkingState);
        $main.on("click", ".apc-save", savePermissions);
    }

    function loadConsole() {
        return frappe
            .call({ method: METHODS.console, freeze: false })
            .then(response => {
                const data = response.message || {};
                catalog = Array.isArray(data.catalog) ? data.catalog : [];
                roles = Array.isArray(data.roles) ? data.roles : [];
                const actor = data.actor || {};
                $main.find(".apc-actor").html(`
                    <div>${esc(actor.full_name || actor.user || "")}</div>
                    <div>${esc(actor.user || "")}</div>
                `);
                renderRoleOptions(roles);
                if (!roles.length) {
                    showEmpty(__("لا توجد أدوار قابلة للإدارة."));
                    return;
                }
                loadRole(String(roles[0].name || ""));
            })
            .catch(error => showError(error, __("تعذر فتح إدارة الصلاحيات.")));
    }

    function renderRoleOptions(items) {
        const $select = $main.find(".apc-role-select");
        $select.empty();
        items.forEach(role => {
            const suffix = role.desk_access ? "" : ` — ${__("بدون Desk")}`;
            $("<option>")
                .attr("value", role.name)
                .text(`${role.name}${suffix}`)
                .appendTo($select);
        });
    }

    function filterRoles() {
        const query = String($(this).val() || "").trim().toLowerCase();
        const filtered = roles.filter(role => String(role.name || "").toLowerCase().includes(query));
        renderRoleOptions(filtered);
        if (selectedRole && filtered.some(role => role.name === selectedRole)) {
            $main.find(".apc-role-select").val(selectedRole);
        }
    }

    function confirmDiscard(next) {
        if (!isDirty()) {
            next();
            return;
        }
        frappe.confirm(
            __("لديك تغييرات غير محفوظة. هل تريد تجاهلها؟"),
            next
        );
    }

    function loadRole(role) {
        confirmDiscard(() => {
            const requestId = ++roleRequest;
            selectedRole = role;
            $main.find(".apc-role-select").val(role);
            $main.find(".apc-content, .apc-savebar").hide();
            $main.find(".apc-loading").show().text(__("جاري تحميل صلاحيات الدور..."));
            frappe
                .call({ method: METHODS.role, args: { role }, freeze: false })
                .then(response => {
                    if (requestId !== roleRequest || role !== selectedRole) return;
                    const data = response.message || {};
                    baseline = clone(data.capabilities || {});
                    working = clone(data.capabilities || {});
                    preview = {
                        role,
                        capabilities: clone(working),
                        changes: [],
                        impact: data.impact || {},
                        requires_self_lockout_confirmation: false,
                        has_sensitive_changes: false,
                    };
                    renderPermissionGroups();
                    renderImpact(preview);
                    renderAudit(data.audit || []);
                    syncDirtyState();
                    $main.find(".apc-loading").hide();
                    $main.find(".apc-content, .apc-savebar").show();
                })
                .catch(error => {
                    if (requestId !== roleRequest) return;
                    showError(error, __("تعذر تحميل صلاحيات الدور."));
                });
        });
    }

    function renderPermissionGroups() {
        const html = catalog.map(group => `
            <section class="apc-group" data-category="${esc(group.key)}">
                <div class="apc-group-head">
                    <h4>${esc(group.label)}</h4>
                    <p>${esc(group.description)}</p>
                </div>
                <div>
                    ${(group.capabilities || []).map(renderCapability).join("")}
                </div>
            </section>
        `).join("");
        $main.find(".apc-groups").html(html || `<div class="apc-empty">${__("لا توجد صلاحيات مسجلة.")}</div>`);
    }

    function renderCapability(capability) {
        const checked = working[capability.key] === true;
        const riskBadge = capability.risk === "critical"
            ? `<span class="apc-badge critical">${__("حرجة")}</span>`
            : capability.risk === "sensitive"
                ? `<span class="apc-badge sensitive">${__("حساسة")}</span>`
                : "";
        const standardBadge = capability.standard
            ? `<span class="apc-badge standard">${__("صلاحية Frappe أساسية")}</span>`
            : "";
        return `
            <label class="apc-capability" data-capability="${esc(capability.key)}">
                <span class="apc-switch">
                    <input type="checkbox" class="apc-capability-input" data-capability="${esc(capability.key)}" ${checked ? "checked" : ""}>
                    <span class="apc-slider"></span>
                </span>
                <span>
                    <span class="apc-capability-title">${esc(capability.label)}</span>
                    <span class="apc-capability-description">${esc(capability.description)}</span>
                </span>
                <span class="apc-badges">${standardBadge}${riskBadge}</span>
            </label>
        `;
    }

    function orderCapabilityKeys() {
        return catalog
            .flatMap(group => group.capabilities || [])
            .filter(capability => capability.doctype === "Door Cutting Order")
            .map(capability => capability.key);
    }

    function onCapabilityChange() {
        const key = String($(this).attr("data-capability") || "");
        working[key] = $(this).is(":checked");

        if (key === "view_orders" && working[key] !== true) {
            const hasDependent = orderCapabilityKeys().some(
                capability => capability !== "view_orders" && working[capability] === true
            );
            if (hasDependent) {
                working.view_orders = true;
                $(this).prop("checked", true);
                frappe.show_alert({
                    message: __("عرض الطلبات مطلوب تلقائيًا عند منح أي صلاحية على الطلب."),
                    indicator: "orange",
                });
            }
        } else if (key !== "view_orders" && working[key] === true) {
            working.view_orders = true;
            $main.find('[data-capability="view_orders"]').prop("checked", true);
        }

        syncDirtyState();
        schedulePreview();
    }

    function schedulePreview() {
        clearTimeout(previewTimer);
        previewTimer = setTimeout(loadPreview, 180);
    }

    function loadPreview() {
        if (!selectedRole) return;
        const requestId = ++previewRequest;
        frappe
            .call({
                method: METHODS.preview,
                args: {
                    role: selectedRole,
                    capabilities: JSON.stringify(working),
                },
                freeze: false,
            })
            .then(response => {
                if (requestId !== previewRequest) return;
                preview = response.message || {};
                working = clone(preview.capabilities || working);
                syncCheckboxes();
                renderImpact(preview);
                syncDirtyState();
            })
            .catch(error => {
                if (requestId !== previewRequest) return;
                frappe.show_alert({
                    message: error && error.message ? error.message : __("تعذر حساب أثر الصلاحيات."),
                    indicator: "red",
                });
            });
    }

    function syncCheckboxes() {
        $main.find(".apc-capability-input").each(function () {
            const key = String($(this).attr("data-capability") || "");
            $(this).prop("checked", working[key] === true);
        });
    }

    function renderImpact(data) {
        const impact = data && data.impact ? data.impact : {};
        const navigation = impact.navigation || {};
        const changes = Array.isArray(data && data.changes) ? data.changes : [];
        const workspaces = Array.isArray(navigation.workspaces) ? navigation.workspaces : [];
        const sections = navigation.sections || {};
        const enabledSections = Object.keys(sections).filter(key => sections[key] === true);
        const sectionLabels = {
            orders: __("الطلبات"), costing: __("التكلفة"), planning: __("خطة القص"),
            drawing: __("الرسم"), production: __("الإنتاج"), administration: __("الإدارة"), reports: __("التقارير"),
        };
        const homeLabel = navigation.home_page === "shop-floor-inbox"
            ? __("صالة الإنتاج")
            : navigation.home_page === "almdina-erp"
                ? __("واجهة Almdina الرئيسية")
                : __("لا يغيّر الصفحة الرئيسية");
        const warning = data && data.requires_self_lockout_confirmation
            ? `<div class="apc-warning">${__("هذا التغيير يزيل آخر صلاحية لديك لإدارة الصلاحيات. بعد الحفظ قد لا تستطيع العودة إلى هذه الصفحة.")}</div>`
            : "";
        const changeHtml = changes.length
            ? changes.map(change => `
                <div class="apc-change">
                    <span>${esc(change.label)}</span>
                    <span class="${change.after ? "on" : "off"}">${change.after ? __("تفعيل") : __("إلغاء")}</span>
                </div>
            `).join("")
            : `<div class="text-muted" style="font-size:12px">${__("لا توجد تغييرات غير محفوظة.")}</div>`;

        $main.find(".apc-enabled-count").text(impact.enabled_count || 0);
        $main.find(".apc-critical-count").text(impact.critical_count || 0);
        $main.find(".apc-change-count").text(changes.length);
        $main.find(".apc-impact-panel").html(`
            <div class="apc-panel-title">${__("أثر الصلاحيات")}</div>
            ${warning}
            <div style="margin-top:10px;font-size:12px"><span class="text-muted">${__("الصفحة الرئيسية")}</span><br><b>${esc(homeLabel)}</b></div>
            <div style="margin-top:12px" class="apc-panel-title">${__("مساحات العمل")}</div>
            <div class="apc-chip-row">${workspaces.length ? workspaces.map(item => `<span class="apc-chip">${esc(item)}</span>`).join("") : `<span class="text-muted">${__("لا توجد مساحة إضافية")}</span>`}</div>
            <div style="margin-top:12px" class="apc-panel-title">${__("الأقسام الظاهرة")}</div>
            <div class="apc-chip-row">${enabledSections.length ? enabledSections.map(key => `<span class="apc-chip">${esc(sectionLabels[key] || key)}</span>`).join("") : `<span class="text-muted">${__("لا توجد أقسام")}</span>`}</div>
            <div style="margin-top:14px" class="apc-panel-title">${__("التغييرات الحالية")}</div>
            <div>${changeHtml}</div>
        `);
    }

    function renderAudit(rows) {
        const html = rows.length
            ? rows.map(row => `
                <div class="apc-audit-item">
                    <div><b>${esc(row.changed_by || "")}</b> · ${esc(row.changed_on || "")}</div>
                    <div>${__("عدد التغييرات")}: <b>${esc(row.change_count || 0)}</b></div>
                    <div class="text-muted" dir="ltr">${esc(row.changed_capabilities || "")}</div>
                </div>
            `).join("")
            : `<div class="text-muted" style="font-size:12px">${__("لا توجد تغييرات مسجلة لهذا الدور.")}</div>`;
        $main.find(".apc-audit-panel").html(`
            <div class="apc-panel-title">${__("آخر تغييرات الدور")}</div>
            <div class="apc-audit-list">${html}</div>
        `);
    }

    function syncDirtyState() {
        const dirty = isDirty();
        $main.find(".apc-dirty")
            .toggleClass("is-dirty", dirty)
            .text(dirty ? __("توجد تغييرات غير محفوظة") : __("لا توجد تغييرات غير محفوظة"));
        $main.find(".apc-save, .apc-reset").prop("disabled", !dirty || saving);
    }

    function resetWorkingState() {
        working = clone(baseline);
        preview = null;
        syncCheckboxes();
        syncDirtyState();
        loadPreview();
    }

    function savePermissions() {
        if (!selectedRole || !isDirty() || saving) return;
        const continueSave = () => {
            const needsLockoutConfirmation = Boolean(preview && preview.requires_self_lockout_confirmation);
            const message = needsLockoutConfirmation
                ? __("سيؤدي هذا الحفظ إلى إزالة آخر صلاحية لديك لإدارة الصلاحيات. هل أنت متأكد تمامًا؟")
                : __("هل تريد حفظ تغييرات صلاحيات الدور {0}؟", [selectedRole]);
            frappe.confirm(message, () => persistPermissions(needsLockoutConfirmation));
        };
        if (!preview || stable(preview.capabilities || {}) !== stable(working)) {
            loadPreview().then ? loadPreview().then(continueSave) : setTimeout(continueSave, 250);
            return;
        }
        continueSave();
    }

    function persistPermissions(confirmSelfLockout) {
        saving = true;
        syncDirtyState();
        frappe
            .call({
                method: METHODS.update,
                args: {
                    role: selectedRole,
                    capabilities: JSON.stringify(working),
                    confirm_self_lockout: confirmSelfLockout ? 1 : 0,
                },
                freeze: true,
                freeze_message: __("جاري حفظ الصلاحيات وتحديث جلسات المستخدمين..."),
            })
            .then(response => {
                const data = response.message || {};
                baseline = clone(data.capabilities || {});
                working = clone(data.capabilities || {});
                preview = {
                    capabilities: clone(working),
                    changes: [],
                    impact: data.impact || {},
                    requires_self_lockout_confirmation: false,
                };
                syncCheckboxes();
                renderImpact(preview);
                renderAudit(data.audit || []);
                frappe.show_alert({ message: __("تم حفظ صلاحيات الدور بنجاح."), indicator: "green" });
            })
            .catch(error => {
                frappe.msgprint({
                    title: __("تعذر حفظ الصلاحيات"),
                    message: esc(error && error.message ? error.message : __("حدث خطأ غير متوقع.")),
                    indicator: "red",
                });
            })
            .finally(() => {
                saving = false;
                syncDirtyState();
            });
    }

    function showEmpty(message) {
        $main.find(".apc-content, .apc-savebar").hide();
        $main.find(".apc-loading").show().text(message);
    }

    function showError(error, fallback) {
        const message = error && error.message ? error.message : fallback;
        showEmpty(message);
    }

    loadConsole();
};
