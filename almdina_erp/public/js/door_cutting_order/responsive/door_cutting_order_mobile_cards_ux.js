(() => {
    "use strict";

    function rootNode(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        if (!field || !field.$wrapper) return null;
        return field.$wrapper.get ? field.$wrapper.get(0) : field.$wrapper[0];
    }

    function isReadOnly(frm) {
        if (
            frappe.almdina
            && typeof frappe.almdina.orderCanEdit === "function"
        ) {
            return !frappe.almdina.orderCanEdit(frm);
        }
        return true;
    }

    function usesResponsiveScrollTable(root) {
        if (!root || root.closest(".dco-measurement-entry-window")) return false;
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

    function shouldUseCardLayout(root, frm) {
        void frm;
        void root;
        return false;
    }

    function shouldUseReadTableLayout(root, frm) {
        return usesResponsiveScrollTable(root) && Boolean(frm);
    }

    function measurementsSection(root) {
        if (!root || typeof root.closest !== "function") return null;
        return root.closest(".dco-measurements-card, [data-fieldname='pieces_section']");
    }

    function applyLayoutClasses(frm) {
        const root = rootNode(frm);
        if (!root) return;
        const shell = root.querySelector(".dco-fast-entry-shell");
        const section = measurementsSection(root);
        const useScrollTable = shouldUseReadTableLayout(root, frm);
        const readonly = isReadOnly(frm);
        const targets = [root, shell].filter(Boolean);

        targets.forEach((node) => {
            node.classList.remove("dco-mobile-piece-cards");
            node.classList.toggle("dco-mobile-piece-read-table", useScrollTable);
            node.classList.toggle("dco-measurement-readonly-surface", useScrollTable && readonly);
        });

        if (section) {
            section.classList.toggle("dco-measurements-mobile-scroll", useScrollTable);
        }
    }

    function observe(frm) {
        const root = rootNode(frm);
        if (!root || frm.__dcoMobileCardsObservedRoot === root) return;

        if (frm.__dcoMobileCardsObserver) frm.__dcoMobileCardsObserver.disconnect();
        if (frm.__dcoMobileCardsResizeHandler) {
            window.removeEventListener("resize", frm.__dcoMobileCardsResizeHandler);
        }

        const refresh = () => applyLayoutClasses(frm);
        if (typeof ResizeObserver === "function") {
            frm.__dcoMobileCardsObserver = new ResizeObserver(refresh);
            frm.__dcoMobileCardsObserver.observe(root);
        }
        window.addEventListener("resize", refresh, { passive: true });
        frm.__dcoMobileCardsResizeHandler = refresh;
        frm.__dcoMobileCardsObservedRoot = root;
    }

    function refresh(frm) {
        applyLayoutClasses(frm);
        observe(frm);
        requestAnimationFrame(() => applyLayoutClasses(frm));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { refresh(frm); },
        refresh(frm) { refresh(frm); },
        almdina_edit_session_changed(frm) { refresh(frm); },
    });

    const measurementLifecycle = window.AlmdinaMeasurementLifecycle;
    if (measurementLifecycle && typeof measurementLifecycle.registerFeature === "function") {
        measurementLifecycle.registerFeature("mobile-piece-layout", () => {
            if (window.cur_frm && window.cur_frm.doctype === "Door Cutting Order") {
                applyLayoutClasses(window.cur_frm);
            }
        });
    }

    window.AlmdinaMobilePieceCardsUX = Object.freeze({
        apply: applyLayoutClasses,
        refresh,
        shouldUseCardLayout,
        shouldUseReadTableLayout,
        isReadOnly,
        usesResponsiveScrollTable,
    });
})();
