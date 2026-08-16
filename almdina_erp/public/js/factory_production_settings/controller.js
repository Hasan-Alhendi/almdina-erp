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
        const api = window.AlmdinaFactoryProductionSettingsApi;
        const stateModule = window.AlmdinaFactoryProductionSettingsState;
        const viewModelModule = window.AlmdinaFactoryProductionSettingsViewModel;
        const rendererModule = window.AlmdinaFactoryProductionSettingsRenderer;
        const interactionsModule = window.AlmdinaFactoryProductionSettingsInteractions;
        const dialogsModule = window.AlmdinaFactoryProductionSettingsDialogs;
        if (
            !frontend
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
        const page = frappe.ui.make_app_page({
            parent: wrapper,
            title: __("إعدادات المعمل"),
            single_column: true,
        });
        const $body = $(wrapper).find(".layout-main-section");
        const escapeHtml = value => frappe.utils.escape_html(String(value ?? ""));
        const viewModel = viewModelModule.create({ translate: __ });
        const renderer = rendererModule.create({ $body, escapeHtml, translate: __ });
        const dialogs = dialogsModule.create({ translate: __, escapeHtml });

        page.add_inner_button(__("سجل التغييرات"), openAudit, null, "history");
        page.add_inner_button(__("تحديث"), load, null, "refresh");
        interactionsModule.bind({
            $body,
            lifecycle: store.lifecycle,
            callbacks: { onEditSection: openSectionDialog },
        });
        if (window.AlmdinaPageRevisit) {
            window.AlmdinaPageRevisit.refreshOnRevisit(wrapper, load);
        }

        renderer.renderLoading();
        load();

        const instance = Object.freeze({
            load,
            dispose() {
                store.dispose();
                if (wrapper.__almdinaProductionSettingsController === instance) {
                    wrapper.__almdinaProductionSettingsController = null;
                }
            },
        });
        wrapper.__almdinaProductionSettingsController = instance;
        return instance;

        function errorMessage(error, fallback) {
            return frontend.errorMessage(error, fallback);
        }

        function freezeOptions(message) {
            return { freeze: true, freezeMessage: message };
        }

        function render() {
            renderer.render(viewModel.page(state.current));
        }

        function load() {
            const token = store.requests.settings.begin();
            renderer.renderLoading();
            return api.getSettings({ freeze: false }).then(data => {
                if (!store.requests.settings.isCurrent(token)) return null;
                store.apply(data || {});
                render();
                return data;
            }).catch(error => {
                if (!store.requests.settings.isCurrent(token)) return null;
                renderer.renderError(errorMessage(error, __("تعذر تحميل إعدادات المعمل.")));
                return null;
            });
        }

        function openSectionDialog(section) {
            if (!viewModel.sectionEditable(state.current, section)) return;
            dialogs.openSection({
                section,
                current: state.current,
                onSubmit: payload => api.updateSettings(
                    payload,
                    freezeOptions(__("جاري حفظ الإعدادات..."))
                ).then(data => {
                    store.apply(data || {});
                    render();
                    dialogs.showSaved();
                    return data;
                }),
            });
        }

        function openAudit() {
            const token = store.requests.audit.begin();
            const surface = dialogs.openAudit(renderer.auditLoadingHtml());
            return api.getAudit({ freeze: false }).then(rows => {
                if (!store.requests.audit.isCurrent(token)) return;
                surface.setHtml(renderer.auditHtml(rows));
            }).catch(error => {
                if (!store.requests.audit.isCurrent(token)) return;
                surface.setHtml(renderer.auditErrorHtml(
                    errorMessage(error, __("تعذر تحميل السجل."))
                ));
            });
        }
    }

    window.AlmdinaFactoryProductionSettingsController = Object.freeze({ mount });
})();
