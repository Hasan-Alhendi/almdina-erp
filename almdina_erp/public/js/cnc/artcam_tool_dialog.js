(() => {
    "use strict";

    if (window.AlmdinaArtcamToolDialog) return;

    function numberValue(tool, key, fallback) {
        if (!tool || tool[key] == null || tool[key] === "") return fallback;
        return tool[key];
    }

    function pinEnglishLabels(dialog) {
        (dialog.fields || []).forEach(df => {
            const field = dialog.fields_dict && dialog.fields_dict[df.fieldname];
            if (!field || !field.$wrapper) return;
            if (df.fieldtype === "Section Break") {
                const head = field.$wrapper.find(".section-head").first();
                if (!df.label) {
                    head.hide();
                    return;
                }
                const caption = head.find("span").first();
                if (caption.length) caption.text(df.label);
                else head.text(df.label);
                return;
            }
            if (df.label) field.$wrapper.find(".control-label").first().text(df.label);
        });
        const button = typeof dialog.get_primary_btn === "function" ? dialog.get_primary_btn() : null;
        if (button && button.text) button.text("Save tool");
    }

    function fieldsFor(tool) {
        const displayNumber = tool && tool.tool_number
            ? String(tool.tool_number).replace(/^T/i, "")
            : "";
        return [
            { fieldtype: "Section Break", label: "Tool" },
            { fieldname: "description", fieldtype: "Data", label: "Tool Name", reqd: 1, default: (tool && (tool.description || tool.tool_name)) || "" },
            { fieldtype: "Column Break" },
            { fieldname: "tool_number", fieldtype: "Int", label: "Tool Number", reqd: 1, default: displayNumber },
            { fieldtype: "Section Break" },
            { fieldname: "diameter_mm", fieldtype: "Float", label: "Diameter (D)", precision: 3, reqd: 1, default: numberValue(tool, "diameter_mm", tool && tool.tool_diameter_mm) },
            { fieldtype: "Column Break" },
            { fieldname: "stepdown_mm", fieldtype: "Float", label: "Stepdown (mm)", precision: 3, reqd: 1, default: numberValue(tool, "stepdown_mm", "") },
            { fieldtype: "Column Break" },
            { fieldname: "final_tool_offset_mm", fieldtype: "Float", label: "Final Tool Offset (mm)", precision: 3, reqd: 1, default: numberValue(tool, "final_tool_offset_mm", "") },
            { fieldtype: "Section Break" },
            { fieldname: "stepover_size_mm", fieldtype: "Float", label: "Stepover size (mm)", precision: 3, reqd: 1, default: numberValue(tool, "stepover_size_mm", "") },
            { fieldtype: "Column Break" },
            { fieldname: "stepover_percent", fieldtype: "Float", label: "Stepover percent of D", precision: 3, reqd: 1, default: numberValue(tool, "stepover_percent", "") },
            { fieldtype: "Column Break" },
            { fieldname: "spindle_speed_rpm", fieldtype: "Int", label: "Spindle Speed (rpm)", reqd: 1, default: numberValue(tool, "spindle_speed_rpm", "") },
            { fieldtype: "Section Break" },
            { fieldname: "feed_rate_mm_sec", fieldtype: "Float", label: "Feed Rate (mm/sec)", precision: 3, reqd: 1, default: numberValue(tool, "feed_rate_mm_sec", "") },
            { fieldtype: "Column Break" },
            { fieldname: "plunge_rate_mm_sec", fieldtype: "Float", label: "Plunge Rate (mm/sec)", precision: 3, reqd: 1, default: numberValue(tool, "plunge_rate_mm_sec", "") },
            { fieldtype: "Section Break" },
            { fieldname: "notes", fieldtype: "Small Text", label: "Notes", reqd: 0, default: (tool && tool.notes) || "" },
        ];
    }

    function open(options = {}) {
        const ui = window.frappe && frappe.ui;
        if (!ui || typeof ui.Dialog !== "function") return null;
        const tool = options.tool || null;
        const dialog = new ui.Dialog({
            title: tool && tool.name ? "Edit Tool" : "New Tool",
            size: "large",
            fields: fieldsFor(tool),
            primary_action_label: "Save tool",
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
        pinEnglishLabels(dialog);
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
