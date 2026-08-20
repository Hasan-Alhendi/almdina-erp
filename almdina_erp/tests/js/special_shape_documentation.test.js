const assert = require("node:assert/strict");
const path = require("node:path");

global.window = global;
const root = path.resolve(__dirname, "../../public/js/special_shape_documentation");
require(path.join(root, "domain/document.js"));
require(path.join(root, "application/history.js"));
require(path.join(root, "application/templates.js"));
require(path.join(root, "application/smart_pen.js"));
require(path.join(root, "application/element_transform.js"));

const api = global.AlmdinaSpecialShapeDocumentation;
const piece = { width_cm: 80, length_cm: 210 };
const initial = api.Document.create(piece);
assert.equal(initial.schema, "almdina.special-shape-documentation");
assert.deepEqual(initial.canvas, { widthMm: 800, heightMm: 2100 });
assert.equal(api.Document.hasContent(initial), false);

for (const definition of api.Templates.DEFINITIONS) {
    const applied = api.Templates.apply(initial, definition.id);
    assert.ok(applied.elements.length, `${definition.id} must produce editable elements`);
    assert.equal(applied.templateId, definition.id);
}

const noisy = [
    { xMm: 100, yMm: 100 }, { xMm: 180, yMm: 103 }, { xMm: 260, yMm: 99 },
    { xMm: 340, yMm: 102 }, { xMm: 104, yMm: 106 },
];
const cleaned = api.SmartPen.clean(noisy, { toleranceMm: 8, joinToleranceMm: 20 });
assert.ok(cleaned.points.length < noisy.length, "smart pen must remove noise");
assert.equal(cleaned.suggestClose, true, "near endpoints must offer closure");
assert.deepEqual(api.SmartPen.close(cleaned.points).at(-1), cleaned.points[0]);

let template = api.Templates.apply(initial, "top-arch");
const element = template.elements[0];
const moved = api.ElementTransform.translate(element, 20, 30, template.canvas);
assert.equal(moved.points[0].xMm, element.points[0].xMm + 20);
assert.equal(moved.points[0].yMm, element.points[0].yMm + 30);
const resized = api.ElementTransform.resize(element, "resize-end", { xMm: 760, yMm: 2000 }, template.canvas);
assert.ok(api.ElementTransform.bounds(resized).maxX > api.ElementTransform.bounds(element).maxX);

const history = api.History.create(initial);
history.commit(template);
assert.equal(history.state().dirty, true);
assert.equal(history.state().canUndo, true);
history.undo();
assert.equal(history.get().elements.length, 0);
history.redo();
assert.ok(history.get().elements.length);
history.markSaved();
assert.equal(history.state().dirty, false);

const image = api.Document.setReference(initial, { fileUrl: "/private/files/reference.jpg", opacity: 0.72, rotationDeg: 0, locked: true });
assert.equal(api.Document.hasContent(image), true);
assert.equal(api.Document.fromStored(api.Document.toStored(image), piece).reference.fileUrl, "/private/files/reference.jpg");

console.log("Special-shape documentation domain, templates, smart pen, transforms, and history passed");
