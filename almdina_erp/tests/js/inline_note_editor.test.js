"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

class FakeElement {
    constructor(tagName) {
        this.tagName = String(tagName || "div").toUpperCase();
        this.style = {};
        this.attributes = {};
        this.children = [];
        this.listeners = new Map();
        this.textContent = "";
        this.parentNode = null;
        this.removed = false;
        this.focused = false;
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    addEventListener(name, callback) {
        this.listeners.set(name, callback);
    }

    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
    }

    remove() {
        this.removed = true;
        if (!this.parentNode) return;
        this.parentNode.children = this.parentNode.children.filter(child => child !== this);
        this.parentNode = null;
    }

    focus() {
        this.focused = true;
    }

    dispatch(name, values = {}) {
        const listener = this.listeners.get(name);
        if (!listener) return;
        listener({
            preventDefault() {},
            ...values,
        });
    }
}

const range = {
    selectNodeContents() {},
    collapse() {},
    deleteContents() {},
    insertNode() {},
    setStartAfter() {},
};
const selection = {
    rangeCount: 1,
    getRangeAt() {
        return range;
    },
    removeAllRanges() {},
    addRange() {},
};
const documentHead = new FakeElement("head");

global.window = {
    requestAnimationFrame(callback) {
        callback();
        return 1;
    },
    setTimeout,
    getSelection() {
        return selection;
    },
};
global.document = {
    head: documentHead,
    getElementById(id) {
        return documentHead.children.find(child => child.id === id) || null;
    },
    createElement(tagName) {
        return new FakeElement(tagName);
    },
    createTextNode(text) {
        return { textContent: String(text) };
    },
    createRange() {
        return range;
    },
};

require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_inline_note_editor.js"
));

const inlineEditor = window.AlmdinaInlineNoteEditor;
assert.ok(Object.isFrozen(inlineEditor), "The inline note API should be immutable");
assert.equal(inlineEditor.clampFontSize("bad"), 18);
assert.equal(inlineEditor.clampFontSize(50), 32);
assert.match(inlineEditor.controlsHtml(), /dco-note-font-size/);
inlineEditor.installStyles();
inlineEditor.installStyles();
assert.equal(documentHead.children.length, 1, "Inline note styles should be installed once");

const wrap = new FakeElement("div");
wrap.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1100, height: 750 });
wrap.querySelectorAll = selector => selector === ".dco-canvas-text-editor"
    ? wrap.children.filter(child => child.className === "dco-canvas-text-editor")
    : [];
const root = {
    querySelector(selector) {
        return selector === ".dco-sketch-paper-wrap" ? wrap : null;
    },
};
const svg = {
    clientWidth: 1000,
    viewBox: { baseVal: { x: 0, y: 0, width: 1000, height: 650 } },
    getScreenCTM() {
        return null;
    },
    getBoundingClientRect() {
        return { left: 10, top: 20, width: 1000, height: 650 };
    },
};

let committed = "";
let closed = 0;
const editor = inlineEditor.open({
    root,
    svg,
    point: { x: 320, y: 240 },
    text: "ملاحظة أولية",
    fontSize: 24,
    color: "#1769aa",
    onCommit(value) {
        committed = value;
    },
    onClose() {
        closed += 1;
    },
});

assert.equal(editor.style.left, "330px", "The editor should open at the clicked canvas X");
assert.equal(editor.style.top, "260px", "The editor should open at the clicked canvas Y");
assert.equal(editor.style.fontSize, "24px");
assert.equal(editor.style.color, "#1769aa");
assert.equal(editor.attributes["aria-label"], "اكتب الملاحظة مباشرة على الرسم");
assert.equal(editor.focused, true, "The inline note should receive focus immediately");

editor.textContent = "قص مائل";
editor.dispatch("keydown", { key: "Enter" });
assert.equal(committed, "قص مائل");
assert.equal(closed, 1);
assert.equal(editor.removed, true);

let cancelledCommit = false;
const cancelled = inlineEditor.open({
    root,
    svg,
    point: { x: 100, y: 100 },
    onCommit() {
        cancelledCommit = true;
    },
});
cancelled.textContent = "لا تحفظ";
cancelled.dispatch("keydown", { key: "Escape" });
assert.equal(cancelledCommit, false, "Escape should cancel the note");

console.log("Inline note point placement, formatting, commit, and cancel simulation passed");
