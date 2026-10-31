const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");
const panelPath = path.join(
    root,
    "public/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js"
);
const registryPath = path.join(
    root,
    "public/js/door_cutting_order/core/door_cutting_order_workspace_asset_registry.js"
);
const translationsPath = path.join(root, "translations/ar.csv");

const windowObject = {};
vm.runInNewContext(fs.readFileSync(panelPath, "utf8"), { window: windowObject }, { filename: panelPath });
const ux = windowObject.AlmdinaOperationalFilesUX;

const panel = fs.readFileSync(panelPath, "utf8");
const registry = fs.readFileSync(registryPath, "utf8");
const translations = fs.readFileSync(translationsPath, "utf8");

assert.strictEqual(ux.cutPathIsEarly(["liner", "recessed_handle_cutout", "back_groove", "cut_path"]), false);
assert.strictEqual(ux.cutPathIsEarly(["cut_path", "liner"]), true);
assert.strictEqual(ux.cutPathIsEarly(["cut_path"]), false);

const inherited = {
    operations: { liner: "Finish", cut_path: "Finish" },
    overrides: { "liner:piece-a:liner_1": "Shallow" },
};
const linerPath = { path_key: "liner:piece-a:liner_1", operation_key: "liner" };
assert.strictEqual(ux.effectivePreset(inherited, linerPath), "Shallow");
delete inherited.overrides[linerPath.path_key];
assert.strictEqual(ux.effectivePreset(inherited, linerPath), "Finish");

const workspace = {
    presets: [
        { name: "Finish", tool_number: "T9", tool_diameter_mm: 6, enabled: true },
        { name: "Wide", tool_number: "T9", tool_diameter_mm: 8, enabled: true },
        { name: "Other", tool_number: "T8", tool_diameter_mm: 6, enabled: true },
        { name: "Off", tool_number: "T9", tool_diameter_mm: 6, enabled: false },
    ],
};
const sheet = {
    paths: [
        { path_key: "cut", operation_key: "cut_path" },
        { path_key: "liner", operation_key: "liner" },
    ],
};
assert.strictEqual(
    ux.toolConflict(workspace, sheet, { operations: { cut_path: "Finish", liner: "Wide" }, overrides: {} }),
    "diameter"
);
assert.strictEqual(
    ux.toolConflict(workspace, sheet, { operations: { cut_path: "Finish", liner: "Other" }, overrides: {} }),
    "number"
);
assert.strictEqual(
    ux.toolConflict(workspace, sheet, { operations: { cut_path: "Off", liner: "Off" }, overrides: {} }),
    "disabled"
);
assert.strictEqual(
    ux.toolConflict(workspace, sheet, { operations: { cut_path: "Finish", liner: "Finish" }, overrides: {} }),
    ""
);

assert.ok(panel.includes("AlmdinaCuttingPlanRender.build"));
assert.ok(panel.includes("data-path-key"));
assert.ok(panel.includes("viewed_plan_token"));
assert.ok(panel.includes("Move earlier"));
assert.ok(panel.includes("ArrowUp"));
assert.ok(panel.includes("draggable"));
assert.ok(panel.includes("Discard the unsaved changes?"));
assert.ok(!panel.includes("GEOMETRY"));
assert.ok(!panel.includes("G01"));
assert.ok(!panel.includes(".nc"));
assert.ok(!panel.includes("Download"));
assert.ok(registry.includes("door_cutting_order_cutting_plan_renderer.js"));
assert.ok(translations.includes("تقديم القص قد يؤدي إلى تحرك الدرفات بعد فصلها عن اللوح."));
assert.ok(translations.includes("فتح إعدادات اللوح"));

console.log("dco_operational_files_phase2.test.js passed");
