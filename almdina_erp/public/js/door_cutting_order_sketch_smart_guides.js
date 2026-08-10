(() => {
    "use strict";

    const renderer = window.AlmdinaSketchRenderer;
    const engine = window.AlmdinaSketchEngine;
    if (!renderer || !engine) {
        console.error("Sketch renderer and engine must load before smart guides");
        return;
    }

    const GUIDE_COLOR = "#2490ef";

    function inferredAxis(state) {
        const draft = state && state.draft;
        if (!draft || !["line", "dimension"].includes(draft.type)) return "";
        const x1 = Number(draft.x1);
        const y1 = Number(draft.y1);
        const x2 = Number(draft.x2);
        const y2 = Number(draft.y2);
        if (![x1, y1, x2, y2].every(Number.isFinite)) return "";
        if (Math.abs(y1 - y2) <= 0.001 && Math.abs(x1 - x2) > 0.001) return "horizontal";
        if (Math.abs(x1 - x2) <= 0.001 && Math.abs(y1 - y2) > 0.001) return "vertical";
        return "";
    }

    function guideMarkup(state, options = {}) {
        const axis = inferredAxis(state);
        if (!axis) return "";
        const width = Number(options.width) > 0 ? Number(options.width) : engine.DEFAULT_CANVAS.width;
        const height = Number(options.height) > 0 ? Number(options.height) : engine.DEFAULT_CANVAS.height;
        const draft = state.draft;
        if (axis === "horizontal") {
            const y = Number(draft.y1);
            return `<g class="dco-smart-axis-guide" pointer-events="none">
                <line x1="0" y1="${y}" x2="${width}" y2="${y}" stroke="${GUIDE_COLOR}" stroke-width="1.5" stroke-dasharray="7 7" opacity=".72" vector-effect="non-scaling-stroke"/>
                <rect x="${Math.max(8, Math.min(width - 80, Number(draft.x2) + 12))}" y="${Math.max(8, y - 28)}" width="64" height="20" rx="7" fill="${GUIDE_COLOR}" opacity=".92"/>
                <text x="${Math.max(40, Math.min(width - 48, Number(draft.x2) + 44))}" y="${Math.max(22, y - 14)}" text-anchor="middle" font-family="Tahoma,Arial" font-size="11" font-weight="700" fill="#fff">أفقي</text>
            </g>`;
        }
        const x = Number(draft.x1);
        return `<g class="dco-smart-axis-guide" pointer-events="none">
            <line x1="${x}" y1="0" x2="${x}" y2="${height}" stroke="${GUIDE_COLOR}" stroke-width="1.5" stroke-dasharray="7 7" opacity=".72" vector-effect="non-scaling-stroke"/>
            <rect x="${Math.max(8, Math.min(width - 72, x + 12))}" y="${Math.max(8, Math.min(height - 28, Number(draft.y2) + 12))}" width="56" height="20" rx="7" fill="${GUIDE_COLOR}" opacity=".92"/>
            <text x="${Math.max(36, Math.min(width - 44, x + 40))}" y="${Math.max(22, Math.min(height - 14, Number(draft.y2) + 26))}" text-anchor="middle" font-family="Tahoma,Arial" font-size="11" font-weight="700" fill="#fff">عمودي</text>
        </g>`;
    }

    function injectBeforeCursor(markup, guides) {
        if (!guides) return markup;
        const marker = '<g class="dco-sketch-cursor-preview"';
        const index = String(markup || "").indexOf(marker);
        if (index < 0) return `${markup || ""}${guides}`;
        return `${markup.slice(0, index)}${guides}${markup.slice(index)}`;
    }

    const baseCanvasView = renderer.canvasView;
    window.AlmdinaSketchRenderer = Object.freeze({
        ...renderer,
        canvasView(state, options = {}) {
            const result = baseCanvasView(state, options);
            return {
                ...result,
                markup: injectBeforeCursor(result.markup, guideMarkup(state, options)),
            };
        },
        smartGuideMarkup: guideMarkup,
        inferredAxis,
    });
})();