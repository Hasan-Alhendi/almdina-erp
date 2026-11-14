const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");
const panelPath = path.join(
    root,
    "public/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js"
);
const cssPath = path.join(
    root,
    "public/css/door_cutting_order_operational_files.css"
);
const translationsPath = path.join(root, "translations/ar.csv");
const windowObject = {};
vm.runInNewContext(fs.readFileSync(panelPath, "utf8"), { window: windowObject }, { filename: panelPath });
const ux = windowObject.AlmdinaOperationalFilesUX;
const panel = fs.readFileSync(panelPath, "utf8");
const css = fs.readFileSync(cssPath, "utf8");
const translations = fs.readFileSync(translationsPath, "utf8");

assert.ok(ux.dialogMarkup);
assert.ok(ux.paintNcPanel);
assert.ok(ux.sheetCardActions);
assert.ok(ux.collectProgramIssues);
assert.ok(panel.includes("download_cnc_sheet_nc"));
assert.ok(panel.includes("Generate NC file"));
assert.ok(panel.includes("data-cnc-card-download"));
assert.ok(panel.includes("syncSheetFooter("));
assert.ok(panel.includes("showGenerationIssueDialog("));
assert.ok(panel.includes("AlmdinaUi"));
assert.ok(panel.includes("errorDialog"));
assert.ok(!panel.includes("URL.createObjectURL"));
assert.ok(!panel.includes("scheduleProgram("));
assert.ok(!panel.includes("data-cnc-program"));
assert.ok(!panel.includes('translate("Simulation NC")') || panel.includes("Simulation NC prepared"));

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

const collected = ux.collectProgramIssues({
    geometry_ready: false,
    issues: [
        { code: "tool_diameter_kerf_mismatch", message: "Kerf mismatch", operation_key: "cut_path", path_key: "cut_path:a", piece_label: "1" },
        { code: "tool_diameter_kerf_mismatch", message: "Kerf mismatch", operation_key: "cut_path", path_key: "cut_path:b", piece_label: "2" },
        { code: "geometry_invalid", message: "Bad geometry", operation_key: "liner", path_key: "liner:a", piece_label: "1" },
    ],
    operations: [],
}, 1);
assert.equal(collected.uniqueCount, 3);
assert.equal(collected.issues.length, 2);
assert.ok(collected.issues.some(item => item.problem.includes("Kerf mismatch") || item.problem.includes("2 problems")));
assert.ok(collected.issues.every(item => item.action));

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
        machining: {
            associations: [
                { association_id: "association:a", name: "Outer", selection: { kind: "selected_vectors" }, profile_id: "" },
                { association_id: "association:b", name: "Inner", selection: { kind: "layer", operation_key: "cut_path" }, profile_id: "" },
            ],
            profiles: [],
        },
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
assert.ok(!dialog.includes("Generate simulation NC"));
assert.ok(!dialog.includes("data-cnc-nc-actions"));
assert.ok(!dialog.includes("Machining preview"));
assert.ok(!dialog.includes("data-cnc-program"));
assert.ok(!dialog.includes("Simulation NC</h4>") && !dialog.includes(">Simulation NC<"));
assert.ok(dialog.includes("dco-operational-sheet__body"));
assert.ok(dialog.includes("dco-operational-sheet__preview"));
assert.ok(dialog.includes("dco-operational-sheet__settings"));
assert.ok(dialog.includes("dco-operational-order__move"));
assert.ok(dialog.includes("Move earlier"));
assert.ok(dialog.includes("data-move=\"earlier\""));
assert.ok(dialog.includes('data-move="later"'));
assert.ok(dialog.includes('dco-operational-order__arrow'));
assert.ok(dialog.includes('aria-hidden="true">↓</span>'));
assert.ok(dialog.includes('<section class="dco-sheet-acc" data-sheet-section="order">'));
assert.ok(dialog.includes("data-delete-association=\"association:a\""));
assert.ok(dialog.indexOf("dco-operational-sheet__preview") < dialog.indexOf("dco-operational-sheet__settings"));

const multi = ux.dialogMarkup(
    {
        can_prepare: true,
        can_edit_factory_cnc: false,
        presets: [{ name: "Finish", enabled: 1, tool_number: "T9", tool_diameter_mm: 5 }],
    },
    {
        sheet_no: 1,
        status: "Not Generated",
        operations: [
            { operation_key: "liner", dxf_layer: "Liner", path_count: 1 },
            { operation_key: "cut_path", dxf_layer: "CUT_PATH", path_count: 1 },
        ],
        paths: [],
        machining: {
            associations: [
                { association_id: "association:liner", name: "Liner", selection: { kind: "layer", operation_key: "liner" }, profile_id: "" },
                { association_id: "association:cut", name: "Cut", selection: { kind: "layer", operation_key: "cut_path" }, profile_id: "" },
            ],
            profiles: [],
        },
        can_download_current: false,
    },
    {
        order: ["liner", "cut_path"],
        operations: { liner: "Finish", cut_path: "Finish" },
        sources: { liner: "factory", cut_path: "factory" },
        overrides: {},
        confirmed: false,
        expanded: {},
        selectedPathKey: "",
        customizing: {},
        factoryPresets: { liner: "Finish", cut_path: "Finish" },
    }
);
assert.ok(multi.includes("association:liner"));
assert.ok(/data-move="earlier"[^>]*disabled/.test(multi) || multi.includes('data-move="earlier" disabled'));
assert.ok(!ux.cutPathIsEarly(["liner", "cut_path"]));

const denied = ux.dialogMarkup(
    {
        can_prepare: false,
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
assert.ok(denied.includes("dco-operational-sheet__preview"));
assert.ok(ux.generateNcControlState({ canPrepare: false }).reason.includes("Preparing operational files is not available for your current permissions."));
assert.ok(panel.includes("Generate NC file"));
assert.equal(ux.generateNcControlState({ canPrepare: false }).disabled, true);
assert.equal(ux.generateNcControlState({ canPrepare: true, geometryReady: false, previewPending: true }).disabled, false);
assert.ok(
    ux.generateNcControlState({ canPrepare: true }).reason
        .includes("Simulation NC is for review only")
);

assert.ok(css.includes("grid-template-columns: minmax(0, 390px) minmax(16rem, 1fr)"));
assert.ok(css.includes("direction: ltr"));
assert.ok(css.includes("max-inline-size: 390px"));
assert.ok(!css.includes(".dco-operational-layers__scroll"));
assert.ok(!css.includes(".dco-operational-sheet__nc-actions"));
assert.ok(css.includes(".dco-operational-sheet-dialog .modal-body"));
assert.ok(css.includes(".dco-operational-sheet-dialog .modal-content"));
assert.ok(css.includes("overflow-y: auto"));
assert.ok(css.includes(".dco-operational-order__move"));
assert.ok(!/syncSheetFooter[\s\S]*data-cnc-footer-action="download"/.test(panel));
assert.ok(panel.includes('data-cnc-footer-action="generate"'));
assert.ok(panel.includes("preserveDialogScroll("));
assert.ok(panel.includes("paintLayerMeta("));
assert.ok(panel.includes("SHEET_PREVIEW_MAX_WIDTH_PX = 390"));
assert.ok(panel.includes("onPresetChosen("));
assert.ok(panel.includes("options.fullRefresh"));
assert.ok(panel.includes("layers.forEach(key => paintLayerMeta"));
assert.equal(ux.SHEET_PREVIEW_MAX_WIDTH_PX, 390);

const fitted = ux.fitBoard(
    { style: {}, dataset: { naturalWidth: "1220", naturalHeight: "2440" } },
    { maxWidthPx: ux.SHEET_PREVIEW_MAX_WIDTH_PX }
);
assert.equal(fitted.style.width, "390px");
assert.equal(fitted.style.maxWidth, "390px");
assert.equal(fitted.style.height, "auto");
assert.equal(fitted.style.aspectRatio, "1220 / 2440");

const scrollHost = { scrollTop: 240 };
const scrollDialog = {
    $wrapper: {
        find(selector) {
            assert.equal(selector, ".modal-body");
            return { get() { return scrollHost; } };
        },
    },
};
ux.preserveDialogScroll(scrollDialog, () => {
    scrollHost.scrollTop = 0;
});
assert.equal(scrollHost.scrollTop, 240);
assert.equal(ux.dialogScrollHost(scrollDialog), scrollHost);

assert.ok(typeof ux.paintLayerMeta === "function");
assert.ok(panel.includes("if (options.forceRemountLinks)"));
assert.ok(panel.includes("remountPresetValues("));

function fakeHost() {
    const listeners = new Map();
    const el = {
        innerHTML: "",
        querySelector(selector) {
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

assert.ok(translations.includes("توليد ملف NC"));
assert.ok(translations.includes("تنزيل ملف NC"));
assert.ok(translations.includes("ما المشكلة؟"));
assert.ok(translations.includes("أين المشكلة؟"));
assert.ok(translations.includes("ماذا أفعل؟"));
assert.ok(translations.includes("تقديم العملية"));
assert.ok(translations.includes("تأخير العملية"));
assert.ok(translations.includes("ملف NC التجريبي للمراجعة فقط"));
assert.ok(translations.includes("جارٍ تحميل مسارات القص"));
assert.ok(translations.includes("لا توجد مسارات قص متاحة لمعاينة هذا اللوح"));
assert.ok(panel.includes("requestSheetProgramPreview("));
assert.ok(panel.includes("collectCutExecutions("));

console.log("dco_operational_files_simulation_nc.test.js passed");
