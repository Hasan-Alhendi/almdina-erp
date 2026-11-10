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
            frm.set_df_property(fieldname, "label", label);
            field.df.label = label;
            if (typeof field.set_label === "function") field.set_label(label);
        });
    },
});
