frappe.ui.form.on("CNC Machine", {
    refresh(frm) {
        const labels = {
            machine_name: "Machine Name",
            width_cm: "Machine Width (cm)",
            length_cm: "Machine Length (cm)",
            cutter_travel_extensions_section: "Cutter Travel Extensions",
            cutter_travel_left_extension_mm: "Left Extension (mm)",
            cutter_travel_right_extension_mm: "Right Extension (mm)",
            cutter_travel_bottom_extension_mm: "Bottom Extension (mm)",
            cutter_travel_top_extension_mm: "Top Extension (mm)",
            enabled: "Enabled",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            const field = frm.get_field(fieldname);
            if (!field) return;
            const translated = __(label);
            frm.set_df_property(fieldname, "label", translated);
            field.df.label = translated;
            if (typeof field.set_label === "function") field.set_label(translated);
        });
    },
});
