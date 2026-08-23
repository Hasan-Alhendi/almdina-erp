(() => {
    "use strict";

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
        if (
            !frontend
            || typeof frontend.createDialogOwner !== "function"
            || !pageLifecycleModule
            || typeof pageLifecycleModule.bindActivationLifecycle !== "function"
            || !api
            || !stateModule
            || !viewModelModule
            || !rendererModule
            || !interactionsModule
            || !dialogsModule
        ) {
            throw new Error("Factory workforce frontend modules are unavailable");
        }

        const store = stateModule.create();
        const state = store.data;
        const viewModel = viewModelModule.create({ translate: __ });
        const page = wrapper.page;
        if (!page) throw new Error("Factory workforce page shell is unavailable");
        const $main = $(wrapper).find(".layout-main-section");
        const renderer = rendererModule.create({
            $main,
            escapeHtml: value => frappe.utils.escape_html(String(value ?? "")),
            translate: __,
        });
        const dialogs = dialogsModule.create({ translate: __ });
        const modalOwner = frontend.createDialogOwner();
        let activation = null;
        let initialLoadPending = true;

        if (typeof page.clear_inner_toolbar === "function") page.clear_inner_toolbar();
        page.set_primary_action(__("إنشاء مستخدم جديد"), openCreateDialog, "add");
        page.add_inner_button(__("تحديث"), load, null, "refresh");

        interactionsModule.bind({
            $main,
            lifecycle: store.lifecycle,
            callbacks: {
                onSearch: value => {
                    state.search = value;
                    load();
                },
                onEnabledChanged: value => {
                    state.enabled = value;
                    load();
                },
                onRefresh: load,
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
                store.deactivate();
                modalOwner.closeAll();
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

        function can(capability) {
            return viewModel.can(state, capability);
        }

        function actionAllowed(user, action) {
            return viewModel.actionAllowed(user, action);
        }

        function syncPrimaryAction() {
            if (page.btn_primary) page.btn_primary.toggle(can("create_users"));
        }

        function render() {
            renderer.render(viewModel.page(state));
        }

        function load() {
            if (!activation || !activation.isActive()) return Promise.resolve(null);
            const isInitialLoad = initialLoadPending;
            initialLoadPending = false;
            const token = store.requests.console.begin({
                search: state.search,
                enabled: state.enabled,
            });
            if (!isInitialLoad && !store.hasRows()) renderer.renderLoading();
            return api.getConsole(state.search, state.enabled, { freeze: false }).then(data => {
                if (!activation.isActive() || !store.requests.console.isCurrent(token)) return null;
                store.applyConsole(data || {});
                syncPrimaryAction();
                render();
                return data;
            }).catch(error => {
                if (!activation.isActive() || !store.requests.console.isCurrent(token)) return null;
                renderer.renderError(errorMessage(error, __("تعذر تحميل البيانات.")));
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
                message: __("لا يمكن إسناد أدوار تحتوي صفحات دخول مختلفة. عدّل Home Page في Role داخل Frappe أو اتركها فارغة في الأدوار الثانوية.")
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
            if (!activation.isActive() || !can("create_users")) return;
            modalOwner.track(dialogs.openCreate({
                canAssignRoles: can("assign_user_roles"),
                roleOptions,
                validateRoles,
                onSubmit: payload => activation.isActive() ? api.createUser(
                    payload,
                    freezeOptions(__("جاري إنشاء المستخدم..."))
                ).then(() => {
                    if (activation.isActive()) dialogs.showAlert(__("تم إنشاء المستخدم."));
                    return load();
                }) : null,
            }));
        }

        function openEditDialog(email) {
            if (!activation.isActive()) return;
            const user = userByEmail(email);
            if (!user) return;
            const canEdit = actionAllowed(user, "edit");
            const canAssignRoles = actionAllowed(user, "assign_roles");
            if (!canEdit && !canAssignRoles) return;

            modalOwner.track(dialogs.openEdit({
                user,
                canEdit,
                canAssignRoles,
                roleOptions,
                validateRoles,
                onSubmit: payload => activation.isActive() ? api.updateUser(
                    user.email,
                    payload,
                    freezeOptions(__("جاري حفظ المستخدم..."))
                ).then(() => {
                    if (activation.isActive()) dialogs.showAlert(__("تم تحديث المستخدم."));
                    return load();
                }) : null,
            }));
        }

        function openPasswordDialog(email) {
            if (!activation.isActive()) return;
            const user = userByEmail(email);
            if (!user || !actionAllowed(user, "reset_password")) return;
            modalOwner.track(dialogs.openPassword({
                user,
                onSubmit: temporaryPassword => activation.isActive() ? api.resetPassword(
                    user.email,
                    temporaryPassword,
                    freezeOptions(__("جاري تحديث كلمة المرور..."))
                ).then(() => {
                    if (activation.isActive()) dialogs.showAlert(__("تم تحديث كلمة المرور دون تسجيل قيمتها."));
                }) : null,
            }));
        }

        function toggleUser(email, enabled) {
            if (!activation.isActive()) return;
            const user = userByEmail(email);
            const action = enabled ? "enable" : "disable";
            if (!user || !actionAllowed(user, action)) return;
            modalOwner.track(dialogs.confirmToggle({
                user,
                enabled,
                onConfirm: () => activation.isActive() ? api.setEnabled(
                    user.email,
                    enabled,
                    freezeOptions(__("جاري تحديث الحساب..."))
                ).then(() => {
                    if (activation.isActive()) dialogs.showAlert(__("تم تحديث حالة المستخدم."));
                    return load();
                }) : null,
            }));
        }

        function adoptUser(email) {
            if (!activation.isActive()) return;
            const user = availableUserByEmail(email);
            if (!user || !can("create_users")) return;
            modalOwner.track(dialogs.confirmAdopt({
                user,
                onConfirm: () => activation.isActive() ? api.adoptUser(
                    user.email,
                    freezeOptions(__("جاري إضافة المستخدم إلى المعمل..."))
                ).then(() => {
                    if (activation.isActive()) dialogs.showAlert(__("تمت إضافة المستخدم إلى المعمل. يمكنك الآن تعيين أدواره."));
                    return load();
                }) : null,
            }));
        }

        function openAudit(email) {
            if (!activation.isActive()) return;
            const user = userByEmail(email);
            if (!user) return;
            const token = store.requests.audit.begin({ user: email });
            return api.getAudit(
                user.email,
                freezeOptions(__("جاري تحميل السجل..."))
            ).then(data => {
                if (!activation.isActive() || !store.requests.audit.isCurrent(token)) return;
                const events = Array.isArray(data.events) ? data.events : [];
                modalOwner.track(dialogs.openAudit({ user, html: renderer.auditHtml(events) }));
            });
        }
    }

    window.AlmdinaFactoryWorkforceController = Object.freeze({ mount });
})();
