"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const pageSource = fs.readFileSync(
    path.resolve(__dirname, "../../almdina_erp/page/factory_master_data/factory_master_data.js"),
    "utf8"
);
const lifecycleSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/page_revisit_refresh.js"),
    "utf8"
);

const METHODS = Object.freeze({
    load: "almdina_erp.almdina_erp.services.master_data_service.get_production_routing_console",
    save: "almdina_erp.almdina_erp.services.master_data_service.save_production_routing",
    toggle: "almdina_erp.almdina_erp.services.master_data_service.set_production_routing_disabled",
    remove: "almdina_erp.almdina_erp.services.master_data_service.delete_production_routing",
});

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return {promise, resolve, reject};
}

async function flush() {
    await Promise.resolve();
    await Promise.resolve();
    await new Promise(resolve => setImmediate(resolve));
}

function routingData(label = "Route 1") {
    return {
        summary: {routings: 1, active_routings: 1, total_stages: 1, in_flight_orders: 0},
        permissions: {
            create_production_routings: true,
            edit_production_routings: true,
            delete_production_routings: true,
        },
        routings: [{
            name: "R-1",
            label,
            disabled: false,
            modified: `modified-${label}`,
            stages: [{
                stage_type: "Cutting",
                department_label: "Cutting",
                operational_role: "CNC Operator",
                is_planning_stage: 1,
            }],
        }],
        stage_catalog: [{
            stage_type: "Cutting",
            label: "Cutting",
            description: "Cut",
            planning: true,
        }],
        operational_roles: ["CNC Operator"],
        audit_log: [],
    };
}

function createRuntime({coldCore = false, pendingStyle = false} = {}) {
    const wrapper = {_route: "factory-master-data"};
    const main = {kind: "main", html: "", writes: [], classesRemoved: []};
    const eventOwners = new WeakMap();
    const callQueues = new Map();
    const calls = [];
    const alerts = [];
    const messages = [];
    const confirms = [];
    const buttons = [];
    const assetLoad = deferred();
    const styleLoad = deferred();

    function eventList(target) {
        if (!eventOwners.has(target)) eventOwners.set(target, []);
        return eventOwners.get(target);
    }

    function namespaceMatches(registered, requested) {
        if (!requested) return true;
        if (requested.startsWith(".")) return registered.includes(requested);
        return registered === requested;
    }

    function collection(target, selector = "") {
        const api = {
            length: 0,
            find(nextSelector) {
                if (target === wrapper && nextSelector === ".layout-main-section") {
                    return collection(main, nextSelector);
                }
                return collection({kind: "query", selector: nextSelector}, nextSelector);
            },
            html(value) {
                if (value === undefined) return target.html || "";
                if (target === main) {
                    main.html = String(value);
                    main.writes.push(main.html);
                } else {
                    target.html = String(value);
                }
                return this;
            },
            on(names, selectorOrHandler, maybeHandler) {
                const delegated = typeof selectorOrHandler === "string" ? selectorOrHandler : null;
                const handler = delegated ? maybeHandler : selectorOrHandler;
                for (const name of String(names).split(/\s+/).filter(Boolean)) {
                    eventList(target).push({name, selector: delegated, handler});
                }
                return this;
            },
            off(name = "") {
                const kept = eventList(target).filter(entry => !namespaceMatches(entry.name, String(name)));
                eventOwners.set(target, kept);
                return this;
            },
            prop() { return this; },
            text(value) {
                if (value === undefined) return target.text || "";
                target.text = String(value);
                return this;
            },
            addClass() { return this; },
            removeClass(names) {
                if (target === main || target.kind === "query") {
                    main.classesRemoved.push(String(names));
                }
                return this;
            },
            get() { return undefined; },
            val() { return ""; },
        };
        return api;
    }

    function jquery(target) {
        if (typeof target === "string") return collection({kind: "html", html: ""});
        return collection(target);
    }

    function trigger(target, name) {
        for (const entry of [...eventList(target)]) {
            if (entry.name.split(".")[0] === name && !entry.selector) entry.handler.call(target);
        }
    }

    function createGate() {
        let generation = 0;
        let current = null;
        return {
            begin(meta = null) {
                current = Object.freeze({generation: ++generation, meta});
                return current;
            },
            isCurrent(token) { return current === token; },
            invalidate() {
                generation += 1;
                current = null;
            },
        };
    }

    function createScope() {
        const cleanups = new Map();
        let disposed = false;
        return {
            track(cleanup, key) {
                if (cleanups.has(key)) cleanups.get(key)();
                cleanups.set(key, cleanup);
                return cleanup;
            },
            dispose() {
                if (disposed) return false;
                disposed = true;
                for (const cleanup of cleanups.values()) cleanup();
                cleanups.clear();
                return true;
            },
        };
    }

    const frontend = {
        createLatestRequestGate: createGate,
        createLifecycleScope: createScope,
        errorMessage(error, fallback) { return error && error.message ? error.message : fallback; },
        ensureStylesheet() {
            return pendingStyle ? styleLoad.promise : Promise.resolve({id: "routing-style"});
        },
    };

    const page = {
        add_inner_button(label, callback) {
            const button = {
                label,
                callback,
                removed: false,
                remove() { this.removed = true; },
            };
            buttons.push(button);
            return button;
        },
    };

    const frappe = {
        pages: {"factory-master-data": {}},
        container: {page: wrapper},
        ui: {
            make_app_page(options) {
                page.options = options;
                return page;
            },
        },
        utils: {
            escape_html(value) {
                return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
            },
        },
        call(request) {
            calls.push(request);
            const queue = callQueues.get(request.method) || [];
            assert.ok(queue.length, `missing queued response for ${request.method}`);
            return queue.shift().promise;
        },
        require(assets) {
            assert.deepEqual(Array.from(assets), [
                "/assets/almdina_erp/js/frontend_foundation.js",
                "/assets/almdina_erp/js/page_revisit_refresh.js",
            ]);
            return assetLoad.promise;
        },
        show_alert(options) {
            alerts.push(options);
            return {hide() {}};
        },
        msgprint(options) {
            const surface = {options, hidden: false, hide() { this.hidden = true; }};
            messages.push(surface);
            return surface;
        },
        confirm(message, yes, no) {
            const surface = {message, yes, no, hidden: false, hide() { this.hidden = true; }};
            confirms.push(surface);
            return surface;
        },
    };

    const windowObject = {frappe, document: {getElementById() { return null; }}};
    const context = vm.createContext({
        window: windowObject,
        document: windowObject.document,
        frappe,
        jQuery: jquery,
        $: jquery,
        __: value => value,
        console,
        Promise,
        Object,
        String,
        Number,
        Boolean,
        Array,
        Set,
        Date,
        Error,
    });

    function installCore() {
        windowObject.AlmdinaFrontend = frontend;
        vm.runInContext(lifecycleSource, context, {filename: "page_revisit_refresh.js"});
    }

    if (!coldCore) installCore();
    vm.runInContext(pageSource, context, {filename: "factory_master_data.js"});

    return {
        wrapper,
        main,
        page,
        frappe,
        alerts,
        messages,
        confirms,
        buttons,
        calls,
        assetLoad,
        styleLoad,
        installCore,
        enqueue(method) {
            const item = deferred();
            if (!callQueues.has(method)) callQueues.set(method, []);
            callQueues.get(method).push(item);
            return item;
        },
        loadPage() {
            return frappe.pages["factory-master-data"].on_page_load(wrapper);
        },
        owner() { return wrapper.__almdinaRoutingWorkflowPage; },
        show() {
            frappe.container.page = wrapper;
            trigger(wrapper, "show");
        },
        hide() {
            frappe.container.page = {};
            trigger(wrapper, "hide");
        },
        listenerCount(target, namespace = "") {
            return eventList(target).filter(entry => !namespace || entry.name.includes(namespace)).length;
        },
    };
}

async function bootActive(data = routingData()) {
    const runtime = createRuntime();
    const initial = runtime.enqueue(METHODS.load);
    const bootstrap = runtime.loadPage();
    await flush();
    initial.resolve({message: data});
    await bootstrap;
    await flush();
    return runtime;
}

function makeEditorDirty(owner, value = "Dirty route") {
    owner.openEditor("R-1");
    owner.state.editor.routing_name = value;
    owner.markDirty();
    return owner.state.editor;
}

async function testColdBootstrapOwnership() {
    const runtime = createRuntime({coldCore: true, pendingStyle: true});
    const bootstrap = runtime.loadPage();
    assert.equal(runtime.page.options.title, "إدارة مسارات الإنتاج");
    assert.match(runtime.main.html, /data-almdina-loading-owner="factory-master-data-bootstrap"/);
    assert.equal(runtime.main.writes.length, 1, "the synchronous scaffold must own one neutral loading surface");

    runtime.hide();
    runtime.installCore();
    runtime.assetLoad.resolve();
    await flush();
    runtime.styleLoad.resolve({id: "routing-style"});
    await bootstrap;
    await flush();
    assert.equal(runtime.calls.length, 0, "late bootstrap must not read for a hidden page");
    assert.equal(runtime.alerts.length, 0, "late bootstrap must not show hidden UI");
    assert.equal(runtime.main.writes.length, 1, "late bootstrap must not replace the hidden DOM");

    const current = runtime.enqueue(METHODS.load);
    runtime.show();
    await flush();
    assert.equal(runtime.calls.length, 1);
    current.resolve({message: routingData("Current")});
    await flush();
    assert.match(runtime.main.html, /Current/);
    assert.equal(
        runtime.main.writes.filter(html => html.includes("data-almdina-loading-owner")).length,
        1,
        "the first read must reuse the bootstrap loading owner"
    );
}

async function testHiddenBootstrapFailureDoesNotCommit() {
    const runtime = createRuntime({coldCore: true, pendingStyle: true});
    const bootstrap = runtime.loadPage();
    runtime.hide();
    runtime.installCore();
    runtime.assetLoad.resolve();
    await flush();
    runtime.styleLoad.reject(new Error("stylesheet failed while hidden"));
    await bootstrap;
    await flush();
    assert.equal(runtime.main.writes.length, 1);
    assert.equal(runtime.alerts.length, 0);
    assert.equal(runtime.calls.length, 0);
}

async function testReadActivationAndWorkingState() {
    const runtime = await bootActive(routingData("Initial"));
    const owner = runtime.owner();

    runtime.hide();
    const stale = runtime.enqueue(METHODS.load);
    runtime.show();
    await flush();
    runtime.hide();
    stale.resolve({message: routingData("Stale")});
    await flush();
    assert.equal(owner.state.data.routings[0].label, "Initial");
    assert.doesNotMatch(runtime.main.html, /Stale/);

    const fresh = runtime.enqueue(METHODS.load);
    runtime.show();
    await flush();
    fresh.resolve({message: routingData("Fresh")});
    await flush();
    assert.equal(owner.state.data.routings[0].label, "Fresh");
    assert.match(runtime.main.html, /Fresh/);

    owner.state.section = "audit";
    owner.state.search = "needle";
    owner.state.status = "disabled";
    const cleanRevisit = runtime.enqueue(METHODS.load);
    runtime.hide();
    runtime.show();
    await flush();
    cleanRevisit.resolve({message: routingData("Clean revisit")});
    await flush();
    assert.equal(owner.state.section, "audit");
    assert.equal(owner.state.search, "needle");
    assert.equal(owner.state.status, "disabled");

    const editor = makeEditorDirty(owner, "Byte-for-byte draft");
    owner.state.draggedStageId = editor.stages[0].clientId;
    const snapshot = JSON.stringify(editor);
    const callsBeforeDirtyRevisit = runtime.calls.length;
    runtime.hide();
    assert.equal(owner.disposed, false, "hide must not dispose the mounted page");
    assert.equal(owner.state.draggedStageId, null, "transient drag state must be cleared");
    runtime.show();
    await flush();
    assert.equal(JSON.stringify(owner.state.editor), snapshot);
    assert.equal(runtime.calls.length, callsBeforeDirtyRevisit, "dirty activation must not destructively read");
    assert.equal(owner.state.section, "routings");
    assert.equal(owner.state.search, "needle");
    assert.equal(owner.state.status, "disabled");
}

async function testTransientChildrenAreGenerationOwned() {
    const runtime = await bootActive();
    const owner = runtime.owner();
    makeEditorDirty(owner);

    owner.refresh();
    const refreshConfirm = runtime.confirms.at(-1);
    const refreshSnapshot = JSON.stringify(owner.state.editor);
    runtime.hide();
    assert.equal(refreshConfirm.hidden, true);
    runtime.show();
    await refreshConfirm.yes();
    await flush();
    assert.equal(JSON.stringify(owner.state.editor), refreshSnapshot, "a stale refresh confirm cannot discard the editor");

    const stageId = owner.state.editor.stages[0].clientId;
    owner.removeStage(stageId);
    const removeConfirm = runtime.confirms.at(-1);
    const removeSnapshot = JSON.stringify(owner.state.editor);
    runtime.hide();
    runtime.show();
    await removeConfirm.yes();
    assert.equal(JSON.stringify(owner.state.editor), removeSnapshot, "a stale remove-stage confirm cannot edit a newer visit");

    owner.closeEditor();
    const closeConfirm = runtime.confirms.at(-1);
    const closeSnapshot = JSON.stringify(owner.state.editor);
    runtime.hide();
    runtime.show();
    await closeConfirm.yes();
    assert.equal(JSON.stringify(owner.state.editor), closeSnapshot, "a stale close confirm cannot discard the editor");

    const callsBeforeStaleCommand = runtime.calls.length;
    owner.toggleRoute({name: "R-1", disabled: "1", modified: "m1"});
    const toggleConfirm = runtime.confirms.at(-1);
    runtime.hide();
    runtime.show();
    await toggleConfirm.yes();
    assert.equal(runtime.calls.length, callsBeforeStaleCommand, "a stale toggle confirm cannot start an RPC");

    owner.state.editor.routing_name = "";
    owner.markDirty();
    await owner.saveEditor();
    const validation = runtime.messages.at(-1);
    assert.equal(validation.hidden, false);
    runtime.hide();
    assert.equal(validation.hidden, true, "feature-owned validation UI must close on deactivate");
}

async function testSaveCompletionAndNewerDraft() {
    const runtime = await bootActive();
    const owner = runtime.owner();
    makeEditorDirty(owner, "Saved while hidden");
    const save = runtime.enqueue(METHODS.save);
    const completion = owner.saveEditor();
    runtime.hide();
    save.resolve({message: {name: "R-1"}});
    assert.deepEqual(await completion, {name: "R-1"}, "the server mutation remains semantically successful");
    await flush();
    assert.equal(runtime.alerts.length, 0);
    assert.ok(owner.state.editor, "hidden completion must not clear working state");

    const reconcile = runtime.enqueue(METHODS.load);
    runtime.show();
    await flush();
    reconcile.resolve({message: routingData("Saved server state")});
    await flush();
    assert.equal(owner.state.editor, null);
    assert.match(runtime.main.html, /Saved server state/);
    assert.equal(runtime.alerts.length, 0, "an old visit must never show a success alert");

    makeEditorDirty(owner, "Save A");
    const saveA = runtime.enqueue(METHODS.save);
    const completionA = owner.saveEditor();
    runtime.hide();
    runtime.show();
    owner.state.editor.routing_name = "Newer generation B draft";
    owner.markDirty();
    const newerSnapshot = JSON.stringify(owner.state.editor);
    saveA.resolve({message: {name: "R-1"}});
    await completionA;
    await flush();
    assert.equal(JSON.stringify(owner.state.editor), newerSnapshot, "old save A cannot overwrite generation B working state");
    assert.equal(owner.reconciliationPending, true);

    owner.closeEditor();
    const discard = runtime.confirms.at(-1);
    const deferredReconcile = runtime.enqueue(METHODS.load);
    const discardResult = discard.yes();
    await flush();
    deferredReconcile.resolve({message: routingData("After discard")});
    await discardResult;
    await flush();
    assert.equal(owner.state.editor, null);
    assert.match(runtime.main.html, /After discard/);
}

async function runHiddenCommand(runtime, method, invoke, label) {
    const owner = runtime.owner();
    const command = runtime.enqueue(method);
    invoke(owner);
    const confirmation = runtime.confirms.at(-1);
    const completion = confirmation.yes();
    await flush();
    runtime.hide();
    command.resolve({message: {ok: true}});
    assert.deepEqual(await completion, {ok: true});
    await flush();
    assert.equal(runtime.alerts.length, 0, `${label} must not alert from a hidden generation`);
    assert.equal(owner.reconciliationPending, true);
    const read = runtime.enqueue(METHODS.load);
    runtime.show();
    await flush();
    read.resolve({message: routingData(`${label} reconciled`)});
    await flush();
    assert.match(runtime.main.html, new RegExp(`${label} reconciled`));
}

async function testToggleDeleteAndHiddenFailure() {
    await runHiddenCommand(
        await bootActive(),
        METHODS.toggle,
        owner => owner.toggleRoute({name: "R-1", disabled: "1", modified: "m1"}),
        "Toggle"
    );
    await runHiddenCommand(
        await bootActive(),
        METHODS.remove,
        owner => owner.deleteRoute({name: "R-1", modified: "m1"}),
        "Delete"
    );

    const runtime = await bootActive();
    const owner = runtime.owner();
    makeEditorDirty(owner, "Failed hidden save");
    const save = runtime.enqueue(METHODS.save);
    const completion = owner.saveEditor();
    runtime.hide();
    save.reject(new Error("hidden failure"));
    assert.equal(await completion, false);
    await flush();
    assert.equal(runtime.alerts.length, 0);
    assert.equal(runtime.messages.length, 0);
    const snapshot = JSON.stringify(owner.state.editor);
    runtime.show();
    await flush();
    assert.equal(JSON.stringify(owner.state.editor), snapshot);
}

async function testRemountDisposesOnlyTheOldOwner() {
    const runtime = await bootActive();
    const oldOwner = runtime.owner();
    const delegatedOwners = runtime.listenerCount(runtime.main, ".prw");
    runtime.hide();
    const oldRead = runtime.enqueue(METHODS.load);
    runtime.show();
    await flush();
    const secondRead = runtime.enqueue(METHODS.load);
    const remount = runtime.loadPage();
    await flush();
    const newOwner = runtime.owner();
    assert.notEqual(newOwner, oldOwner);
    assert.equal(oldOwner.disposed, true);
    assert.equal(newOwner.disposed, false);
    assert.equal(runtime.listenerCount(runtime.wrapper, ".almdinaPageActivation"), 2);
    assert.equal(runtime.buttons.filter(button => !button.removed).length, 1);
    oldRead.resolve({message: routingData("Disposed owner")});
    await flush();
    assert.doesNotMatch(runtime.main.html, /Disposed owner/, "disposed owner reads cannot commit into the remount");
    secondRead.resolve({message: routingData("Remounted")});
    await remount;
    await flush();
    assert.equal(
        runtime.listenerCount(runtime.main, ".prw"),
        delegatedOwners,
        "remount must leave one delegated event set"
    );

    runtime.hide();
    assert.equal(newOwner.disposed, false, "a normal hide is deactivation, not disposal");
}

(async () => {
    await testColdBootstrapOwnership();
    await testHiddenBootstrapFailureDoesNotCommit();
    await testReadActivationAndWorkingState();
    await testTransientChildrenAreGenerationOwned();
    await testSaveCompletionAndNewerDraft();
    await testToggleDeleteAndHiddenFailure();
    await testRemountDisposesOnlyTheOldOwner();
    console.log("Factory Master Data PAGE lifecycle simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
