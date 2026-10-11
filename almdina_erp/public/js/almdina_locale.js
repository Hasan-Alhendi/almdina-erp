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

    // Domain optimizer labels are stored as composed message IDs. Translate the
    // known prefix and the remainder through Frappe; this is not a catalog.
    const COMPOSED_LABEL_PREFIXES = ["Auto Pro اختار: ", "بحث معمق اختار: ", "Auto اختار: "];

    function translateLabel(value) {
        const text = String(value == null ? "" : value);
        if (!text) return text;
        const direct = translate(text);
        if (direct !== text) return direct;
        for (let index = 0; index < COMPOSED_LABEL_PREFIXES.length; index += 1) {
            const prefix = COMPOSED_LABEL_PREFIXES[index];
            if (text.indexOf(prefix) !== 0) continue;
            return translate(prefix) + translate(text.slice(prefix.length));
        }
        return text;
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
        translateLabel,
        context,
    });
})();
