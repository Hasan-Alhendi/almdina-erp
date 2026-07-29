(() => {
    "use strict";

    const STYLE_ID = "dco-special-shape-note-guard-css";
    const NOTE_WORDS = ["ملاحظة", "note"];
    const MODAL_SELECTOR = ".dco-special-shape-modal";
    const CANVAS_SELECTOR = ".dco-sketch-paper";
    const EDITOR_CLASS = "dco-point-text-editor";
    let lastPointer = null;
    let fallbackPrompt = null;

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            ${MODAL_SELECTOR} .${EDITOR_CLASS}{
                position:absolute;
                z-index:90;
                display:inline-block;
                min-width:1ch;
                max-width:min(480px,78%);
                min-height:1.35em;
                padding:0;
                margin:0;
                border:0!important;
                border-radius:0!important;
                background:transparent!important;
                box-shadow:none!important;
                outline:0!important;
                color:var(--text-color,#172033);
                font-family:Tahoma,Arial,sans-serif;
                font-weight:700;
                line-height:1.35;
                direction:rtl;
                text-align:right;
                white-space:pre;
                overflow:visible;
                caret-color:var(--primary,#1674c5);
                transform:translate(-100%,-50%);
                transform-origin:right center;
                user-select:text;
            }
            ${MODAL_SELECTOR} .${EDITOR_CLASS}:focus{
                border:0!important;
                background:transparent!important;
                box-shadow:none!important;
                outline:0!important;
            }
        `;
        document.head.appendChild(style);
    }

    function visibleModal() {
        const modals = [...document.querySelectorAll(MODAL_SELECTOR)];
        return modals.reverse().find(modal => {
            const style = window.getComputedStyle(modal);
            return style.display !== "none" && style.visibility !== "hidden";
        }) || null;
    }

    function activeContext() {
        const modal = visibleModal();
        const root = modal && modal.querySelector(".dco-special-sketch-shell");
        const svg = root && root.querySelector(CANVAS_SELECTOR);
        const wrap = root && root.querySelector(".dco-sketch-paper-wrap");
        if (!modal || !root || !svg || !wrap || svg.dataset.tool !== "note") return null;
        return { modal, root, svg, wrap };
    }

    function isNotePrompt(fields, title) {
        const field = Array.isArray(fields) ? fields[0] : null;
        const descriptor = [title, field && field.label, field && field.fieldname]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
        return NOTE_WORDS.some(word => descriptor.includes(word))
            || Boolean(field && field.fieldname === "text");
    }

    function pointForEditor(context) {
        const rect = context.svg.getBoundingClientRect();
        if (
            lastPointer
            && lastPointer.svg === context.svg
            && lastPointer.clientX >= rect.left
            && lastPointer.clientX <= rect.right
            && lastPointer.clientY >= rect.top
            && lastPointer.clientY <= rect.bottom
        ) {
            return lastPointer;
        }
        return {
            svg: context.svg,
            clientX: rect.left + rect.width / 2,
            clientY: rect.top + rect.height / 2,
        };
    }

    function selectedFontSize(context) {
        const control = context.root.querySelector(".dco-note-font-size");
        const value = Number(control && control.value);
        return Number.isFinite(value) ? Math.max(12, Math.min(32, value)) : 18;
    }

    function selectedColor(context) {
        const selected = context.root.querySelector(".dco-sketch-color.is-active");
        return selected && selected.dataset.color ? selected.dataset.color : "#172033";
    }

    function placeCaretAtEnd(element) {
        const selection = window.getSelection && window.getSelection();
        if (!selection || !document.createRange) return;
        const range = document.createRange();
        range.selectNodeContents(element);
        range.collapse(false);
        selection.removeAllRanges();
        selection.addRange(range);
    }

    function openPointTextEditor(context, fields, callback) {
        context.wrap.querySelectorAll(`.${EDITOR_CLASS}`).forEach(node => node.remove());

        const field = Array.isArray(fields) ? fields[0] : null;
        const point = pointForEditor(context);
        const wrapRect = context.wrap.getBoundingClientRect();
        const left = Math.max(8, Math.min(wrapRect.width - 8, point.clientX - wrapRect.left));
        const top = Math.max(8, Math.min(wrapRect.height - 8, point.clientY - wrapRect.top));
        const editor = document.createElement("span");
        editor.className = EDITOR_CLASS;
        editor.contentEditable = "true";
        editor.setAttribute("role", "textbox");
        editor.setAttribute("aria-label", "اكتب الملاحظة مباشرة على الرسم");
        editor.setAttribute("dir", "rtl");
        editor.spellcheck = false;
        editor.textContent = String((field && field.default) || "");
        editor.style.left = `${left}px`;
        editor.style.top = `${top}px`;
        editor.style.fontSize = `${selectedFontSize(context)}px`;
        editor.style.color = selectedColor(context);
        context.wrap.appendChild(editor);

        let finished = false;
        const finish = commit => {
            if (finished) return;
            finished = true;
            const text = String(editor.textContent || "").replace(/\u00a0/g, " ").trim();
            editor.remove();
            if (!commit || !text) return;
            callback({ text });
        };

        editor.addEventListener("keydown", event => {
            if (event.key === "Enter") {
                event.preventDefault();
                finish(true);
            } else if (event.key === "Escape") {
                event.preventDefault();
                finish(false);
            }
        });
        editor.addEventListener("paste", event => {
            const clipboard = event.clipboardData || window.clipboardData;
            if (!clipboard) return;
            event.preventDefault();
            const text = String(clipboard.getData("text") || "").replace(/[\r\n]+/g, " ");
            document.execCommand("insertText", false, text);
        });
        editor.addEventListener("blur", () => finish(true), { once: true });
        window.requestAnimationFrame(() => {
            editor.focus({ preventScroll: true });
            placeCaretAtEnd(editor);
        });
        return editor;
    }

    function guardedPrompt(fields, callback, title, actionLabel) {
        const context = activeContext();
        if (context && isNotePrompt(fields, title)) {
            return openPointTextEditor(context, fields, callback);
        }
        return fallbackPrompt(fields, callback, title, actionLabel);
    }

    function installPromptGuard() {
        if (!window.frappe || typeof frappe.prompt !== "function") return false;
        if (frappe.prompt === guardedPrompt) return true;
        fallbackPrompt = frappe.prompt.bind(frappe);
        try {
            const descriptor = Object.getOwnPropertyDescriptor(frappe, "prompt");
            Object.defineProperty(frappe, "prompt", {
                configurable: true,
                enumerable: descriptor ? descriptor.enumerable : true,
                get() {
                    return guardedPrompt;
                },
                set(candidate) {
                    if (typeof candidate === "function" && candidate !== guardedPrompt) {
                        fallbackPrompt = candidate.bind(frappe);
                    }
                },
            });
        } catch (error) {
            frappe.prompt = guardedPrompt;
        }
        return frappe.prompt === guardedPrompt;
    }

    document.addEventListener("pointerdown", event => {
        const svg = event.target && event.target.closest
            ? event.target.closest(`${MODAL_SELECTOR} ${CANVAS_SELECTOR}`)
            : null;
        if (!svg || svg.dataset.tool !== "note") return;
        lastPointer = {
            svg,
            clientX: Number(event.clientX),
            clientY: Number(event.clientY),
        };
        installPromptGuard();
    }, true);

    installStyles();
    installPromptGuard();

    window.AlmdinaSpecialShapeNoteGuard = Object.freeze({
        installPromptGuard,
        isNotePrompt,
    });
})();
