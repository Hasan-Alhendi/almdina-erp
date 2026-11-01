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

assert.ok(ux.dialogMarkup);
assert.ok(ux.paintNcPanel);
assert.ok(ux.sheetCardActions);
assert.ok(panel.includes("download_cnc_sheet_nc"));
assert.ok(panel.includes("Generate simulation NC"));
assert.ok(panel.includes("data-cnc-card-download"));
assert.ok(!panel.includes("URL.createObjectURL"));

const markup = ux.programMarkup({
    sheet_width_mm: 1000,
    sheet_length_mm: 2000,
    geometry_ready: false,
    machine_ready: false,
    nc_export_ready: false,
    issues: [{ code: "geometry_invalid", message: "This path geometry cannot be used.", operation_key: "cut_path", path_key: "cut_path:a", piece_label: "1.1" }],
    operations: [
        {
            operation_key: "cut_path",
            toolpaths: [
                {
                    path_key: "cut_path:a",
                    operation_key: "cut_path",
                    piece_label: "1.1",
                    ready: false,
                    issues: ["geometry_invalid"],
                    issue_messages: ["This path geometry cannot be used."],
                    points: [[0, 0], [10, 0]],
                    motions: [],
                },
            ],
        },
    ],
});
assert.ok(markup.list.includes("geometry problems block simulation NC generation") || markup.list.includes("{0} geometry problems"));
assert.ok(!markup.list.includes("data-cnc-generate-nc"));

const card = ux.sheetCardActions({
    sheet_no: 1,
    status: "Generated",
    can_download_current: true,
    download_is_previous: false,
    operational_file: "CNC-FILE-1",
    generated_file: "/private/files/a.sim.nc",
});
assert.ok(card.includes("data-cnc-card-download"));
assert.ok(card.includes("Download simulation NC"));

const needs = ux.sheetCardActions({
    sheet_no: 1,
    status: "Needs Regeneration",
    can_download_current: true,
    download_is_previous: true,
    operational_file: "CNC-FILE-1",
    generated_file: "/private/files/a.sim.nc",
});
assert.ok(needs.includes("Download previous simulation NC"));
assert.ok(needs.includes("needs regeneration") || needs.includes("Needs regeneration"));

const dialog = ux.dialogMarkup(
    {
        can_prepare: true,
        can_edit_factory_cnc: false,
        presets: [{ name: "Finish", enabled: 1, tool_number: "T9", tool_diameter_mm: 5 }],
    },
    {
        sheet_no: 1,
        status: "Not Generated",
        operations: [{ operation_key: "cut_path", dxf_layer: "CUT_PATH", path_count: 1 }],
        paths: [{ path_key: "cut_path:a", operation_key: "cut_path", piece_label: "1.1" }],
        can_download_current: false,
    },
    {
        order: ["cut_path"],
        operations: { cut_path: "Finish" },
        sources: { cut_path: "factory" },
        overrides: {},
        confirmed: false,
        expanded: {},
        selectedPathKey: "",
        customizing: {},
        factoryPresets: { cut_path: "Finish" },
    }
);
assert.ok(dialog.includes("Generate simulation NC"));
assert.ok(dialog.includes("data-cnc-nc-actions"));
assert.ok(dialog.includes("Simulation NC is for review only"));

function fakeHost() {
    const listeners = new Map();
    const el = {
        innerHTML: "",
        querySelector(selector) {
            if (!this.innerHTML.includes(selector.replace(/\[|\]/g, "")) && !selector.includes("data-cnc-download-nc")) {
                // fall through to attribute search below
            }
            if (selector === "[data-cnc-download-nc]" || selector.includes("data-cnc-download-nc")) {
                const match = this.innerHTML.match(/data-cnc-download-nc[^>]*/);
                if (!match) return null;
                const tag = match[0];
                const operational = (tag.match(/data-operational-file="([^"]*)"/) || [])[1] || "";
                const fileUrl = (tag.match(/data-file-url="([^"]*)"/) || [])[1] || "";
                return {
                    getAttribute(name) {
                        if (name === "data-operational-file") return operational;
                        if (name === "data-file-url") return fileUrl;
                        return null;
                    },
                    addEventListener(type, fn) {
                        listeners.set(type, fn);
                    },
                };
            }
            return null;
        },
    };
    return el;
}

const host = fakeHost();
ux.paintNcPanel(host, {
    verification: { ok: true },
    tool_number: "T9",
    path_count: 1,
    pass_count: 1,
    status: "Generated",
    message: "Simulation NC prepared. This file is not approved for a workshop machine.",
    text: "G90\nM30\n",
    operational_file: "CNC-FILE-1",
    file_url: "/private/files/a.sim.nc",
    sheet_no: 1,
}, { frm: { doc: { name: "DCO-1" } } });
assert.ok(host.innerHTML.includes("data-cnc-download-nc"), "download button should appear after successful generation payload");
assert.ok(host.innerHTML.includes("CNC-FILE-1"));
assert.ok(host.innerHTML.includes("/private/files/a.sim.nc"));
assert.ok(!host.innerHTML.includes("blob:"));
const button = host.querySelector("[data-cnc-download-nc]");
assert.ok(button);
assert.equal(button.getAttribute("data-operational-file"), "CNC-FILE-1");
assert.equal(button.getAttribute("data-file-url"), "/private/files/a.sim.nc");

assert.ok(translations.includes("توليد NC تجريبي"));
assert.ok(translations.includes("تنزيل النسخة السابقة من NC التجريبي"));
assert.ok(translations.includes("ملف NC التجريبي للمراجعة فقط"));

console.log("dco_operational_files_simulation_nc.test.js passed");
