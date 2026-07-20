frappe.query_reports["Remnant Inventory"] = {
    filters: [
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nAvailable\nReserved\nConsumed\nScrapped", default: "Available" },
        { fieldname: "board_item", label: __("Board Item"), fieldtype: "Link", options: "Item", get_query: () => ({ filters: { custom_is_mdf: 1 } }) },
        { fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse" },
        { fieldname: "material", label: __("Material"), fieldtype: "Data" },
        { fieldname: "color", label: __("Color"), fieldtype: "Data" },
    ],
};
