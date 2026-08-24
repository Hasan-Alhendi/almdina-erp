(() => {
    "use strict";

    if (window.AlmdinaFactoryPermissionsController) return;

    function mount(wrapper) {
        if (!wrapper) throw new Error("Factory permissions wrapper is required");
        if (
            wrapper.__almdinaFactoryPermissionsController
            && typeof wrapper.__almdinaFactoryPermissionsController.dispose === "function"
        ) {
            wrapper.__almdinaFactoryPermissionsController.dispose();
        }

        const frontend = window.AlmdinaFrontend;
        const pageLifecycleModule = window.AlmdinaPageRevisit;
        const api = window.AlmdinaFactoryPermissionsApi;
        const stateModule = window.AlmdinaFactoryPermissionsState;
        const viewModelModule = window.AlmdinaFactoryPermissionsViewModel;
        const rendererModule = window.AlmdinaFactoryPermissionsRenderer;
        const interactionsModule = window.AlmdinaFactoryPermissionsInteractions;
        if (
            !frontend
            || !pageLifecycleModule
            || typeof pageLifecycleModule.bindActivationLifecycle !== "function"
            || !api
            || !stateModule
            || !viewModelModule
            || !rendererModule
            || !interactionsModule
        ) {
            throw new Error("Factory permissions frontend modules are unavailable");
        }

        const store = stateModule.create();
        const state = store.data;
        const lifecycle = store.lifecycle;
        const clone = store.clone;
        const stable = store.stable;
        const unique = store.unique;
        const isDirty = store.isDirty;
        const viewModel = viewModelModule.create({ translate: __ });
        if (!wrapper.page) throw new Error("Factory permissions page shell is unavailable");

        const $main = $(wrapper).find(".layout-main-section");
        const renderer = rendererModule.create({
            $main,
            escapeHtml: value => frappe.utils.escape_html(String(value ?? "")),
            translate: __,
        });
        let activation = null;
        let featureShellReady = false;
        let reconcileAfterSave = false;
        const ownedTransients = new Set();
        const interactions = interactionsModule.bind({
            $main,
            lifecycle,
            renderer,
            callbacks: {
                onRoleQuery: renderRoleMenu,
                onRoleMenuClose: restore => renderer.closeRoleMenu(restore, state.selectedRole),
                onRoleSelected: chooseRole,
                onCapabilityChanged,
                onGroupToggle,
                onGlobalToggle,
                onExport: exportSelectedRole,
                onImportFile: importPermissionFile,
                onReset: resetWorkingState,
                onSave: savePermissions,
            },
        });

        const instance = Object.freeze({
            load: loadConsole,
            dispose() {
                closeTransientSurfaces();
                interactions.dispose();
                store.dispose();
                if (wrapper.__almdinaFactoryPermissionsController === instance) {
                    wrapper.__almdinaFactoryPermissionsController = null;
                }
            },
        });
        wrapper.__almdinaFactoryPermissionsController = instance;
        activation = pageLifecycleModule.bindActivationLifecycle(wrapper, {
            onActivate: activatePage,
            onDeactivate: () => {
                closeTransientSurfaces();
                cancelPreviewTimer();
                store.deactivate();
            },
        });
        if (!activation) {
            instance.dispose();
            throw new Error("Factory permissions page lifecycle is unavailable");
        }
        lifecycle.track(() => activation.dispose(), "permissions-page-activation");
        if (activation.isActive()) activatePage();
        return instance;

        function errorMessage(error, fallback) {
            return frontend.errorMessage(error, fallback);
        }

        function isActive() {
            return Boolean(activation && activation.isActive());
        }

        function activeGeneration() {
            return isActive() ? activation.generation() : null;
        }

        function isCurrentGeneration(generation) {
            return generation !== null
                && isActive()
                && activation.generation() === generation;
        }

        function ownTransient(surface) {
            if (surface && typeof surface.hide === "function") ownedTransients.add(surface);
            return surface;
        }

        function closeTransientSurfaces() {
            for (const surface of ownedTransients) surface.hide();
            ownedTransients.clear();
        }

        function confirmForGeneration(message, generation, onConfirm, onCancel) {
            if (!isCurrentGeneration(generation)) return null;
            let surface = null;
            const invoke = callback => () => {
                if (surface) ownedTransients.delete(surface);
                if (!isCurrentGeneration(generation)) return null;
                return typeof callback === "function" ? callback() : null;
            };
            surface = frappe.confirm(message, invoke(onConfirm), invoke(onCancel));
            return ownTransient(surface);
        }

        function showMessage(options) {
            return ownTransient(frappe.msgprint(options));
        }

        function activatePage() {
            if (state.saving) return null;
            if (reconcileAfterSave) return loadConsole({ reconcile: true });
            return isDirty() ? null : loadConsole();
        }

        function ensureFeatureShell() {
            if (featureShellReady) return;
            renderer.renderShell();
            featureShellReady = true;
        }

        function renderRoleMenu(query) {
            renderer.renderRoleMenu(viewModel.roleMenu(state.roles, query, state.selectedRole));
        }

        function chooseRole(role) {
            if (!role) return;
            renderer.setRolePickerValue(role);
            renderer.closeRoleMenu(false, state.selectedRole);
            if (role !== state.selectedRole) requestRoleChange(role);
        }

        function requestRoleChange(role) {
            const generation = activeGeneration();
            if (generation === null) return null;
            const selectRole = () => {
                store.requests.console.invalidate();
                return loadRole(role);
            };
            if (!isDirty()) return selectRole();
            return confirmForGeneration(
                __("لديك تغييرات غير محفوظة. هل تريد تجاهلها؟"),
                generation,
                selectRole,
                () => renderer.setRolePickerValue(state.selectedRole)
            );
        }

        function loadConsole(options = {}) {
            const reconcile = options.reconcile === true;
            if (!isActive() || state.saving || (!reconcile && isDirty())) return Promise.resolve(null);
            store.requests.role.invalidate();
            store.invalidatePending();
            const token = store.requests.console.begin();
            return api.getConsole({ freeze: false }).then(data => {
                if (!isActive() || !store.requests.console.isCurrent(token)) return null;
                const resolved = data || {};
                ensureFeatureShell();
                state.catalog = Array.isArray(resolved.catalog) ? resolved.catalog : [];
                state.roles = Array.isArray(resolved.roles) ? resolved.roles : [];
                state.transfer = resolved.transfer || {};
                renderer.renderActor(resolved.actor || {});
                renderRoleMenu("");
                if (!state.roles.length) return showEmpty(__("لا توجد أدوار قابلة للإدارة."));
                const selected = state.roles.find(role => String(role.name || "") === state.selectedRole);
                const role = String((selected || state.roles[0]).name || "");
                return loadRole(role, { reconcile });
            }).catch(error => {
                if (!isActive() || !store.requests.console.isCurrent(token)) return null;
                showError(error, __("تعذر فتح إدارة الصلاحيات."));
                return null;
            });
        }

        function loadRole(role, options = {}) {
            if (!isActive()) return Promise.resolve(null);
            cancelPreviewTimer();
            store.requests.preview.invalidate();
            const token = store.requests.role.begin({ role });
            state.selectedRole = role;
            store.requests.transfer.invalidate();
            renderer.setRolePickerValue(role);
            renderRoleMenu("");
            renderer.closeRoleMenu(false, role);
            renderer.showRoleLoading(__("جاري تحميل صلاحيات الدور..."));
            return api.getRole(role, { freeze: false }).then(data => {
                if (!isActive() || !store.requests.role.isCurrent(token) || role !== state.selectedRole) return null;
                const resolved = data || {};
                state.baseline = clone(resolved.capabilities);
                state.working = clone(resolved.capabilities);
                state.preview = { capabilities: clone(state.working), changes: [], impact: resolved.impact || {} };
                if (options.reconcile === true) reconcileAfterSave = false;
                renderPermissionState(resolved.audit || []);
                renderer.showLoaded();
            }).catch(error => {
                if (isActive() && store.requests.role.isCurrent(token)) {
                    showError(error, __("تعذر تحميل صلاحيات الدور."));
                }
                return null;
            });
        }

        function renderPermissionState(auditRows) {
            renderer.renderPermissionGroups(viewModel.permissionGroups(state.catalog, state.working));
            syncBulkControls();
            renderImpact(state.preview);
            renderer.renderAudit(viewModel.audit(auditRows));
            syncDirtyState();
        }

        function allCapabilityKeys() {
            return viewModel.capabilityKeys(state.catalog, state.working);
        }

        function groupCapabilityKeys(groupKey) {
            return viewModel.groupCapabilityKeys(state.catalog, state.working, groupKey);
        }

        function cancelPreviewTimer() {
            lifecycle.track(() => {}, "permissions-preview-timer");
        }

        function queuePreview() {
            syncDirtyState();
            lifecycle.timeout(() => {
                loadPreview().then(() => {
                    if (isActive()) syncDirtyState();
                });
            }, 180, "permissions-preview-timer");
        }

        function onCapabilityChanged(key, enabled) {
            state.working[key] = enabled === true;
            syncBulkControls();
            queuePreview();
        }

        function setCapabilities(keys, enabled) {
            unique(keys).forEach(key => { state.working[key] = enabled === true; });
            renderer.syncCheckboxes(state.working);
            syncBulkControls();
            queuePreview();
        }

        function onGroupToggle(groupKey) {
            const keys = groupCapabilityKeys(groupKey);
            if (!keys.length) return;
            setCapabilities(keys, !keys.every(key => state.working[key] === true));
        }

        function onGlobalToggle() {
            const keys = allCapabilityKeys();
            if (!keys.length) return;
            setCapabilities(keys, !keys.every(key => state.working[key] === true));
        }

        function syncBulkControls() {
            renderer.syncBulkControls(viewModel.bulkControls(state.catalog, state.working));
        }

        function loadPreview() {
            if (!isActive() || !state.selectedRole) return Promise.resolve(null);
            const requestedRole = state.selectedRole;
            const requestedState = clone(state.working);
            const token = store.requests.preview.begin({ role: requestedRole, state: stable(requestedState) });
            return api.previewRole(requestedRole, requestedState, { freeze: false }).then(data => {
                if (
                    !isActive()
                    || !store.requests.preview.isCurrent(token)
                    || requestedRole !== state.selectedRole
                    || stable(requestedState) !== stable(state.working)
                ) {
                    return null;
                }
                return applyPreview(data || {});
            }).catch(error => {
                if (isActive() && store.requests.preview.isCurrent(token)) {
                    frappe.show_alert({ message: errorMessage(error, __("تعذر حساب أثر الصلاحيات.")), indicator: "red" });
                }
                return null;
            });
        }

        function applyPreview(data) {
            state.preview = data || {};
            state.working = clone(state.preview.capabilities || state.working);
            renderer.syncCheckboxes(state.working);
            syncBulkControls();
            renderImpact(state.preview);
            syncDirtyState();
            return state.preview;
        }

        function previewExternal(request, successMessage) {
            if (!isActive()) return Promise.resolve(null);
            const requestedRole = state.selectedRole;
            const token = store.requests.transfer.begin({ role: requestedRole });
            return Promise.resolve().then(request).then(data => {
                if (!isActive() || !store.requests.transfer.isCurrent(token) || requestedRole !== state.selectedRole) {
                    return null;
                }
                const preview = applyPreview(data || {});
                frappe.show_alert({ message: successMessage, indicator: "green" }, 6);
                return preview;
            }).catch(error => {
                if (isActive() && store.requests.transfer.isCurrent(token)) {
                    showMessage({
                        title: __("تعذر تحميل الصلاحيات"),
                        message: frappe.utils.escape_html(String(errorMessage(error, __("حدث خطأ غير متوقع.")) || "")),
                        indicator: "red",
                    });
                }
                return null;
            });
        }

        function exportSelectedRole() {
            if (!isActive() || !state.selectedRole) return;
            const requestedRole = state.selectedRole;
            const token = store.requests.transfer.begin({ role: requestedRole, operation: "export" });
            api.exportRole(requestedRole, {
                freeze: true,
                freezeMessage: __("جاري تجهيز ملف الصلاحيات..."),
            }).then(documentData => {
                if (
                    !isActive()
                    || !store.requests.transfer.isCurrent(token)
                    || requestedRole !== state.selectedRole
                ) {
                    return;
                }
                const filename = `almdina-permissions-${requestedRole.replace(/[^a-zA-Z0-9_-]+/g, "-")}.json`;
                renderer.downloadJson(filename, documentData || {});
                frappe.show_alert({ message: __("تم تصدير ملف الصلاحيات."), indicator: "green" });
            }).catch(error => {
                if (!isActive() || !store.requests.transfer.isCurrent(token)) return;
                showMessage({
                    title: __("تعذر التصدير"),
                    message: frappe.utils.escape_html(String(errorMessage(error, __("حدث خطأ غير متوقع.")) || "")),
                    indicator: "red",
                });
            });
        }

        function importPermissionFile(file) {
            if (!isActive() || !file || !state.selectedRole) return;
            const generation = activeGeneration();
            const maxBytes = Number(state.transfer.max_bytes || 131072);
            if (file.size > maxBytes) {
                showMessage({ title: __("ملف كبير جدًا"), message: __("حجم ملف الصلاحيات يتجاوز الحد المسموح."), indicator: "red" });
                return;
            }
            const reader = new FileReader();
            reader.onload = () => {
                if (!isCurrentGeneration(generation)) return;
                const payload = String(reader.result || "");
                try {
                    const parsed = JSON.parse(payload);
                    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("not-object");
                } catch (error) {
                    showMessage({ title: __("ملف JSON غير صالح"), message: __("تعذر قراءة الملف ككائن JSON صحيح. لم يتم تغيير أي صلاحية."), indicator: "red" });
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
            reader.onerror = () => {
                if (!isCurrentGeneration(generation)) return;
                showMessage({ title: __("تعذر قراءة الملف"), message: __("لم يتمكن المتصفح من قراءة ملف الصلاحيات."), indicator: "red" });
            };
            reader.readAsText(file, "utf-8");
        }

        function renderImpact(data) {
            const resolved = data || {};
            renderer.renderImpact(viewModel.impact(resolved));
            renderer.syncDirtyState({
                dirty: isDirty(),
                saving: state.saving,
                stats: viewModel.stats(state.catalog, state.working, resolved.changes || []),
            });
        }

        function syncDirtyState() {
            const changes = state.preview && Array.isArray(state.preview.changes) ? state.preview.changes : [];
            renderer.syncDirtyState({
                dirty: isDirty(),
                saving: state.saving,
                stats: viewModel.stats(state.catalog, state.working, changes),
            });
        }

        function resetWorkingState() {
            if (!isActive()) return;
            store.invalidatePending();
            state.working = clone(state.baseline);
            state.preview = { capabilities: clone(state.working), changes: [], impact: (state.preview && state.preview.impact) || {} };
            renderer.syncCheckboxes(state.working);
            syncBulkControls();
            loadPreview();
            syncDirtyState();
        }

        function refreshRuntimePermissions() {
            const permissions = window.AlmdinaPermissions;
            if (!permissions || typeof permissions.refresh !== "function") return Promise.resolve();
            return Promise.resolve()
                .then(() => permissions.refresh())
                .catch(error => console.error("Failed to refresh runtime permissions after save", error));
        }

        function savePermissions() {
            if (!state.selectedRole || !isDirty() || state.saving) return Promise.resolve(false);
            const executeSave = async confirmSelfLockout => {
                const generation = activeGeneration();
                if (generation === null) return false;
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
                    if (!isCurrentGeneration(generation) || requestedRole !== state.selectedRole) {
                        reconcileAfterSave = true;
                        await refreshRuntimePermissions();
                        return true;
                    }
                    const resolved = data || {};
                    state.baseline = clone(resolved.capabilities || requestedState);
                    state.working = clone(state.baseline);
                    state.preview = { capabilities: clone(state.working), changes: [], impact: resolved.impact || {} };
                    renderPermissionState(resolved.audit || []);
                    await refreshRuntimePermissions();
                    if (isCurrentGeneration(generation)) {
                        frappe.show_alert({ message: __("تم حفظ صلاحيات الدور."), indicator: "green" });
                    }
                    return true;
                } catch (error) {
                    if (isCurrentGeneration(generation)) {
                        frappe.show_alert({ message: errorMessage(error, __("تعذر حفظ الصلاحيات.")), indicator: "red" }, 7);
                    }
                    return false;
                } finally {
                    state.saving = false;
                    if (reconcileAfterSave && isActive()) {
                        await loadConsole({ reconcile: true });
                    } else if (isActive()) {
                        syncDirtyState();
                    }
                }
            };

            const generation = activeGeneration();
            if (generation === null) return Promise.resolve(false);
            return Promise.resolve(loadPreview()).then(preview => {
                if (!isCurrentGeneration(generation) || !preview || !isDirty()) return false;
                if (preview.requires_self_lockout_confirmation) {
                    confirmForGeneration(
                        __("سيؤدي هذا الحفظ إلى إزالة آخر صلاحية لديك لإدارة الصلاحيات. هل تريد المتابعة؟"),
                        generation,
                        () => executeSave(true)
                    );
                    return false;
                }
                return executeSave(false);
            });
        }

        function showEmpty(message) {
            ensureFeatureShell();
            renderer.showEmpty(message);
        }

        function showError(error, fallback) {
            const message = errorMessage(error, fallback);
            showEmpty(message);
            frappe.show_alert({ message, indicator: "red" }, 7);
        }
    }

    window.AlmdinaFactoryPermissionsController = Object.freeze({ mount });
})();
