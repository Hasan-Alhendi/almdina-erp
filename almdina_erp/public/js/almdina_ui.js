(() => {
    "use strict";

    if (window.AlmdinaUi) return;

    const BUTTON_VARIANTS = Object.freeze({
        primary: "btn alm-btn-primary",
        secondary: "btn btn-default",
        danger: "btn alm-btn-danger",
        success: "btn alm-btn-success",
    });

    function escapeHtml(value) {
        const runtime = window.frappe;
        if (runtime && runtime.utils && typeof runtime.utils.escape_html === "function") {
            return runtime.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function htmlAttr(name, value) {
        if (value === undefined || value === null || value === false) return "";
        return ` ${String(name)}="${escapeHtml(value)}"`;
    }

    function button(options = {}) {
        const variant = String(options.variant || "secondary").trim();
        const size = String(options.size || "").trim();
        const className = String(options.className || "").trim();
        const label = String(options.label || "");
        const type = String(options.type || "button").trim() || "button";
        const disabled = options.disabled === true;
        const attrs = options.attrs && typeof options.attrs === "object" ? options.attrs : {};
        const classes = [
            BUTTON_VARIANTS[variant] || BUTTON_VARIANTS.secondary,
            size,
            className,
        ].filter(Boolean).join(" ");
        const extraAttrs = Object.entries(attrs)
            .map(([key, value]) => htmlAttr(key, value))
            .join("");

        return `<button type="${escapeHtml(type)}" class="${classes}"${disabled ? " disabled" : ""}${extraAttrs}>${escapeHtml(label)}</button>`;
    }

    function empty(options = {}) {
        const message = String(options.message || "");
        const title = String(options.title || "").trim();
        const className = String(options.className || "").trim();
        const action = String(options.actionHtml || "").trim();
        const classes = ["alm-empty", className].filter(Boolean).join(" ");
        const titleHtml = title ? `<strong>${escapeHtml(title)}</strong>` : "";
        const actionHtml = action ? `<div class="alm-empty-action">${action}</div>` : "";

        return `<div class="${classes}" role="status">${titleHtml}${escapeHtml(message)}${actionHtml}</div>`;
    }

    window.AlmdinaUi = Object.freeze({
        button,
        empty,
        escapeHtml,
    });
})();
