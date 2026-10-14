(() => {
    "use strict";

    const STYLE_ID = "dco-measurement-actions-css";
    const EDITOR_CLASS = "dco-measurement-entry-window";
    const EDIT_LABEL = "Edit order";
    const SAVE_LABEL = "Save";
    const CANCEL_LABEL = "Cancel";
    const PRINT_LABEL = "Print measurements";
    const CLOSE_LABEL = "Close and return";

    function translateCopy(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        return String(message == null ? "" : message);
    }

    function emphasizedValue(template, value) {
        const marker = "\u0001";
        const translated = String(translateCopy(template, [marker]));
        const splitAt = translated.indexOf(marker);
        const before = splitAt >= 0 ? translated.slice(0, splitAt) : translated;
        const after = splitAt >= 0 ? translated.slice(splitAt + marker.length) : "";
        return `${esc(before)}<b>${esc(value)}</b>${esc(after)}`;
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const dir = document.documentElement && document.documentElement.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function uiButton(options = {}) {
        const ui = window.AlmdinaUi;
        if (!ui || typeof ui.button !== "function") {
            throw new Error("AlmdinaUi.button is required for DCO measurement actions");
        }
        return ui.button(options);
    }

    function entryWindowIcon(kind) {
        const icons = {
            print: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 9V4h10v5"></path><rect x="6" y="9" width="12" height="10" rx="1.5"></rect><path d="M6 14h12"></path></svg>',
            edit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 18.5V20h1.5L17 8.5 15.5 7 4 18.5z"></path><path d="M14 5l3 3"></path></svg>',
            close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 7h6v10H10z"></path><path d="M14 12H6"></path><path d="M8 10l-2 2 2 2"></path></svg>',
            save: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l4 4L19 6"></path></svg>',
            cancel: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 7l8 10M16 7L8 17"></path></svg>',
        };
        return icons[kind] || "";
    }

    function entryWindowIconButton(options = {}) {
        const className = String(options.className || "").trim();
        const label = String(options.label || "").trim();
        const icon = String(options.icon || "").trim();
        const variant = String(options.variant || "secondary").trim();
        const disabled = options.disabled === true;
        const button = uiButton({
            label: "",
            variant,
            className: `dco-entry-window-icon-button ${className}`,
            disabled,
            attrs: { "aria-label": label, title: label },
        });
        return button.replace("</button>", `${icon}<span class="dco-entry-window-icon-label">${esc(label)}</span></button>`);
    }

    function orderEdgeColor(frm) {
        return String(frm.doc.edge_color || "").trim() || translateCopy("Not specified");
    }

    function printMeasurements(frm) {
        const documents = window.AlmdinaOrderDocumentPrint;
        if (!documents || typeof documents.printMeasurements !== "function") {
            frappe.msgprint(translateCopy("Could not prepare the measurements print. Reload the page and try again."));
            return Promise.resolve(false);
        }
        return Promise.resolve(documents.printMeasurements(frm));
    }

    function measurementRoot(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function updateEditorState(frm) {
        const state = frm && frm._dcoMeasurementEntryWindow;
        if (!state || !state.overlay || !state.overlay.isConnected) return;
        const status = state.overlay.querySelector(".dco-entry-window-status");
        const dirty = typeof frm.is_dirty === "function" ? frm.is_dirty() : Boolean(frm.dirty);
        if (status) {
            status.classList.toggle("is-dirty", dirty);
            status.innerHTML = dirty
                ? `<span class="dot"></span><span>${esc(translateCopy("Unsaved changes"))}</span>`
                : `<span class="dot"></span><span>${esc(translateCopy("All changes are saved"))}</span>`;
        }
        renderInlineOrderEditAction(frm);
    }

    function orderRevisionUx() {
        return window.AlmdinaOrderRevisionUX || null;
    }

    function isInlineEditActive(frm) {
        const revision = orderRevisionUx();
        return Boolean(
            revision
            && typeof revision.captureEditSessionPresence === "function"
            && revision.captureEditSessionPresence(frm)
        );
    }

    function canInlineStartEdit(frm) {
        const revision = orderRevisionUx();
        return Boolean(
            revision
            && typeof revision.canOfferEditSession === "function"
            && revision.canOfferEditSession(frm)
        );
    }

    function inlineActionSignature(frm) {
        const state = frm && frm._dcoMeasurementEntryWindow;
        return [
            isInlineEditActive(frm) ? "editing" : "idle",
            Boolean(state && state.saving) ? "1" : "0",
            canInlineStartEdit(frm) ? "1" : "0",
        ].join(":");
    }

    function flushOrderMeasurements(frm) {
        const owner = window.AlmdinaDoorCuttingFastEntry;
        if (owner && typeof owner.flush === "function") owner.flush(frm);
    }

    function renderInlineOrderEditAction(frm) {
        const state = frm && frm._dcoMeasurementEntryWindow;
        if (!state || !state.overlay || !state.overlay.isConnected) return;
        const host = state.overlay.querySelector(".dco-entry-window-order-edit-action");
        if (!host) return;
        const busy = Boolean(state.saving);
        const signature = inlineActionSignature(frm);
        if (host.dataset.almdinaInlineEdit === signature) {
            host.querySelectorAll("button").forEach((button) => {
                button.disabled = busy;
            });
            return;
        }
        host.dataset.almdinaInlineEdit = signature;
        if (isInlineEditActive(frm)) {
            host.innerHTML = `
                ${entryWindowIconButton({
                    label: translateCopy(CANCEL_LABEL),
                    className: "dco-inline-order-edit-cancel",
                    icon: entryWindowIcon("cancel"),
                    disabled: busy,
                })}
                ${entryWindowIconButton({
                    label: translateCopy(SAVE_LABEL),
                    className: "dco-inline-order-edit-save",
                    icon: entryWindowIcon("save"),
                    variant: "primary",
                    disabled: busy,
                })}
            `;
            return;
        }
        host.innerHTML = entryWindowIconButton({
            label: translateCopy(EDIT_LABEL),
            className: "dco-inline-order-edit-start",
            icon: entryWindowIcon("edit"),
            disabled: !canInlineStartEdit(frm) || busy,
        });
    }

    function ensureEditorRootMounted(frm) {
        const state = frm && frm._dcoMeasurementEntryWindow;
        if (!state || !state.overlay || !state.overlay.isConnected) return;
        const currentRoot = measurementRoot(frm);
        if (!currentRoot) return;
        if (currentRoot !== state.root) state.root = currentRoot;
        if (state.root.parentNode !== state.host) state.host.appendChild(state.root);
        updateEditorState(frm);
    }

    function closeEditableMeasurements(frm) {
        const state = frm && frm._dcoMeasurementEntryWindow;
        if (!state) return;

        if (state.root && state.placeholder && state.placeholder.parentNode) {
            state.placeholder.parentNode.insertBefore(state.root, state.placeholder);
            state.placeholder.remove();
        }
        if (state.overlay && state.overlay.parentNode) state.overlay.remove();
        document.body.classList.remove("dco-measurement-entry-open");
        frm._dcoMeasurementEntryWindow = null;
        requestAnimationFrame(() => ensureActions(frm));
    }

    function openEditableMeasurements(frm) {
        installStyles();
        const existing = frm._dcoMeasurementEntryWindow;
        if (existing && existing.overlay && existing.overlay.isConnected) {
            existing.overlay.querySelector(".dco-entry-window-close")?.focus();
            return;
        }

        const root = measurementRoot(frm);
        const shell = root && root.querySelector(".dco-fast-entry-shell");
        if (!root || !shell || !root.parentNode) {
            frappe.msgprint(translateCopy("Could not open the entry table. Reload the order and try again."));
            return;
        }

        const placeholder = document.createComment("dco-measurement-entry-origin");
        root.parentNode.insertBefore(placeholder, root);

        const overlay = document.createElement("section");
        overlay.className = EDITOR_CLASS;
        overlay.setAttribute("role", "dialog");
        overlay.setAttribute("aria-modal", "true");
        overlay.setAttribute("dir", uiDirection());
        overlay.setAttribute("aria-label", translateCopy("Door measurement entry table"));
        const orderName = frm.doc.name || translateCopy("Draft");
        const customerName = frm.doc.customer || translateCopy("No customer");
        overlay.innerHTML = `
            <header class="dco-entry-window-header">
                <div class="dco-entry-window-top">
                    <div class="dco-entry-window-title">
                        <strong>${esc(translateCopy("Door entry table"))}</strong>
                        <span>${esc(translateCopy("{0} · {1}", [orderName, customerName]))}</span>
                    </div>
                    <div class="dco-entry-window-actions almdina-ui">
                        ${entryWindowIconButton({
                            label: translateCopy(PRINT_LABEL),
                            className: "dco-entry-window-print",
                            icon: entryWindowIcon("print"),
                        })}
                        <span class="dco-entry-window-order-edit-action"></span>
                        ${entryWindowIconButton({
                            label: translateCopy(CLOSE_LABEL),
                            className: "dco-entry-window-close",
                            icon: entryWindowIcon("close"),
                        })}
                    </div>
                </div>
                <div class="dco-entry-window-meta">
                    <span>${emphasizedValue("Edge type: {0}", frm.doc.default_edge_type || "—")}</span>
                    <span>${emphasizedValue("Edge color: {0}", orderEdgeColor(frm))}</span>
                    <span class="dco-entry-window-status"><span class="dot"></span><span>${esc(translateCopy("All changes are saved"))}</span></span>
                </div>
            </header>
            <div class="dco-entry-window-body">
                <div class="dco-entry-window-host"></div>
            </div>`;

        document.body.appendChild(overlay);
        const host = overlay.querySelector(".dco-entry-window-host");
        host.appendChild(root);
        document.body.classList.add("dco-measurement-entry-open");

        const state = { overlay, host, root, placeholder, saving: false, stateFrame: null };
        frm._dcoMeasurementEntryWindow = state;
        renderInlineOrderEditAction(frm);

        overlay.addEventListener("pointerdown", event => {
            if (event.target.closest(".dco-inline-order-edit-save")) {
                flushOrderMeasurements(frm);
            }
        }, true);

        overlay.addEventListener("click", event => {
            if (event.target.closest(".dco-entry-window-close")) {
                event.preventDefault();
                closeEditableMeasurements(frm);
                return;
            }
            if (event.target.closest(".dco-entry-window-print")) {
                event.preventDefault();
                printMeasurements(frm);
                return;
            }
            if (event.target.closest(".dco-inline-order-edit-start")) {
                event.preventDefault();
                const revision = orderRevisionUx();
                if (revision && typeof revision.enterEditSession === "function") {
                    revision.enterEditSession(frm);
                    renderInlineOrderEditAction(frm);
                }
                return;
            }
            if (event.target.closest(".dco-inline-order-edit-save")) {
                event.preventDefault();
                const revision = orderRevisionUx();
                if (!revision || typeof revision.commitEditSession !== "function" || state.saving) return;
                flushOrderMeasurements(frm);
                state.saving = true;
                renderInlineOrderEditAction(frm);
                Promise.resolve(revision.commitEditSession(frm)).finally(() => {
                    state.saving = false;
                    renderInlineOrderEditAction(frm);
                });
                return;
            }
            if (event.target.closest(".dco-inline-order-edit-cancel")) {
                event.preventDefault();
                const revision = orderRevisionUx();
                if (revision && typeof revision.cancelEditSession === "function") {
                    Promise.resolve(revision.cancelEditSession(frm)).finally(() => renderInlineOrderEditAction(frm));
                }
            }
        });

        overlay.addEventListener("keydown", event => {
            if (event.key === "Escape" && !document.querySelector(".modal.show")) {
                event.preventDefault();
                closeEditableMeasurements(frm);
            }
        });

        const scheduleState = () => {
            if (state.stateFrame) return;
            state.stateFrame = requestAnimationFrame(() => {
                state.stateFrame = null;
                updateEditorState(frm);
            });
        };
        overlay.addEventListener("input", scheduleState, true);
        overlay.addEventListener("change", scheduleState, true);

        updateEditorState(frm);
        requestAnimationFrame(() => {
            const scroller = root.querySelector(".dco-fast-entry-scroll");
            if (scroller) scroller.focus({ preventScroll: true });
        });
    }

    function toolbarIconSvg(kind) {
        if (kind === "print") {
            return `
                <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                    <path d="M7 8V4h10v4"></path>
                    <path d="M7 17H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2"></path>
                    <path d="M7 14h10v6H7z"></path>
                    <path d="M17.5 11.5h.01"></path>
                </svg>`;
        }
        return `
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M8 3H3v5"></path>
                <path d="M16 3h5v5"></path>
                <path d="M21 16v5h-5"></path>
                <path d="M3 16v5h5"></path>
            </svg>`;
    }

    function decorateToolbarIconButton(button, { label, title, kind }) {
        if (!button) return;
        const resolvedLabel = String(label || "").trim();
        const resolvedTitle = String(title || resolvedLabel).trim();
        if (button.classList && typeof button.classList.add === "function") {
            button.classList.add("dco-toolbar-icon-button");
        } else if (!/\bdco-toolbar-icon-button\b/.test(String(button.className || ""))) {
            button.className = `${String(button.className || "").trim()} dco-toolbar-icon-button`.trim();
        }
        if (button.title !== resolvedTitle) button.title = resolvedTitle;
        if (button.getAttribute("aria-label") !== resolvedLabel) {
            button.setAttribute("aria-label", resolvedLabel);
        }
        // Preserve an existing SVG; only restore when another layer wiped the icon.
        if (!button.querySelector("svg")) {
            button.innerHTML = toolbarIconSvg(kind);
        }
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-measurement-table-actions{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-inline-start:auto;direction:inherit}
            .dco-measurement-table-actions .dco-toolbar-icon-button{width:32px!important;min-width:32px!important;height:32px!important;min-height:32px!important;padding:0!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;overflow:hidden!important;border-radius:8px!important}
            .dco-measurement-table-actions .dco-toolbar-icon-button svg{width:16px;height:16px;display:block;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;pointer-events:none}
            body.dco-measurement-entry-open{overflow:hidden!important}
            .${EDITOR_CLASS}{position:fixed;inset:0;z-index:1040;display:flex;flex-direction:column;background:var(--bg-color,#f4f6f8);color:var(--text-color,#172033)}
            .dco-entry-window-header{display:flex;flex-direction:column;gap:8px;padding:10px 16px;border-bottom:1px solid var(--border-color,#dfe3e8);background:var(--card-bg,#fff);box-shadow:0 4px 18px rgba(15,23,42,.08)}
            .dco-entry-window-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;min-width:0}
            .dco-entry-window-title{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1 1 auto}.dco-entry-window-title strong{font-size:17px;font-weight:900}.dco-entry-window-title span{font-size:11px;color:var(--text-muted,#66717e);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
            .dco-entry-window-meta{display:flex;align-items:center;justify-content:flex-start;gap:7px;flex-wrap:wrap}.dco-entry-window-meta>span{display:inline-flex;align-items:center;gap:4px;padding:5px 8px;border:1px solid var(--border-color,#dfe3e8);border-radius:999px;background:var(--subtle-fg,#f7f9fb);font-size:10px;white-space:nowrap}
            .dco-entry-window-status .dot{width:7px;height:7px;border-radius:50%;background:#209454}.dco-entry-window-status.is-dirty{border-color:rgba(218,146,21,.35);background:rgba(218,146,21,.08);color:#8a5a08}.dco-entry-window-status.is-dirty .dot{background:#d99215}
            .dco-entry-window-actions{display:inline-flex;align-items:center;justify-content:flex-start;gap:6px;flex:0 0 auto;flex-wrap:nowrap}
            .dco-entry-window-icon-button{width:38px!important;min-width:38px!important;height:38px!important;min-height:38px!important;padding:0!important;display:inline-flex!important;align-items:center!important;justify-content:center!important;border-radius:9px!important;font-weight:850!important}
            .dco-entry-window-icon-button svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.85;stroke-linecap:round;stroke-linejoin:round;pointer-events:none}
            .dco-entry-window-icon-label{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
            .dco-entry-window-actions .dco-entry-window-order-edit-action{display:inline-flex;align-items:center;gap:6px}
            .dco-entry-window-body{flex:1;min-height:0;padding:10px}.dco-entry-window-host{height:100%;min-height:0}.dco-entry-window-host>[data-fieldname="pieces_fast_entry"],.dco-entry-window-host>.frappe-control{height:100%;margin:0!important}.dco-entry-window-host .dco-fast-entry-shell{height:100%;display:flex;flex-direction:column;border-radius:12px}.dco-entry-window-host .dco-fast-entry-toolbar{flex:0 0 auto}.dco-entry-window-host .dco-fast-entry-scroll{flex:1 1 auto;max-height:none!important;height:auto!important;min-height:0;overflow:auto!important}.dco-entry-window-host .dco-fast-table{min-width:1180px}.dco-entry-window-host .dco-measurement-table-actions{display:none!important}
            @media(max-width:760px){.dco-measurement-table-actions{width:100%;margin-inline-start:0}.dco-entry-window-header{padding:9px 12px;gap:7px}.dco-entry-window-top{align-items:center;gap:8px}.dco-entry-window-icon-button{width:40px!important;min-width:40px!important;height:40px!important;min-height:40px!important}.dco-entry-window-body{padding:6px}}
        `;
        document.head.appendChild(style);
    }

    function ensureActions(frm) {
        installStyles();
        const root = measurementRoot(frm);
        const toolbar = root && root.querySelector(".dco-fast-entry-toolbar");
        if (!toolbar) return false;
        let actions = toolbar.querySelector(".dco-measurement-table-actions");
        if (!actions) {
            actions = document.createElement("div");
            actions.className = "dco-measurement-table-actions";
            toolbar.appendChild(actions);
        }
        let printButton = actions.querySelector(".dco-print-measurements");
        if (!printButton) {
            printButton = document.createElement("button");
            printButton.type = "button";
            printButton.className = "btn btn-default btn-sm dco-toolbar-icon-button dco-print-measurements";
            actions.appendChild(printButton);
        }
        let openButton = actions.querySelector(".dco-open-measurements-window");
        if (!openButton) {
            openButton = document.createElement("button");
            openButton.type = "button";
            openButton.className = "btn btn-default btn-sm dco-toolbar-icon-button dco-open-measurements-window";
            actions.appendChild(openButton);
        }
        decorateToolbarIconButton(printButton, {
            label: translateCopy(PRINT_LABEL),
            kind: "print",
        });
        decorateToolbarIconButton(openButton, {
            label: translateCopy("Expand measurement table"),
            title: translateCopy("Open measurement table in a separate window"),
            kind: "expand",
        });
        if (!root._dcoMeasurementActionsBound) {
            root._dcoMeasurementActionsBound = true;
            root.addEventListener("click", event => {
                const clickedPrint = event.target.closest(".dco-print-measurements");
                if (clickedPrint && root.contains(clickedPrint)) {
                    event.preventDefault();
                    printMeasurements(frm);
                    return;
                }
                const clickedOpen = event.target.closest(".dco-open-measurements-window");
                if (clickedOpen && root.contains(clickedOpen)) {
                    event.preventDefault();
                    openEditableMeasurements(frm);
                }
            });
        }
        return true;
    }

    function schedule(frm) {
        const lifecycle = window.AlmdinaMeasurementLifecycle;
        if (!lifecycle) {
            ensureActions(frm);
            requestAnimationFrame(() => ensureActions(frm));
            setTimeout(() => ensureActions(frm), 180);
            setTimeout(() => ensureActions(frm), 600);
            if (frm._dcoMeasurementEntryWindow) {
                requestAnimationFrame(() => ensureEditorRootMounted(frm));
            }
            return;
        }

        lifecycle.schedule(
            frm,
            "measurement-actions",
            () => ensureActions(frm),
            { delays: [180, 600] }
        );
        if (frm._dcoMeasurementEntryWindow) {
            lifecycle.schedule(
                frm,
                "measurement-editor-remount",
                () => ensureEditorRootMounted(frm),
                { immediate: false }
            );
        }
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) {
            const coordinator = window.AlmdinaDcoEditSessionCoordinator;
            const snapshot = coordinator && typeof coordinator.snapshot === "function"
                ? coordinator.snapshot(frm)
                : null;
            if (snapshot && snapshot.phase === "saving") return;
            schedule(frm);
        },
    });

    const measurementLifecycle = window.AlmdinaMeasurementLifecycle;
    if (measurementLifecycle && typeof measurementLifecycle.registerFeature === "function") {
        measurementLifecycle.registerFeature("measurement-actions", ensureActions);
    }

    window.AlmdinaMeasurementActions = {
        print: printMeasurements,
        open: openEditableMeasurements,
        close: closeEditableMeasurements,
        ensureActions,
    };
})();
