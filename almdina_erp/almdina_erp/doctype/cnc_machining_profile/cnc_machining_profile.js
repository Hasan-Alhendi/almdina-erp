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
        frm.set_df_property("tool_values_json", "hidden", 1);
    },
});
