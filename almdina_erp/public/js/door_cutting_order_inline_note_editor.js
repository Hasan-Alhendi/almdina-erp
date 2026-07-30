(() => {
    "use strict";

    const DEFAULT_FONT_SIZE = 18;
    const FONT_SIZES = Object.freeze([12, 14, 16, 18, 20, 24, 28, 32]);
    const STYLE_ID = "dco-inline-note-editor-css";

    function clampFontSize(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return DEFAULT_FONT_SIZE;
        return Math.max(
            FONT_SIZES[0],
            Math.min(FONT_SIZES[FONT_SIZES.length - 1], Math.round(numeric))
        );
    }

    function controlsHtml() {
        return `
            <div class="dco-note-font-controls" aria-hidden="true">
                <div class="dco-note-font-label">
                    <span>حجم خط الملاحظة</span>
                    <b class="dco-note-font-value">${DEFAULT_FONT_SIZE} px</b>
                </div>
                <select class="dco-note-font-size" aria-label="حجم خط الملاحظة">
                    ${FONT_SIZES.map(size => `<option value="${size}">${size} px</option>`).join("")}
                </select>
            </div>`;
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-note-font-controls{display:none;padding:8px;border:1px solid var(--border-color,#dce2e7);border-radius:10px;background:var(--subtle-fg,#f7f9fa)}
            .dco-note-font-controls.is-visible{display:block}
            .dco-note-font-label{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px;font-size:10px;font-weight:900}
            .dco-note-font-label b{color:var(--primary,#1674c5);font-variant-numeric:tabular-nums}
            .dco-note-font-size{width:100%;min-height:34px;border:1px solid var(--border-color,#d4dbe1);border-radius:8px;background:var(--card-bg,#fff);padding:4px 8px;font-weight:800;cursor:pointer}
            .dco-canvas-text-editor{position:absolute;z-index:45;display:inline-block;min-width:1ch;max-width:min(460px,78%);min-height:1.35em;padding:0;margin:0;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;outline:0!important;color:var(--text-color,#172033);font-family:Tahoma,Arial,sans-serif;font-weight:700;line-height:1.35;direction:rtl;text-align:right;white-space:pre;overflow:visible;caret-color:var(--primary,#1674c5);transform:translate(-100%,-50%);transform-origin:right center;user-select:text}
            .dco-canvas-text-editor:focus{border:0!important;background:transparent!important;box-shadow:none!important;outline:0!important}
            @media(max-width:700px){.dco-note-font-controls{min-width:145px}.dco-canvas-text-editor{max-width:70%}}
        `;
        document.head.appendChild(style);
    }

    function canvasPointToClient(svg, point, canvas) {
        try {
            const matrix = svg.getScreenCTM && svg.getScreenCTM();
            if (matrix && svg.createSVGPoint) {
                const svgPoint = svg.createSVGPoint();
                svgPoint.x = Number(point.x);
                svgPoint.y = Number(point.y);
                const transformed = svgPoint.matrixTransform(matrix);
                return { clientX: transformed.x, clientY: transformed.y };
            }
        } catch (error) {
            // Fall through while the SVG is resizing or its matrix is unavailable.
        }
        const rect = svg.getBoundingClientRect();
        const viewBox = svg.viewBox && svg.viewBox.baseVal
            ? svg.viewBox.baseVal
            : { x: 0, y: 0, width: canvas.width, height: canvas.height };
        return {
            clientX: rect.left + (Number(point.x) - viewBox.x) * rect.width / Math.max(1, viewBox.width),
            clientY: rect.top + (Number(point.y) - viewBox.y) * rect.height / Math.max(1, viewBox.height),
        };
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

    function insertPlainTextAtCaret(text) {
        const selection = window.getSelection && window.getSelection();
        if (!selection || !selection.rangeCount) return;
        const range = selection.getRangeAt(0);
        range.deleteContents();
        const textNode = document.createTextNode(text);
        range.insertNode(textNode);
        range.setStartAfter(textNode);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
    }

    function open({
        root,
        svg,
        point,
        text = "",
        fontSize = DEFAULT_FONT_SIZE,
        color = "#172033",
        canvas = { width: 1000, height: 650 },
        onCommit,
        onClose,
    }) {
        const wrap = root && root.querySelector(".dco-sketch-paper-wrap");
        if (!wrap || !svg) return null;
        wrap.querySelectorAll(".dco-canvas-text-editor").forEach(node => node.remove());

        const clientPoint = canvasPointToClient(svg, point, canvas);
        const wrapRect = wrap.getBoundingClientRect();
        const left = Math.max(8, Math.min(wrapRect.width - 8, clientPoint.clientX - wrapRect.left));
        const top = Math.max(8, Math.min(wrapRect.height - 8, clientPoint.clientY - wrapRect.top));
        const normalizedSize = clampFontSize(fontSize);
        const scale = Math.max(
            0.55,
            svg.clientWidth / Math.max(1, svg.viewBox.baseVal.width || canvas.width)
        );
        const editor = document.createElement("span");
        editor.className = "dco-canvas-text-editor";
        editor.contentEditable = "true";
        editor.setAttribute("role", "textbox");
        editor.setAttribute("aria-label", "اكتب الملاحظة مباشرة على الرسم");
        editor.setAttribute("dir", "rtl");
        editor.spellcheck = false;
        editor.textContent = String(text || "");
        editor.style.left = `${left}px`;
        editor.style.top = `${top}px`;
        editor.style.fontSize = `${Math.max(12, Math.min(34, normalizedSize * scale))}px`;
        editor.style.color = color;
        wrap.appendChild(editor);

        let finished = false;
        const finish = commit => {
            if (finished) return;
            finished = true;
            const value = String(editor.textContent || "").replace(/\u00a0/g, " ").trim();
            editor.remove();
            if (commit && value && typeof onCommit === "function") onCommit(value);
            if (typeof onClose === "function") onClose();
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
            insertPlainTextAtCaret(
                String(clipboard.getData("text") || "").replace(/[\r\n]+/g, " ")
            );
        });
        editor.addEventListener("blur", () => finish(true), { once: true });
        const requestFrame = window.requestAnimationFrame || (callback => window.setTimeout(callback, 0));
        requestFrame(() => {
            editor.focus({ preventScroll: true });
            placeCaretAtEnd(editor);
        });
        return editor;
    }

    window.AlmdinaInlineNoteEditor = Object.freeze({
        DEFAULT_FONT_SIZE,
        FONT_SIZES,
        clampFontSize,
        controlsHtml,
        installStyles,
        open,
    });
})();
