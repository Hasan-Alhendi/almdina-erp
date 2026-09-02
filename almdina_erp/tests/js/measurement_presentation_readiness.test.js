"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

let registeredKey = null;
let presentationOwner = null;

global.window = {
    AlmdinaMeasurementLifecycle: {
        registerFeature(key, owner) {
            registeredKey = key;
            presentationOwner = typeof owner === "function" ? owner : owner?.reconcile;
            return true;
        },
    },
    getComputedStyle(node) {
        return node && node.__computedStyle ? node.__computedStyle : {};
    },
};

require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_presentation_owner.js"
));

assert.equal(registeredKey, "measurement-presentation");
assert.equal(typeof presentationOwner, "function");

function styled(values) {
    return { __computedStyle: { ...values } };
}

function surface({
    toolbarDisplay = "flex",
    overflowX = "auto",
    tableLayout = "fixed",
    edgeDisplays = ["grid", "grid"],
    toggleDisplays = ["inline-flex", "inline-flex", "inline-flex", "inline-flex"],
} = {}) {
    const toolbar = styled({ display: toolbarDisplay });
    const scroll = styled({ overflowX });
    const table = styled({ tableLayout });
    const edgeGroups = edgeDisplays.map(display => styled({ display }));
    const toggles = toggleDisplays.map(display => styled({ display }));

    return {
        querySelector(selector) {
            if (selector === ".dco-fast-entry-toolbar") return toolbar;
            if (selector === ".dco-fast-entry-scroll") return scroll;
            if (selector === ".dco-fast-table") return table;
            return null;
        },
        querySelectorAll(selector) {
            if (selector === ".dco-edge-buttons") return edgeGroups;
            if (selector === ".dco-check-toggle") return toggles;
            return [];
        },
    };
}

assert.equal(
    presentationOwner({}, surface()),
    true,
    "a structurally and visually ready measurement table must settle"
);

assert.equal(
    presentationOwner({}, surface({ edgeDisplays: ["block", "grid"] })),
    false,
    "the stacked edge-control state from the slow-network regression must not be marked ready"
);

assert.equal(
    presentationOwner({}, surface({ tableLayout: "auto" })),
    false,
    "table geometry must be fixed before lifecycle readiness is stamped"
);

assert.equal(
    presentationOwner({}, surface({ toolbarDisplay: "block" })),
    false,
    "toolbar presentation is part of the measurement readiness contract"
);

assert.equal(
    presentationOwner({}, surface({ overflowX: "hidden" })),
    true,
    "compact desktop horizontal overflow is a valid presentation mode"
);

assert.equal(
    presentationOwner({}, surface({ overflowX: "visible" })),
    true,
    "mobile-card visible overflow is a valid presentation mode"
);

const originalGetComputedStyle = window.getComputedStyle;
delete window.getComputedStyle;
assert.equal(
    presentationOwner({}, surface()),
    true,
    "non-browser harnesses continue to rely on the central structural lifecycle contract"
);
window.getComputedStyle = originalGetComputedStyle;

const manifestPath = path.resolve(__dirname, "../../frontend_assets.py");
const manifest = fs.readFileSync(manifestPath, "utf8");
const structureCss = "/assets/almdina_erp/css/door_cutting_order_measurement_structure.css";
const responsiveCss = "/assets/almdina_erp/css/door_cutting_order_responsive.css";
const lifecycleJs = "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_lifecycle.js";
const presentationJs = "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_presentation_owner.js";

assert.ok(manifest.includes(structureCss), "measurement structural CSS must be an app asset");
assert.ok(
    manifest.indexOf(structureCss) < manifest.indexOf(responsiveCss),
    "measurement structural CSS must load before responsive enhancement CSS"
);
assert.ok(manifest.includes(presentationJs), "presentation owner must be in the DCO asset manifest");
assert.ok(
    manifest.indexOf(lifecycleJs) < manifest.indexOf(presentationJs),
    "presentation owner must register after the central measurement lifecycle"
);

const css = fs.readFileSync(
    path.resolve(__dirname, "../../public/css/door_cutting_order_measurement_structure.css"),
    "utf8"
);
assert.match(css, /\.dco-fast-entry-shell\s+\.dco-edge-buttons\s*\{[^}]*display:\s*grid;/s);
assert.doesNotMatch(css, /!important/);

console.log("measurement presentation readiness regression tests passed");
