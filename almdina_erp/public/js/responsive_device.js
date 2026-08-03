(() => {
    "use strict";

    const PHONE_SHORT_SIDE_MAX_WIDTH = 600;
    const PHONE_VIEWPORT_MAX_WIDTH = 900;

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

    function isPhoneLayout(root) {
        return deviceShortSide() <= PHONE_SHORT_SIDE_MAX_WIDTH
            && viewportWidth(root) <= PHONE_VIEWPORT_MAX_WIDTH;
    }

    window.AlmdinaResponsiveDevice = Object.freeze({
        PHONE_SHORT_SIDE_MAX_WIDTH,
        PHONE_VIEWPORT_MAX_WIDTH,
        deviceShortSide,
        isPhoneLayout,
        viewportWidth,
    });
})();
