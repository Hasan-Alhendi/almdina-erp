(() => {
    "use strict";

    const PHONE_SHORT_SIDE_MAX_WIDTH = 600;
    const PHONE_VIEWPORT_MAX_WIDTH = 900;
    const TABLET_VIEWPORT_MAX_WIDTH = 1366;
    const COARSE_POINTER_QUERY = "(pointer: coarse)";
    const NO_HOVER_QUERY = "(hover: none)";

    function positiveDimension(value) {
        const dimension = Number(value || 0);
        return Number.isFinite(dimension) && dimension > 0 ? dimension : null;
    }

    function viewportWidth(root) {
        const widths = [
            root && root.getBoundingClientRect && root.getBoundingClientRect().width,
            document.documentElement && document.documentElement.clientWidth,
            window.innerWidth,
        ].map(positiveDimension).filter(Boolean);
        return widths.length ? Math.min(...widths) : Number.POSITIVE_INFINITY;
    }

    function deviceShortSide() {
        const width = positiveDimension(window.screen && window.screen.width);
        const height = positiveDimension(window.screen && window.screen.height);
        if (width && height) return Math.min(width, height);
        return width || height || Number.POSITIVE_INFINITY;
    }

    function mediaMatches(query) {
        try {
            return Boolean(window.matchMedia && window.matchMedia(query).matches);
        } catch (error) {
            return false;
        }
    }

    function isPhoneDevice(root) {
        const viewport = viewportWidth(root);
        // Prefer the live viewport so real phones and mobile browser chrome still
        // get cards even when screen.* reports the desktop monitor size (common
        // with DevTools, PWAs embedded in desktop shells, or some WebViews).
        if (viewport <= PHONE_SHORT_SIDE_MAX_WIDTH) return true;
        return deviceShortSide() <= PHONE_SHORT_SIDE_MAX_WIDTH
            && viewport <= PHONE_VIEWPORT_MAX_WIDTH;
    }

    function isTabletDevice(root) {
        const width = viewportWidth(root);
        return !isPhoneDevice(root)
            && width <= TABLET_VIEWPORT_MAX_WIDTH
            && mediaMatches(COARSE_POINTER_QUERY)
            && mediaMatches(NO_HOVER_QUERY);
    }

    function usesCardLayout(root) {
        return isPhoneDevice(root) || isTabletDevice(root);
    }

    // Backward-compatible name used by the order-list controller. Its intent is
    // responsive card presentation, so tablets intentionally participate now.
    function isPhoneLayout(root) {
        return usesCardLayout(root);
    }

    window.AlmdinaResponsiveDevice = Object.freeze({
        PHONE_SHORT_SIDE_MAX_WIDTH,
        PHONE_VIEWPORT_MAX_WIDTH,
        TABLET_VIEWPORT_MAX_WIDTH,
        deviceShortSide,
        isPhoneDevice,
        isPhoneLayout,
        isTabletDevice,
        usesCardLayout,
        viewportWidth,
    });
})();
