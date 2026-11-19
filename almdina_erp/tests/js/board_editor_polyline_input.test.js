"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const VOID = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"]);

function parseAttrs(raw) {
    const attrs = {};
    const re = /([^\s=\/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"']+)))?/g;
    let match;
    while ((match = re.exec(raw))) {
        attrs[match[1]] = match[2] != null ? match[2] : (match[3] != null ? match[3] : (match[4] != null ? match[4] : ""));
    }
    return attrs;
}

class MiniElement {
    constructor(tag, attrs, owner) {
        this.tagName = String(tag || "div").toUpperCase();
        this.attrs = attrs || {};
        this.owner = owner;
        this.children = [];
        this.parentElement = null;
        this.style = {};
        this.listeners = {};
        this.value = this.attrs.value || "";
        this.disabled = Object.prototype.hasOwnProperty.call(this.attrs, "disabled");
        this.dataset = {};
        Object.keys(this.attrs).forEach((key) => {
            if (key.indexOf("data-") !== 0) return;
            const name = key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
            this.dataset[name] = this.attrs[key];
        });
        this.clientWidth = 900;
        this.clientHeight = 640;
        this.scrollLeft = 0;
        this.scrollTop = 0;
        this.offsetWidth = 180;
        this.offsetHeight = 28;
        const classes = this;
        this.classList = {
            contains(name) { return classes.classNames().includes(name); },
            add(name) {
                if (!classes.classList.contains(name)) {
                    classes.attrs.class = `${classes.attrs.class || ""} ${name}`.trim();
                }
            },
            remove(name) {
                classes.attrs.class = classes.classNames().filter((item) => item !== name).join(" ");
            },
            toggle(name) {
                if (classes.classList.contains(name)) classes.classList.remove(name);
                else classes.classList.add(name);
            },
        };
    }

    classNames() {
        return String(this.attrs.class || "").split(/\s+/).filter(Boolean);
    }

    getAttribute(name) {
        return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
    }

    setAttribute(name, value) {
        this.attrs[name] = String(value);
        if (name === "value") this.value = String(value);
        if (name === "disabled") this.disabled = true;
    }

    addEventListener(type, fn) {
        this.listeners[type] = this.listeners[type] || [];
        this.listeners[type].push(fn);
    }

    remove() {
        if (!this.parentElement) return;
        this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
        this.parentElement = null;
    }

    appendChild(child) {
        child.parentElement = this;
        this.children.push(child);
        return child;
    }

    focus() {
        if (this.disabled) return;
        if (this.owner) this.owner.activeElement = this;
    }

    set innerHTML(value) {
        this._html = String(value == null ? "" : value);
        this.children = [];
        parseHtml(this._html, this);
    }

    get innerHTML() {
        return this._html || "";
    }

    getBoundingClientRect() {
        return this.rect || { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight, right: this.clientWidth, bottom: this.clientHeight };
    }

    setPointerCapture() {}

    releasePointerCapture() {}

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] || null;
    }

    querySelectorAll(selector) {
        const found = [];
        const visit = (node) => {
            node.children.forEach((child) => {
                if (matches(child, selector)) found.push(child);
                visit(child);
            });
        };
        visit(this);
        return found;
    }
}

function matchSimple(element, selector) {
    let rest = selector.trim();
    if (!rest) return false;
    if (/^[a-zA-Z]/.test(rest)) {
        const tag = rest.match(/^[a-zA-Z0-9:-]+/)[0];
        if (element.tagName !== tag.toUpperCase()) return false;
        rest = rest.slice(tag.length);
    }
    while (rest) {
        if (rest[0] === ".") {
            const name = rest.match(/^\.([A-Za-z0-9_-]+)/);
            if (!name || !element.classList.contains(name[1])) return false;
            rest = rest.slice(name[0].length);
        } else if (rest[0] === "[") {
            const body = rest.match(/^\[([^\]]+)\]/);
            if (!body) return false;
            const equals = body[1].match(/^([^=]+)="([^"]*)"$/);
            if (equals) {
                if (element.getAttribute(equals[1]) !== equals[2]) return false;
            } else if (element.getAttribute(body[1]) == null) return false;
            rest = rest.slice(body[0].length);
        } else {
            return false;
        }
    }
    return true;
}

function matches(element, selector) {
    return selector.split(",").some((part) => {
        const bits = part.trim().split(/\s+/).filter(Boolean);
        if (!bits.length || !matchSimple(element, bits[bits.length - 1])) return false;
        let cursor = element.parentElement;
        for (let index = bits.length - 2; index >= 0; index -= 1) {
            while (cursor && !matchSimple(cursor, bits[index])) cursor = cursor.parentElement;
            if (!cursor) return false;
            cursor = cursor.parentElement;
        }
        return true;
    });
}

function parseHtml(html, parent) {
    const re = /<!--[\s\S]*?-->|<(\/?)([A-Za-z][\w:-]*)([^>]*?)(\/?)>/g;
    const stack = [parent];
    let match;
    while ((match = re.exec(html))) {
        if (match[0].startsWith("<!--")) continue;
        const closing = match[1] === "/";
        const tag = match[2];
        const self = match[4] === "/" || VOID.has(tag.toLowerCase());
        if (closing) {
            for (let index = stack.length - 1; index > 0; index -= 1) {
                const found = stack[index].tagName.toLowerCase() === tag.toLowerCase();
                stack.pop();
                if (found) break;
            }
            continue;
        }
        const element = new MiniElement(tag, parseAttrs(match[3] || ""), parent.owner);
        stack[stack.length - 1].appendChild(element);
        if (!self) stack.push(element);
    }
}

function emit(element, type, extras) {
    const event = Object.assign({
        type,
        key: "",
        target: element,
        currentTarget: element,
        bubbles: true,
        defaultPrevented: false,
        cancelBubble: false,
        preventDefault() { this.defaultPrevented = true; },
        stopPropagation() { this.cancelBubble = true; },
    }, extras || {});
    const chain = [];
    let node = element;
    while (node) {
        chain.push(node);
        node = node.parentElement;
    }
    chain.forEach((current) => {
        if (event.cancelBubble) return;
        event.currentTarget = current;
        (current.listeners[type] || []).slice().forEach((fn) => fn(event));
    });
    return event;
}

function loadEditor() {
    const document = {
        activeElement: null,
        createElementNS(_ns, tag) {
            return new MiniElement(tag, {}, document);
        },
    };
    const context = {
        frappe: { utils: { escape_html: (value) => String(value == null ? "" : value) } },
        __: (message) => message,
        console,
        document,
        setTimeout(fn) { return 1; },
        clearTimeout() {},
        addEventListener() {},
        removeEventListener() {},
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    [
        "public/js/board_editor/editor_mode.js",
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/rotation_geometry.js",
        "public/js/board_editor/measure_geometry.js",
        "public/js/board_editor/drawing_space.js",
        "public/js/board_editor/drawing_model.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
        "public/js/board_editor/drawing_properties_panel.js",
    ].forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    context.__miniOwner = document;
    return context;
}

function piece(type) {
    return {
        piece_key: type === "Special" ? "special" : "regular",
        piece_id: type === "Special" ? 1 : 2,
        piece_instance_id: type === "Special" ? "piece:special" : "piece:regular",
        piece_type: type,
        label: type === "Special" ? "Special door" : "Regular door",
        sheet_no: 1,
        local_x_mm: 100,
        local_y_mm: 200,
        rotation_deg: 0,
        editable: true,
        distribution: "active",
        placement_cm: { x: 10, y: 20, w: 60, h: 210 },
        entry_pivot_mm: { x: 400, y: 1250 },
        pivot_mm: { x: 400, y: 1250 },
    };
}

function session() {
    return {
        pieces: { special: piece("Special"), regular: piece("Regular") },
        boards: { 1: { sheet_no: 1, origin_x_mm: 500, origin_y_mm: 40, trim_x_mm: 0, trim_y_mm: 0 } },
    };
}

function payload() {
    return {
        projection: {
            sheets: [],
            pieces: [
                { piece_id: 1, piece_instance_id: "piece:special", piece_type: "Special", original_w: 60, original_h: 210, label: "Special door" },
                { piece_id: 2, piece_instance_id: "piece:regular", piece_type: "Regular", original_w: 40, original_h: 80, label: "Regular door" },
            ],
        },
    };
}

function hostFor(context) {
    const host = new MiniElement("section", { class: "abe-canvas-host" }, context.document);
    host.clientWidth = 900;
    host.clientHeight = 640;
    host.getBoundingClientRect = () => ({ left: 0, top: 0, width: 900, height: 640, right: 900, bottom: 640 });
    return host;
}

function renderDrawing(context, drawingView, scale, extraHandlers) {
    const { createStore, History } = context.AlmdinaBoardEditor;
    const store = createStore(payload());
    store.attachSession(session(), History.create(session()));
    store.noteDraftBaseline({ canSaveLayout: true, draftVersion: 2, savedFingerprint: "fp-layout" });
    store.setEditorMode("drawing");
    store.selectPiece(1, { pieceKey: "special", mode: "replace" });
    store.setViewport({
        scale: scale || 1,
        scrollX: 10,
        scrollY: 12,
        padX: 8,
        padY: 8,
        opened: true,
        userAdjusted: true,
        cameraToken: 3,
    });
    if (drawingView) store.setDrawingView(drawingView);
    const host = hostFor(context);
    const commits = [];
    const bubbles = [];
    host.addEventListener("keydown", () => bubbles.push("host"));
    const handlers = Object.assign({
        commitDrawingHud(length, angle) { commits.push([length, angle]); },
        onDrawingMeasureInput() {},
    }, extraHandlers || {});
    context.AlmdinaBoardEditor.CanvasRenderer.render(host, store.snapshot(), handlers);
    const properties = new MiniElement("aside", { class: "abe-draw-props" }, context.document);
    context.AlmdinaBoardEditor.DrawingProperties.render(properties, store.snapshot(), handlers);
    host.__drawProps = properties;
    const dock = host.querySelector(".abe-float-dock");
    if (dock) dock.getBoundingClientRect = () => ({ left: 8, top: 560, width: 880, height: 72, right: 888, bottom: 632 });
    return { host, store, commits, bubbles };
}

function field(host, kind) {
    const bar = host.querySelector("[data-abe-drawing-measure]")
        || (host.__drawProps && host.__drawProps.querySelector("[data-abe-drawing-measure]"));
    assert.ok(bar, "measure bar");
    return bar.querySelector(kind === "angle" ? "[data-abe-drawing-angle]" : "[data-abe-drawing-length]");
}

function readyDrawing(tool, measure, paths) {
    return {
        tool,
        ready: true,
        dirty: false,
        messageKey: "This special piece is selected for drawing.",
        canFinish: true,
        canClose: true,
        canCancel: true,
        paths: paths || [],
        measure,
    };
}

const context = loadEditor();
const css = fs.readFileSync(path.join(root, "public/css/board_editor.css"), "utf8");
const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
assert.match(catalog, /Length \(mm\),الطول \(مم\)/);
assert.match(catalog, /Angle \(°\),الزاوية \(°\)/);
assert.match(css, /\.abe-drawing-measure\s*\{[^}]*display:\s*flex/);
assert.match(css, /\.abe-drawing-cursor\.is-visible\s*\{[^}]*display:\s*flex/);
assert.match(css, /\.abe-drawing-measure input[^}]*direction:\s*ltr/);
assert.doesNotMatch(css, /\.abe-drawing-measure\s*\{[^}]*display:\s*none/);

const hiddenBeforeStart = renderDrawing(context, readyDrawing("polyline", {
    mode: "draw",
    enabled: false,
}));
const disabledLength = field(hiddenBeforeStart.host, "length");
const disabledAngle = field(hiddenBeforeStart.host, "angle");
assert.equal(disabledLength.disabled, true);
assert.equal(disabledAngle.disabled, true);
assert.equal(disabledLength.getAttribute("dir"), "ltr");
assert.equal(disabledAngle.getAttribute("dir"), "ltr");
assert.equal(hiddenBeforeStart.host.querySelector("[data-abe-drawing-measure]").getAttribute("style"), null);
assert.equal(hiddenBeforeStart.host.querySelector("[data-abe-drawing-cursor]").classList.contains("is-visible"), false);
assert.doesNotMatch(hiddenBeforeStart.host.innerHTML, /data-abe-drawing-hud/);

context.AlmdinaLocale = { direction: () => "rtl" };
const rtl = renderDrawing(context, readyDrawing("polyline", { mode: "draw", enabled: true, lengthMm: 350, angleDeg: 90 }));
assert.equal(rtl.host.querySelector("[data-abe-drawing-measure]").getAttribute("dir"), "rtl");
assert.equal(field(rtl.host, "length").getAttribute("dir"), "ltr");
assert.equal(field(rtl.host, "length").value, "350");
assert.equal(field(rtl.host, "angle").value, "90");
assert.equal(rtl.host.querySelectorAll("[data-abe-drawing-length]").length, 1);
assert.equal(field(rtl.host, "length").getAttribute("tabindex"), null);
assert.equal(rtl.host.querySelector("[data-abe-drawing-cursor] [data-abe-drawing-length]").getAttribute("tabindex"), null);
context.AlmdinaLocale = { direction: () => "ltr" };
const ltr = renderDrawing(context, readyDrawing("polyline", { mode: "draw", enabled: true, lengthMm: 350, angleDeg: 90 }));
assert.equal(ltr.host.querySelector("[data-abe-drawing-measure]").getAttribute("dir"), "ltr");

const active = renderDrawing(context, readyDrawing("polyline", {
    mode: "draw",
    enabled: true,
    lengthMm: 12,
    angleDeg: 10,
}, [{
    id: "path-1",
    closed: false,
    selected: true,
    active: true,
    points: [{ id: "n1", x: 600, y: 240 }, { id: "n2", x: 950, y: 240 }],
}]));
const lengthInput = field(active.host, "length");
const angleInput = field(active.host, "angle");
assert.equal(lengthInput.disabled, false);
assert.equal(angleInput.disabled, false);
const sameLength = lengthInput;
const sameAngle = angleInput;
lengthInput.focus();
assert.equal(context.document.activeElement, lengthInput);
active.host.querySelector(".abe-world") || assert.fail("world");
context.AlmdinaBoardEditor.CanvasRenderer.patchDrawingPreview(
    active.host,
    { x1: 600, y1: 240, x2: 700, y2: 240 },
    null,
    { lengthMm: 80, angleDeg: 0, clientX: 200, clientY: 180 }
);
assert.equal(field(active.host, "length"), sameLength);
assert.equal(field(active.host, "angle"), sameAngle);
assert.equal(context.document.activeElement, lengthInput);
assert.equal(lengthInput.value, "12", "focused text is not replaced by pointer movement");
context.document.activeElement = null;
context.AlmdinaBoardEditor.CanvasRenderer.patchDrawingPreview(
    active.host,
    { x1: 600, y1: 240, x2: 900, y2: 240 },
    null,
    { lengthMm: 180, angleDeg: -90, clientX: 240, clientY: 220 }
);
assert.equal(lengthInput.value, "180");
assert.equal(angleInput.value, "270");
assert.equal(active.host.querySelector("[data-abe-drawing-cursor]").classList.contains("is-visible"), true);
assert.equal(active.host.querySelector("[data-abe-drawing-cursor] [data-abe-drawing-length]").value, lengthInput.value);
assert.equal(active.host.querySelector("[data-abe-drawing-cursor] [data-abe-drawing-angle]").value, angleInput.value);

lengthInput.value = "350";
emit(lengthInput, "input");
context.AlmdinaBoardEditor.CanvasRenderer.patchDrawingPreview(
    active.host,
    { x1: 600, y1: 240, x2: 610, y2: 300 },
    null,
    { lengthMm: 22, angleDeg: 90, clientX: 860, clientY: 620 }
);
assert.equal(lengthInput.value, "350");
assert.equal(angleInput.value, "90");
const cursorTop = Number.parseFloat(active.host.querySelector("[data-abe-drawing-cursor]").style.top);
assert.ok(cursorTop < 560, `cursor overlaps the drawing actions at ${cursorTop}`);
lengthInput.value = "";
emit(lengthInput, "input");
context.document.activeElement = null;
context.AlmdinaBoardEditor.CanvasRenderer.patchDrawingPreview(
    active.host,
    null,
    null,
    { lengthMm: 140, angleDeg: 90, clientX: 160, clientY: 160 }
);
assert.equal(lengthInput.value, "140", "clearing a typed length lets the preview return");
lengthInput.value = "350";
emit(lengthInput, "input");
assert.equal(active.host.querySelector("[data-abe-drawing-cursor] [data-abe-drawing-length]").value, "350");
const entered = emit(angleInput, "keydown", { key: "Enter" });
assert.equal(entered.defaultPrevented, true);
assert.equal(entered.cancelBubble, true);
assert.equal(active.bubbles.length, 0);
assert.deepEqual(active.commits, [["350", "90"]]);

const sessionModel = context.AlmdinaBoardEditor.DrawingModel.createSession();
sessionModel.activate({ pieceInstanceId: "piece:special", widthMm: 600, lengthMm: 2100 });
sessionModel.markReady();
sessionModel.placePoint(0, 0);
assert.equal(sessionModel.placePolar(350, 90), true);
const committedNodes = sessionModel.current().document.paths[0].nodes;
assert.equal(sessionModel.current().document.paths[0].segments.length, 1);
assert.ok(Math.abs(committedNodes[1].x_mm) < 0.02);
assert.ok(Math.abs(committedNodes[1].y_mm - 350) < 0.02);
assert.equal(sessionModel.undo(), true);
assert.equal(sessionModel.current().document.paths.length, 0);
assert.equal(sessionModel.redo(), true);
assert.equal(sessionModel.current().document.paths[0].segments.length, 1);
const fingerprintBefore = context.AlmdinaBoardEditor.SessionDocument.distributionFingerprint(active.store.snapshot().session);
sessionModel.placePolar(120, 0);
assert.equal(context.AlmdinaBoardEditor.SessionDocument.distributionFingerprint(active.store.snapshot().session), fingerprintBefore);
assert.equal(active.store.snapshot().canUndo, false);

angleInput.value = "";
angleInput.dataset.locked = "";
lengthInput.value = "350";
lengthInput.dataset.locked = "1";
emit(lengthInput, "input");
context.document.activeElement = null;
context.AlmdinaBoardEditor.CanvasRenderer.patchDrawingPreview(
    active.host,
    null,
    null,
    { lengthMm: 15, angleDeg: 180, clientX: 120, clientY: 120 }
);
assert.equal(lengthInput.value, "350");
assert.equal(angleInput.value, "180");
const lengthOnly = emit(lengthInput, "keydown", { key: "Enter" });
assert.equal(lengthOnly.cancelBubble, true);
assert.deepEqual(active.commits[active.commits.length - 1], ["350", "180"]);

lengthInput.dataset.locked = "";
active.host.querySelectorAll("[data-abe-drawing-length]").forEach((input) => {
    input.dataset.locked = "";
});
angleInput.value = "90";
emit(angleInput, "input");
context.document.activeElement = null;
context.AlmdinaBoardEditor.CanvasRenderer.patchDrawingPreview(
    active.host,
    null,
    null,
    { lengthMm: 275, angleDeg: 10, clientX: 130, clientY: 130 }
);
assert.equal(angleInput.value, "90");
assert.equal(lengthInput.value, "275");
emit(angleInput, "keydown", { key: "Enter" });
assert.deepEqual(active.commits[active.commits.length - 1], ["275", "90"]);
assert.equal(active.commits.length, 3);

const zoomA = renderDrawing(context, readyDrawing("polyline", {
    mode: "draw", enabled: true, lengthMm: 350, angleDeg: 90,
}), 0.25);
const zoomB = renderDrawing(context, readyDrawing("polyline", {
    mode: "draw", enabled: true, lengthMm: 350, angleDeg: 90,
}), 4);
assert.match(zoomA.host.innerHTML, /scale\(0\.25\)/);
assert.match(zoomB.host.innerHTML, /scale\(4\)/);
assert.equal(field(zoomA.host, "length").value, "350");
assert.equal(field(zoomB.host, "length").value, "350");
assert.equal(field(zoomA.host, "angle").value, field(zoomB.host, "angle").value);

const boardStore = context.AlmdinaBoardEditor.createStore(payload());
boardStore.attachSession(session(), context.AlmdinaBoardEditor.History.create(session()));
boardStore.noteDraftBaseline({ canSaveLayout: true, draftVersion: 2, savedFingerprint: "fp-layout" });
boardStore.setEditorMode("board");
boardStore.selectPiece(1, { pieceKey: "special", mode: "replace" });
const boardHost = hostFor(context);
context.AlmdinaBoardEditor.CanvasRenderer.render(boardHost, boardStore.snapshot(), {});
assert.equal(boardHost.querySelector("[data-abe-drawing-measure]"), null);
assert.equal(boardHost.querySelector("[data-abe-drawing-cursor]"), null);
assert.doesNotMatch(boardHost.innerHTML, /data-abe-drawing-workspace/);

const selected = renderDrawing(context, readyDrawing("select", {
    mode: "edit",
    enabled: true,
    lengthMm: 350,
    angleDeg: 0,
}, [{
    id: "path-1",
    closed: false,
    selected: true,
    points: [{ id: "n1", x: 10, y: 20 }, { id: "n2", x: 360, y: 20 }],
}]));
assert.equal(field(selected.host, "length").value, "350");
assert.equal(field(selected.host, "angle").value, "0");
assert.match(selected.host.innerHTML, /data-abe-drawing-path="path-1"[^>]*d="[^"]*360 20/);
const edited = renderDrawing(context, readyDrawing("select", {
    mode: "edit",
    enabled: true,
    lengthMm: 400,
    angleDeg: 0,
}, [{
    id: "path-1",
    closed: false,
    selected: true,
    points: [{ id: "n1", x: 10, y: 20 }, { id: "n2", x: 410, y: 20 }],
}]));
assert.equal(field(edited.host, "length").value, "400");
assert.match(edited.host.innerHTML, /410 20/);
assert.doesNotMatch(edited.host.innerHTML, /360 20/);

const closed = renderDrawing(context, readyDrawing("select", {
    mode: "closed",
    enabled: false,
    messageKey: "Closed paths cannot be resized one segment at a time.",
}));
assert.equal(closed.host.querySelector("[data-abe-drawing-measure]"), null);
assert.match(closed.host.__drawProps.innerHTML, /Closed paths cannot be resized one segment at a time/);
assert.equal(closed.host.querySelector("[data-abe-drawing-length]"), null);
assert.equal(closed.host.__drawProps.querySelector("[data-abe-drawing-length]"), null);

const drawingSource = fs.readFileSync(path.join(root, "public/js/board_editor/drawing_model.js"), "utf8");
const controllerSource = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
assert.doesNotMatch(drawingSource, /layout_json|special_shape_geometry_json/);
assert.doesNotMatch(controllerSource, /layout_json|special_shape_geometry_json/);
assert.match(controllerSource, /commitNumeric\(\{/);
assert.match(controllerSource, /drawingSession\.placePoint\(resolved\.x, resolved\.y\)/);
assert.doesNotMatch(controllerSource, /if \(useLength == null \|\| useAngle == null\) return/);

function commitHarness(scale) {
    const drawn = context.AlmdinaBoardEditor.DrawingModel.createSession();
    drawn.activate({ pieceInstanceId: "piece:special", widthMm: 600, lengthMm: 2100 });
    drawn.markReady();
    const entry = { lengthText: "", angleText: "", lengthLocked: false, angleLocked: false };
    const pointer = { length: null, angle: null };
    const calls = [];
    const host = hostFor(context);
    const { createStore, History } = context.AlmdinaBoardEditor;
    const store = createStore(payload());
    store.attachSession(session(), History.create(session()));
    store.noteDraftBaseline({ canSaveLayout: true, draftVersion: 2, savedFingerprint: "fp-layout" });
    store.setEditorMode("drawing");
    store.selectPiece(1, { pieceKey: "special", mode: "replace" });
    store.setViewport({
        scale: scale || 1,
        scrollX: 0,
        scrollY: 0,
        padX: 0,
        padY: 0,
        opened: true,
        userAdjusted: true,
        cameraToken: 1,
    });
    function viewOf() {
        const record = drawn.current();
        const path = record.document.paths[0];
        const paths = [];
        if (path) {
            paths.push({
                id: path.id,
                closed: path.closed === true,
                selected: true,
                active: true,
                points: path.nodes.map((node) => ({ id: node.id, x: node.x_mm, y: node.y_mm })),
            });
        } else if (record.cursor) {
            paths.push({
                id: "draft-start",
                closed: false,
                selected: true,
                active: true,
                points: [{ id: record.cursor.nodeId, x: record.cursor.x, y: record.cursor.y }],
            });
        }
        const error = record.measureError;
        return readyDrawing("polyline", {
            mode: "draw",
            enabled: Boolean(record.cursor),
            lengthMm: null,
            angleDeg: null,
            lengthText: entry.lengthText,
            angleText: entry.angleText,
            lengthLocked: entry.lengthLocked,
            angleLocked: entry.angleLocked,
            errorKey: error && error.messageKey,
            errorField: error && error.field,
        }, paths);
    }
    function paint() {
        store.setDrawingView(viewOf());
        context.AlmdinaBoardEditor.CanvasRenderer.render(host, store.snapshot(), {
            commitDrawingHud(length, angle) {
                calls.push([length, angle]);
                const result = drawn.commitNumeric({
                    lengthText: length,
                    angleText: angle,
                    previewLength: pointer.length,
                    previewAngle: pointer.angle,
                });
                if (result.ok) {
                    entry.lengthText = "";
                    entry.angleText = "";
                    entry.lengthLocked = false;
                    entry.angleLocked = false;
                    pointer.length = null;
                    pointer.angle = null;
                }
                paint();
                return result;
            },
            onDrawingMeasureInput(field, value) {
                if (field === "angle") {
                    entry.angleLocked = String(value || "").trim() !== "";
                    entry.angleText = entry.angleLocked ? String(value) : "";
                } else {
                    entry.lengthLocked = String(value || "").trim() !== "";
                    entry.lengthText = entry.lengthLocked ? String(value) : "";
                }
            },
            drawingPointerDown(event) {
                if (!event || event.button !== 0 || event.doorX == null) return false;
                drawn.placePoint(event.doorX, event.doorY);
                entry.lengthText = "";
                entry.angleText = "";
                entry.lengthLocked = false;
                entry.angleLocked = false;
                paint();
                return true;
            },
        });
    }
    paint();
    return { host, session: drawn, store, calls, pointer, entry, paint };
}

function typeMeasure(host, length, angle) {
    const lengthInput = field(host, "length");
    const angleInput = field(host, "angle");
    lengthInput.value = length;
    emit(lengthInput, "input");
    angleInput.value = angle;
    emit(angleInput, "input");
    return { lengthInput, angleInput };
}

function nodesOf(session) {
    const path = session.current().document.paths[0];
    return path ? path.nodes : [];
}

const numeric = commitHarness(1);
emit(numeric.host.querySelector("[data-abe-stage]"), "pointerdown", { button: 0, doorX: 100, doorY: 100 });
assert.equal(numeric.session.current().document.paths.length, 0, "start click does not create a segment");
const typed = typeMeasure(numeric.host, "200", "90");
const beforeClick = numeric.session.current().document.paths.length;
const enteredSegment = emit(typed.angleInput, "keydown", { key: "Enter" });
assert.equal(enteredSegment.defaultPrevented, true);
assert.equal(enteredSegment.cancelBubble, true);
assert.equal(beforeClick, 0);
assert.equal(numeric.calls.length, 1);
assert.deepEqual(numeric.calls[0], ["200", "90"]);
const firstNodes = nodesOf(numeric.session);
assert.equal(firstNodes.length, 2);
assert.equal(numeric.session.current().document.paths[0].segments.length, 1);
assert.equal(firstNodes[1].x_mm, 100);
assert.equal(firstNodes[1].y_mm, 300);
assert.match(numeric.host.querySelector("[data-abe-drawing-path]").getAttribute("d"), /M100 100 L100 300/);
assert.equal(numeric.session.current().cursor.x, 100);
assert.equal(numeric.session.current().cursor.y, 300);
assert.equal(field(numeric.host, "length").disabled, false);
assert.equal(field(numeric.host, "length").value, "");
assert.equal(numeric.session.documentDirty(numeric.session.current()), true);

typeMeasure(numeric.host, "100", "0");
emit(field(numeric.host, "angle"), "keydown", { key: "Enter" });
const chained = nodesOf(numeric.session);
assert.equal(chained.length, 3);
assert.equal(numeric.session.current().document.paths[0].segments.length, 2);
assert.equal(chained[2].x_mm, 200);
assert.equal(chained[2].y_mm, 300);
assert.match(numeric.host.querySelector("[data-abe-drawing-path]").getAttribute("d"), /L200 300/);

const arabicDigits = commitHarness(1);
emit(arabicDigits.host.querySelector("[data-abe-stage]"), "pointerdown", { button: 0, doorX: 100, doorY: 100 });
typeMeasure(arabicDigits.host, "٢٠٠", "٩٠");
emit(field(arabicDigits.host, "angle"), "keydown", { key: "Enter" });
assert.equal(nodesOf(arabicDigits.session)[1].x_mm, 100);
assert.equal(nodesOf(arabicDigits.session)[1].y_mm, 300);

const fromLength = commitHarness(1);
emit(fromLength.host.querySelector("[data-abe-stage]"), "pointerdown", { button: 0, doorX: 100, doorY: 100 });
typeMeasure(fromLength.host, "200", "90");
const lengthField = field(fromLength.host, "length");
lengthField.focus();
emit(lengthField, "keydown", { key: "Enter" });
assert.equal(fromLength.calls.length, 1);
assert.equal(fromLength.session.current().document.paths[0].segments.length, 1);
assert.equal(nodesOf(fromLength.session)[1].y_mm, 300);

const moved = commitHarness(1);
emit(moved.host.querySelector("[data-abe-stage]"), "pointerdown", { button: 0, doorX: 100, doorY: 100 });
typeMeasure(moved.host, "200", "90");
moved.pointer.length = 40;
moved.pointer.angle = 0;
context.AlmdinaBoardEditor.CanvasRenderer.patchDrawingPreview(
    moved.host,
    { x1: 0, y1: 0, x2: 40, y2: 0 },
    null,
    { lengthMm: 40, angleDeg: 0, clientX: 30, clientY: 30 }
);
assert.equal(field(moved.host, "length").value, "200");
assert.equal(field(moved.host, "angle").value, "90");
emit(field(moved.host, "angle"), "keydown", { key: "Enter" });
assert.equal(nodesOf(moved.session)[1].x_mm, 100);
assert.equal(nodesOf(moved.session)[1].y_mm, 300);

const mixed = commitHarness(1);
const stage = () => mixed.host.querySelector("[data-abe-stage]");
emit(stage(), "pointerdown", { button: 0, doorX: 100, doorY: 100 });
emit(stage(), "pointerdown", { button: 0, doorX: 180, doorY: 100 });
typeMeasure(mixed.host, "50", "90");
emit(field(mixed.host, "angle"), "keydown", { key: "Enter", code: "NumpadEnter", keyCode: 13 });
emit(stage(), "pointerdown", { button: 0, doorX: 180, doorY: 220 });
const mixedNodes = nodesOf(mixed.session);
assert.equal(mixed.session.current().document.paths.length, 1);
assert.equal(mixed.session.current().document.paths[0].segments.length, 3);
assert.equal(mixedNodes.length, 4);
assert.equal(mixedNodes[0].x_mm, 100);
assert.equal(mixedNodes[1].x_mm, 180);
assert.equal(mixedNodes[1].y_mm, 100);
assert.equal(mixedNodes[2].x_mm, 180);
assert.equal(mixedNodes[2].y_mm, 150);
assert.equal(mixedNodes[3].x_mm, 180);
assert.equal(mixedNodes[3].y_mm, 220);
assert.equal(mixedNodes[1].id !== mixedNodes[2].id && mixed.session.current().document.paths[0].segments[1].from_node, mixedNodes[1].id);

function rejected(length, angle, message, preview) {
    const harness = commitHarness(1);
    emit(harness.host.querySelector("[data-abe-stage]"), "pointerdown", { button: 0, doorX: 100, doorY: 100 });
    const cursor = harness.session.current().cursor.nodeId;
    if (preview) {
        harness.pointer.length = preview.length;
        harness.pointer.angle = preview.angle;
    }
    typeMeasure(harness.host, length, angle);
    emit(field(harness.host, "angle"), "keydown", { key: "Enter" });
    assert.equal(harness.session.current().document.paths.length, 0, message);
    assert.equal(harness.session.current().cursor.nodeId, cursor, message);
    assert.equal(harness.host.querySelector("[data-abe-drawing-path]"), null, message);
    const alert = harness.host.querySelector("[data-abe-drawing-measure-error]");
    assert.ok(alert, message);
    assert.match(harness.host.innerHTML, new RegExp(message.replace(/[.]/g, "\\.")));
    assert.equal(field(harness.host, "length").disabled, false);
}
rejected("0", "90", "A zero-length segment was not created");
rejected("abc", "90", "Enter a valid length");
rejected("200", "north", "Enter a valid angle");
rejected("", "90", "Enter a length");

const history = commitHarness(1);
emit(history.host.querySelector("[data-abe-stage]"), "pointerdown", { button: 0, doorX: 100, doorY: 100 });
typeMeasure(history.host, "200", "90");
emit(field(history.host, "angle"), "keydown", { key: "Enter" });
assert.equal(history.session.undo(), true);
history.paint();
assert.equal(history.session.current().document.paths.length, 0);
assert.equal(history.host.querySelector("[data-abe-drawing-path]"), null);
assert.equal(history.session.current().cursor.x, 100);
assert.equal(history.session.redo(), true);
history.paint();
assert.equal(nodesOf(history.session)[1].y_mm, 300);
assert.match(history.host.querySelector("[data-abe-drawing-path]").getAttribute("d"), /L100 300/);

const zoomedOut = commitHarness(0.25);
const zoomedIn = commitHarness(4);
[zoomedOut, zoomedIn].forEach((harness) => {
    emit(harness.host.querySelector("[data-abe-stage]"), "pointerdown", { button: 0, doorX: 100, doorY: 100 });
    typeMeasure(harness.host, "200", "90");
    emit(field(harness.host, "angle"), "keydown", { key: "Enter" });
});
assert.equal(nodesOf(zoomedOut.session)[1].x_mm, nodesOf(zoomedIn.session)[1].x_mm);
assert.equal(nodesOf(zoomedOut.session)[1].y_mm, nodesOf(zoomedIn.session)[1].y_mm);
assert.equal(
    zoomedOut.host.querySelector("[data-abe-drawing-path]").getAttribute("d"),
    zoomedIn.host.querySelector("[data-abe-drawing-path]").getAttribute("d")
);
assert.notEqual(
    zoomedOut.host.querySelector(".abe-svg").getAttribute("width"),
    zoomedIn.host.querySelector(".abe-svg").getAttribute("width")
);

const saved = JSON.parse(JSON.stringify(numeric.session.current().document));
const restored = context.AlmdinaBoardEditor.DrawingModel.createSession();
restored.activate({ pieceInstanceId: "piece:special", widthMm: 600, lengthMm: 2100 });
const ticket = restored.beginLoad();
assert.equal(restored.applyLoaded("piece:special", ticket.token, {
    ok: true,
    drawing: saved,
    drawing_version: 4,
}), true);
const restoredPath = restored.current().document.paths[0];
assert.equal(restoredPath.nodes.length, 3);
assert.equal(restoredPath.nodes[1].y_mm, 300);
assert.equal(restoredPath.nodes[2].x_mm, 200);
const restoredLength = context.AlmdinaBoardEditor.DrawingSpace.lengthMm(
    restoredPath.nodes[0].x_mm,
    restoredPath.nodes[0].y_mm,
    restoredPath.nodes[1].x_mm,
    restoredPath.nodes[1].y_mm
);
assert.ok(Math.abs(restoredLength - 200) < 0.001);

const layoutFingerprint = context.AlmdinaBoardEditor.SessionDocument.distributionFingerprint(boardStore.snapshot().session);
const boardUndo = boardStore.snapshot().canUndo;
numeric.session.commitNumeric({ lengthText: "15", angleText: "0" });
assert.equal(context.AlmdinaBoardEditor.SessionDocument.distributionFingerprint(boardStore.snapshot().session), layoutFingerprint);
assert.equal(boardStore.snapshot().canUndo, boardUndo);
assert.equal(boardStore.snapshot().editorMode, "board");
assert.equal(boardHost.querySelector("[data-abe-drawing-measure]"), null);

const outside = commitHarness(1);
emit(outside.host.querySelector("[data-abe-stage]"), "pointerdown", { button: 0, doorX: 100, doorY: 100 });
typeMeasure(outside.host, "500", "180");
emit(field(outside.host, "length"), "keydown", { key: "Enter" });
assert.equal(nodesOf(outside.session)[1].x_mm, -400);
assert.equal(nodesOf(outside.session)[1].y_mm, 100);
assert.equal(outside.host.querySelector("[data-abe-drawing-measure-error]"), null);

const Space = context.AlmdinaBoardEditor.DrawingSpace;
const pieceFrame = (rotation) => Space.pieceFrame({
    sheet_no: 1,
    rotation_deg: rotation,
    placement_cm: { x: 0, y: 0 },
    entry_pivot_mm: { x: 0, y: 0 },
    pivot_mm: { x: 0, y: 0 },
}, { 1: { origin_x_mm: 0, origin_y_mm: 0 } }, { widthMm: 600 });
const straight = Space.doorToWorld(pieceFrame(0), 100, 300);
const turned = Space.doorToWorld(pieceFrame(90), 100, 300);
assert.equal(straight.x, 100);
assert.equal(straight.y, 300);
assert.ok(Math.abs(turned.x - straight.x) > 1 || Math.abs(turned.y - straight.y) > 1);

const Renderer = context.AlmdinaBoardEditor.CanvasRenderer;
const hudGap = 24;
const hudHysteresis = 16;

function hudBox(position, width, height) {
    return {
        left: position.left,
        top: position.top,
        right: position.left + width,
        bottom: position.top + height,
    };
}

function pointOutside(box, x, y) {
    return x < box.left || x > box.right || y < box.top || y > box.bottom;
}

function placeHud(spec) {
    return Renderer.computePolylineHudPosition(Object.assign({
        width: 180,
        height: 28,
        gap: hudGap,
        hysteresis: hudHysteresis,
        bounds: { left: 8, top: 8, right: 892, bottom: 552 },
    }, spec));
}

const rightHud = placeHud({ startX: 120, startY: 240, endX: 360, endY: 250, previousSide: "left" });
assert.equal(rightHud.side, "right");
assert.equal(rightHud.placedSide, "right");
assert.equal(rightHud.above, true);
assert.equal(rightHud.left, 120 + hudGap);
assert.equal(rightHud.top, 240 - 28 - hudGap);
assert.ok(pointOutside(hudBox(rightHud, 180, 28), 120, 240));
assert.ok(pointOutside(hudBox(rightHud, 180, 28), 360, 250));
const rightHudFurther = placeHud({ startX: 120, startY: 240, endX: 560, endY: 280, previousSide: "right" });
assert.equal(rightHudFurther.left, rightHud.left);
assert.equal(rightHudFurther.top, rightHud.top);
assert.equal(rightHudFurther.side, "right");

const leftHud = placeHud({ startX: 520, startY: 240, endX: 300, endY: 230, previousSide: "right" });
assert.equal(leftHud.side, "left");
assert.equal(leftHud.placedSide, "left");
assert.equal(leftHud.above, true);
assert.equal(leftHud.left, 520 - 180 - hudGap);
assert.equal(leftHud.top, 240 - 28 - hudGap);
assert.ok(pointOutside(hudBox(leftHud, 180, 28), 520, 240));
assert.ok(pointOutside(hudBox(leftHud, 180, 28), 300, 230));
const leftHudFurther = placeHud({ startX: 520, startY: 240, endX: 80, endY: 300, previousSide: "left" });
assert.equal(leftHudFurther.left, leftHud.left);
assert.equal(leftHudFurther.top, leftHud.top);
assert.equal(leftHudFurther.side, "left");

let verticalSide = "right";
let verticalBox = null;
[260, 280, 300, 340].forEach((y) => {
    const placed = placeHud({ startX: 300, startY: 80, endX: 300, endY: y, previousSide: verticalSide });
    verticalSide = placed.side;
    if (!verticalBox) verticalBox = { left: placed.left, top: placed.top };
    assert.equal(placed.left, verticalBox.left);
    assert.equal(placed.top, verticalBox.top);
});
assert.equal(verticalSide, "right");

let jitterSide = "right";
[-8, 6, -12, 10, -15].forEach((dx) => {
    const placed = placeHud({ startX: 300, startY: 80, endX: 300 + dx, endY: 260, previousSide: jitterSide });
    jitterSide = placed.side;
});
assert.equal(jitterSide, "right", "small motion around vertical keeps the current side");
const crossed = placeHud({ startX: 300, startY: 80, endX: 300 - 20, endY: 260, previousSide: jitterSide });
assert.equal(crossed.side, "left");
const crossedBack = placeHud({ startX: 300, startY: 80, endX: 300 + 20, endY: 260, previousSide: "left" });
assert.equal(crossedBack.side, "right");

const rightEdge = placeHud({ startX: 820, startY: 180, endX: 880, endY: 180, previousSide: "right" });
assert.equal(rightEdge.side, "right");
assert.equal(rightEdge.placedSide, "left");
assert.ok(rightEdge.left >= 8);
assert.ok(rightEdge.left + 180 <= 892);
assert.ok(pointOutside(hudBox(rightEdge, 180, 28), 820, 180));
const rightEdgeStill = placeHud({ startX: 820, startY: 180, endX: 900, endY: 220, previousSide: "right" });
assert.equal(rightEdgeStill.left, rightEdge.left);
assert.equal(rightEdgeStill.top, rightEdge.top);

const leftEdge = placeHud({ startX: 40, startY: 180, endX: 10, endY: 180, previousSide: "left" });
assert.equal(leftEdge.side, "left");
assert.equal(leftEdge.placedSide, "right");
assert.ok(leftEdge.left >= 8);
assert.ok(pointOutside(hudBox(leftEdge, 180, 28), 40, 180));

const topEdge = placeHud({ startX: 200, startY: 16, endX: 360, endY: 80, previousSide: "right" });
assert.equal(topEdge.above, false);
assert.ok(topEdge.top >= 8);
assert.ok(pointOutside(hudBox(topEdge, 180, 28), 200, 16));

const bottomEdge = placeHud({
    startX: 200,
    startY: 530,
    endX: 360,
    endY: 540,
    previousSide: "right",
    bounds: { left: 8, top: 8, right: 892, bottom: 552 },
});
assert.equal(bottomEdge.above, true);
assert.ok(bottomEdge.top + 28 <= 552);
assert.ok(pointOutside(hudBox(bottomEdge, 180, 28), 200, 530));
const bottomEdgeStill = placeHud({
    startX: 200,
    startY: 530,
    endX: 560,
    endY: 600,
    previousSide: "right",
    bounds: { left: 8, top: 8, right: 892, bottom: 552 },
});
assert.equal(bottomEdgeStill.left, bottomEdge.left);
assert.equal(bottomEdgeStill.top, bottomEdge.top);

const englishHud = placeHud({ startX: 80, startY: 200, endX: 280, endY: 200, width: 160, previousSide: "left" });
const arabicHud = placeHud({ startX: 80, startY: 200, endX: 280, endY: 200, width: 260, previousSide: "left" });
assert.equal(englishHud.left, 80 + hudGap);
assert.equal(englishHud.left, arabicHud.left);
assert.ok(arabicHud.left + 260 > englishHud.left + 160);
assert.ok(pointOutside(hudBox(arabicHud, 260, 28), 80, 200));
const openBounds = { left: -400, top: -100, right: 1200, bottom: 800 };
const englishLeft = placeHud({ startX: 500, startY: 200, endX: 280, endY: 200, width: 160, previousSide: "right", bounds: openBounds });
const arabicLeft = placeHud({ startX: 500, startY: 200, endX: 280, endY: 200, width: 260, previousSide: "right", bounds: openBounds });
assert.equal(arabicLeft.left, 500 - 260 - hudGap);
assert.equal(englishLeft.left, 500 - 160 - hudGap);
assert.equal(arabicLeft.left + 260, englishLeft.left + 160);
assert.equal(arabicLeft.left + 260, 500 - hudGap);

function screenGap(scale) {
    const start = Renderer.worldToScreen(0, 0, { scale, padX: 0, padY: 0, minX: 0, minY: 0, scrollX: 0, scrollY: 0 });
    const end = Renderer.worldToScreen(100, 0, { scale, padX: 0, padY: 0, minX: 0, minY: 0, scrollX: 0, scrollY: 0 });
    const placed = placeHud({
        startX: start.x,
        startY: start.y,
        endX: end.x,
        endY: end.y,
        previousSide: "left",
        bounds: { left: -1000, top: -1000, right: 4000, bottom: 4000 },
    });
    return { travel: end.x - start.x, gap: placed.left - start.x, side: placed.side, left: placed.left, top: placed.top };
}
const zoomedGap = screenGap(1);
const closerGap = screenGap(4);
assert.ok(Math.abs(closerGap.travel / zoomedGap.travel - 4) < 0.001);
assert.equal(zoomedGap.gap, hudGap);
assert.equal(closerGap.gap, hudGap);
assert.equal(zoomedGap.side, "right");

const SpaceApi = context.AlmdinaBoardEditor.DrawingSpace;
function rotatedFrame(rotation) {
    return SpaceApi.pieceFrame({
        sheet_no: 1,
        rotation_deg: rotation,
        placement_cm: { x: 0, y: 0 },
        entry_pivot_mm: { x: 0, y: 0 },
        pivot_mm: { x: 0, y: 0 },
    }, { 1: { origin_x_mm: 0, origin_y_mm: 0 } }, { widthMm: 600 });
}
function screenSide(rotation, x2, y2) {
    const frame = rotatedFrame(rotation);
    const start = SpaceApi.doorToWorld(frame, 0, 0);
    const end = SpaceApi.doorToWorld(frame, x2, y2);
    const camera = { scale: 1, padX: 0, padY: 0, minX: 0, minY: 0, scrollX: 0, scrollY: 0 };
    const startScreen = Renderer.worldToScreen(start.x, start.y, camera);
    const endScreen = Renderer.worldToScreen(end.x, end.y, camera);
    return {
        startScreen,
        endScreen,
        placed: placeHud({
            startX: startScreen.x,
            startY: startScreen.y,
            endX: endScreen.x,
            endY: endScreen.y,
            previousSide: endScreen.x >= startScreen.x ? "left" : "right",
            bounds: { left: -2000, top: -2000, right: 2000, bottom: 2000 },
        }),
    };
}
const turnedDown = screenSide(90, 0, 200);
assert.equal(turnedDown.placed.side, "left");
assert.equal(turnedDown.placed.above, true);
assert.equal(turnedDown.placed.left, turnedDown.startScreen.x - 180 - hudGap);
assert.equal(turnedDown.placed.top, turnedDown.startScreen.y - 28 - hudGap);
assert.notEqual(turnedDown.placed.left, turnedDown.endScreen.x + hudGap);
const turnedRight = screenSide(180, 200, 0);
assert.equal(turnedRight.placed.side, "left");
assert.equal(turnedRight.placed.left, turnedRight.startScreen.x - 180 - hudGap);
const turnedThirty = screenSide(30, 200, 0);
assert.equal(turnedThirty.placed.side, "right");
assert.equal(turnedThirty.placed.left, turnedThirty.startScreen.x + hudGap);

function identityHost() {
    const drawn = renderDrawing(context, readyDrawing("polyline", {
        mode: "draw",
        enabled: true,
        lengthMm: 10,
        angleDeg: 0,
    }));
    const world = drawn.host.querySelector(".abe-world");
    const svg = drawn.host.querySelector(".abe-svg");
    world.setAttribute("transform", "translate(0,0) scale(1)");
    svg.setAttribute("width", "900");
    svg.setAttribute("height", "640");
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 900, height: 640, right: 900, bottom: 640 });
    return drawn;
}

function movePreview(host, x1, y1, x2, y2, hud) {
    Renderer.patchDrawingPreview(host, { x1, y1, x2, y2 }, null, Object.assign({
        lengthMm: Math.abs(x2 - x1),
        angleDeg: 0,
        clientX: x2,
        clientY: y2,
    }, hud || {}));
    return host.querySelector("[data-abe-drawing-cursor]");
}

const placedHost = identityHost();
const anchorX = 400;
const anchorY = 240;
const rightCursor = movePreview(placedHost.host, anchorX, anchorY, 560, 250, { lengthMm: 160 });
assert.equal(rightCursor.getAttribute("data-abe-hud-side"), "right");
assert.equal(rightCursor.getAttribute("data-abe-hud-placed"), "right");
assert.equal(Number.parseFloat(rightCursor.style.left), anchorX + hudGap);
assert.equal(Number.parseFloat(rightCursor.style.top), anchorY - 28 - hudGap);
assert.equal(field(placedHost.host, "length").value, "160");
const anchoredRight = { left: rightCursor.style.left, top: rightCursor.style.top };
movePreview(placedHost.host, anchorX, anchorY, 660, 250, { lengthMm: 260, clientX: 700, clientY: 40 });
assert.equal(rightCursor.style.left, anchoredRight.left);
assert.equal(rightCursor.style.top, anchoredRight.top);
assert.equal(placedHost.host.querySelector("[data-abe-drawing-preview]").getAttribute("x2"), "660");
assert.equal(field(placedHost.host, "length").value, "260");
movePreview(placedHost.host, anchorX, anchorY, 860, 280, { lengthMm: 460, clientX: 20, clientY: 600 });
assert.equal(rightCursor.style.left, anchoredRight.left);
assert.equal(rightCursor.style.top, anchoredRight.top);
assert.equal(rightCursor, placedHost.host.querySelector("[data-abe-drawing-cursor]"));

const leftCursor = movePreview(placedHost.host, anchorX, anchorY, 200, 230, { lengthMm: 200 });
assert.equal(leftCursor.getAttribute("data-abe-hud-side"), "left");
assert.equal(Number.parseFloat(leftCursor.style.left), anchorX - 180 - hudGap);
assert.equal(Number.parseFloat(leftCursor.style.top), anchorY - 28 - hudGap);
const anchoredLeft = { left: leftCursor.style.left, top: leftCursor.style.top };
movePreview(placedHost.host, anchorX, anchorY, 80, 260, { lengthMm: 320, clientX: 8, clientY: 8 });
assert.equal(leftCursor.style.left, anchoredLeft.left);
assert.equal(leftCursor.style.top, anchoredLeft.top);
movePreview(placedHost.host, anchorX, anchorY, 20, 300, { lengthMm: 380 });
assert.equal(leftCursor.style.left, anchoredLeft.left);
assert.equal(leftCursor.style.top, anchoredLeft.top);

const floating = placedHost.host.querySelector("[data-abe-drawing-cursor] [data-abe-drawing-length]");
floating.value = "200";
emit(floating, "input");
floating.focus();
movePreview(placedHost.host, anchorX, anchorY, 760, 240, { lengthMm: 360, clientX: 220, clientY: 190 });
assert.equal(leftCursor.style.left, anchoredLeft.left);
assert.equal(leftCursor.style.top, anchoredLeft.top);
assert.equal(leftCursor.getAttribute("data-abe-hud-side"), "left");
assert.equal(context.document.activeElement, floating);
assert.equal(floating.value, "200");
assert.equal(placedHost.host.querySelector("[data-abe-drawing-cursor] [data-abe-drawing-length]"), floating);
assert.equal(placedHost.commits.length, 0);
context.document.activeElement = null;
const switched = movePreview(placedHost.host, anchorX, anchorY, 700, 240, { lengthMm: 300 });
assert.equal(switched.getAttribute("data-abe-hud-side"), "right");
assert.equal(Number.parseFloat(switched.style.left), anchorX + hudGap);
assert.equal(Number.parseFloat(switched.style.top), anchorY - 28 - hudGap);
assert.equal(floating.value, "200");
movePreview(placedHost.host, anchorX, anchorY, 520, 200, { lengthMm: 120, clientX: 440, clientY: 200 });
assert.equal(switched.style.left, `${anchorX + hudGap}px`);
assert.equal(switched.style.top, `${anchorY - 28 - hudGap}px`);

const nextAnchor = movePreview(placedHost.host, 400, 300, 620, 300, { lengthMm: 220 });
assert.equal(nextAnchor.getAttribute("data-abe-hud-side"), "right");
assert.equal(Number.parseFloat(nextAnchor.style.left), 400 + hudGap);
assert.equal(Number.parseFloat(nextAnchor.style.top), 300 - 28 - hudGap);
const nextFixed = { left: nextAnchor.style.left, top: nextAnchor.style.top };
movePreview(placedHost.host, 400, 300, 860, 340, { lengthMm: 460, clientX: 430, clientY: 250 });
assert.equal(nextAnchor.style.left, nextFixed.left);
assert.equal(nextAnchor.style.top, nextFixed.top);

const edgeCursor = movePreview(placedHost.host, 820, 180, 900, 180, { lengthMm: 80 });
assert.equal(edgeCursor.getAttribute("data-abe-hud-side"), "right");
assert.equal(edgeCursor.getAttribute("data-abe-hud-placed"), "left");
assert.ok(Number.parseFloat(edgeCursor.style.left) + 180 <= 892);
assert.ok(Number.parseFloat(edgeCursor.style.top) + 28 <= 560);
const edgeFixed = edgeCursor.style.left;
movePreview(placedHost.host, 820, 180, 980, 200, { lengthMm: 160 });
assert.equal(edgeCursor.style.left, edgeFixed);

let drawingClicks = 0;
const pointerHost = renderDrawing(context, readyDrawing("polyline", {
    mode: "draw",
    enabled: true,
    lengthMm: 10,
    angleDeg: 0,
}), 1, {
    drawingPointerDown() {
        drawingClicks += 1;
        return true;
    },
});
const worldNode = pointerHost.host.querySelector(".abe-world");
const svgNode = pointerHost.host.querySelector(".abe-svg");
worldNode.setAttribute("transform", "translate(0,0) scale(1)");
svgNode.setAttribute("width", "900");
svgNode.setAttribute("height", "640");
svgNode.getBoundingClientRect = () => ({ left: 0, top: 0, width: 900, height: 640, right: 900, bottom: 640 });
movePreview(pointerHost.host, 100, 200, 360, 210);
const cursorInput = pointerHost.host.querySelector("[data-abe-drawing-cursor] [data-abe-drawing-angle]");
cursorInput.value = "90";
emit(cursorInput, "pointerdown", { button: 0, clientX: 400, clientY: 180 });
emit(cursorInput, "click", { button: 0, clientX: 400, clientY: 180 });
assert.equal(drawingClicks, 0);
assert.equal(cursorInput.value, "90");
emit(pointerHost.host.querySelector("[data-abe-stage]"), "pointerdown", { button: 0, clientX: 360, clientY: 210 });
assert.equal(drawingClicks, 1);
assert.equal(pointerHost.commits.length, 0);

const toolbarLength = field(pointerHost.host, "length");
const toolbarAngle = field(pointerHost.host, "angle");
toolbarLength.value = "200";
emit(toolbarLength, "input");
toolbarAngle.value = "90";
emit(toolbarAngle, "input");
movePreview(pointerHost.host, 80, 200, 40, 200);
emit(toolbarAngle, "keydown", { key: "Enter" });
assert.deepEqual(pointerHost.commits, [["200", "90"]]);
assert.equal(pointerHost.store.snapshot().canUndo, false);
assert.equal(pointerHost.store.snapshot().editorMode, "drawing");
assert.equal(boardHost.querySelector("[data-abe-drawing-cursor]"), null);

console.log("board editor polyline input tests ok");
