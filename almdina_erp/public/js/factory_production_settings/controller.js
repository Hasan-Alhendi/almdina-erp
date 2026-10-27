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
        const viewModel = viewModelModule.create({ translate });
        const renderer = rendererModule.create({ $body, escapeHtml, translate });
        const dialogs = dialogsModule.create({ translate, escapeHtml });
        let activation = null;
        let initialLoadPending = true;
        let whatsapp = null;
        let backups = null;
        let customerBot = null;

        if (typeof page.clear_inner_toolbar === "function") page.clear_inner_toolbar();
        page.add_inner_button(translate("Change log"), openAudit, null, "history");
        page.add_inner_button(translate("Refresh"), load, null, "refresh");
        interactionsModule.bind({
            $body,
            lifecycle: store.lifecycle,
            callbacks: {
                onEditSection: openSectionDialog,
                onCreateWhatsApp: () => whatsapp && whatsapp.create(),
                onReconnectWhatsApp: () => whatsapp && whatsapp.reconnect(),
            },
        });

        const instance = Object.freeze({
            load,
            dispose() {
                if (whatsapp && typeof whatsapp.dispose === "function") whatsapp.dispose();
                if (backups && typeof backups.dispose === "function") backups.dispose();
                if (customerBot && typeof customerBot.dispose === "function") customerBot.dispose();
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
                if (whatsapp && typeof whatsapp.deactivate === "function") whatsapp.deactivate();
                if (backups && typeof backups.deactivate === "function") backups.deactivate();
                if (customerBot && typeof customerBot.deactivate === "function") customerBot.deactivate();
                dialogs.deactivate();
                store.deactivate();
            },
        });
        if (!activation) {
            instance.dispose();
            throw new Error("Production Settings page lifecycle is unavailable");
        }
        const whatsappModule = window.AlmdinaFactoryProductionSettingsWhatsApp;
        if (whatsappModule && typeof whatsappModule.attach === "function") {
            whatsapp = whatsappModule.attach({
                api,
                renderer,
                dialogs,
                frontend,
                lifecycle: store.lifecycle,
                translate,
                isActive: () => Boolean(activation && activation.isActive()),
            });
        }
        const backupModule = window.AlmdinaFactoryProductionSettingsBackups;
        if (backupModule && typeof backupModule.attach === "function") {
            backups = backupModule.attach({
                api,
                renderer,
                dialogs,
                frontend,
                lifecycle: store.lifecycle,
                translate,
                $body,
                isActive: () => Boolean(activation && activation.isActive()),
            });
        }
        const customerBotModule = window.AlmdinaFactoryProductionSettingsCustomerBot;
        if (customerBotModule && typeof customerBotModule.attach === "function") {
            customerBot = customerBotModule.attach({
                api, renderer, frontend, dialogs, lifecycle: store.lifecycle, translate, $body,
                isActive: () => Boolean(activation && activation.isActive()),
                permissions: () => ({
                    canOperate: viewModel.canManageCustomerBotOperation(state.current),
                    canEditTexts: viewModel.canManageCustomerBotSettings(state.current),
                }),
            });
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
            // Full-page render replaces panel placeholders, so each visible
            // panel loads its own snapshot again.
            if (viewModel.canManageWhatsAppSession(state.current) && whatsapp) whatsapp.refresh();
            if (viewModel.page(state.current).showBackupPanel && backups) backups.refresh();
            if (viewModel.showCustomerBot(state.current) && customerBot) customerBot.refresh();
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
                renderer.renderError(errorMessage(error, translate("Could not load factory settings.")));
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
                    freezeOptions(translate("Saving settings..."))
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
                    errorMessage(error, translate("Could not load the log."))
                ));
            });
        }
    }

    window.AlmdinaFactoryProductionSettingsController = Object.freeze({ mount });
})();
