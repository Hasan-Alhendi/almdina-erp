"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = { innerWidth: 1400, innerHeight: 900 };
global.document = {};

require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_board_presenter.js"
));

const presenter = window.AlmdinaPlanBoardPresenter;
assert.ok(presenter, "Plan board presenter must be installed");
assert.equal(Object.isFrozen(presenter), true, "Presenter API must be immutable");

window.innerWidth = 500;
assert.equal(presenter.desiredBoardColumns(1300), 1, "Mobile viewport stays one-column");

window.innerWidth = 800;
assert.equal(presenter.desiredBoardColumns(800), 2, "Tablet viewport stays two-column");

window.innerWidth = 1400;
assert.equal(presenter.desiredBoardColumns(500), 1, "Narrow plan root stays one-column");
assert.equal(presenter.desiredBoardColumns(600), 2, "Medium plan root uses two columns");
assert.equal(presenter.desiredBoardColumns(800), 3, "Wide plan root uses three columns");
assert.equal(presenter.desiredBoardColumns(1200), 4, "Very wide plan root uses four columns");

console.log("Cutting plan board presenter policy checks passed");
