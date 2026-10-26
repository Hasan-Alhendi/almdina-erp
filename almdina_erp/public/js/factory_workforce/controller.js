(() => {
    "use strict";

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split("{" + index + "}").join(String(value));
            });
        }
        return text;
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const dir = root && root.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }


    if (window.AlmdinaFactoryWorkforceController) return;

    function mount(wrapper) {
        if (!wrapper) throw new Error("Factory workforce wrapper is required");
        if (
            wrapper.__almdinaFactoryWorkforceController
            && typeof wrapper.__almdinaFactoryWorkforceController.dispose === "function"
        ) {
            wrapper.__almdinaFactoryWorkforceController.dispose();
        }

        const frontend = window.AlmdinaFrontend;
        const pageLifecycleModule = window.AlmdinaPageRevisit;
        const api = window.AlmdinaFactoryWorkforceApi;
        const stateModule = window.AlmdinaFactoryWorkforceState;
        const viewModelModule = window.AlmdinaFactoryWorkforceViewModel;
        const rendererModule = window.AlmdinaFactoryWorkforceRenderer;
        const interactionsModule = window.AlmdinaFactoryWorkforceInteractions;
        const dialogsModule = window.AlmdinaFactoryWorkforceDialogs;
        const toolbarModule = window.AlmdinaFactoryWorkforceToolbar;
        if (
            !frontend
            || !pageLifecycleModule
            || typeof pageLifecycleModule.bindActivationLifecycle !== "function"
            || !api
            || !stateModule
            || !viewModelModule
            || !rendererModule
            || !interactionsModule
            || !dialogsModule
            || !toolbarModule
        ) {
            throw new Error("Factory workforce frontend modules are unavailable");
        }

        const store = stateModule.create();
        const state = store.data;
        const viewModel = viewModelModule.create({ translate });
        const page = wrapper.page;
        if (!page) throw new Error("Factory workforce page shell is unavailable");
        const $main = $(wrapper).find(".layout-main-section");
        const renderer = rendererModule.create({
            $main,
            escapeHtml: value => frappe.utils.escape_html(String(value ?? "")),
            translate,
        });
        const dialogs = dialogsModule.create({ translate });
        const toolbar = toolbarModule.create({
            $main,
            state,
            lifecycle: store.lifecycle,
            load,
            translate,
        });
        let activation = null;
        let initialLoadPending = true;
        if (typeof page.clear_inner_toolbar === "function") page.clear_inner_toolbar();
        page.set_primary_action(translate("Create new user"), openCreateDialog, "add");
        syncPrimaryAction();
        page.add_inner_button(translate("Refresh"), load, null, "refresh");
        interactionsModule.bind({
            $main,
            lifecycle: store.lifecycle,
            callbacks: {
                onEdit: openEditDialog,
                onPassword: openPasswordDialog,
                onToggle: toggleUser,
                onAudit: openAudit,
                onAdopt: adoptUser,
            },
        });
        const instance = Object.freeze({
            load,
            dispose() {
                toolbar.dispose();
                dialogs.dispose();
                store.dispose();
                if (wrapper.__almdinaFactoryWorkforceController === instance) {
                    wrapper.__almdinaFactoryWorkforceController = null;
                }
            },
        });
        wrapper.__almdinaFactoryWorkforceController = instance;
        activation = pageLifecycleModule.bindActivationLifecycle(wrapper, {
            onActivate: load,
            onDeactivate: () => {
                toolbar.dispose();
                dialogs.deactivate();
                store.deactivate();
            },
        });
        if (!activation) {
            instance.dispose();
            throw new Error("Factory workforce page lifecycle is unavailable");
        }
        store.lifecycle.track(() => activation.dispose(), "workforce-page-activation");
        if (activation.isActive()) load();
        return instance;
        function errorMessage(error, fallback) {
            return frontend.errorMessage(error, fallback);
        }
        function freezeOptions(message) {
            return { freeze: true, freezeMessage: message };
        }
        function activeGeneration() {
            return activation && activation.isActive() ? activation.generation() : null;
        }
        function isCurrentGeneration(generation) {
            return generation !== null
                && activation.isActive()
                && activation.generation() === generation;
        }
        function runMutation(generation, request, successMessage, refresh = true, preserveDraft = false) {
            if (!isCurrentGeneration(generation)) return Promise.resolve(null);
            return Promise.resolve().then(request).then(data => {
                if (!isCurrentGeneration(generation)) {
                    if (refresh && activation.isActive()) return load().then(() => data);
                    return data;
                }
                dialogs.showAlert(successMessage);
                if (!refresh) return data;
                return load().then(() => data);
            }).catch(error => {
                if (!isCurrentGeneration(generation) && !preserveDraft) return null;
                throw error;
            });
        }
        function can(capability) {
            return viewModel.can(state, capability);
        }
        function actionAllowed(user, action) {
            return viewModel.actionAllowed(user, action);
        }
        function syncPrimaryAction() {
            if (page.btn_primary) page.btn_primary.toggle(can("create_users"));
        }
        function render(options = {}) {
            renderer.render(viewModel.page(state), options);
            if (options.preserveToolbar !== true) {
                toolbar.mount();
            }
        }
        function load() {
            if (!activation || !activation.isActive()) return Promise.resolve(null);
            state.permissions = {};
            syncPrimaryAction();
            const isInitialLoad = initialLoadPending;
            initialLoadPending = false;
            const token = store.requests.console.begin({
                search: state.search,
                enabled: state.enabled,
            });
            if (!isInitialLoad && !store.hasRows()) {
                toolbar.dispose();
                renderer.renderLoading();
            }
            return api.getConsole(state.search, state.enabled, { freeze: false }).then(data => {
                if (!activation.isActive() || !store.requests.console.isCurrent(token)) return null;
                store.applyConsole(data || {});
                syncPrimaryAction();
                render({ preserveToolbar: toolbar.isMounted() });
                return data;
            }).catch(error => {
                if (!activation.isActive() || !store.requests.console.isCurrent(token)) return null;
                toolbar.dispose();
                renderer.renderError(errorMessage(error, translate("Could not load data.")));
                return null;
            });
        }
        function roleOptions(query) {
            return viewModel.roleOptions(state.roles, query);
        }
        function validateRoles(selectedRoles) {
            const policy = viewModel.roleHomePolicy(state.roles, selectedRoles);
            if (!policy.hasConflict) return { ok: true };
            const details = policy.configured
                .map(item => `${item.role} ← ${item.homePage}`)
                .join("<br>");
            return {
                ok: false,
                message: translate("Roles with different login pages cannot be assigned. Edit the Home Page on the Role in Frappe or leave it empty on secondary roles.")
                    + `<div class="mt-2 text-muted">${details}</div>`,
            };
        }
        function userByEmail(email) {
            return viewModel.findUser(state.users, email);
        }
        function availableUserByEmail(email) {
            return viewModel.findUser(state.availableUsers, email);
        }
        function openCreateDialog() {
            if (!can("create_users")) return;
            const generation = activeGeneration();
            if (generation === null) return;
            dialogs.openCreate({
                canAssignRoles: can("assign_user_roles"),
                languages: state.languages,
                roleOptions,
                validateRoles,
                onSubmit: payload => runMutation(
                    generation,
                    () => api.createUser(payload, freezeOptions(translate("Creating user..."))),
                    translate("User created."),
                    true,
                    true
                ),
            });
        }
        function openEditDialog(email) {
            const user = userByEmail(email);
            if (!user) return;
            const canEdit = actionAllowed(user, "edit");
            const canAssignRoles = actionAllowed(user, "assign_roles");
            if (!canEdit && !canAssignRoles) return;
            const generation = activeGeneration();
            if (generation === null) return;

            dialogs.openEdit({
                user,
                canEdit,
                canAssignRoles,
                languages: state.languages,
                roleOptions,
                validateRoles,
                onSubmit: payload => runMutation(
                    generation,
                    () => api.updateUser(user.email, payload, freezeOptions(translate("Saving user..."))),
                    translate("User updated."),
                    true,
                    true
                ),
            });
        }
        function openPasswordDialog(email) {
            const user = userByEmail(email);
            if (!user || !actionAllowed(user, "reset_password")) return;
            const generation = activeGeneration();
            if (generation === null) return;
            dialogs.openPassword({
                user,
                onSubmit: temporaryPassword => runMutation(
                    generation,
                    () => api.resetPassword(user.email, temporaryPassword, freezeOptions(translate("Updating password..."))),
                    translate("Password updated without logging its value."),
                    false,
                    true
                ),
            });
        }
        function toggleUser(email, enabled) {
            const user = userByEmail(email);
            const action = enabled ? "enable" : "disable";
            if (!user || !actionAllowed(user, action)) return;
            const generation = activeGeneration();
            if (generation === null) return;
            dialogs.confirmToggle({
                user,
                enabled,
                onConfirm: () => runMutation(
                    generation,
                    () => api.setEnabled(user.email, enabled, freezeOptions(translate("Updating the account..."))),
                    translate("User status updated.")
                ),
            });
        }
        function adoptUser(email) {
            const user = availableUserByEmail(email);
            if (!user || !can("create_users")) return;
            const generation = activeGeneration();
            if (generation === null) return;
            dialogs.confirmAdopt({
                user,
                onConfirm: () => runMutation(
                    generation,
                    () => api.adoptUser(user.email, freezeOptions(translate("Adding user to the factory..."))),
                    translate("User added to the factory. You can now assign their roles.")
                ),
            });
        }
        function openAudit(email) {
            const user = userByEmail(email);
            if (!user) return;
            const generation = activeGeneration();
            if (generation === null) return;
            const token = store.requests.audit.begin({ user: email });
            return api.getAudit(
                user.email,
                freezeOptions(translate("Loading the log..."))
            ).then(data => {
                if (!isCurrentGeneration(generation) || !store.requests.audit.isCurrent(token)) return;
                const events = Array.isArray(data.events) ? data.events : [];
                dialogs.openAudit({ user, html: renderer.auditHtml(events) });
            });
        }
    }

    window.AlmdinaFactoryWorkforceController = Object.freeze({ mount });
})();
