"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/factory_workforce/view_model.js"),
    "utf8"
);

const fakeWindow = {};
const context = vm.createContext({
    window: fakeWindow,
    Object,
    Array,
    Boolean,
    Number,
    String,
});
vm.runInContext(source, context);

const moduleApi = fakeWindow.AlmdinaFactoryWorkforceViewModel;
assert.ok(moduleApi && typeof moduleApi.create === "function");
const model = moduleApi.create({ translate: value => value });

const roles = [
    { name: "Drawing", desk_access: 1, home_page: "/desk/door-cutting-order" },
    { name: "CNC", desk_access: 0, home_page: "" },
    { name: "Sanding", desk_access: 1, home_page: "/desk/shop-floor-inbox" },
];
assert.deepEqual(
    JSON.parse(JSON.stringify(model.roleOptions(roles, "cn"))),
    [{ value: "CNC", description: "دور بدون Desk · صفحة الدخول غير محددة" }]
);
assert.deepEqual(
    JSON.parse(JSON.stringify(model.roleOptions(roles, "draw"))),
    [{ value: "Drawing", description: "وصول Desk · صفحة الدخول: /desk/door-cutting-order" }]
);
assert.equal(model.roleHomePolicy(roles, ["Drawing"]).hasConflict, false);
assert.equal(model.roleHomePolicy(roles, ["Drawing", "Sanding"]).hasConflict, true);

const user = {
    email: "worker@example.com",
    full_name: "Worker",
    enabled: 1,
    language: "ar",
    default_workspace: "Almdina",
    last_active: "2026-08-16",
    active_assignments: 2,
    roles: ["Drawing"],
    actions: {
        edit: { allowed: true },
        assign_roles: { allowed: false },
        reset_password: { allowed: true },
        disable: { allowed: true },
        enable: { allowed: false },
    },
};
const data = {
    users: [user],
    availableUsers: [],
    roles,
    permissions: {
        create_users: true,
        assign_user_roles: true,
        disable_users: true,
    },
    summary: {
        total: 1,
        enabled: 1,
        disabled: 0,
        active_assignments: 2,
    },
    search: "worker",
    enabled: "1",
};

assert.equal(model.can(data, "create_users"), true);
assert.equal(model.can(data, "missing"), false);
assert.equal(model.actionAllowed(user, "edit"), true);
assert.equal(model.actionAllowed(user, "assign_roles"), false);
assert.equal(model.actionAllowed({}, "edit"), false);
assert.equal(model.findUser(data.users, "worker@example.com"), user);
assert.equal(model.findUser(data.users, "missing@example.com"), null);

const userModel = model.userModel(user, data);
assert.equal(userModel.canEdit, true);
assert.equal(userModel.canResetPassword, true);
assert.equal(userModel.canDisable, true);
assert.equal(userModel.canEnable, false);
assert.equal(userModel.showActiveAssignmentWarning, true);
assert.equal(userModel.activeAssignments, 2);
assert.deepEqual(JSON.parse(JSON.stringify(userModel.roles)), ["Drawing"]);

const summary = model.summaryCards(data.summary);
assert.equal(summary.length, 4);
assert.equal(summary[0].value, 1);
assert.equal(summary[3].value, 2);

const available = model.availableUserModel({
    email: "outside@example.com",
    full_name: "Outside",
    enabled: 0,
    default_app: "",
    default_workspace: "",
    last_active: "",
});
assert.equal(available.source, "بدون تطبيق افتراضي");
assert.equal(available.enabled, false);
assert.equal(available.defaultWorkspace, "—");

const page = model.page(data);
assert.equal(page.canCreateUsers, true);
assert.equal(page.canAssignRoles, true);
assert.equal(page.search, "worker");
assert.equal(page.enabled, "1");
assert.equal(page.users.length, 1);
assert.equal(page.availableUsers.length, 0);

const deniedPage = model.page({ ...data, permissions: {} });
assert.equal(deniedPage.canCreateUsers, false);
assert.equal(deniedPage.canAssignRoles, false);

console.log("Factory workforce view-model simulation passed");
