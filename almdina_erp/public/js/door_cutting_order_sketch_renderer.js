(() => {
    "use strict";

    const sketchEngine = window.AlmdinaSketchEngine;
    if (!sketchEngine) {
        console.error("AlmdinaSketchEngine must load before the sketch renderer");
        return;
    }

    const DEFAULT_CANVAS = sketchEngine.DEFAULT_CANVAS;

    function esc(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function escAttr(value) {
        return esc(value).replace(/`/g, "&#96;");
    }

    function canvasSize(options = {}) {
        return {
            width: Number(options.width) > 0
                ? Number(options.width)
                : DEFAULT_CANVAS.width,
            height: Number(options.height) > 0
                ? Number(options.height)
                : DEFAULT_CANVAS.height,
        };
    }

    function noteFontSize(value, resolver) {
        if (typeof resolver === "function") return resolver(value);
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return 18;
        return Math.max(12, Math.min(32, Math.round(numeric)));
    }

    function pathData(points) {
        return sketchEngine.sanitizePoints(points).map((point, index) =>
            `${index ? "L" : "M"} ${point[0].toFixed(1)} ${point[1].toFixed(1)}`
        ).join(" ");
    }

    function textPosition(element) {
        const x = (Number(element.x1) + Number(element.x2)) / 2;
        const y = (Number(element.y1) + Number(element.y2)) / 2;
        return { x, y: y - 12 };
    }

    function elementMarkup(element, options = {}) {
        if (!element || typeof element !== "object") return "";
        const color = escAttr(element.color || "#172033");
        const selectedClass = options.selected ? " is-selected" : "";
        const common = [
            `data-element-id="${escAttr(element.id)}"`,
            `class="dco-sketch-element${selectedClass}"`,
            `opacity="${options.draft ? ".62" : "1"}"`,
        ].join(" ");

        if (element.type === "pen") {
            const points = options.draft
                ? sketchEngine.normalizePenStroke(element.points)
                : element.points;
            return `<path ${common} d="${pathData(points)}" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`;
        }
        if (element.type === "line") {
            return `<line ${common} x1="${Number(element.x1)}" y1="${Number(element.y1)}" x2="${Number(element.x2)}" y2="${Number(element.y2)}" stroke="${color}" stroke-width="4" stroke-linecap="round"/>`;
        }
        if (element.type === "rectangle") {
            return `<rect ${common} x="${Number(element.x)}" y="${Number(element.y)}" width="${Number(element.width)}" height="${Number(element.height)}" rx="2" fill="none" stroke="${color}" stroke-width="4"/>`;
        }
        if (element.type === "ellipse") {
            return `<ellipse ${common} cx="${Number(element.cx)}" cy="${Number(element.cy)}" rx="${Number(element.rx)}" ry="${Number(element.ry)}" fill="none" stroke="${color}" stroke-width="4"/>`;
        }
        if (element.type === "dimension") {
            const position = textPosition(element);
            const text = String(element.text || "");
            const halfWidth = Math.max(34, text.length * 7);
            return `<g ${common}>
                <line x1="${Number(element.x1)}" y1="${Number(element.y1)}" x2="${Number(element.x2)}" y2="${Number(element.y2)}" stroke="${color}" stroke-width="2.5" marker-start="url(#dco-arrow-start)" marker-end="url(#dco-arrow-end)"/>
                <rect x="${position.x - halfWidth}" y="${position.y - 18}" width="${halfWidth * 2}" height="27" rx="6" fill="#fff" stroke="${color}" stroke-width="1.2"/>
                <text x="${position.x}" y="${position.y + 1}" text-anchor="middle" font-family="Tahoma,Arial" font-size="17" font-weight="700" fill="${color}">${esc(text)}</text>
            </g>`;
        }
        if (element.type === "note") {
            const text = String(element.text || "");
            const displayText = text.length > 34 ? `${text.slice(0, 33)}…` : text;
            const fontSize = noteFontSize(
                element.font_size || element.fontSize,
                options.noteFontSize
            );
            const textAnchor = element.text_anchor === "middle" ? "middle" : "end";
            return `<g ${common}>
                <text x="${Number(element.x)}" y="${Number(element.y)}" text-anchor="${textAnchor}" dominant-baseline="middle" direction="rtl" unicode-bidi="plaintext" font-family="Tahoma,Arial,sans-serif" font-size="${fontSize}" font-weight="700" fill="${color}">${esc(displayText)}</text>
            </g>`;
        }
        return "";
    }

    function selectionMarkup(state, options = {}) {
        if (!state || state.tool !== "select") return "";
        const element = (state.elements || []).find(
            item => item.id === state.selectedId
        );
        const canvas = canvasSize(options);
        const bounds = sketchEngine.elementBounds(element, {
            noteFontSize: options.noteFontSize,
        });
        if (!bounds) return "";

        const padding = 9;
        const x = Math.max(0, bounds.x - padding);
        const y = Math.max(0, bounds.y - padding);
        const width = Math.max(
            18,
            Math.min(canvas.width - x, bounds.width + padding * 2)
        );
        const height = Math.max(
            18,
            Math.min(canvas.height - y, bounds.height + padding * 2)
        );
        const handles = [
            [x, y],
            [x + width, y],
            [x, y + height],
            [x + width, y + height],
        ].map(point =>
            `<circle class="dco-sketch-selection-handle" cx="${point[0]}" cy="${point[1]}" r="5"/>`
        ).join("");

        return `<g class="dco-sketch-selection-overlay">
            <rect class="dco-sketch-selection-box" x="${x}" y="${y}" width="${width}" height="${height}" rx="5"/>
            ${handles}
        </g>`;
    }

    function snapIndicatorMarkup(snapPoint) {
        if (!snapPoint) return "";
        const x = Number(snapPoint.x);
        const y = Number(snapPoint.y);
        if (!Number.isFinite(x) || !Number.isFinite(y)) return "";
        return `<g class="dco-sketch-snap-indicator">
            <circle class="dco-sketch-snap-point" cx="${x}" cy="${y}" r="9"/>
            <path d="M${x - 5} ${y}H${x + 5}M${x} ${y - 5}V${y + 5}" stroke="#158e5b" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
        </g>`;
    }

    function canvasView(state, options = {}) {
        const canvas = canvasSize(options);
        const elements = Array.isArray(state && state.elements)
            ? state.elements
            : [];
        const selectedId = String(state && state.selectedId || "");
        const elementOptions = {
            noteFontSize: options.noteFontSize,
        };
        const items = elements.map(element => elementMarkup(element, {
            ...elementOptions,
            selected: element.id === selectedId,
        })).join("");
        const draft = state && state.draft
            ? elementMarkup(state.draft, { ...elementOptions, draft: true })
            : "";
        const viewBox = state && state.viewBox
            ? state.viewBox
            : { x: 0, y: 0, width: canvas.width, height: canvas.height };
        const selection = selectionMarkup(state, options);
        const snapIndicator = snapIndicatorMarkup(state && state.snapPoint);
        const gridFill = state && state.gridVisible === false
            ? "#fff"
            : "url(#dco-grid)";

        return {
            viewBox: [
                Number(viewBox.x) || 0,
                Number(viewBox.y) || 0,
                Number(viewBox.width) || canvas.width,
                Number(viewBox.height) || canvas.height,
            ].join(" "),
            markup: `
                <defs>
                    <pattern id="dco-small-grid" width="20" height="20" patternUnits="userSpaceOnUse">
                        <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#edf0f2" stroke-width="1"/>
                    </pattern>
                    <pattern id="dco-grid" width="100" height="100" patternUnits="userSpaceOnUse">
                        <rect width="100" height="100" fill="url(#dco-small-grid)"/>
                        <path d="M 100 0 L 0 0 0 100" fill="none" stroke="#d7dde2" stroke-width="1.5"/>
                    </pattern>
                    <marker id="dco-arrow-start" markerWidth="9" markerHeight="9" refX="4.5" refY="4.5" orient="auto-start-reverse">
                        <path d="M9,0 L0,4.5 L9,9" fill="none" stroke="#172033" stroke-width="1.5"/>
                    </marker>
                    <marker id="dco-arrow-end" markerWidth="9" markerHeight="9" refX="4.5" refY="4.5" orient="auto">
                        <path d="M0,0 L9,4.5 L0,9" fill="none" stroke="#172033" stroke-width="1.5"/>
                    </marker>
                </defs>
                <rect x="0" y="0" width="${canvas.width}" height="${canvas.height}" fill="#fff"/>
                <rect x="0" y="0" width="${canvas.width}" height="${canvas.height}" fill="${gridFill}"/>
                ${items}${draft}${selection}${snapIndicator}
                <g class="dco-sketch-cursor-preview" display="none">
                    <circle class="dco-sketch-cursor-ring" cx="0" cy="0" r="4" fill="none" stroke="#1674c5" stroke-width="2" vector-effect="non-scaling-stroke"/>
                    <path class="dco-sketch-cursor-cross" d="M-7 0H7M0-7V7" fill="none" stroke="#1674c5" stroke-width="1.4" vector-effect="non-scaling-stroke"/>
                </g>`,
        };
    }

    function sidebarView(elements) {
        const source = Array.isArray(elements) ? elements : [];
        const dimensions = source.filter(element => element.type === "dimension");
        const notes = source.filter(element => element.type === "note");
        const drawingElements = source.filter(element =>
            ["pen", "line", "rectangle", "ellipse"].includes(element.type)
        );
        const empty = text => `<div class="dco-sketch-empty">${text}</div>`;
        const dimensionsMarkup = dimensions.length
            ? dimensions.map((element, index) =>
                `<button type="button" class="dco-sketch-list-item" data-select-id="${escAttr(element.id)}"><span class="dco-sketch-list-badge">↔</span><span><b>قياس ${index + 1}</b><br>${esc(element.text)}</span></button>`
            ).join("")
            : empty("لم تضع قياسات بعد.<br>اختر أداة «قياس» وارسم سهمًا.");
        const notesMarkup = notes.length
            ? notes.map((element, index) =>
                `<button type="button" class="dco-sketch-list-item" data-select-id="${escAttr(element.id)}"><span class="dco-sketch-list-badge">T</span><span><b>ملاحظة ${index + 1}</b><br>${esc(element.text)}</span></button>`
            ).join("")
            : empty("لا توجد ملاحظات مكتوبة على الرسم.");
        const progress = [
            { done: drawingElements.length > 0, text: "رسم حدود الدرفة" },
            { done: dimensions.length > 0, text: `إضافة القياسات (${dimensions.length})` },
            { done: notes.length > 0, text: `ملاحظات المصمم (${notes.length})` },
        ];
        const progressMarkup = progress.map(item => `
            <div class="dco-sketch-progress-item ${item.done ? "is-done" : ""}">
                <span class="dco-sketch-progress-dot">${item.done ? "✓" : "•"}</span>
                <span>${item.text}</span>
            </div>`).join("");

        return {
            dimensions: dimensionsMarkup,
            notes: notesMarkup,
            progress: progressMarkup,
        };
    }

    window.AlmdinaSketchRenderer = Object.freeze({
        pathData,
        textPosition,
        elementMarkup,
        selectionMarkup,
        snapIndicatorMarkup,
        canvasView,
        sidebarView,
    });
})();
