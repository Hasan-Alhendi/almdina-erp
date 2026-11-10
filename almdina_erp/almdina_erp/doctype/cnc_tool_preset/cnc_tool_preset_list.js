frappe.listview_settings["CNC Tool Preset"] = {
    onload(listview) {
        const labels = {
            tool_name: "Tool Name",
            tool_number: "Tool Number",
            tool_diameter_mm: "Tool Diameter (mm)",
            spindle_speed_rpm: "Spindle Speed (RPM)",
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
