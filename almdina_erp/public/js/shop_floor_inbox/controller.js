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

    function mount(wrapper, options = {}) {
        if (!wrapper) throw new Error("Shop Floor Inbox wrapper is required");
        const previous = wrapper.__almdinaShopFloorInboxController;
        if (previous && typeof previous.dispose === "function") previous.dispose();

        const pageLifecycle = window.AlmdinaPageRevisit;
        if (!pageLifecycle || typeof pageLifecycle.bindActivationLifecycle !== "function") {
            throw new Error("Shop Floor Inbox page lifecycle is unavailable");
        }
        if (!Api || !State || !ViewModel || !Renderer || !Interactions || !Dialogs) {
            throw new Error("Shop Floor Inbox frontend modules are unavailable");
        }

        const state = State.create();
        const page = options.page || wrapper.page;
        const shell = Renderer.createShell(wrapper, page);
        let activation = null;
        let disposed = false;
        let reconcileAfterMutation = false;
        let logoutCompleted = false;
        let initialLoadPending = typeof shell.hasBootstrapLoading === "function"
            && shell.hasBootstrapLoading();
        let interactionOwner = null;
        const dialogs = Dialogs.create({ isCurrentGeneration });

        interactionOwner = Interactions.bind(shell, state.lifecycle, {
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

        const instance = Object.freeze({
            refresh,
            dispose() {
                if (disposed) return false;
                disposed = true;
                dialogs.dispose();
                state.dispose();
                if (wrapper.__almdinaShopFloorInboxController === instance) {
                    wrapper.__almdinaShopFloorInboxController = null;
                }
                return true;
            },
        });
        wrapper.__almdinaShopFloorInboxController = instance;

        activation = pageLifecycle.bindActivationLifecycle(wrapper, {
            onActivate: activatePage,
            onDeactivate: deactivatePage,
        });
        if (!activation) {
            instance.dispose();
            throw new Error("Shop Floor Inbox activation owner is unavailable");
        }
        state.lifecycle.track(() => activation.dispose(), "shop-floor-page-activation");
        if (activation.isActive()) activatePage();
        return instance;

        function isActive() {
            return !disposed && activation && activation.isActive();
        }

        function activeGeneration() {
            return isActive() ? activation.generation() : null;
        }

        function isCurrentGeneration(generation) {
            return generation !== null
                && isActive()
                && activation.generation() === generation;
        }

        function isCurrentVisit(generation, mode) {
            return isCurrentGeneration(generation) && state.mode() === mode;
        }

        function beginLoading(message) {
            const bootstrapOwnsLoading = initialLoadPending;
            initialLoadPending = false;
            if (!bootstrapOwnsLoading) Renderer.loading(shell, message);
        }

        async function loadSessionContext({ fresh = false } = {}) {
            const cached = state.context();
            if (cached && !fresh) return cached;
            const token = state.beginContextRequest();
            const context = await Api.getSessionContext();
            if (!isActive() || !state.isCurrentContextRequest(token)) return null;
            return state.setContext(context || {});
        }

        function renderCurrent() {
            if (!isActive()) return;
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

        async function renderAccount({ freshContext = false } = {}) {
            const requestedMode = "account";
            Renderer.syncTabs(shell, requestedMode);
            beginLoading(__("جاري تحميل معلومات الحساب..."));
            try {
                const context = await loadSessionContext({ fresh: freshContext });
                if (!isActive() || state.mode() !== requestedMode || !context) return null;
                Renderer.renderAccount(shell, ViewModel.account(context));
                return context;
            } catch (error) {
                if (isActive() && state.mode() === requestedMode) {
                    Renderer.error(shell, errorMessage(error, __("تعذر تحميل معلومات الحساب.")));
                }
                return null;
            }
        }

        async function loadList({ freshContext = false } = {}) {
            const requestedMode = state.mode();
            if (requestedMode === "account") return renderAccount({ freshContext });
            const token = state.beginListRequest({ mode: requestedMode });
            beginLoading(__("جاري التحميل..."));
            try {
                const context = await loadSessionContext({ fresh: freshContext });
                if (
                    !context
                    || !isActive()
                    || !state.isCurrentListRequest(token)
                    || state.mode() !== requestedMode
                ) {
                    return null;
                }
                const [rows, archiveRows] = await Promise.all([Api.getInbox(), Api.getArchive()]);
                if (
                    !isActive()
                    || !state.isCurrentListRequest(token)
                    || state.mode() !== requestedMode
                ) {
                    return null;
                }
                state.setRows(rows || [], archiveRows || []);
                renderCurrent();
                return state.snapshot();
            } catch (error) {
                if (isActive() && state.isCurrentListRequest(token) && state.mode() === requestedMode) {
                    Renderer.error(shell, errorMessage(error, __("تعذر تحميل طلبات الإنتاج.")));
                }
                return null;
            }
        }

        function refresh({ freshContext = true } = {}) {
            if (!isActive()) return Promise.resolve(null);
            return state.mode() === "account"
                ? renderAccount({ freshContext })
                : loadList({ freshContext });
        }

        function activatePage() {
            if (logoutCompleted) {
                window.location.href = "/login";
                return Promise.resolve(null);
            }
            if (reconcileAfterMutation) reconcileAfterMutation = false;
            return refresh({ freshContext: true });
        }

        function deactivatePage() {
            dialogs.deactivate();
            if (interactionOwner && typeof interactionOwner.deactivate === "function") {
                interactionOwner.deactivate();
            }
            state.deactivate();
        }

        function scheduleMutationReconciliation() {
            reconcileAfterMutation = true;
            if (!isActive()) return Promise.resolve(null);
            reconcileAfterMutation = false;
            return refresh({ freshContext: true });
        }

        function setMode(nextMode) {
            if (!isActive()) return;
            state.setMode(nextMode);
            Renderer.syncTabs(shell, state.mode());
            if (state.mode() === "account") renderAccount();
            else loadList();
        }

        function setRouteFilter(value) {
            if (!isActive()) return;
            state.setRouteFilter(value);
            if (state.mode() === "board") renderCurrent();
        }

        function setSearch(value) {
            if (!isActive()) return;
            state.setSearch(value);
            if (state.mode() !== "board") return;
            renderCurrent();
            Renderer.focusSearch(shell);
        }

        function openOrder(context) {
            if (isActive() && context.order) {
                frappe.set_route("Form", "Door Cutting Order", context.order);
            }
        }

        function quickAction(context, button) {
            const quickActions = window.AlmdinaShopFloorQuickActions;
            const generation = activeGeneration();
            if (generation === null || !quickActions || typeof quickActions.perform !== "function") return null;
            const requestedMode = state.mode();
            const token = state.beginQuickAction({ mode: requestedMode, stage: context.stage });
            const lifecycle = {
                isCurrent: () => isCurrentVisit(generation, requestedMode)
                    && state.isCurrentQuickAction(token),
                ownTransient: (surface, key) => dialogs.own(
                    surface,
                    `quick-action:${String(key || "child")}`,
                    generation
                ),
                onStaleMutationSuccess: scheduleMutationReconciliation,
            };
            const operation = quickActions.perform(context, {
                button,
                lifecycle,
                onSuccess: () => loadList({ freshContext: false }),
                onError: error => dialogs.error(
                    errorMessage(error, __("تعذر تنفيذ الإجراء.")),
                    generation
                ),
            });
            return Promise.resolve(operation).catch(error => {
                if (lifecycle.isCurrent()) {
                    dialogs.error(errorMessage(error, __("تعذر تنفيذ الإجراء.")), generation);
                }
                return null;
            });
        }

        function finishHandoff(context, generation, nextAssignee = "", isCurrentOperation = null) {
            const current = typeof isCurrentOperation === "function"
                ? isCurrentOperation
                : () => isCurrentGeneration(generation);
            return Api.handoffStage(context.stage, nextAssignee).then(data => {
                if (!current()) {
                    return scheduleMutationReconciliation().then(() => data);
                }
                dialogs.success(
                    context.next ? __("تم إرسال الطلب للقسم التالي.") : __("الطلب جاهز للتسليم."),
                    generation
                );
                return loadList({ freshContext: false }).then(() => data);
            }).catch(error => {
                if (current()) {
                    dialogs.error(errorMessage(error, __("تعذر نقل الطلب.")), generation);
                }
                return null;
            });
        }

        function handoff(context) {
            const generation = activeGeneration();
            if (generation === null || !context || !context.stage) return null;
            const requestedMode = state.mode();
            const token = state.beginHandoffRequest({ mode: requestedMode, stage: context.stage });
            const current = () => isCurrentVisit(generation, requestedMode)
                && state.isCurrentHandoffRequest(token);
            if (!context.next) {
                return dialogs.confirmTerminal(generation, () => {
                    if (current()) finishHandoff(context, generation, "", current);
                });
            }
            return Api.getHandoffContext(context.stage).then(handoffContext => {
                if (!current()) return null;
                const handoffData = handoffContext || {};
                const workers = Array.isArray(handoffData.workers) ? handoffData.workers : [];
                if (!workers.length) return dialogs.noWorkers(handoffData, generation);
                return dialogs.promptWorker(handoffData, generation, nextAssignee => {
                    if (current()) finishHandoff(context, generation, nextAssignee, current);
                });
            }).catch(error => {
                if (current()) {
                    dialogs.error(errorMessage(error, __("تعذر تحميل عمال القسم التالي.")), generation);
                }
                return null;
            });
        }

        function logout() {
            const generation = activeGeneration();
            if (generation === null) return;
            dialogs.confirmLogout(generation, () => {
                Api.logout(__("جاري تسجيل الخروج..."))
                    .catch(() => null)
                    .finally(() => {
                        logoutCompleted = true;
                        if (isCurrentGeneration(generation)) window.location.href = "/login";
                    });
            });
        }
    }

    window.AlmdinaShopFloorInboxController = Object.freeze({ mount });
})();
