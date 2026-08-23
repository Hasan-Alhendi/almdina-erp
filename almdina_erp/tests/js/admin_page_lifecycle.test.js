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
    const wrapper = {
        page: {
            btn_primary: { toggle() {} },
            clear_inner_toolbar() { innerButtons.length = 0; },
            set_primary_action() {},
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

    function createDialogOwner() {
        const owned = new Set();
        return {
            track(dialog) { if (dialog && typeof dialog.hide === "function") owned.add(dialog); return dialog; },
            closeAll() { owned.forEach(dialog => dialog.hide()); owned.clear(); },
        };
    }

    const frappe = {
        container: { page: wrapper },
        ui: {
            make_app_page() {
                throw new Error("Controllers must reuse the synchronous page shell");
            },
        },
        utils: { escape_html: value => String(value || "") },
        show_alert() {},
        msgprint() {},
        confirm(message, yes) { if (yes) yes(); },
    };
    const fakeWindow = {
        frappe,
        jQuery: jquery,
        AlmdinaFrontend: {
            createLatestRequestGate,
            createLifecycleScope,
            createDialogOwner,
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
        fakeWindow,
        frappe,
        innerButtons,
        main,
        timers,
        wrapper,
        listenerCount: () => wrapperEvents.size,
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
        create: () => ({ openAudit() { renders.audit += 1; } }),
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
    const renders = { shell: 0, loaded: 0, checkboxSync: 0, dirtySync: 0 };
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
        exportRole: () => Promise.resolve({}),
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

    harness.fakeWindow.AlmdinaFactoryPermissionsController.mount(harness.wrapper);
    assert.equal(harness.listenerCount(), 2, "Permissions remount must replace activation listeners instead of duplicating them");
}

(async () => {
    await testWorkforceLifecycle();
    await testProductionSettingsLifecycle();
    await testPermissionsLifecycle();
    console.log("Admin Frappe page read lifecycle simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
