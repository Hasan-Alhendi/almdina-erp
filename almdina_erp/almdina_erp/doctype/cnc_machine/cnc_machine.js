frappe.ui.form.on("CNC Machine", {
    refresh(frm) {
        const labels = {
            machine_name: "Machine Name",
            width_cm: "Machine Width (cm)",
            length_cm: "Machine Length (cm)",
            work_zero_position: "Work Zero Position",
            left_stop_cm: "Left Stop (cm)",
            right_stop_cm: "Right Stop (cm)",
            bottom_stop_cm: "Bottom Stop (cm)",
            top_stop_cm: "Top Stop (cm)",
            enabled: "Enabled",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            const field = frm.get_field(fieldname);
            if (!field) return;
            const labelsApi = window.AlmdinaCncLabels;
            const text = labelsApi && typeof labelsApi.profileLabel === "function"
                ? labelsApi.profileLabel(label)
                : (typeof __ === "function" ? __(label) : label);
            frm.set_df_property(fieldname, "label", text);
            field.df.label = text;
            if (typeof field.set_label === "function") field.set_label(text);
        });
        apply_corner_stops(frm);
    },
    work_zero_position(frm) {
        apply_corner_stops(frm);
    },
});

const CNC_STOP_FIELDS = ["left_stop_cm", "right_stop_cm", "bottom_stop_cm", "top_stop_cm"];

function apply_corner_stops(frm) {
    const labelsApi = window.AlmdinaCncLabels;
    const active = labelsApi && typeof labelsApi.activeStopFields === "function"
        ? labelsApi.activeStopFields(frm.doc.work_zero_position)
        : [];
    CNC_STOP_FIELDS.forEach(fieldname => {
        const show = active.indexOf(fieldname) >= 0;
        if (typeof frm.toggle_display === "function") frm.toggle_display(fieldname, show);
        frm.set_df_property(fieldname, "hidden", show ? 0 : 1);
        frm.set_df_property(fieldname, "reqd", show ? 1 : 0);
    });
    const retired = frm.doc.work_zero_position === "Center";
    if (typeof frm.set_intro === "function") {
        frm.set_intro(
            retired
                ? __("This CNC machine still uses Center as its work zero. Choose Bottom Left, Bottom Right, Top Left, or Top Right before generating a new file.")
                : ""
        );
    }
}
