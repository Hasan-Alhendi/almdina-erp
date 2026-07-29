(() => {
    "use strict";

    const base = window.AlmdinaShapePrint;
    if (!base || window.AlmdinaReadableShapePrintInstalled) return;
    window.AlmdinaReadableShapePrintInstalled = true;

    function esc(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function clampFontSize(value) {
        const parsed = Number(value || 0);
        if (!Number.isFinite(parsed)) return 24;
        return Math.max(24, Math.min(38, parsed));
    }

    function displayText(value) {
        const text = String(value || "");
        return text.length > 34 ? `${text.slice(0, 33)}…` : text;
    }

    function fallbackEnhance(markup) {
        return String(markup || "")
            .replace(/<rect[^>]*fill="#fff8c9"[^>]*\/>/g, "")
            .replace(
                /font-size="16" font-weight="700" fill="#4c421a"/g,
                'font-size="24" font-weight="800" fill="#172033" paint-order="stroke" stroke="#fff" stroke-width="2.4" stroke-linejoin="round"'
            );
    }

    function enhanceSvg(piece, options = {}) {
        const markup = base.svg(piece, options);
        const payload = base.drawingPayload(piece);
        if (!markup || !payload || typeof DOMParser === "undefined" || typeof XMLSerializer === "undefined") {
            return fallbackEnhance(markup);
        }

        try {
            const documentNode = new DOMParser().parseFromString(markup, "image/svg+xml");
            if (documentNode.querySelector("parsererror")) return fallbackEnhance(markup);
            const notes = (payload.elements || []).filter(element => element && element.type === "note");
            const textNodes = [...documentNode.querySelectorAll("text")];

            notes.forEach(note => {
                const expected = displayText(note.text);
                const textNode = textNodes.find(node => node.textContent === expected && !node.dataset.dcoReadableNote);
                if (!textNode) return;
                textNode.dataset.dcoReadableNote = "1";
                textNode.setAttribute("font-size", String(clampFontSize(note.font_size || note.fontSize || 24)));
                textNode.setAttribute("font-weight", "800");
                textNode.setAttribute("fill", /^#[0-9a-f]{3,8}$/i.test(String(note.color || "")) ? note.color : "#172033");
                textNode.setAttribute("paint-order", "stroke");
                textNode.setAttribute("stroke", "#fff");
                textNode.setAttribute("stroke-width", "2.4");
                textNode.setAttribute("stroke-linejoin", "round");
                textNode.setAttribute("direction", "rtl");
                textNode.setAttribute("unicode-bidi", "plaintext");
                textNode.setAttribute("text-anchor", note.text_anchor === "middle" ? "middle" : "end");
                const group = textNode.parentElement;
                if (group) {
                    group.querySelectorAll('rect[fill="#fff8c9"]').forEach(rect => rect.remove());
                }
            });

            return new XMLSerializer().serializeToString(documentNode.documentElement);
        } catch (error) {
            console.warn("Could not enhance printed drawing notes", error);
            return fallbackEnhance(markup);
        }
    }

    function notesCell(piece, notes, options = {}) {
        const drawing = enhanceSvg(piece, options);
        const text = String(notes || "").trim();
        if (!drawing) return esc(text || "—");
        return `<div class="dco-piece-notes">
            ${text ? `<div class="dco-piece-notes-text">${esc(text)}</div>` : ""}
            <figure class="dco-piece-sketch">
                ${drawing}
                <figcaption>${esc(options.caption || "رسمة الدرفة")}</figcaption>
            </figure>
        </div>`;
    }

    const css = `${base.css || ""}
        .dco-piece-sketch svg text[data-dco-readable-note="1"]{font-family:Tahoma,"Segoe UI",Arial,sans-serif!important}
    `;

    window.AlmdinaShapePrint = Object.freeze({
        ...base,
        svg: enhanceSvg,
        notesCell,
        css,
    });
})();
