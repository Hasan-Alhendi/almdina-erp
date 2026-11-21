"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const sandbox = { window: {} };
vm.createContext(sandbox);
for (const name of ["catalog_labels", "view_model", "dialogs"]) {
    vm.runInContext(fs.readFileSync(path.resolve(__dirname,
        `../../public/js/factory_production_settings/${name}.js`), "utf8"), sandbox);
}
const labels = {
    "Horizontal edge protection (mm)": "هامش حماية أفقي (مم)",
    "Vertical edge protection (mm)": "هامش حماية عمودي (مم)",
};
for (const language of ["ar", "en"]) {
    const translate = text => language === "ar" ? labels[text] || text : text;
    const model = sandbox.window.AlmdinaFactoryProductionSettingsViewModel.create({ translate });
    const dialogs = sandbox.window.AlmdinaFactoryProductionSettingsDialogs.create({ translate, escapeHtml: String });
    const current = { values: { edge_protection_horizontal_mm: 5.5, edge_protection_vertical_mm: 10 } };
    const rows = model.sections(current).find(section => section.key === "cutting").rows;
    const fields = dialogs.sectionFields("cutting", current);
    for (const [fieldname, label, expected] of [
        ["edge_protection_horizontal_mm", "Horizontal edge protection (mm)", 5.5],
        ["edge_protection_vertical_mm", "Vertical edge protection (mm)", 10],
    ]) {
        assert.equal(rows.find(row => row.label === translate(label)).value, expected);
        const field = fields.find(value => value.fieldname === fieldname);
        assert.equal(field.label, translate(label));
        assert.equal(field.default, expected);
        assert.equal(field.fieldtype, "Float");
        assert.equal(field.non_negative, 1);
        assert.match(field.description, /Trim already counts/);
        assert.equal(dialogs.sectionFields("cutting", { values: {} }).find(value => value.fieldname === fieldname).default, 0);
    }
    assert.equal(fields.filter(field => field.fieldname === "max_centerable_edge_gap_cm").length, 1);
}
console.log("Edge protection Arabic/English settings and defaults passed");
