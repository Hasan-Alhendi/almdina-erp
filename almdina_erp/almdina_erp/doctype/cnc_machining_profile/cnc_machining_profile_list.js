frappe.listview_settings["CNC Machining Profile"] = {
    onload(listview) {
        const labels = {
            profile_id: "Profile ID",
            profile_name: "Profile Name",
            tool_preset: "Tool",
            final_depth_mm: "Final Depth (mm)",
            enabled: "Enabled",
        };
        (listview.meta.fields || []).forEach((df) => {
            if (labels[df.fieldname]) df.label = labels[df.fieldname];
        });
        (listview.columns || []).forEach((column) => {
            if (column.df && labels[column.df.fieldname]) {
                column.df.label = labels[column.df.fieldname];
            }
        });
    },
};
