(() => {
    "use strict";

    if (window.AlmdinaFactoryPermissionsController) return;

    const EVENT_NAMESPACE = ".almdinaFactoryPermissions";

    function mount(wrapper) {
        if (!wrapper) throw new Error("Factory permissions wrapper is required");
        if (
            wrapper.__almdinaFactoryPermissionsController
            && typeof wrapper.__almdinaFactoryPermissionsController.dispose === "function"
        ) {
            wrapper.__almdinaFactoryPermissionsController.dispose();
        }

        const frontend = window.AlmdinaFrontend;
        const api = window.AlmdinaFactoryPermissionsApi;
        const stateModule = window.AlmdinaFactoryPermissionsState;
        if (!frontend || !api || !stateModule) {
            throw new Error("Factory permissions frontend modules are unavailable");
        }

        const store = stateModule.create();
        const state = store.data;
        const lifecycle = store.lifecycle;
        const clone = store.clone;
        const stable = store.stable;
        const unique = store.unique;
        const isDirty = store.isDirty;

        frappe.ui.make_app_page({
            parent: wrapper,
            title: __("إدارة صلاحيات المعمل"),
            single_column: true,
        });

        const $main = $(wrapper).find(".layout-main-section");
        renderShell();
        bindEvents();
        if (window.AlmdinaPageRevisit) {
            // Unsaved matrix edits outrank freshness: only reload a clean console.
            window.AlmdinaPageRevisit.refreshOnRevisit(wrapper, () => (
                state.saving || isDirty() ? null : loadConsole()
            ));
        }
        loadConsole();

        const instance = Object.freeze({
            dispose() {
                lifecycle.dispose();
                $main.off(EVENT_NAMESPACE);
                $(document).off(EVENT_NAMESPACE);
                if (wrapper.__almdinaFactoryPermissionsController === instance) {
                    wrapper.__almdinaFactoryPermissionsController = null;
                }
            },
        });
        wrapper.__almdinaFactoryPermissionsController = instance;
        return instance;

        function esc(value) {
            return frappe.utils.escape_html(String(value ?? ""));
        }

        function errorMessage(error, fallback) {
            return frontend.errorMessage(error, fallback);
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
            $main.off(EVENT_NAMESPACE);
            $(document).off(EVENT_NAMESPACE);

            $main.on(`focus${EVENT_NAMESPACE} input${EVENT_NAMESPACE}`, ".apc-role-picker", function () {
                renderRoleMenu(String($(this).val() || ""));
                openRoleMenu();
            });
            $main.on(`keydown${EVENT_NAMESPACE}`, ".apc-role-picker", handleRolePickerKeydown);
            $main.on(`click${EVENT_NAMESPACE}`, ".apc-role-toggle", function () {
                const $menu = $main.find(".apc-role-menu");
                if ($menu.prop("hidden")) {
                    renderRoleMenu("");
                    openRoleMenu();
                    $main.find(".apc-role-picker").trigger("focus");
                } else {
                    closeRoleMenu(true);
                }
            });
            $main.on(`click${EVENT_NAMESPACE}`, ".apc-role-option", function () {
                chooseRole(String($(this).attr("data-role") || ""));
            });
            $(document).on(`mousedown${EVENT_NAMESPACE}`, event => {
                if (!$(event.target).closest(".apc-role-combo").length) closeRoleMenu(true);
            });
            $main.on(`change${EVENT_NAMESPACE}`, ".apc-capability-input", onCapabilityChange);
            $main.on(`click${EVENT_NAMESPACE}`, ".apc-select-all-group", onGroupBulkToggle);
            $main.on(`click${EVENT_NAMESPACE}`, ".apc-select-all-global", onGlobalBulkToggle);
            $main.on(`click${EVENT_NAMESPACE}`, ".apc-export", exportSelectedRole);
            $main.on(`click${EVENT_NAMESPACE}`, ".apc-import", () => $main.find(".apc-import-file").trigger("click"));
            $main.on(`change${EVENT_NAMESPACE}`, ".apc-import-file", importPermissionFile);
            $main.on(`click${EVENT_NAMESPACE}`, ".apc-reset", resetWorkingState);
            $main.on(`click${EVENT_NAMESPACE}`, ".apc-save", savePermissions);

            lifecycle.track(() => $main.off(EVENT_NAMESPACE), "permissions-main-events");
            lifecycle.track(() => $(document).off(EVENT_NAMESPACE), "permissions-document-events");
        }

        function loadConsole() {
            return api.getConsole({ freeze: false }).then(data => {
                const resolved = data || {};
                state.catalog = Array.isArray(resolved.catalog) ? resolved.catalog : [];
                state.roles = Array.isArray(resolved.roles) ? resolved.roles : [];
                state.transfer = resolved.transfer || {};
                const actor = resolved.actor || {};
                $main.find(".apc-actor").html(`<div>${esc(actor.full_name || actor.user || "")}</div><div>${esc(actor.user || "")}</div>`);
                renderRoleMenu("");
                if (!state.roles.length) return showEmpty(__("لا توجد أدوار قابلة للإدارة."));
                return loadRole(String(state.roles[0].name || ""));
            }).catch(error => showError(error, __("تعذر فتح إدارة الصلاحيات.")));
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
            cancelPreviewTimer();
            store.requests.preview.invalidate();
            const token = store.requests.role.begin({ role });
            state.selectedRole = role;
            store.requests.transfer.invalidate();
            $main.find(".apc-role-picker").val(role);
            renderRoleMenu("");
            closeRoleMenu(false);
            $main.find(".apc-content,.apc-savebar").hide();
            $main.find(".apc-loading").show().text(__("جاري تحميل صلاحيات الدور..."));
            return api.getRole(role, { freeze: false }).then(data => {
                if (!store.requests.role.isCurrent(token) || role !== state.selectedRole) return;
                const resolved = data || {};
                state.baseline = clone(resolved.capabilities);
                state.working = clone(resolved.capabilities);
                state.preview = { capabilities: clone(state.working), changes: [], impact: resolved.impact || {} };
                renderPermissionGroups();
                renderImpact(state.preview);
                renderAudit(resolved.audit || []);
                syncDirtyState();
                $main.find(".apc-loading").hide();
                $main.find(".apc-content,.apc-savebar").show();
            }).catch(error => {
                if (store.requests.role.isCurrent(token)) showError(error, __("تعذر تحميل صلاحيات الدور."));
            });
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

        function cancelPreviewTimer() {
            lifecycle.track(() => {}, "permissions-preview-timer");
        }

        function queuePreview() {
            syncDirtyState();
            lifecycle.timeout(() => {
                loadPreview().then(() => syncDirtyState());
            }, 180, "permissions-preview-timer");
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
            const requestedRole = state.selectedRole;
            const requestedState = clone(state.working);
            const token = store.requests.preview.begin({ role: requestedRole, state: stable(requestedState) });
            return api.previewRole(requestedRole, requestedState, { freeze: false }).then(data => {
                if (
                    !store.requests.preview.isCurrent(token)
                    || requestedRole !== state.selectedRole
                    || stable(requestedState) !== stable(state.working)
                ) {
                    return null;
                }
                return applyPreview(data || {});
            }).catch(error => {
                if (store.requests.preview.isCurrent(token)) {
                    frappe.show_alert({ message: errorMessage(error, __("تعذر حساب أثر الصلاحيات.")), indicator: "red" });
                }
                return null;
            });
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

        function previewExternal(request, successMessage) {
            const requestedRole = state.selectedRole;
            const token = store.requests.transfer.begin({ role: requestedRole });
            return Promise.resolve().then(request).then(data => {
                if (!store.requests.transfer.isCurrent(token) || requestedRole !== state.selectedRole) return null;
                const preview = applyPreview(data || {});
                frappe.show_alert({ message: successMessage, indicator: "green" }, 6);
                return preview;
            }).catch(error => {
                if (store.requests.transfer.isCurrent(token)) {
                    frappe.msgprint({
                        title: __("تعذر تحميل الصلاحيات"),
                        message: esc(errorMessage(error, __("حدث خطأ غير متوقع."))),
                        indicator: "red",
                    });
                }
                return null;
            });
        }

        function exportSelectedRole() {
            if (!state.selectedRole) return;
            const requestedRole = state.selectedRole;
            api.exportRole(requestedRole, {
                freeze: true,
                freezeMessage: __("جاري تجهيز ملف الصلاحيات..."),
            }).then(documentData => {
                if (requestedRole !== state.selectedRole) return;
                const resolved = documentData || {};
                const blob = new Blob([JSON.stringify(resolved, null, 2)], { type: "application/json;charset=utf-8" });
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = `almdina-permissions-${requestedRole.replace(/[^a-zA-Z0-9_-]+/g, "-")}.json`;
                document.body.appendChild(link);
                link.click();
                link.remove();
                window.setTimeout(() => URL.revokeObjectURL(url), 1000);
                frappe.show_alert({ message: __("تم تصدير ملف الصلاحيات."), indicator: "green" });
            }).catch(error => frappe.msgprint({
                title: __("تعذر التصدير"),
                message: esc(errorMessage(error, __("حدث خطأ غير متوقع."))),
                indicator: "red",
            }));
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
                const role = state.selectedRole;
                previewExternal(
                    () => api.previewImport(role, payload, {
                        freeze: true,
                        freezeMessage: __("جاري التحقق من الصلاحيات..."),
                    }),
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
            store.invalidatePending();
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
            frappe.show_alert({ message: errorMessage(error, fallback), indicator: "red" }, 7);
        }

        function savePermissions() {
            if (!state.selectedRole || !isDirty() || state.saving) return;
            const executeSave = async confirmSelfLockout => {
                const requestedRole = state.selectedRole;
                const requestedState = clone(state.working);
                state.saving = true;
                store.invalidatePending();
                cancelPreviewTimer();
                syncDirtyState();
                try {
                    const data = await api.updateRole(
                        requestedRole,
                        requestedState,
                        confirmSelfLockout,
                        { freeze: true, freezeMessage: __("جاري حفظ الصلاحيات...") }
                    );
                    if (requestedRole !== state.selectedRole) return false;
                    const resolved = data || {};
                    state.baseline = clone(resolved.capabilities || requestedState);
                    state.working = clone(state.baseline);
                    state.preview = { capabilities: clone(state.working), changes: [], impact: resolved.impact || {} };
                    renderPermissionGroups();
                    renderImpact(state.preview);
                    renderAudit(resolved.audit || []);
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
            const message = errorMessage(error, fallback);
            showEmpty(message);
            frappe.show_alert({ message, indicator: "red" }, 7);
        }
    }

    window.AlmdinaFactoryPermissionsController = Object.freeze({ mount });
})();
