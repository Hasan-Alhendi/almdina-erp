frappe.query_reports["Piece Size Usage Analysis"] = {
    filters: [
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
        { fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
        { fieldname: "board_item", label: __("Board Item"), fieldtype: "Link", options: "Item" },
        { fieldname: "material", label: __("Material"), fieldtype: "Data" },
        { fieldname: "color", label: __("Color"), fieldtype: "Data" },
        { fieldname: "thickness_mm", label: __("Thickness MM"), fieldtype: "Float" },
    ],
};
