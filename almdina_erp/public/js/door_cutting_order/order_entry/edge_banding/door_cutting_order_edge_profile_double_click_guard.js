(() => {
    "use strict";

    const CLICK_DELAY_MS = 260;
    const SIDE_CONFIG = {
        long_right: {
            side: "long_right",
            selectedField: "edge_long_right",
            overrideField: "edge_long_right_type_override",
            label: "Right long edge",
        },
        long_left: {
            side: "long_left",
            selectedField: "edge_long_left",
            overrideField: "edge_long_left_type_override",
            label: "Left long edge",
        },
        width_top: {
            side: "width_top",
            selectedField: "edge_width_top",
            overrideField: "edge_width_top_type_override",
            label: "Top width edge",
        },
        width_bottom: {
            side: "width_bottom",
            selectedField: "edge_width_bottom",
            overrideField: "edge_width_bottom_type_override",
            label: "Bottom width edge",
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

    function orderKey(frm) {
        if (!frm || !frm.doc) return "";
        const name = String(frm.doc.name || "").trim();
        if (name) return name;
        // Unsaved drafts still need a stable session key so a pending click
        // cannot leak into a different order form instance.
        return `__draft__:${String(frm.doc.doctype || "Door Cutting Order")}`;
    }

    function targetKey(order, rowName, side) {
        return `${order}\0${rowName}\0${side}`;
    }

    function edgeTarget(event) {
        const toggle = event.target && event.target.closest
            ? event.target.closest(".dco-check-toggle.dco-edge-profile-target[data-edge-side]")
            : null;
        const root = rootFor(activeFrm);
        if (!toggle || !root || !root.contains(toggle)) return null;
        const config = SIDE_CONFIG[toggle.dataset.edgeSide];
        const tr = toggle.closest("tr[data-row-name]");
        if (!config || !tr) return null;
        const rowName = String(tr.dataset.rowName || "");
        const side = String(config.side || "");
        const order = orderKey(activeFrm);
        return {
            toggle,
            tr,
            config,
            order,
            rowName,
            side,
            key: targetKey(order, rowName, side),
        };
    }

    function findRowByName(root, rowName) {
        if (!root || !rowName) return null;
        return Array.from(root.querySelectorAll("tr[data-row-name]")).find(tr => (
            String(tr.dataset.rowName || "") === rowName
        )) || null;
    }

    function resolveLiveToggle(pending) {
        if (!pending) return null;
        if (pending.toggle && pending.toggle.isConnected) return pending.toggle;
        // Materializing a virtual starter rewrites data-row-name on the same <tr>
        // without recreating the side button. Prefer the live row node first.
        let tr = pending.tr && pending.tr.isConnected ? pending.tr : null;
        if (!tr) {
            const root = rootFor(activeFrm);
            tr = findRowByName(root, pending.rowName);
        }
        if (!tr) return null;
        const matches = Array.from(tr.querySelectorAll(
            `.dco-check-toggle.dco-edge-profile-target[data-edge-side="${pending.side}"]`
        ));
        return matches.find(toggle => toggle && toggle.isConnected) || null;
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

    function flushPendingClick(frm) {
        if (!pendingClick) return false;
        if (frm && activeFrm && frm !== activeFrm) return false;
        const pending = pendingClick;
        window.clearTimeout(pending.timer);
        pendingClick = null;
        if (!activeFrm || orderKey(activeFrm) !== pending.order) return false;
        const toggle = resolveLiveToggle(pending);
        if (!toggle) return false;
        replayLegacySingleClick(toggle);
        return true;
    }

    function scheduleSingleClick(identity) {
        if (pendingClick && pendingClick.key === identity.key) {
            // Same side again before the timer: restart the double-click window.
            cancelPendingClick();
        } else if (pendingClick) {
            // A different door/side must not cancel the previous selection.
            flushPendingClick();
        }
        pendingClick = {
            order: identity.order,
            rowName: identity.rowName,
            side: identity.side,
            key: identity.key,
            toggle: identity.toggle,
            tr: identity.tr,
            timer: window.setTimeout(() => {
                const current = pendingClick;
                pendingClick = null;
                if (!current) return;
                if (!activeFrm || orderKey(activeFrm) !== current.order) return;
                const toggle = resolveLiveToggle(current);
                if (toggle) replayLegacySingleClick(toggle);
            }, CLICK_DELAY_MS),
        };
    }

    function bindActiveForm(frm) {
        if (activeFrm && frm && orderKey(activeFrm) !== orderKey(frm)) {
            // Never apply a delayed click from order A onto order B.
            cancelPendingClick();
        } else if (activeFrm && frm && activeFrm !== frm) {
            cancelPendingClick();
        }
        activeFrm = frm;
    }

    document.addEventListener("click", event => {
        if (replayingSingleClick) return;
        const target = edgeTarget(event);
        if (!target || !isEditable(activeFrm)) return;

        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();

        const detail = Number(event.detail || 0);
        if (detail > 1) {
            // Only suppress the delayed single-click for a double-click on the
            // same door/side. A detail>1 on another target must not drop the
            // previous pending selection.
            if (pendingClick && pendingClick.key === target.key) {
                cancelPendingClick();
            } else if (pendingClick) {
                flushPendingClick();
            }
            return;
        }
        scheduleSingleClick(target);
    }, true);

    document.addEventListener("dblclick", event => {
        const target = edgeTarget(event);
        if (!target || !isEditable(activeFrm)) return;

        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();

        if (pendingClick && pendingClick.key === target.key) {
            cancelPendingClick();
        } else if (pendingClick) {
            flushPendingClick();
        }

        const controls = window.AlmdinaEdgeProfileControls;
        if (controls && typeof controls.openSidePopover === "function") {
            controls.openSidePopover(activeFrm, target.tr, target.config, target.toggle);
        }
    }, true);

    document.addEventListener("keydown", event => {
        if (event.key === "Escape") cancelPendingClick();
    }, true);

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { bindActiveForm(frm); },
        refresh(frm) { bindActiveForm(frm); },
    });

    window.AlmdinaEdgeProfileDoubleClickGuard = Object.freeze({
        cancelPendingClick,
        flushPendingClick,
        replayLegacySingleClick,
        CLICK_DELAY_MS,
    });
})();
