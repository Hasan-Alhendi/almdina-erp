(() => {
    "use strict";

    if (window.AlmdinaCustomerInvoiceAddonSummary) return;

    const EXTRA_ADDON_TYPE = "extra_addon";
    const ADDON_ALIASES = Object.freeze({
        liner: "لاينر",
        "لاينر": "لاينر",
        "حفر مسكة غطس": "مسكة غطس",
        "تفريغ مسكة مخفية": "مسكة غطس",
        "مسكة غطس": "مسكة غطس",
    });

    function number(value) {
        const parsed = Number(value || 0);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function addonLabel(description) {
        const text = String(description || "")
            .trim()
            .replace(/^إضافة\s+/, "")
            .replace(/\s*[—-]\s*درفة\s+رقم\s+\d+\s*$/, "")
            .trim();
        return ADDON_ALIASES[text.toLocaleLowerCase()] || ADDON_ALIASES[text] || text || "إضافة";
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
                    unit: String(line.unit || "درفة").trim() || "درفة",
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
