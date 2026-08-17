(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingProfessional = window.AlmdinaDoorDrawingProfessional || Object.create(null);
    const v4 = window.AlmdinaDoorDrawingV4;
    const geometry = v4.Geometry;
    const documentModel = v4.DocumentModel;
    const dimensionDomain = v4.DimensionDomain;
    if (!geometry || !documentModel || !dimensionDomain) {
        throw new Error("Professional editor view-model dependencies are incomplete");
    }

    const TOOL_LABELS = Object.freeze({
        select: "تحديد",
        node: "تعديل النقاط",
        pen: "القلم الذكي",
        dimension: "الأبعاد",
        hand: "تحريك اللوحة",
    });
    const SNAP_LABELS = Object.freeze({
        close: "إغلاق ذكي",
        endpoint: "نقطة نهاية",
        intersection: "تقاطع",
        midpoint: "منتصف",
        perpendicular: "عمودي",
        edge: "على ضلع",
        parallel: "متوازي",
        extension: "امتداد",
        horizontal: "أفقي",
        vertical: "رأسي",
        angle: "زاوية",
        grid: "شبكة",
    });

    function pathNodes(document, pathId) {
        const path = documentModel.pathById(document, pathId);
        if (!path) return [];
        const ids = new Set([path.startNodeId]);
        (path.segmentIds || []).forEach(id => {
            const segment = documentModel.segmentById(document, id);
            if (!segment) return;
            ids.add(segment.startNodeId);
            ids.add(segment.endNodeId);
        });
        return [...ids].map(id => documentModel.nodeById(document, id)).filter(Boolean);
    }

    function pathBounds(document, pathId) {
        const nodes = pathNodes(document, pathId);
        if (!nodes.length) return null;
        const xs = nodes.map(node => node.xMm);
        const ys = nodes.map(node => node.yMm);
        const minX = Math.min(...xs);
        const maxX = Math.max(...xs);
        const minY = Math.min(...ys);
        const maxY = Math.max(...ys);
        return Object.freeze({
            xMm: minX,
            yMm: minY,
            widthMm: maxX - minX,
            heightMm: maxY - minY,
        });
    }

    function layers(state) {
        return Object.freeze((state.document.paths || []).map((path, index) => Object.freeze({
            id: path.id,
            label: index === 0 ? "محيط الدرفة" : `مسار ${index + 1}`,
            closed: Boolean(path.closed),
        })));
    }

    function properties(state) {
        const selection = state.selection;
        if (selection && selection.kind === "path") {
            const box = pathBounds(state.document, selection.id);
            return Object.freeze({
                kind: "path",
                title: "Selection",
                values: Object.freeze(box ? [
                    { label: "X", value: `${geometry.roundMm(box.xMm)} mm` },
                    { label: "Y", value: `${geometry.roundMm(box.yMm)} mm` },
                    { label: "W", value: `${geometry.roundMm(box.widthMm)} mm` },
                    { label: "H", value: `${geometry.roundMm(box.heightMm)} mm` },
                ] : []),
                help: "V للتحديد · A لتعديل النقاط",
            });
        }
        if (selection && selection.kind === "node") {
            const node = documentModel.nodeById(state.document, selection.id);
            return Object.freeze({
                kind: "node",
                title: "Node",
                values: Object.freeze(node ? [
                    { label: "X", value: `${geometry.roundMm(node.xMm)} mm` },
                    { label: "Y", value: `${geometry.roundMm(node.yMm)} mm` },
                ] : []),
                help: "اسحب النقطة؛ المحاذاة والـSnap يعملان أثناء الحركة.",
            });
        }
        if (selection && selection.kind === "dimension") {
            const measurement = dimensionDomain.resolve(state.document, selection.id);
            return Object.freeze({
                kind: "dimension",
                title: "Dimension",
                values: Object.freeze(measurement ? [
                    { label: "Length", value: `${geometry.roundMm(measurement.valueMm)} mm` },
                ] : []),
                help: "اكتب قيمة مباشرة ثم Enter لتثبيت البعد.",
            });
        }
        return Object.freeze({
            kind: "document",
            title: "Frame",
            values: Object.freeze([
                { label: "W", value: `${geometry.roundMm(state.document.blank.widthMm)} mm` },
                { label: "H", value: `${geometry.roundMm(state.document.blank.heightMm)} mm` },
            ]),
            help: "P القلم الذكي · D الأبعاد · Space للتحريك",
        });
    }

    function snapText(preview) {
        if (!preview || preview.type === "free") return "";
        const base = SNAP_LABELS[preview.semantic] || SNAP_LABELS[preview.type] || "Snap";
        return preview.semantic === "angle" ? `${base} ${Math.round(preview.angleDeg || 0)}°` : base;
    }

    function hint(state, readOnly = false) {
        if (readOnly) return "عرض فقط · Space أو أداة اليد للتحريك";
        if (state.drag) return "Snap ذكي أثناء تحريك النقطة · Shift لقفل 45° · Alt لتعطيل Snap · Esc للإلغاء";
        if (state.toolState.activeTool === "pen") {
            return state.activePathId
                ? "انقر لإضافة ضلع · Shift لقفل 45° · Alt لتعطيل Snap · اقترب من البداية للإغلاق · اكتب الطول مباشرة"
                : "انقر لبدء الرسم · P";
        }
        if (state.toolState.activeTool === "node") return "انقر واسحب نقطة · A";
        if (state.toolState.activeTool === "dimension") return "انقر على ضلع لإضافة/تحديد البعد · D";
        if (state.selection) return "العنصر محدد · A للنقاط · Esc لإلغاء التحديد";
        return "V تحديد · A نقاط · P قلم · D أبعاد";
    }

    root.EditorViewModel = Object.freeze({
        TOOL_LABELS,
        SNAP_LABELS,
        pathNodes,
        pathBounds,
        layers,
        properties,
        snapText,
        hint,
    });
})();
