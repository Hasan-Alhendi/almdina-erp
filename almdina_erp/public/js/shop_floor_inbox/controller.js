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

        const state = State.create();
        const shell = Renderer.createShell(wrapper);
        let disposed = false;

        function active() {
            return !disposed && !state.lifecycle.isDisposed();
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
            quickActions.perform(context, { button, onSuccess: loadList });
        }

        function finishHandoff(context, nextAssignee = "") {
            Api.handoffStage(context.stage, nextAssignee)
                .then(() => {
                    Dialogs.success(context.next ? __("تم إرسال الطلب للقسم التالي.") : __("الطلب جاهز للتسليم."));
                    loadList();
                })
                .catch(error => Dialogs.error(errorMessage(error, __("تعذر نقل الطلب."))));
        }

        function handoff(context) {
            if (!context || !context.stage) return;
            if (!context.next) {
                Dialogs.confirmTerminal(() => finishHandoff(context));
                return;
            }
            Api.getHandoffContext(context.stage)
                .then(handoffContext => {
                    const handoff = handoffContext || {};
                    const workers = Array.isArray(handoff.workers) ? handoff.workers : [];
                    if (!workers.length) {
                        Dialogs.noWorkers(handoff);
                        return;
                    }
                    Dialogs.promptWorker(handoff, nextAssignee => finishHandoff(context, nextAssignee));
                })
                .catch(error => Dialogs.error(errorMessage(error, __("تعذر تحميل عمال القسم التالي."))));
        }

        function logout() {
            Dialogs.confirmLogout(() => {
                Api.logout(__("جاري تسجيل الخروج..."))
                    .catch(() => null)
                    .finally(() => { window.location.href = "/login"; });
            });
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
            state.dispose();
            delete wrapper.__almdinaShopFloorInboxRefresh;
            delete wrapper.__almdinaShopFloorInboxDispose;
        };

        if (window.AlmdinaPageRevisit) {
            window.AlmdinaPageRevisit.refreshOnRevisit(wrapper, refresh);
        }

        loadSessionContext()
            .then(context => context && active() ? loadList() : null)
            .catch(error => {
                if (active()) Renderer.error(shell, errorMessage(error, __("لا تملك صلاحية الدخول إلى صالة الإنتاج.")));
            });

        return Object.freeze({ refresh, dispose: wrapper.__almdinaShopFloorInboxDispose });
    }

    window.AlmdinaShopFloorInboxController = Object.freeze({ mount });
})();
