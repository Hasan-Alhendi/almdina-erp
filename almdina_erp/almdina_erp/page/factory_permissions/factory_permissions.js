frappe.pages["factory-permissions"].on_page_load = function (wrapper) {
    "use strict";

    const METHODS = Object.freeze({
        console: "almdina_erp.almdina_erp.services.permission_management_service.get_permission_console",
        role: "almdina_erp.almdina_erp.services.permission_management_service.get_role_permissions",
        preview: "almdina_erp.almdina_erp.services.permission_management_service.preview_role_permissions",
        update: "almdina_erp.almdina_erp.services.permission_management_service.update_role_permissions",
    });

    const state = {
        catalog: [],
        roles: [],
        actor: {},
        selectedRole: "",
        selected: null,
        baseline: {},
        working: {},
        preview: null,
        roleQuery: "",
        capabilityQuery: "",
        enabledOnly: false,
        roleRequest: 0,
        previewRequest: 0,
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
            Object.keys(value || {}).sort().reduce((result, key) => {
                result[key] = value[key] === true;
                return result;
            }, {})
        );
    }

    function isDirty() {
        return stable(state.baseline) !== stable(state.working);
    }

    function allCapabilities() {
        return state.catalog.flatMap(group => group.capabilities || []);
    }

    function capabilityMap() {
        return new Map(allCapabilities().map(item => [item.key, item]));
    }

    function localMissingDependencies() {
        const byKey = capabilityMap();
        return allCapabilities()
            .filter(item => state.working[item.key] === true)
            .map(item => {
                const missing = (item.requires || []).filter(
                    required => state.working[required] !== true
                );
                return {
                    key: item.key,
                    label: item.label,
                    missing,
                    missingLabels: missing.map(
                        key => (byKey.get(key) || {}).label || key
                    ),
                };
            })
            .filter(item => item.missing.length);
    }

    function injectStyles() {
        if (document.getElementById("almdina-permission-console-style")) return;
        const style = document.createElement("style");
        style.id = "almdina-permission-console-style";
        style.textContent = `
            .apc-shell{direction:rtl;padding-bottom:96px}.apc-hero{display:flex;justify-content:space-between;gap:20px;padding:22px;margin-bottom:14px;border:1px solid var(--border-color);border-radius:18px;background:var(--fg-color)}.apc-hero h2{margin:0 0 7px;font-size:22px;font-weight:800}.apc-hero p{margin:0;max-width:860px;color:var(--text-muted);line-height:1.85}.apc-actor{min-width:210px;text-align:left;direction:ltr;font-size:12px;line-height:1.7}
            .apc-toolbar{display:grid;grid-template-columns:minmax(280px,1fr) minmax(320px,1.25fr) minmax(250px,.8fr);gap:12px;margin-bottom:14px}.apc-panel{border:1px solid var(--border-color);border-radius:15px;background:var(--fg-color);padding:15px}.apc-panel-title{font-size:13px;font-weight:800;margin-bottom:8px}.apc-panel-hint{margin-top:7px;color:var(--text-muted);font-size:11px;line-height:1.6}.apc-role-tools{display:grid;grid-template-columns:minmax(130px,.7fr) minmax(170px,1fr);gap:8px}.apc-filter-tools{display:grid;grid-template-columns:minmax(180px,1fr) auto;gap:8px}.apc-input,.apc-select{width:100%;min-height:42px;border:1px solid var(--border-color);border-radius:10px;padding:8px 11px;background:var(--control-bg);color:var(--text-color);outline:none}.apc-input:focus,.apc-select:focus{border-color:var(--primary);box-shadow:0 0 0 2px color-mix(in srgb,var(--primary) 16%,transparent)}
            .apc-filter-toggle{min-width:112px;border-radius:10px}.apc-filter-toggle.is-active{background:var(--primary)!important;border-color:var(--primary)!important;color:var(--fg-color)!important}.apc-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.apc-stat{padding:9px 6px;border-radius:10px;background:var(--subtle-fg);text-align:center}.apc-stat strong{display:block;font-size:18px}.apc-stat span{font-size:11px;color:var(--text-muted)}
            .apc-content{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(300px,.72fr);gap:14px;align-items:start}.apc-groups{display:grid;gap:12px}.apc-group{border:1px solid var(--border-color);border-radius:15px;overflow:hidden;background:var(--fg-color)}.apc-group-head{display:flex;justify-content:space-between;gap:12px;padding:13px 15px;background:var(--subtle-fg);border-bottom:1px solid var(--border-color)}.apc-group-head h4{margin:0 0 3px;font-size:15px;font-weight:800}.apc-group-head p{margin:0;font-size:12px;color:var(--text-muted)}.apc-group-count{align-self:center;border-radius:999px;padding:4px 8px;background:var(--fg-color);font-size:11px;font-weight:700;color:var(--text-muted)}
            .apc-capability{display:grid;grid-template-columns:46px minmax(0,1fr) auto;gap:11px;align-items:center;padding:12px 15px;border-bottom:1px solid var(--border-color);cursor:pointer}.apc-capability:last-child{border-bottom:0}.apc-capability:hover{background:var(--subtle-fg)}.apc-capability.is-invalid{outline:2px solid var(--orange-300);outline-offset:-2px}.apc-capability-title{display:block;font-size:13px;font-weight:800;margin-bottom:2px}.apc-capability-description{display:block;font-size:12px;line-height:1.6;color:var(--text-muted)}.apc-requires{display:block;margin-top:5px;font-size:11px;line-height:1.6;color:var(--orange-700)}.apc-switch{position:relative;width:42px;height:24px;display:inline-block;margin:0}.apc-switch input{opacity:0;width:0;height:0}.apc-slider{position:absolute;inset:0;cursor:pointer;border-radius:24px;background:var(--gray-400);transition:.18s}.apc-slider:before{content:"";position:absolute;width:18px;height:18px;right:3px;top:3px;border-radius:50%;background:var(--fg-color);box-shadow:0 1px 3px rgba(0,0,0,.2);transition:.18s}.apc-switch input:checked+.apc-slider{background:var(--primary)}.apc-switch input:checked+.apc-slider:before{transform:translateX(-18px)}
            .apc-badges{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}.apc-badge{border-radius:999px;padding:3px 7px;font-size:10px;font-weight:800;white-space:nowrap;background:var(--subtle-fg)}.apc-badge.sensitive{color:var(--orange-700)}.apc-badge.critical{color:var(--red-600)}.apc-side{position:sticky;top:58px;display:grid;gap:12px}.apc-chip-row{display:flex;flex-wrap:wrap;gap:6px}.apc-chip{border-radius:999px;padding:5px 9px;background:var(--subtle-fg);font-size:11px;font-weight:700}.apc-warning,.apc-error{padding:10px;border-radius:10px;font-size:12px;line-height:1.7}.apc-warning{border:1px solid var(--orange-300)}.apc-error{border:1px solid var(--red-300);color:var(--red-600)}.apc-change{display:flex;justify-content:space-between;gap:8px;padding:7px 0;border-bottom:1px solid var(--border-color);font-size:12px}.apc-change:last-child{border-bottom:0}.apc-change .on{color:var(--green-600);font-weight:800}.apc-change .off{color:var(--red-600);font-weight:800}.apc-audit-list{display:grid;gap:8px}.apc-audit-item{padding:9px;border-radius:9px;background:var(--subtle-fg);font-size:11px;line-height:1.6}.apc-empty{padding:34px 18px;text-align:center;border:1px dashed var(--border-color);border-radius:14px;color:var(--text-muted);background:var(--subtle-fg)}
            .apc-savebar{position:fixed;z-index:90;right:0;left:0;bottom:0;display:flex;justify-content:center;pointer-events:none;padding:10px 16px}.apc-savebar-inner{pointer-events:auto;width:min(760px,calc(100vw - 30px));display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border:1px solid var(--border-color);border-radius:14px;background:var(--fg-color);box-shadow:0 8px 30px rgba(0,0,0,.13)}.apc-save-actions{display:flex;gap:8px}.apc-dirty{font-size:12px;font-weight:700;color:var(--text-muted)}.apc-dirty.is-dirty{color:var(--orange-700)}.apc-dirty.is-invalid{color:var(--red-600)}
            @media(max-width:1100px){.apc-toolbar{grid-template-columns:1fr 1fr}.apc-summary-panel{grid-column:1/-1}}@media(max-width:900px){.apc-content{grid-template-columns:1fr}.apc-side{position:static;grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.apc-hero{display:block;padding:16px}.apc-actor{margin-top:12px;text-align:right}.apc-toolbar,.apc-role-tools,.apc-filter-tools,.apc-side{grid-template-columns:1fr}.apc-capability{grid-template-columns:42px minmax(0,1fr)}.apc-badges{grid-column:2;justify-content:flex-start}.apc-savebar-inner{align-items:stretch;flex-direction:column}.apc-save-actions .btn{flex:1}}
        `;
        document.head.appendChild(style);
    }

    function renderShell() {
        $main.html(`
            <div class="apc-shell">
                <div class="apc-hero">
                    <div>
                        <h2>${__("مصفوفة صلاحيات Almdina")}</h2>
                        <p>${__("اختر دورًا ثم حدد صلاحياته يدويًا. لا توجد قوالب أو استيراد أو منح مخفية؛ كل صلاحية مفعلة هنا هي قرار صريح من المدير.")}</p>
                    </div>
                    <div class="apc-actor text-muted"></div>
                </div>
                <div class="apc-toolbar">
                    <div class="apc-panel">
                        <div class="apc-panel-title">${__("الدور")}</div>
                        <div class="apc-role-tools">
                            <input type="search" class="apc-input apc-role-search" placeholder="${__("ابحث عن دور...")}">
                            <select class="apc-select apc-role-select"></select>
                        </div>
                        <div class="apc-panel-hint">${__("كل دور جديد يبدأ دون صلاحيات، ثم تحدد ما يحتاجه فقط.")}</div>
                    </div>
                    <div class="apc-panel">
                        <div class="apc-panel-title">${__("البحث في الصلاحيات")}</div>
                        <div class="apc-filter-tools">
                            <input type="search" class="apc-input apc-capability-search" placeholder="${__("ابحث بالاسم أو الوصف...")}">
                            <button type="button" class="btn btn-default apc-filter-toggle" aria-pressed="false">${__("المفعلة فقط")}</button>
                        </div>
                        <div class="apc-panel-hint apc-filter-result"></div>
                    </div>
                    <div class="apc-panel apc-summary-panel">
                        <div class="apc-panel-title">${__("ملخص الدور")}</div>
                        <div class="apc-summary">
                            <div class="apc-stat"><strong class="apc-enabled-count">0</strong><span>${__("مفعلة")}</span></div>
                            <div class="apc-stat"><strong class="apc-critical-count">0</strong><span>${__("حرجة")}</span></div>
                            <div class="apc-stat"><strong class="apc-change-count">0</strong><span>${__("تغييرات")}</span></div>
                        </div>
                        <div class="apc-panel-hint">${__("لا يوجد نسخ أو تطبيق جماعي للصلاحيات؛ التعديل يتم على الدور المحدد فقط.")}</div>
                    </div>
                </div>
                <div class="apc-content">
                    <div class="apc-groups"></div>
                    <div class="apc-side">
                        <div class="apc-panel apc-dependencies"></div>
                        <div class="apc-panel apc-preview"></div>
                        <div class="apc-panel apc-audit"></div>
                    </div>
                </div>
                <div class="apc-savebar">
                    <div class="apc-savebar-inner">
                        <div class="apc-dirty">${__("لم يتم اختيار دور بعد")}</div>
                        <div class="apc-save-actions">
                            <button type="button" class="btn btn-default apc-reset" disabled>${__("تراجع")}</button>
                            <button type="button" class="btn btn-primary apc-save" disabled>${__("حفظ الصلاحيات")}</button>
                        </div>
                    </div>
                </div>
            </div>
        `);
    }

    function bindEvents() {
        $main.on("input", ".apc-role-search", function () {
            state.roleQuery = String($(this).val() || "").trim().toLowerCase();
            renderRoleOptions();
        });

        $main.on("change", ".apc-role-select", function () {
            const nextRole = String($(this).val() || "");
            if (!nextRole || nextRole === state.selectedRole) return;
            if (isDirty()) {
                frappe.confirm(
                    __("لديك تغييرات غير محفوظة. هل تريد تجاهلها والانتقال إلى الدور الآخر؟"),
                    () => loadRole(nextRole),
                    () => renderRoleOptions()
                );
                return;
            }
            loadRole(nextRole);
        });

        $main.on("input", ".apc-capability-search", function () {
            state.capabilityQuery = String($(this).val() || "").trim().toLowerCase();
            renderCapabilities();
        });

        $main.on("click", ".apc-filter-toggle", function () {
            state.enabledOnly = !state.enabledOnly;
            renderCapabilities();
            renderFilterToggle();
        });

        $main.on("change", ".apc-capability-toggle", function () {
            if (!state.selectedRole || state.saving) return;
            const key = String($(this).data("capability") || "");
            if (!key) return;
            state.working[key] = $(this).is(":checked");
            state.preview = null;
            renderCapabilities();
            renderSummary();
            renderDependencies();
            renderSaveBar();
            schedulePreview();
        });

        $main.on("click", ".apc-reset", function () {
            if (!state.selectedRole || state.saving) return;
            state.working = clone(state.baseline);
            state.preview = null;
            renderAll();
            loadPreview().then(() => renderPreview());
        });

        $main.on("click", ".apc-save", savePermissions);
    }

    function filteredRoles() {
        if (!state.roleQuery) return state.roles;
        return state.roles.filter(row =>
            String(row.name || "").toLowerCase().includes(state.roleQuery)
        );
    }

    function renderRoleOptions() {
        const roles = filteredRoles();
        const $select = $main.find(".apc-role-select");
        const options = [
            `<option value="">${esc(__("اختر دورًا"))}</option>`,
            ...roles.map(row =>
                `<option value="${esc(row.name)}" ${row.name === state.selectedRole ? "selected" : ""}>${esc(row.name)}</option>`
            ),
        ];
        $select.html(options.join(""));
    }

    function renderActor() {
        const fullName = state.actor.full_name || state.actor.user || "";
        const user = state.actor.user || "";
        $main.find(".apc-actor").html(
            fullName
                ? `<strong>${esc(fullName)}</strong><br>${esc(user)}`
                : ""
        );
    }

    function capabilityMatches(item) {
        if (state.enabledOnly && state.working[item.key] !== true) return false;
        if (!state.capabilityQuery) return true;
        const haystack = [
            item.key,
            item.label,
            item.description,
            item.doctype,
            ...(item.requires_labels || []),
        ].join(" ").toLowerCase();
        return haystack.includes(state.capabilityQuery);
    }

    function renderCapabilities() {
        const missing = new Set(
            localMissingDependencies().flatMap(item => [item.key, ...item.missing])
        );
        let visibleCount = 0;
        const groups = state.catalog.map(group => {
            const items = (group.capabilities || []).filter(capabilityMatches);
            visibleCount += items.length;
            if (!items.length) return "";
            return `
                <section class="apc-group">
                    <div class="apc-group-head">
                        <div>
                            <h4>${esc(group.label)}</h4>
                            <p>${esc(group.description)}</p>
                        </div>
                        <span class="apc-group-count">${items.length}</span>
                    </div>
                    ${items.map(item => {
                        const checked = state.working[item.key] === true;
                        const requires = item.requires_labels || [];
                        const riskClass = item.risk === "critical" ? "critical" : item.risk === "sensitive" ? "sensitive" : "";
                        return `
                            <label class="apc-capability ${missing.has(item.key) && checked ? "is-invalid" : ""}">
                                <span class="apc-switch">
                                    <input class="apc-capability-toggle" type="checkbox" data-capability="${esc(item.key)}" ${checked ? "checked" : ""} ${state.selectedRole ? "" : "disabled"}>
                                    <span class="apc-slider"></span>
                                </span>
                                <span>
                                    <span class="apc-capability-title">${esc(item.label)}</span>
                                    <span class="apc-capability-description">${esc(item.description)}</span>
                                    ${requires.length ? `<span class="apc-requires">${esc(__("يتطلب أيضًا"))}: ${requires.map(esc).join("، ")}. ${esc(__("لن يضيف النظام هذه الصلاحيات تلقائيًا"))}.</span>` : ""}
                                </span>
                                <span class="apc-badges">
                                    ${item.standard ? `<span class="apc-badge">${esc(__("Frappe"))}</span>` : ""}
                                    ${riskClass ? `<span class="apc-badge ${riskClass}">${esc(item.risk === "critical" ? __("حرجة") : __("حساسة"))}</span>` : ""}
                                </span>
                            </label>
                        `;
                    }).join("")}
                </section>
            `;
        }).join("");

        $main.find(".apc-groups").html(
            groups || `<div class="apc-empty">${esc(state.selectedRole ? __("لا توجد صلاحيات مطابقة للبحث الحالي.") : __("اختر دورًا لعرض الصلاحيات."))}</div>`
        );
        $main.find(".apc-filter-result").text(
            state.selectedRole
                ? __("{0} صلاحية ظاهرة من أصل {1}", [visibleCount, allCapabilities().length])
                : __("اختر دورًا أولًا")
        );
    }

    function renderFilterToggle() {
        $main.find(".apc-filter-toggle")
            .toggleClass("is-active", state.enabledOnly)
            .attr("aria-pressed", state.enabledOnly ? "true" : "false");
    }

    function renderSummary() {
        const enabled = allCapabilities().filter(item => state.working[item.key] === true);
        const critical = enabled.filter(item => item.risk === "critical");
        const changes = state.preview?.changes || [];
        $main.find(".apc-enabled-count").text(enabled.length);
        $main.find(".apc-critical-count").text(critical.length);
        $main.find(".apc-change-count").text(changes.length || (isDirty() ? "…" : 0));
    }

    function renderDependencies() {
        const missing = localMissingDependencies();
        const $target = $main.find(".apc-dependencies");
        if (!state.selectedRole) {
            $target.html(`<div class="apc-panel-title">${esc(__("الاعتمادات"))}</div><div class="apc-empty">${esc(__("اختر دورًا أولًا."))}</div>`);
            return;
        }
        if (!missing.length) {
            $target.html(`<div class="apc-panel-title">${esc(__("الاعتمادات"))}</div><div class="apc-chip-row"><span class="apc-chip">${esc(__("المصفوفة مكتملة"))}</span></div><div class="apc-panel-hint">${esc(__("كل صلاحية مفعلة لديها الصلاحيات المطلوبة صراحةً."))}</div>`);
            return;
        }
        $target.html(`
            <div class="apc-panel-title">${esc(__("صلاحيات مطلوبة قبل الحفظ"))}</div>
            <div class="apc-error">${missing.map(item => `${esc(item.label)} ← ${item.missingLabels.map(esc).join("، ")}`).join("<br>")}</div>
            <div class="apc-panel-hint">${esc(__("لن يضيف النظام هذه الصلاحيات تلقائيًا. فعّلها أنت فقط عندما تكون مطلوبة فعلًا للدور."))}</div>
        `);
    }

    function renderPreview() {
        const $target = $main.find(".apc-preview");
        if (!state.selectedRole) {
            $target.html(`<div class="apc-panel-title">${esc(__("معاينة التغييرات"))}</div><div class="apc-empty">${esc(__("لا يوجد دور محدد."))}</div>`);
            return;
        }
        if (localMissingDependencies().length) {
            $target.html(`<div class="apc-panel-title">${esc(__("معاينة التغييرات"))}</div><div class="apc-warning">${esc(__("أكمل الصلاحيات المطلوبة أولًا لعرض معاينة الخادم."))}</div>`);
            return;
        }
        const changes = state.preview?.changes || [];
        if (!changes.length) {
            $target.html(`<div class="apc-panel-title">${esc(__("معاينة التغييرات"))}</div><div class="apc-empty">${esc(isDirty() ? __("جاري تحديث المعاينة…") : __("لا توجد تغييرات غير محفوظة."))}</div>`);
            return;
        }
        $target.html(`
            <div class="apc-panel-title">${esc(__("معاينة التغييرات"))}</div>
            ${changes.map(change => `
                <div class="apc-change">
                    <span>${esc(change.label)}</span>
                    <span class="${change.after ? "on" : "off"}">${esc(change.after ? __("تفعيل") : __("إلغاء"))}</span>
                </div>
            `).join("")}
            ${state.preview?.requires_self_lockout_confirmation ? `<div class="apc-warning">${esc(__("هذا التعديل سيزيل آخر صلاحية لديك لإدارة الصلاحيات وسيطلب تأكيدًا إضافيًا عند الحفظ."))}</div>` : ""}
        `);
    }

    function renderAudit() {
        const rows = state.selected?.audit || [];
        const $target = $main.find(".apc-audit");
        $target.html(`
            <div class="apc-panel-title">${esc(__("آخر تعديلات الدور"))}</div>
            ${rows.length ? `<div class="apc-audit-list">${rows.map(row => `
                <div class="apc-audit-item">
                    <strong>${esc(row.changed_by || "")}</strong><br>
                    ${esc(row.changed_on || "")} · ${esc(__("{0} تغيير", [row.change_count || 0]))}
                </div>
            `).join("")}</div>` : `<div class="apc-empty">${esc(__("لا يوجد سجل تغييرات لهذا الدور بعد."))}</div>`}
        `);
    }

    function renderSaveBar() {
        const dirty = isDirty();
        const invalid = localMissingDependencies().length > 0;
        const disabled = !state.selectedRole || !dirty || invalid || state.saving;
        const $dirty = $main.find(".apc-dirty");
        $dirty
            .toggleClass("is-dirty", dirty && !invalid)
            .toggleClass("is-invalid", invalid)
            .text(
                !state.selectedRole
                    ? __("لم يتم اختيار دور بعد")
                    : invalid
                        ? __("لا يمكن الحفظ قبل استكمال الصلاحيات المطلوبة")
                        : dirty
                            ? __("توجد تغييرات غير محفوظة")
                            : __("كل التغييرات محفوظة")
            );
        $main.find(".apc-reset").prop("disabled", !state.selectedRole || !dirty || state.saving);
        $main.find(".apc-save").prop("disabled", disabled).text(state.saving ? __("جارٍ الحفظ…") : __("حفظ الصلاحيات"));
    }

    function renderAll() {
        renderRoleOptions();
        renderActor();
        renderFilterToggle();
        renderCapabilities();
        renderSummary();
        renderDependencies();
        renderPreview();
        renderAudit();
        renderSaveBar();
    }

    function schedulePreview() {
        window.clearTimeout(state.previewTimer);
        if (!state.selectedRole || localMissingDependencies().length) {
            state.preview = null;
            renderPreview();
            return;
        }
        state.previewTimer = window.setTimeout(() => {
            loadPreview().then(() => {
                renderSummary();
                renderPreview();
                renderSaveBar();
            });
        }, 220);
    }

    function loadPreview() {
        if (!state.selectedRole || localMissingDependencies().length) {
            return Promise.resolve(null);
        }
        const request = ++state.previewRequest;
        return frappe.call({
            method: METHODS.preview,
            args: {
                role: state.selectedRole,
                capabilities: JSON.stringify(state.working),
            },
        }).then(response => {
            if (request !== state.previewRequest) return null;
            state.preview = response.message || null;
            return state.preview;
        }).catch(error => {
            if (request === state.previewRequest) state.preview = null;
            throw error;
        });
    }

    function applySelected(payload) {
        state.selected = payload || null;
        state.selectedRole = payload?.role || "";
        state.baseline = clone(payload?.capabilities || {});
        state.working = clone(state.baseline);
        state.preview = null;
        renderAll();
        if (state.selectedRole) {
            loadPreview().then(() => {
                renderSummary();
                renderPreview();
            });
        }
    }

    function loadRole(role) {
        const request = ++state.roleRequest;
        return frappe.call({
            method: METHODS.role,
            args: { role },
            freeze: true,
            freeze_message: __("تحميل صلاحيات الدور…"),
        }).then(response => {
            if (request !== state.roleRequest) return;
            applySelected(response.message || null);
        });
    }

    function loadConsole() {
        const routeRole = String((frappe.get_route && frappe.get_route()[2]) || "").trim();
        return frappe.call({
            method: METHODS.console,
            args: { role: routeRole || undefined },
            freeze: true,
            freeze_message: __("تحميل مصفوفة الصلاحيات…"),
        }).then(response => {
            const message = response.message || {};
            state.catalog = message.catalog || [];
            state.roles = message.roles || [];
            state.actor = message.actor || {};
            if (message.selected) {
                applySelected(message.selected);
                return;
            }
            renderAll();
            if (state.roles.length) loadRole(state.roles[0].name);
        });
    }

    function savePermissions() {
        if (!state.selectedRole || state.saving || !isDirty()) return;
        if (localMissingDependencies().length) {
            frappe.msgprint(__("أكمل الصلاحيات المطلوبة قبل الحفظ."));
            return;
        }

        loadPreview().then(preview => {
            const execute = confirmSelfLockout => {
                state.saving = true;
                renderSaveBar();
                return frappe.call({
                    method: METHODS.update,
                    args: {
                        role: state.selectedRole,
                        capabilities: JSON.stringify(state.working),
                        confirm_self_lockout: confirmSelfLockout ? 1 : 0,
                    },
                    freeze: true,
                    freeze_message: __("حفظ صلاحيات الدور…"),
                }).then(response => {
                    applySelected(response.message || null);
                    frappe.show_alert({ message: __("تم حفظ صلاحيات الدور."), indicator: "green" });
                }).finally(() => {
                    state.saving = false;
                    renderSaveBar();
                });
            };

            if (preview?.requires_self_lockout_confirmation) {
                frappe.confirm(
                    __("هذا التعديل يزيل آخر صلاحية لديك لإدارة الصلاحيات. هل تريد المتابعة؟"),
                    () => execute(true)
                );
                return;
            }
            execute(false);
        });
    }
};
