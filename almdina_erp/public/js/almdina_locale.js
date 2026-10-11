(() => {
    "use strict";

    if (window.AlmdinaLocale) return;

    // Matches frappe.utils.jinja_globals.is_rtl. Layout only; not a dictionary.
    const RTL_BASE_LANGUAGES = new Set(["ar", "he", "fa", "ps"]);

    function pageLanguage() {
        const boot = window.frappe && window.frappe.boot;
        const bootLanguage = boot && (boot.lang || (boot.user && boot.user.language));
        const htmlLanguage = document.documentElement && document.documentElement.lang;
        return String(bootLanguage || htmlLanguage || "ar").trim();
    }

    function normalizeLanguage(language) {
        const value = String(language || "").trim().toLowerCase().replace(/_/g, "-");
        return value || "ar";
    }

    function baseLanguage(language) {
        return normalizeLanguage(language).split("-")[0];
    }

    function currentLanguage() {
        return normalizeLanguage(pageLanguage());
    }

    function pageDirection() {
        const dir = document.documentElement && document.documentElement.getAttribute("dir");
        return String(dir || "").trim().toLowerCase();
    }

    function isRTL(language) {
        if (language === undefined || language === null || language === "") {
            const dir = pageDirection();
            if (dir === "rtl" || dir === "ltr") return dir === "rtl";
        }
        return RTL_BASE_LANGUAGES.has(baseLanguage(language || currentLanguage()));
    }

    function direction(language) {
        return isRTL(language) ? "rtl" : "ltr";
    }

    function translate(message, replacements) {
        const translator = window.__;
        if (typeof translator !== "function") return String(message == null ? "" : message);
        return replacements === undefined ? translator(message) : translator(message, replacements);
    }

    function context(language) {
        const resolved = language ? normalizeLanguage(language) : currentLanguage();
        const rtl = isRTL(language ? resolved : undefined);
        return Object.freeze({
            language: resolved,
            direction: rtl ? "rtl" : "ltr",
            isRTL: rtl,
        });
    }

    window.AlmdinaLocale = Object.freeze({
        currentLanguage,
        direction,
        isRTL,
        translate,
        context,
    });
})();
