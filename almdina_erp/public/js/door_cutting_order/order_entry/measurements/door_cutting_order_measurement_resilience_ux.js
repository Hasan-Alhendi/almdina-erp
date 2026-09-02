(() => {
    "use strict";

    const STYLE_ID = "dco-measurement-resilience-css";
    const RESTORE_DELAYS = [0, 50];

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function escapeHtml(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            /* Horizontal scrolling keeps the notes column readable instead of
               crushing it into leftover space or hiding row actions. */
            .dco-fast-entry-scroll {
                overflow-x:auto !important;
                overflow-y:auto !important;
                overscroll-behavior:contain;
                overflow-anchor:none;
                scrollbar-width:thin;
                scrollbar-color:rgba(91,105,120,.48) transparent;
            }
            .dco-fast-entry-scroll::-webkit-scrollbar { width:10px; height:10px; }
            .dco-fast-entry-scroll::-webkit-scrollbar-track { background:rgba(0,0,0,.025); }
            .dco-fast-entry-scroll::-webkit-scrollbar-thumb {
                background:rgba(91,105,120,.42);
                border:2px solid transparent;
                background-clip:padding-box;
                border-radius:999px;
            }
            .dco-fast-entry-scroll::-webkit-scrollbar-thumb:hover { background:rgba(58,73,88,.58); background-clip:padding-box; }

            .dco-notes-editor {
                display:grid;
                grid-template-columns:minmax(220px,1fr) 31px;
                align-items:center;
                gap:4px;
                width:100%;
                min-width:260px;
            }
            .dco-notes-editor .dco-notes-input {
                min-width:0 !important;
                text-overflow:ellipsis;
                white-space:nowrap;
                overflow:hidden;
                padding-inline-end:7px !important;
            }
            .dco-notes-expand {
                width:31px;
                height:35px;
                min-width:31px;
                border:1px solid var(--border-color,#ccd3da);
                border-radius:7px;
                background:var(--card-bg,#fff);
                color:var(--text-muted,#607080);
                cursor:pointer;
                display:inline-grid;
                place-items:center;
                padding:0;
                font-size:15px;
                line-height:1;
                transition:border-color .12s ease,background .12s ease,color .12s ease,transform .05s ease;
            }
            .dco-notes-expand:hover:not(:disabled),
            .dco-notes-expand:focus-visible {
                border-color:var(--primary,#2490ef);
                color:var(--primary,#1674c5);
                background:rgba(36,144,239,.07);
                outline:none;
            }
            .dco-notes-expand:active:not(:disabled) { transform:scale(.96); }
            .dco-notes-expand.has-note {
                border-color:rgba(36,144,239,.36);
                color:var(--primary,#1674c5);
                background:rgba(36,144,239,.08);
                font-weight:900;
            }
            .dco-notes-expand.has-long-note::after {
                content:"";
                position:absolute;
                width:6px;
                height:6px;
                margin:-23px -22px 0 0;
                border-radius:50%;
                background:#e0a21a;
                box-shadow:0 0 0 2px var(--card-bg,#fff);
            }
            .dco-notes-expand { position:relative; }
            .dco-notes-expand:disabled { opacity:.38; cursor:not-allowed; }

            .dco-large-notes-dialog .modal-dialog { max-width:min(760px,94vw) !important; }
            .dco-large-notes-dialog .modal-content { border-radius:16px; overflow:hidden; }
            .dco-large-notes-dialog .modal-body { background:var(--subtle-fg,#f6f8fa); }
            .dco-large-notes-dialog textarea[data-fieldname="notes"] {
                min-height:240px !important;
                max-height:55vh;
                resize:vertical;
                padding:14px !important;
                border-radius:11px !important;
                font-size:15px;
                line-height:1.85;
                background:var(--card-bg,#fff);
            }
            .dco-note-context {
                display:flex;
                align-items:center;
                gap:8px;
                flex-wrap:wrap;
                margin-bottom:10px;
                padding:9px 11px;
                border:1px solid var(--border-color,#dfe3e8);
                border-radius:10px;
                background:var(--card-bg,#fff);
                color:var(--text-muted,#607080);
                font-size:12px;
            }
            .dco-note-context b { color:var(--text-color,#172033); }

            .dco-fast-table .dco-col-notes {
                width:auto !important;
                min-width:300px !important;
            }

            @media (max-width:980px) {
                .dco-fast-table {
                    width:1180px !important;
                    min-width:1180px !important;
                    max-width:none !important;
                }
                .dco-fast-table .dco-col-notes { width:auto !important; min-width:300px !important; }
                .dco-fast-table .dco-select-col,
                .dco-fast-table .dco-col-no {
                    position:sticky;
                    background:var(--card-bg,#fff) !important;
                }
                .dco-fast-table .dco-select-col { right:0; z-index:7; }
                .dco-fast-table .dco-col-no { right:32px; z-index:6; box-shadow:-5px 0 9px rgba(15,23,42,.055); }
                .dco-fast-table thead .dco-select-col,
                .dco-fast-table thead .dco-col-no { z-index:12; }
            }

            @media (max-width:720px) {
                /* Keep important actions reachable through horizontal scrolling. */
                .dco-fast-table .dco-col-sketch,
                .dco-fast-table .dco-col-delete { display:table-cell !important; }
                .dco-fast-table { width:1180px !important; min-width:1180px !important; }
                .dco-fast-table .dco-col-notes { width:auto !important; min-width:300px !important; }
                .dco-fast-entry-toolbar { align-items:flex-start; }
            }
        `;
        document.head.appendChild(style);
    }

    function getRoot(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function rowByName(frm, name) {
        return (frm.doc.pieces || []).find(row => row.name === name) || null;
    }

    function noteButtonTitle(value) {
        const length = String(value || "").length;
        if (!length) return isArabic() ? "فتح محرر ملاحظة كبيرة" : "Open large note editor";
        return isArabic()
            ? `فتح الملاحظة كاملة — ${length} حرف`
            : `Open full note — ${length} characters`;
    }

    function refreshNoteEditor(editor) {
        if (!editor) return;
        const input = editor.querySelector("input.dco-notes-input");
        const button = editor.querySelector("button.dco-notes-expand");
        if (!input || !button) return;
        const value = String(input.value || "");
        input.title = value;
        button.title = noteButtonTitle(value);
        button.setAttribute("aria-label", noteButtonTitle(value));
        button.classList.toggle("has-note", Boolean(value.trim()));
        button.classList.toggle("has-long-note", value.length > 45);
        const tr = editor.closest("tr[data-row-name]");
        button.disabled = Boolean(tr && tr.classList.contains("dco-virtual-row"));
    }

    function decorateNotes(root) {
        root.querySelectorAll("input.dco-fast-input[data-field='notes']").forEach(input => {
            let editor = input.closest(".dco-notes-editor");
            if (!editor) {
                editor = document.createElement("div");
                editor.className = "dco-notes-editor";
                input.classList.add("dco-notes-input");
                input.parentNode.insertBefore(editor, input);
                editor.appendChild(input);

                const button = document.createElement("button");
                button.type = "button";
                button.className = "dco-notes-expand";
                button.innerHTML = "↗";
                editor.appendChild(button);
            }
            refreshNoteEditor(editor);
        });
    }

    function openNotesDialog(frm, input) {
        const tr = input.closest("tr[data-row-name]");
        const row = rowByName(frm, tr && tr.dataset.rowName);
        if (!row) return;

        const pieceNo = row.piece_no || row.idx || "—";
        const context = `${row.width_cm || "—"} × ${row.length_cm || "—"} سم · ${isArabic() ? "العدد" : "Qty"}: ${row.qty || 1}`;
        const dialog = new frappe.ui.Dialog({
            title: isArabic() ? `ملاحظات الدرفة رقم ${pieceNo}` : `Piece ${pieceNo} notes`,
            size: "large",
            fields: [
                {
                    fieldname: "context",
                    fieldtype: "HTML",
                    options: `<div class="dco-note-context"><b>${isArabic() ? "الدرفة" : "Piece"} #${escapeHtml(pieceNo)}</b><span>${escapeHtml(context)}</span><span>${isArabic() ? "يمكن كتابة ملاحظة طويلة متعددة الأسطر." : "Long multi-line notes are supported."}</span></div>`,
                },
                {
                    fieldname: "notes",
                    fieldtype: "Small Text",
                    label: isArabic() ? "الملاحظات الكاملة" : "Full notes",
                },
            ],
            primary_action_label: isArabic() ? "حفظ الملاحظة" : "Save note",
            primary_action(values) {
                const value = String(values.notes || "").trim();
                row.notes = value;
                input.value = value;
                frm.dirty();
                refreshNoteEditor(input.closest(".dco-notes-editor"));
                Promise.resolve(frm.script_manager.trigger("notes", row.doctype, row.name)).catch(error => console.error(error));
                dialog.hide();
                frappe.show_alert({
                    message: isArabic() ? "تم تحديث ملاحظة الدرفة." : "Piece note updated.",
                    indicator: "green",
                });
            },
        });

        dialog.$wrapper.addClass("dco-large-notes-dialog");
        dialog.set_value("notes", row.notes || "");
        dialog.show();
        requestAnimationFrame(() => {
            const textarea = dialog.$wrapper.find('textarea[data-fieldname="notes"]').get(0);
            if (!textarea) return;
            textarea.focus();
            textarea.setSelectionRange(textarea.value.length, textarea.value.length);
            textarea.addEventListener("keydown", event => {
                if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                    event.preventDefault();
                    dialog.get_primary_btn().trigger("click");
                }
            });
        });
    }

    function scrollableAncestors(node) {
        const snapshots = [];
        let current = node && node.parentElement;
        while (current && current !== document.body) {
            const style = window.getComputedStyle(current);
            const canScroll = /(auto|scroll|overlay)/.test(`${style.overflowY} ${style.overflowX}`);
            if (canScroll && (current.scrollHeight > current.clientHeight || current.scrollWidth > current.clientWidth)) {
                snapshots.push({ node: current, top: current.scrollTop, left: current.scrollLeft });
            }
            current = current.parentElement;
        }
        return snapshots;
    }

    function capturePosition(root, control) {
        const scroller = root.querySelector(".dco-fast-entry-scroll");
        const tr = control.closest("tr[data-row-name]");
        const scrollingElement = document.scrollingElement;
        return {
            rowName: tr ? tr.dataset.rowName || "" : "",
            fieldName: control.dataset.field || "",
            tableTop: scroller ? scroller.scrollTop : 0,
            tableLeft: scroller ? scroller.scrollLeft : 0,
            documentTop: scrollingElement ? scrollingElement.scrollTop : 0,
            documentLeft: scrollingElement ? scrollingElement.scrollLeft : 0,
            ancestors: scrollableAncestors(root),
        };
    }

    function restorePosition(frm, state, token) {
        if (!state || frm._dco_piece_type_restore_token !== token) return;
        const root = getRoot(frm);
        if (!root) return;
        const scroller = root.querySelector(".dco-fast-entry-scroll");
        const selector = state.rowName && state.fieldName
            ? `tr[data-row-name="${CSS.escape(state.rowName)}"] [data-field="${CSS.escape(state.fieldName)}"]`
            : "";
        const control = selector ? root.querySelector(selector) : null;

        if (control) control.focus({ preventScroll: true });
        if (scroller) {
            scroller.scrollTop = state.tableTop;
            scroller.scrollLeft = state.tableLeft;
        }
        state.ancestors.forEach(snapshot => {
            if (!snapshot.node || !snapshot.node.isConnected) return;
            snapshot.node.scrollTop = snapshot.top;
            snapshot.node.scrollLeft = snapshot.left;
        });
        if (document.scrollingElement) {
            document.scrollingElement.scrollTop = state.documentTop;
            document.scrollingElement.scrollLeft = state.documentLeft;
        }
    }

    function preservePositionAcrossPieceTypeRender(frm, root, control) {
        const state = capturePosition(root, control);
        const token = `${Date.now()}-${Math.random()}`;
        frm._dco_piece_type_restore_token = token;

        queueMicrotask(() => requestAnimationFrame(() => restorePosition(frm, state, token)));
        RESTORE_DELAYS.forEach(delay => {
            window.setTimeout(() => restorePosition(frm, state, token), delay);
        });
        window.setTimeout(() => {
            if (frm._dco_piece_type_restore_token === token) frm._dco_piece_type_restore_token = null;
        }, 180);
    }

    function bind(frm, root) {
        if (root._dcoMeasurementResilienceBound) return;
        root._dcoMeasurementResilienceBound = true;

        root.addEventListener("change", event => {
            const control = event.target.closest("select.dco-fast-select[data-field='piece_type']");
            if (!control || !root.contains(control)) return;
            preservePositionAcrossPieceTypeRender(frm, root, control);
        }, true);

        root.addEventListener("input", event => {
            const input = event.target.closest("input.dco-notes-input[data-field='notes']");
            if (!input || !root.contains(input)) return;
            refreshNoteEditor(input.closest(".dco-notes-editor"));
        }, true);

        root.addEventListener("click", event => {
            const button = event.target.closest("button.dco-notes-expand");
            if (!button || !root.contains(button)) return;
            event.preventDefault();
            event.stopPropagation();
            const input = button.closest(".dco-notes-editor")?.querySelector("input.dco-notes-input");
            if (input) openNotesDialog(frm, input);
        });
    }

    function observe(frm, root) {
        if (root._dcoMeasurementResilienceObserver) return;
        const observer = new MutationObserver(() => {
            requestAnimationFrame(() => {
                const lifecycle = window.AlmdinaMeasurementLifecycle;
                if (
                    lifecycle
                    && typeof lifecycle.isReady === "function"
                    && typeof lifecycle.recover === "function"
                    && lifecycle.isReady(frm) === false
                ) {
                    lifecycle.recover(frm);
                }

                const currentRoot = getRoot(frm);
                if (!currentRoot) return;
                decorateNotes(currentRoot);
                bind(frm, currentRoot);
            });
        });
        observer.observe(root, { childList: true, subtree: true });
        root._dcoMeasurementResilienceObserver = observer;
    }

    function enhance(frm) {
        installStyles();
        const root = getRoot(frm);
        if (!root) return;
        decorateNotes(root);
        bind(frm, root);
        observe(frm, root);
    }

    function schedule(frm) {
        const lifecycle = window.AlmdinaMeasurementLifecycle;
        if (!lifecycle) {
            enhance(frm);
            requestAnimationFrame(() => enhance(frm));
            setTimeout(() => enhance(frm), 180);
            return;
        }
        lifecycle.schedule(
            frm,
            "measurement-resilience",
            () => enhance(frm),
            { delays: [180] }
        );
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        pieces_add(frm) { schedule(frm); },
        pieces_remove(frm) { schedule(frm); },
    });

    const measurementLifecycle = window.AlmdinaMeasurementLifecycle;
    if (measurementLifecycle && typeof measurementLifecycle.registerFeature === "function") {
        measurementLifecycle.registerFeature("measurement-resilience", enhance);
    }
})();
