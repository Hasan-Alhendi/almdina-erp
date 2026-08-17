"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
const listeners = new Map();

global.document = { body: { tagName: "BODY" } };
global.window = {
    AlmdinaDoorDrawingProfessional: Object.create(null),
    addEventListener(type, handler) { listeners.set(type, handler); },
    removeEventListener(type, handler) { if (listeners.get(type) === handler) listeners.delete(type); },
};

require(path.join(root, "public/js/door_drawing_v4/professional/keyboard_controller.js"));
const keyboard = global.window.AlmdinaDoorDrawingProfessional.KeyboardController;
assert.ok(keyboard, "professional keyboard controller must register");

const scope = {
    isConnected: true,
    getClientRects() { return [{ width: 100, height: 100 }]; },
};
const calls = [];
const mounted = keyboard.mount(scope, {
    tool(tool, key) { calls.push(["tool", tool, key]); },
    undo() { calls.push(["undo"]); },
    redo() { calls.push(["redo"]); },
    escape() { calls.push(["escape"]); },
    spaceDown() { calls.push(["space-down"]); },
    spaceUp() { calls.push(["space-up"]); },
});

function keydown(key, options = {}) {
    let prevented = false;
    listeners.get("keydown")({
        key,
        code: options.code || (key === " " ? "Space" : `Key${String(key).toUpperCase()}`),
        target: options.target || { tagName: "DIV", isContentEditable: false },
        ctrlKey: Boolean(options.ctrlKey),
        metaKey: Boolean(options.metaKey),
        shiftKey: Boolean(options.shiftKey),
        altKey: Boolean(options.altKey),
        isComposing: false,
        repeat: Boolean(options.repeat),
        preventDefault() { prevented = true; },
    });
    return prevented;
}
function keyup(key, options = {}) {
    listeners.get("keyup")({
        key,
        code: options.code || (key === " " ? "Space" : `Key${String(key).toUpperCase()}`),
        preventDefault() {},
    });
}

for (const [key, expected] of [["v", "select"], ["a", "node"], ["p", "pen"], ["d", "dimension"]]) {
    assert.equal(keydown(key), true, `${key.toUpperCase()} must be owned by the visible drawing workspace`);
    assert.deepEqual(calls.at(-1), ["tool", expected, key]);
}
assert.equal(keydown("p", { code: "KeyP", shiftKey: true }), true, "Shift+P must activate the separate smart pencil");
assert.deepEqual(calls.at(-1), ["tool", "smart-pencil", "shift+p"]);

// event.code identifies the physical key even when Windows/browser input language is Arabic.
// The actual event.key can therefore be Arabic and the design shortcuts must still work.
for (const [key, code, expected, label] of [
    ["ر", "KeyV", "select", "v"],
    ["ش", "KeyA", "node", "a"],
    ["ح", "KeyP", "pen", "p"],
    ["ي", "KeyD", "dimension", "d"],
]) {
    assert.equal(keydown(key, { code }), true, `${code} must work regardless of Arabic keyboard layout`);
    assert.deepEqual(calls.at(-1), ["tool", expected, label]);
}
assert.equal(keydown("ح", { code: "KeyP", shiftKey: true }), true, "Shift+P must work on Arabic keyboard layout too");
assert.deepEqual(calls.at(-1), ["tool", "smart-pencil", "shift+p"]);

keydown("z", { ctrlKey: true, code: "KeyZ" });
assert.deepEqual(calls.at(-1), ["undo"]);
keydown("ئ", { ctrlKey: true, code: "KeyZ" });
assert.deepEqual(calls.at(-1), ["undo"], "Ctrl+Z must use the physical key on Arabic layout too");
keydown("z", { ctrlKey: true, shiftKey: true, code: "KeyZ" });
assert.deepEqual(calls.at(-1), ["redo"]);
keydown("Escape");
assert.deepEqual(calls.at(-1), ["escape"]);
keydown(" ", { code: "Space" });
assert.deepEqual(calls.at(-1), ["space-down"]);
keyup(" ", { code: "Space" });
assert.deepEqual(calls.at(-1), ["space-up"]);

const countBeforeInput = calls.length;
const textInput = { tagName: "INPUT", type: "text", isContentEditable: false };
assert.equal(keydown("p", { code: "KeyP", target: textInput }), false, "typing in an input must not switch tools");
assert.equal(calls.length, countBeforeInput);
const contentEditable = { tagName: "DIV", isContentEditable: true };
assert.equal(keydown("a", { code: "KeyA", target: contentEditable }), false, "contenteditable typing must not switch tools");
assert.equal(calls.length, countBeforeInput);

scope.isConnected = false;
assert.equal(keydown("v", { code: "KeyV" }), false, "hidden/unmounted workspace must not capture shortcuts");
assert.equal(calls.length, countBeforeInput);
scope.isConnected = true;

mounted.destroy();
assert.equal(listeners.has("keydown"), false);
assert.equal(listeners.has("keyup"), false);

console.log("Professional drawing keyboard behavior passed, including Arabic layout and Smart Pencil");
