"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js", relativePath), "utf8");
}

function deferred() {
    let resolvePromise;
    let rejectPromise;
    const request = {
        settled: false,
        promise: new Promise((resolve, reject) => {
            resolvePromise = resolve;
            rejectPromise = reject;
        }),
    };
    request.resolve = value => {
        request.settled = true;
        resolvePromise(value);
    };
    request.reject = error => {
        request.settled = true;
        rejectPromise(error);
    };
    return request;
}

function queue() {
    const requests = [];
    return {
        requests,
        call() {
            const request = deferred();
            requests.push(request);
            return request.promise;
        },
        pending() {
            return requests.find(request => !request.settled);
        },
    };
}

function createLatestRequestGate() {
    let generation = 0;
    return {
        begin(meta = null) {
            generation += 1;
            return Object.freeze({ generation, meta });
        },
        isCurrent(token) {
            return Boolean(token && token.generation === generation);
        },
        invalidate() {
            generation += 1;
            return generation;
        },
    };
}

function createLifecycleScope() {
    let disposed = false;
    const cleanups = new Map();
    return {
        track(cleanup, key) {
            if (cleanups.has(key)) cleanups.get(key)();
            if (disposed) {
                cleanup();
                return null;
            }
            cleanups.set(key, cleanup);
            return key;
        },
        dispose() {
            if (disposed) return false;
            disposed = true;
            for (const cleanup of cleanups.values()) cleanup();
            cleanups.clear();
            return true;
        },
        isDisposed: () => disposed,
    };
}

function createHarness() {
    const wrapperEvents = new Map();
    const wrapper = { page: {}, bootstrapLoading: true };
    const otherPage = {};
    const queues = {
        context: queue(),
        inbox: queue(),
        archive: queue(),
        ready: queue(),
        handoffContext: queue(),
        handoff: queue(),
        logout: queue(),
    };
    const renders = {
        loading: 0,
        board: [],
        list: [],
        account: [],
        error: [],
        focus: 0,
    };
    const dialogEvents = {
        created: 0,
        disposed: 0,
        deactivated: 0,
        promptWorker: 0,
        noWorkers: 0,
        success: 0,
        error: 0,
        terminalYes: null,
        logoutYes: null,
        owned: 0,
    };
    const quickOperations = [];
    const routes = [];
    let actions = null;
    let activeInteractionOwners = 0;
    let interactionDeactivations = 0;
    let quickUiSuccess = 0;

    function jquery(target) {
        assert.equal(target, wrapper);
        return {
            on(eventName, callback) {
                wrapperEvents.set(String(eventName), callback);
                return this;
            },
            off(eventName) {
                const namespace = String(eventName || "");
                if (namespace.startsWith(".")) {
                    for (const name of [...wrapperEvents.keys()]) {
                        if (name.endsWith(namespace)) wrapperEvents.delete(name);
                    }
                } else if (namespace) {
                    wrapperEvents.delete(namespace);
                } else {
                    wrapperEvents.clear();
                }
                return this;
            },
        };
    }

    function trigger(eventName) {
        for (const [registered, callback] of [...wrapperEvents.entries()]) {
            if (registered.split(".")[0] === eventName) callback.call(wrapper);
        }
    }

    const frappe = {
        container: { page: wrapper },
        set_route(...parts) { routes.push(parts); },
    };
    const fakeWindow = {
        frappe,
        jQuery: jquery,
        location: { href: "" },
        AlmdinaFrontend: {
            createLatestRequestGate,
            createLifecycleScope,
            errorMessage(error, fallback) {
                return error && error.message ? error.message : fallback;
            },
        },
        AlmdinaShopFloorInboxApi: {
            getSessionContext: () => queues.context.call(),
            getInbox: () => queues.inbox.call(),
            getArchive: () => queues.archive.call(),
            getReadyForDelivery: () => queues.ready.call(),
            getHandoffContext: () => queues.handoffContext.call(),
            handoffStage: () => queues.handoff.call(),
            logout: () => queues.logout.call(),
        },
        AlmdinaShopFloorInboxViewModel: {
            board(snapshot) {
                return { routeFilter: snapshot.routeFilter, snapshot };
            },
            list(snapshot) { return { snapshot }; },
            account(context) { return { context }; },
        },
        AlmdinaShopFloorInboxRenderer: {
            createShell() {
                const ownsBootstrap = wrapper.bootstrapLoading;
                wrapper.bootstrapLoading = false;
                return {
                    page: wrapper.page,
                    $section: {},
                    hasBootstrapLoading: () => ownsBootstrap,
                };
            },
            syncTabs() {},
            loading() { renders.loading += 1; },
            renderBoard(shell, model, search, mode) {
                renders.board.push({ model, search, mode });
            },
            renderList(shell, model, mode) { renders.list.push({ model, mode }); },
            renderAccount(shell, model) { renders.account.push(model); },
            error(shell, message) { renders.error.push(message); },
            focusSearch() { renders.focus += 1; },
        },
        AlmdinaShopFloorInboxInteractions: {
            bind(shell, lifecycle, callbacks) {
                actions = callbacks;
                activeInteractionOwners += 1;
                lifecycle.track(() => { activeInteractionOwners -= 1; }, "interactions");
                return {
                    deactivate() { interactionDeactivations += 1; },
                };
            },
        },
        AlmdinaShopFloorInboxDialogs: {
            create() {
                dialogEvents.created += 1;
                return {
                    own(surface) { dialogEvents.owned += 1; return surface; },
                    confirmTerminal(generation, onYes) {
                        dialogEvents.terminalYes = onYes;
                        return {};
                    },
                    confirmLogout(generation, onYes) {
                        dialogEvents.logoutYes = onYes;
                        return {};
                    },
                    promptWorker() { dialogEvents.promptWorker += 1; return {}; },
                    noWorkers() { dialogEvents.noWorkers += 1; return {}; },
                    success() { dialogEvents.success += 1; },
                    error() { dialogEvents.error += 1; },
                    deactivate() { dialogEvents.deactivated += 1; },
                    dispose() { dialogEvents.disposed += 1; },
                };
            },
        },
        AlmdinaShopFloorQuickActions: {
            perform(context, options) {
                const operation = deferred();
                quickOperations.push({ context, options, operation });
                return operation.promise.then(data => {
                    if (!options.lifecycle.isCurrent()) {
                        return Promise.resolve(options.lifecycle.onStaleMutationSuccess(data)).then(() => data);
                    }
                    quickUiSuccess += 1;
                    return Promise.resolve(options.onSuccess(data)).then(() => data);
                });
            },
        },
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe,
        $: jquery,
        __(value) { return value; },
        console,
        Promise,
        Object,
        Array,
        Map,
        Set,
        String,
        Number,
        Boolean,
        JSON,
        Error,
    });
    vm.runInContext(source("page_revisit_refresh.js"), context, { filename: "page_revisit_refresh.js" });
    vm.runInContext(source("shop_floor_inbox/state.js"), context, { filename: "shop_floor_inbox/state.js" });
    vm.runInContext(source("shop_floor_inbox/controller.js"), context, { filename: "shop_floor_inbox/controller.js" });

    return {
        actions: () => actions,
        activeInteractionOwners: () => activeInteractionOwners,
        controller: fakeWindow.AlmdinaShopFloorInboxController,
        dialogEvents,
        fakeWindow,
        interactionDeactivations: () => interactionDeactivations,
        listenerCount: () => wrapperEvents.size,
        quickOperations,
        quickUiSuccess: () => quickUiSuccess,
        queues,
        renders,
        routes,
        wrapper,
        hide() {
            frappe.container.page = otherPage;
            trigger("hide");
        },
        show() {
            frappe.container.page = wrapper;
            wrapper._route = "shop-floor-inbox";
            trigger("show");
        },
    };
}

async function flush() {
    await Promise.resolve();
    await new Promise(resolve => setImmediate(resolve));
}

async function resolveBoardRefresh(harness, context = {}, rows = [], archiveRows = [], readyRows = []) {
    const contextRequest = harness.queues.context.pending();
    assert.ok(contextRequest, "a current activation must own one context request");
    contextRequest.resolve(context);
    await flush();

    const inboxRequest = harness.queues.inbox.pending();
    assert.ok(inboxRequest, "the current context must start one inbox request");
    inboxRequest.resolve(rows);

    if (context.can_view_history === true) {
        const archiveRequest = harness.queues.archive.pending();
        assert.ok(archiveRequest, "history capability must start one archive request");
        archiveRequest.resolve(archiveRows);
    }

    if (context.capabilities && context.capabilities.mark_delivered === true) {
        const readyRequest = harness.queues.ready.pending();
        assert.ok(readyRequest, "delivery capability must start one ready-for-delivery request");
        readyRequest.resolve(readyRows);
    }
    await flush();
}

async function testReadInvalidationAndFreshRevisit() {
    const harness = createHarness();
    harness.controller.mount(harness.wrapper, { page: harness.wrapper.page });
    assert.equal(harness.queues.context.requests.length, 1);
    assert.equal(harness.renders.loading, 0, "the synchronous bootstrap must remain the only initial loading owner");

    harness.hide();
    harness.queues.context.requests[0].resolve({ visit: "stale-context" });
    await flush();
    assert.equal(harness.queues.inbox.requests.length, 0, "a context response after hide must not become authoritative");
    assert.equal(harness.renders.board.length, 0);

    harness.show();
    harness.queues.context.requests[1].resolve({ visit: "stale-list" });
    await flush();
    assert.equal(harness.queues.inbox.requests.length, 1);
    harness.hide();
    harness.queues.inbox.requests[0].resolve([{ id: "A" }]);
    await flush();
    assert.equal(harness.renders.board.length, 0, "list work from an inactive visit must not render");

    harness.show();
    await resolveBoardRefresh(harness, { visit: "current" }, [{ id: "B" }], []);
    assert.equal(harness.renders.board.length, 1, "the current revisit must render exactly once");
    assert.equal(harness.renders.board[0].model.snapshot.sessionContext.visit, "current");
    assert.equal(harness.dialogEvents.disposed, 0, "simple hide must not dispose the mounted controller");
}

async function testMountWhileInactiveWaitsForCurrentShow() {
    const harness = createHarness();
    harness.hide();
    harness.controller.mount(harness.wrapper, { page: harness.wrapper.page });
    assert.equal(harness.queues.context.requests.length, 0, "late assets may mount the controller inactive without starting reads");
    assert.equal(harness.renders.board.length, 0);
    harness.show();
    await resolveBoardRefresh(harness, { visit: "first-current-show" }, [{ id: "fresh" }], []);
    assert.equal(harness.renders.board.length, 1);
    assert.equal(harness.renders.loading, 0, "the preserved bootstrap surface owns loading until the first current render");
}

async function testHistoryAndDeliveryReadsFollowCapabilities() {
    const deliveryHarness = createHarness();
    deliveryHarness.controller.mount(deliveryHarness.wrapper, { page: deliveryHarness.wrapper.page });
    await resolveBoardRefresh(
        deliveryHarness,
        { can_view_history: false, capabilities: { mark_delivered: true } },
        [],
        [],
        [{ id: "ready" }]
    );
    assert.equal(deliveryHarness.queues.archive.requests.length, 0, "history must not be requested without its capability");
    assert.equal(deliveryHarness.queues.ready.requests.length, 1, "delivery-ready data remains independently operational");
    assert.equal(deliveryHarness.renders.board.at(-1).model.snapshot.archiveRows.length, 0);
    assert.equal(deliveryHarness.renders.board.at(-1).model.snapshot.readyRows.length, 1);

    const historyHarness = createHarness();
    historyHarness.controller.mount(historyHarness.wrapper, { page: historyHarness.wrapper.page });
    await resolveBoardRefresh(
        historyHarness,
        { can_view_history: true, capabilities: { mark_delivered: false } },
        [],
        [{ id: "history" }],
        []
    );
    assert.equal(historyHarness.queues.archive.requests.length, 1, "history capability must request the archive");
    assert.equal(historyHarness.queues.ready.requests.length, 0, "history alone must not request delivery-ready data");
    assert.equal(historyHarness.renders.board.at(-1).model.snapshot.archiveRows.length, 1);
}

async function testMutationCompletionAndGenerationReconciliation() {
    const harness = createHarness();
    harness.controller.mount(harness.wrapper, { page: harness.wrapper.page });
    await resolveBoardRefresh(harness, { visit: "initial" }, [], []);
    const baselineRenders = harness.renders.board.length;

    harness.actions().quickAction({ order: "DCO-1", stage: "PST-1", canStart: true }, {});
    assert.equal(harness.quickOperations.length, 1);
    harness.hide();
    harness.quickOperations[0].operation.resolve({ ok: true });
    await flush();
    assert.equal(harness.quickUiSuccess(), 0, "a hidden mutation completion must not call UI onSuccess");
    assert.equal(harness.renders.board.length, baselineRenders);

    harness.show();
    await resolveBoardRefresh(harness, { visit: "after-hidden-mutation" }, [{ id: "fresh" }], []);
    assert.equal(harness.renders.board.length, baselineRenders + 1);

    harness.actions().quickAction({ order: "DCO-2", stage: "PST-2", canStart: true }, {});
    const oldOperation = harness.quickOperations[1];
    harness.hide();
    harness.show();
    assert.ok(harness.queues.context.pending(), "generation B starts its activation reconciliation");
    oldOperation.operation.resolve({ ok: true });
    await flush();
    assert.equal(harness.queues.context.requests.length, 4, "old generation success must replace B with one newer read");

    harness.queues.context.requests[2].resolve({ visit: "superseded-B" });
    await flush();
    assert.equal(harness.queues.inbox.requests.length, 2, "superseded context B must not start list work");
    await resolveBoardRefresh(harness, { visit: "current-C" }, [{ id: "C" }], []);
    assert.equal(harness.quickUiSuccess(), 0, "generation A cannot commit into generation B/C");
    assert.equal(harness.renders.board.at(-1).model.snapshot.sessionContext.visit, "current-C");
}

async function testHandoffReadAndTransientChildInvalidation() {
    const harness = createHarness();
    harness.controller.mount(harness.wrapper, { page: harness.wrapper.page });
    await resolveBoardRefresh(harness, { visit: "initial" }, [], []);

    harness.actions().handoff({ stage: "PST-3", next: "CNC" });
    assert.equal(harness.queues.handoffContext.requests.length, 1);
    harness.hide();
    harness.queues.handoffContext.requests[0].resolve({
        workers: [{ name: "worker@example.com" }],
        next_department: "CNC",
    });
    await flush();
    assert.equal(harness.dialogEvents.promptWorker, 0, "a stale handoff read must not open a worker child");
    assert.equal(harness.dialogEvents.noWorkers, 0, "a stale handoff read must not open a no-workers child");
    assert.equal(harness.dialogEvents.deactivated, 1, "page deactivation owns child-surface cleanup");

    harness.show();
    await resolveBoardRefresh(harness, { visit: "handoff-current" }, [], []);
    const renderCount = harness.renders.board.length;
    harness.actions().handoff({ stage: "PST-FINAL", next: "" });
    assert.equal(typeof harness.dialogEvents.terminalYes, "function");
    harness.dialogEvents.terminalYes();
    assert.equal(harness.queues.handoff.requests.length, 1, "confirmed handoff must start the server mutation");
    harness.hide();
    harness.queues.handoff.requests[0].resolve({ ok: true });
    await flush();
    assert.equal(harness.dialogEvents.success, 0, "hidden handoff success must not alert");
    assert.equal(harness.renders.board.length, renderCount, "hidden handoff success must not render");
    harness.show();
    await resolveBoardRefresh(harness, { visit: "after-handoff" }, [{ id: "fresh" }], []);
    assert.equal(harness.renders.board.length, renderCount + 1, "handoff success reconciles on the next activation");
}

async function testInteractionStateAndAccountModeSurviveRevisit() {
    const harness = createHarness();
    harness.controller.mount(harness.wrapper, { page: harness.wrapper.page });
    await resolveBoardRefresh(harness, { visit: "initial" }, [], []);

    harness.actions().setSearch("Door 42");
    harness.actions().setRouteFilter("route-a");
    harness.actions().setMode("inbox");
    await flush();
    harness.queues.inbox.pending().resolve([{ id: "inbox" }]);
    await flush();
    harness.hide();
    harness.show();
    await resolveBoardRefresh(harness, { visit: "inbox-revisit" }, [{ id: "fresh-inbox" }], []);
    assert.equal(harness.renders.list.at(-1).mode, "inbox", "inbox mode must survive revisit");

    harness.actions().setMode("board");
    await flush();
    harness.queues.inbox.pending().resolve([]);
    await flush();
    const board = harness.renders.board.at(-1);
    assert.equal(board.search, "door 42");
    assert.equal(board.model.routeFilter, "route-a");

    harness.actions().setMode("account");
    await flush();
    const accountBefore = harness.renders.account.length;
    harness.hide();
    harness.show();
    const inboxCount = harness.queues.inbox.requests.length;
    harness.queues.context.pending().resolve({ identity: { user: "worker@example.com" } });
    await flush();
    assert.equal(harness.renders.account.length, accountBefore + 1, "account mode must refresh and survive revisit");
    assert.equal(harness.queues.inbox.requests.length, inboxCount, "account activation must not start list reads");
}

async function testRemountReplacesOwnersWithoutHideDispose() {
    const harness = createHarness();
    const first = harness.controller.mount(harness.wrapper, { page: harness.wrapper.page });
    assert.equal(harness.listenerCount(), 2);
    assert.equal(harness.activeInteractionOwners(), 1);

    const second = harness.controller.mount(harness.wrapper, { page: harness.wrapper.page });
    assert.notEqual(first, second);
    assert.equal(harness.listenerCount(), 2, "remount must leave one show/hide activation owner");
    assert.equal(harness.activeInteractionOwners(), 1, "remount must replace delegated/drag-drop ownership");
    assert.equal(harness.dialogEvents.disposed, 1, "remount must dispose the old transient-child owner");

    const requestsBeforeOldRefresh = harness.queues.context.requests.length;
    await first.refresh();
    assert.equal(harness.queues.context.requests.length, requestsBeforeOldRefresh, "the replaced controller cannot refresh");

    harness.hide();
    assert.equal(harness.activeInteractionOwners(), 1, "hide must not fully dispose delegated handlers");
    assert.equal(harness.interactionDeactivations(), 1, "hide only suspends drag/drop transient state");
    harness.show();
    assert.equal(harness.queues.context.requests.length, requestsBeforeOldRefresh + 1);
}

async function testLogoutConfirmationRemainsPageOwned() {
    const harness = createHarness();
    harness.controller.mount(harness.wrapper, { page: harness.wrapper.page });
    await resolveBoardRefresh(harness, { visit: "initial" }, [], []);
    harness.actions().logout();
    assert.equal(typeof harness.dialogEvents.logoutYes, "function");
    harness.dialogEvents.logoutYes();
    assert.equal(harness.queues.logout.requests.length, 1);
    harness.hide();
    harness.queues.logout.requests[0].resolve({ ok: true });
    await flush();
    assert.equal(harness.fakeWindow.location.href, "", "hidden logout completion cannot navigate immediately");
    harness.show();
    assert.equal(harness.fakeWindow.location.href, "/login", "the next current activation reconciles the ended session");
}

(async () => {
    await testReadInvalidationAndFreshRevisit();
    await testMountWhileInactiveWaitsForCurrentShow();
    await testHistoryAndDeliveryReadsFollowCapabilities();
    await testMutationCompletionAndGenerationReconciliation();
    await testHandoffReadAndTransientChildInvalidation();
    await testInteractionStateAndAccountModeSurviveRevisit();
    await testRemountReplacesOwnersWithoutHideDispose();
    await testLogoutConfirmationRemainsPageOwned();
    console.log("Shop Floor PAGE lifecycle regression simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
