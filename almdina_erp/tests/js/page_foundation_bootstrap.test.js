"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const FOUNDATION = "/assets/almdina_erp/js/frontend_foundation.js";

const SPECS = Object.freeze([
    {
        route: "factory-permissions",
        source: "factory_permissions/factory_permissions.js",
        controller: "AlmdinaFactoryPermissionsController",
        stylesheet: "/assets/almdina_erp/css/factory_permissions.css",
    },
    {
        route: "factory-workforce",
        source: "factory_workforce/factory_workforce.js",
        controller: "AlmdinaFactoryWorkforceController",
        stylesheet: "/assets/almdina_erp/css/factory_workforce.css",
    },
    {
        route: "factory-production-settings",
        source: "factory_production_settings/factory_production_settings.js",
        controller: "AlmdinaFactoryProductionSettingsController",
        stylesheet: "/assets/almdina_erp/css/factory_production_settings.css",
    },
]);

function pageSource(spec) {
    return fs.readFileSync(
        path.resolve(__dirname, "../../almdina_erp/page", spec.source),
        "utf8"
    );
}

async function simulate(spec, { foundationReady = false, legacyLoader = false } = {}) {
    const requireCalls = [];
    const moduleGroups = [];
    const stylesheetCalls = [];
    const mounts = [];
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

    if (foundationReady) fakeWindow.AlmdinaFrontend = foundation;

    const frappe = {
        pages: {
            [spec.route]: {},
        },
        require(assets) {
            const recorded = Array.isArray(assets) ? Array.from(assets) : assets;
            requireCalls.push(recorded);

            if (assets === FOUNDATION) {
                fakeWindow.AlmdinaFrontend = foundation;
                return Promise.resolve([FOUNDATION]);
            }

            if (Array.isArray(assets)) installController();
            return Promise.resolve(assets);
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
    await Promise.resolve(result);

    return {
        alerts,
        fakeWindow,
        main,
        moduleGroups,
        mounts,
        requireCalls,
        stylesheetCalls,
        wrapper,
    };
}

(async () => {
    for (const spec of SPECS) {
        const cold = await simulate(spec);
        assert.equal(cold.alerts.length, 0, `${spec.route}: cold bootstrap must not render an error`);
        assert.equal(cold.requireCalls.length, 1, `${spec.route}: cold bootstrap should load only the missing foundation natively`);
        assert.equal(cold.requireCalls[0], FOUNDATION, `${spec.route}: cold bootstrap must request the shared foundation`);
        assert.equal(typeof cold.fakeWindow.AlmdinaFrontend, "object");
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
    }

    console.log("Page foundation cold/warm bootstrap regression simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
