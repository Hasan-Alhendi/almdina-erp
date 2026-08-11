"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

const styles = [];
global.window = {
    AlmdinaReferenceImageContract: Object.freeze({
        DEFAULT_OPACITY: 0.34,
        MIN_OPACITY: 0.12,
        MAX_OPACITY: 0.85,
    }),
    AlmdinaReferenceImageAcquisition: Object.freeze({}),
    AlmdinaSpecialShapeEditor: Object.freeze({
        open() {},
        view() {},
    }),
    setTimeout,
};
global.frappe = {
    utils: {
        escape_html(value) {
            return String(value)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        },
    },
};
global.document = {
    head: {
        appendChild(node) {
            styles.push(node);
        },
    },
    getElementById(id) {
        return styles.find(node => node.id === id) || null;
    },
    createElement(tagName) {
        return {
            tagName: String(tagName).toUpperCase(),
            id: "",
            textContent: "",
        };
    },
    querySelectorAll() {
        return [];
    },
};
global.MutationObserver = class {
    observe() {}
    disconnect() {}
};

require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_reference_image_ux.js"
));

const ux = window.AlmdinaReferenceImageUX;
assert.ok(Object.isFrozen(ux), "Reference image UX API should be immutable");
ux.installStyles();
ux.installStyles();
assert.equal(styles.length, 1, "Reference image styles should be installed only once");

const reference = {
    file_url: "/private/files/reference.jpg",
    file_name: 'door <script>alert("x")</script>.jpg',
    source: "scanner",
    opacity: 0.4,
    visible: true,
};
const editable = ux.referencePanelHtml(reference, false);
assert.match(editable, /data-reference-upload/);
assert.match(editable, /data-reference-scan/);
assert.match(editable, /data-reference-opacity/);
assert.match(editable, /مسح ضوئي/);
assert.doesNotMatch(editable, /<script>/, "Reference file names must be escaped");
assert.match(editable, /&lt;script&gt;/);

const readonly = ux.referencePanelHtml(reference, true);
assert.doesNotMatch(readonly, /data-reference-upload/);
assert.doesNotMatch(readonly, /data-reference-scan/);
assert.match(readonly, /data-reference-open/);

const empty = ux.referencePanelHtml(null, false);
assert.match(empty, /رفع من الملفات/);
assert.match(empty, /مسح من الطابعة/);

console.log("Reference image UX controls and escaping tests passed");
