"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const DESIGN_SYSTEM_MODULE = "/assets/almdina_erp/js/almdina_ui.js";

const cases = [
    {
        file: "../../almdina_erp/page/factory_workforce/factory_workforce.js",
        page: "factory-workforce",
        controller: "AlmdinaFactoryWorkforceController",
        featureModuleCount: 8,
        modulePrefix: "/assets/almdina_erp/js/factory_workforce/",
        sharedModules: [DESIGN_SYSTEM_MODULE],
    },
    {
        file: "../../almdina_erp/page/factory_permissions/factory_permissions.js",
        page: "factory-permissions",
        controller: "AlmdinaFactoryPermissionsController",
        featureModuleCount: 7,
        modulePrefix: "/assets/almdina_erp/js/factory_permissions/",
        sharedModules: [DESIGN_SYSTEM_MODULE],
    },
    {
        file: "../../almdina_erp/page/factory_production_settings/factory_production_settings.js",
        page: "factory-production-settings",
        controller: "AlmdinaFactoryProductionSettingsController",
        featureModuleCount: 7,
        modulePrefix: "/assets/almdina_erp/js/factory_production_settings/",
        sharedModules: [DESIGN_SYSTEM_MODULE],
    },
];

async function flushPromises() {
    await Promise.resolve();
    await new Promise(resolve => setImmediate(resolve));
}

async function simulateCachedFoundation(config) {
    const source = fs.readFileSync(path.resolve(__dirname, config.file), "utf8");
    const requireCalls = [];
    let mountCount = 0;
    let alertCount = 0;
    let renderedError = "";

    // This deliberately represents the deploy-skew state that caused the
    // production regression: the previous foundation is already cached and has
    // the long-lived helpers, but it predates requireAssets().
    const cachedFoundation = {
        errorMessage(error, fallback) {
            return error && error.message ? error.message : fallback;
        },
        ensureStylesheet() {
            return Promise.resolve({});
        },
    };

    const frappe = {
        pages: { [config.page]: {} },
        require(items) {
            requireCalls.push(items);
            return Promise.resolve();
        },
        utils: {
            escape_html(value) {
                return String(value);
            },
        },
        show_alert() {
            alertCount += 1;
        },
        ui: {
            make_app_page(options) {
                options.parent.page = { parent: options.parent };
                return options.parent.page;
            },
        },
    };

    const windowObject = {
        AlmdinaFrontend: cachedFoundation,
        AlmdinaPageRevisit: {
            bindActivationLifecycle() {
                return { isActive: () => true, dispose() {} };
            },
        },
        [config.controller]: {
            mount() {
                mountCount += 1;
            },
        },
    };

    const mainSection = {
        html(value) {
            renderedError = String(value || "");
        },
    };

    const context = vm.createContext({
        window: windowObject,
        frappe,
        $() {
            return {
                find() {
                    return mainSection;
                },
            };
        },
        __(value) {
            return value;
        },
        Promise,
        Object,
        String,
        Error,
        console,
    });

    vm.runInContext(source, context, { filename: path.basename(config.file) });
    frappe.pages[config.page].on_page_load({});
    await flushPromises();

    assert.equal(alertCount, 0, `${config.page} must not alert on cached-foundation deploy skew`);
    assert.equal(
        renderedError.includes("تعذر تحميل"),
        false,
        `${config.page} must not render a bootstrap error`
    );
    assert.equal(mountCount, 1, `${config.page} controller must mount once`);
    assert.equal(requireCalls.length, 1, `${config.page} must issue exactly one native fallback require`);

    const batch = requireCalls[0];
    assert.ok(Array.isArray(batch), `${config.page} fallback must be a batch array`);
    assert.equal(
        batch.length,
        config.featureModuleCount + config.sharedModules.length,
        `${config.page} must load the full approved module batch`
    );

    const approvedSharedModules = new Set(config.sharedModules);
    for (const sharedModule of approvedSharedModules) {
        assert.equal(
            batch.filter(asset => String(asset) === sharedModule).length,
            1,
            `${config.page} must load shared prerequisite ${sharedModule} exactly once`
        );
    }

    const featureModules = batch.filter(asset => !approvedSharedModules.has(String(asset)));
    assert.equal(
        featureModules.length,
        config.featureModuleCount,
        `${config.page} must load every owned feature module`
    );
    assert.ok(
        featureModules.every(asset => String(asset).startsWith(config.modulePrefix)),
        `${config.page} fallback feature modules must stay within their owned prefix`
    );
    assert.ok(
        batch.every(
            asset => approvedSharedModules.has(String(asset)) || String(asset).startsWith(config.modulePrefix)
        ),
        `${config.page} fallback may contain only approved shared prerequisites and owned feature modules`
    );
}

(async () => {
    for (const config of cases) {
        await simulateCachedFoundation(config);
    }
    console.log("Modular pages tolerate a cached pre-requireAssets frontend foundation");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
