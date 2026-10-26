"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../");
const operatorPath = path.join(
    root,
    "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js"
);

const formHandlers = {};
const window = {};
const sandbox = {
    window,
    document: {},
    frappe: {
        ui: { form: { on(doctype, handlers) { formHandlers[doctype] = handlers; } } },
        utils: { escape_html(value) { return String(value); } },
    },
    __: message => String(message),
    Object,
    String,
    Number,
    Boolean,
    Promise,
    Set,
    Map,
    console,
};
window.frappe = sandbox.frappe;

vm.runInNewContext(fs.readFileSync(operatorPath, "utf8"), sandbox, { filename: operatorPath });

window.AlmdinaOrderDimensionValidation = {
    boardDimensions() {
        return { length: 280, width: 210, valid: true };
    },
    positiveNumber(value) {
        const number = Number(value);
        return Number.isFinite(number) && number > 0 ? number : null;
    },
};

const issuesFor = (length, width, allow_rotation = 0) => (
    window.AlmdinaDoorCuttingFastEntry.pieceDimensionIssues(
        {},
        { length_cm: length, width_cm: width, allow_rotation }
    )
);
const assertIssues = (actual, expected) => {
    assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected);
};

assertIssues(issuesFor(250, 180), {}); // 1. valid
assertIssues(issuesFor(290, 180), { length_cm: "Exceeds board length" }); // 2. length
assertIssues(issuesFor(250, 220), { width_cm: "Exceeds board width" }); // 3. width
assertIssues(issuesFor(290, 220), {
    length_cm: "Exceeds board length",
    width_cm: "Exceeds board width",
}); // 4. both independently
assertIssues(issuesFor(280, 210), {}); // 5. equality
assertIssues(issuesFor(200, 250, 1), { width_cm: "Exceeds board width" }); // 6. no rotation swap
assertIssues(issuesFor(280, 220), { width_cm: "Exceeds board width" }); // 7. length correction leaves width
assertIssues(issuesFor("", 220), {
    width_cm: "Exceeds board width",
    length_cm: "Piece length must be a positive number.",
}); // temporary empty input remains editable and independently validated

const source = fs.readFileSync(operatorPath, "utf8");
assert.match(source, /data-field-error=\"\$\{fieldname\}\"/); // 8. local error node
assert.match(source, /\.dco-piece-dimension-error \{[^}]*display:block/);
assert.match(source, /max-width:100%/);
assert.match(source, /overflow-wrap:anywhere/);
const liveInputHandler = source
    .split('root.addEventListener("input", event => {', 2)[1]
    .split('root.addEventListener("change"', 1)[0];
assert.match(liveInputHandler, /syncInputToModel\(currentFrm, input, false\)/);
assert.match(liveInputHandler, /\}, true\);/);
assert.doesNotMatch(liveInputHandler, /renderFastMeasurements|\.focus\(|\.select\(/);
assert.match(source, /liveRowDimensionValues\(tr, row\)/);

console.log("piece dimension validation tests passed", Object.keys(formHandlers).length);
