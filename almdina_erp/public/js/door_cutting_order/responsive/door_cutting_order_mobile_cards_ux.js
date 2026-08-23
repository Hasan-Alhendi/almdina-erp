(() => {
    "use strict";

    function rootNode(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return null;
        return field.$wrapper.get ? field.$wrapper.get(0) : field.$wrapper[0];
    }

    function shouldUseCardLayout(root) {
        const responsiveDevice = window.AlmdinaResponsiveDevice;
        if (
            responsiveDevice
            && typeof responsiveDevice.usesCardLayout === "function"
        ) {
            return responsiveDevice.usesCardLayout(root);
        }
        if (
            responsiveDevice
            && typeof responsiveDevice.isPhoneLayout === "function"
        ) {
            return responsiveDevice.isPhoneLayout(root);
        }
        try {
            return Boolean(
                window.matchMedia
                && window.matchMedia("(max-width: 600px)").matches
            );
        } catch (error) {
            return false;
        }
    }

    function apply(frm) {
        const root = rootNode(frm);
        if (!root) return;
        root.classList.toggle("dco-mobile-piece-cards", shouldUseCardLayout(root));
    }

    function observe(frm) {
        const root = rootNode(frm);
        if (!root || frm.__dcoMobileCardsObservedRoot === root) return;

        if (frm.__dcoMobileCardsObserver) frm.__dcoMobileCardsObserver.disconnect();
        if (frm.__dcoMobileCardsResizeHandler) {
            window.removeEventListener("resize", frm.__dcoMobileCardsResizeHandler);
        }

        const refresh = () => apply(frm);
        if (typeof ResizeObserver === "function") {
            frm.__dcoMobileCardsObserver = new ResizeObserver(refresh);
            frm.__dcoMobileCardsObserver.observe(root);
        }
        window.addEventListener("resize", refresh, { passive: true });
        frm.__dcoMobileCardsResizeHandler = refresh;
        frm.__dcoMobileCardsObservedRoot = root;
    }

    function refresh(frm) {
        apply(frm);
        observe(frm);
        requestAnimationFrame(() => apply(frm));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
    });

    window.AlmdinaMobilePieceCardsUX = Object.freeze({
        apply,
        shouldUseCardLayout,
    });
})();
