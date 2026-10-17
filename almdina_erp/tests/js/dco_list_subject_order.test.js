"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const css = fs.readFileSync(
    path.join(root, "public/css/door_cutting_order_list_rtl_subject.css"),
    "utf8"
);
const listCss = fs.readFileSync(
    path.join(root, "public/css/door_cutting_order_list.css"),
    "utf8"
);
const listJs = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/list_view/door_cutting_order_list.js"),
    "utf8"
);
const compactJs = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/list_view/door_cutting_order_compact_list_ux.js"),
    "utf8"
);

const subject = ".dco-order-list .list-row-col:is(.name, .list-subject, [data-fieldname=\"name\"])";

assert.ok(css.includes(subject));
assert.ok(css.includes("direction: inherit;"));
assert.ok(css.includes(`${subject} > :not(.select-like)`));
assert.ok(css.includes("direction: ltr;"));
assert.ok(css.includes("unicode-bidi: isolate;"));
assert.ok(css.includes(`${subject} > .select-like`));
assert.equal(css.includes("direction: rtl"), false);
assert.equal(css.includes("row-reverse"), false);
assert.equal(/\bleft\s*:/.test(css), false);
assert.equal(/\bright\s*:/.test(css), false);

assert.ok(listCss.includes('.dco-order-list .list-row-col:is(.order_date, [data-fieldname="order_date"])'));
assert.equal(
    listCss.includes(".name, .list-subject, .order_date, [data-fieldname=\"name\"], [data-fieldname=\"order_date\"]"),
    false
);

for (const forbidden of ["MutationObserver", "setInterval", "requestAnimationFrame"]) {
    assert.equal(css.includes(forbidden), false);
}

// Frappe DOM contract used by both header and rows: checkbox host first, ID second.
function subjectChildren() {
    return [
        { className: "select-like", role: "checkbox" },
        { className: "ellipsis", role: "id", text: "26-00001", href: "/app/door-cutting-order/26-00001" },
    ];
}

function paintOrderLeftToRight(direction) {
    const children = subjectChildren();
    return direction === "rtl"
        ? [...children].reverse().map((node) => node.role)
        : children.map((node) => node.role);
}

function logicalStartOrder() {
    // Flex items keep DOM order relative to the writing direction start edge.
    return subjectChildren().map((node) => node.role);
}

assert.deepEqual(paintOrderLeftToRight("ltr"), ["checkbox", "id"]);
assert.deepEqual(paintOrderLeftToRight("rtl"), ["id", "checkbox"]);
assert.deepEqual(logicalStartOrder(), ["checkbox", "id"]);
assert.equal(subjectChildren()[0].role, "checkbox");
assert.equal(subjectChildren()[1].role, "id");
assert.equal(subjectChildren()[1].href, "/app/door-cutting-order/26-00001");

assert.equal(listJs.includes("select-like"), false);
assert.equal(compactJs.includes("select-like"), false);
assert.equal(listJs.includes("door_cutting_order_list_rtl_subject"), false);

console.log("dco list subject order ok");
