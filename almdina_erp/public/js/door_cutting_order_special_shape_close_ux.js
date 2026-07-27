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

    installStyles();
    document.addEventListener("click", handleCloseClick, true);
})();
