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

    function canLoadReadyForDelivery(context) {
        return Boolean(
            context
            && context.capabilities
            && context.capabilities.mark_delivered === true
        );
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
        let boardToolbarControls = null;
        let boardToolbarMounted = false;
        let $refreshButton = null;
        state.lifecycle.track(() => disposeBoardToolbarControls(), "shop-floor-board-toolbar-owner");
        const dialogs = Dialogs.create({ isCurrentGeneration });

        if (typeof page.add_inner_button === "function") {
            $refreshButton = page.add_inner_button(__("تحديث"), refresh, null, "refresh");
        }
        syncRefreshButtonVisibility();

        interactionOwner = Interactions.bind(shell, state.lifecycle, {
            setMode,
            refresh,
            logout,
            openOrder,
            quickAction,
            handoff,
        });
        Renderer.syncTabs(shell, state.mode());

        const instance = Object.freeze({
            refresh,
            dispose() {
                if (disposed) return false;
                disposed = true;
                disposeBoardToolbarControls();
                boardToolbarMounted = false;
                if ($refreshButton && typeof $refreshButton.remove === "function") {
                    $refreshButton.remove();
                    $refreshButton = null;
                }
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
            if (!bootstrapOwnsLoading) {
                disposeBoardToolbarControls();
                boardToolbarMounted = false;
                Renderer.loading(shell, message);
            }
        }

        async function loadSessionContext({ fresh = false } = {}) {
            const cached = state.context();
            if (cached && !fresh) return cached;
            const token = state.beginContextRequest();
            const context = await Api.getSessionContext();
            if (!isActive() || !state.isCurrentContextRequest(token)) return null;
            return state.setContext(context || {});
        }

        function renderCurrent(options = {}) {
            if (!isActive()) return;
            const snapshot = state.snapshot();
            Renderer.syncTabs(shell, snapshot.mode);
            if (snapshot.mode === "account") {
                disposeBoardToolbarControls();
                boardToolbarMounted = false;
                Renderer.renderAccount(shell, ViewModel.account(snapshot.sessionContext || {}));
                return;
            }
            if (snapshot.mode === "board") {
                const model = ViewModel.board(snapshot);
                if (model.routeFilter !== snapshot.routeFilter) state.setRouteFilter(model.routeFilter);
                const preserveToolbar = options.preserveBoardToolbar === true && boardToolbarMounted;
                Renderer.renderBoard(shell, model, snapshot.mode, { preserveToolbar });
                if (preserveToolbar) {
                    syncBoardToolbarControlValues(snapshot, model);
                } else {
                    mountBoardToolbarControls(snapshot, model);
                    boardToolbarMounted = true;
                }
                return;
            }
            disposeBoardToolbarControls();
            boardToolbarMounted = false;
            Renderer.renderList(shell, ViewModel.list(snapshot), snapshot.mode);
        }

        function allRoutesLabel() {
            return __("كل المسارات");
        }

        function routeFilterCatalog(routes) {
            const entries = (routes || []).map(route => [
                String(route.name || ""),
                String(route.label || route.name || __("مسار غير محدد")),
            ]);
            const options = [allRoutesLabel(), ...entries.map(([, label]) => label)].join("\n");
            return { entries, options };
        }

        function routeFilterLabel(entries, value) {
            if (!value) return allRoutesLabel();
            const match = entries.find(([name]) => name === value);
            return match ? match[1] : allRoutesLabel();
        }

        function routeFilterValue(entries, label) {
            if (label === allRoutesLabel()) return "";
            const match = entries.find(([, text]) => text === label);
            return match ? match[0] : "";
        }

        function disposeBoardToolbarControls() {
            if (!boardToolbarControls) return;
            boardToolbarControls.route.dispose();
            boardToolbarControls.search.dispose();
            boardToolbarControls = null;
        }

        function mountBoardToolbarControls(snapshot, model) {
            disposeBoardToolbarControls();
            const ui = window.AlmdinaUi;
            if (!ui || typeof ui.control !== "function") {
                throw new Error("AlmdinaUi.control is required for Shop Floor Inbox board toolbar");
            }
            const $routeMount = shell.$content.find(".almdina-sf-route-mount");
            const $searchMount = shell.$content.find(".almdina-sf-search-mount");
            if (!$routeMount.length || !$searchMount.length) return;

            const { entries, options } = routeFilterCatalog(model.routes);
            const route = ui.control({
                parent: $routeMount,
                fieldname: "route_filter",
                fieldtype: "Select",
                options,
                value: routeFilterLabel(entries, model.routeFilter),
                className: "almdina-sf-route-control-mount",
                onlyInput: true,
                onChange: value => {
                    setRouteFilter(routeFilterValue(entries, String(value || "")));
                },
            });
            const search = ui.control({
                parent: $searchMount,
                fieldname: "board_search",
                fieldtype: "Data",
                placeholder: __("رقم الطلب، الزبون، العامل..."),
                value: snapshot.search || "",
                className: "almdina-sf-search-control-mount",
                onlyInput: true,
                onChange: value => {
                    applyBoardSearch(String(value || ""));
                },
            });
            boardToolbarControls = { route, search, entries };
        }

        function syncBoardToolbarControlValues(snapshot, model) {
            if (!boardToolbarControls) return;
            const routeLabel = routeFilterLabel(boardToolbarControls.entries, model.routeFilter);
            if (boardToolbarControls.route.getValue() !== routeLabel) {
                boardToolbarControls.route.setValue(routeLabel);
            }
            if (boardToolbarControls.search.getValue() !== snapshot.search) {
                boardToolbarControls.search.setValue(snapshot.search);
            }
        }

        function applyBoardSearch(value) {
            if (!isActive()) return;
            state.setSearch(value);
            if (state.mode() !== "board") return;
            renderCurrent({ preserveBoardToolbar: true });
            if (boardToolbarControls && boardToolbarControls.search) {
                Renderer.focusSearch(shell, boardToolbarControls.search);
            }
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
                    disposeBoardToolbarControls();
                    boardToolbarMounted = false;
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

                const archiveRequest = context.can_view_history === true
                    ? Api.getArchive()
                    : Promise.resolve([]);
                const readyRequest = canLoadReadyForDelivery(context)
                    ? Api.getReadyForDelivery()
                    : Promise.resolve([]);
                const [rows, archiveRows, readyRows] = await Promise.all([
                    Api.getInbox(),
                    archiveRequest,
                    readyRequest,
                ]);
                if (
                    !isActive()
                    || !state.isCurrentListRequest(token)
                    || state.mode() !== requestedMode
                ) {
                    return null;
                }
                state.setRows(rows || [], archiveRows || [], readyRows || []);
                renderCurrent();
                return state.snapshot();
            } catch (error) {
                if (isActive() && state.isCurrentListRequest(token) && state.mode() === requestedMode) {
                    disposeBoardToolbarControls();
                    boardToolbarMounted = false;
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
            disposeBoardToolbarControls();
            boardToolbarMounted = false;
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
            syncRefreshButtonVisibility();
            if (state.mode() === "account") renderAccount();
            else loadList();
        }

        function syncRefreshButtonVisibility() {
            if (!$refreshButton) return;
            const visible = state.mode() !== "account";
            if (typeof $refreshButton.toggle === "function") {
                $refreshButton.toggle(visible);
            }
        }

        function setRouteFilter(value) {
            if (!isActive()) return;
            state.setRouteFilter(value);
            if (state.mode() === "board") {
                renderCurrent({ preserveBoardToolbar: boardToolbarMounted });
            }
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
