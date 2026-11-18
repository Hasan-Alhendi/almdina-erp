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

class FakeElement {
    constructor(className) {
        this.className = className || "";
        this.children = [];
        this.parent = null;
        this.style = {
            width: "",
            height: "",
            setProperty() {},
            removeProperty() {},
        };
        this.dataset = {};
        this.clientWidth = 0;
        this.clientHeight = 0;
    }

    get nextElementSibling() {
        if (!this.parent) return null;
        const index = this.parent.children.indexOf(this);
        return index >= 0 ? this.parent.children[index + 1] || null : null;
    }

    appendChild(child) {
        this.insertBefore(child, null);
        return child;
    }

    insertBefore(child, anchor) {
        if (child.parent) {
            const siblings = child.parent.children;
            const index = siblings.indexOf(child);
            if (index >= 0) siblings.splice(index, 1);
        }
        child.parent = this;
        const at = anchor ? this.children.indexOf(anchor) : -1;
        if (at < 0) this.children.push(child);
        else this.children.splice(at, 0, child);
        return child;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] || null;
    }

    querySelectorAll(selector) {
        const className = selector.replace(/^:scope > \./, "").replace(/^\./, "");
        const directOnly = selector.startsWith(":scope >");
        const found = [];
        const visit = (node, direct) => {
            node.children.forEach(child => {
                if ((!directOnly || direct) && child.className.split(/\s+/).includes(className)) {
                    found.push(child);
                }
                if (!directOnly) visit(child, false);
            });
        };
        visit(this, true);
        return found;
    }
}

function childClasses(node) {
    return node.children.map(child => child.className);
}

document.createElement = () => new FakeElement("");

const belowPlan = new FakeElement("dco-cutting-plan");
belowPlan.clientWidth = 900;
belowPlan.appendChild(new FakeElement("dco-margin-policy-alert"));
belowPlan.appendChild(new FakeElement("dco-sheet-card"));
belowPlan.appendChild(new FakeElement("dco-sheet-card"));
belowPlan.appendChild(new FakeElement("dco-unplaced-pieces-warning"));
presenter.layoutBoardGallery(belowPlan);
assert.deepEqual(childClasses(belowPlan), [
    "dco-margin-policy-alert",
    "dco-unplaced-pieces-warning",
    "dco-board-gallery",
]);
assert.equal(belowPlan.children[2].children.length, 2);
presenter.layoutBoardGallery(belowPlan);
assert.deepEqual(childClasses(belowPlan), [
    "dco-margin-policy-alert",
    "dco-unplaced-pieces-warning",
    "dco-board-gallery",
]);
assert.equal(belowPlan.querySelectorAll(".dco-unplaced-pieces-warning").length, 1);

const abovePlan = new FakeElement("dco-cutting-plan");
abovePlan.clientWidth = 900;
abovePlan.appendChild(new FakeElement("dco-unplaced-pieces-warning"));
abovePlan.appendChild(new FakeElement("dco-margin-policy-alert"));
abovePlan.appendChild(new FakeElement("dco-sheet-card"));
presenter.layoutBoardGallery(abovePlan);
assert.deepEqual(childClasses(abovePlan), [
    "dco-margin-policy-alert",
    "dco-unplaced-pieces-warning",
    "dco-board-gallery",
]);

const placedPlan = new FakeElement("dco-cutting-plan");
placedPlan.clientWidth = 900;
placedPlan.appendChild(new FakeElement("dco-sheet-card"));
presenter.layoutBoardGallery(placedPlan);
assert.deepEqual(childClasses(placedPlan), ["dco-board-gallery"]);

console.log("Cutting plan board presenter policy checks passed");
