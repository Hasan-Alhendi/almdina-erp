"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const localeSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/almdina_locale.js"),
    "utf8"
);
const switcherSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/almdina_language_switcher.js"),
    "utf8"
);
const assetsSource = fs.readFileSync(
    path.resolve(__dirname, "../../frontend_assets.py"),
    "utf8"
);

const METHOD = "almdina_erp.almdina_erp.services.user_language_service.set_current_user_language";
const EVENT = "sidebar_setup.almdinaLanguageSwitcher";
const DIRTY_MESSAGE =
    "You have unsaved changes. Do you want to discard them and refresh the page?";

function menuFixture() {
    return [
        { name: "desktop", label: "Desktop", icon: "home" },
        { name: "display", label: "Display", icon: "monitor", items: [] },
        { label: "Reload", action: "frappe.ui.toolbar.clear_cache()", icon: "rotate-ccw" },
        { name: "help", label: "Help", icon: "info" },
        { name: "logout", label: "Logout", icon: "logout" },
    ];
}

function languageItem(items) {
    return items.find((item) => item && item.name === "almdina-language");
}

function load(options) {
    const settings = options || {};
    const handlers = {};
    const calls = [];
    const notices = [];
    const confirms = [];
    const reloads = [];
    const items = menuFixture();
    const sidebar = {};
    if (settings.headerReady) sidebar.sidebar_header = { dropdown_items: items };
    const fakeWindow = {
        frappe: {
            boot: {
                lang: settings.lang || "ar",
                almdina_ui_languages: settings.languages || [],
            },
            session: { user: settings.user || "user@example.com" },
            app: { sidebar: sidebar },
            call(opts) {
                calls.push(opts);
                if (settings.invokeCall === "success" && opts.callback) {
                    opts.callback({ message: { language: opts.args.language } });
                }
                if (settings.invokeCall === "error" && opts.error) opts.error();
            },
            unfreeze() {},
            msgprint(notice) {
                notices.push(notice);
            },
            confirm(message, onYes, onNo) {
                confirms.push({ message, onYes, onNo });
                if (settings.confirmChoice === "yes" && typeof onYes === "function") onYes();
                if (settings.confirmChoice === "no" && typeof onNo === "function") onNo();
            },
        },
        jQuery() {
            return {
                off(event) {
                    delete handlers[event];
                    return this;
                },
                on(event, fn) {
                    handlers[event] = fn;
                    return this;
                },
            };
        },
        __: (message) => message,
        location: {
            reload() {
                reloads.push(1);
            },
        },
        document: {},
        cur_frm: settings.cur_frm || null,
        queueMicrotask,
        Promise,
        Object,
        String,
        Array,
    };
    fakeWindow.window = fakeWindow;
    const context = vm.createContext(fakeWindow);
    vm.runInContext(localeSource, context, { filename: "almdina_locale.js" });
    vm.runInContext(switcherSource, context, { filename: "almdina_language_switcher.js" });
    return { window: fakeWindow, handlers, calls, notices, confirms, reloads, items, sidebar };
}

async function flush() {
    await Promise.resolve();
    await Promise.resolve();
}

async function openSidebar(loaded, sidebar) {
    loaded.handlers[EVENT]({}, { sidebar: sidebar || loaded.sidebar });
    if (!loaded.sidebar.sidebar_header) {
        loaded.sidebar.sidebar_header = { dropdown_items: loaded.items };
    }
    await flush();
}

(async () => {
    assert.match(assetsSource, /almdina_language_switcher\.js/);
    assert.ok(
        assetsSource.indexOf("almdina_locale.js")
            < assetsSource.indexOf("almdina_language_switcher.js")
    );

    const languages = [
        { code: "ar", name: "العربية", direction: "rtl" },
        { code: "en", name: "English", direction: "ltr" },
        { code: "tr", name: "Türkçe", direction: "ltr" },
    ];

    const placed = load({ headerReady: false, languages: languages, lang: "ar" });
    assert.equal(languageItem(placed.items), undefined);
    await openSidebar(placed);
    await openSidebar(placed);
    const switcher = languageItem(placed.items);
    assert.ok(switcher);
    assert.equal(placed.items.filter((item) => item.name === "almdina-language").length, 1);
    assert.equal(placed.items.indexOf(switcher), 2);
    assert.equal(placed.items[1].name, "display");
    assert.equal(placed.items[3].action, "frappe.ui.toolbar.clear_cache()");
    assert.equal(switcher.label, "Language");
    assert.equal(switcher.icon, "globe");
    assert.deepEqual(
        switcher.items.map((item) => item.label),
        ["العربية", "English"]
    );
    assert.equal(switcher.items[0].icon, "check");
    assert.equal(switcher.items[1].icon, undefined);

    switcher.items[0].onClick();
    assert.equal(placed.calls.length, 0);
    assert.equal(placed.reloads.length, 0);

    const freshSidebar = { sidebar_header: { dropdown_items: menuFixture() } };
    await openSidebar(placed, freshSidebar);
    assert.equal(
        freshSidebar.sidebar_header.dropdown_items.filter((item) => item.name === "almdina-language").length,
        1
    );

    const choosing = load({ headerReady: true, languages: languages, lang: "ar" });
    const choosingItem = languageItem(choosing.items);
    choosingItem.items[1].onClick();
    choosingItem.items[0].onClick();
    assert.equal(choosing.calls.length, 1);
    assert.equal(choosing.calls[0].method, METHOD);
    assert.equal(choosing.calls[0].type, "POST");
    assert.equal(choosing.calls[0].args.language, "en");
    assert.equal(Object.keys(choosing.calls[0].args).join(","), "language");
    assert.equal(choosing.calls[0].freeze_message, "Changing language...");
    assert.equal(Object.hasOwn(choosing.calls[0].args, "user"), false);
    assert.equal(Object.hasOwn(choosing.calls[0].args, "email"), false);
    choosing.calls[0].callback({ message: { language: "en" } });
    choosing.calls[0].callback({ message: { language: "en" } });
    assert.equal(choosing.reloads.length, 1);
    assert.equal(choosing.confirms.length, 0);

    const dirtyCancel = load({
        headerReady: true,
        languages: languages,
        lang: "ar",
        cur_frm: { is_dirty() { return true; } },
        confirmChoice: "no",
    });
    languageItem(dirtyCancel.items).items[1].onClick();
    dirtyCancel.calls[0].callback({ message: { language: "en" } });
    assert.equal(dirtyCancel.confirms.length, 1);
    assert.equal(dirtyCancel.confirms[0].message, DIRTY_MESSAGE);
    assert.equal(dirtyCancel.reloads.length, 0);

    const dirtyProceed = load({
        headerReady: true,
        languages: languages,
        lang: "ar",
        cur_frm: { is_dirty() { return true; } },
        confirmChoice: "yes",
    });
    languageItem(dirtyProceed.items).items[1].onClick();
    dirtyProceed.calls[0].callback({ message: { language: "en" } });
    assert.equal(dirtyProceed.confirms.length, 1);
    assert.equal(dirtyProceed.reloads.length, 1);

    const failed = load({
        headerReady: true,
        languages: languages,
        lang: "ar",
        invokeCall: "error",
    });
    const failedItem = languageItem(failed.items);
    failedItem.items[1].onClick();
    assert.equal(failed.reloads.length, 0);
    assert.equal(failed.window.frappe.boot.lang, "ar");
    assert.equal(languageItem(failed.items).items[0].icon, "check");
    assert.equal(failed.notices.length, 1);
    assert.equal(failed.notices[0].message, "Could not change language.");
    assert.equal(failedItem.items.length, 2);

    const regional = load({
        headerReady: true,
        lang: "en",
        languages: [
            { code: "ar", name: "العربية", direction: "rtl" },
            { code: "en", name: "English", direction: "ltr" },
            { code: "pt-BR", name: "Português (Brasil)", direction: "ltr" },
        ],
    });
    const regionalItem = languageItem(regional.items);
    assert.deepEqual(
        regionalItem.items.map((item) => item.label),
        ["العربية", "English"]
    );
    assert.equal(regionalItem.items[1].icon, "check");
    regionalItem.items[1].onClick();
    assert.equal(regional.calls.length, 0);
    regionalItem.items[0].onClick();
    assert.equal(regional.calls[0].args.language, "ar");

    const guest = load({ headerReady: true, languages: languages, user: "Guest" });
    assert.equal(languageItem(guest.items), undefined);

    const bootOnly = load({
        headerReady: true,
        lang: "tr",
        languages: [
            { code: "tr", name: "Türkçe", direction: "ltr" },
            { code: "ar", name: "العربية", direction: "rtl" },
        ],
    });
    assert.deepEqual(
        languageItem(bootOnly.items).items.map((item) => item.name),
        ["almdina-language:ar"]
    );

    assert.equal(switcherSource.includes('["ar", "en"]'), false);
    assert.equal(switcherSource.includes("MutationObserver"), false);
    assert.equal(switcherSource.includes("ResizeObserver"), false);
    assert.match(switcherSource, /is_dirty/);

    console.log("Almdina language switcher simulation passed");
})().catch((error) => {
    console.error(error);
    process.exit(1);
});
