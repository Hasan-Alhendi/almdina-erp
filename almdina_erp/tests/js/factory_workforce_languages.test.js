"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function load(relativePath, context) {
    const source = fs.readFileSync(path.resolve(__dirname, relativePath), "utf8");
    vm.runInContext(source, context, { filename: relativePath });
}

const languages = [
    { code: "ar", name: "العربية", direction: "rtl" },
    { code: "en", name: "English", direction: "ltr" },
    { code: "fr", name: "Français", direction: "ltr" },
];

const viewWindow = {};
load("../../public/js/factory_workforce/view_model.js", vm.createContext({
    window: viewWindow,
    Object,
    Array,
    Boolean,
    Number,
    String,
    Set,
}));
const viewModel = viewWindow.AlmdinaFactoryWorkforceViewModel.create({ translate: value => value });
const user = {
    email: "worker@example.com",
    full_name: "Worker",
    enabled: 1,
    language: "fr",
    roles: [],
    actions: { edit: { allowed: true } },
};
const labeled = viewModel.userModel(user, { languages, permissions: {} });
assert.equal(labeled.languageLabel, "Français");
assert.equal(viewModel.languageName("ar", languages), "العربية");
assert.notEqual(labeled.languageLabel, "العربية");

class FakeDialog {
    constructor(config) {
        this.config = config;
        this.hidden = 0;
    }
    show() {}
    hide() { this.hidden += 1; }
    get_values() { return {}; }
    set_values() {}
}

const dialogWindow = { frappe: { ui: { Dialog: FakeDialog } } };
load("../../public/js/factory_workforce/dialogs.js", vm.createContext({
    window: dialogWindow,
    frappe: dialogWindow.frappe,
    Object,
    Array,
    Set,
    String,
    Error,
    Promise,
}));
const dialogs = dialogWindow.AlmdinaFactoryWorkforceDialogs.create({ translate: value => value });
const created = dialogs.openCreate({ languages, canAssignRoles: false, roleOptions: () => [] });
const createLanguage = created.config.fields.find(field => field.fieldname === "language");
assert.deepEqual(JSON.parse(JSON.stringify(createLanguage.options.map(option => option.value))), ["ar", "en", "fr"]);
assert.deepEqual(JSON.parse(JSON.stringify(createLanguage.options.map(option => option.label))), ["العربية", "English", "Français"]);
assert.equal(createLanguage.default, "ar");

const edited = dialogs.openEdit({
    languages,
    user: { email: "worker@example.com", first_name: "Worker", language: "fr", roles: [] },
    canEdit: true,
    canAssignRoles: false,
    roleOptions: () => [],
});
const editLanguage = edited.config.fields.find(field => field.fieldname === "language");
assert.equal(editLanguage.default, "fr");
assert.equal(editLanguage.options.find(option => option.value === "fr").label, "Français");

console.log("Factory workforce language catalog simulation passed");
