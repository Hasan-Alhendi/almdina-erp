frappe.ui.form.on("CNC Tool Preset", {
    refresh(frm) {
        const labels = {
            tool_name: "Tool Name",
            tool_number: "Tool Number",
            tool_diameter_mm: "Tool Diameter (mm)",
            spindle_speed_rpm: "Spindle Speed (RPM)",
            notes: "Notes",
            stepdown_mm: "Stepdown",
            final_tool_offset_mm: "Final Tool Offset",
            stepover_size_mm: "Stepover Size",
            stepover_percent: "Stepover Percent of D",
            feed_rate_mm_sec: "Feed Rate (mm/sec)",
            plunge_rate_mm_sec: "Plunge Rate (mm/sec)",
            enabled: "Enabled",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            const field = frm.get_field(fieldname);
            if (!field) return;
            const labelsApi = window.AlmdinaCncLabels;
            const text = labelsApi && typeof labelsApi.toolLabel === "function"
                ? labelsApi.toolLabel(label)
                : label;
            frm.set_df_property(fieldname, "label", text);
            field.df.label = text;
            if (typeof field.set_label === "function") field.set_label(text);
        });
        const numberField = frm.get_field("tool_number");
        if (numberField && numberField.$input) {
            numberField.$input.val(display_tool_number(frm.doc.tool_number));
        }
    },
});

function display_tool_number(value) {
    if (value == null || value === "") return "";
    const raw = String(value).trim();
    const match = raw.match(/^(?:T)?([1-9][0-9]{0,2})$/i);
    return match ? match[1] : raw;
}
