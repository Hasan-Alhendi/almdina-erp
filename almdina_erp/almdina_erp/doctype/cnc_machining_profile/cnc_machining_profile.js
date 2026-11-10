frappe.ui.form.on("CNC Machining Profile", {
    refresh(frm) {
        const labels = {
            profile_id: "Profile ID",
            profile_name: "Profile Name",
            tool_preset: "Tool",
            tool_values_json: "Tool Values",
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
    },
    tool_preset(frm) {
        const name = frm.doc.tool_preset;
        if (!name) {
            frm.set_value("tool_values_json", null);
            return;
        }
        frappe.db.get_doc("CNC Tool Preset", name).then((tool) => {
            frm.set_value("tool_values_json", {
                description: tool.tool_name,
                tool_type: tool.tool_type,
                tool_number: tool.tool_number,
                tool_units: tool.tool_units,
                rate_units: tool.rate_units,
                notes: tool.notes,
                diameter_mm: tool.tool_diameter_mm,
                stepdown_mm: tool.stepdown_mm,
                final_tool_offset_mm: tool.final_tool_offset_mm,
                stepover_size_mm: tool.stepover_size_mm,
                stepover_percent: tool.stepover_percent,
                spindle_speed_rpm: tool.spindle_speed_rpm,
                feed_rate_mm_sec: tool.feed_rate_mm_sec,
                plunge_rate_mm_sec: tool.plunge_rate_mm_sec,
                feed_rate_mm_min: tool.feed_rate_mm_min,
                plunge_rate_mm_min: tool.plunge_rate_mm_min,
                pass_depth_mm: tool.pass_depth_mm,
                tool_preset: tool.name,
                enabled: !!cint(tool.enabled),
            });
        });
    },
});
