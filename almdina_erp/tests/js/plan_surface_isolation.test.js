"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order_plan_surface_bootstrap.js"),
    "utf8"
);

function htmlWrapper(initial = "") {
    return {
        content: initial,
        attributes: {},
        attr(name, value) {
            if (arguments.length === 1) return this.attributes[name];
            this.attributes[name] = String(value || "");
            return this;
        },
        html(value) {
            if (arguments.length === 0) return this.content;
            this.content = String(value || "");
            return this;
        },
        empty() {
            this.content = "";
            return this;
        },
        find(selector) {
            const className = String(selector || "").replace(/^\./, "");
            return { length: className && this.content.includes(className) ? 1 : 0 };
        },
        children() {
            return { length: this.content.trim() ? 1 : 0 };
        },
    };
}

function buildHarness({ canViewPlan, asyncPresenter = false }) {
    const actions = htmlWrapper();
    const layout = htmlWrapper();
    const requiredAssets = [];
    const requestedCapabilities = [];
    const timers = [];
    const handlers = {};

    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "DCO-TEST-0001" },
        fields_dict: {
            plan_control_actions: {
                df: { hidden: 1, permlevel: 1, hidden_due_to_dependency: 1 },
                $wrapper: actions,
            },
            cutting_plan_html: {
                df: { hidden: 1, permlevel: 1, hidden_due_to_dependency: 1 },
                $wrapper: layout,
            },
        },
    };

    const fakeWindow = {
        cur_frm: frm,
        AlmdinaPermissions: {
            canDocument(_frm, capability) {
                requestedCapabilities.push(capability);
                return capability === "view_cutting_plan" && canViewPlan;
            },
            can(capability) {
                requestedCapabilities.push(capability);
                return capability === "view_cutting_plan" && canViewPlan;
            },
        },
        addEventListener() {},
        setTimeout(callback) {
            timers.push(callback);
            return timers.length;
        },
        clearTimeout() {},
    };

    const fakeFrappe = {
        ui: {
            form: {
                on(doctype, mapping) {
                    assert.equal(doctype, "Door Cutting Order");
                    Object.assign(handlers, mapping);
                },
            },
        },
        require(asset) {
            requiredAssets.push(asset);
            if (asset.endsWith("door_cutting_order_cutting_plan_renderer.js")) {
                fakeWindow.AlmdinaCuttingPlanRender = {};
            } else if (asset.endsWith("door_cutting_order_plan_ux.js")) {
                fakeWindow.AlmdinaDoorCuttingPlanUX = {
                    refresh() {
                        const render = () => {
                            actions.html('<div class="dco-plan-actions-shell"><button class="dco-recalculate-plan">recalc</button></div>');
                            return true;
                        };
                        return asyncPresenter ? Promise.resolve().then(render) : render();
                    },
                };
            } else if (asset.endsWith("door_cutting_order_plan_controls_ux.js")) {
                fakeWindow.AlmdinaPlanControlsUX = { apply() {} };
            } else if (asset.endsWith("door_cutting_order_plan_tabs_ux.js")) {
                fakeWindow.AlmdinaPlanTabsUX = {
                    afterRender() {
                        layout.html('<div class="dco-plan-tabs"><div class="dco-plan-tab-content">PLAN</div></div>');
                        return true;
                    },
                };
            } else if (asset.endsWith("door_cutting_order_plan_content_ux.js")) {
                fakeWindow.AlmdinaPlanContentUX = {
                    apply() {},
                    isReady() {
                        return layout.attr("data-almdina-order") === frm.doc.name;
                    },
                };
            }
            return Promise.resolve();
        },
    };

    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Object,
        String,
        Boolean,
        Promise,
        Error,
    });
    vm.runInContext(source, context, {
        filename: "door_cutting_order_plan_surface_bootstrap.js",
    });

    return {
        actions,
        layout,
        frm,
        handlers,
        fakeWindow,
        requiredAssets,
        requestedCapabilities,
        timers,
    };
}

(async () => {
    const authorized = buildHarness({ canViewPlan: true });
    const recovered = await authorized.fakeWindow.AlmdinaCuttingPlanSurfaceBootstrap.recover(
        authorized.frm
    );

    assert.equal(recovered, true);
    assert.ok(
        authorized.fakeWindow.AlmdinaCuttingPlanSurfaceBootstrap.surfaceReady(authorized.frm),
        "authorized plan surface must recover even when plan modules were initially absent"
    );
    assert.match(authorized.actions.content, /dco-plan-actions-shell/);
    assert.match(authorized.actions.content, /dco-recalculate-plan/);
    assert.match(authorized.layout.content, /dco-plan-tabs/);
    assert.deepEqual(
        authorized.frm.fields_dict.plan_control_actions.df,
        { hidden: 0, permlevel: 0, hidden_due_to_dependency: 0 },
        "authorized plan commands must recover from stale hidden/permlevel metadata"
    );
    assert.deepEqual(
        authorized.requiredAssets,
        [
            "/assets/almdina_erp/js/door_cutting_order_cutting_plan_renderer.js",
            "/assets/almdina_erp/js/door_cutting_order_plan_ux.js",
            "/assets/almdina_erp/js/door_cutting_order_plan_controls_ux.js",
            "/assets/almdina_erp/js/door_cutting_order_plan_tabs_ux.js",
            "/assets/almdina_erp/js/door_cutting_order_plan_content_ux.js",
        ]
    );
    assert.ok(authorized.requestedCapabilities.includes("view_cutting_plan"));
    assert.ok(
        !authorized.requestedCapabilities.includes("view_costs"),
        "cutting-plan recovery must never depend on cost visibility"
    );
    assert.ok(
        authorized.timers.length > 0,
        "lazy-loaded bootstrap should also schedule recovery for the active form"
    );

    const asyncAuthorized = buildHarness({ canViewPlan: true, asyncPresenter: true });
    const pendingRecovery = asyncAuthorized.fakeWindow.AlmdinaCuttingPlanSurfaceBootstrap.recover(
        asyncAuthorized.frm
    );
    assert.equal(
        asyncAuthorized.actions.content,
        "",
        "the asynchronous presenter must start with an empty action surface"
    );
    assert.equal(await pendingRecovery, true);
    assert.match(asyncAuthorized.actions.content, /dco-plan-actions-shell/);
    assert.ok(
        asyncAuthorized.fakeWindow.AlmdinaCuttingPlanSurfaceBootstrap.surfaceReady(
            asyncAuthorized.frm
        ),
        "surface recovery must wait for stage context before checking action readiness"
    );

    const denied = buildHarness({ canViewPlan: false });
    denied.actions.html('<div class="dco-plan-actions-shell">STALE</div>');
    denied.layout.html('<div class="dco-plan-tabs">STALE</div>');
    const deniedResult = await denied.fakeWindow.AlmdinaCuttingPlanSurfaceBootstrap.recover(
        denied.frm
    );

    assert.equal(deniedResult, false);
    assert.equal(denied.actions.content, "");
    assert.equal(denied.layout.content, "");
    assert.deepEqual(denied.requiredAssets, []);

    console.log("cutting plan surface isolation simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
