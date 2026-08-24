(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsController) return;

    function mount(wrapper) {
        if (!wrapper) throw new Error("Production Settings wrapper is required");
        if (
            wrapper.__almdinaProductionSettingsController
            && typeof wrapper.__almdinaProductionSettingsController.dispose === "function"
        ) {
            wrapper.__almdinaProductionSettingsController.dispose();
        }

        const frontend = window.AlmdinaFrontend;
        const pageLifecycleModule = window.AlmdinaPageRevisit;
        const api = window.AlmdinaFactoryProductionSettingsApi;
        const stateModule = window.AlmdinaFactoryProductionSettingsState;
        const viewModelModule = window.AlmdinaFactoryProductionSettingsViewModel;
        const rendererModule = window.AlmdinaFactoryProductionSettingsRenderer;
        const interactionsModule = window.AlmdinaFactoryProductionSettingsInteractions;
        const dialogsModule = window.AlmdinaFactoryProductionSettingsDialogs;
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
        ) {
            throw new Error("Production Settings frontend modules are unavailable");
        }

        const store = stateModule.create();
        const state = store.data;
        const page = wrapper.page;
        if (!page) throw new Error("Production Settings page shell is unavailable");
        const $body = $(wrapper).find(".layout-main-section");
        const escapeHtml = value => frappe.utils.escape_html(String(value ?? ""));
        const viewModel = viewModelModule.create({ translate: __ });
        const renderer = rendererModule.create({ $body, escapeHtml, translate: __ });
        const dialogs = dialogsModule.create({ translate: __, escapeHtml });
        let activation = null;
        let initialLoadPending = true;

        if (typeof page.clear_inner_toolbar === "function") page.clear_inner_toolbar();
        page.add_inner_button(__("سجل التغييرات"), openAudit, null, "history");
        page.add_inner_button(__("تحديث"), load, null, "refresh");
        interactionsModule.bind({
            $body,
            lifecycle: store.lifecycle,
            callbacks: { onEditSection: openSectionDialog },
        });

        const instance = Object.freeze({
            load,
            dispose() {
                dialogs.dispose();
                store.dispose();
                if (wrapper.__almdinaProductionSettingsController === instance) {
                    wrapper.__almdinaProductionSettingsController = null;
                }
            },
        });
        wrapper.__almdinaProductionSettingsController = instance;
        activation = pageLifecycleModule.bindActivationLifecycle(wrapper, {
            onActivate: load,
            onDeactivate: () => {
                dialogs.deactivate();
                store.deactivate();
            },
        });
        if (!activation) {
            instance.dispose();
            throw new Error("Production Settings page lifecycle is unavailable");
        }
        store.lifecycle.track(() => activation.dispose(), "production-settings-page-activation");
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

        function render() {
            renderer.render(viewModel.page(state.current));
        }

        function load() {
            if (!activation || !activation.isActive()) return Promise.resolve(null);
            const isInitialLoad = initialLoadPending;
            initialLoadPending = false;
            const token = store.requests.settings.begin();
            if (!isInitialLoad) renderer.renderLoading();
            return api.getSettings({ freeze: false }).then(data => {
                if (!activation.isActive() || !store.requests.settings.isCurrent(token)) return null;
                store.apply(data || {});
                render();
                return data;
            }).catch(error => {
                if (!activation.isActive() || !store.requests.settings.isCurrent(token)) return null;
                renderer.renderError(errorMessage(error, __("تعذر تحميل إعدادات المعمل.")));
                return null;
            });
        }

        function openSectionDialog(section) {
            if (!viewModel.sectionEditable(state.current, section)) return;
            const generation = activeGeneration();
            if (generation === null) return;
            dialogs.openSection({
                section,
                current: state.current,
                onSubmit: payload => api.updateSettings(
                    payload,
                    freezeOptions(__("جاري حفظ الإعدادات..."))
                ).then(data => {
                    if (!isCurrentGeneration(generation)) {
                        if (activation.isActive()) return load().then(() => data);
                        return data;
                    }
                    store.apply(data || {});
                    render();
                    dialogs.showSaved();
                    return data;
                }),
            });
        }

        function openAudit() {
            const generation = activeGeneration();
            if (generation === null) return;
            const token = store.requests.audit.begin();
            const surface = dialogs.openAudit(renderer.auditLoadingHtml());
            return api.getAudit({ freeze: false }).then(rows => {
                if (!isCurrentGeneration(generation) || !store.requests.audit.isCurrent(token)) return;
                surface.setHtml(renderer.auditHtml(rows));
            }).catch(error => {
                if (!isCurrentGeneration(generation) || !store.requests.audit.isCurrent(token)) return;
                surface.setHtml(renderer.auditErrorHtml(
                    errorMessage(error, __("تعذر تحميل السجل."))
                ));
            });
        }
    }

    window.AlmdinaFactoryProductionSettingsController = Object.freeze({ mount });
})();
