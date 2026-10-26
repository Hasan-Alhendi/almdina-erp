"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname,
    "../../public/js/door_cutting_order/cutting_plan/secure_dxf_export.js"), "utf8");
const prefix = "almdina_erp.almdina_erp.services.dxf_export_service.";
const plan = {
    full_board_width_cm: 100,
    full_board_length_cm: 100,
    kerf_mm: 5,
    trim_cm: 0,
    sheets: [{
        sheet_no: 1,
        full_width_cm: 100,
        full_length_cm: 100,
        pieces: [{ id: 1, label: "1.1", x: 10, y: 10, w: 20, h: 30 }],
    }],
};

function harness({ preferOriginal = false, includeSawCenters = true, rejection = null,
    archive = false } = {}) {
    const calls = [];
    const downloads = [];
    // Includes non-UTF-8 bytes: original downloads must never decode/re-encode DXF.
    const original = Buffer.from([0, 255, 128, 13, 10, 65]);
    const snapshot = JSON.stringify(plan);
    const response = {
        plan: JSON.parse(snapshot),
        prefer_original_upload: preferOriginal,
        include_saw_centers: includeSawCenters,
    };
    const frappe = {
        almdina: {},
        provide() {},
        ui: { form: { on() {} } },
        show_alert() {},
        throw(message) { throw new Error(message); },
        call({ method, args }) {
            const name = method.slice(prefix.length);
            calls.push({ name, args });
            if (name === "get_validated_dxf_plan") {
                if (archive) return Promise.reject(new Error("Historical manufacturing export rejected"));
                if (rejection) return Promise.reject(rejection);
                return Promise.resolve({ message: response });
            }
            if (name === "download_uploaded_dxf") {
                if (!preferOriginal && !archive) {
                    return Promise.reject(new Error("Original upload has no manufacturing CUT_PATH"));
                }
                return Promise.resolve({ message: {
                    filename: "original.dxf", content_b64: original.toString("base64"),
                } });
            }
            assert.equal(name, "normalize_dxf_for_autocad");
            return Promise.resolve({ message: {
                filename: "manufacturing.dxf", content_b64: args.content_b64,
            } });
        },
    };
    const window = { frappe };
    vm.runInNewContext(source, {
        window, frappe, console, atob, btoa, Uint8Array,
        __: message => message,
        Blob: class { constructor(parts) { this.parts = parts; } },
        URL: {
            createObjectURL(blob) {
                downloads.push(Buffer.from(blob.parts[0]));
                return "blob:test";
            },
            revokeObjectURL() {},
        },
        document: {
            body: { appendChild() {}, removeChild() {} },
            createElement: () => ({ click() {} }),
        },
        setTimeout(callback) { callback(); },
    });
    return {
        export: (source, options) => frappe.almdina.export_order_dxf("DCO-ROUTING", source, options),
        calls, downloads, original, response,
        assertUnchanged() { assert.equal(JSON.stringify(response.plan), snapshot); },
    };
}

function entities(bytes, layer) {
    const text = bytes.toString("ascii").split("0\r\nSECTION\r\n2\r\nENTITIES\r\n")[1];
    assert.ok(text, "generated DXF has an entity section");
    return text.split(/(?<=\r\n)0\r\n/).filter(entity => entity.includes(`8\r\n${layer}\r\n`));
}

async function run() {
    const stale = { hasOriginalFile: true, preferOriginalUpload: true, originalIsManufacturingReady: true };
    const absent = harness();
    // Reproduces the reported rejection: cached flags claim the designer file is ready.
    await absent.export("Approved", stale);
    assert.deepEqual(absent.calls.map(call => call.name), ["get_validated_dxf_plan", "normalize_dxf_for_autocad"]);
    const cutPaths = entities(absent.downloads[0], "CUT_PATH");
    assert.equal(cutPaths.length, 1, "one closed cutter contour for the single door");
    assert.deepEqual([...cutPaths[0].matchAll(/10\r\n([^\r]+)\r\n20\r\n([^\r]+)\r\n/g)]
        .map(match => [Number(match[1]), Number(match[2])]),
    [[97.5, 597.5], [302.5, 597.5], [302.5, 902.5], [97.5, 902.5]],
    "CUT_PATH is offset 2.5 mm from the finished door, in the existing DXF coordinate frame");
    assert.equal(new Set(cutPaths).size, cutPaths.length, "generated paths are not duplicated");
    assert.equal(entities(absent.downloads[0], "GEOMETRY").length, 4);
    await absent.export("Approved", {});
    assert.deepEqual(absent.downloads[1], absent.downloads[0], "repeat download has identical geometry");
    absent.assertUnchanged();

    for (const source of ["Approved", "Custom", "uploaded", "uploaded dxf", "uploaded_dxf", "dxf", null]) {
        const missing = harness();
        await missing.export(source, stale);
        assert.deepEqual(missing.downloads[0], absent.downloads[0], `${source}: server overrides stale ready flags`);
        assert.equal(missing.calls[0].name, "get_validated_dxf_plan");
        if (source) assert.equal(missing.calls[0].args.plan_source, source);
        missing.assertUnchanged();

        const present = harness({ preferOriginal: true });
        await present.export(source, {
            hasOriginalFile: false, preferOriginalUpload: false, originalIsManufacturingReady: false,
        });
        assert.deepEqual(present.calls.map(call => call.name), ["get_validated_dxf_plan", "download_uploaded_dxf"]);
        assert.deepEqual(present.downloads[0], present.original, `${source}: keep original bytes with valid paths`);
        await present.export(source, stale);
        assert.deepEqual(present.downloads[1], present.original);
        present.assertUnchanged();
    }

    const draft = harness({ preferOriginal: true, includeSawCenters: false });
    await draft.export("Custom", stale);
    assert.deepEqual(draft.downloads[0], draft.original, "unapproved Custom keeps designer original");

    for (const includeSawCenters of [false, true]) {
        const system = harness({ includeSawCenters });
        await system.export("System", stale);
        assert.equal(entities(system.downloads[0], "CUT_PATH").length > 0, includeSawCenters);
        system.assertUnchanged();
    }

    for (const reason of ["partial CUT_PATH", "invalid CUT_PATH", "unsafe CUT_PATH", "stale plan", "permission denied"]) {
        const invalid = harness({ rejection: new Error(reason) });
        await assert.rejects(invalid.export("Approved", stale), error => error.message === reason);
        assert.deepEqual(invalid.calls.map(call => call.name), ["get_validated_dxf_plan"]);
        assert.equal(invalid.downloads.length, 0, "validation rejection never falls back to raw or generated DXF");
    }

    const historical = harness({ archive: true });
    await historical.export("Custom", { archiveOnly: true, preferOriginalUpload: false });
    assert.deepEqual(historical.calls.map(call => call.name), ["download_uploaded_dxf"]);
    assert.deepEqual(historical.downloads[0], historical.original, "historical archive bypasses manufacturing validation");

    const delivered = harness({ archive: true });
    await delivered.export("Custom", { frm: { doc: { name: "DCO-ROUTING", status: "Delivered" } } });
    assert.deepEqual(delivered.calls.map(call => call.name), ["download_uploaded_dxf"]);
    assert.deepEqual(delivered.downloads[0], delivered.original);

    const deliveredApproved = harness();
    await deliveredApproved.export("Approved", { ...stale, frm: { doc: { name: "DCO-ROUTING", status: "Delivered" } } });
    assert.deepEqual(deliveredApproved.downloads[0], absent.downloads[0], "Delivered Approved stays manufacturing-only");

    console.log("Approved DXF server-authoritative routing, geometry, safety and archive regressions passed");
}

run().catch(error => { console.error(error); process.exitCode = 1; });
