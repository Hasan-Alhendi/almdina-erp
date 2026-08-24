"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js", relativePath), "utf8");
}

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

function endpointQueue() {
    const requests = [];
    return {
        requests,
        call() {
            const request = deferred();
            requests.push(request);
            return request.promise;
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
        generation: () => generation,
    };
}

function createHarness() {
    const wrapperEvents = new Map();
    const timers = [];
    const main = {};
    const innerButtons = [];
    const alerts = [];
    const messages = [];
    const confirms = [];
    let primaryAction = null;
    const wrapper = {
        page: {
            btn_primary: { toggle() {} },
            clear_inner_toolbar() { innerButtons.length = 0; },
            set_primary_action(label, callback) { primaryAction = { label, callback }; },
            add_inner_button(label, callback) { innerButtons.push({ label, callback }); },
        },
    };
    const otherPage = {};

    function jquery(target) {
        return {
            find() {
                return main;
            },
            on(eventName, callback) {
                wrapperEvents.set(String(eventName), callback);
                return this;
            },
            off(eventName) {
                const name = String(eventName || "");
                if (name.startsWith(".")) {
                    for (const key of [...wrapperEvents.keys()]) {
                        if (key.endsWith(name)) wrapperEvents.delete(key);
                    }
                } else if (name) wrapperEvents.delete(name);
                else wrapperEvents.clear();
                return this;
            },
        };
    }

    function trigger(eventName) {
        for (const [registered, callback] of [...wrapperEvents.entries()]) {
            if (registered.split(".")[0] === eventName) callback.call(wrapper);
        }
    }

    function createLifecycleScope() {
        let disposed = false;
        const cleanups = new Map();
        let sequence = 0;

        function key(value) {
            if (value) return String(value);
            sequence += 1;
            return `cleanup:${sequence}`;
        }

        function track(cleanup, requestedKey = "") {
            if (typeof cleanup !== "function") return null;
            const resolved = key(requestedKey);
            if (cleanups.has(resolved)) cleanups.get(resolved)();
            if (disposed) {
                cleanup();
                return null;
            }
            cleanups.set(resolved, cleanup);
            return resolved;
        }

        function timeout(callback, delay, requestedKey = "") {
            const timer = { callback, cancelled: false, ran: false };
            timers.push(timer);
            track(() => { timer.cancelled = true; }, requestedKey || "timer");
            return timer;
        }

        function dispose() {
            if (disposed) return false;
            disposed = true;
            for (const cleanup of cleanups.values()) cleanup();
            cleanups.clear();
            return true;
        }

        return { track, timeout, dispose, isDisposed: () => disposed };
    }

    const frappe = {
        container: { page: wrapper },
        ui: {
            make_app_page() {
                throw new Error("Controllers must reuse the synchronous page shell");
            },
        },
        utils: { escape_html: value => String(value || "") },
        show_alert(payload) { alerts.push(payload); },
        msgprint(payload) {
            const surface = { hidden: 0, hide() { this.hidden += 1; } };
            messages.push({ payload, surface });
            return surface;
        },
        confirm(message, yes, no) {
            const surface = { hidden: 0, hide() { this.hidden += 1; } };
            confirms.push({ message, yes, no, surface });
            return surface;
        },
    };
    const fakeWindow = {
        frappe,
        jQuery: jquery,
        AlmdinaFrontend: {
            createLatestRequestGate,
            createLifecycleScope,
            errorMessage(error, fallback) {
                return error && error.message ? error.message : fallback;
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

    return {
        context,
        alerts,
        confirms,
        fakeWindow,
        frappe,
        innerButtons,
        main,
        messages,
        timers,
        wrapper,
        listenerCount: () => wrapperEvents.size,
        primaryAction: () => primaryAction,
        hide() {
            frappe.container.page = otherPage;
            trigger("hide");
        },
        show() {
            frappe.container.page = wrapper;
            wrapper._route = "admin-page";
            trigger("show");
        },
        runTimers() {
            for (const timer of timers) {
                if (timer.cancelled || timer.ran) continue;
                timer.ran = true;
                timer.callback();
            }
        },
    };
}

function evaluate(harness, relativePath) {
    vm.runInContext(source(relativePath), harness.context, { filename: relativePath });
}

async function flush() {
    await Promise.resolve();
    await new Promise(resolve => setImmediate(resolve));
}

async function testWorkforceLifecycle() {
    const harness = createHarness();
    const consoleQueue = endpointQueue();
    const auditQueue = endpointQueue();
    const renders = { loading: 0, content: 0, audit: 0 };
    let callbacks = null;

    harness.fakeWindow.AlmdinaFactoryWorkforceApi = {
        getConsole: () => consoleQueue.call(),
        getAudit: () => auditQueue.call(),
    };
    harness.fakeWindow.AlmdinaFactoryWorkforceViewModel = {
        create: () => ({
            page: () => ({}),
            can: () => true,
            actionAllowed: () => true,
            roleOptions: () => [],
            roleHomePolicy: () => ({ hasConflict: false, configured: [] }),
            findUser: (rows, email) => ({ email }),
        }),
    };
    harness.fakeWindow.AlmdinaFactoryWorkforceRenderer = {
        create: () => ({
            renderLoading() { renders.loading += 1; },
            renderError() {},
            render() { renders.content += 1; },
            auditHtml: () => "audit",
        }),
    };
    harness.fakeWindow.AlmdinaFactoryWorkforceInteractions = {
        bind: options => { callbacks = options.callbacks; return true; },
    };
    harness.fakeWindow.AlmdinaFactoryWorkforceDialogs = {
        create: () => ({
            openAudit() { renders.audit += 1; },
            showAlert() {},
            deactivate() {},
            dispose() {},
        }),
    };

    evaluate(harness, "factory_workforce/state.js");
    evaluate(harness, "factory_workforce/controller.js");
    const controller = harness.fakeWindow.AlmdinaFactoryWorkforceController.mount(harness.wrapper);

    assert.equal(consoleQueue.requests.length, 1);
    assert.equal(renders.loading, 0, "the synchronous page bootstrap owns the initial loading transition");
    harness.hide();
    consoleQueue.requests[0].resolve({ users: [{ email: "old@example.com" }] });
    await flush();
    assert.equal(renders.content, 0, "a Workforce console response after hide must not render");

    harness.show();
    assert.equal(consoleQueue.requests.length, 2, "the first real revisit must start a fresh Workforce read");
    consoleQueue.requests[1].resolve({ users: [{ email: "new@example.com" }] });
    await flush();
    assert.equal(renders.content, 1);

    callbacks.onAudit("new@example.com");
    assert.equal(auditQueue.requests.length, 1);
    harness.hide();
    auditQueue.requests[0].resolve({ events: [{ action: "old" }] });
    await flush();
    assert.equal(renders.audit, 0, "a Workforce audit response after hide must not open a dialog");

    harness.show();
    assert.equal(consoleQueue.requests.length, 3);
    const staleBeforeRemount = consoleQueue.requests[2];
    harness.fakeWindow.AlmdinaFactoryWorkforceController.mount(harness.wrapper);
    assert.equal(harness.listenerCount(), 2, "Workforce remount must retain one show/hide listener pair");
    assert.equal(consoleQueue.requests.length, 4);
    staleBeforeRemount.resolve({ users: [{ email: "stale-remount@example.com" }] });
    consoleQueue.requests[3].resolve({ users: [{ email: "fresh-remount@example.com" }] });
    await flush();
    assert.equal(renders.content, 2, "only the replacement Workforce controller may commit after remount");
    controller.dispose();
}

async function testProductionSettingsLifecycle() {
    const harness = createHarness();
    const settingsQueue = endpointQueue();
    const auditQueue = endpointQueue();
    const renders = { loading: 0, content: 0, audit: 0 };

    harness.fakeWindow.AlmdinaFactoryProductionSettingsApi = {
        getSettings: () => settingsQueue.call(),
        getAudit: () => auditQueue.call(),
    };
    harness.fakeWindow.AlmdinaFactoryProductionSettingsViewModel = {
        create: () => ({ page: () => ({}), sectionEditable: () => false }),
    };
    harness.fakeWindow.AlmdinaFactoryProductionSettingsRenderer = {
        create: () => ({
            renderLoading() { renders.loading += 1; },
            renderError() {},
            render() { renders.content += 1; },
            auditLoadingHtml: () => "loading",
            auditHtml: () => "audit",
            auditErrorHtml: () => "error",
        }),
    };
    harness.fakeWindow.AlmdinaFactoryProductionSettingsInteractions = { bind: () => true };
    harness.fakeWindow.AlmdinaFactoryProductionSettingsDialogs = {
        create: () => ({
            openAudit: () => ({ setHtml() { renders.audit += 1; } }),
            deactivate() {},
            dispose() {},
        }),
    };

    evaluate(harness, "factory_production_settings/state.js");
    evaluate(harness, "factory_production_settings/controller.js");
    harness.fakeWindow.AlmdinaFactoryProductionSettingsController.mount(harness.wrapper);

    assert.equal(settingsQueue.requests.length, 1);
    assert.equal(renders.loading, 0, "Production Settings must not duplicate its initial loading transition");
    harness.hide();
    settingsQueue.requests[0].resolve({ marker: "old" });
    await flush();
    assert.equal(renders.content, 0, "stale settings must not render after hide");

    harness.show();
    assert.equal(settingsQueue.requests.length, 2);
    assert.equal(renders.loading, 1, "a later active revisit owns one loading transition");
    settingsQueue.requests[1].resolve({ marker: "fresh" });
    await flush();
    assert.equal(renders.content, 1);

    harness.innerButtons[0].callback();
    assert.equal(auditQueue.requests.length, 1);
    harness.hide();
    auditQueue.requests[0].resolve([{ action: "old" }]);
    await flush();
    assert.equal(renders.audit, 0, "stale Production Settings audit must not update its dialog");
}

async function testPermissionsLifecycle() {
    const harness = createHarness();
    const consoleQueue = endpointQueue();
    const roleQueue = endpointQueue();
    const previewQueue = endpointQueue();
    const transferQueue = endpointQueue();
    const exportQueue = endpointQueue();
    const renders = { shell: 0, loaded: 0, checkboxSync: 0, dirtySync: 0, downloads: 0 };
    let callbacks = null;

    class FakeFileReader {
        readAsText(file) {
            this.result = file.contents;
            this.onload();
        }
    }
    harness.context.FileReader = FakeFileReader;
    harness.fakeWindow.AlmdinaFactoryPermissionsApi = {
        getConsole: () => consoleQueue.call(),
        getRole: () => roleQueue.call(),
        previewRole: () => previewQueue.call(),
        previewImport: () => transferQueue.call(),
        exportRole: () => exportQueue.call(),
        updateRole: () => Promise.resolve({ capabilities: {} }),
    };
    harness.fakeWindow.AlmdinaFactoryPermissionsViewModel = {
        create: () => ({
            roleMenu: () => [],
            permissionGroups: () => [],
            bulkControls: () => ({ groups: [] }),
            impact: () => ({}),
            audit: () => [],
            stats: () => ({ total: 1, enabled: 0, critical: 0, changes: 0 }),
            capabilityKeys: () => ["view"],
            groupCapabilityKeys: () => ["view"],
        }),
    };
    harness.fakeWindow.AlmdinaFactoryPermissionsRenderer = {
        create: () => ({
            renderShell() { renders.shell += 1; },
            renderActor() {},
            renderRoleMenu() {},
            setRolePickerValue() {},
            closeRoleMenu() {},
            showRoleLoading() {},
            showLoaded() { renders.loaded += 1; },
            renderPermissionGroups() {},
            syncCheckboxes() { renders.checkboxSync += 1; },
            syncBulkControls() {},
            renderImpact() {},
            renderAudit() {},
            syncDirtyState() { renders.dirtySync += 1; },
            showEmpty() {},
            downloadJson() { renders.downloads += 1; },
        }),
    };
    harness.fakeWindow.AlmdinaFactoryPermissionsInteractions = {
        bind: options => {
            callbacks = options.callbacks;
            return { dispose() {} };
        },
    };

    evaluate(harness, "factory_permissions/state.js");
    evaluate(harness, "factory_permissions/controller.js");
    harness.fakeWindow.AlmdinaFactoryPermissionsController.mount(harness.wrapper);

    assert.equal(consoleQueue.requests.length, 1);
    assert.equal(renders.shell, 0, "the neutral synchronous bootstrap must remain until fresh console data arrives");
    harness.hide();
    consoleQueue.requests[0].resolve({ roles: [{ name: "Old" }] });
    await flush();
    assert.equal(renders.shell, 0, "stale Permissions console data must not replace the bootstrap surface");
    assert.equal(roleQueue.requests.length, 0);

    harness.show();
    assert.equal(consoleQueue.requests.length, 2);
    consoleQueue.requests[1].resolve({ catalog: [], roles: [{ name: "Role A" }], transfer: {} });
    await flush();
    assert.equal(renders.shell, 1);
    assert.equal(roleQueue.requests.length, 1);

    harness.hide();
    roleQueue.requests[0].resolve({ capabilities: { view: false }, impact: {}, audit: [] });
    await flush();
    assert.equal(renders.loaded, 0, "a stale Permissions role response must not commit after hide");

    harness.show();
    assert.equal(consoleQueue.requests.length, 3);
    consoleQueue.requests[2].resolve({ catalog: [], roles: [{ name: "Role A" }], transfer: {} });
    await flush();
    assert.equal(roleQueue.requests.length, 2);
    roleQueue.requests[1].resolve({ capabilities: { view: false }, impact: {}, audit: [] });
    await flush();
    assert.equal(renders.loaded, 1);

    callbacks.onCapabilityChanged("view", true);
    harness.runTimers();
    assert.equal(previewQueue.requests.length, 1);
    const checkboxBeforePreview = renders.checkboxSync;
    const dirtyBeforePreview = renders.dirtySync;
    harness.hide();
    previewQueue.requests[0].resolve({ capabilities: { view: true }, changes: [{ key: "view" }], impact: {} });
    await flush();
    assert.equal(renders.checkboxSync, checkboxBeforePreview, "stale preview must not apply capabilities");
    assert.equal(renders.dirtySync, dirtyBeforePreview, "stale preview completion must not touch hidden presentation");

    harness.show();
    assert.equal(
        consoleQueue.requests.length,
        3,
        "dirty Permissions state must survive revisit without a console reload"
    );

    callbacks.onImportFile({ size: 10, contents: '{"view":true}' });
    await flush();
    assert.equal(transferQueue.requests.length, 1);
    const checkboxBeforeTransfer = renders.checkboxSync;
    harness.hide();
    transferQueue.requests[0].resolve({ capabilities: { view: true }, changes: [], impact: {} });
    await flush();
    assert.equal(renders.checkboxSync, checkboxBeforeTransfer, "stale transfer/import preview must not commit");

    harness.show();
    callbacks.onExport();
    assert.equal(exportQueue.requests.length, 1);
    harness.hide();
    exportQueue.requests[0].resolve({ role: "Role A" });
    await flush();
    assert.equal(renders.downloads, 0, "stale export completion must not create a download after hide");

    harness.fakeWindow.AlmdinaFactoryPermissionsController.mount(harness.wrapper);
    assert.equal(harness.listenerCount(), 2, "Permissions remount must replace activation listeners instead of duplicating them");
}

async function testWorkforceMutationLifecycle() {
    const harness = createHarness();
    const consoleQueue = endpointQueue();
    const createQueue = endpointQueue();
    const toggleQueue = endpointQueue();
    const renders = { content: 0 };
    const dialogOwners = [];
    let callbacks = null;
    let createConfig = null;
    let toggleConfig = null;

    harness.fakeWindow.AlmdinaFactoryWorkforceApi = {
        getConsole: () => consoleQueue.call(),
        createUser: () => createQueue.call(),
        setEnabled: () => toggleQueue.call(),
        getAudit: () => Promise.resolve({ events: [] }),
    };
    harness.fakeWindow.AlmdinaFactoryWorkforceViewModel = {
        create: () => ({
            page: () => ({}),
            can: () => true,
            actionAllowed: () => true,
            roleOptions: () => [],
            roleHomePolicy: () => ({ hasConflict: false, configured: [] }),
            findUser: (rows, email) => ({ email }),
        }),
    };
    harness.fakeWindow.AlmdinaFactoryWorkforceRenderer = {
        create: () => ({
            renderLoading() {},
            renderError() {},
            render() { renders.content += 1; },
            auditHtml: () => "audit",
        }),
    };
    harness.fakeWindow.AlmdinaFactoryWorkforceInteractions = {
        bind: options => { callbacks = options.callbacks; return true; },
    };
    harness.fakeWindow.AlmdinaFactoryWorkforceDialogs = {
        create: () => {
            const owner = { deactivations: 0, disposals: 0 };
            dialogOwners.push(owner);
            return {
                openCreate(config) { createConfig = config; },
                confirmToggle(config) { toggleConfig = config; },
                showAlert(message) { harness.frappe.show_alert({ message }); },
                deactivate() { owner.deactivations += 1; },
                dispose() { owner.disposals += 1; },
            };
        },
    };

    evaluate(harness, "factory_workforce/state.js");
    evaluate(harness, "factory_workforce/controller.js");
    const controller = harness.fakeWindow.AlmdinaFactoryWorkforceController.mount(harness.wrapper);
    consoleQueue.requests[0].resolve({ users: [{ email: "worker@example.com" }], permissions: {} });
    await flush();
    assert.equal(renders.content, 1);

    harness.primaryAction().callback();
    const createMutation = createConfig.onSubmit({ email: "new@example.com" });
    await flush();
    assert.equal(createQueue.requests.length, 1);
    harness.hide();
    assert.equal(dialogOwners[0].deactivations, 1, "Workforce hide must close its transient children");
    assert.equal(dialogOwners[0].disposals, 0, "Workforce hide must not dispose the mounted owner");
    createQueue.requests[0].resolve({ ok: true });
    await createMutation;
    await flush();
    assert.equal(harness.alerts.length, 0, "hidden Workforce create completion must not show success UI");
    assert.equal(renders.content, 1, "hidden Workforce create completion must not render");
    assert.equal(consoleQueue.requests.length, 1, "hidden mutation completion must wait for revisit reconciliation");

    harness.show();
    assert.equal(consoleQueue.requests.length, 2);
    consoleQueue.requests[1].resolve({ users: [{ email: "new@example.com" }], permissions: {} });
    await flush();
    assert.equal(renders.content, 2, "Workforce revisit must reconcile once from fresh server state");
    await createConfig.onSubmit({ email: "stale-dialog@example.com" });
    assert.equal(createQueue.requests.length, 1, "a child surface from an older visit cannot start another mutation");

    callbacks.onToggle("new@example.com", false);
    const toggleMutation = toggleConfig.onConfirm();
    await flush();
    assert.equal(toggleQueue.requests.length, 1);
    harness.hide();
    harness.show();
    assert.equal(consoleQueue.requests.length, 3, "revisit may start while the prior mutation is still pending");
    toggleQueue.requests[0].resolve({ ok: true });
    await flush();
    assert.equal(consoleQueue.requests.length, 4, "a mutation completing in a newer visit must start post-mutation reconciliation");
    consoleQueue.requests[2].resolve({ users: [{ email: "new@example.com", enabled: true }], permissions: {} });
    consoleQueue.requests[3].resolve({ users: [{ email: "new@example.com", enabled: false }], permissions: {} });
    await toggleMutation;
    await flush();
    assert.equal(harness.alerts.length, 0, "hidden Workforce enable/disable completion must not show success UI");
    assert.equal(renders.content, 3, "only the post-mutation reconciliation may render in the newer visit");

    harness.fakeWindow.AlmdinaFactoryWorkforceController.mount(harness.wrapper);
    assert.equal(dialogOwners[0].disposals, 1, "Workforce remount must dispose the prior dialog owner");
    assert.equal(harness.listenerCount(), 2, "Workforce remount must retain one activation owner");
    controller.dispose();
}

async function testProductionSettingsMutationLifecycle() {
    const harness = createHarness();
    const settingsQueue = endpointQueue();
    const updateQueue = endpointQueue();
    const auditQueue = endpointQueue();
    const renders = { content: 0, audit: 0 };
    const dialogOwners = [];
    let callbacks = null;
    let sectionConfig = null;

    harness.fakeWindow.AlmdinaFactoryProductionSettingsApi = {
        getSettings: () => settingsQueue.call(),
        updateSettings: () => updateQueue.call(),
        getAudit: () => auditQueue.call(),
    };
    harness.fakeWindow.AlmdinaFactoryProductionSettingsViewModel = {
        create: () => ({ page: () => ({}), sectionEditable: () => true }),
    };
    harness.fakeWindow.AlmdinaFactoryProductionSettingsRenderer = {
        create: () => ({
            renderLoading() {},
            renderError() {},
            render() { renders.content += 1; },
            auditLoadingHtml: () => "loading",
            auditHtml: () => "audit",
            auditErrorHtml: () => "error",
        }),
    };
    harness.fakeWindow.AlmdinaFactoryProductionSettingsInteractions = {
        bind: options => { callbacks = options.callbacks; return true; },
    };
    harness.fakeWindow.AlmdinaFactoryProductionSettingsDialogs = {
        create: () => {
            const owner = { deactivations: 0, disposals: 0 };
            dialogOwners.push(owner);
            return {
                openSection(config) { sectionConfig = config; },
                openAudit() { return { setHtml() { renders.audit += 1; } }; },
                showSaved() { harness.frappe.show_alert({ message: "saved" }); },
                deactivate() { owner.deactivations += 1; },
                dispose() { owner.disposals += 1; },
            };
        },
    };

    evaluate(harness, "factory_production_settings/state.js");
    evaluate(harness, "factory_production_settings/controller.js");
    harness.fakeWindow.AlmdinaFactoryProductionSettingsController.mount(harness.wrapper);
    settingsQueue.requests[0].resolve({ values: { default_kerf_mm: 3 } });
    await flush();
    assert.equal(renders.content, 1);

    callbacks.onEditSection("cutting");
    const updateMutation = sectionConfig.onSubmit({ default_kerf_mm: 4 });
    harness.hide();
    assert.equal(dialogOwners[0].deactivations, 1);
    assert.equal(dialogOwners[0].disposals, 0, "Production Settings hide must not dispose the controller");
    updateQueue.requests[0].resolve({ values: { default_kerf_mm: 4 } });
    await updateMutation;
    await flush();
    assert.equal(harness.alerts.length, 0, "hidden settings mutation must not show saved UI");
    assert.equal(renders.content, 1, "hidden settings mutation must not render its response");

    harness.show();
    assert.equal(settingsQueue.requests.length, 2);
    settingsQueue.requests[1].resolve({ values: { default_kerf_mm: 4 } });
    await flush();
    assert.equal(renders.content, 2, "Production Settings revisit must render one fresh server snapshot");

    callbacks.onEditSection("cutting");
    const supersededMutation = sectionConfig.onSubmit({ default_kerf_mm: 5 });
    harness.hide();
    harness.show();
    assert.equal(settingsQueue.requests.length, 3);
    updateQueue.requests[1].resolve({ values: { default_kerf_mm: 5 } });
    await flush();
    assert.equal(settingsQueue.requests.length, 4, "a Settings mutation from an older visit must reconcile after it completes");
    settingsQueue.requests[2].resolve({ values: { default_kerf_mm: 4 } });
    settingsQueue.requests[3].resolve({ values: { default_kerf_mm: 5 } });
    await supersededMutation;
    await flush();
    assert.equal(harness.alerts.length, 0, "a superseded Settings mutation must not show success UI in the newer visit");
    assert.equal(renders.content, 3, "only the post-mutation Settings reconciliation may render");

    harness.innerButtons[0].callback();
    harness.hide();
    auditQueue.requests[0].resolve([{ action: "stale" }]);
    await flush();
    assert.equal(renders.audit, 0, "hidden audit completion cannot update a stale child surface");

    harness.show();
    harness.fakeWindow.AlmdinaFactoryProductionSettingsController.mount(harness.wrapper);
    assert.equal(dialogOwners[0].disposals, 1, "Production Settings remount must replace the old dialog owner");
    assert.equal(harness.listenerCount(), 2, "Production Settings remount must retain one activation owner");
}

async function testPermissionsMutationLifecycle() {
    const harness = createHarness();
    const consoleQueue = endpointQueue();
    const roleQueue = endpointQueue();
    const previewQueue = endpointQueue();
    const updateQueue = endpointQueue();
    const renders = { permissionState: 0, dirty: 0 };
    let callbacks = null;
    let runtimeRefreshes = 0;

    harness.fakeWindow.AlmdinaPermissions = {
        refresh() { runtimeRefreshes += 1; return Promise.resolve(); },
    };
    harness.fakeWindow.AlmdinaFactoryPermissionsApi = {
        getConsole: () => consoleQueue.call(),
        getRole: () => roleQueue.call(),
        previewRole: () => previewQueue.call(),
        previewImport: () => Promise.resolve({}),
        exportRole: () => Promise.resolve({}),
        updateRole: () => updateQueue.call(),
    };
    harness.fakeWindow.AlmdinaFactoryPermissionsViewModel = {
        create: () => ({
            roleMenu: () => [],
            permissionGroups: () => [],
            bulkControls: () => ({ groups: [] }),
            impact: () => ({}),
            audit: () => [],
            stats: () => ({ total: 1, enabled: 1, critical: 0, changes: 1 }),
            capabilityKeys: () => ["view"],
            groupCapabilityKeys: () => ["view"],
        }),
    };
    harness.fakeWindow.AlmdinaFactoryPermissionsRenderer = {
        create: () => ({
            renderShell() {},
            renderActor() {},
            renderRoleMenu() {},
            setRolePickerValue() {},
            closeRoleMenu() {},
            showRoleLoading() {},
            showLoaded() {},
            renderPermissionGroups() { renders.permissionState += 1; },
            syncCheckboxes() {},
            syncBulkControls() {},
            renderImpact() {},
            renderAudit() {},
            syncDirtyState() { renders.dirty += 1; },
            showEmpty() {},
            downloadJson() {},
        }),
    };
    harness.fakeWindow.AlmdinaFactoryPermissionsInteractions = {
        bind: options => {
            callbacks = options.callbacks;
            return { dispose() {} };
        },
    };

    evaluate(harness, "factory_permissions/state.js");
    evaluate(harness, "factory_permissions/controller.js");
    harness.fakeWindow.AlmdinaFactoryPermissionsController.mount(harness.wrapper);
    consoleQueue.requests[0].resolve({ catalog: [], roles: [{ name: "Role A" }], transfer: {} });
    await flush();
    roleQueue.requests[0].resolve({ capabilities: { view: false }, impact: {}, audit: [] });
    await flush();
    assert.equal(renders.permissionState, 1);

    callbacks.onCapabilityChanged("view", true);
    harness.runTimers();
    previewQueue.requests[0].resolve({ capabilities: { view: true }, changes: [{ key: "view" }], impact: {} });
    await flush();

    const saveFlow = callbacks.onSave();
    assert.equal(previewQueue.requests.length, 2, "save must validate the current preview before mutation");
    previewQueue.requests[1].resolve({ capabilities: { view: true }, changes: [{ key: "view" }], impact: {} });
    await flush();
    assert.equal(updateQueue.requests.length, 1);
    const rendersBeforeHiddenSave = renders.permissionState;
    harness.hide();
    updateQueue.requests[0].resolve({ capabilities: { view: true }, impact: {}, audit: [] });
    assert.equal(await saveFlow, true, "the server mutation remains semantically successful while hidden");
    await flush();
    assert.equal(runtimeRefreshes, 1, "global permission state still refreshes after a successful mutation");
    assert.equal(harness.alerts.length, 0, "hidden Permissions save must not show success UI");
    assert.equal(renders.permissionState, rendersBeforeHiddenSave, "hidden save response must not become working UI");

    harness.show();
    assert.equal(consoleQueue.requests.length, 2, "hidden save success must force fresh reconciliation despite old dirty state");
    consoleQueue.requests[1].resolve({ catalog: [], roles: [{ name: "Role A" }], transfer: {} });
    await flush();
    assert.equal(roleQueue.requests.length, 2);
    roleQueue.requests[1].resolve({ capabilities: { view: true }, impact: {}, audit: [] });
    await flush();
    assert.equal(renders.permissionState, rendersBeforeHiddenSave + 1, "fresh role state must render once after revisit");

    callbacks.onCapabilityChanged("view", false);
    harness.runTimers();
    previewQueue.requests[2].resolve({
        capabilities: { view: false },
        changes: [{ key: "view" }],
        impact: {},
        requires_self_lockout_confirmation: true,
    });
    await flush();
    const confirmationFlow = callbacks.onSave();
    previewQueue.requests[3].resolve({
        capabilities: { view: false },
        changes: [{ key: "view" }],
        impact: {},
        requires_self_lockout_confirmation: true,
    });
    await confirmationFlow;
    assert.equal(harness.confirms.length, 1);
    harness.hide();
    assert.equal(harness.confirms[0].surface.hidden, 1, "Permissions hide must close the owned confirmation");
    harness.confirms[0].yes();
    await flush();
    assert.equal(updateQueue.requests.length, 1, "a confirmation callback from an old visit cannot start a save");

    harness.show();
    assert.equal(consoleQueue.requests.length, 2, "dirty unsaved Permissions state must still survive a normal revisit");
    harness.fakeWindow.AlmdinaFactoryPermissionsController.mount(harness.wrapper);
    assert.equal(harness.listenerCount(), 2, "Permissions remount must retain exactly one activation owner");
}

async function testDialogModulesOwnTransientSurfaces() {
    const surfaces = [];
    const messages = [];
    let buttonWrites = 0;

    class FakeDialog {
        constructor(config) {
            this.config = config;
            this.hidden = 0;
            this.values = {};
            this.restoredValues = [];
            this.fields_dict = {
                audit: { $wrapper: { html() {} } },
                audit_html: { $wrapper: { html() {} } },
            };
            surfaces.push(this);
        }
        show() {}
        hide() { this.hidden += 1; }
        get_values() { return { ...this.values }; }
        set_values(values) {
            this.values = { ...(values || {}) };
            this.restoredValues.push({ ...this.values });
        }
        get_primary_btn() {
            return { prop() { buttonWrites += 1; } };
        }
    }

    const frappe = {
        ui: { Dialog: FakeDialog },
        confirm() {
            const surface = { hidden: 0, hide() { this.hidden += 1; } };
            surfaces.push(surface);
            return surface;
        },
        msgprint(payload) {
            messages.push(payload);
            const surface = { hidden: 0, hide() { this.hidden += 1; } };
            surfaces.push(surface);
            return surface;
        },
        show_alert() {},
    };
    const fakeWindow = { frappe };
    const context = vm.createContext({
        window: fakeWindow,
        frappe,
        console,
        Promise,
        Object,
        Array,
        Set,
        String,
        Error,
    });

    vm.runInContext(source("factory_workforce/dialogs.js"), context, { filename: "factory_workforce/dialogs.js" });
    const workforceMutation = deferred();
    const workforce = fakeWindow.AlmdinaFactoryWorkforceDialogs.create({ translate: value => value });
    const createDialog = workforce.openCreate({
        canAssignRoles: false,
        roleOptions: () => [],
        onSubmit: () => workforceMutation.promise,
    });
    workforce.confirmToggle({ user: { email: "worker@example.com" }, enabled: false });
    workforce.openAudit({ user: { email: "worker@example.com" }, html: "audit" });
    const workforceCompletion = createDialog.config.primary_action({ email: "worker@example.com" });
    workforce.deactivate();
    workforceMutation.resolve({ ok: true });
    await workforceCompletion;
    assert.equal(createDialog.hidden, 1, "stale Workforce dialog completion must not touch an already deactivated child");

    const workforceDraft = workforce.openCreate({ canAssignRoles: false, roleOptions: () => [] });
    workforceDraft.values = { email: "draft@example.com", first_name: "Draft" };
    workforce.deactivate();
    const resumedWorkforceDraft = workforce.openCreate({ canAssignRoles: false, roleOptions: () => [] });
    assert.equal(resumedWorkforceDraft.values.email, "draft@example.com", "Workforce revisit must restore unsent dialog input");
    assert.equal(resumedWorkforceDraft.values.first_name, "Draft");
    workforce.deactivate();

    vm.runInContext(source("factory_production_settings/dialogs.js"), context, { filename: "factory_production_settings/dialogs.js" });
    const settingsMutation = deferred();
    const settings = fakeWindow.AlmdinaFactoryProductionSettingsDialogs.create({
        translate: value => value,
        escapeHtml: value => String(value || ""),
    });
    const settingsDialog = settings.openSection({
        section: "production",
        current: { values: {} },
        onSubmit: () => settingsMutation.promise,
    });
    settings.openAudit("loading");
    settingsDialog.config.primary_action({});
    assert.equal(buttonWrites, 1, "active submit may disable its owned action once");
    settings.deactivate();
    settingsMutation.resolve({ ok: true });
    await flush();
    assert.equal(settingsDialog.hidden, 1, "stale Settings completion must not hide the child a second time");
    assert.equal(buttonWrites, 1, "stale Settings completion must not mutate hidden dialog controls");
    assert.equal(messages.length, 0, "deactivated child completions must not open error surfaces");

    const settingsDraft = settings.openSection({ section: "production", current: { values: {} } });
    settingsDraft.values = { default_production_routing: "Draft Route", allow_stage_override: 1 };
    settings.deactivate();
    const resumedSettingsDraft = settings.openSection({ section: "production", current: { values: {} } });
    assert.equal(resumedSettingsDraft.values.default_production_routing, "Draft Route", "Settings revisit must restore unsent section input");
    assert.equal(resumedSettingsDraft.values.allow_stage_override, 1);
}

(async () => {
    await testWorkforceLifecycle();
    await testProductionSettingsLifecycle();
    await testPermissionsLifecycle();
    await testWorkforceMutationLifecycle();
    await testProductionSettingsMutationLifecycle();
    await testPermissionsMutationLifecycle();
    await testDialogModulesOwnTransientSurfaces();
    console.log("Admin Frappe PAGE lifecycle simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
