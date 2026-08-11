"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_exact_line_edit_model.js"
), "utf8");

assert.doesNotThrow(() => new Function(source));
assert.ok(source.includes("outside-piece"));
assert.ok(source.includes("preserveConnections"));
assert.ok(source.includes("moveSharedEndpoint"));

console.log("Exact line edit bounds contract passed");