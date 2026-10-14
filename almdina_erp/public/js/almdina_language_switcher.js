(() => {
    "use strict";

    if (window.AlmdinaLanguageSwitcher) return;

    const ITEM_NAME = "almdina-language";
    const RELOAD_ACTION = "frappe.ui.toolbar.clear_cache()";
    const EVENT = "sidebar_setup.almdinaLanguageSwitcher";
    const METHOD = "almdina_erp.almdina_erp.services.user_language_service.set_current_user_language";

    let pending = false;
    let reloading = false;

    function translate(message) {
        if (typeof window.__ === "function") return window.__(message);
        return message;
    }

    function languageMatchKey(language) {
        return String(language || "").trim().replace(/_/g, "-").toLowerCase();
    }

    function currentLanguageKey() {
        const locale = window.AlmdinaLocale;
        if (!locale || typeof locale.currentLanguage !== "function") return "";
        return languageMatchKey(locale.currentLanguage());
    }

    function isGuest() {
        const session = window.frappe && frappe.session;
        const user = session && session.user;
        return !user || user === "Guest";
    }

    function bootLanguages() {
        const boot = window.frappe && frappe.boot;
        const rows = boot && boot.almdina_ui_languages;
        if (!Array.isArray(rows)) return [];
        return rows.filter((row) => row && String(row.code || "").trim());
    }

    function languageMenuItems() {
        const current = currentLanguageKey();
        return bootLanguages().map((language) => {
            const code = String(language.code).trim();
            const item = {
                name: ITEM_NAME + ":" + languageMatchKey(code),
                label: String(language.name || code),
                onClick() {
                    chooseLanguage(code);
                },
            };
            if (current && languageMatchKey(code) === current) item.icon = "check";
            return item;
        });
    }

    function switcherItem() {
        const items = languageMenuItems();
        if (!items.length) return null;
        return {
            name: ITEM_NAME,
            label: "Language",
            icon: "globe",
            items: items,
        };
    }

    function dropdownItems(sidebar) {
        const header = sidebar && sidebar.sidebar_header;
        const items = header && header.dropdown_items;
        return Array.isArray(items) ? items : null;
    }

    function removeSwitcher(items) {
        const index = items.findIndex((item) => item && item.name === ITEM_NAME);
        if (index >= 0) items.splice(index, 1);
    }

    function reconcile(sidebar) {
        const resolved = sidebar || (window.frappe && frappe.app && frappe.app.sidebar);
        const items = dropdownItems(resolved);
        if (!items) return;
        if (isGuest()) {
            removeSwitcher(items);
            return;
        }
        const entry = switcherItem();
        const existing = items.findIndex((item) => item && item.name === ITEM_NAME);
        if (!entry) {
            if (existing >= 0) items.splice(existing, 1);
            return;
        }
        if (existing >= 0) {
            items[existing].label = entry.label;
            items[existing].icon = entry.icon;
            items[existing].items = entry.items;
            return;
        }
        const reloadIndex = items.findIndex((item) => item && item.action === RELOAD_ACTION);
        if (reloadIndex >= 0) {
            items.splice(reloadIndex, 0, entry);
            return;
        }
        const displayIndex = items.findIndex((item) => item && item.name === "display");
        items.splice(displayIndex >= 0 ? displayIndex + 1 : items.length, 0, entry);
    }

    function reportFailure() {
        if (reloading) return;
        pending = false;
        if (window.frappe && typeof frappe.unfreeze === "function") frappe.unfreeze();
        if (window.frappe && typeof frappe.msgprint === "function") {
            frappe.msgprint({
                message: translate("Could not change language."),
                indicator: "red",
            });
        }
    }

    function chooseLanguage(code) {
        if (pending || reloading) return;
        if (!code || languageMatchKey(code) === currentLanguageKey()) return;
        const call = window.frappe && frappe.call;
        if (typeof call !== "function") {
            reportFailure();
            return;
        }
        pending = true;
        call({
            method: METHOD,
            type: "POST",
            args: { language: code },
            freeze: true,
            freeze_message: translate("Changing language..."),
            callback(response) {
                const saved = response && response.message && response.message.language;
                if (!saved) {
                    reportFailure();
                    return;
                }
                if (reloading) return;
                reloading = true;
                window.location.reload();
            },
            error() {
                reportFailure();
            },
        });
    }

    // sidebar_setup runs before SidebarHeader exists. The microtask runs after
    // setup() assigns sidebar.sidebar_header. create_menu keeps dropdown_items
    // by reference and rebuilds the menu the next time it opens.
    function schedule(sidebar) {
        const run = function () {
            reconcile(sidebar);
        };
        if (typeof queueMicrotask === "function") queueMicrotask(run);
        else Promise.resolve().then(run);
    }

    function bind() {
        const jq = window.jQuery;
        if (typeof jq === "function") {
            jq(document).off(EVENT).on(EVENT, function (_event, payload) {
                schedule(payload && payload.sidebar);
            });
        }
        const sidebar = window.frappe && frappe.app && frappe.app.sidebar;
        if (sidebar && sidebar.sidebar_header) reconcile(sidebar);
    }

    bind();

    window.AlmdinaLanguageSwitcher = Object.freeze({
        itemName: ITEM_NAME,
        reconcile: reconcile,
    });
})();
