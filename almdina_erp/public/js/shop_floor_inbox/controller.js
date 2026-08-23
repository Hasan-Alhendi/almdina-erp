(() => {
    "use strict";

    const Api = window.AlmdinaShopFloorInboxApi;
    const State = window.AlmdinaShopFloorInboxState;
    const ViewModel = window.AlmdinaShopFloorInboxViewModel;
    const Renderer = window.AlmdinaShopFloorInboxRenderer;
    const Interactions = window.AlmdinaShopFloorInboxInteractions;
    const Dialogs = window.AlmdinaShopFloorInboxDialogs;

    function errorMessage(error, fallback) {
        const Frontend = window.AlmdinaFrontend;
        return Frontend && typeof Frontend.errorMessage === "function"
            ? Frontend.errorMessage(error, fallback)
            : (error && error.message ? error.message : fallback);
    }

    function mount(wrapper) {
        if (wrapper.__almdinaShopFloorInboxDispose) wrapper.__almdinaShopFloorInboxDispose();

        const pageLifecycleModule = window.AlmdinaPageRevisit;
        if (!pageLifecycleModule || typeof pageLifecycleModule.bindActivationLifecycle !== "function") {
            throw new Error("Almdina page lifecycle is required before Shop Floor Inbox");
        }

        const state = State.create();
        const shell = Renderer.createShell(wrapper);
        let disposed = false;
        let activation = null;
        const actionDialogs = new Set();

        function active() {
            return Boolean(!disposed && !state.lifecycle.isDisposed() && activation && activation.isActive());
        }

        function trackActionDialog(dialog) {
            if (dialog && typeof dialog.hide === "function") actionDialogs.add(dialog);
            return dialog;
        }

        async function loadSessionContext() {
            const cached = state.context();
            if (cached) return cached;
            const token = state.beginContextRequest();
            const context = await Api.getSessionContext();
            if (!active() || !state.isCurrentContextRequest(token)) return null;
            return state.setContext(context || {});
        }

        function renderCurrent() {
            if (!active()) return;
            const snapshot = state.snapshot();
            Renderer.syncTabs(shell, snapshot.mode);
            if (snapshot.mode === "account") {
                Renderer.renderAccount(shell, ViewModel.account(snapshot.sessionContext || {}));
                return;
            }
            if (snapshot.mode === "board") {
                const model = ViewModel.board(snapshot);
                if (model.routeFilter !== snapshot.routeFilter) state.setRouteFilter(model.routeFilter);
                Renderer.renderBoard(shell, model, snapshot.search, snapshot.mode);
                return;
            }
            Renderer.renderList(shell, ViewModel.list(snapshot), snapshot.mode);
        }

        async function renderAccount() {
            if (!active()) return null;
            Renderer.syncTabs(shell, "account");
            Renderer.loading(shell, __("جاري تحميل معلومات الحساب..."));
            try {
                const context = await loadSessionContext();
                if (!active() || state.mode() !== "account" || !context) return;
                Renderer.renderAccount(shell, ViewModel.account(context));
            } catch (error) {
                if (active() && state.mode() === "account") {
                    Renderer.error(shell, errorMessage(error, __("تعذر تحميل معلومات الحساب.")));
                }
            }
        }

        async function loadList() {
            if (!active()) return null;
            const requestedMode = state.mode();
            if (requestedMode === "account") return renderAccount();
            const token = state.beginListRequest({ mode: requestedMode });
            Renderer.loading(shell, __("جاري التحميل..."));
            try {
                const context = await loadSessionContext();
                if (!context || !state.isCurrentListRequest(token) || state.mode() !== requestedMode) return;
                const [rows, archiveRows] = await Promise.all([Api.getInbox(), Api.getArchive()]);
                if (!active() || !state.isCurrentListRequest(token) || state.mode() !== requestedMode) return;
                state.setRows(rows || [], archiveRows || []);
                renderCurrent();
            } catch (error) {
                if (active() && state.isCurrentListRequest(token)) {
                    Renderer.error(shell, errorMessage(error, __("تعذر تحميل طلبات الإنتاج.")));
                }
            }
        }

        function setMode(nextMode) {
            state.setMode(nextMode);
            Renderer.syncTabs(shell, state.mode());
            if (state.mode() === "account") renderAccount();
            else loadList();
        }

        function setRouteFilter(value) {
            state.setRouteFilter(value);
            if (state.mode() === "board") renderCurrent();
        }

        function setSearch(value) {
            state.setSearch(value);
            if (state.mode() !== "board") return;
            renderCurrent();
            Renderer.focusSearch(shell);
        }

        function openOrder(context) {
            if (context.order) frappe.set_route("Form", "Door Cutting Order", context.order);
        }

        function quickAction(context, button) {
            const quickActions = window.AlmdinaShopFloorQuickActions;
            if (!quickActions || typeof quickActions.perform !== "function") return;
            quickActions.perform(context, {
                button,
                onSuccess: loadList,
                isActive: active,
                onDialog: trackActionDialog,
            });
        }

        function deactivate() {
            state.deactivate();
            actionDialogs.forEach(dialog => {
                if (dialog && typeof dialog.hide === "function") dialog.hide();
            });
            actionDialogs.clear();
        }

        function finishHandoff(context, nextAssignee = "") {
            if (!active()) return;
            Api.handoffStage(context.stage, nextAssignee)
                .then(() => {
                    if (!active()) return;
                    Dialogs.success(context.next ? __("تم إرسال الطلب للقسم التالي.") : __("الطلب جاهز للتسليم."));
                    loadList();
                })
                .catch(error => {
                    if (active()) trackActionDialog(Dialogs.error(errorMessage(error, __("تعذر نقل الطلب."))));
                });
        }

        function handoff(context) {
            if (!active() || !context || !context.stage) return;
            if (!context.next) {
                trackActionDialog(Dialogs.confirmTerminal(() => finishHandoff(context)));
                return;
            }
            Api.getHandoffContext(context.stage)
                .then(handoffContext => {
                    if (!active()) return;
                    const handoff = handoffContext || {};
                    const workers = Array.isArray(handoff.workers) ? handoff.workers : [];
                    if (!workers.length) {
                        trackActionDialog(Dialogs.noWorkers(handoff));
                        return;
                    }
                    trackActionDialog(Dialogs.promptWorker(handoff, nextAssignee => finishHandoff(context, nextAssignee)));
                })
                .catch(error => {
                    if (active()) trackActionDialog(Dialogs.error(errorMessage(error, __("تعذر تحميل عمال القسم التالي."))));
                });
        }

        function logout() {
            trackActionDialog(Dialogs.confirmLogout(() => {
                if (!active()) return;
                Api.logout(__("جاري تسجيل الخروج..."))
                    .catch(() => null)
                    .finally(() => { window.location.href = "/login"; });
            }));
        }

        function refresh() {
            if (!active()) return Promise.resolve();
            return state.mode() === "account" ? renderAccount() : loadList();
        }

        Interactions.bind(shell, state.lifecycle, {
            setMode,
            refresh,
            logout,
            openOrder,
            quickAction,
            setRouteFilter,
            setSearch,
            handoff,
        });
        Renderer.syncTabs(shell, state.mode());

        wrapper.__almdinaShopFloorInboxRefresh = refresh;
        wrapper.__almdinaShopFloorInboxDispose = () => {
            if (disposed) return;
            disposed = true;
            deactivate();
            state.dispose();
            if (activation) activation.dispose();
            delete wrapper.__almdinaShopFloorInboxRefresh;
            delete wrapper.__almdinaShopFloorInboxDispose;
        };

        activation = pageLifecycleModule.bindActivationLifecycle(wrapper, {
            onActivate: refresh,
            onDeactivate: deactivate,
        });
        if (!activation) {
            wrapper.__almdinaShopFloorInboxDispose();
            throw new Error("Shop Floor Inbox activation lifecycle is unavailable");
        }
        state.lifecycle.track(() => activation.dispose(), "shop-floor-page-activation");
        if (activation.isActive()) refresh();

        return Object.freeze({ refresh, dispose: wrapper.__almdinaShopFloorInboxDispose });
    }
    window.AlmdinaShopFloorInboxController = Object.freeze({ mount });
})();
