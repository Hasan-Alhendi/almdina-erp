"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const domainDir = path.resolve(__dirname, "../../public/js/door_drawing_v2/domain");
const files = fs.readdirSync(domainDir).filter(name => name.endsWith(".js"));
assert.ok(files.length >= 3, "Door Drawing V2 domain modules must exist");

files.forEach(name => {
    const source = fs.readFileSync(path.join(domainDir, name), "utf8");
    assert.doesNotMatch(source, /\bpixels?\b/i, `${name} must not define manufacturing geometry in pixels`);
    assert.doesNotMatch(source, /\bpx\b/i, `${name} must not depend on CSS pixel units`);
    assert.doesNotMatch(source, /DEFAULT_CANVAS|canvasToCm|cmToCanvas/, `${name} must remain independent from the renderer/viewport`);
});

console.log("Door Drawing V2 domain separation contract passed");
