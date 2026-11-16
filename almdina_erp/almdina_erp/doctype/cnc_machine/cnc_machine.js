frappe.ui.form.on("CNC Machine", {
    refresh(frm) {
        const labelsApi = window.AlmdinaCncLabels;
        if (labelsApi && typeof labelsApi.applyMachineFieldLabels === "function") {
            labelsApi.applyMachineFieldLabels(frm);
        }
        apply_corner_stops(frm);
    },
    work_zero_position(frm) {
        apply_corner_stops(frm);
    },
});

function apply_corner_stops(frm) {
    const labelsApi = window.AlmdinaCncLabels;
    if (labelsApi && typeof labelsApi.applyCornerStops === "function") {
        labelsApi.applyCornerStops(frm);
    }
}
