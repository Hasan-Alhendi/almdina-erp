frappe.ui.form.on("CNC Tool Preset", {
    refresh(frm) {
        const labelsApi = window.AlmdinaCncLabels;
        if (labelsApi && typeof labelsApi.applyToolFieldLabels === "function") {
            labelsApi.applyToolFieldLabels(frm);
        }
        const numberField = frm.get_field("tool_number");
        if (numberField && numberField.$input) {
            numberField.$input.val(display_tool_number(frm.doc.tool_number));
        }
    },
});

function display_tool_number(value) {
    if (value == null || value === "") return "";
    const raw = String(value).trim();
    const match = raw.match(/^(?:T)?([1-9][0-9]{0,2})$/i);
    return match ? match[1] : raw;
}
