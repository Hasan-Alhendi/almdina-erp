(() => {
    "use strict";

    if (window.AlmdinaCustomerInvoiceAddonSummary) return;

    const EXTRA_ADDON_TYPE = "extra_addon";
    // Compatibility: historical stored descriptions. They select a message ID and are not shown raw.
    const LEGACY_ADDON_PREFIX = /^(?:إضافة|Add-on)\s+/;
    const LEGACY_DOOR_SUFFIX = /\s*[—-]\s*(?:درفة\s+رقم|door number)\s+\d+\s*$/;
    const ADDON_MESSAGE_IDS = Object.freeze({
        liner: "Liner",
        "لاينر": "Liner",
        "حفر مسكة غطس": "Recessed handle",
        "تفريغ مسكة مخفية": "Recessed handle",
        "مسكة غطس": "Recessed handle",
    });

    function translate(message) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") return locale.translate(message);
        if (typeof __ === "function") return __(message);
        return String(message == null ? "" : message);
    }

    function number(value) {
        const parsed = Number(value || 0);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function addonLabel(description) {
        const text = String(description || "")
            .trim()
            .replace(LEGACY_ADDON_PREFIX, "")
            .replace(LEGACY_DOOR_SUFFIX, "")
            .trim();
        const messageId = ADDON_MESSAGE_IDS[text.toLocaleLowerCase()] || ADDON_MESSAGE_IDS[text];
        if (messageId) return translate(messageId);
        return text || translate("Add-on");
    }

    function summarizeLines(lines) {
        const result = [];
        const groups = new Map();

        (Array.isArray(lines) ? lines : []).forEach(source => {
            const line = { ...source };
            if (String(line.type || "").trim() !== EXTRA_ADDON_TYPE) {
                result.push(line);
                return;
            }

            const label = addonLabel(line.description);
            let group = groups.get(label);
            if (!group) {
                group = {
                    ...line,
                    description: label,
                    quantity: 0,
                    unit: String(line.unit || "").trim() || translate("Door"),
                    rate: 0,
                    amount: 0,
                    note: "",
                };
                groups.set(label, group);
                result.push(group);
            }

            group.quantity += number(line.quantity);
            group.amount += number(line.amount);
        });

        groups.forEach(group => {
            group.rate = group.quantity > 0 ? group.amount / group.quantity : 0;
        });

        return result;
    }

    function install() {
        const base = window.AlmdinaOrderCostUX;
        if (!base || typeof base.invoiceLines !== "function") return false;
        if (base.__customerInvoiceAddonSummary) return true;

        const originalInvoiceLines = base.invoiceLines;
        window.AlmdinaOrderCostUX = Object.freeze({
            ...base,
            __customerInvoiceAddonSummary: true,
            invoiceLines(frm) {
                return summarizeLines(originalInvoiceLines.call(base, frm));
            },
        });
        return true;
    }

    window.AlmdinaCustomerInvoiceAddonSummary = Object.freeze({
        addonLabel,
        install,
        summarizeLines,
    });

    install();
})();
