(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const precision = root.Precision;
    const documents = root.DocumentModel;
    if (!precision || !documents) throw new Error("Door Drawing V2 domain must load before LegacyAdapter");

    function parseJson(raw) {
        if (!raw) return null;
        if (typeof raw === "object") return JSON.parse(JSON.stringify(raw));
        try { return JSON.parse(raw); } catch (error) { return null; }
    }

    function mmPointFromCm(point) {
        if (!Array.isArray(point) || point.length < 2) throw new TypeError("Legacy point must contain x and y");
        return { x:precision.cmToMm(point[0]), y:precision.cmToMm(point[1]) };
    }

    function legacyPolygon(rawGeometry) {
        const geometry = parseJson(rawGeometry);
        if (!geometry || Number(geometry.version) !== 1 || geometry.kind !== "polygon" || geometry.units !== "cm" || !Array.isArray(geometry.points) || geometry.points.length < 3) return null;
        return documents.createObject("polygon", {
            points: geometry.points.map(mmPointFromCm),
        }, {
            id: "legacy-main-geometry",
            category: "geometry",
            name: "Main Shape",
            metadata: {
                source: "legacy-special-shape-geometry-v1",
                template: String(geometry.template || "custom"),
                exact: geometry.exact !== false,
            },
        });
    }

    function exactLineElement(element) {
        const meta = element && element.exact_line;
        if (!meta || Number(meta.version) !== 1 || meta.units !== "cm" || !Array.isArray(meta.start_cm) || !Array.isArray(meta.end_cm)) return null;
        return documents.createObject("line", {
            start:mmPointFromCm(meta.start_cm),
            end:mmPointFromCm(meta.end_cm),
        }, {
            id:String(element.id || "legacy-line"),
            category:"geometry",
            name:"Line",
            style:{ stroke:element.color || "#111111" },
            metadata:{ source:"legacy-exact-line-v1" },
        });
    }

    function angleOf(center, point) {
        const c = mmPointFromCm(center);
        const p = mmPointFromCm(point);
        return Math.atan2(p.y-c.y, p.x-c.x) * 180 / Math.PI;
    }

    function exactArcElement(element) {
        const meta = element && element.exact_arc;
        if (!meta || Number(meta.version) !== 1 || meta.units !== "cm" || !Array.isArray(meta.center_cm) || !Array.isArray(meta.start_cm) || !Array.isArray(meta.end_cm)) return null;
        return documents.createObject("arc", {
            center:mmPointFromCm(meta.center_cm),
            radius:precision.cmToMm(meta.radius_cm),
            startAngleDeg:angleOf(meta.center_cm, meta.start_cm),
            endAngleDeg:angleOf(meta.center_cm, meta.end_cm),
            clockwise:Number(meta.side) < 0,
        }, {
            id:String(element.id || "legacy-arc"),
            category:"geometry",
            name:"Arc",
            style:{ stroke:element.color || "#111111" },
            metadata:{
                source:"legacy-exact-arc-v1",
                startMm:mmPointFromCm(meta.start_cm),
                endMm:mmPointFromCm(meta.end_cm),
                riseMm:precision.cmToMm(meta.rise_cm),
            },
        });
    }

    function approximateNote(element, door, canvas) {
        if (!element || element.type !== "note" || !String(element.text || "").trim()) return null;
        const width = Number(canvas && canvas.width) || 1000;
        const height = Number(canvas && canvas.height) || 650;
        const x = Math.max(0, Math.min(door.width, Number(element.x || 0) / width * door.width));
        const yTop = Math.max(0, Math.min(door.height, Number(element.y || 0) / height * door.height));
        return documents.createObject("text", {
            position:{ x:precision.serialized(x), y:precision.serialized(door.height-yTop) },
            rotationDeg:0,
        }, {
            id:String(element.id || `legacy-note-${Date.now()}`),
            category:"notes",
            name:"Note",
            style:{ stroke:element.color || "#111111" },
            metadata:{
                source:"legacy-note-v1",
                approximatePosition:true,
                text:String(element.text || ""),
                legacyFontSize:Number(element.font_size || element.fontSize || 18),
            },
        });
    }

    function fromRow(row, context = {}) {
        const widthMm = precision.cmToMm(row && row.width_cm);
        const heightMm = precision.cmToMm(row && row.length_cm);
        let document = documents.createDocument({
            orderId:context.orderId || "",
            rowId:(row && row.name) || context.rowId || "",
            widthMm,
            heightMm,
            quantity:(row && row.qty) || 1,
            createdFrom:"legacy-adapter",
        });
        const warnings = [];
        const exactPolygon = legacyPolygon(row && row.special_shape_geometry_json);
        const drawing = parseJson(row && row.special_shape_drawing_json);
        let exactObjectCount = 0;

        if (exactPolygon) {
            document = documents.addObject(document, exactPolygon);
            exactObjectCount += 1;
            if (drawing && Array.isArray(drawing.elements) && drawing.elements.some(item => item.exact_line || item.exact_arc)) {
                warnings.push("Exact V1 drawing segments were not duplicated because canonical polygon geometry already exists.");
            }
        } else if (drawing && Number(drawing.version) === 1 && Array.isArray(drawing.elements)) {
            drawing.elements.forEach(element => {
                const exact = exactArcElement(element) || exactLineElement(element);
                if (!exact) return;
                document = documents.addObject(document, exact);
                exactObjectCount += 1;
            });
        }

        if (drawing && Number(drawing.version) === 1 && Array.isArray(drawing.elements)) {
            drawing.elements.forEach(element => {
                const note = approximateNote(element, document.door, drawing.canvas);
                if (note) document = documents.addObject(document, note);
            });
            const visualOnly = drawing.elements.filter(element => !element.exact_line && !element.exact_arc && element.type !== "note");
            if (visualOnly.length) warnings.push(`${visualOnly.length} legacy visual element(s) remain reference-only because screen coordinates are not manufacturing geometry.`);
            document.metadata.legacyReference = {
                drawingVersion:1,
                hasVisualOnlyElements:visualOnly.length > 0,
            };
        }

        const status = exactObjectCount > 0 ? (warnings.length ? "partial" : "exact") : (drawing ? "reference-only" : "empty");
        return { document, status, warnings };
    }

    root.LegacyAdapter = Object.freeze({
        fromRow,
        legacyPolygon,
        exactLineElement,
        exactArcElement,
    });
})();
