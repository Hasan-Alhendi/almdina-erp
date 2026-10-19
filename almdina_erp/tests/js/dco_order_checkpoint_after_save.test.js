"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const core = path.resolve(__dirname, "../../public/js/door_cutting_order/core");

function deferred() {
    let resolve;
    const promise = new Promise(complete => { resolve = complete; });
    return { promise, resolve };
}

function runtime() {
    const handlers = {};
    const scheduledUiWork = [];
    const document = {};
    const window = {
        addEventListener() {},
        setTimeout(callback) { scheduledUiWork.push(callback); },
        requestAnimationFrame(callback) { scheduledUiWork.push(callback); },
        AlmdinaPermissions: { canDocument: () => true, version: () => 1 },
    };
    const frappe = {
        almdina: {},
        provide() {},
        get_route: () => ["Form", "Door Cutting Order", window.cur_frm.doc.name],
        router: { on() {} },
        ui: { form: { on(doctype, events) {
            assert.equal(doctype, "Door Cutting Order");
            Object.assign(handlers, events);
        } } },
        show_alert() {},
        msgprint() {},
    };
    window.frappe = frappe;
    const context = vm.createContext({
        window, document, frappe, console,
        $: () => ({ on() {} }),
    });
    for (const file of ["door_cutting_order_edit_session_coordinator.js", "door_cutting_order_revision_ux.js"]) {
        vm.runInContext(fs.readFileSync(path.join(core, file), "utf8"), context, { filename: file });
    }
    const frm = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name: "DCO-CHECKPOINT", status: "Draft", docstatus: 0, modified: "M1" },
        dirty: true,
        fields_dict: {},
        is_new: () => false,
        is_dirty() { return this.dirty; },
        has_perm: () => true,
        toggle_enable(fields, enabled) { this.inputsEnabled = enabled; },
        remove_custom_button() {},
        trigger() {},
    };
    window.cur_frm = frm;
    const ux = window.AlmdinaOrderRevisionUX;
    let saveNumber = 0;

    function nextNativeSave(outcome = "success") {
        const earlierAfterSaveHandler = deferred();
        let afterSave;
        frm.save = () => {
            saveNumber += 1;
            if (outcome === "reject") return Promise.reject(new Error("native Save rejected"));
            if (outcome === "validation") return Promise.resolve();
            frm.dirty = false;
            frm.doc.modified = `M${saveNumber + 1}`;
            // Frappe's Save request can resolve before ScriptManager's serial
            // after_save chain reaches this app's handler. An earlier handler
            // is intentionally held by a promise, with no elapsed-time assumption.
            afterSave = earlierAfterSaveHandler.promise.then(() => handlers.after_save(frm));
            return Promise.resolve();
        };
        return {
            async deliverAfterSave() {
                assert.ok(afterSave, "a successful native Save scheduled after_save");
                earlierAfterSaveHandler.resolve();
                await afterSave;
            },
        };
    }

    return { frm, ux, coordinator: window.AlmdinaDcoEditSessionCoordinator, nextNativeSave };
}

async function delayedCheckpointAfterSaveKeepsEditing() {
    const { frm, ux, coordinator, nextNativeSave } = runtime();
    assert.equal(await ux.enterEditSession(frm), true);
    const checkpoint = nextNativeSave();
    assert.equal(await ux.persistOrderEditCheckpoint(frm), true);
    assert.equal(frm.is_dirty(), false);
    assert.equal(ux.isEditSessionActive(frm), true);
    await checkpoint.deliverAfterSave();
    assert.equal(ux.isEditableDraft(frm), true,
        "a delayed native after_save must preserve the acknowledged pre-plan Edit Session");
    assert.equal(frm.inputsEnabled, true);
    assert.equal(coordinator.snapshot(frm).phase, "editing");

    // Checkpoint intent is one-shot. The next explicit Save must finish editing
    // even when its after_save also runs after frm.save has already resolved.
    frm.dirty = true;
    const explicit = nextNativeSave();
    assert.equal(await ux.commitEditSession(frm), true);
    await explicit.deliverAfterSave();
    assert.equal(ux.isEditSessionActive(frm), false);
    assert.equal(frm.inputsEnabled, false);
    assert.equal(coordinator.snapshot(frm).phase, "idle");
}

async function failedCheckpointClearsIntent(outcome) {
    const { frm, ux, nextNativeSave } = runtime();
    assert.equal(await ux.enterEditSession(frm), true);
    nextNativeSave(outcome);
    if (outcome === "reject") {
        await assert.rejects(ux.persistOrderEditCheckpoint(frm), /native Save rejected/);
    } else {
        assert.equal(await ux.persistOrderEditCheckpoint(frm), false);
    }
    assert.equal(frm.is_dirty(), true);
    assert.equal(ux.isEditSessionActive(frm), true);
    assert.equal(frm.__almdina_preserve_edit_session_after_save, false,
        "a failed Save with no after_save must not retain checkpoint preserve intent");
    const explicit = nextNativeSave();
    assert.equal(await ux.commitEditSession(frm), true);
    await explicit.deliverAfterSave();
    assert.equal(ux.isEditSessionActive(frm), false,
        "an explicit Save after checkpoint failure must still finish editing");
}

async function run() {
    const tests = [
        ["delayed after_save preserves checkpoint and later explicit Save locks", delayedCheckpointAfterSaveKeepsEditing],
        ["validation failure clears checkpoint intent", () => failedCheckpointClearsIntent("validation")],
        ["rejected Save clears checkpoint intent", () => failedCheckpointClearsIntent("reject")],
    ];
    for (const [name, test] of tests) {
        try {
            await test();
            console.log(`PASS ${name}`);
        } catch (error) {
            process.exitCode = 1;
            console.error(`FAIL ${name}`);
            console.error(error);
        }
    }
}

run().catch(error => { console.error(error); process.exitCode = 1; });
