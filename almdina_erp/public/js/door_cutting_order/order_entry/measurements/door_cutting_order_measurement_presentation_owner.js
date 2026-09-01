(() => {
    "use strict";

    const root = window;
    const lifecycle = root.AlmdinaMeasurementLifecycle;
    if (!lifecycle || typeof lifecycle.registerFeature !== "function") {
        throw new Error(
            "AlmdinaMeasurementLifecycle is required before measurement presentation owner"
        );
    }

    const FLEX_DISPLAYS = new Set(["flex", "inline-flex"]);
    const GRID_DISPLAYS = new Set(["grid", "inline-grid"]);
    const SCROLLABLE_OVERFLOW = new Set(["auto", "scroll", "overlay"]);

    function first(rootNode, selector) {
        if (!rootNode || typeof rootNode.querySelector !== "function") return null;
        return rootNode.querySelector(selector);
    }

    function all(rootNode, selector) {
        if (!rootNode || typeof rootNode.querySelectorAll !== "function") return [];
        return Array.from(rootNode.querySelectorAll(selector) || []);
    }

    function computed(node) {
        if (!node || typeof root.getComputedStyle !== "function") return null;
        try {
            return root.getComputedStyle(node);
        } catch (_error) {
            return null;
        }
    }

    function normalized(value) {
        return String(value || "").trim().toLowerCase();
    }

    function displayMatches(node, accepted) {
        const style = computed(node);
        return Boolean(style && accepted.has(normalized(style.display)));
    }

    function scrollIsReady(node) {
        const style = computed(node);
        if (!style) return false;
        const overflowX = normalized(style.overflowX || style.overflow);
        return SCROLLABLE_OVERFLOW.has(overflowX);
    }

    function tableIsReady(node) {
        const style = computed(node);
        return Boolean(style && normalized(style.tableLayout) === "fixed");
    }

    function reconcile(_frm, rootNode) {
        if (!rootNode || typeof rootNode.querySelector !== "function") return false;

        const toolbar = first(rootNode, ".dco-fast-entry-toolbar");
        const scroll = first(rootNode, ".dco-fast-entry-scroll");
        const table = first(rootNode, ".dco-fast-table");
        if (!toolbar || !scroll || !table) return false;

        // Non-browser test/SSR harnesses cannot prove computed presentation. The
        // central lifecycle still owns structural readiness there; in a browser,
        // computed style is mandatory before the surface may be marked ready.
        if (typeof root.getComputedStyle !== "function") return true;

        if (!displayMatches(toolbar, FLEX_DISPLAYS)) return false;
        if (!scrollIsReady(scroll)) return false;
        if (!tableIsReady(table)) return false;

        const edgeGroups = all(rootNode, ".dco-edge-buttons");
        if (edgeGroups.some(node => !displayMatches(node, GRID_DISPLAYS))) return false;

        const toggles = all(rootNode, ".dco-check-toggle");
        if (toggles.some(node => !displayMatches(node, FLEX_DISPLAYS))) return false;

        return true;
    }

    lifecycle.registerFeature("measurement-presentation", { reconcile });
})();
