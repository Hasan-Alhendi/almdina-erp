(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsCncMachines) return;

    const DOCTYPE = "CNC Machine";

    function attach(options = {}) {
        const editable = options.editable;

        function manage() {
            if (window.frappe && typeof frappe.set_route === "function") {
                frappe.set_route("List", DOCTYPE);
            }
            return null;
        }

        function create() {
            if (typeof editable === "function" && !editable()) return null;
            if (window.frappe && typeof frappe.new_doc === "function") {
                return frappe.new_doc(DOCTYPE);
            }
            if (window.frappe && typeof frappe.set_route === "function") {
                frappe.set_route("Form", DOCTYPE, "new");
            }
            return null;
        }

        return Object.freeze({ manage, create });
    }

    window.AlmdinaFactoryProductionSettingsCncMachines = Object.freeze({ attach });
})();
