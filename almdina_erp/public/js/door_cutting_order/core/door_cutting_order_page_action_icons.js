(() => {
    "use strict";

    if (window.AlmdinaDcoPageActionIcons) return;

    const ICON_ATTR = "data-dco-action-icon";
    const LABEL_ATTR = "data-dco-action-label";
    const BUTTON_CLASS = "dco-page-action-with-icon";

    // Official WhatsApp glyph paths (inline; no extra asset download).
    const WHATSAPP_SVG = (
        '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        + '<path fill="currentColor" d="M12 2a9.94 9.94 0 0 0-8.59 14.91L2 22l5.24-1.37A9.94 9.94 0 1 0 12 2zm0 18.1a8.16 8.16 0 0 1-4.16-1.14l-.3-.18-3.11.82.83-3.03-.2-.31A8.17 8.17 0 1 1 12 20.1zm4.48-5.93c-.25-.12-1.46-.72-1.69-.8-.23-.09-.4-.12-.56.12-.17.25-.64.8-.79.97-.14.16-.29.18-.54.06-.25-.12-1.05-.39-2-1.23-.74-.66-1.24-1.47-1.38-1.72-.15-.25-.02-.38.11-.5.11-.11.25-.29.37-.43.12-.14.17-.25.25-.41.08-.17.04-.31-.02-.43-.06-.12-.56-1.35-.77-1.85-.2-.48-.41-.41-.56-.42h-.48c-.17 0-.43.06-.66.31-.23.25-.87.85-.87 2.07 0 1.22.89 2.4 1.01 2.56.12.17 1.76 2.68 4.26 3.76.6.26 1.06.41 1.42.52.6.19 1.14.16 1.57.1.48-.07 1.46-.6 1.67-1.17.21-.58.21-1.07.14-1.17-.06-.11-.23-.17-.48-.29z"/>'
        + "</svg>"
    );

    function buttonNode(value) {
        if (!value) return null;
        if (value.nodeType) return value;
        if (value.jquery || (window.jQuery && value instanceof window.jQuery)) return value[0] || null;
        return value[0] && value[0].nodeType ? value[0] : null;
    }

    function frappeIcon(name) {
        if (window.frappe && frappe.utils && typeof frappe.utils.icon === "function") {
            return frappe.utils.icon(name, "sm");
        }
        const safe = String(name || "").replace(/[^a-z0-9-]/gi, "");
        return (
            `<svg class="icon icon-sm" aria-hidden="true"><use href="#icon-${safe}"></use></svg>`
        );
    }

    function iconMarkup(icon) {
        if (icon === "whatsapp") return WHATSAPP_SVG;
        return frappeIcon(icon);
    }

    function ensure(button, options = {}) {
        const node = buttonNode(button);
        const icon = String(options.icon || "").trim();
        if (!node || !node.isConnected || !icon) return false;

        const label = options.label == null
            ? ""
            : String(options.label);
        node.classList.add(BUTTON_CLASS);

        let iconHost = node.querySelector(`[${ICON_ATTR}]`);
        let labelHost = node.querySelector(`[${LABEL_ATTR}]`);

        if (!iconHost || !labelHost) {
            const existingText = String(node.textContent || "").replace(/\s+/g, " ").trim();
            node.replaceChildren();
            iconHost = document.createElement("span");
            iconHost.className = "dco-page-action-icon";
            iconHost.setAttribute(ICON_ATTR, icon);
            iconHost.setAttribute("aria-hidden", "true");
            labelHost = document.createElement("span");
            labelHost.className = "dco-page-action-label";
            labelHost.setAttribute(LABEL_ATTR, "1");
            labelHost.textContent = label || existingText;
            node.append(iconHost, labelHost);
        }

        if (iconHost.getAttribute(ICON_ATTR) !== icon || !iconHost.childElementCount) {
            iconHost.setAttribute(ICON_ATTR, icon);
            iconHost.innerHTML = iconMarkup(icon);
        }
        if (label) labelHost.textContent = label;
        return true;
    }

    window.AlmdinaDcoPageActionIcons = Object.freeze({
        BUTTON_CLASS,
        ICON_ATTR,
        LABEL_ATTR,
        ensure,
        iconMarkup,
    });
})();
