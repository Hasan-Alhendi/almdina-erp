"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const controllerSource = fs.readFileSync(
    path.join(root, "public/js/board_editor/controller.js"),
    "utf8"
);
const foundationSource = fs.readFileSync(
    path.join(root, "public/js/frontend_foundation.js"),
    "utf8"
);

function loadGate() {
    const context = {
        window: {},
        document: {
            getElementById() { return null; },
            querySelector() { return null; },
            head: { appendChild() {} },
        },
    };
    context.window.document = context.document;
    context.globalThis = context;
    vm.createContext(context);
    vm.runInContext(foundationSource, context);
    return context.window.AlmdinaFrontend.createLatestRequestGate();
}

function acceptsProjection(gate, requestToken, openGeneration, generation, suspended) {
    return !(
        openGeneration !== generation
        || suspended
        || !gate.isCurrent(requestToken)
    );
}

const gate = loadGate();
const requestToken = gate.begin();
assert.equal(gate.isCurrent(), false);
assert.equal(gate.isCurrent(requestToken), true);
assert.equal(acceptsProjection(gate, requestToken, 1, 1, false), true);

const staleGate = loadGate();
const first = staleGate.begin();
staleGate.begin();
assert.equal(staleGate.isCurrent(first), false);
staleGate.invalidate();
const current = staleGate.begin();
assert.equal(acceptsProjection(staleGate, current, 1, 2, false), false);
assert.equal(acceptsProjection(staleGate, current, 2, 2, true), false);

assert.match(controllerSource, /const requestToken = requestGate\.begin\(\)/);
assert.match(controllerSource, /requestGate\.isCurrent\(requestToken\)/);
assert.doesNotMatch(controllerSource, /requestGate\.isCurrent\(\)/);
assert.match(controllerSource, /abe-retry/);
assert.match(controllerSource, /Board editor render failed/);
assert.match(controllerSource, /loadedRevisionToken/);
assert.match(controllerSource, /content_revision_token/);
assert.match(controllerSource, /responsePlan !== planName/);

console.log("board editor open contract passed");
