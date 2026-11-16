frappe.ui.form.on("CNC Machine", {
    refresh(frm) {
        const labels = {
            machine_name: "Machine Name",
            width_cm: "Machine Width (cm)",
            length_cm: "Machine Length (cm)",
            work_zero_position: "Work Zero Position",
            left_stop_cm: "Left Stop (cm)",
            bottom_stop_cm: "Bottom Stop (cm)",
            enabled: "Enabled",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            const field = frm.get_field(fieldname);
            if (!field) return;
            const text = typeof __ === "function" ? __(label) : label;
            frm.set_df_property(fieldname, "label", text);
            field.df.label = text;
            if (typeof field.set_label === "function") field.set_label(text);
        });
    },
});
