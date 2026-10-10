"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order");

function read(relativePath) {
    return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function elementFrom(html) {
    const node = {
        innerHTML: html,
        dataset: {},
        style: { setProperty() {} },
        get outerHTML() { return this.innerHTML; },
        querySelector(selector) {
            const token = String(selector || "").replace(".", "");
            if (!token || !this.innerHTML.includes(token)) return null;
            return elementFrom(this.innerHTML);
        },
        querySelectorAll(selector) {
            const found = this.querySelector(selector);
            return found ? [found] : [];
        },
        cloneNode() { return elementFrom(this.innerHTML); },
    };
    return node;
}

const prints = [];
const fakeWindow = {
    AlmdinaOrderDocumentPrintTheme: {
        headerHtml() { return ""; },
        headerCss() { return ""; },
    },
    open() {
        return {
            document: {
                open() {},
                write(html) { prints.push(String(html)); },
                close() {},
            },
        };
    },
};
const documentStub = {
    documentElement: { lang: "ar" },
    getElementById() { return null; },
    createElement() { return elementFrom(""); },
    head: { appendChild() {} },
};
const frappe = {
    boot: { lang: "ar" },
    msgprint() {},
    ui: { form: { on() {} } },
    utils: { escape_html(value) { return String(value ?? ""); } },
};

const context = vm.createContext({
    window: fakeWindow,
    document: documentStub,
    frappe,
    console,
    JSON,
    Number,
    String,
    Math,
    Object,
    Array,
    Set,
    Map,
    WeakMap,
    Promise,
    Boolean,
    Error,
    __: (value) => value,
});

[
    "drawing/door_cutting_order_special_shape_geometry.js",
    "drawing/door_cutting_order_shape_output_contract.js",
    "drawing/door_cutting_order_clipped_corner_ux.js",
    "cutting_plan/door_cutting_order_piece_geometry.js",
    "cutting_plan/door_cutting_order_cutting_plan_renderer.js",
].forEach((relativePath) => {
    vm.runInContext(read(relativePath), context, { filename: relativePath });
});

const renderer = fakeWindow.AlmdinaCuttingPlanRender;
const frm = {
    doc: {
        name: "DCO-BREAK-ONLY",
        customer: "عميل",
        board_description: "MDF",
        pieces: [],
    },
};

function planFor(piece) {
    return {
        usable_board_width_cm: 122,
        usable_board_length_cm: 244,
        full_board_width_cm: 122,
        full_board_length_cm: 244,
        sheets: [{
            sheet_no: 1,
            pieces: [piece],
        }],
    };
}

function cornerPiece(label, flags) {
    return {
        id: label,
        x: 0,
        y: 0,
        w: 100,
        h: 200,
        original_w: 100,
        original_h: 200,
        area_m2: 0.2,
        label,
        piece_type: "Clipped Corner",
        clipped_corner_position: "Top Right",
        clipped_corner_width_cm: 20,
        clipped_corner_length_cm: 40,
        rotated: false,
        edge_width_top: 0,
        edge_width_bottom: 0,
        edge_long_right: 0,
        edge_long_left: 0,
        edge_break: 0,
        edge_break_only: 0,
        ...flags,
    };
}

function outline(html) {
    return (html.match(/<path d="([^"]+)"/) || [])[1] || "";
}

function breakOnlyPoints(html) {
    return (html.match(/dco-edge-break-only-svg"[^>]*points="([^"]+)"/) || [])[1] || "";
}

const alone = cornerPiece("alone", { edge_break_only: 1 });
const withSide = cornerPiece("with-side", {
    edge_break_only: 1,
    edge_width_top: 1,
});
const fullPath = cornerPiece("full-path", { edge_break: 1 });
const clear = cornerPiece("clear", {});
const aloneOutline = outline(renderer.build(frm, planFor(clear)));

const aloneHtml = renderer.build(frm, planFor(alone));
const alonePoints = breakOnlyPoints(aloneHtml);
assert.ok(alonePoints, "Break-only with no outer sides must draw the diagonal edge");
assert.equal(alonePoints.split(" ").length, 2, "Break-only highlighting must cover the diagonal segment only");
assert.equal(outline(aloneHtml), aloneOutline, "Edge banding must not change the cut outline");
assert.doesNotMatch(aloneHtml, /dco-edge-break-svg"/);

const withSideHtml = renderer.build(frm, planFor(withSide));
assert.ok(breakOnlyPoints(withSideHtml), "Break-only must still draw beside an outer side");
assert.match(withSideHtml, /dco-edge-line-svg "/);
assert.equal(outline(withSideHtml), aloneOutline);

const fullPathHtml = renderer.build(frm, planFor(fullPath));
assert.match(fullPathHtml, /dco-edge-break-svg"/);
assert.equal(breakOnlyPoints(fullPathHtml), "");
assert.equal(outline(fullPathHtml), aloneOutline);

const clearHtml = renderer.build(frm, planFor(clear));
assert.doesNotMatch(clearHtml, /dco-piece-edge-svg/);
assert.doesNotMatch(clearHtml, /dco-edge-line-svg/);

async function printed(piece) {
    prints.length = 0;
    const opened = await renderer.print(frm, planFor(piece));
    assert.equal(opened, true);
    return prints[prints.length - 1] || "";
}

async function main() {
    const printedAlone = await printed(alone);
    assert.equal(breakOnlyPoints(printedAlone), alonePoints, "Print must use the same break-only diagonal as the preview");
    assert.equal(outline(printedAlone), aloneOutline);

    const printedWithSide = await printed(withSide);
    assert.ok(breakOnlyPoints(printedWithSide));
    assert.match(printedWithSide, /dco-edge-line-svg "/);

    const printedFullPath = await printed(fullPath);
    assert.match(printedFullPath, /dco-edge-break-svg"/);
    assert.equal(breakOnlyPoints(printedFullPath), "");

    const printedClear = await printed(clear);
    assert.doesNotMatch(printedClear, /<svg class="dco-piece-edge-svg/);
    assert.doesNotMatch(printedClear, /<polyline/);
    assert.doesNotMatch(printedClear, /dco-edge-break-only-svg/);

    console.log("Cutting plan break-only edge regression passed");
}

main().catch((error) => {
    console.error(error);
    process.exit(1);
});
