(() => {
    "use strict";

    const STYLE_ID = "dco-special-edge-visual-guard-css";
    const LEGACY_OBSERVER_KEYS = Object.freeze([
        "_dcoSideEdgeObserver",
        "_dcoCompactEdgeProfileControlsObserver",
    ]);

    function installSpecialEdgeVisualGuard() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-operator-form .dco-fast-table tbody tr:not(.dco-special-row)
            .dco-check-toggle.dco-edge-profile-target.is-edge-missing.is-checked {
                background:var(--primary,#2490ef)!important;
                border-color:var(--primary,#2490ef)!important;
                color:#fff!important;
                box-shadow:0 2px 7px rgba(15,23,42,.16)!important;
            }
            .dco-operator-form .dco-fast-table tbody tr.dco-special-row
            .dco-check-toggle.is-checked,
            .dco-operator-form .dco-fast-table tbody tr.dco-special-row
            .dco-check-toggle.dco-edge-profile-target.is-edge-custom.is-checked,
            .dco-operator-form .dco-fast-table tbody tr.dco-special-row
            .dco-check-toggle.dco-edge-profile-target.is-edge-missing.is-checked {
                background:#b5701c!important;
                border-color:#b5701c!important;
                color:#fff!important;
                box-shadow:0 2px 7px rgba(111,78,55,.18)!important;
            }
        `;
        document.head.appendChild(style);
    }

    function measurementWrapper(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function disconnectLegacyObservers(wrapper) {
        if (!wrapper) return 0;
        let disconnected = 0;
        LEGACY_OBSERVER_KEYS.forEach(key => {
            const observer = wrapper[key];
            if (observer && typeof observer.disconnect === "function") {
                observer.disconnect();
                disconnected += 1;
            }
            wrapper[key] = null;
        });
        return disconnected;
    }

    function structuralMeasurementMutation(mutation) {
        const nodes = [
            ...(mutation.addedNodes || []),
            ...(mutation.removedNodes || []),
        ];
        return nodes.some(node => {
            if (!node || node.nodeType !== 1) return false;
            if (node.matches(".dco-fast-entry-shell,tbody,tr[data-row-name]")) return true;
            if (node.matches("td") && node.querySelector("input[data-field],select[data-field]")) return true;
            return Boolean(node.querySelector(
                ".dco-fast-entry-shell,tbody tr[data-row-name],input[data-field='width_cm'],select[data-field='piece_type']"
            ));
        });
    }

    function renderDecorations(frm) {
        installSpecialEdgeVisualGuard();
        const wrapper = measurementWrapper(frm);
        if (!wrapper) return false;

        // These renderers still own their feature-specific UI and form-field hooks,
        // but their historical broad DOM observers are not runtime owners anymore.
        const multiEdge = window.AlmdinaMultiEdgeBanding;
        if (multiEdge && typeof multiEdge.schedule === "function") {
            multiEdge.schedule(frm);
        }
        const controls = window.AlmdinaEdgeProfileControls;
        if (controls && typeof controls.schedule === "function") {
            controls.schedule(frm);
        }

        // schedule() performs its immediate apply synchronously. Once bind() has
        // installed the old observers, disconnect them here; later delayed applies
        // keep their bound flags and therefore do not recreate those observers.
        disconnectLegacyObservers(wrapper);
        return true;
    }

    function scheduleStructuralRefresh(frm) {
        const lifecycle = window.AlmdinaMeasurementLifecycle;
        if (lifecycle && typeof lifecycle.schedule === "function") {
            lifecycle.schedule(
                frm,
                "edge-render-structure",
                () => renderDecorations(frm),
                { immediate: false, delays: [] }
            );
            return;
        }
        window.requestAnimationFrame(() => renderDecorations(frm));
    }

    function registerObserver(frm, observer) {
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.registerObserver === "function") {
            context.registerObserver(frm, "edge-render-structure-observer", observer);
        }
    }

    function install(frm) {
        installSpecialEdgeVisualGuard();
        const wrapper = measurementWrapper(frm);
        if (!wrapper) return false;

        if (frm.__dcoEdgeRenderObservedWrapper !== wrapper) {
            if (frm.__dcoEdgeRenderObserver) frm.__dcoEdgeRenderObserver.disconnect();

            let queued = false;
            const observer = new MutationObserver(mutations => {
                if (queued || !mutations.some(structuralMeasurementMutation)) return;
                queued = true;
                const lifecycle = window.AlmdinaMeasurementLifecycle;
                const finish = () => {
                    queued = false;
                    renderDecorations(frm);
                };
                if (lifecycle && typeof lifecycle.schedule === "function") {
                    lifecycle.schedule(
                        frm,
                        "edge-render-owner-frame",
                        finish,
                        { immediate: false, delays: [] }
                    );
                } else {
                    window.requestAnimationFrame(finish);
                }
            });
            observer.observe(wrapper, { childList: true, subtree: true });
            frm.__dcoEdgeRenderObserver = observer;
            frm.__dcoEdgeRenderObservedWrapper = wrapper;
            registerObserver(frm, observer);
        }

        renderDecorations(frm);
        return true;
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { install(frm); },
        refresh(frm) { install(frm); },
        almdina_edit_session_changed(frm) { install(frm); },
        pieces_add(frm) { scheduleStructuralRefresh(frm); },
        pieces_remove(frm) { scheduleStructuralRefresh(frm); },
    });

    const measurementLifecycle = window.AlmdinaMeasurementLifecycle;
    if (measurementLifecycle && typeof measurementLifecycle.registerFeature === "function") {
        measurementLifecycle.registerFeature("edge-render-owner", install);
    }

    window.AlmdinaEdgeRenderOwner = Object.freeze({
        install,
        renderDecorations,
        disconnectLegacyObservers,
        structuralMeasurementMutation,
    });
})();
