"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const helperSource = fs.readFileSync(path.join(root, "tests/js/board_editor_polyline_input.test.js"), "utf8");

function load(files) {
    const context = {
        console,
        __: (message) => message,
        frappe: { utils: { escape_html: (value) => String(value == null ? "" : value) }, boot: { lang: "en" } },
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    vm.runInContext(
        `${helperSource.slice(helperSource.indexOf("const VOID"), helperSource.indexOf("function loadEditor"))}\nthis.MiniElement = MiniElement;\n`,
        context
    );
    return context;
}

const dom = load([
    "public/js/board_editor/editor_mode.js",
    "public/js/board_editor/drawing_space.js",
    "public/js/board_editor/drawing_model.js",
    "public/js/board_editor/drawing_properties_panel.js",
]);

function render(drawingView) {
    const host = new dom.MiniElement("aside", {}, {});
    dom.AlmdinaBoardEditor.DrawingProperties.reset();
    dom.AlmdinaBoardEditor.DrawingProperties.render(host, {
        editorMode: "drawing",
        drawingTarget: { status: "special", canEdit: true, label: "Door", widthCm: 60, lengthCm: 210 },
        drawingView,
    }, {});
    return host;
}

const shapes = render({
    tool: "shapes",
    shapeKind: "circle",
    ready: true,
    paths: [],
    shapes: [],
});
const kinds = ["rectangle", "circle", "ellipse", "arc", "polygon", "trapezoid", "l_shape", "clipped_corner", "bezier"];
assert.equal(shapes.querySelectorAll("[data-abe-shape-kind]").length, 9);
kinds.forEach((kind) => {
    const button = shapes.querySelector(`[data-abe-shape-kind="${kind}"]`);
    assert.ok(button);
    assert.equal(button.classList.contains("abe-prop-btn"), true);
    assert.equal(button.getAttribute("aria-label").length > 0, true);
    assert.equal(button.getAttribute("title"), button.getAttribute("aria-label"));
});
assert.equal((shapes.innerHTML.match(/abe-shape-glyph/g) || []).length, 9);
assert.equal(shapes.querySelector('[data-abe-shape-kind="circle"]').getAttribute("aria-pressed"), "true");
assert.match(shapes.innerHTML, /abe-shape-menu/);

const references = render({
    tool: "select",
    ready: true,
    referenceMenuOpen: true,
    references: [
        { id: "r1", selected: false, hidden: true, locked: true },
        { id: "r2", selected: true, hidden: false, locked: false, href: "data:image/png;base64,abc" },
    ],
    referenceForm: {
        x_mm: 12,
        y_mm: 18,
        width_mm: 40,
        height_mm: 30,
        rotation_deg: 15,
        opacity: 0.4,
        aspectLocked: true,
    },
    paths: [],
    shapes: [],
});
assert.equal(references.querySelectorAll("[data-abe-reference-select]").length, 2);
assert.equal(references.querySelectorAll('[data-abe-reference-action="delete"]').length, 1);
assert.equal(references.querySelector('[data-abe-reference-action="delete"]').getAttribute("data-abe-reference-id"), "r2");
assert.equal(references.querySelector('[data-abe-reference-action="hide"]').getAttribute("data-abe-reference-id"), "r2");
assert.equal(references.querySelector('[data-abe-reference-action="lock"]').getAttribute("data-abe-reference-id"), "r2");
assert.equal(references.querySelector('[data-abe-reference-field="x_mm"]').getAttribute("value"), "12");
assert.match(references.innerHTML, /data-abe-reference-opacity/);
assert.match(references.innerHTML, /40%/);

const hidden = render({
    tool: "select",
    ready: true,
    referenceMenuOpen: true,
    references: [{ id: "r1", selected: true, hidden: true, locked: true }],
    referenceForm: { x_mm: 4, y_mm: 5, width_mm: 6, height_mm: 7, rotation_deg: 0, opacity: 1, aspectLocked: true },
    paths: [],
    shapes: [],
});
assert.equal(hidden.querySelector('[data-abe-reference-select="r1"]').getAttribute("aria-pressed"), "true");
assert.equal(hidden.querySelector('[data-abe-reference-field="x_mm"]').getAttribute("value"), "4");
assert.match(hidden.querySelector('[data-abe-reference-action="hide"]').getAttribute("aria-label"), /Show reference image/);
assert.match(hidden.querySelector('[data-abe-reference-action="lock"]').getAttribute("aria-label"), /Unlock reference image/);

const textHost = new dom.MiniElement("aside", {}, {});
const textView = {
    editorMode: "drawing",
    drawingTarget: { status: "special", canEdit: true },
    drawingView: {
        tool: "text",
        ready: true,
        textLive: true,
        textForm: {
            text: "ا",
            fontSizeMm: 20,
            fontWeight: "regular",
            direction: "auto",
            align: "right",
            xMm: 10,
            yMm: 12,
            widthMm: 30,
            heightMm: 8,
            rotationDeg: 0,
            aspectLocked: true,
            state: "editable",
        },
        paths: [],
        shapes: [],
    },
};
let typed = "";
dom.AlmdinaBoardEditor.DrawingProperties.reset();
dom.AlmdinaBoardEditor.DrawingProperties.render(textHost, textView, {
    onTextInput(value) { typed = value; },
});
const field = textHost.querySelector('[data-abe-text-field="text"]');
assert.equal(field.tagName, "TEXTAREA");
assert.equal(field.getAttribute("dir"), "auto");
assert.match(textHost.innerHTML, /abe-metric-wide/);
field.value = "مدينة";
(field.listeners.input || []).forEach((fn) => fn({ stopPropagation() {} }));
assert.equal(typed, "مدينة");
const sameField = field;
textView.drawingView.textForm = Object.assign({}, textView.drawingView.textForm, { text: "مدينة", widthMm: 90, heightMm: 20 });
dom.AlmdinaBoardEditor.DrawingProperties.render(textHost, textView, { onTextInput(value) { typed = value; } });
assert.equal(textHost.querySelector('[data-abe-text-field="text"]'), sameField);
assert.equal(sameField.value, "مدينة");

const boardGuard = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
assert.match(boardGuard, /if \(drawingMode && DrawingProperties/);
const picker = boardGuard.slice(boardGuard.indexOf("function openReferencePicker"), boardGuard.indexOf("function toggleReferenceMenu"));
assert.ok(picker.indexOf("input.click") > 0);
assert.ok(picker.indexOf("input.click") < picker.indexOf("syncDrawing"));
assert.match(boardGuard, /if \(files.length\) uploadReferenceFiles\(files\)/);
assert.doesNotMatch(picker, /addReference|deleteReference/);

const drawing = dom.AlmdinaBoardEditor.DrawingModel.createSession();
drawing.activate({ pieceInstanceId: "piece:door-1", widthMm: 600, lengthMm: 2100 });
drawing.markReady();
const image = { x_mm: 0, y_mm: 0, width_mm: 10, height_mm: 10, rotation_deg: 0, opacity: 1 };
const first = drawing.addReference(Object.assign({ file_id: "FILE-1" }, image));
const second = drawing.addReference(Object.assign({ file_id: "FILE-2" }, image));
assert.equal(drawing.deleteReference(second), true);
assert.equal(drawing.current().selection.referenceId, first);
assert.equal(drawing.current().document.references.length, 1);
assert.equal(drawing.deleteReference(first), true);
assert.equal(drawing.current().selection, null);

const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
assert.match(page, /drawing_properties_panel\.js\?v=3/);
assert.match(page, /board_editor\.css\?v=51/);

console.log("board editor properties ui tests ok");
