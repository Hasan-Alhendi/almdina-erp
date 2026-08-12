(() => {
    "use strict";

    if (window.AlmdinaPageRevisit) return;

    // Frappe builds a desk page once and keeps its DOM alive for the rest of the
    // session. Every later visit only fires "show", so a page that fetches its
    // data inside `on_page_load` keeps presenting the first visit's snapshot
    // until the browser is reloaded. Pages register their loader here to reload
    // whenever the user comes back.
    function refreshOnRevisit(wrapper, reload) {
        if (!wrapper || typeof reload !== "function") return false;

        // Frappe fires "show" immediately after `on_page_load`; that first event
        // belongs to the load the page already performed.
        let initialShowConsumed = false;

        wrapper.on_page_show = function () {
            if (!initialShowConsumed) {
                initialShowConsumed = true;
                return;
            }
            try {
                Promise.resolve(reload()).catch(error => {
                    console.error("Failed to refresh Almdina page on revisit", error);
                });
            } catch (error) {
                console.error("Failed to refresh Almdina page on revisit", error);
            }
        };

        return true;
    }

    window.AlmdinaPageRevisit = Object.freeze({ refreshOnRevisit });
})();
