"use strict";

/**
 * Behavioral contract: Frappe 16.60 desk rail background token must map to
 * Almdina brand navy so forced on-primary ink stays readable.
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "../..");
const THEME = fs.readFileSync(path.join(ROOT, "public/css/almdina_desk_theme.css"), "utf8");
const SIDEBAR = fs.readFileSync(path.join(ROOT, "public/css/almdina_desk_sidebar.css"), "utf8");
const ASSETS = fs.readFileSync(path.join(ROOT, "frontend_assets.py"), "utf8");

// Optional live check against the local Frappe 16.60 checkout when present.
const FRAPPE_SIDEBAR = path.resolve(
    ROOT,
    "../../../frappe/frappe/public/scss/desk/sidebar.scss"
);
if (fs.existsSync(FRAPPE_SIDEBAR)) {
    const frappeSidebar = fs.readFileSync(FRAPPE_SIDEBAR, "utf8");
    assert.match(
        frappeSidebar,
        /--desk-sidebar-bg:\s*var\(--surface-sidebar\)/,
        "Frappe 16.60 still owns --desk-sidebar-bg from --surface-sidebar"
    );
    assert.match(
        frappeSidebar,
        /background:\s*var\(--desk-sidebar-bg\)/,
        "Frappe paints .body-sidebar with --desk-sidebar-bg"
    );
}

function blockFor(selectorPrefix) {
    const marker = `${selectorPrefix} {`;
    const start = THEME.indexOf(marker);
    assert.ok(start >= 0, `missing block ${selectorPrefix}`);
    const end = THEME.indexOf("\n}", start);
    assert.ok(end > start, `unclosed block ${selectorPrefix}`);
    return THEME.slice(start, end + 2);
}

const light = blockFor(":root,\n[data-theme=\"light\"]");
const dark = blockFor("[data-theme=\"dark\"]");

for (const [name, block] of [["light", light], ["dark", dark]]) {
    assert.match(block, /--desk-sidebar-bg:\s*var\(--alm-primary\)/, `${name} maps desk sidebar bg`);
    assert.doesNotMatch(block, /--dock-bg:/, `${name} uses Frappe's dock-to-sidebar bridge`);
    assert.match(block, /--dock-ink-active:\s*var\(--alm-on-primary/, `${name} maps dock active ink`);
    assert.match(block, /--sidebar-hover-color:\s*color-mix\(in srgb, var\(--alm-on-primary\) 12%, var\(--alm-primary\)\)/);
    assert.match(block, /--sidebar-active-color:\s*var\(--alm-accent/);
}

assert.match(
    THEME,
    /\.body-sidebar[\s\S]*color:\s*var\(--alm-on-primary/,
    "sidebar text remains on-primary white"
);
assert.match(
    SIDEBAR,
    /\.shell-header/,
    "collapsed polish covers Frappe 16.60 shell-header"
);
assert.match(SIDEBAR, /\.standard-sidebar-item:not\(\.active-sidebar\):has\(a:not\(\.section-break\)\):hover\s*\{\s*background-color:\s*var\(--sidebar-hover-color\)/);
assert.match(SIDEBAR, /\.body-sidebar \.active-sidebar,[\s\S]*background-color:\s*var\(--sidebar-active-color\)/);
assert.match(SIDEBAR, /\.dock \.dock-item:hover,[\s\S]*background-color:\s*var\(--sidebar-hover-color\)/);
assert.match(SIDEBAR, /\.dock \.dock-item.active,[\s\S]*background-color:\s*var\(--sidebar-active-color\)/);
assert.match(SIDEBAR, /\.item-anchor:not\(\.section-break\):hover,[\s\S]*color:\s*var\(--alm-on-primary/);

function contrastOnWhite(hex) {
    const channels = hex.match(/[\da-f]{2}/gi).map(value => parseInt(value, 16) / 255);
    const linear = channels.map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    const luminance = linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
    return 1.05 / (luminance + 0.05);
}
assert.ok(contrastOnWhite("2563eb") >= 4.5, "active blue remains legible with white labels");
assert.match(
    ASSETS,
    /almdina_desk_theme\.css\?v=4/,
    "theme cache-buster bumped so browsers load the bridge"
);
assert.match(
    ASSETS,
    /almdina_desk_sidebar\.css\?v=4/,
    "sidebar CSS cache-buster bumped"
);

console.log("desk sidebar token bridge tests passed");
