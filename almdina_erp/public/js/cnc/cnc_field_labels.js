(() => {
    "use strict";

    if (window.AlmdinaCncLabels) return;

    const TOOL_ARABIC_ONLY = new Set([
        "Tool Name",
        "Tool Number",
        "Tool Diameter (mm)",
        "Diameter (D)",
        "Diameter (mm)",
        "Spindle Speed (RPM)",
        "Spindle Speed (rpm)",
    ]);

    const TOOL_ENGLISH_NAME = {
        "Stepdown": "Stepdown",
        "Stepdown (mm)": "Stepdown",
        "Final Tool Offset": "Final Tool Offset",
        "Final Tool Offset (mm)": "Final Tool Offset",
        "Stepover Size": "Stepover Size",
        "Stepover Size (mm)": "Stepover Size",
        "Stepover size (mm)": "Stepover Size",
        "Stepover size": "Stepover Size",
        "Stepover Percent of D": "Stepover Percent of D",
        "Stepover percent of D": "Stepover Percent of D",
        "Stepover Percent": "Stepover Percent of D",
        "Feed Rate (mm/sec)": "Feed Rate",
        "Feed Rate (mm/min)": "Feed Rate",
        "Plunge Rate (mm/sec)": "Plunge Rate",
        "Plunge Rate (mm/min)": "Plunge Rate",
        "Notes": "Notes",
        "Enabled": "Enabled",
    };

    const STOP_FIELDS = Object.freeze({
        "Bottom Left": ["left_stop_cm", "bottom_stop_cm"],
        "Bottom Right": ["right_stop_cm", "bottom_stop_cm"],
        "Top Left": ["left_stop_cm", "top_stop_cm"],
        "Top Right": ["right_stop_cm", "top_stop_cm"],
    });

    function escapeHtml(value) {
        return String(value == null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function pageLanguageIsArabic() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.currentLanguage === "function") {
            return String(locale.currentLanguage()).toLowerCase().split("-")[0] === "ar";
        }
        const boot = window.frappe && window.frappe.boot;
        const language = boot && (boot.lang || (boot.user && boot.user.language));
        if (language) return String(language).toLowerCase().split("-")[0] === "ar";
        const htmlLanguage = document.documentElement && document.documentElement.lang;
        if (htmlLanguage) return String(htmlLanguage).toLowerCase().split("-")[0] === "ar";
        return true;
    }

    function translate(message) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") return locale.translate(message);
        if (typeof window.__ === "function") return window.__(message);
        return String(message == null ? "" : message);
    }

    function profileLabel(english) {
        const source = String(english || "");
        if (!pageLanguageIsArabic()) return source;
        return translate(source);
    }

    function toolLabel(english) {
        const source = String(english || "");
        if (!pageLanguageIsArabic()) return source;
        const arabic = translate(source);
        if (TOOL_ARABIC_ONLY.has(source)) return arabic;
        const englishName = TOOL_ENGLISH_NAME[source] || source.replace(/\s*\([^)]*\)\s*$/, "");
        return `${arabic} (${englishName})`;
    }

    function activeStopFields(position) {
        return (STOP_FIELDS[String(position || "")] || []).slice();
    }

    function toolDisclosureButton(label, open) {
        const expanded = open !== false;
        return `<button type="button" class="dco-tool-disclosure" data-tool-settings-toggle aria-expanded="${expanded ? "true" : "false"}">
            <span class="dco-tool-disclosure__chevron" aria-hidden="true"></span>
            <span class="dco-tool-disclosure__label">${escapeHtml(label)}</span>
        </button>`;
    }

    window.AlmdinaCncLabels = Object.freeze({
        pageLanguageIsArabic,
        profileLabel,
        toolLabel,
        activeStopFields,
        toolDisclosureButton,
        escapeHtml,
    });
})();
