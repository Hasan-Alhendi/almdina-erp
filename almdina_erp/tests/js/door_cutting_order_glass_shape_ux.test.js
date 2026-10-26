"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const source = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/drawing/door_cutting_order_glass_shape_ux.js"),
    "utf8"
);
const operator = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js"),
    "utf8"
);
const corner = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js"),
    "utf8"
);
const recovery = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/recovery/application/door_cutting_order_recovery_projection.js"),
    "utf8"
);
const csv = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
const glassCss = fs.readFileSync(
    path.join(root, "public/css/door_cutting_order_glass_shape.css"), "utf8"
);
const assetManifest = fs.readFileSync(path.join(root, "frontend_assets.py"), "utf8");
const translations = new Map(csv.split(/\r?\n/).map((line) => {
    const delimiter = line.indexOf(",");
    return delimiter < 0 ? ["", ""] : [line.slice(0, delimiter), line.slice(delimiter + 1).split(",")[0]];
}));

const documentStub = {
    documentElement: { lang: "ar" },
    getElementById() { return null; },
    createElement() { return { id: "", textContent: "" }; },
    head: { appendChild() {} },
};

function translate(message) {
    const text = String(message);
    return documentStub.documentElement.lang === "ar"
        ? (translations.get(text) || text)
        : text;
}

const fakeWindow = {};
vm.runInContext(source, vm.createContext({
    window: fakeWindow,
    document: documentStub,
    __: translate,
    frappe: {},
    Object,
    Array,
    Boolean,
    Number,
    String,
    Math,
    console,
}));

const api = fakeWindow.AlmdinaGlassShape;
assert.equal(api.GLASS_TYPE, "Glass");
assert.equal(api.isGlass({ piece_type: "Glass" }), true);
assert.equal(api.isGlass({ piece_type: "Regular" }), false);
assert.equal(api.isGlass({ piece_type: "Clipped Corner" }), false);
assert.equal(api.isGlass({ piece_type: "L-Shaped Corner" }), false);
assert.equal(api.isGlass({ piece_type: "Special" }), false);

const reference = {
    piece_type: "Glass",
    width_cm: 52.1,
    length_cm: 72.5,
    glass_margin_mm: 65,
};
const opening = api.openingMm(52.1, 72.5, 65);
assert.equal(opening.openingWidthMm, 391);
assert.equal(opening.openingLengthMm, 595);
assert.equal(api.marginCmTextFromMm(65), "6.5");
assert.equal(api.marginMmFromCm("6.5"), 65);
assert.equal(api.approvedMarginText(reference), "6.5");

const shown = api.previewState(52.1, 72.5, "6.5");
assert.equal(shown.status, "valid");
assert.equal(shown.opening.marginMm, 65);
assert.equal(shown.opening.openingWidthMm, 391);
assert.equal(shown.opening.openingLengthMm, 595);

const precise = { piece_type: "Glass", width_cm: 52.1, length_cm: 72.5, glass_margin_mm: 65.125 };
assert.equal(api.marginCmTextFromMm(65.001), "6.5001");
assert.equal(api.approvedMarginText(precise), "6.5125");
assert.equal(api.marginMmFromCm("6.5125"), 65.125);
assert.equal(api.marginMmFromCm(api.approvedMarginText(precise)), 65.125);
assert.equal(api.applyDraft(precise, api.approvedMarginText(precise)).glass_margin_mm, 65.125);

const preview = api.previewSvg(52.1, 72.5, shown);
assert.match(preview, /dco-glass-frame/);
assert.match(preview, /dco-glass-opening/);
assert.match(preview, /391/);
assert.match(preview, /595/);

const liveRoot = fakeEditorRoot();
api.renderEditor(liveRoot, reference, "6.5");
assert.equal(liveRoot.nodes["[data-opening-width]"].textContent, "391");
assert.equal(liveRoot.nodes["[data-opening-length]"].textContent, "595");
assert.match(liveRoot.nodes["[data-glass-preview]"].innerHTML, /dco-glass-opening/);
api.renderEditor(liveRoot, reference, "7");
assert.equal(liveRoot.nodes["[data-opening-width]"].textContent, "381");
assert.match(source, /addEventListener\("input"/);

const session = api.beginSession(reference);
assert.equal(session.draft, "6.5");
session.setDraft("8");
assert.equal(session.preview().opening.openingWidthMm, 361);
const cancelled = session.cancel();
assert.equal(cancelled.dirty, false);
assert.equal(cancelled.save, false);
assert.equal(cancelled.draft, "6.5");
assert.equal(reference.glass_margin_mm, 65);

session.setDraft("6.5");
const applied = session.apply();
assert.equal(applied.ok, true);
assert.equal(applied.save, false);
assert.equal(applied.values.glass_margin_mm, 65);
assert.equal(reference.glass_margin_mm, 65);
reference.glass_margin_mm = applied.glass_margin_mm;
const reopened = api.beginSession(reference);
assert.equal(reopened.draft, "6.5");
assert.equal(reopened.preview().opening.openingLengthMm, 595);
assert.equal(api.applyDraft(reference, reopened.draft).glass_margin_mm, reference.glass_margin_mm);

reference.width_cm = 10;
const resized = api.previewState(reference.width_cm, reference.length_cm, api.approvedMarginText(reference));
assert.equal(resized.status, "invalid");
assert.equal(reference.glass_margin_mm, 65);
assert.equal(api.applyDraft(reference, "6.5").ok, false);
reference.width_cm = 52.1;

for (const draft of ["0", "-0.5", "", "26.05"]) {
    const rejected = api.applyDraft(
        { piece_type: "Glass", width_cm: 52.1, length_cm: 72.5, glass_margin_mm: 65 },
        draft
    );
    assert.equal(rejected.ok, false, draft);
    assert.equal(rejected.save, false);
}

const stored = {
    piece_type: "Regular",
    width_cm: 52.1,
    length_cm: 72.5,
    glass_margin_mm: 65,
};
assert.equal(api.shapeButtonState(stored, { editable: true, virtual: false }), null);
stored.piece_type = "Glass";
const glassButton = api.shapeButtonState(stored, { editable: true, virtual: false });
assert.equal(glassButton.enabled, true);
assert.equal(api.shapeButtonState(stored, { editable: false, virtual: false }).enabled, true);
assert.equal(api.shapeButtonState(stored, { editable: false, virtual: true }).enabled, false);
assert.equal(typeof api.view, "function");
assert.match(source, /if \(readOnly\) \{[\s\S]*?input.disabled = true/);
assert.match(operator, /AlmdinaGlassShape\.view\(currentFrm, row\)/);
assert.match(operator, /AlmdinaClippedCornerEditor\.view\(currentFrm, row\)/);
assert.match(operator, /AlmdinaSpecialShapeEditor\.view\(currentFrm, row\)/);
assert.equal(glassButton.incomplete, false);
assert.match(glassButton.label, /6\.5/);
assert.match(glassButton.label, /سم/);
stored.piece_type = "Regular";
assert.equal(api.shapeButtonState(stored, { editable: true, virtual: false }), null);
assert.equal(stored.glass_margin_mm, 65);
stored.piece_type = "Glass";
assert.equal(api.approvedMarginText(stored), "6.5");
assert.equal(api.shapeButtonState(stored, { editable: true, virtual: false }).incomplete, false);

const empty = {
    piece_type: "Glass",
    width_cm: 52.1,
    length_cm: 72.5,
    glass_margin_mm: 0,
};
const emptyButton = api.shapeButtonState(empty, { editable: true, virtual: false });
assert.equal(api.approvedMarginText(empty), "");
assert.equal(emptyButton.enabled, true);
assert.equal(emptyButton.incomplete, true);
assert.equal(api.beginSession(empty).draft, "");

assert.equal(api.shapeButtonState({
    piece_type: "Clipped Corner",
    glass_margin_mm: 65,
}, { editable: true }), null);
assert.match(corner, /Apply corner/);
assert.match(corner, /min-height:430px/);
assert.match(corner, /min-height:280px/);
assert.match(corner, /min-height:240px/);
const desktopStyles = glassCss.split("@media")[0];
assert.match(desktopStyles, /\.dco-glass-preview\{[^}]*height:188px/);
assert.match(desktopStyles, /min-height:0/);
assert.doesNotMatch(desktopStyles, /min-height:\s*420px|min-height:\s*260px|min-height:\s*220px/);
assert.doesNotMatch(desktopStyles, /overflow-y:\s*auto/);
assert.match(glassCss, /@media\(max-width:720px\)\{[\s\S]*overflow-y:auto/);
assert.match(source, /\$\{__\("cm"\)\}/);
const cornerOpen = operator.indexOf("window.AlmdinaClippedCornerEditor.open(currentFrm, row)");
const glassOpen = operator.indexOf("window.AlmdinaGlassShape.open(currentFrm, row)");
const specialOpen = operator.indexOf("window.AlmdinaSpecialShapeEditor.open(currentFrm, row)");
assert.ok(cornerOpen > -1 && glassOpen > cornerOpen && specialOpen > glassOpen);
assert.equal(source.includes("frm.save"), false);
assert.match(source, /commitChildValues/);
assert.match(source, /glass_margin_mm: marginMm/);
assert.match(recovery, /glass_margin_mm/);

assert.match(glassCss, /var\(--text-color\)/);
assert.doesNotMatch(glassCss, /#172033|#000\b|color:\s*#/);
assert.match(translations.get("Glass Door"), /درفة بلور/);
assert.equal(translations.get("Glass Margin"), "هامش البلور");
assert.equal(translations.get("Glass Opening Dimensions"), "أبعاد فتحة البلور");
assert.equal(translations.get("Opening Width"), "عرض الفتحة");
assert.equal(translations.get("Opening Length"), "طول الفتحة");
assert.equal(translations.get("Apply Shape"), "اعتماد الشكل");
assert.equal(translations.get("Invalid Glass Margin"), "هامش البلور غير صالح");

documentStub.documentElement.lang = "en";
const english = api.shapeButtonState(reference, { editable: true, virtual: false });
assert.match(english.title, /Glass Door/);
assert.match(english.title, /391/);
documentStub.documentElement.lang = "ar";
const arabic = api.shapeButtonState({
    piece_type: "Glass",
    width_cm: 52.1,
    length_cm: 72.5,
    glass_margin_mm: 65,
}, { editable: true, virtual: false });
assert.match(arabic.title, /درفة بلور/);
assert.match(arabic.label, /6\.5/);
assert.match(arabic.label, /سم/);
const invalidArabic = api.shapeButtonState({
    piece_type: "Glass",
    width_cm: 10,
    length_cm: 72.5,
    glass_margin_mm: 65,
}, { editable: true, virtual: false });
assert.equal(invalidArabic.title, "هامش البلور غير صالح");
assert.equal(invalidArabic.enabled, true);

function fakeEditorRoot() {
    const nodes = {};
    return {
        nodes,
        querySelector(selector) {
            if (!nodes[selector]) {
                nodes[selector] = {
                    classList: { toggle() {} },
                    textContent: "",
                    innerHTML: "",
                    value: "",
                };
            }
            return nodes[selector];
        },
    };
}

const enlargedPreview = api.previewSvg(52.1, 72.5, api.previewState(52.1, 72.5, "6.5"));
const frameWidth = Number(enlargedPreview.match(/class="dco-glass-frame"[^>]*width="([0-9.]+)"/)[1]);
assert.ok(frameWidth > 170, `glass drawing should fill more of the preview, got ${frameWidth}`);
assert.match(enlargedPreview, /class="dco-glass-opening"/);
assert.match(desktopStyles, /var\(--card-bg/);
assert.match(assetManifest, /\/assets\/almdina_erp\/css\/door_cutting_order_glass_shape\.css\?v=1/);
assert.doesNotMatch(source, /createElement\("style"\)|installStyles|editorStyles/);
assert.equal(Object.prototype.hasOwnProperty.call(api, "editorStyles"), false);
assert.doesNotMatch(desktopStyles, /overflow-y:\s*auto/);

console.log("door_cutting_order_glass_shape_ux.test.js: ok");
