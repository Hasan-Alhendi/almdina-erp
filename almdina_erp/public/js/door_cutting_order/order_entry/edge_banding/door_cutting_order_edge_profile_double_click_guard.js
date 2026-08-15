(() => {
    "use strict";

    const CLICK_DELAY_MS = 260;
    const SIDE_CONFIG = {
        long_right: {
            side: "long_right",
            selectedField: "edge_long_right",
            overrideField: "edge_long_right_type_override",
            labelAr: "الطول الأيمن",
            labelEn: "Right long edge",
        },
        long_left: {
            side: "long_left",
            selectedField: "edge_long_left",
            overrideField: "edge_long_left_type_override",
            labelAr: "الطول الأيسر",
            labelEn: "Left long edge",
        },
        width_top: {
            side: "width_top",
            selectedField: "edge_width_top",
            overrideField: "edge_width_top_type_override",
            labelAr: "العرض العلوي",
            labelEn: "Top width edge",
        },
        width_bottom: {
            side: "width_bottom",
            selectedField: "edge_width_bottom",
            overrideField: "edge_width_bottom_type_override",
            labelAr: "العرض السفلي",
            labelEn: "Bottom width edge",
        },
    };
    let activeFrm = null;
    let pendingClick = null;
    let replayingSingleClick = false;

    function rootFor(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function isEditable(frm) {
        if (!frm) return false;
        if (window.frappe && frappe.almdina && frappe.almdina.orderCanEdit) {
            return frappe.almdina.orderCanEdit(frm);
        }
        return frm.doc.docstatus === 0;
    }

    function edgeTarget(event) {
        const toggle = event.target && event.target.closest
            ? event.target.closest(".dco-check-toggle.dco-edge-profile-target[data-edge-side]")
            : null;
        const root = rootFor(activeFrm);
        if (!toggle || !root || !root.contains(toggle)) return null;
        const config = SIDE_CONFIG[toggle.dataset.edgeSide];
        const tr = toggle.closest("tr[data-row-name]");
        return config && tr ? { toggle, tr, config } : null;
    }

    function cancelPendingClick() {
        if (!pendingClick) return;
        window.clearTimeout(pendingClick.timer);
        pendingClick = null;
    }

    function replayLegacySingleClick(toggle) {
        if (!toggle || !toggle.isConnected) return;
        replayingSingleClick = true;
        try {
            toggle.click();
        } finally {
            replayingSingleClick = false;
        }
    }

    function scheduleSingleClick(toggle) {
        cancelPendingClick();
        pendingClick = {
            toggle,
            timer: window.setTimeout(() => {
                const target = pendingClick && pendingClick.toggle;
                pendingClick = null;
                replayLegacySingleClick(target);
            }, CLICK_DELAY_MS),
        };
    }

    document.addEventListener("click", event => {
        if (replayingSingleClick) return;
        const target = edgeTarget(event);
        if (!target || !isEditable(activeFrm)) return;

        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();

        if (Number(event.detail || 0) > 1) {
            cancelPendingClick();
            return;
        }
        scheduleSingleClick(target.toggle);
    }, true);

    document.addEventListener("dblclick", event => {
        const target = edgeTarget(event);
        if (!target || !isEditable(activeFrm)) return;

        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        cancelPendingClick();

        const controls = window.AlmdinaEdgeProfileControls;
        if (controls && typeof controls.openSidePopover === "function") {
            controls.openSidePopover(activeFrm, target.tr, target.config, target.toggle);
        }
    }, true);

    document.addEventListener("keydown", event => {
        if (event.key === "Escape") cancelPendingClick();
    }, true);

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { activeFrm = frm; },
        refresh(frm) { activeFrm = frm; },
    });

    window.AlmdinaEdgeProfileDoubleClickGuard = Object.freeze({
        cancelPendingClick,
        replayLegacySingleClick,
    });
})();
