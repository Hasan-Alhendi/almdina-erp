"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const cases = [
    {
        file: "../../almdina_erp/page/factory_workforce/factory_workforce.js",
        page: "factory-workforce",
        controller: "AlmdinaFactoryWorkforceController",
        moduleCount: 7,
        modulePrefix: "/assets/almdina_erp/js/factory_workforce/",
    },
    {
        file: "../../almdina_erp/page/factory_permissions/factory_permissions.js",
        page: "factory-permissions",
        controller: "AlmdinaFactoryPermissionsController",
        moduleCount: 6,
        modulePrefix: "/assets/almdina_erp/js/factory_permissions/",
    },
    {
        file: "../../almdina_erp/page/factory_production_settings/factory_production_settings.js",
        page: "factory-production-settings",
        controller: "AlmdinaFactoryProductionSettingsController",
        moduleCount: 7,
        modulePrefix: "/assets/almdina_erp/js/factory_production_settings/",
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
    };

    const windowObject = {
        AlmdinaFrontend: cachedFoundation,
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
    assert.equal(renderedError, "", `${config.page} must not render a bootstrap error`);
    assert.equal(mountCount, 1, `${config.page} controller must mount once`);
    assert.equal(requireCalls.length, 1, `${config.page} must issue exactly one native fallback require`);
    assert.ok(Array.isArray(requireCalls[0]), `${config.page} fallback must be a batch array`);
    assert.equal(requireCalls[0].length, config.moduleCount, `${config.page} must load the full module batch`);
    assert.ok(
        requireCalls[0].every(asset => String(asset).startsWith(config.modulePrefix)),
        `${config.page} fallback must contain only its owned feature modules`
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
