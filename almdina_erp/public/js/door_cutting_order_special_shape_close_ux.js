(() => {
    "use strict";

    const STYLE_ID = "dco-special-shape-close-fix-css";
    const MODAL_SELECTOR = ".dco-special-shape-modal";
    const CLOSE_SELECTOR = [
        ".modal-header .btn-modal-close",
        ".modal-header .btn-close",
        ".modal-header .close",
        ".modal-header [data-dismiss='modal']",
        ".modal-header [data-bs-dismiss='modal']",
    ].join(",");
    const V2_STAGE3_SCRIPTS = Object.freeze([
        "/assets/almdina_erp/js/door_drawing_v2/domain/precision_policy.js",
        "/assets/almdina_erp/js/door_drawing_v2/domain/geometry_engine.js",
        "/assets/almdina_erp/js/door_drawing_v2/domain/document_model.js",
        "/assets/almdina_erp/js/door_drawing_v2/infrastructure/legacy_adapter.js",
        "/assets/almdina_erp/js/door_drawing_v2/presentation/viewport_model.js",
        "/assets/almdina_erp/js/door_drawing_v2/presentation/editor_shell_ux.js",
    ]);

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            ${MODAL_SELECTOR} .modal-header .btn-modal-close,
            ${MODAL_SELECTOR} .modal-header .btn-close,
            ${MODAL_SELECTOR} .modal-header .close,
            ${MODAL_SELECTOR} .modal-header [data-dismiss="modal"],
            ${MODAL_SELECTOR} .modal-header [data-bs-dismiss="modal"] {
                position: relative !important;
                z-index: 20 !important;
                pointer-events: auto !important;
                cursor: pointer !important;
            }
        `;
        document.head.appendChild(style);
    }

    function requestModalHide(modal) {
        if (!modal || modal.dataset.dcoClosePending === "1") return;
        modal.dataset.dcoClosePending = "1";

        const release = () => {
            window.setTimeout(() => {
                if (modal && modal.dataset) delete modal.dataset.dcoClosePending;
            }, 0);
        };

        try {
            const $modal = window.jQuery ? window.jQuery(modal) : null;
            if ($modal && typeof $modal.modal === "function") {
                $modal.modal("hide");
                release();
                return;
            }

            if (window.bootstrap && window.bootstrap.Modal) {
                const instance = window.bootstrap.Modal.getInstance(modal)
                    || window.bootstrap.Modal.getOrCreateInstance(modal);
                instance.hide();
                release();
                return;
            }

            // Fallback for unexpected modal implementations: invoke the same
            // cancellable Bootstrap lifecycle events used by the unsaved guard.
            const hideEvent = window.jQuery
                ? window.jQuery.Event("hide.bs.modal")
                : new CustomEvent("hide.bs.modal", { bubbles: true, cancelable: true });

            if (window.jQuery) {
                window.jQuery(modal).trigger(hideEvent);
                if (hideEvent.isDefaultPrevented()) {
                    release();
                    return;
                }
            } else if (!modal.dispatchEvent(hideEvent)) {
                release();
                return;
            }

            modal.classList.remove("show");
            modal.style.display = "none";
            modal.setAttribute("aria-hidden", "true");
            modal.removeAttribute("aria-modal");
            modal.dispatchEvent(new CustomEvent("hidden.bs.modal", { bubbles: true }));
            release();
        } catch (error) {
            console.error("Failed to close special-shape dialog", error);
            release();
            frappe.msgprint("تعذر إغلاق نافذة الرسم. أعد تحميل الصفحة ثم حاول مرة أخرى.");
        }
    }

    function handleCloseClick(event) {
        const button = event.target && event.target.closest
            ? event.target.closest(CLOSE_SELECTOR)
            : null;
        if (!button) return;

        const modal = button.closest(MODAL_SELECTOR);
        if (!modal) return;

        // Capture the click before Bootstrap/Frappe competing handlers. The
        // actual hide still uses Bootstrap, so the existing unsaved-changes
        // confirmation remains authoritative.
        event.preventDefault();
        event.stopImmediatePropagation();
        event.stopPropagation();
        window.requestAnimationFrame(() => requestModalHide(modal));
    }

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            if (document.querySelector(`script[data-dco-v2-src="${src}"]`)) {
                resolve();
                return;
            }
            const script = document.createElement("script");
            script.src = src;
            script.async = false;
            script.dataset.dcoV2Src = src;
            script.onload = () => resolve();
            script.onerror = () => reject(new Error(`Failed to load ${src}`));
            document.head.appendChild(script);
        });
    }

    function bootstrapDoorDrawingV2() {
        if (window.__almdinaDoorDrawingV2Stage3Boot) return;
        window.__almdinaDoorDrawingV2Stage3Boot = true;
        V2_STAGE3_SCRIPTS.reduce(
            (promise, src) => promise.then(() => loadScript(src)),
            Promise.resolve()
        ).catch(error => {
            window.__almdinaDoorDrawingV2Stage3Boot = false;
            console.error("Door Drawing V2 Stage 3 bootstrap failed", error);
        });
    }

    installStyles();
    bootstrapDoorDrawingV2();
    document.addEventListener("click", handleCloseClick, true);
})();
