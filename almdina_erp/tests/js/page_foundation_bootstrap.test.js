"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";
const PAGE_LIFECYCLE = "/assets/almdina_erp/js/page_revisit_refresh.js";

const SPECS = Object.freeze([
    {
        route: "factory-permissions",
        source: "factory_permissions/factory_permissions.js",
        controller: "AlmdinaFactoryPermissionsController",
        stylesheet: "/assets/almdina_erp/css/factory_permissions.css",
        loadingMarker: "جاري تحميل مصفوفة الصلاحيات",
    },
    {
        route: "factory-workforce",
        source: "factory_workforce/factory_workforce.js",
        controller: "AlmdinaFactoryWorkforceController",
        stylesheet: "/assets/almdina_erp/css/factory_workforce.css",
        loadingMarker: "جاري تحميل مستخدمي المعمل",
    },
    {
        route: "factory-production-settings",
        source: "factory_production_settings/factory_production_settings.js",
        controller: "AlmdinaFactoryProductionSettingsController",
        stylesheet: "/assets/almdina_erp/css/factory_production_settings.css",
        loadingMarker: "جاري تحميل إعدادات المعمل",
    },
    {
        route: "shop-floor-inbox",
        source: "shop_floor_inbox/shop_floor_inbox.js",
        controller: "AlmdinaShopFloorInboxController",
        stylesheet: "/assets/almdina_erp/css/shop_floor_responsive.css",
        loadingMarker: "جاري تجهيز صالة الإنتاج",
    },
]);

function pageSource(spec) {
    return fs.readFileSync(
        path.resolve(__dirname, "../../almdina_erp/page", spec.source),
        "utf8"
    );
}

function deferred() {
    let resolve;
    const promise = new Promise(resolvePromise => { resolve = resolvePromise; });
    return { promise, resolve };
}

async function simulate(spec, { foundationReady = false, legacyLoader = false } = {}) {
    const requireCalls = [];
    const moduleGroups = [];
    const stylesheetCalls = [];
    const mounts = [];
    const pageShells = [];
    const alerts = [];
    const wrapper = { route: spec.route };
    const main = {
        content: "",
        html(value) {
            this.content = String(value || "");
            return this;
        },
    };
    const fakeWindow = {};
    const pageLifecycle = {
        bindActivationLifecycle() {
            return { isActive: () => true, dispose() {} };
        },
    };

    function installController() {
        fakeWindow[spec.controller] = {
            mount(receivedWrapper) {
                mounts.push(receivedWrapper);
                return { mounted: true };
            },
        };
    }

    const foundation = {
        errorMessage(error, fallback) {
            return error && error.message ? error.message : fallback;
        },
        ensureStylesheet(href, options) {
            stylesheetCalls.push({ href, options });
            return Promise.resolve({ href });
        },
    };

    if (!legacyLoader) {
        foundation.requireAssets = items => {
            moduleGroups.push(Array.from(items || []));
            installController();
            return Promise.resolve(items);
        };
    }

    if (foundationReady) {
        fakeWindow.AlmdinaFrontend = foundation;
        fakeWindow.AlmdinaPageRevisit = pageLifecycle;
    }

    const frappe = {
        pages: {
            [spec.route]: {},
        },
        require(assets) {
            const recorded = Array.isArray(assets) ? Array.from(assets) : assets;
            requireCalls.push(recorded);

            const batch = Array.isArray(assets) ? assets : [assets];
            if (batch.includes(FOUNDATION)) {
                fakeWindow.AlmdinaFrontend = foundation;
            }
            if (batch.includes(PAGE_LIFECYCLE)) fakeWindow.AlmdinaPageRevisit = pageLifecycle;

            if (batch.some(asset => String(asset).includes(`/${spec.route.replace(/-/g, "_")}/`))) {
                installController();
            }
            return Promise.resolve(assets);
        },
        ui: {
            make_app_page(options) {
                pageShells.push(options);
                wrapper.page = { parent: wrapper };
                return wrapper.page;
            },
        },
        utils: {
            escape_html(value) {
                return String(value || "");
            },
        },
        show_alert(payload) {
            alerts.push(payload);
        },
    };

    const context = vm.createContext({
        window: fakeWindow,
        frappe,
        $() {
            return {
                find() {
                    return main;
                },
            };
        },
        __(value) {
            return value;
        },
        console,
        Promise,
        Object,
        Array,
        String,
        Error,
    });

    vm.runInContext(pageSource(spec), context, { filename: spec.source });
    const result = frappe.pages[spec.route].on_page_load(wrapper);
    assert.equal(pageShells.length, 1, `${spec.route}: Frappe page shell must be synchronous`);
    assert.equal(mounts.length, 0, `${spec.route}: controller must wait for async dependencies`);
    assert.ok(main.content.includes(spec.loadingMarker), `${spec.route}: loading surface must exist before awaiting bootstrap`);
    await Promise.resolve(result);

    return {
        alerts,
        fakeWindow,
        main,
        moduleGroups,
        mounts,
        pageShells,
        requireCalls,
        stylesheetCalls,
        wrapper,
    };
}

async function simulateShowHideWhileAssetsArePending(spec) {
    const featureAssets = deferred();
    const events = new Map();
    const wrapper = { route: spec.route };
    const otherPage = {};
    const main = {
        content: "",
        html(value) { this.content = String(value || ""); return this; },
    };
    const mounts = [];
    let refreshes = 0;

    function trigger(eventName) {
        const callback = events.get(eventName);
        if (callback) callback();
    }

    const frappe = {
        pages: { [spec.route]: {} },
        container: { page: null },
        require() {
            throw new Error("warm core must not use the native loader");
        },
        ui: {
            make_app_page(options) {
                wrapper.page = { parent: options.parent };
                return wrapper.page;
            },
        },
        utils: { escape_html: value => String(value || "") },
        show_alert() {},
    };
    const pageLifecycle = {
        bindActivationLifecycle(receivedWrapper, callbacks) {
            let active = frappe.container.page === receivedWrapper;
            events.set("show", () => {
                if (active) return;
                active = true;
                callbacks.onActivate();
            });
            events.set("hide", () => {
                if (!active) return;
                active = false;
                if (callbacks.onDeactivate) callbacks.onDeactivate();
            });
            return { isActive: () => active, dispose() {} };
        },
    };
    const fakeWindow = {
        AlmdinaPageRevisit: pageLifecycle,
        AlmdinaFrontend: {
            errorMessage(error, fallback) { return error && error.message ? error.message : fallback; },
            requireAssets() { return featureAssets.promise; },
            ensureStylesheet() { return Promise.resolve({}); },
        },
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe,
        $() { return { find: () => main }; },
        __(value) { return value; },
        console,
        Promise,
        Object,
        Array,
        String,
        Error,
    });

    vm.runInContext(pageSource(spec), context, { filename: spec.source });
    const bootstrap = frappe.pages[spec.route].on_page_load(wrapper);

    assert.ok(main.content.includes(spec.loadingMarker));
    assert.equal(mounts.length, 0);

    // Reproduce Frappe v16 exactly: it does not await on_page_load before show.
    frappe.container.page = wrapper;
    wrapper._route = spec.route;
    trigger("show");
    frappe.container.page = otherPage;
    trigger("hide");

    fakeWindow[spec.controller] = {
        mount(receivedWrapper) {
            mounts.push(receivedWrapper);
            const lifecycle = pageLifecycle.bindActivationLifecycle(receivedWrapper, {
                onActivate() { refreshes += 1; },
            });
            if (lifecycle.isActive()) refreshes += 1;
            return lifecycle;
        },
    };
    featureAssets.resolve([]);
    await bootstrap;

    assert.equal(mounts.length, 1, `${spec.route}: delayed assets must still mount one controller`);
    assert.equal(refreshes, 0, `${spec.route}: mounting while hidden must not start an inactive read`);

    frappe.container.page = wrapper;
    trigger("show");
    assert.equal(refreshes, 1, `${spec.route}: the next show must perform one fresh refresh`);
}

(async () => {
    for (const spec of SPECS) {
        const cold = await simulate(spec);
        assert.equal(cold.alerts.length, 0, `${spec.route}: cold bootstrap must not render an error`);
        assert.equal(cold.requireCalls.length, 1, `${spec.route}: cold bootstrap should load one core batch natively`);
        assert.deepEqual(
            cold.requireCalls[0],
            [FOUNDATION, PAGE_LIFECYCLE],
            `${spec.route}: cold bootstrap must request both deterministic core dependencies`
        );
        assert.equal(typeof cold.fakeWindow.AlmdinaFrontend, "object");
        assert.equal(typeof cold.fakeWindow.AlmdinaPageRevisit.bindActivationLifecycle, "function");
        assert.equal(cold.moduleGroups.length, 1, `${spec.route}: feature modules should remain one batched group`);
        assert.equal(cold.mounts.length, 1, `${spec.route}: controller must mount exactly once after cold bootstrap`);
        assert.equal(cold.mounts[0], cold.wrapper);
        assert.equal(cold.stylesheetCalls.length, 1);
        assert.equal(cold.stylesheetCalls[0].href, spec.stylesheet);

        const warm = await simulate(spec, { foundationReady: true });
        assert.equal(warm.alerts.length, 0, `${spec.route}: warm bootstrap must stay healthy`);
        assert.equal(warm.requireCalls.length, 0, `${spec.route}: an already-ready foundation must not be re-requested`);
        assert.equal(warm.moduleGroups.length, 1);
        assert.equal(warm.mounts.length, 1, `${spec.route}: warm controller mount must remain singular`);

        const legacy = await simulate(spec, { foundationReady: true, legacyLoader: true });
        assert.equal(legacy.alerts.length, 0, `${spec.route}: compatibility loader must stay healthy`);
        assert.equal(legacy.moduleGroups.length, 0, `${spec.route}: legacy foundation has no shared requireAssets helper`);
        assert.equal(legacy.requireCalls.length, 1, `${spec.route}: legacy foundation must fall back to one native feature batch`);
        assert.ok(Array.isArray(legacy.requireCalls[0]), `${spec.route}: compatibility fallback must batch feature assets`);
        assert.equal(legacy.mounts.length, 1, `${spec.route}: compatibility controller mount must remain singular`);

        await simulateShowHideWhileAssetsArePending(spec);
    }

    console.log("Page foundation cold/warm bootstrap regression simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
