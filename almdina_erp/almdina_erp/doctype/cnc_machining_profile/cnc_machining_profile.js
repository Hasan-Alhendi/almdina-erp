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
            frm.set_df_property(fieldname, "label", label);
            field.df.label = label;
            if (typeof field.set_label === "function") field.set_label(label);
        });
        frm.set_df_property("profile_id", "reqd", 0);
        frm.set_df_property("tool_values_json", "hidden", 1);
        frm.set_df_property("tool_values_json", "reqd", 0);
        frm._profile_tool_name = frm.doc.tool_preset || "";
        frm._profile_ready = true;
        paint_profile_tool_editor(frm, false);
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

function escape_text(value) {
    if (frappe.utils && typeof frappe.utils.escape_html === "function") {
        return frappe.utils.escape_html(value == null ? "" : String(value));
    }
    return String(value == null ? "" : value);
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

function tool_diameter(tool) {
    const value = tool && (tool.diameter_mm != null ? tool.diameter_mm : tool.tool_diameter_mm);
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : 0;
}

function display_tool_number(value) {
    if (value == null || value === "") return "";
    const raw = String(value).trim();
    const match = raw.match(/^(?:T)?([1-9][0-9]{0,2})$/i);
    return match ? match[1] : raw;
}

function editor_box(frm) {
    const field = frm.fields_dict && frm.fields_dict.tool_preset;
    if (!field || !field.$wrapper) return null;
    let box = field.$wrapper.parent().children("[data-profile-tool-editor]");
    if (!box.length) {
        box = $('<div class="frappe-control" data-profile-tool-editor></div>');
        field.$wrapper.after(box);
    }
    return box;
}

function paint_profile_tool_editor(frm, force) {
    const box = editor_box(frm);
    if (!box) return;
    if (!force && box.find("[data-profile-tool]").length) return;
    const tool = frm._profile_tool || stored_tool(frm);
    frm._profile_tool = tool;
    frm._profile_tool_name = frm.doc.tool_preset || tool.tool_preset || "";
    const name = tool.description || tool.tool_name || frm.doc.tool_preset || "";
    const diameter = tool_diameter(tool);
    const summary = name
        ? `${translate_label("Tool")}: ${name} · ${translate_label("Tool Diameter (mm)")} ${diameter}`
        : translate_label("Choose a tool to copy its protected properties.");
    const inputs = PROFILE_TOOL_FIELDS.map(([fieldname, label]) => {
        const value = fieldname === "tool_number" ? display_tool_number(tool[fieldname]) : tool[fieldname];
        return `<div class="form-group col-sm-6">
            <label class="control-label">${escape_text(translate_label(label))}</label>
            <input class="form-control" data-profile-tool="${fieldname}" value="${escape_text(value == null ? "" : value)}">
        </div>`;
    }).join("");
    box.html(
        `<div class="form-section"><div class="section-head">${escape_text(translate_label("Editable tool settings"))}</div></div>
        <p class="text-muted" data-tool-summary>${escape_text(summary)}</p>
        <div class="row">${inputs}</div>`
    );
}

function allowed_tool_overrides(frm) {
    const box = editor_box(frm);
    const overrides = {};
    PROFILE_TOOL_FIELDS.forEach(([fieldname]) => {
        const input = box && box.find(`[data-profile-tool="${fieldname}"]`);
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
