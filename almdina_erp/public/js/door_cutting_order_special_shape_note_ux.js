(() => {
    "use strict";

    const STYLE_ID = "dco-special-shape-inline-note-css";
    const DEFAULT_FONT_SIZE = 18;
    const FONT_SIZES = [12, 14, 16, 18, 20, 24, 28, 32];
    const NOTE_TITLES = new Set(["إضافة ملاحظة", "تعديل الملاحظة"]);
    let activeSession = null;

    function esc(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function clampFontSize(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return DEFAULT_FONT_SIZE;
        return Math.max(FONT_SIZES[0], Math.min(FONT_SIZES[FONT_SIZES.length - 1], Math.round(numeric)));
    }

    function parsePayload(row) {
        try {
            const raw = row && row.special_shape_drawing_json;
            const payload = typeof raw === "string" ? JSON.parse(raw || "{}") : (raw || {});
            return payload && Number(payload.version) === 1 && Array.isArray(payload.elements)
                ? payload
                : { version: 1, elements: [] };
        } catch (error) {
            return { version: 1, elements: [] };
        }
    }

    function noteMapFromRow(row) {
        const notes = new Map();
        parsePayload(row).elements.forEach(element => {
            if (!element || element.type !== "note" || !element.id) return;
            notes.set(String(element.id), {
                text: String(element.text || ""),
                color: String(element.color || "#172033"),
                x: Number(element.x) || 0,
                y: Number(element.y) || 0,
                fontSize: clampFontSize(element.font_size || element.fontSize || 16),
            });
        });
        return notes;
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-special-shape-modal .dco-sketch-note-bg{display:none!important;fill:none!important;stroke:none!important}
            .dco-special-shape-modal .dco-note-font-controls{display:none;padding:8px;border:1px solid var(--border-color,#dce2e7);border-radius:10px;background:var(--subtle-fg,#f7f9fa)}
            .dco-special-shape-modal .dco-note-font-controls.is-visible{display:block}
            .dco-special-shape-modal .dco-note-font-label{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px;font-size:10px;font-weight:900}
            .dco-special-shape-modal .dco-note-font-label b{color:var(--primary,#1674c5);font-variant-numeric:tabular-nums}
            .dco-special-shape-modal .dco-note-font-size{width:100%;min-height:34px;border:1px solid var(--border-color,#d4dbe1);border-radius:8px;background:var(--card-bg,#fff);padding:4px 8px;font-weight:800;cursor:pointer}
            .dco-special-shape-modal .dco-inline-note-editor{position:absolute;z-index:40;min-width:190px;max-width:min(420px,75%);height:38px;padding:4px 2px;border:0;border-bottom:2px solid var(--primary,#2490ef);border-radius:0;background:transparent!important;box-shadow:none!important;color:var(--text-color,#172033);font-family:Tahoma,Arial,sans-serif;font-weight:700;line-height:1.35;direction:rtl;text-align:center;outline:0;transform:translate(-50%,-50%)}
            .dco-special-shape-modal .dco-inline-note-editor::placeholder{color:#72808c;font-weight:500}
            .dco-special-shape-modal .dco-inline-note-help{position:absolute;z-index:41;transform:translate(-50%,10px);padding:4px 7px;border-radius:7px;background:rgba(23,32,51,.82);color:#fff;font-size:9px;white-space:nowrap;pointer-events:none}
            .dco-special-shape-modal .dco-note-font-unsaved{color:#8a5a12!important;background:#fff3d6!important}
            @media(max-width:700px){.dco-special-shape-modal .dco-note-font-controls{min-width:150px}.dco-special-shape-modal .dco-inline-note-editor{min-width:150px;max-width:68%}}
        `;
        document.head.appendChild(style);
    }

    function visibleSpecialModal() {
        const modals = [...document.querySelectorAll(".dco-special-shape-modal")];
        return modals.reverse().find(modal => {
            const style = window.getComputedStyle(modal);
            return style.display !== "none" && style.visibility !== "hidden";
        }) || null;
    }

    function selectedElementId(session) {
        const selected = session.svg && session.svg.querySelector(".dco-sketch-element.is-selected[data-element-id]");
        return selected ? String(selected.getAttribute("data-element-id") || "") : "";
    }

    function selectedNoteId(session) {
        const id = selectedElementId(session);
        return id && session.notes.has(id) ? id : "";
    }

    function activeNoteTool(session) {
        return Boolean(session.svg && session.svg.dataset.tool === "note");
    }

    function syncFontControl(session) {
        if (!session.controls) return;
        const selectedId = selectedNoteId(session);
        const selected = selectedId ? session.notes.get(selectedId) : null;
        if (selected) session.fontSize = selected.fontSize;
        session.controls.classList.toggle("is-visible", activeNoteTool(session) || Boolean(selected));
        const select = session.controls.querySelector(".dco-note-font-size");
        const value = session.controls.querySelector(".dco-note-font-value");
        if (select) select.value = String(clampFontSize(session.fontSize));
        if (value) value.textContent = `${clampFontSize(session.fontSize)} px`;
    }

    function applyNotePresentation(session) {
        if (!session.svg) return;
        session.svg.querySelectorAll("[data-element-id]").forEach(group => {
            const id = group.getAttribute("data-element-id") || "";
            const note = session.notes.get(id);
            if (!note) return;
            group.querySelectorAll(".dco-sketch-note-bg,rect").forEach(rect => rect.remove());
            const text = group.querySelector("text");
            if (!text) return;
            text.textContent = note.text;
            text.setAttribute("x", String(note.x));
            text.setAttribute("y", String(note.y));
            text.setAttribute("text-anchor", "middle");
            text.setAttribute("dominant-baseline", "middle");
            text.setAttribute("direction", "rtl");
            text.setAttribute("unicode-bidi", "plaintext");
            text.setAttribute("font-size", String(note.fontSize));
            text.setAttribute("font-weight", "700");
            text.setAttribute("fill", note.color || "#172033");
            text.removeAttribute("stroke");
            text.style.pointerEvents = "all";
        });
        syncFontControl(session);
    }

    function schedulePresentation(session) {
        if (session.presentationFrame) return;
        session.presentationFrame = window.requestAnimationFrame(() => {
            session.presentationFrame = null;
            applyNotePresentation(session);
        });
    }

    function markFontDirty(session) {
        session.fontDirty = true;
        const saveState = session.root.querySelector(".dco-sketch-save-state");
        if (saveState && !saveState.classList.contains("is-dirty")) {
            saveState.classList.add("dco-note-font-unsaved");
            saveState.textContent = "● حجم خط الملاحظة غير محفوظ";
        }
    }

    function installFontControls(session) {
        const toolbar = session.root.querySelector(".dco-sketch-toolbar");
        if (!toolbar || toolbar.querySelector(".dco-note-font-controls")) return;
        const controls = document.createElement("div");
        controls.className = "dco-note-font-controls";
        controls.innerHTML = `
            <div class="dco-note-font-label"><span>حجم خط الملاحظة</span><b class="dco-note-font-value">${DEFAULT_FONT_SIZE} px</b></div>
            <select class="dco-note-font-size" aria-label="حجم خط الملاحظة">
                ${FONT_SIZES.map(size => `<option value="${size}">${size} px</option>`).join("")}
            </select>`;
        const colors = toolbar.querySelector(".dco-sketch-colors");
        if (colors && colors.parentNode) colors.parentNode.insertBefore(controls, colors.nextSibling);
        else toolbar.appendChild(controls);
        session.controls = controls;
        const select = controls.querySelector(".dco-note-font-size");
        select.value = String(session.fontSize);
        select.addEventListener("change", () => {
            session.fontSize = clampFontSize(select.value);
            const selectedId = selectedNoteId(session);
            if (selectedId) {
                const note = session.notes.get(selectedId);
                note.fontSize = session.fontSize;
                markFontDirty(session);
                applyNotePresentation(session);
            } else {
                syncFontControl(session);
            }
        });
    }

    function noteEditorPoint(session, editingExisting) {
        if (editingExisting) {
            const selected = session.svg.querySelector(".dco-sketch-element.is-selected text");
            if (selected) {
                const rect = selected.getBoundingClientRect();
                return { clientX: rect.left + rect.width / 2, clientY: rect.top + rect.height / 2 };
            }
        }
        return session.lastPointer || {
            clientX: session.svg.getBoundingClientRect().left + session.svg.clientWidth / 2,
            clientY: session.svg.getBoundingClientRect().top + session.svg.clientHeight / 2,
        };
    }

    function canvasPoint(session, clientPoint) {
        const editor = window.AlmdinaSpecialShapeEditor;
        if (editor && typeof editor.clientPointToCanvas === "function") {
            return editor.clientPointToCanvas(session.svg, clientPoint.clientX, clientPoint.clientY);
        }
        return { x: 0, y: 0 };
    }

    function openInlineEditor(session, defaultValue, callback, editingExisting) {
        const wrap = session.root.querySelector(".dco-sketch-paper-wrap");
        if (!wrap || !session.svg) return null;
        wrap.querySelectorAll(".dco-inline-note-editor,.dco-inline-note-help").forEach(node => node.remove());

        const location = noteEditorPoint(session, editingExisting);
        const wrapRect = wrap.getBoundingClientRect();
        const left = Math.max(20, Math.min(wrapRect.width - 20, location.clientX - wrapRect.left));
        const top = Math.max(20, Math.min(wrapRect.height - 20, location.clientY - wrapRect.top));
        const input = document.createElement("input");
        input.type = "text";
        input.className = "dco-inline-note-editor";
        input.value = String(defaultValue || "");
        input.placeholder = "اكتب الملاحظة هنا";
        input.maxLength = 500;
        input.style.left = `${left}px`;
        input.style.top = `${top}px`;
        const scale = Math.max(0.55, session.svg.clientWidth / Math.max(1, session.svg.viewBox.baseVal.width || 1000));
        input.style.fontSize = `${Math.max(12, Math.min(34, session.fontSize * scale))}px`;

        const help = document.createElement("div");
        help.className = "dco-inline-note-help";
        help.textContent = "Enter للحفظ · Esc للإلغاء";
        help.style.left = `${left}px`;
        help.style.top = `${top + 20}px`;
        wrap.append(input, help);

        const existingId = editingExisting ? selectedNoteId(session) : "";
        const point = canvasPoint(session, location);
        let finished = false;
        const finish = commit => {
            if (finished) return;
            finished = true;
            const text = String(input.value || "").trim();
            input.remove();
            help.remove();
            if (!commit || !text) return;
            callback(text);
            window.requestAnimationFrame(() => {
                const id = existingId || selectedElementId(session);
                if (!id) return;
                const previous = session.notes.get(id) || {};
                const group = [...session.svg.querySelectorAll("[data-element-id]")]
                    .find(node => String(node.getAttribute("data-element-id") || "") === id);
                const selectedText = group && group.querySelector("text");
                const color = selectedText ? selectedText.getAttribute("fill") : previous.color;
                session.notes.set(id, {
                    text,
                    color: color && color !== "#4c421a" ? color : (previous.color || session.color || "#172033"),
                    x: editingExisting ? Number(previous.x || point.x) : point.x,
                    y: editingExisting ? Number(previous.y || point.y) : point.y,
                    fontSize: editingExisting ? clampFontSize(previous.fontSize || session.fontSize) : session.fontSize,
                });
                markFontDirty(session);
                applyNotePresentation(session);
            });
        };
        input.addEventListener("keydown", event => {
            if (event.key === "Enter") {
                event.preventDefault();
                finish(true);
            } else if (event.key === "Escape") {
                event.preventDefault();
                finish(false);
            }
        });
        input.addEventListener("blur", () => window.setTimeout(() => finish(true), 0), { once: true });
        window.requestAnimationFrame(() => {
            input.focus({ preventScroll: true });
            input.select();
        });
        return input;
    }

    function installPromptBridge() {
        if (frappe._dcoSpecialShapeOriginalPrompt) return;
        frappe._dcoSpecialShapeOriginalPrompt = frappe.prompt.bind(frappe);
        frappe.prompt = function dcoSpecialShapePrompt(fields, callback, title, actionLabel) {
            const session = activeSession;
            const normalizedTitle = String(title || "").trim();
            if (
                session
                && session.modal.isConnected
                && !session.readOnly
                && NOTE_TITLES.has(normalizedTitle)
            ) {
                const field = Array.isArray(fields) ? fields[0] : null;
                const defaultValue = field && field.default ? String(field.default) : "";
                const editingExisting = normalizedTitle === "تعديل الملاحظة";
                return openInlineEditor(session, defaultValue, callback, editingExisting);
            }
            return frappe._dcoSpecialShapeOriginalPrompt(fields, callback, title, actionLabel);
        };
    }

    function patchRowPayload(session) {
        const payload = parsePayload(session.row);
        let changed = false;
        payload.elements.forEach(element => {
            if (!element || element.type !== "note" || !element.id) return;
            const note = session.notes.get(String(element.id));
            if (!note) return;
            const size = clampFontSize(note.fontSize);
            if (Number(element.font_size) !== size) {
                element.font_size = size;
                changed = true;
            }
        });
        if (!changed && !session.fontDirty) return;
        session.row.special_shape_drawing_json = JSON.stringify(payload);
        session.frm.dirty();
        session.fontDirty = false;
    }

    function patchPrintedSvg(piece, markup) {
        if (!markup || typeof DOMParser === "undefined") return markup;
        const payload = parsePayload(piece);
        const notes = payload.elements.filter(element => element && element.type === "note");
        if (!notes.length) return markup;
        try {
            const doc = new DOMParser().parseFromString(markup, "image/svg+xml");
            const groups = [...doc.querySelectorAll("g")].filter(group =>
                group.querySelector('rect[fill="#fff8c9"],rect[stroke="#b9a34f"]')
            );
            groups.forEach((group, index) => {
                const note = notes[index];
                if (!note) return;
                group.querySelectorAll("rect").forEach(rect => rect.remove());
                const text = group.querySelector("text");
                if (!text) return;
                text.textContent = String(note.text || "");
                text.setAttribute("x", String(Number(note.x) || 0));
                text.setAttribute("y", String(Number(note.y) || 0));
                text.setAttribute("text-anchor", "middle");
                text.setAttribute("dominant-baseline", "middle");
                text.setAttribute("direction", "rtl");
                text.setAttribute("unicode-bidi", "plaintext");
                text.setAttribute("font-size", String(clampFontSize(note.font_size || 16)));
                text.setAttribute("fill", String(note.color || "#172033"));
            });
            return new XMLSerializer().serializeToString(doc.documentElement);
        } catch (error) {
            console.warn("Unable to apply transparent note print styling", error);
            return markup;
        }
    }

    function installPrintBridge() {
        const original = window.AlmdinaShapePrint;
        if (!original || original._inlineNotePatched) return;
        const patchedSvg = (piece, options = {}) => patchPrintedSvg(piece, original.svg(piece, options));
        const patchedNotesCell = (piece, notes, options = {}) => {
            const drawing = patchedSvg(piece, options);
            const text = String(notes || "").trim();
            if (!drawing) return esc(text || "—");
            return `<div class="dco-piece-notes">
                ${text ? `<div class="dco-piece-notes-text">${esc(text)}</div>` : ""}
                <figure class="dco-piece-sketch">
                    ${drawing}
                    <figcaption>${esc(options.caption || "رسمة الدرفة")}</figcaption>
                </figure>
            </div>`;
        };
        window.AlmdinaShapePrint = Object.freeze({
            ...original,
            _inlineNotePatched: true,
            svg: patchedSvg,
            notesCell: patchedNotesCell,
        });
    }

    function enhanceSession(frm, row, options) {
        const modal = visibleSpecialModal();
        const root = modal && modal.querySelector(".dco-special-sketch-shell");
        const svg = root && root.querySelector(".dco-sketch-paper");
        if (!modal || !root || !svg || modal.dataset.dcoInlineNoteEnhanced === "1") return;
        modal.dataset.dcoInlineNoteEnhanced = "1";
        const session = {
            frm,
            row,
            options: options || {},
            readOnly: Boolean(options && options.readOnly),
            modal,
            root,
            svg,
            notes: noteMapFromRow(row),
            fontSize: DEFAULT_FONT_SIZE,
            fontDirty: false,
            saving: false,
            lastPointer: null,
            presentationFrame: null,
            controls: null,
            observer: null,
        };
        activeSession = session;
        installFontControls(session);
        applyNotePresentation(session);

        svg.addEventListener("pointerdown", event => {
            if (svg.dataset.tool !== "note") return;
            session.lastPointer = { clientX: event.clientX, clientY: event.clientY };
            session.color = root.querySelector(".dco-sketch-color.is-active")?.dataset.color || "#172033";
        }, true);

        session.observer = new MutationObserver(() => schedulePresentation(session));
        session.observer.observe(root, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ["class", "data-tool"],
        });

        modal.addEventListener("click", event => {
            if (event.target.closest(".modal-footer .btn-primary")) session.saving = true;
        }, true);

        if (window.jQuery) {
            window.jQuery(modal).on("hide.bs.modal.dco-inline-note", event => {
                if (session.saving) {
                    patchRowPayload(session);
                    return;
                }
                const internalDirty = Boolean(root.querySelector(".dco-sketch-save-state.is-dirty"));
                if (!session.fontDirty || internalDirty || session.allowFontClose) return;
                event.preventDefault();
                frappe.confirm(
                    "غيّرت حجم خط الملاحظة ولم تحفظ الرسم. هل تريد الإغلاق وفقدان التعديل؟",
                    () => {
                        session.allowFontClose = true;
                        window.jQuery(modal).modal("hide");
                    }
                );
            });
            window.jQuery(modal).one("hidden.bs.modal.dco-inline-note", () => {
                if (session.observer) session.observer.disconnect();
                if (session.presentationFrame) window.cancelAnimationFrame(session.presentationFrame);
                if (activeSession === session) activeSession = null;
            });
        }
    }

    function installEditorBridge() {
        const editor = window.AlmdinaSpecialShapeEditor;
        if (!editor || editor._inlineNotePatched) return;
        const originalOpen = editor.open.bind(editor);
        editor.open = function openWithInlineNotes(frm, row, options = {}) {
            const result = originalOpen(frm, row, options);
            window.setTimeout(() => enhanceSession(frm, row, options), 0);
            window.requestAnimationFrame(() => enhanceSession(frm, row, options));
            return result;
        };
        editor.view = function viewWithInlineNotes(frm, row) {
            return editor.open(frm, row, { readOnly: true });
        };
        editor._inlineNotePatched = true;
    }

    installStyles();
    installPromptBridge();
    installPrintBridge();
    installEditorBridge();
})();
