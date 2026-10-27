"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order");
function deferred() {
    let resolve, reject;
    const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
    return { promise, resolve, reject };
}
function makeHarness(file) {
    const calls = [], alerts = [], events = [], invalidations = [], reloads = [];
    const frm = {
        doctype: "Door Cutting Order", generation: 1,
        doc: { doctype: "Door Cutting Order", name: "A", pieces: [], status: "At Drawing" },
        is_new() { return false; },
        reload_doc() { reloads.push(this.doc.name); return Promise.resolve(); },
    };
    const win = {
        cur_frm: frm,
        addEventListener(name, fn) { events.push({ name, fn }); },
        dispatchEvent() {},
        AlmdinaPermissions: { canDocument() { return true; } },
        AlmdinaDocumentContext: {
            capture(form) { return { identity: "Door Cutting Order::" + form.doc.name, generation: form.generation }; },
            isSameDocument(form, token) {
                return Boolean(token && token.identity === "Door Cutting Order::" + form.doc.name
                    && token.generation === form.generation);
            },
            isCurrent(form, token) {
                return this.isSameDocument(form, token) && win.cur_frm === form;
            },
            registerCleanup() {}, cancelEffect() {}, schedule() {},
        },
        AlmdinaPlanWorkspaceState: {
            invalidate(form, reason) { invalidations.push({ order: form.doc.name, reason }); },
            snapshot() { return null; },
        },
        AlmdinaCostWorkspaceState: { snapshot() { return null; } },
        AlmdinaWorkspaceSyncCoordinator: {
            invalidate(form) { invalidations.push({ order: form.doc.name, reason: "cost" }); },
            refresh() { return Promise.resolve(["plan", "cost"]); },
        },
        AlmdinaUi: {
            fileUploader(options) { win.uploader = options; return options; },
            errorDialog() { return null; },
        },
        AlmdinaLocale: { translate: x => x },
    };
    const realtime = {};
    const frappe = {
        almdina: {}, provide() { this.almdina = this.almdina || {}; },
        ui: { form: { on() {} } },
        realtime: { on(name, fn) { realtime[name] = fn; }, off() {} },
        call(options) {
            const d = deferred();
            calls.push({ ...d, ...options });
            return d.promise;
        },
        show_alert(message) { alerts.push(message); },
        msgprint() {}, throw(message) { throw Error(message); },
    };
    const downloads = [];
    win.AlmdinaFrontend = {
        // Transport is certified in error_diagnostics.test.js. This harness
        // isolates the document-generation ownership of delayed completions.
        ownedRpc(method, args, options) {
            return frappe.call({ method, args, freeze: options.freeze })
                .then(response => response.message);
        },
    };
    const document = {
        body: { appendChild() {}, removeChild() {} },
        createElement() { return { click() { downloads.push(this.download); } }; },
    };
    const ctx = vm.createContext({
        window: win, frappe, document, console, Promise, Array, Object, Set, Map,
        String, Number, Boolean, Date, Uint8Array, Math,
        Blob: class Blob { constructor(parts) { this.parts = parts; } },
        URL: { createObjectURL() { return "blob:test"; }, revokeObjectURL() {} },
        atob: value => Buffer.from(value, "base64").toString("binary"),
        btoa: value => Buffer.from(value, "binary").toString("base64"),
        setTimeout() {}, __: x => x,
        CustomEvent: class CustomEvent { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
    });
    vm.runInContext(fs.readFileSync(path.join(root, file), "utf8"), ctx, { filename: file });
    function visit(name) {
        frm.generation += 1;
        frm.doc = { doctype: "Door Cutting Order", name, pieces: [], status: "At Drawing" };
    }
    return { frm, win, frappe, calls, alerts, invalidations, reloads, realtime, downloads, visit };
}

test("recalculation rejects A -> B and A -> B -> A late status, and does not reuse A generation", async () => {
    const h = makeHarness("cutting_plan/door_cutting_order_plan_recalculation_job.js");
    const job = h.win.AlmdinaPlanRecalculationJob;
    const a = job.fetchStatus(h.frm);
    assert.equal(h.calls.at(-1).args.order_name, "A");
    h.visit("B");
    job.bind(h.frm);
    h.calls[0].resolve({ message: { status: "running", generation: 99 } });
    await a;
    assert.equal(job.snapshot(h.frm).status, "idle", "A cannot paint B");
    const b = job.fetchStatus(h.frm);
    h.calls[1].resolve({ message: { status: "queued", generation: 1 } });
    await b;
    assert.equal(job.snapshot(h.frm).generation, 1, "A generation cannot reject B generation");
    h.visit("A");
    job.bind(h.frm);
    const oldA = job.fetchStatus(h.frm);
    h.visit("B");
    h.visit("A");
    job.bind(h.frm);
    h.calls[2].resolve({ message: { status: "completed", generation: 999 } });
    await oldA;
    assert.equal(job.snapshot(h.frm).status, "idle", "a prior visit to the same name is not current");
});

test("recalculation ignores delayed enqueue, out-of-order status and stale refresh completion", async () => {
    const h = makeHarness("cutting_plan/door_cutting_order_plan_recalculation_job.js");
    const job = h.win.AlmdinaPlanRecalculationJob;
    const a = job.enqueueAfterSave(h.frm, { resources: ["plan"] });
    h.visit("B");
    h.calls[0].resolve({ message: { queued: true, status: "queued", generation: 17 } });
    await a;
    assert.equal(job.snapshot(h.frm).status, "idle");
    assert.equal(h.invalidations.length, 0);
    const older = job.fetchStatus(h.frm);
    const newer = job.fetchStatus(h.frm);
    h.calls[2].resolve({ message: { status: "running", generation: 4 } });
    await newer;
    h.calls[1].resolve({ message: { status: "queued", generation: 4 } });
    await older;
    assert.equal(job.snapshot(h.frm).status, "running", "an older status response must not regress progress");
    job.applyState(h.frm, { status: "queued", generation: 5 });
    const refresh = deferred();
    let refreshStarted = false;
    h.win.AlmdinaWorkspaceSyncCoordinator.refresh = () => { refreshStarted = true; return refresh.promise; };
    h.win.AlmdinaCostWorkspaceState.snapshot = form => ({
        data: { price_approval_status: form.doc.name === "A" ? "Approved" : "Unapproved" },
    });
    let invalidationNotices = 0;
    h.win.AlmdinaFinalPriceApprovalUX = { notifyAutoInvalidation() { invalidationNotices += 1; } };
    const finishing = job.fetchStatus(h.frm);
    h.calls[3].resolve({ message: { status: "completed", generation: 5 } });
    for (let i = 0; i < 5 && !refreshStarted; i += 1) await Promise.resolve();
    assert.equal(refreshStarted, true);
    h.visit("A");
    h.visit("B");
    refresh.resolve([]);
    await finishing;
    assert.equal(invalidationNotices, 0, "stale refresh must not notify the next order");
});

test("drawing approval does not reload or announce another order or another visit", async () => {
    const h = makeHarness("cutting_plan/door_cutting_order_drawing_approval_ux.js");
    h.frm.doc.system_plan_json = JSON.stringify({ sheets: [{ pieces: [{}] }] });
    const approval = h.win.AlmdinaDrawingApprovalUX;
    // Approval is invoked through the single-source form action.
    h.frappe.confirm = (_message, callback) => callback();
    h.frappe.prompt = () => {};
    const trigger = () => {
        // Existing source selection is synchronous for a single valid plan.
        const original = h.frappe.call.bind(h.frappe);
        approval.approvalSources(h.frm);
        // The actual entry point is the Drawing stage action, which is closure-private.
        return original;
    };
    trigger();
    // Use the exposed Frappe handler's button path in production when registered.
    // Direct closure entry is intentionally not exported; execute the source with one test-only tail.
    const code = fs.readFileSync(path.join(root, "cutting_plan/door_cutting_order_drawing_approval_ux.js"), "utf8");
    const instrumented = code.replace("window.AlmdinaDrawingApprovalUX = Object.freeze({", "window.__approvalForTest = submitApproval;\n\twindow.AlmdinaDrawingApprovalUX = Object.freeze({");
    const ctx = vm.createContext({ window: h.win, frappe: h.frappe, console, __: x => x, setTimeout() {} });
    vm.runInContext(instrumented, ctx);
    const a = h.win.__approvalForTest(h.frm, "System");
    assert.equal(h.calls[0].args.order_name, "A");
    h.visit("B");
    h.calls[0].resolve({ message: {} });
    await a;
    assert.equal(h.reloads.length, 0);
    assert.equal(h.alerts.length, 0);
    const firstA = h.win.__approvalForTest(h.frm, "System");
    h.visit("A");
    h.visit("B");
    h.calls[1].resolve({ message: {} });
    await firstA;
    assert.equal(h.reloads.length, 0);
});

test("secure DXF upload keeps server target A but prevents stale B reload and messages", async () => {
    const h = makeHarness("cutting_plan/secure_dxf_upload.js");
    h.frappe.almdina.upload_production_dxf(h.frm);
    const first = h.win.uploader.on_success({ file_url: "/private/files/A.dxf" });
    assert.equal(h.calls[0].args.order_name, "A", "backend mutation remains targeted at A");
    h.visit("B");
    h.calls[0].resolve({ message: { ok: true } });
    await first;
    assert.equal(h.reloads.length, 0);
    assert.equal(h.alerts.length, 0);
    assert.equal(h.invalidations.length, 0);
    h.visit("A");
    h.frappe.almdina.upload_production_dxf(h.frm);
    const second = h.win.uploader.on_success({ file_url: "/private/files/A2.dxf" });
    h.visit("B");
    h.visit("A");
    h.calls[1].resolve({ message: { ok: true } });
    await second;
    assert.equal(h.reloads.length, 0, "A -> B -> A must not reload the later visit");
});

test("validated DXF export abandons old form response and old normalize response", async () => {
    const h = makeHarness("cutting_plan/secure_dxf_export.js");
    const minimalPlan = {
        full_board_width_cm: 100, full_board_length_cm: 100, trim_cm: 0,
        sheets: [{ sheet_no: 1, full_width_cm: 100, full_length_cm: 100,
            pieces: [{ id: 1, x: 1, y: 1, w: 10, h: 10 }] }],
    };
    const pending = h.frappe.almdina.export_validated_dxf(h.frm);
    h.visit("B");
    h.calls[0].resolve({ message: { plan: structuredClone(minimalPlan) } });
    await pending;
    assert.equal(h.calls.length, 1, "A response must not submit a normalization request under B");
    h.visit("A");
    const again = h.frappe.almdina.export_validated_dxf(h.frm);
    h.calls[1].resolve({ message: { plan: structuredClone(minimalPlan) } });
    for (let i = 0; i < 6 && h.calls.length < 3; i += 1) await Promise.resolve();
    assert.equal(h.calls.length, 3, "a current export reaches normalize");
    h.visit("B");
    h.calls[2].resolve({ message: { filename: "A.dxf", content_b64: "RkFLRQ==" } });
    await again;
    assert.equal(h.downloads.length, 0, "late normalize must not download after navigation");
    // Explicit by-name API remains independent of the visible Desk form.
    const explicit = h.frappe.almdina.export_order_dxf("EXPLICIT");
    h.calls[3].resolve({ message: { plan: structuredClone(minimalPlan) } });
    for (let i = 0; i < 6 && h.calls.length < 5; i += 1) await Promise.resolve();
    assert.equal(h.calls[4].args.order_name, "EXPLICIT");
    h.calls[4].resolve({ message: { filename: "EXPLICIT.dxf", content_b64: "RkFLRQ==" } });
    await explicit;
    assert.equal(h.downloads.length, 1);
});


test("DXF keeps the original edge-profile cache for L-shaped notch compensation", async () => {
    const h = makeHarness("cutting_plan/secure_dxf_export.js");
    h.frm._dco_side_edge_profiles = new Map([
        ["EDGE-2MM", { thickness_mm: 2, rate_usd_per_meter: 1 }],
    ]);
    h.frm.doc.default_edge_type = "EDGE-2MM";
    h.frm.doc.pieces = [{
        piece_type: "L-Shaped Corner", clipped_corner_position: "top_right",
        clipped_corner_width_cm: 2, clipped_corner_length_cm: 2,
        edge_break: 1,
    }];
    let capturedThickness = null;
    h.win.AlmdinaLinerGeometry = {
        contourNotchFromOrder(sourceForm) {
            capturedThickness = sourceForm._dco_side_edge_profiles?.get("EDGE-2MM")?.thickness_mm;
            throw new Error("STOP_AFTER_INPUT_SNAPSHOT");
        },
    };
    const plan = {
        sheets: [{ pieces: [{ source_piece_no: 1, x: 1, y: 1, w: 10, h: 10 }] }],
    };
    const operation = h.frappe.almdina.export_validated_dxf(h.frm);
    h.frm._dco_side_edge_profiles.clear();
    h.calls[0].resolve({ message: { plan } });
    await assert.rejects(operation, /STOP_AFTER_INPUT_SNAPSHOT/);
    assert.equal(capturedThickness, 2, "form-owned profiles must be frozen with DXF inputs");
});


test("late enqueue within the same visit cannot regress a newer realtime job state", async () => {
    const h = makeHarness("cutting_plan/door_cutting_order_plan_recalculation_job.js");
    const job = h.win.AlmdinaPlanRecalculationJob;
    const pending = job.enqueueAfterSave(h.frm, { resources: ["plan"] });
    job.applyState(h.frm, { status: "running", generation: 8 });
    h.calls[0].resolve({ message: { queued: true, status: "queued", generation: 8 } });
    await pending;
    assert.equal(job.snapshot(h.frm).status, "running");
    assert.equal(h.invalidations.length, 1, "accepted enqueue still invalidates dependent cost");
});
