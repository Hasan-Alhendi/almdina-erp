frappe.listview_settings["CNC Machine"] = {
    onload(listview) {
        const labels = {
            machine_name: "Machine Name",
            width_cm: "Machine Width (cm)",
            length_cm: "Machine Length (cm)",
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
