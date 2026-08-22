"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/frontend_foundation.js"),
    "utf8"
);

const requireCalls = [];
const fakeWindow = {
    frappe: {
        require(items) {
            requireCalls.push(items);
            return Promise.resolve();
        },
    },
    document: { head: {} },
    setTimeout,
    clearTimeout,
};

const context = vm.createContext({
    window: fakeWindow,
    console,
    Promise,
    Object,
    String,
    Number,
    Boolean,
    Array,
    Map,
    Set,
    Error,
});
vm.runInContext(source, context, { filename: "frontend_foundation.js" });

(async () => {
    const frontend = fakeWindow.AlmdinaFrontend;
    assert.ok(frontend);
    assert.equal(typeof frontend.requireAssets, "function");

    const assets = ["/assets/a.js", "/assets/b.js", "/assets/a.js", ""];
    const first = frontend.requireAssets(assets);
    const second = frontend.requireAssets(["/assets/a.js", "/assets/b.js"]);
    const [firstResult, secondResult] = await Promise.all([first, second]);

    assert.equal(requireCalls.length, 1, "one dependency group must call frappe.require once");
    assert.equal(
        JSON.stringify(requireCalls[0]),
        JSON.stringify(["/assets/a.js", "/assets/b.js"]),
        "the batch must be deduplicated before reaching Frappe"
    );
    assert.equal(JSON.stringify(firstResult), JSON.stringify(requireCalls[0]));
    assert.equal(JSON.stringify(secondResult), JSON.stringify(requireCalls[0]));

    await frontend.requireAssets("/assets/c.js");
    assert.equal(requireCalls.length, 2);
    assert.equal(JSON.stringify(requireCalls[1]), JSON.stringify(["/assets/c.js"]));

    console.log("Frontend asset loader batches cold-page dependencies once");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
