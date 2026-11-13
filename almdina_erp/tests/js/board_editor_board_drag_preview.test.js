"use strict";

/**
 * Board-drag preview must shift frame + pieces once as a single visual unit.
 * Regression: the sheet frame used to also carry data-sheet-group, so
 * patchDragPreview translated it twice while pieces moved once.
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load() {
    const files = [
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/snap_geometry.js",
        "public/js/board_editor/rotation_geometry.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_edge_display.js",
        "public/js/board_editor/plan_display_style.js",
        "public/js/board_editor/plan_edge_marks.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
        document: {
            createElementNS: () => ({
                setAttribute() {},
                style: {},
                appendChild() {},
            }),
        },
        console,
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    });
    return context.window.AlmdinaBoardEditor;
}

function makeAttrMap(initial) {
    const attrs = Object.assign({}, initial || {});
    return {
        getAttribute(name) {
            return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
        },
        setAttribute(name, value) {
            attrs[name] = String(value);
        },
        removeAttribute(name) {
            delete attrs[name];
        },
        _attrs: attrs,
    };
}

function makeNode(attrs, children, parent) {
    const node = makeAttrMap(attrs);
    node.children = children || [];
    node.parentNode = parent || null;
    node.style = {};
    node.children.forEach((child) => {
        child.parentNode = node;
    });
    node.appendChild = (child) => {
        node.children.push(child);
        child.parentNode = node;
        return child;
    };
    node.querySelectorAll = (selector) => {
        const match = selector.match(/^\[([^=\]]+)(?:=\"([^\"]*)\")?\]$/);
        if (!match) return [];
        const attr = match[1];
        const wanted = match[2];
        const out = [];
        function walk(current) {
            const value = current.getAttribute(attr);
            if (wanted === undefined ? value != null : value === wanted) out.push(current);
            (current.children || []).forEach(walk);
        }
        walk(node);
        return out;
    };
    node.querySelector = (selector) => {
        if (selector === ".abe-world") return node;
        const found = node.querySelectorAll(selector);
        return found.length ? found[0] : null;
    };
    return node;
}

const editor = load();
const { CanvasRenderer, SessionDocument, createStore, History } = editor;

// Source contract: frame keeps data-sheet; only outer host owns data-sheet-group.
{
    const source = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
    assert.match(source, /data-sheet="\$\{esc\(String\(element\.sheet_no\)\)\}"/);
    assert.doesNotMatch(
        source,
        /class="abe-sheet[^"]*"[\s\S]{0,40}data-sheet-group=/
    );
    assert.match(source, /node\.parentNode !== world/);
    assert.match(source, /<g data-sheet-group="\$\{esc\(key\)\}">/);
}

// DOM simulation: nested data-sheet-group must not double-translate the frame.
{
    const world = makeNode({ class: "abe-world" }, []);
    const hostGroup = makeNode({ "data-sheet-group": "1" }, [], world);
    const frame = makeNode({ "data-sheet": "1", class: "abe-sheet" }, [], hostGroup);
    const piece = makeNode({ "data-piece-key": "instance:a" }, [], hostGroup);
    hostGroup.children = [frame, piece];
    world.children = [hostGroup];

    // Legacy bug fixture: frame also carries data-sheet-group.
    const legacyFrame = makeNode(
        { "data-sheet": "1", "data-sheet-group": "1", class: "abe-sheet" },
        [],
        hostGroup
    );
    const legacyWorld = makeNode({ class: "abe-world" }, []);
    const legacyHost = makeNode({ "data-sheet-group": "1" }, [legacyFrame, piece], legacyWorld);
    legacyFrame.parentNode = legacyHost;
    piece.parentNode = legacyHost;
    legacyWorld.children = [legacyHost];
    legacyHost.parentNode = legacyWorld;

    const host = {
        querySelector(sel) {
            if (sel === ".abe-world") return world;
            return null;
        },
    };

    CanvasRenderer.patchDragPreview(host, {
        kind: "board",
        sheetNo: 1,
        dx: 120,
        dy: 50,
        valid: true,
    });

    assert.equal(hostGroup.getAttribute("transform"), "translate(120,50)");
    assert.equal(hostGroup.getAttribute("data-abe-drag-shift"), "1");
    // Frame/piece inherit visually; they must not get their own translate.
    assert.equal(frame.getAttribute("transform"), null);
    assert.equal(piece.getAttribute("transform"), null);

    // Defense: even with a nested data-sheet-group frame, only the world child shifts.
    const legacyHostEl = {
        querySelector(sel) {
            if (sel === ".abe-world") return legacyWorld;
            return null;
        },
    };
    CanvasRenderer.patchDragPreview(legacyHostEl, {
        kind: "board",
        sheetNo: 1,
        dx: 80,
        dy: 20,
        valid: true,
    });
    assert.equal(legacyHost.getAttribute("transform"), "translate(80,20)");
    assert.equal(legacyFrame.getAttribute("transform"), null);
}

// Rendered markup: sheet frame has data-sheet, outer group has data-sheet-group once.
{
    const projection = {
        board: { kerf_cm: 0.4 },
        layers: [{ match_key: "GEOMETRY", original_name: "GEOMETRY", aci_color: 7 }],
        sheets: [{
            sheet_no: 1,
            full_width_cm: 100,
            full_length_cm: 100,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
            usable_width_cm: 100,
            usable_length_cm: 100,
        }],
        pieces: [{
            piece_id: 1,
            piece_instance_id: "pi-a",
            label: "A",
            sheet_no: 1,
            placement_cm: { x: 10, y: 10, w: 20, h: 15 },
        }],
        elements: [
            {
                element_id: "sheet:1",
                kind: "sheet_outline",
                sheet_no: 1,
                layer_match_key: "SHEET",
                payload: {
                    full_width_cm: 100,
                    full_length_cm: 100,
                    usable_width_cm: 100,
                    usable_length_cm: 100,
                    applied_trim_width_cm: 0,
                    applied_trim_length_cm: 0,
                },
            },
            {
                element_id: "p1",
                kind: "placement_rect",
                sheet_no: 1,
                piece_id: 1,
                piece_instance_id: "pi-a",
                layer_match_key: "GEOMETRY",
                payload: {
                    placement_cm: { x: 10, y: 10, w: 20, h: 15 },
                    fill_role: "regular",
                },
            },
        ],
    };
    const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
    const session = SessionDocument.buildFromProjection(projection, layout);
    const history = History.create(session);
    const store = createStore({ projection, order_name: "O", plan_name: "P" });
    store.attachSession(history.get(), history);
    store.setViewport({
        scale: 0.25,
        opened: true,
        userAdjusted: true,
        columns: 1,
        scrollX: 0,
        scrollY: 0,
        fitted: false,
        cameraToken: 1,
    });

    const stage = {
        clientWidth: 900,
        clientHeight: 600,
        scrollLeft: 0,
        scrollTop: 0,
        classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
        style: {},
        addEventListener() {},
        querySelector() { return null; },
        setPointerCapture() {},
        releasePointerCapture() {},
        getBoundingClientRect() {
            return { left: 0, top: 0, width: 900, height: 600, right: 900, bottom: 600 };
        },
    };
    const host = {
        clientWidth: 900,
        clientHeight: 640,
        style: {},
        __html: "",
        set innerHTML(value) { this.__html = String(value); },
        get innerHTML() { return this.__html; },
        querySelector(sel) {
            if (sel === "[data-abe-stage]") return stage;
            return {
                addEventListener() {},
                querySelector() { return null; },
                querySelectorAll() { return []; },
                onclick: null,
                classList: { add() {}, remove() {}, contains() { return false; } },
                style: {},
                getBoundingClientRect() {
                    return { left: 0, top: 0, width: 800, height: 600, right: 800, bottom: 600 };
                },
            };
        },
        querySelectorAll() { return []; },
    };

    CanvasRenderer.render(host, store.snapshot(), {});
    const html = host.innerHTML;
    assert.match(html, /data-sheet-group="1"/);
    assert.match(html, /data-sheet="1"/);
    assert.match(html, /class="abe-sheet/);
    // Frame must not repeat data-sheet-group next to abe-sheet.
    assert.doesNotMatch(html, /data-sheet-group="1"[^>]*class="abe-sheet/);
    assert.doesNotMatch(html, /class="abe-sheet[^"]*"[^>]*data-sheet-group=/);

    const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
    assert.match(page, /canvas_renderer\.js\?v=43/);
    assert.match(page, /move_interaction\.js\?v=29/);
}

console.log("board_editor_board_drag_preview.test.js: ok");
