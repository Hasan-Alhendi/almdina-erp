"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const pageSource = fs.readFileSync(path.join(root, "almdina_erp/page/cnc_sheet_settings/cnc_sheet_settings.js"), "utf8");
const staleArtcam = { markup() { return '<form data-artcam-editor><input data-field="name"></form>'; } };
const stalePanel = { dialogMarkup() { return "stale"; } };
const windowObject = {
    location: { origin: "http://almdina.local:8000" },
    AlmdinaFrontend: { ensureStylesheet() { return Promise.resolve(); } },
    AlmdinaArtcamMachining: staleArtcam,
    AlmdinaOperationalFilesUX: stalePanel,
};
const requests = [];
const main = { innerHTML: "" };
const wrapper = { querySelector(selector) { return selector === ".layout-main-section" ? main : null; } };
const frappe = {
    pages: { "cnc-sheet-settings": {} },
    utils: { escape_html(value) { return String(value); } },
    assets: {
        load_asset(assetPath, url) {
            requests.push({ path: assetPath, url });
            assert.equal(new URL(url).pathname, assetPath);
            assert.equal(new URL(url).searchParams.get("v"), "1");
            const file = path.join(root, "public", assetPath.replace("/assets/almdina_erp/", ""));
            vm.runInNewContext(fs.readFileSync(file, "utf8"), { window: windowObject });
            return Promise.resolve();
        },
    },
    require(asset) {
        assert.equal(asset, "/assets/almdina_erp/js/almdina_ui.js");
        return Promise.resolve();
    },
};
const context = {
    window: windowObject, frappe, URL, Promise,
    $() { return { off() { return this; }, on() { return this; } }; },
};
vm.runInNewContext(pageSource, context);

async function mainTest() {
    frappe.pages["cnc-sheet-settings"].on_page_load(wrapper);
    await wrapper.__almdinaCncSheetBoot;
    assert.deepEqual(requests.map(row => path.basename(row.path)), [
        "artcam_machining_ux.js", "door_cutting_order_operational_files_ux.js",
    ]);
    assert.notEqual(windowObject.AlmdinaArtcamMachining, staleArtcam);
    assert.notEqual(windowObject.AlmdinaOperationalFilesUX, stalePanel);
    assert.equal(windowObject.AlmdinaArtcamMachining.assetRevision, 1);
    assert.equal(windowObject.AlmdinaOperationalFilesUX.assetRevision, 1);
    const sheet = { sheet_no: 1, machining: { profiles: [], associations: [] } };
    const workspace = { can_prepare: false, cnc_machines: [] };
    const editor = windowObject.AlmdinaArtcamMachining.markup(workspace, sheet, {});
    assert.match(editor, /data-field="source" disabled>/);
    assert.match(editor, /data-artcam-calculate disabled>/);
    const panel = windowObject.AlmdinaOperationalFilesUX.dialogMarkup(workspace, sheet, {});
    assert.match(panel, /data-sheet-section="associations"[^]*?<fieldset class="dco-artcam-readonly" disabled>/);
    console.log("cnc_sheet_asset_freshness.test.js passed");
}

mainTest().catch(error => { console.error(error); process.exitCode = 1; });
