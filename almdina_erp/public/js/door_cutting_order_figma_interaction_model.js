(() => {
    "use strict";

    const engine = window.AlmdinaSketchEngine;
    const lineModel = window.AlmdinaExactLineModel;
    const arcModel = window.AlmdinaExactArcModel;
    const segmentModel = window.AlmdinaExactSegmentDimensionModel;
    if (!engine || !lineModel || !arcModel || !segmentModel) {
        console.error("Drawing interaction dependencies must load before figma interaction model");
        return;
    }

    const DEFAULT_OFFSET_CM = 2;
    const DEFAULT_OFFSET_CANVAS = 18;

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function selected(elements, selectedId) {
        return (Array.isArray(elements) ? elements : []).find(
            element => String(element && element.id) === String(selectedId || "")
        ) || null;
    }

    function uniqueId(prefix = "copy") {
        return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    }

    function shiftPoint(point, delta) {
        return [Number(point[0]) + Number(delta[0]), Number(point[1]) + Number(delta[1])];
    }

    function exactDuplicate(element, transform, offsetCm = DEFAULT_OFFSET_CM) {
        const line = lineModel.exactMeta(element);
        if (line) {
            const result = lineModel.buildElement({
                transform,
                startCm: shiftPoint(line.start_cm, [offsetCm, offsetCm]),
                lengthCm: line.length_cm,
                angleDeg: line.angle_deg,
                color: element.color,
                id: uniqueId("exact-line-copy"),
            });
            if (result.valid) return { valid: true, element: { ...clone(element), ...result.element, id: result.element.id } };
            const reverse = lineModel.buildElement({
                transform,
                startCm: shiftPoint(line.start_cm, [-offsetCm, -offsetCm]),
                lengthCm: line.length_cm,
                angleDeg: line.angle_deg,
                color: element.color,
                id: uniqueId("exact-line-copy"),
            });
            return reverse.valid
                ? { valid: true, element: { ...clone(element), ...reverse.element, id: reverse.element.id } }
                : { valid: false, reason: "outside-piece", element: null };
        }

        const arc = arcModel.arcMeta(element);
        if (arc) {
            const attempt = delta => arcModel.buildElement({
                transform,
                startCm: shiftPoint(arc.start_cm, delta),
                endCm: shiftPoint(arc.end_cm, delta),
                riseCm: arc.rise_cm,
                side: arc.side,
                color: element.color,
                id: uniqueId("exact-arc-copy"),
            });
            let result = attempt([offsetCm, offsetCm]);
            if (!result.valid) result = attempt([-offsetCm, -offsetCm]);
            if (!result.valid) return { valid: false, reason: result.reason || "outside-piece", element: null };
            return { valid: true, element: { ...clone(element), ...result.element, id: result.element.id } };
        }
        return null;
    }

    function duplicateElement(element, transform, options = {}) {
        if (!element) return { valid: false, reason: "missing-element", element: null };
        const exact = exactDuplicate(element, transform, Number(options.offsetCm) || DEFAULT_OFFSET_CM);
        if (exact) return exact;
        const moved = engine.translateElement(
            element,
            Number(options.offsetCanvas) || DEFAULT_OFFSET_CANVAS,
            Number(options.offsetCanvas) || DEFAULT_OFFSET_CANVAS,
            { width: engine.DEFAULT_CANVAS.width, height: engine.DEFAULT_CANVAS.height }
        );
        moved.id = uniqueId(`${element.type || "element"}-copy`);
        return { valid: true, element: moved };
    }

    function rebuildEndpoint(element, transform, role, pointCm) {
        return segmentModel.rebuildWithEndpoint(element, transform, role, pointCm);
    }

    function applyEndpointDrag(elements, selectedId, role, pointCm, transform, options = {}) {
        const source = Array.isArray(elements) ? elements : [];
        const current = selected(source, selectedId);
        if (!current) return { valid: false, reason: "missing-selected", elements: clone(source), changedIds: [] };
        const rebuilt = rebuildEndpoint(current, transform, role, pointCm);
        if (!rebuilt.valid || !rebuilt.element) {
            return { valid: false, reason: rebuilt.reason || "invalid-endpoint", elements: clone(source), changedIds: [] };
        }
        return segmentModel.applyEdit(source, selectedId, rebuilt.element, transform, {
            preserveConnections: options.preserveConnections !== false,
        });
    }

    function elementKind(element) {
        if (lineModel.exactMeta(element)) return "exact-line";
        if (arcModel.arcMeta(element)) return "exact-arc";
        if (!element) return "";
        if (element.smart_template_key) return "template";
        return String(element.type || "");
    }

    window.AlmdinaFigmaInteractionModel = Object.freeze({
        DEFAULT_OFFSET_CM,
        DEFAULT_OFFSET_CANVAS,
        clone,
        selected,
        duplicateElement,
        rebuildEndpoint,
        applyEndpointDrag,
        elementKind,
    });
})();
