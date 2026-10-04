(() => {
    "use strict";

    if (window.AlmdinaWorkspaceKeepPaint) return;

    /**
     * DCO workspace presentation rule (Plan + Cost):
     * A reload that still retains the last snapshot must not wipe mounted UI.
     * Full pending/error wipe is only for first load or hard empty/error states.
     */
    function presentationData(snapshot) {
        if (!snapshot || snapshot.data == null) return null;
        if (snapshot.status === "ready") return snapshot.data;
        // beginLoad keeps prior data while status flips to loading.
        if (snapshot.status === "loading") return snapshot.data;
        return null;
    }

    function shouldRetain(snapshot) {
        return Boolean(presentationData(snapshot));
    }

    function isPresentationBusy(snapshot) {
        return Boolean(snapshot && snapshot.status === "loading" && snapshot.data != null);
    }

    function markBusy(target, busy) {
        if (!target) return;
        const node = target.nodeType
            ? target
            : (typeof target.get === "function" ? target.get(0) : target[0]);
        if (!node || !node.setAttribute) return;
        if (busy) {
            node.setAttribute("aria-busy", "true");
            return;
        }
        if (typeof node.removeAttribute === "function") {
            node.removeAttribute("aria-busy");
        }
    }

    window.AlmdinaWorkspaceKeepPaint = Object.freeze({
        presentationData,
        shouldRetain,
        isPresentationBusy,
        markBusy,
    });
})();
