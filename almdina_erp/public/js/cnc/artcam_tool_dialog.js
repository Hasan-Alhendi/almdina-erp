(() => {
    "use strict";

    if (window.AlmdinaArtcamToolDialog) return;

    function translate(message) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") return locale.translate(message);
        if (typeof __ === "function") return __(message);
        return String(message || "");
    }

    function numberValue(tool, key, fallback) {
        if (!tool || tool[key] == null || tool[key] === "") return fallback;
        return tool[key];
    }

    function open(options = {}) {
        const ui = window.frappe && frappe.ui;
        if (!ui || typeof ui.Dialog !== "function") return null;
        const tool = options.tool || null;
        const displayNumber = tool && tool.tool_number
            ? String(tool.tool_number).replace(/^T/i, "")
            : "";
        const dialog = new ui.Dialog({
            title: translate(tool ? "Edit Tool" : "Edit Tool"),
            fields: [
                { fieldname: "description", fieldtype: "Data", label: translate("Description"), reqd: 1, default: (tool && (tool.description || tool.tool_name)) || "" },
                { fieldname: "tool_type", fieldtype: "Select", label: translate("Tool Type"), options: "Ball Nose", default: "Ball Nose", reqd: 1 },
                { fieldname: "tool_number", fieldtype: "Int", label: translate("Tool Number"), reqd: 1, default: displayNumber },
                { fieldname: "tool_units", fieldtype: "Select", label: translate("Tool Units"), options: "mm", default: "mm", reqd: 1 },
                { fieldname: "rate_units", fieldtype: "Select", label: translate("Rate Units"), options: "mm/sec", default: "mm/sec", reqd: 1 },
                { fieldname: "notes", fieldtype: "Small Text", label: translate("Notes"), default: (tool && tool.notes) || "" },
                { fieldname: "diameter_mm", fieldtype: "Float", label: translate("Diameter (D)"), reqd: 1, default: numberValue(tool, "diameter_mm", tool && tool.tool_diameter_mm) },
                { fieldname: "stepdown_mm", fieldtype: "Float", label: translate("Stepdown"), reqd: 1, default: numberValue(tool, "stepdown_mm", "") },
                { fieldname: "final_tool_offset_mm", fieldtype: "Float", label: translate("Final Tool Offset"), reqd: 1, default: numberValue(tool, "final_tool_offset_mm", "") },
                { fieldname: "stepover_size_mm", fieldtype: "Float", label: translate("Stepover size"), reqd: 1, default: numberValue(tool, "stepover_size_mm", "") },
                { fieldname: "stepover_percent", fieldtype: "Float", label: translate("Stepover percent of D"), reqd: 1, default: numberValue(tool, "stepover_percent", "") },
                { fieldname: "spindle_speed_rpm", fieldtype: "Int", label: translate("Spindle Speed (rpm)"), reqd: 1, default: numberValue(tool, "spindle_speed_rpm", "") },
                { fieldname: "feed_rate_mm_sec", fieldtype: "Float", label: translate("Feed Rate (mm/sec)"), reqd: 1, default: numberValue(tool, "feed_rate_mm_sec", "") },
                { fieldname: "plunge_rate_mm_sec", fieldtype: "Float", label: translate("Plunge Rate (mm/sec)"), reqd: 1, default: numberValue(tool, "plunge_rate_mm_sec", "") },
            ],
            primary_action_label: translate("Save tool"),
            primary_action(values) {
                const payload = Object.assign({}, values, {
                    tool_type: "Ball Nose",
                    tool_units: "mm",
                    rate_units: "mm/sec",
                });
                if (tool && tool.name) payload.name = tool.name;
                const pending = options.onSubmit ? options.onSubmit(payload) : null;
                Promise.resolve(pending).then(() => dialog.hide()).catch(() => {});
            },
        });
        dialog.show();
        return dialog;
    }

    function openSaved(options = {}) {
        if (!options.editable) return null;
        const presets = Array.isArray(options.presets) ? options.presets : [];
        const current = options.name
            ? presets.find(row => row && row.name === options.name) || null
            : null;
        return open({ tool: current, onSubmit: options.onSubmit });
    }

    window.AlmdinaArtcamToolDialog = Object.freeze({ open, openSaved });
})();
