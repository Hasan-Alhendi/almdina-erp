frappe.ui.form.on("CNC Machining Profile", {
    refresh(frm) {
        const labels = {
            profile_id: "Profile ID",
            profile_name: "Profile Name",
            tool_preset: "Tool",
            final_depth_mm: "Final Depth (mm)",
            safe_z_mm: "Safe Z (mm)",
            home_x_mm: "Home X (mm)",
            home_y_mm: "Home Y (mm)",
            home_z_mm: "Home Z (mm)",
            enabled: "Enabled",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            const field = frm.get_field(fieldname);
            if (!field) return;
            const text = profile_label(label);
            frm.set_df_property(fieldname, "label", text);
            field.df.label = text;
            if (typeof field.set_label === "function") field.set_label(text);
        });
        frm.set_df_property("profile_id", "reqd", 0);
        frm.set_df_property("tool_values_json", "hidden", 1);
        frm.set_df_property("tool_values_json", "reqd", 0);
        const labelsApi = window.AlmdinaCncLabels;
        if (labelsApi && typeof labelsApi.ensureFormFieldsWritable === "function") {
            labelsApi.ensureFormFieldsWritable(frm, {
                keepHidden: ["tool_values_json"],
                keepReadOnly: ["profile_id"],
            });
        }
        frm._profile_tool_name = frm.doc.tool_preset || "";
        frm._profile_ready = true;
        ensure_profile_tools(frm).then(rows => {
            const host = profile_tool_host(frm);
            const existing = host && host.data("picker");
            if (existing) {
                existing.setTools(tool_choices(rows, frm));
                return;
            }
            paint_profile_tool_editor(frm, false);
        });
    },
    tool_preset(frm) {
        if (!frm._profile_ready) return;
        const selected = String(frm.doc.tool_preset || "");
        if (!selected || selected === String(frm._profile_tool_name || "")) return;
        frm._profile_tool_name = selected;
        copy_selected_tool(frm, selected);
    },
    before_save(frm) {
        frm.doc.tool_values_json = allowed_tool_overrides(frm);
    },
});

const PROFILE_TOOL_FIELDS = [
    ["tool_number", "Tool Number"],
    ["stepdown_mm", "Stepdown"],
    ["stepover_size_mm", "Stepover Size (mm)"],
    ["feed_rate_mm_sec", "Feed Rate (mm/sec)"],
    ["plunge_rate_mm_sec", "Plunge Rate (mm/sec)"],
    ["spindle_speed_rpm", "Spindle Speed (RPM)"],
];

function translate_label(message) {
    return typeof __ === "function" ? __(message) : message;
}

function profile_label(message) {
    const labelsApi = window.AlmdinaCncLabels;
    if (labelsApi && typeof labelsApi.profileLabel === "function") return labelsApi.profileLabel(message);
    return translate_label(message);
}

function tool_label(message) {
    const labelsApi = window.AlmdinaCncLabels;
    if (labelsApi && typeof labelsApi.toolLabel === "function") return labelsApi.toolLabel(message);
    return translate_label(message);
}

function stored_tool(frm) {
    const raw = frm.doc.tool_values_json;
    if (raw && typeof raw === "object") return Object.assign({}, raw);
    if (typeof raw === "string" && raw.trim()) {
        try {
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === "object" ? parsed : {};
        } catch (error) {
            return {};
        }
    }
    return {};
}

function display_tool_number(value) {
    if (value == null || value === "") return "";
    const raw = String(value).trim();
    const match = raw.match(/^(?:T)?([1-9][0-9]{0,2})$/i);
    return match ? match[1] : raw;
}

function profile_tool_host(frm) {
    const field = frm.fields_dict && frm.fields_dict.tool_preset;
    if (!field || !field.$wrapper) return null;
    const native = field.$wrapper.find(".control-input-wrapper, .control-input");
    if (native && native.addClass) native.addClass("dco-tool-picker-native");
    let host = field.$wrapper.children("[data-tool-picker-host]");
    if (!host.length) {
        host = $('<div data-tool-picker-host></div>');
        field.$wrapper.append(host);
    }
    return host;
}

function ensure_profile_tools(frm) {
    if (Array.isArray(frm._profile_tool_choices)) return Promise.resolve(frm._profile_tool_choices);
    const db = window.frappe && frappe.db;
    if (!db || typeof db.get_list !== "function") return Promise.resolve([]);
    return db.get_list("CNC Tool Preset", {
        fields: ["name", "tool_name"],
        filters: { enabled: 1 },
        limit: 500,
    }).then(rows => {
        frm._profile_tool_choices = rows || [];
        return frm._profile_tool_choices;
    }).catch(() => []);
}

function tool_choices(rows, frm) {
    const tool = frm._profile_tool || stored_tool(frm);
    const selected = String(frm.doc.tool_preset || "");
    const choices = (rows || []).map(row => ({
        value: row.name,
        label: row.tool_name || row.name,
    }));
    if (selected && !choices.some(row => row.value === selected)) {
        choices.unshift({
            value: selected,
            label: tool.tool_name || tool.description || selected,
        });
    }
    return choices;
}

function paint_profile_tool_editor(frm, force) {
    const host = profile_tool_host(frm);
    const pickerApi = window.AlmdinaCncToolPicker;
    if (!host || !pickerApi || typeof pickerApi.mount !== "function") return;
    if (!force && host.data("picker")) return;
    const tool = frm._profile_tool || stored_tool(frm);
    frm._profile_tool = tool;
    const selected = String(frm.doc.tool_preset || "");
    const picker = pickerApi.mount(host.get(0), {
        showLabel: false,
        label: profile_label("Tool"),
        changeLabel: profile_label("Tool"),
        emptyLabel: profile_label("Choose a tool"),
        selected,
        selectedLabel: tool.description || tool.tool_name || selected,
        tools: tool_choices(frm._profile_tool_choices, frm),
        settingAttribute: "data-profile-tool",
        selectAttribute: "data-profile-tool-select",
        fields: selected ? PROFILE_TOOL_FIELDS.map(([fieldname, label]) => ({
            name: fieldname,
            label: tool_label(label),
            value: fieldname === "tool_number" ? display_tool_number(tool[fieldname]) : tool[fieldname],
        })) : [],
        onToolChange(value) {
            if (!value || value === String(frm.doc.tool_preset || "")) return;
            frm.set_value("tool_preset", value);
        },
        onFieldInput(fieldname, value) {
            frm._profile_tool = frm._profile_tool || {};
            frm._profile_tool[fieldname] = fieldname === "tool_number" || value === "" ? value : Number(value);
        },
    });
    host.data("picker", picker);
}

function allowed_tool_overrides(frm) {
    const host = profile_tool_host(frm);
    const overrides = {};
    PROFILE_TOOL_FIELDS.forEach(([fieldname]) => {
        const input = host && host.find(`[data-profile-tool="${fieldname}"]`);
        if (!input || !input.length || input.val() === "") return;
        overrides[fieldname] = fieldname === "tool_number" ? input.val() : Number(input.val());
    });
    return overrides;
}

function copy_selected_tool(frm, name) {
    frappe.db.get_doc("CNC Tool Preset", name).then(doc => {
        if (String(frm.doc.tool_preset || "") !== name) return;
        frm._profile_tool = {
            description: doc.tool_name,
            tool_name: doc.tool_name,
            tool_preset: doc.name,
            tool_type: doc.tool_type,
            tool_number: display_tool_number(doc.tool_number),
            tool_units: doc.tool_units,
            rate_units: doc.rate_units,
            notes: doc.notes || "",
            diameter_mm: doc.tool_diameter_mm,
            tool_diameter_mm: doc.tool_diameter_mm,
            stepdown_mm: doc.stepdown_mm,
            final_tool_offset_mm: doc.final_tool_offset_mm,
            stepover_size_mm: doc.stepover_size_mm,
            stepover_percent: doc.stepover_percent,
            spindle_speed_rpm: doc.spindle_speed_rpm,
            feed_rate_mm_sec: doc.feed_rate_mm_sec,
            plunge_rate_mm_sec: doc.plunge_rate_mm_sec,
            enabled: doc.enabled,
        };
        paint_profile_tool_editor(frm, true);
    });
}
