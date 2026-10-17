"use strict";

// Instrument the private rendering helpers inside a VM; do not expose a new
// production global just to test physical edge-banding orientation.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const rendererPath = path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_cutting_plan_renderer.js"
);
const source = fs.readFileSync(rendererPath, "utf8");
const marker = "    window.AlmdinaCuttingPlanRender = {";
assert.ok(source.includes(marker));
const instrumented = source.replace(marker, `
    window.__physicalEdgeFlags = piece_edge_flags;
    window.__physicalDxfOverlays = render_piece_overlays;
${marker}`);

const fakeWindow = {
    AlmdinaMachiningOverlay: {
        visualOverlays: () => [
            {
                kind: "liner",
                layer: "Liner",
                geometry: { path: [[999, 999], [999, 1200]], closed: false },
            },
        ],
    },
};
const context = vm.createContext({window: fakeWindow, console, Math, Number, JSON, Object, Array, Set});
vm.runInContext(instrumented, context, { filename: "cutting_plan_renderer.js" });
const edge = fakeWindow.__physicalEdgeFlags;
const physical = { edge_long_right: 1, edge_long_left: 0, edge_width_top: 0, edge_width_bottom: 0 };
for (const [turns, side] of [[0, "right"], [1, "bottom"], [2, "left"], [3, "top"]]) {
    const piece = { ...physical, rotated: turns % 2 === 1, rotation_quarter_turns: turns };
    const flags = edge(piece, { source: "dxf" });
    for (const key of ["left", "top", "right", "bottom"]) {
        assert.equal(flags[key], key === side ? 1 : 0, `turn ${turns}, side ${key}`);
    }
}
// System plans with historical bbox-only orientation remain unchanged.
const old = edge({ ...physical, rotated: true }, { source: "system" });
assert.equal(old.bottom, 1);
assert.equal(old.right, 0);

// The source DXF path must be displayed, never a regenerated order-side path.
const overlays = fakeWindow.__physicalDxfOverlays(
    { doc: { pieces: [] } },
    {
        source_piece_no: 1,
        overlays: [{
            kind: "liner", layer: "Liner",
            geometry: { path: [[10, 10], [20, 10], [20, 30], [10, 30]], closed: true },
        }],
    },
    { source: "dxf", placement: { xCm: 0, yCm: 0, widthCm: 54.9, heightCm: 100 } },
    null,
    null
);
assert.match(overlays, /data-overlay-kind="liner"/);
assert.doesNotMatch(overlays, /999/);
assert.match(overlays, /dco-extra-overlay/);
console.log("DXF physical edge-banding and persisted machining render tests passed");
