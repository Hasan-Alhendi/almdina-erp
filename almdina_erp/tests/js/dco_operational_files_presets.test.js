const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");
const panelPath = path.join(
    root,
    "public/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js"
);
const translationsPath = path.join(root, "translations/ar.csv");
const windowObject = {};
vm.runInNewContext(fs.readFileSync(panelPath, "utf8"), { window: windowObject }, { filename: panelPath });
const ux = windowObject.AlmdinaOperationalFilesUX;
const panel = fs.readFileSync(panelPath, "utf8");
const translations = fs.readFileSync(translationsPath, "utf8");

const linerPaths = [1, 2, 3, 4, 5].map(number => ({
    path_key: `liner:piece:${number}`,
    operation_key: "liner",
    piece_label: String(number),
    tool_preset: "",
}));
const sheet = {
    sheet_no: 1,
    cut_path_early_confirmed: false,
    operations: [
        {
            operation_key: "liner",
            dxf_layer: "Liner",
            tool_preset: "Finish",
            preset_source: "factory",
            factory_preset: "Finish",
            path_count: 5,
        },
        {
            operation_key: "cut_path",
            dxf_layer: "CUT_PATH",
            tool_preset: "Finish",
            preset_source: "factory",
            factory_preset: "Finish",
            path_count: 1,
        },
    ],
    paths: linerPaths.concat([{
        path_key: "cut:piece:1",
        operation_key: "cut_path",
        piece_label: "1",
        tool_preset: "",
    }]),
};
const workspace = {
    can_prepare: true,
    can_edit_factory_cnc: true,
    presets: [{
        name: "Finish",
        preset_name: "Finish",
        tool_number: "T9",
        tool_diameter_mm: 6,
        enabled: true,
        final_depth_mm: 18.5,
        spindle_speed_rpm: 15000,
        feed_rate_mm_min: 10200,
        plunge_rate_mm_min: 1800,
    }, {
        name: "Shallow",
        preset_name: "Shallow",
        tool_number: "T9",
        tool_diameter_mm: 6,
        enabled: true,
        final_depth_mm: 7,
    }, {
        name: "Off",
        preset_name: "Off",
        tool_number: "T9",
        tool_diameter_mm: 6,
        enabled: false,
    }],
};

const state = ux.sheetState(sheet);
linerPaths.forEach(pathRow => {
    assert.strictEqual(ux.effectivePreset(state, pathRow), "Finish");
    assert.strictEqual(state.overrides[pathRow.path_key], undefined);
});
const html = ux.dialogMarkup(workspace, sheet, state);
assert.strictEqual((html.match(/data-operation-preset-host=/g) || []).length, 0);
assert.strictEqual((html.match(/data-path-preset-host=/g) || []).length, 0);
assert.ok(html.includes("Vector Associations"));
assert.ok(html.includes("Associations appear here after they are saved."));
assert.ok(!html.includes("data-add-preset"));
assert.ok(!html.includes("<select data-operation-key="));

ux.applyLayerPreset(state, "liner", "Shallow");
linerPaths.forEach(pathRow => {
    assert.strictEqual(ux.effectivePreset(state, pathRow), "Shallow");
});
assert.strictEqual(state.sources.liner, "sheet");
const changed = ux.dialogMarkup(workspace, sheet, state);
assert.ok(!changed.includes("data-path-preset-host="));

ux.customizePath(state, linerPaths[0].path_key, "Finish", state.operations.liner);
assert.strictEqual(ux.effectivePreset(state, linerPaths[0]), "Finish");
linerPaths.slice(1).forEach(pathRow => {
    assert.strictEqual(ux.effectivePreset(state, pathRow), "Shallow");
});
state.expanded.liner = true;
state.customizing[linerPaths[0].path_key] = true;
const custom = ux.dialogMarkup(workspace, sheet, state);
assert.ok(!custom.includes("data-path-preset-host="));
assert.ok(panel.includes("Custom preset"));
assert.ok(panel.includes("Use the layer preset"));

ux.clearPathPreset(state, linerPaths[0].path_key);
linerPaths.forEach(pathRow => {
    assert.strictEqual(ux.effectivePreset(state, pathRow), "Shallow");
});
ux.restoreLayerPreset(state, "liner");
assert.strictEqual(state.sources.liner, "factory");
assert.strictEqual(state.operations.liner, "Finish");
ux.restoreFactoryPresets(state);
assert.strictEqual(state.sources.cut_path, "factory");

const empty = ux.dialogMarkup({
    can_prepare: true,
    can_edit_factory_cnc: false,
    presets: [],
}, sheet, ux.sheetState(sheet));
assert.ok(panel.includes("A factory settings manager must create them."));
assert.ok(empty.includes("Vector Associations"));
const creatable = ux.dialogMarkup({
    can_prepare: true,
    can_edit_factory_cnc: true,
    presets: [],
}, sheet, ux.sheetState(sheet));
assert.ok(!creatable.includes("data-add-preset"));
assert.ok(panel.includes("No CNC tool presets have been created yet."));
assert.ok(!creatable.includes("data-operation-preset-host="));

const readonly = ux.dialogMarkup({
    can_prepare: false,
    can_edit_factory_cnc: false,
    presets: workspace.presets,
}, sheet, ux.sheetState(sheet));
assert.ok(panel.includes("Preparing operational files is not available"));
assert.ok(!readonly.includes("data-customize-path"));
assert.ok(!readonly.includes("data-path-preset-host="));

const disabledSheet = ux.sheetState(sheet);
disabledSheet.operations.liner = "Off";
assert.strictEqual(ux.effectivePreset(disabledSheet, linerPaths[0]), "Off");
assert.ok(panel.includes("This tool preset is disabled."));

assert.ok(panel.includes("mountPresetControls("));
assert.ok(panel.includes('fieldtype: "Link"'));
assert.ok(panel.includes('options: "CNC Tool Preset"'));
assert.ok(panel.includes("frappe.ui.form.Quick Entry") || panel.includes("get_query"));
assert.ok(!panel.includes("openPresetEditor("));
assert.ok(!panel.includes("save_cnc_tool_preset"));
assert.ok(panel.includes("dialog._cncNcRequest"));
assert.ok(panel.includes("get_cnc_sheet_program"));
assert.ok(panel.includes("operation_sources"));
assert.strictEqual(ux.cutPathIsEarly(["liner", "recessed_handle_cutout", "back_groove", "cut_path"]), false);
assert.ok(panel.includes("Cutting first may let the pieces move after they separate from the board."));
assert.ok(!panel.includes("GEOMETRY"));
assert.ok(!panel.includes("G01"));
assert.ok(panel.includes("generate_cnc_sheet_nc"));
assert.ok(panel.includes("Generate NC file"));
assert.ok(panel.includes("syncSheetFooter("));
assert.ok(panel.includes("preserveDialogScroll("));
assert.ok(panel.includes("paintLayerMeta("));
assert.ok(!/actions\.prepend\(download\)/.test(panel));
assert.ok(!panel.includes('data-cnc-footer-action="download"'));
assert.ok(panel.includes("not approved for a workshop machine"));
assert.ok(!panel.includes("data-cnc-program"));
assert.ok(translations.includes("إدارة الريش"));
assert.ok(translations.includes("إعدادات الملفات التشغيلية"));
assert.ok(translations.includes("استعادة إعداد المصنع"));
assert.ok(translations.includes("إعدادات ريش CNC"));
assert.ok(translations.includes("توليد ملف NC"));

console.log("dco_operational_files_presets.test.js passed");
