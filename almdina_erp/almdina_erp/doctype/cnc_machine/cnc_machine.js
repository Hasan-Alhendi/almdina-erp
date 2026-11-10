frappe.ui.form.on("CNC Machine", {
    refresh(frm) {
        const labels = {
            machine_name: "Machine Name",
            width_cm: "Machine Width (cm)",
            length_cm: "Machine Length (cm)",
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
