(() => {
    "use strict";

    const METHOD = "almdina_erp.almdina_erp.services.production_settings_service.get_print_identity";
    const FALLBACK = Object.freeze({
        print_factory_name: "مجمع المدينة المنورة التجاري",
        print_factory_description: "الواح هايغلوس - فورميكا - cnc - ليزر - قشر",
        print_factory_address: "دمشق - ببيلا - طريق السيدة زينب",
        print_factory_contacts: "",
    });

    let cachedIdentity = null;
    let pendingRequest = null;

    function clean(value) {
        return String(value ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
    }

    function normalize(payload) {
        const source = payload && typeof payload === "object" ? payload : {};
        return Object.freeze({
            print_factory_name: clean(source.print_factory_name) || FALLBACK.print_factory_name,
            print_factory_description: clean(source.print_factory_description) || FALLBACK.print_factory_description,
            print_factory_address: clean(source.print_factory_address) || FALLBACK.print_factory_address,
            print_factory_contacts: clean(source.print_factory_contacts),
        });
    }

    async function fetchIdentity() {
        const response = await frappe.call({ method: METHOD });
        return normalize(response && response.message);
    }

    async function get(options = {}) {
        if (options.force === true) cachedIdentity = null;
        if (cachedIdentity) return cachedIdentity;
        if (!pendingRequest) {
            pendingRequest = fetchIdentity()
                .then(identity => {
                    cachedIdentity = identity;
                    return identity;
                })
                .catch(error => {
                    console.warn("Factory print identity could not be loaded; using configured defaults.", error);
                    cachedIdentity = normalize(FALLBACK);
                    return cachedIdentity;
                })
                .finally(() => {
                    pendingRequest = null;
                });
        }
        return pendingRequest;
    }

    function fallback() {
        return normalize(FALLBACK);
    }

    function clear() {
        cachedIdentity = null;
        pendingRequest = null;
    }

    window.AlmdinaFactoryPrintIdentity = Object.freeze({ get, fallback, clear });
})();