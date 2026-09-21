"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const foundationSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/frontend_foundation.js"),
    "utf8"
);
const toolbarSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/factory_workforce/toolbar.js"),
    "utf8"
);

function mountPoint() {
    return { length: 1 };
}

const controls = [];
const fakeWindow = {
    setTimeout,
    clearTimeout,
    document: { head: {}, createElement() {} },
    AlmdinaUi: {
        control(options) {
            const control = {
                fieldname: options.fieldname,
                disposed: 0,
                dispose() { this.disposed += 1; },
                getValue() { return options.value || ""; },
                setValue() {},
            };
            controls.push(control);
            return control;
        },
    },
};

function $(value) {
    return value;
}

const context = vm.createContext({
    window: fakeWindow,
    $, 
    Promise,
    Object,
    String,
    Number,
    Boolean,
    Array,
    Map,
    Set,
    console,
    __: value => value,
});
vm.runInContext(foundationSource, context, { filename: "frontend_foundation.js" });
vm.runInContext(toolbarSource, context, { filename: "factory_workforce/toolbar.js" });

const lifecycle = fakeWindow.AlmdinaFrontend.createLifecycleScope();
const main = {
    find(selector) {
        assert.ok(selector === ".aw-search-mount" || selector === ".aw-enabled-mount");
        return mountPoint();
    },
};
const toolbar = fakeWindow.AlmdinaFactoryWorkforceToolbar.create({
    $main: main,
    state: { search: "", enabled: "all" },
    lifecycle,
    load() {},
    translate: value => value,
});

assert.equal(toolbar.mount(), true);
assert.equal(controls.length, 2, "first mount must create one toolbar set");
const firstSet = controls.slice();
toolbar.dispose();
assert.deepEqual(firstSet.map(control => control.disposed), [1, 1]);

assert.equal(toolbar.mount(), true);
assert.equal(controls.length, 4, "remount must create one replacement toolbar set");
const secondSet = controls.slice(2);
assert.deepEqual(secondSet.map(control => control.disposed), [0, 0]);

assert.equal(lifecycle.dispose(), true);
assert.deepEqual(secondSet.map(control => control.disposed), [1, 1]);
assert.equal(lifecycle.dispose(), false);

console.log("Factory Workforce toolbar ownership lifecycle simulation passed");
