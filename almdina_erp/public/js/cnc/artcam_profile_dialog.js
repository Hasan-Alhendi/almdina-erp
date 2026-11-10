(() => {
    "use strict";

    if (window.AlmdinaArtcamProfileDialog) return;

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
        if (button && button.text) button.text("Save profile");
    }

    function toolChoices(presets) {
        return (presets || []).filter(row => row && row.enabled !== false).map(row => ({
            value: row.name,
            label: row.description || row.tool_name || row.preset_name || row.name,
        }));
    }

    function writeSelect(dialog, fieldname, rows, selected) {
        const field = dialog.fields_dict && dialog.fields_dict[fieldname];
        const input = field && field.$input && field.$input.get(0);
        if (!input) return;
        input.innerHTML = "";
        const blank = document.createElement("option");
        blank.value = "";
        blank.textContent = "Choose";
        input.appendChild(blank);
        rows.forEach(row => {
            const option = document.createElement("option");
            option.value = row.value;
            option.textContent = row.label;
            input.appendChild(option);
        });
        if (selected) input.value = selected;
    }

    function toolPayload(preset) {
        const source = preset || {};
        const number = source.tool_number == null ? "" : String(source.tool_number).replace(/^T/i, "");
        return {
            description: source.description || source.tool_name || "",
            tool_type: "Ball Nose",
            tool_number: number,
            tool_units: "mm",
            rate_units: "mm/sec",
            notes: source.notes || "",
            diameter_mm: source.diameter_mm != null ? source.diameter_mm : source.tool_diameter_mm,
            stepdown_mm: source.stepdown_mm,
            final_tool_offset_mm: source.final_tool_offset_mm,
            stepover_size_mm: source.stepover_size_mm,
            stepover_percent: source.stepover_percent,
            spindle_speed_rpm: source.spindle_speed_rpm,
            feed_rate_mm_sec: source.feed_rate_mm_sec,
            plunge_rate_mm_sec: source.plunge_rate_mm_sec,
        };
    }

    function storedToolPayload(tool) {
        const source = tool || {};
        return toolPayload(Object.assign({}, source, {
            tool_number: source.tool_number,
            tool_type: source.tool_type || "Ball Nose",
            tool_units: source.tool_units || "mm",
            rate_units: source.rate_units || "mm/sec",
        }));
    }

    function fieldsFor() {
        return [
            { fieldtype: "Section Break", label: "Profile" },
            { fieldname: "profile_name", fieldtype: "Data", label: "Profile Name", reqd: 1 },
            { fieldname: "tool_preset", fieldtype: "Select", label: "Tool", reqd: 1, options: "\n" },
            { fieldtype: "Section Break", label: "Machining" },
            { fieldname: "final_depth_mm", fieldtype: "Float", label: "Final Depth (mm)", precision: 3, reqd: 1 },
            { fieldtype: "Column Break" },
            { fieldname: "safe_z_mm", fieldtype: "Float", label: "Safe Z (mm)", precision: 3, reqd: 1 },
            { fieldtype: "Section Break", label: "Home" },
            { fieldname: "home_x_mm", fieldtype: "Float", label: "Home X (mm)", precision: 3, reqd: 1 },
            { fieldtype: "Column Break" },
            { fieldname: "home_y_mm", fieldtype: "Float", label: "Home Y (mm)", precision: 3, reqd: 1 },
            { fieldtype: "Column Break" },
            { fieldname: "home_z_mm", fieldtype: "Float", label: "Home Z (mm)", precision: 3, reqd: 1 },
        ];
    }

    function open(options = {}) {
        const ui = window.frappe && frappe.ui;
        if (!ui || typeof ui.Dialog !== "function" || !options.editable) return null;
        const profile = options.profile || null;
        const presets = Array.isArray(options.presets) ? options.presets : [];
        const dialog = new ui.Dialog({
            title: profile ? "Edit Profile" : "New Profile",
            size: "large",
            fields: fieldsFor(),
            primary_action_label: "Save profile",
            primary_action(values) {
                const payload = {
                    name: values.profile_name,
                    tool_preset: values.tool_preset,
                    final_depth_mm: values.final_depth_mm,
                    safe_z_mm: values.safe_z_mm,
                    home_x_mm: values.home_x_mm,
                    home_y_mm: values.home_y_mm,
                    home_z_mm: values.home_z_mm,
                };
                if (profile && profile.profile_id) payload.profile_id = profile.profile_id;
                const pending = options.onSubmit ? options.onSubmit(payload) : null;
                Promise.resolve(pending).then(() => dialog.hide()).catch(() => {});
            },
        });
        dialog._currentTool = profile ? (profile.tool_preset || "") : "";
        const toolField = dialog.fields_dict.tool_preset;
        const originalChange = toolField.df.change;
        toolField.df.change = function changeTool() {
            const selected = this.get_value();
            if (selected && selected !== dialog._currentTool) {
                dialog._currentTool = selected;
                const preset = presets.find(row => row && row.name === selected);
                if (preset) dialog.set_values(toolPayload(preset));
            }
            if (typeof originalChange === "function") originalChange.apply(this, arguments);
            pinEnglishLabels(dialog);
        };
        dialog.show();
        if (profile) {
            dialog.set_values(Object.assign({
                profile_name: profile.name || "",
                final_depth_mm: profile.final_depth_mm,
                safe_z_mm: profile.safe_z_mm,
                home_x_mm: profile.home_x_mm,
                home_y_mm: profile.home_y_mm,
                home_z_mm: profile.home_z_mm,
            }, storedToolPayload(profile.tool_values || {})));
        }
        const choices = toolChoices(presets);
        writeSelect(dialog, "tool_preset", choices, profile && profile.tool_preset);
        if (profile && profile.tool_preset && dialog.fields_dict.tool_preset) {
            dialog.fields_dict.tool_preset.set_value(profile.tool_preset);
            writeSelect(dialog, "tool_preset", choices, profile.tool_preset);
        }
        pinEnglishLabels(dialog);
        return dialog;
    }

    window.AlmdinaArtcamProfileDialog = Object.freeze({ open });
})();
