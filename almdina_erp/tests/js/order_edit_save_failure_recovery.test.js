"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const frappeApp = path.resolve(root, "../../frappe");
const frappeFormPath = path.join(
    frappeApp,
    "frappe/public/js/frappe/form/form.js"
);
const coordinatorPath = path.join(
    root,
    "public/js/door_cutting_order/core/door_cutting_order_edit_session_coordinator.js"
);
const revisionPath = path.join(
    root,
    "public/js/door_cutting_order/core/door_cutting_order_revision_ux.js"
);
const pageEditPath = path.join(
    root,
    "public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js"
);
const saveIntentPath = path.join(
    root,
    "public/js/door_cutting_order/core/door_cutting_order_edit_save_intent_ux.js"
);

const frappeFormSource = fs.readFileSync(frappeFormPath, "utf8");
assert.match(frappeFormSource, /validate_and_save\(save_action, callback, btn, on_error, resolve, reject\)/);
assert.match(frappeFormSource, /if \(on_error\) \{\s*on_error\(\);\s*reject\(\);/s);
assert.match(
    fs.readFileSync(path.join(frappeApp, "frappe/__init__.py"), "utf8"),
    /__version__\s*=\s*"16\.33\.1"/
);

// Reproduce the Frappe v16.33.1 Form.save / validate_and_save contract that
// leaves the returned Promise pending when validation fails and on_error is
// omitted. The installed form.js catch swallows rejections, so awaiting the
// Promise alone is not proof of success.
function createFrappeSave(options = {}) {
    const state = {
        calls: 0,
        failures: 0,
        successes: 0,
        lastOnError: null,
        mode: options.mode || "reject-before-save",
        hangWithoutOnError: options.hangWithoutOnError !== false,
    };

    function save(save_action, callback, btn, on_error) {
        state.calls += 1;
        state.lastOnError = on_error;
        return new Promise((resolve, reject) => {
            const fail = () => {
                state.failures += 1;
                if (on_error) {
                    on_error();
                    reject(new Error("validation failed"));
                    return;
                }
                if (!state.hangWithoutOnError) {
                    reject(new Error("validation failed"));
                }
                // Match Frappe: without on_error the Promise stays pending.
            };

            const succeed = () => {
                state.successes += 1;
                if (typeof options.onSuccess === "function") options.onSuccess();
                if (typeof callback === "function") callback({});
                resolve();
            };

            Promise.resolve()
                .then(() => {
                    if (typeof options.beforeSave === "function") {
                        return options.beforeSave();
                    }
                    return undefined;
                })
                .then(() => {
                    if (state.mode === "reject-before-save") {
                        fail();
                        return;
                    }
                    if (state.mode === "server-error") {
                        const response = { exc: "Server Error" };
                        if (on_error) {
                            on_error();
                            reject(new Error("server error"));
                        }
                        if (typeof callback === "function") callback(response);
                        if (!on_error) resolve();
                        return;
                    }
                    if (state.mode === "network-error") {
                        fail();
                        return;
                    }
                    succeed();
                })
                .catch((error) => {
                    if (on_error) {
                        on_error();
                        reject(error);
                    }
                });
        }).then(() => {
            // Frappe always attaches a success-action then/catch that swallows.
        }).catch(() => {
            // Frappe v16.33.1 swallows the rejection here, so await frm.save()
            // fulfills even when validation failed — provided on_error rejected
            // the inner promise. Without on_error the inner promise never settles.
        });
    }

    return { save, state };
}

function createSandbox() {
    const formHandlers = {};
    const window = {
        requestAnimationFrame(fn) { return setTimeout(fn, 0); },
        setTimeout,
        clearTimeout,
        addEventListener() {},
        removeEventListener() {},
        cur_frm: null,
    };
    const document = {
        getElementById() { return null; },
        documentElement: { getAttribute() { return "rtl"; } },
        querySelector() { return null; },
        querySelectorAll() { return []; },
        createElement() {
            return {
                style: {},
                setAttribute() {},
                appendChild() {},
            };
        },
    };
    const frappe = {
        provide(name) {
            const parts = String(name).split(".");
            let current = sandbox;
            parts.forEach((part) => {
                if (!current[part]) current[part] = {};
                current = current[part];
            });
            return current;
        },
        ui: {
            form: {
                on(doctype, handlers) {
                    formHandlers[doctype] = Object.assign(
                        {},
                        formHandlers[doctype] || {},
                        handlers
                    );
                },
                close_grid_form() {},
            },
        },
        utils: {
            escape_html(value) { return String(value ?? ""); },
        },
        get_route() {
            const frm = window.cur_frm;
            if (!frm || !frm.doc || !frm.doc.name) return [];
            return ["Form", frm.doctype, frm.doc.name];
        },
        show_alert() {},
        msgprint() {},
        call() { return Promise.resolve({ message: {} }); },
        set_route() {},
        almdina: {},
        views: { formview: {} },
    };
    const jq = {
        closest() { return jq; },
        addClass() { return jq; },
        removeClass() { return jq; },
        find() { return jq; },
        html() { return jq; },
        append() { return jq; },
        prepend() { return jq; },
        remove() { return jq; },
        on() { return jq; },
        off() { return jq; },
        each() { return jq; },
        get() { return null; },
        length: 0,
    };
    const $ = () => jq;
    $.fn = {};

    const sandbox = {
        window,
        document,
        frappe,
        $,
        console,
        Object,
        String,
        Number,
        Boolean,
        Promise,
        Set,
        Map,
        WeakMap,
        Array,
        Error,
        setTimeout,
        clearTimeout,
        __: (message) => String(message),
        __formHandlers: formHandlers,
    };
    window.frappe = frappe;
    window.$ = $;
    window.console = console;
    window.AlmdinaPermissions = {
        version() { return 1; },
        canDocument() { return true; },
        can() { return true; },
    };
    window.AlmdinaLocale = {
        translate(message) { return String(message); },
        direction() { return "rtl"; },
    };
    window.AlmdinaUi = {
        button({ label, className = "", disabled = false, attrs = {} }) {
            const title = attrs.title ? ` title="${attrs.title}"` : "";
            return `<button type="button" class="${className}"${disabled ? " disabled" : ""}${title}>${label}</button>`;
        },
    };
    window.AlmdinaDocumentContext = {
        capture(frm) {
            return Object.freeze({
                identity: `${frm.doctype}::${frm.doc.name}`,
                generation: Number(frm._almdinaDocumentContextGeneration || 0),
            });
        },
        isCurrent(frm, token) {
            return Boolean(
                window.cur_frm === frm
                && token
                && token.identity === `${frm.doctype}::${frm.doc.name}`
                && Number(token.generation) === Number(frm._almdinaDocumentContextGeneration || 0)
            );
        },
        scheduleFrame(_frm, _key, callback) {
            callback();
        },
    };
    return sandbox;
}

function load(sandbox, relativePath) {
    const filename = path.join(root, relativePath);
    vm.runInNewContext(
        fs.readFileSync(filename, "utf8"),
        sandbox,
        { filename }
    );
}

function buttonNode(className, disabled) {
    return {
        disabled: Boolean(disabled),
        className,
        closest(selector) {
            return String(selector).includes(className) ? this : null;
        },
        setAttribute() {},
        removeAttribute() {},
    };
}

function makeForm(sandbox, name, pieces) {
    const toolbarHost = {
        children: [],
        querySelector(selector) {
            if (selector.includes("dco-tab-edit-save")) {
                return this._save || null;
            }
            if (selector.includes("dco-tab-edit-cancel")) {
                return this._cancel || null;
            }
            if (selector.includes("dco-tab-edit-start")) {
                return this._startRendered ? this._start : null;
            }
            if (selector.includes("__state")) {
                return this._state || null;
            }
            return null;
        },
        querySelectorAll() { return []; },
        getAttribute(name) { return this.attrs[name]; },
        setAttribute(name, value) { this.attrs[name] = String(value); },
        attrs: {},
        innerHTML: "",
        _listeners: {},
        addEventListener(type, handler) {
            if (!this._listeners[type]) this._listeners[type] = [];
            this._listeners[type].push(handler);
        },
        contains(node) {
            return node === this || node === this._save || node === this._cancel || node === this._start;
        },
    };
    const pageRoot = {
        nodeType: 1,
        classList: { add() {}, remove() {} },
        querySelector(selector) {
            if (String(selector).includes("dco-tab-edit-toolbar")) return toolbarHost;
            if (String(selector).includes("dco-tab-edit-toolbar-slot")) return null;
            if (String(selector).includes("data-fieldname")) return null;
            return null;
        },
        querySelectorAll() { return []; },
        prepend() {},
    };
    toolbarHost.isConnected = true;
    const frm = {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name,
            docstatus: 0,
            status: "Draft",
            revision_state: "Current",
            pieces: pieces.slice(),
            board_length_cm: 280,
            board_width_cm: 210,
        },
        _almdinaDocumentContextGeneration: 0,
        dirtyFlag: true,
        is_new() { return false; },
        is_dirty() { return Boolean(this.dirtyFlag); },
        dirty() { this.dirtyFlag = true; },
        has_perm() { return true; },
        trigger() {},
        reload_doc() {
            this.dirtyFlag = false;
            return Promise.resolve();
        },
        wrapper: pageRoot,
        page: {
            wrapper: pageRoot,
            clear_primary_action() {},
            set_primary_action() {},
        },
        fields_dict: {},
        toolbar: { current_status: null, set_primary_action() {} },
        disable_save() {},
        enable_save() {},
        toggle_enable() {},
        set_intro() {},
        remove_custom_button() {},
        add_custom_button() {},
        get_active_tab() {
            return { df: { fieldname: "order_tab" } };
        },
        script_manager: { trigger() { return Promise.resolve(); } },
    };
    toolbarHost._dcoTabEditForm = frm;
    toolbarHost.setAttribute("data-almdina-tab-edit-kind", "order");
    toolbarHost.setAttribute("data-editing", "1");
    toolbarHost.setAttribute("data-almdina-action-mode", "save");
    toolbarHost._save = buttonNode("dco-tab-edit-save", false);
    toolbarHost._cancel = buttonNode("dco-tab-edit-cancel", false);
    toolbarHost._state = { textContent: "" };
    Object.defineProperty(toolbarHost, "innerHTML", {
        get() { return this._html || ""; },
        set(value) {
            this._html = String(value);
            const saveMatch = this._html.match(/<button[^>]*class="[^"]*dco-tab-edit-save[^"]*"[^>]*>/);
            const cancelMatch = this._html.match(/<button[^>]*class="[^"]*dco-tab-edit-cancel[^"]*"[^>]*>/);
            this._save = buttonNode(
                "dco-tab-edit-save",
                Boolean(saveMatch && /\sdisabled(?:\s|>)/.test(saveMatch[0]))
            );
            this._cancel = buttonNode(
                "dco-tab-edit-cancel",
                Boolean(cancelMatch && /\sdisabled(?:\s|>)/.test(cancelMatch[0]))
            );
            const startMatch = this._html.match(/<button[^>]*class="[^"]*dco-tab-edit-start[^"]*"[^>]*>/);
            this._startRendered = Boolean(startMatch);
            this._start = buttonNode(
                "dco-tab-edit-start",
                Boolean(startMatch && /\sdisabled(?:\s|>)/.test(startMatch[0]))
            );
        },
    });
    frm._toolbarHost = toolbarHost;
    sandbox.window.cur_frm = frm;
    return frm;
}

function piece(overrides) {
    return Object.assign({
        name: "piece-1",
        width_cm: 40,
        length_cm: 80,
        qty: 1,
        piece_type: "Regular",
    }, overrides);
}

function settle(ms = 20) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function run() {
    const revisionSource = fs.readFileSync(revisionPath, "utf8");
    assert.match(revisionSource, /function saveDocument\(frm, saveAction\)/);
    assert.match(revisionSource, /on_error/);
    assert.match(revisionSource, /await saveDocument\(frm\)/);
    assert.doesNotMatch(
        revisionSource.split("async function persistOrderEditCheckpoint", 2)[1]
            .split("function confirmEditSession", 2)[0],
        /await frm\.save\(\);/
    );

    // Baseline: bare frm.save() hangs forever when Frappe rejects before_save
    // without on_error. This proves the regression shape.
    {
        const hanging = createFrappeSave({ mode: "reject-before-save", hangWithoutOnError: true });
        let settled = false;
        hanging.save("Save").then(() => { settled = "resolved"; }, () => { settled = "rejected"; });
        await settle(40);
        assert.equal(settled, false, "Frappe save without on_error must stay pending on validation failure");
        assert.equal(hanging.state.failures, 1);
    }

    const sandbox = createSandbox();
    load(sandbox, "public/js/door_cutting_order/core/door_cutting_order_edit_session_coordinator.js");
    load(sandbox, "public/js/door_cutting_order/core/door_cutting_order_revision_ux.js");
    load(sandbox, "public/js/door_cutting_order/core/door_cutting_order_edit_save_intent_ux.js");
    load(sandbox, "public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js");

    const coordinator = sandbox.window.AlmdinaDcoEditSessionCoordinator;
    const pageEdit = sandbox.window.AlmdinaPageEditActionUX;
    const revision = sandbox.window.AlmdinaOrderRevisionUX;
    assert.ok(coordinator && pageEdit && revision);

    async function startOrderEdit(frm) {
        const started = await coordinator.start(frm, "order");
        assert.equal(started, true);
        assert.equal(coordinator.snapshot(frm).phase, "editing");
        pageEdit.sync(frm);
    }

    function clickToolbar(frm, which) {
        const host = frm._toolbarHost;
        const button = which === "cancel" ? host._cancel : host._save;
        const handlers = (host._listeners && host._listeners.click) || [];
        assert.ok(handlers.length > 0, "toolbar click handler is bound");
        handlers.forEach((handler) => handler({
            target: button,
            preventDefault() {},
        }));
    }

    async function rejectedSave(frm) {
        assert.equal(frm._toolbarHost._save.disabled, false);
        clickToolbar(frm, "save");
        assert.equal(frm.__almdinaPageEditActionBusy, true);
        assert.equal(frm._toolbarHost._save.disabled, true);
        assert.equal(frm._toolbarHost._cancel.disabled, true);
        await settle(40);
        assert.equal(frm.__almdinaPageEditActionBusy, false);
        assert.equal(coordinator.snapshot(frm).phase, "editing");
        assert.equal(frm._toolbarHost.getAttribute("data-almdina-action-mode"), "save");
        assert.equal(frm._toolbarHost._save.disabled, false);
        assert.equal(frm._toolbarHost._cancel.disabled, false);
    }

    // 1. Zero width rejects save, restores editing, clears busy, keeps rows.
    {
        const frm = makeForm(sandbox, "DCO-SAVE-1", [
            piece({ name: "old-1", width_cm: 40, length_cm: 80 }),
            piece({ name: "new-1", width_cm: 0, length_cm: 120 }),
        ]);
        const saveApi = createFrappeSave({
            mode: "reject-before-save",
            hangWithoutOnError: true,
            beforeSave() { throw new Error("Invalid dimension"); },
            onSuccess() { frm.dirtyFlag = false; },
        });
        frm.save = saveApi.save;

        await startOrderEdit(frm);
        assert.equal(frm.doc.pieces.length, 2);
        assert.equal(frm.__almdina_edit_session, true);

        await rejectedSave(frm);
        assert.ok(saveApi.state.lastOnError, "rejected save must pass on_error so Frappe settles the promise");
        assert.equal(coordinator.snapshot(frm).activeKind, "order");
        assert.equal(frm.__almdina_lock_after_save, false);
        assert.equal(frm.__almdina_edit_session, true);
        assert.equal(frm.dirtyFlag, true);
        assert.equal(frm.doc.pieces.length, 2);
        assert.equal(frm.doc.pieces[1].width_cm, 0);
        assert.equal(frm.doc.pieces[1].length_cm, 120);
    }

    async function withInvalidPiece(invalidPiece, correctPiece) {
        const frm = makeForm(sandbox, `DCO-${invalidPiece.name}`, [
            piece({ name: "kept", width_cm: 50, length_cm: 90 }),
            piece(invalidPiece),
        ]);
        const saveApi = createFrappeSave({
            mode: "reject-before-save",
            hangWithoutOnError: true,
            beforeSave() {
                const bad = frm.doc.pieces.some(row => (
                    !(Number(row.width_cm) > 0)
                    || !(Number(row.length_cm) > 0)
                    || Number(row.width_cm) > Number(frm.doc.board_width_cm)
                    || Number(row.length_cm) > Number(frm.doc.board_length_cm)
                ));
                if (bad) throw new Error("Invalid dimension");
            },
            onSuccess() { frm.dirtyFlag = false; },
        });
        frm.save = saveApi.save;
        await startOrderEdit(frm);
        await rejectedSave(frm);
        assert.ok(saveApi.state.lastOnError, "saveDocument must pass on_error into frm.save");
        assert.equal(frm.__almdina_lock_after_save, false);
        assert.equal(frm.doc.pieces.length, 2);
        assert.equal(frm.dirtyFlag, true);

        Object.assign(frm.doc.pieces[1], correctPiece);
        saveApi.state.mode = "success";
        frm.dirtyFlag = true;
        clickToolbar(frm, "save");
        assert.equal(frm.__almdinaPageEditActionBusy, true);
        await settle(40);
        assert.equal(frm.__almdinaPageEditActionBusy, false);
        assert.equal(coordinator.snapshot(frm).phase, "idle");
        assert.equal(frm.dirtyFlag, false);
        assert.equal(frm.doc.pieces.length, 2);
        assert.equal(frm.doc.pieces[1].width_cm, correctPiece.width_cm);
        assert.equal(frm.doc.pieces[1].length_cm, correctPiece.length_cm);
        assert.equal(saveApi.state.successes, 1);
        return { frm, saveApi };
    }

    // 3. Zero length, empty measure, exceeds width, exceeds length.
    await withInvalidPiece(
        { name: "bad-length", width_cm: 40, length_cm: 0 },
        { width_cm: 40, length_cm: 100 }
    );
    await withInvalidPiece(
        { name: "bad-empty", width_cm: "", length_cm: 90 },
        { width_cm: 55, length_cm: 90 }
    );
    await withInvalidPiece(
        { name: "bad-wide", width_cm: 250, length_cm: 90 },
        { width_cm: 100, length_cm: 90 }
    );
    await withInvalidPiece(
        { name: "bad-long", width_cm: 40, length_cm: 300 },
        { width_cm: 40, length_cm: 200 }
    );

    // 1 again with zero width + successful retry.
    await withInvalidPiece(
        { name: "bad-width", width_cm: 0, length_cm: 120 },
        { width_cm: 60, length_cm: 120 }
    );

    // 4. Failed save then cancel.
    {
        const frm = makeForm(sandbox, "DCO-CANCEL", [
            piece({ name: "row", width_cm: 0, length_cm: 80 }),
        ]);
        const saveApi = createFrappeSave({
            mode: "reject-before-save",
            hangWithoutOnError: true,
            beforeSave() { throw new Error("Invalid dimension"); },
        });
        frm.save = saveApi.save;
        await startOrderEdit(frm);
        await rejectedSave(frm);
        assert.equal(frm.__almdina_edit_session, true);
        assert.equal(frm.doc.pieces[0].width_cm, 0);

        clickToolbar(frm, "cancel");
        assert.equal(frm.__almdinaPageEditActionBusy, true);
        await settle(40);
        assert.equal(frm.__almdinaPageEditActionBusy, false);
        assert.equal(coordinator.snapshot(frm).phase, "idle");
        assert.equal(frm.__almdina_edit_session, false);
    }

    // 5. Several failed saves, then one success.
    {
        const frm = makeForm(sandbox, "DCO-RETRY", [
            piece({ name: "new-a", width_cm: 0, length_cm: 80 }),
            piece({ name: "new-b", width_cm: 30, length_cm: "" }),
        ]);
        const saveApi = createFrappeSave({
            mode: "reject-before-save",
            hangWithoutOnError: true,
            beforeSave() {
                const bad = frm.doc.pieces.some(row => !(Number(row.width_cm) > 0) || !(Number(row.length_cm) > 0));
                if (bad) throw new Error("Invalid dimension");
            },
            onSuccess() { frm.dirtyFlag = false; },
        });
        frm.save = saveApi.save;
        await startOrderEdit(frm);
        for (let attempt = 0; attempt < 3; attempt += 1) {
            frm.dirtyFlag = true;
            await rejectedSave(frm);
            assert.equal(frm.doc.pieces.length, 2);
            assert.equal(frm.doc.pieces[0].width_cm, 0);
            assert.equal(frm.doc.pieces[1].length_cm, "");
        }
        frm.doc.pieces[0].width_cm = 45;
        frm.doc.pieces[1].length_cm = 88;
        saveApi.state.mode = "success";
        frm.dirtyFlag = true;
        clickToolbar(frm, "save");
        await settle(40);
        assert.equal(frm.__almdinaPageEditActionBusy, false);
        assert.equal(saveApi.state.successes, 1);
        assert.equal(frm.doc.pieces[0].width_cm, 45);
        assert.equal(frm.doc.pieces[1].length_cm, 88);
        assert.equal(coordinator.snapshot(frm).phase, "idle");
    }

    // 6. Server / network failure still returns to editing.
    for (const mode of ["server-error", "network-error"]) {
        const frm = makeForm(sandbox, `DCO-${mode}`, [
            piece({ name: "ok", width_cm: 40, length_cm: 80 }),
        ]);
        const saveApi = createFrappeSave({
            mode,
            hangWithoutOnError: true,
            onSuccess() { frm.dirtyFlag = false; },
        });
        frm.save = saveApi.save;
        await startOrderEdit(frm);
        frm.dirtyFlag = true;
        await rejectedSave(frm);
        assert.equal(frm.dirtyFlag, true, mode);
        assert.equal(frm.doc.pieces.length, 1, mode);
        saveApi.state.mode = "success";
        frm.dirtyFlag = true;
        clickToolbar(frm, "save");
        await settle(40);
        assert.equal(frm.__almdinaPageEditActionBusy, false, mode);
        assert.equal(saveApi.state.successes, 1, mode);
        assert.equal(frm.dirtyFlag, false, mode);
        assert.equal(coordinator.snapshot(frm).phase, "idle", mode);
    }

    // 7. Duplicate saves while busy are blocked by page-edit busy flag.
    {
        const frm = makeForm(sandbox, "DCO-BUSY", [
            piece({ name: "ok", width_cm: 40, length_cm: 80 }),
        ]);
        let release;
        const gate = new Promise(resolve => { release = resolve; });
        const saveApi = createFrappeSave({
            mode: "success",
            hangWithoutOnError: true,
            beforeSave() { return gate; },
            onSuccess() { frm.dirtyFlag = false; },
        });
        frm.save = saveApi.save;
        await startOrderEdit(frm);
        frm.dirtyFlag = true;
        clickToolbar(frm, "save");
        assert.equal(frm.__almdinaPageEditActionBusy, true);
        assert.equal(frm._toolbarHost._save.disabled, true);
        assert.equal(frm._toolbarHost._cancel.disabled, true);
        await settle(10);
        assert.equal(coordinator.snapshot(frm).phase, "saving");
        assert.equal(saveApi.state.calls, 1);
        frm._toolbarHost._save.disabled = false;
        clickToolbar(frm, "save");
        await settle(10);
        assert.equal(saveApi.state.calls, 1, "a second click while busy must not start another save");
        release();
        await settle(40);
        assert.equal(frm.__almdinaPageEditActionBusy, false);
        assert.equal(coordinator.snapshot(frm).phase, "idle");
        assert.equal(saveApi.state.successes, 1);
    }

    // 8. Stale failure after document switch must not alter the new document.
    {
        const first = makeForm(sandbox, "DCO-OLD", [
            piece({ name: "bad", width_cm: 0, length_cm: 80 }),
        ]);
        let releaseFail;
        const failGate = new Promise(resolve => { releaseFail = resolve; });
        const firstSave = createFrappeSave({
            mode: "reject-before-save",
            hangWithoutOnError: true,
            beforeSave() {
                return failGate.then(() => {
                    throw new Error("Invalid dimension");
                });
            },
        });
        first.save = firstSave.save;
        await startOrderEdit(first);
        first.dirtyFlag = true;
        clickToolbar(first, "save");
        await settle(10);
        assert.equal(coordinator.snapshot(first).phase, "saving");
        assert.equal(first.__almdinaPageEditActionBusy, true);

        const second = makeForm(sandbox, "DCO-NEW", [
            piece({ name: "ok", width_cm: 40, length_cm: 80 }),
        ]);
        second._almdinaDocumentContextGeneration = 1;
        const secondSave = createFrappeSave({
            mode: "success",
            onSuccess() { second.dirtyFlag = false; },
        });
        second.save = secondSave.save;
        await startOrderEdit(second);
        assert.equal(coordinator.snapshot(second).phase, "editing");
        assert.equal(second.__almdinaPageEditActionBusy, undefined);
        assert.equal(second._toolbarHost._save.disabled, false);

        releaseFail();
        await settle(40);
        assert.equal(coordinator.snapshot(second).phase, "editing");
        assert.equal(second.__almdina_edit_session, true);
        assert.equal(second.__almdinaPageEditActionBusy, undefined);
        assert.equal(second._toolbarHost._save.disabled, false);
        assert.equal(second.doc.pieces[0].width_cm, 40);
        assert.equal(first.__almdinaPageEditActionBusy, false);
    }

    // 8b. Same form object, newer document identity: stale failure must not
    // leave the new identity in saving or clear a busy mark it does not own.
    {
        const frm = makeForm(sandbox, "DCO-SAME", [
            piece({ name: "kept", width_cm: 0, length_cm: 70 }),
        ]);
        let releaseFail;
        const failGate = new Promise(resolve => { releaseFail = resolve; });
        const saveApi = createFrappeSave({
            mode: "reject-before-save",
            hangWithoutOnError: true,
            beforeSave() {
                return failGate.then(() => {
                    throw new Error("Invalid dimension");
                });
            },
        });
        frm.save = saveApi.save;
        await startOrderEdit(frm);
        clickToolbar(frm, "save");
        await settle(10);
        assert.equal(coordinator.snapshot(frm).phase, "saving");
        frm.doc.name = "DCO-SAME-NEXT";
        frm._almdinaDocumentContextGeneration = 4;
        frm.doc.pieces[0].width_cm = 33;
        assert.equal(coordinator.snapshot(frm).phase, "idle");
        releaseFail();
        await settle(40);
        assert.equal(coordinator.snapshot(frm).phase, "idle");
        assert.equal(coordinator.snapshot(frm).documentIdentity, "Door Cutting Order::DCO-SAME-NEXT");
        assert.equal(frm.__almdinaPageEditActionBusy, false);
        assert.equal(frm.doc.pieces[0].width_cm, 33);
    }

    // 9. Checkpoint failure clears preserve marker and stays distinct from explicit save.
    {
        const frm = makeForm(sandbox, "DCO-CHECK", [
            piece({ name: "ok", width_cm: 40, length_cm: 80 }),
        ]);
        const saveApi = createFrappeSave({
            mode: "reject-before-save",
            hangWithoutOnError: true,
            beforeSave() { throw new Error("network"); },
        });
        frm.save = saveApi.save;
        await startOrderEdit(frm);
        frm.dirtyFlag = true;
        const ok = await Promise.race([
            sandbox.frappe.almdina.persistOrderEditCheckpoint(frm),
            settle(100).then(() => "timeout"),
        ]);
        assert.equal(ok, false);
        assert.ok(saveApi.state.lastOnError);
        assert.equal(frm.__almdina_preserve_edit_session_after_save, false);
        assert.equal(frm.__almdina_lock_after_save, undefined);
        assert.equal(coordinator.snapshot(frm).phase, "editing");
        assert.equal(frm.__almdina_edit_session, true);
        assert.equal(frm.__almdinaPageEditActionBusy, undefined);
        assert.equal(frm._toolbarHost._save.disabled, false);
        assert.equal(frm.dirtyFlag, true);
    }

    // New-document save inside an open session also settles and restores buttons.
    {
        const frm = makeForm(sandbox, "DCO-NEWDOC", [
            piece({ name: "bad", width_cm: 0, length_cm: 80 }),
        ]);
        const saveApi = createFrappeSave({
            mode: "reject-before-save",
            hangWithoutOnError: true,
            beforeSave() { throw new Error("Invalid dimension"); },
        });
        frm.save = saveApi.save;
        await startOrderEdit(frm);
        frm.is_new = () => true;
        frm.dirtyFlag = true;
        clickToolbar(frm, "save");
        await settle(40);
        assert.equal(saveApi.state.calls, 1);
        assert.ok(saveApi.state.lastOnError);
        assert.equal(frm.__almdinaPageEditActionBusy, false);
        assert.equal(coordinator.snapshot(frm).phase, "editing");
        assert.equal(frm.doc.pieces[0].width_cm, 0);
        assert.equal(frm.dirtyFlag, true);
    }

    console.log("order edit save failure recovery tests passed");
}

run().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
