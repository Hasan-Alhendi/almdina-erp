"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/factory_production_settings/view_model.js"),
    "utf8"
);

const fakeWindow = {};
const context = vm.createContext({ window: fakeWindow, Object, Array, Boolean, Number, String });
vm.runInContext(source, context);

const moduleApi = fakeWindow.AlmdinaFactoryProductionSettingsViewModel;
assert.ok(moduleApi && typeof moduleApi.create === "function");
const model = moduleApi.create({ translate: value => value });

const current = {
    values: {
        default_kerf_mm: 5,
        default_trim_margin_mm: 5,
        default_packing_mode: "Auto",
        default_cutting_machine_type: "Panel Saw",
        default_optimization_time_limit_sec: 10,
        optimal_search_piece_limit: 20,
        default_cutting_cost_per_board_usd: 3,
        default_special_design_fee_usd: 1,
        default_special_cnc_fee_usd: 2,
        default_special_manual_edge_fee_usd: 4,
        default_special_margin_percent: 10,
        default_production_routing: "Drawing",
        allow_stage_override: 0,
        allow_unplaced_approval: 1,
        print_factory_name: "Almdina",
        print_factory_description: "Factory",
        print_factory_address: "Address",
        print_factory_contacts: "111\n222",
    },
    permissions: {
        sections: {
            cutting: { editable: true },
            costing: { editable: false },
            production: { editable: true },
            print_identity: { editable: false },
        },
    },
    legacy_values: {
        enforce_stock_control: 1,
        default_warehouse: "Old WH",
        reserve_stock_on_approval: 0,
        stock_consumption_point: "Approval",
        prefer_remnants_before_full_boards: 1,
        min_remnant_width_mm: 100,
        min_remnant_length_mm: 200,
        min_remnant_area_m2: 0.1,
        remnant_cost_policy: "Fixed",
        remnant_rate_usd_per_m2: 5,
    },
};

assert.equal(model.sectionEditable(current, "cutting"), true);
assert.equal(model.sectionEditable(current, "costing"), false);
assert.equal(model.sectionEditable(current, "missing"), false);
assert.equal(model.yesNo(1), "نعم");
assert.equal(model.yesNo(0), "لا");
assert.equal(model.display(null), "—");
assert.equal(model.values(current).default_kerf_mm, 5);

const sections = model.sections(current);
assert.equal(sections.length, 4);
assert.deepEqual(
    JSON.parse(JSON.stringify(sections.map(section => [section.key, section.editable]))),
    [
        ["cutting", true],
        ["costing", false],
        ["production", true],
        ["print_identity", false],
    ]
);
assert.equal(sections[0].rows[0].value, 5);
assert.equal(sections[1].rows[0].value, "3 USD");
assert.equal(sections[2].rows[1].value, "غير مسموح");
assert.equal(sections[2].rows[2].value, "مسموح");
assert.equal(sections[3].rows[3].multiline, true);

const legacy = model.legacy(current);
assert.equal(legacy.length, 10);
assert.equal(legacy[0].value, "نعم");
assert.equal(legacy[1].value, "Old WH");
assert.equal(legacy[9].value, "5 USD");

const page = model.page(current);
assert.equal(page.hasLegacy, true);
assert.equal(page.sections.length, 4);
assert.equal(page.legacy.length, 10);

const noLegacy = model.page({ values: {}, permissions: { sections: {} } });
assert.equal(noLegacy.hasLegacy, false);
assert.equal(noLegacy.legacy.length, 10, "legacy rows retain historical field labels even when values are absent");

console.log("Factory production settings view-model simulation passed");
