"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(file) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js/door_cutting_order", file), "utf8");
}

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}

function settings() {
    return { packing_mode: "optimal", cutting_machine_type: "Auto", kerf_mm: 3,
        trim_margin_mm: 5, optimization_time_limit_sec: 30 };
}

class Control {
    constructor(name, value) {
        this.name = name;
        this.value = value;
        this.disabled = false;
        this.attributes = name ? { "data-almdina-plan-setting": name } : {};
        this.handlers = [];
        this.length = 1;
    }
    attr(name, value) {
        if (value === undefined) return this.attributes[name];
        this.attributes[name] = value;
        return this;
    }
    removeAttr(name) { delete this.attributes[name]; return this; }
    prop(name, value) {
        if (value === undefined) return this[name];
        this[name] = value;
        return this;
    }
    val(value) {
        if (value === undefined) return this.value;
        this.value = value;
        return this;
    }
    on(_events, handler) { this.handlers.push(handler); return this; }
    off() { this.handlers = []; return this; }
    toggleClass() { return this; }
    trigger() { return this; }
    is() { return false; }
}

class Group {
    constructor(items = []) { this.items = items; this.length = items.length; }
    each(callback) { this.items.forEach((item, index) => callback(index, item)); return this; }
    first() { return this.items[0] || new Group(); }
    on(events, handler) { this.items.forEach(item => item.on(events, handler)); return this; }
    off() { this.items.forEach(item => item.off()); return this; }
    remove() { return this; }
    toggleClass() { return this; }
    find() { return new Group(); }
}

function environment() {
    const handlers = [];
    const commitFlight = deferred();
    const calls = [];
    const seed = settings();
    let previewFlight = null;
    let previewPending = false;
    const host = {
        length: 1, editor: false, fields: new Map(), recalculate: new Control(null, "recalculate"),
        delegated: null,
        children(selector) {
            if (selector !== ".dco-plan-settings-editor" || !this.editor) return new Group();
            return {
                length: 1,
                first: () => ({ find: () => new Group([...this.fields.values()]), toggleClass() {} }),
                remove: () => { this.editor = false; this.fields.clear(); },
            };
        },
        prepend() {
            this.editor = true;
            this.fields = new Map(Object.entries(seed).map(([key, value]) => [key, new Control(key, value)]));
            return this;
        },
        find(selector) {
            const items = [];
            if (selector.includes("[data-almdina-plan-setting]")) items.push(...this.fields.values());
            if (selector.includes(".dco-recalculate-plan")) items.push(this.recalculate);
            return new Group(items);
        },
        off() { this.delegated = null; return this; },
        on(_events, _selector, callback) { this.delegated = callback; return this; },
        input(name, value, force = false) {
            const control = this.fields.get(name);
            assert.ok(control, `missing setting ${name}`);
            if (control.disabled && !force) return false;
            control.val(value);
            control.handlers.forEach(handler => handler.call(control));
            if (this.delegated) this.delegated();
            return true;
        },
    };
    const frm = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name: "DCO-1", docstatus: 0, status: "Draft" },
        fields_dict: { plan_control_actions: { $wrapper: host } },
        is_new() { return false; }, is_dirty() { return false; },
        trigger(event) { handlers.forEach(map => map[event] && map[event](this)); },
    };
    const window = {
        cur_frm: frm,
        addEventListener() {},
        dispatchEvent() {},
        requestAnimationFrame(callback) { callback(); },
        AlmdinaPermissions: { canDocument() { return true; } },
        AlmdinaPlanFieldAccessAdapter: { apply() {} },
        AlmdinaPlanWorkspacePresenterAdapter: { activeSettings() { return { ...seed }; }, project() {} },
        AlmdinaPlanPreviewPresenter: {
            renderActionMessage() {}, renderPreviewPlan() {}, renderPersistedEditingState() {},
            restorePersistedPresentation() {},
        },
        AlmdinaPlanWorkspaceAPI: {
            preview(_name, requested) {
                calls.push(["preview", requested.packing_mode]);
                if (previewPending) { previewFlight = deferred(); return previewFlight.promise; }
                return Promise.resolve({
                    preview_id: "D", plan: { sheets: [{}] },
                    summary: { settings: requested, validation: { status: "Valid", needs_recalculation: false } },
                });
            },
            commitPreview(_name, id) { calls.push(["commit", id]); return commitFlight.promise; },
        },
    };
    const frappe = {
        ui: { form: { on(_doctype, mapping) { handlers.push(mapping); } } },
        utils: { escape_html: String }, msgprint() {}, show_alert() {},
    };
    const document = {
        getElementById() { return null; }, createElement() { return {}; }, head: { appendChild() {} },
    };
    const context = vm.createContext({ window, document, frappe, $: item => item, __: String, console,
        CustomEvent: class { constructor(name, options) { this.name = name; this.detail = options.detail; } },
        structuredClone, Promise, Set, WeakMap, Map });
    for (const file of [
        "core/door_cutting_order_workspace_store.js",
        "core/door_cutting_order_edit_session_coordinator.js",
        "cutting_plan/door_cutting_order_plan_edit_session_ux.js",
        "cutting_plan/door_cutting_order_plan_preview_session.js",
        "cutting_plan/door_cutting_order_plan_preview_edit_ux.js",
    ]) vm.runInContext(source(file), context, { filename: file });
    const store = window.AlmdinaWorkspaceStore.create("plan");
    const requestId = store.beginLoad("Door Cutting Order::DCO-1");
    store.resolveLoad("Door Cutting Order::DCO-1", requestId, { approved_plan: "" });
    window.AlmdinaPlanWorkspaceState = {
        storeFor() { return store; }, snapshot() { return store.snapshot(); },
        load() { return Promise.resolve(store.snapshot()); },
    };
    const coordinator = window.AlmdinaDcoEditSessionCoordinator;
    const preview = window.AlmdinaPlanPreviewSession;
    return { frm, host, store, coordinator, preview, commitFlight, calls,
        setPreviewPending() { previewPending = true; },
        finishPreview(id, requested) {
            previewFlight.resolve({ preview_id: id, plan: { sheets: [{}] },
                summary: { settings: requested, validation: { status: "Valid", needs_recalculation: false } } });
        },
    };
}

async function ready(env) {
    assert.equal(await env.coordinator.start(env.frm, "plan"), true);
    assert.equal(env.coordinator.snapshot(env.frm).phase, "editing");
    assert.equal(await env.preview.preview(env.frm, settings()), true);
    assert.equal(env.preview.snapshot(env.frm).previewId, "D");
}

async function run() {
    const success = environment();
    await ready(success);
    const generation = success.frm.__almdinaPlanPreviewSession.generation;
    const saving = success.coordinator.save(success.frm, "plan");
    assert.equal(success.coordinator.snapshot(success.frm).phase, "saving");
    for (const name of Object.keys(settings())) {
        assert.equal(success.host.fields.get(name).disabled, true, `${name} should be disabled`);
        assert.equal(success.host.fields.get(name).attr("aria-disabled"), "true");
    }
    assert.equal(success.host.recalculate.disabled, true);
    const draft = success.store.snapshot().draft;
    assert.equal(success.host.input("packing_mode", "auto"), false);
    assert.equal(success.host.input("trim_margin_mm", 12), false);
    // Even a programmatic input event cannot bypass the phase guard.
    success.host.input("packing_mode", "auto", true);
    success.host.input("trim_margin_mm", 12, true);
    assert.deepEqual(success.store.snapshot().draft, draft);
    assert.equal(success.preview.invalidate(success.frm), false);
    assert.equal(success.preview.snapshot(success.frm).status, "saving");
    assert.equal(success.preview.snapshot(success.frm).previewId, "D");
    assert.equal(success.frm.__almdinaPlanPreviewSession.generation, generation);
    success.commitFlight.resolve({ committed: true });
    assert.equal(await saving, true);
    assert.deepEqual(success.calls.filter(call => call[0] === "commit"), [["commit", "D"]]);
    assert.equal(success.coordinator.snapshot(success.frm).phase, "idle");

    const failure = environment();
    await ready(failure);
    const failedSave = failure.coordinator.save(failure.frm, "plan");
    assert.equal(failure.host.fields.get("kerf_mm").disabled, true);
    failure.commitFlight.reject(new Error("server rejected preview"));
    assert.equal(await failedSave, false);
    assert.equal(failure.coordinator.snapshot(failure.frm).phase, "editing");
    assert.equal(failure.host.fields.get("kerf_mm").disabled, false);
    assert.equal(failure.host.recalculate.disabled, false);
    assert.equal(failure.store.snapshot().editing, true);
    assert.equal(failure.preview.snapshot(failure.frm).status, "stale");
    assert.equal(failure.host.input("kerf_mm", 4), true);
    assert.equal(failure.store.snapshot().draft.kerf_mm, 4);

    const identity = environment();
    await ready(identity);
    const old = identity.frm.__almdinaPlanPreviewSession;
    const identitySave = identity.coordinator.save(identity.frm, "plan");
    identity.frm.doc.name = "DCO-2";
    identity.commitFlight.resolve({ committed: true });
    assert.equal(await identitySave, false);
    assert.equal(identity.frm.__almdinaPlanPreviewSession, old);
    assert.equal(old.status, "saving", "the old completion must not alter the new document state");
    assert.equal(identity.coordinator.snapshot(identity.frm).phase, "idle");

    // Preview remains editable until Save begins.
    const previewing = environment();
    await ready(previewing);
    previewing.setPreviewPending();
    const request = previewing.preview.preview(previewing.frm, settings());
    assert.equal(previewing.preview.snapshot(previewing.frm).status, "previewing");
    assert.equal(previewing.host.fields.get("trim_margin_mm").disabled, false);
    assert.equal(previewing.host.input("trim_margin_mm", 9), true);
    assert.equal(previewing.preview.snapshot(previewing.frm).status, "stale");
    previewing.finishPreview("obsolete", settings());
    assert.equal(await request, false);
}

run().then(() => console.log("plan preview Save phase lock tests passed"))
    .catch(error => { console.error(error); process.exitCode = 1; });
