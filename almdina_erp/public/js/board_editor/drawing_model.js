(() => {
    "use strict";

    const Space = () => window.AlmdinaBoardEditor.DrawingSpace;
    const SCHEMA = "almdina.board-editor-drawing";
    const HISTORY_LIMIT = 80;

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function quantize(value) {
        return Space().quantizeMm(value);
    }

    function emptyDocument(pieceInstanceId, widthMm, lengthMm) {
        return {
            schema: SCHEMA,
            version: 1,
            units: "mm",
            coordinate_space: "door_local",
            piece_instance_id: String(pieceInstanceId || ""),
            blank: { width_mm: quantize(widthMm), length_mm: quantize(lengthMm) },
            paths: [],
            shapes: [],
            references: [],
        };
    }

    function canonical(document) {
        return JSON.stringify(document);
    }

    function blankRecord(pieceInstanceId, widthMm, lengthMm) {
        const document = emptyDocument(pieceInstanceId, widthMm, lengthMm);
        return {
            pieceInstanceId: String(pieceInstanceId || ""),
            widthMm: document.blank.width_mm,
            lengthMm: document.blank.length_mm,
            document,
            savedCanonical: canonical(document),
            drawingVersion: 0,
            ready: false,
            loadToken: 0,
            seq: 1,
            cursor: null,
            selection: null,
            past: [],
            future: [],
            messageKey: "",
            errorCode: "",
        };
    }

    function documentDirty(record) {
        return canonical(record.document) !== record.savedCanonical;
    }

    function snapshot(record) {
        return {
            document: clone(record.document),
            cursor: record.cursor ? clone(record.cursor) : null,
            selection: record.selection ? clone(record.selection) : null,
        };
    }

    function restore(record, shot) {
        record.document = clone(shot.document);
        record.cursor = shot.cursor ? clone(shot.cursor) : null;
        record.selection = shot.selection ? clone(shot.selection) : null;
    }

    function remember(record) {
        record.past = record.past.slice(-(HISTORY_LIMIT - 1));
        record.past.push(snapshot(record));
        if (record.past.length > HISTORY_LIMIT) record.past = record.past.slice(-HISTORY_LIMIT);
        record.future = [];
    }

    function nextId(record, prefix) {
        const id = `${prefix}${record.seq}`;
        record.seq += 1;
        return id;
    }

    function pointOf(x, y) {
        return { x: quantize(x), y: quantize(y) };
    }

    function fail(record, code, messageKey) {
        record.errorCode = code;
        record.messageKey = messageKey;
        return false;
    }

    function clearStatus(record) {
        record.errorCode = "";
        record.messageKey = "";
    }

    function pathById(record, pathId) {
        return record.document.paths.find((path) => path.id === pathId) || null;
    }

    function placePoint(record, x, y) {
        if (!record.ready) return fail(record, "not_ready", "The drawing is still loading.");
        const point = pointOf(x, y);
        if (point.x == null || point.y == null) {
            return fail(record, "invalid_point", "That point is outside the drawing range.");
        }
        clearStatus(record);
        if (!record.cursor) {
            remember(record);
            record.cursor = {
                pathId: null,
                nodeId: nextId(record, "n"),
                x: point.x,
                y: point.y,
            };
            record.selection = null;
            record.measureError = null;
            return true;
        }
        if (Space().samePoint(record.cursor, point)) {
            return fail(record, "zero_length", "A zero-length segment was not created.");
        }
        remember(record);
        const cursor = record.cursor;
        let path = cursor.pathId ? pathById(record, cursor.pathId) : null;
        const node = { id: nextId(record, "n"), x_mm: point.x, y_mm: point.y };
        const segment = {
            id: nextId(record, "s"),
            kind: "line",
            from_node: cursor.nodeId,
            to_node: node.id,
        };
        if (!path) {
            const start = { id: cursor.nodeId, x_mm: cursor.x, y_mm: cursor.y };
            path = {
                id: nextId(record, "p"),
                role: "construction",
                closed: false,
                nodes: [start, node],
                segments: [segment],
                source_shape_id: null,
            };
            record.document.paths.push(path);
        } else {
            path.nodes.push(node);
            path.segments.push(segment);
        }
        record.cursor = { pathId: path.id, nodeId: node.id, x: point.x, y: point.y };
        record.selection = { pathId: path.id, segmentId: segment.id };
        record.measureError = null;
        return true;
    }

    function parseMeasure(text) {
        const digits = String(text == null ? "" : text).trim()
            .replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)))
            .replace(/[۰-۹]/g, (digit) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit)))
            .replace(/[٫,]/g, ".");
        if (!digits) return { empty: true, invalid: false, value: null };
        const number = Number(digits);
        if (!Number.isFinite(number)) return { empty: false, invalid: true, value: null };
        return { empty: false, invalid: false, value: number };
    }

    // Length and angle text win over the pointer. A length with no known
    // direction uses 0° (door-local +X). An angle with no positive length
    // does not create a segment.
    function resolveNumericSegment(spec) {
        const input = spec || {};
        const length = parseMeasure(input.lengthText);
        const angle = parseMeasure(input.angleText);
        const previewLength = Number(input.previewLength);
        const previewAngle = Number(input.previewAngle);
        const hasPreviewLength = Number.isFinite(previewLength) && previewLength > 0;
        const hasPreviewAngle = Number.isFinite(previewAngle);
        if (length.invalid) {
            return { ok: false, field: "length", messageKey: "Enter a valid length." };
        }
        if (!length.empty && !(length.value > 0)) {
            return { ok: false, field: "length", messageKey: "A zero-length segment was not created." };
        }
        if (angle.invalid) {
            return { ok: false, field: "angle", messageKey: "Enter a valid angle." };
        }
        const useLength = !length.empty ? length.value : (hasPreviewLength ? previewLength : null);
        let useAngle = null;
        if (!angle.empty) useAngle = angle.value;
        else if (hasPreviewAngle) useAngle = previewAngle;
        else if (!length.empty) useAngle = 0;
        if (useLength == null) {
            return { ok: false, field: "length", messageKey: "Enter a length." };
        }
        if (useAngle == null) {
            return { ok: false, field: "angle", messageKey: "Enter a valid angle." };
        }
        return { ok: true, field: "", messageKey: "", lengthMm: useLength, angleDeg: useAngle };
    }

    function commitNumeric(record, spec) {
        if (!record || !record.cursor) {
            if (record) {
                record.measureError = {
                    field: "length",
                    messageKey: "Click a start point before entering a length.",
                };
            }
            return {
                ok: false,
                field: "length",
                messageKey: "Click a start point before entering a length.",
            };
        }
        const decision = resolveNumericSegment(spec);
        if (!decision.ok) {
            record.measureError = { field: decision.field, messageKey: decision.messageKey };
            return decision;
        }
        const end = Space().segmentEnd(record.cursor, decision.lengthMm, decision.angleDeg);
        if (!end || Space().samePoint(record.cursor, end)) {
            const messageKey = "A zero-length segment was not created.";
            record.measureError = { field: "length", messageKey };
            return { ok: false, field: "length", messageKey };
        }
        record.measureError = null;
        const placed = placePoint(record, end.x, end.y);
        if (!placed) {
            const messageKey = record.messageKey || "A zero-length segment was not created.";
            record.measureError = { field: "length", messageKey };
            return { ok: false, field: "length", messageKey };
        }
        record.measureError = null;
        return {
            ok: true,
            field: "",
            messageKey: "",
            end,
            lengthMm: end.lengthMm,
            angleDeg: decision.angleDeg,
        };
    }

    function placePolar(record, lengthValue, angleValue) {
        if (!record.cursor) {
            return fail(record, "no_start", "Click a start point before entering a length.");
        }
        const end = Space().segmentEnd(record.cursor, lengthValue, angleValue);
        if (!end) {
            return fail(record, "zero_length", "A zero-length segment was not created.");
        }
        return placePoint(record, end.x, end.y);
    }

    function finish(record) {
        if (!record.cursor) return false;
        remember(record);
        record.cursor = null;
        clearStatus(record);
        return true;
    }

    function closePath(record) {
        const path = record.cursor && record.cursor.pathId ? pathById(record, record.cursor.pathId) : null;
        if (!path || path.closed || path.nodes.length < 2) {
            return fail(record, "cannot_close", "Finish at least one segment before closing the path.");
        }
        const first = path.nodes[0];
        const last = path.nodes[path.nodes.length - 1];
        if (Space().samePoint(
            { x: first.x_mm, y: first.y_mm },
            { x: last.x_mm, y: last.y_mm }
        )) {
            return fail(record, "zero_length", "A zero-length segment was not created.");
        }
        remember(record);
        path.segments.push({
            id: nextId(record, "s"),
            kind: "line",
            from_node: last.id,
            to_node: first.id,
        });
        path.closed = true;
        record.cursor = null;
        record.selection = { pathId: path.id, segmentId: path.segments[path.segments.length - 1].id };
        clearStatus(record);
        return true;
    }

    function cancelPath(record) {
        if (!record.cursor) return false;
        remember(record);
        if (record.cursor.pathId) {
            record.document.paths = record.document.paths.filter((path) => path.id !== record.cursor.pathId);
            if (record.selection && record.selection.pathId === record.cursor.pathId) record.selection = null;
        }
        record.cursor = null;
        clearStatus(record);
        return true;
    }

    function escape(record) {
        if (record.cursor && !record.cursor.pathId) return cancelPath(record);
        return false;
    }

    function undo(record) {
        if (!record.past.length) return false;
        record.future.push(snapshot(record));
        restore(record, record.past.pop());
        clearStatus(record);
        return true;
    }

    function redo(record) {
        if (!record.future.length) return false;
        record.past.push(snapshot(record));
        restore(record, record.future.pop());
        clearStatus(record);
        return true;
    }

    function chainIds(path) {
        const ids = [];
        if (!path.segments.length) return path.nodes.map((node) => node.id);
        let cursor = path.segments[0].from_node;
        path.segments.forEach((segment) => {
            ids.push(segment.from_node);
            cursor = segment.to_node;
        });
        if (!path.closed) ids.push(cursor);
        return ids;
    }

    function editSegment(record, pathId, segmentId, lengthValue, angleValue) {
        const path = pathById(record, pathId);
        const segment = path && path.segments.find((row) => row.id === segmentId);
        if (!path || !segment || segment.kind !== "line") return false;
        const from = path.nodes.find((node) => node.id === segment.from_node);
        const to = path.nodes.find((node) => node.id === segment.to_node);
        const length = quantize(lengthValue);
        if (!from || !to || length == null || length <= 0) {
            return fail(record, "zero_length", "A zero-length segment was not created.");
        }
        const moved = Space().polarPoint({ x: from.x_mm, y: from.y_mm }, length, angleValue);
        const next = pointOf(moved.x, moved.y);
        if (next.x == null || Space().samePoint({ x: from.x_mm, y: from.y_mm }, next)) {
            return fail(record, "zero_length", "A zero-length segment was not created.");
        }
        if (path.closed) {
            const following = path.segments.find((row) => row.from_node === to.id);
            const after = following && path.nodes.find((node) => node.id === following.to_node);
            if (after && Space().samePoint({ x: after.x_mm, y: after.y_mm }, next)) {
                return fail(record, "zero_length", "A zero-length segment was not created.");
            }
        }
        if (Space().samePoint({ x: to.x_mm, y: to.y_mm }, next)) {
            clearStatus(record);
            return true;
        }
        const dx = next.x - to.x_mm;
        const dy = next.y - to.y_mm;
        remember(record);
        if (path.closed) {
            to.x_mm = next.x;
            to.y_mm = next.y;
        } else {
            const order = chainIds(path);
            const endAt = order.indexOf(to.id);
            path.nodes.forEach((node) => {
                const index = order.indexOf(node.id);
                if (node.id === to.id) {
                    node.x_mm = next.x;
                    node.y_mm = next.y;
                } else if (index > endAt) {
                    node.x_mm = quantize(node.x_mm + dx);
                    node.y_mm = quantize(node.y_mm + dy);
                }
            });
        }
        if (record.cursor && record.cursor.pathId === path.id && record.cursor.nodeId === to.id) {
            record.cursor.x = next.x;
            record.cursor.y = next.y;
        }
        clearStatus(record);
        return true;
    }

    function deleteSelection(record) {
        if (!record.selection) return false;
        if (record.selection.nodeId) return deleteNode(record, record.selection.pathId, record.selection.nodeId);
        if (record.selection.shapeId && !record.selection.pathId) {
            return deleteShape(record, record.selection.shapeId);
        }
        remember(record);
        const pathId = record.selection.pathId;
        record.document.paths = record.document.paths.filter((path) => path.id !== pathId);
        record.document.shapes = (record.document.shapes || []).filter((shape) => shape.path_id !== pathId);
        if (record.cursor && record.cursor.pathId === pathId) record.cursor = null;
        record.selection = null;
        clearStatus(record);
        return true;
    }

    function selectPath(record, pathId, segmentId) {
        if (!pathById(record, pathId)) return false;
        record.selection = selectionOf({ pathId, segmentId: segmentId || null });
        clearStatus(record);
        return true;
    }

    function hitSegment(record, doorPoint, threshold) {
        let best = null;
        let bestDistance = Math.max(0, Number(threshold) || 0);
        (record.document.shapes || []).forEach((shape) => {
            if (!shape || shape.exploded) return;
            const built = Space().normalizeShape(shape.kind, shape.params);
            if (!built.ok) return;
            const inside = built.figure.closed !== false && Space().pointInPolygon(doorPoint, built.figure.points);
            const distance = inside ? 0 : Space().outlineDistance(doorPoint, built.figure.points, built.figure.closed !== false);
            if (distance <= bestDistance) {
                bestDistance = distance;
                best = { shapeId: shape.id, pathId: null, segmentId: null };
            }
        });
        record.document.paths.forEach((path) => {
            const nodes = {};
            path.nodes.forEach((node) => { nodes[node.id] = node; });
            path.segments.forEach((segment) => {
                const from = nodes[segment.from_node];
                const to = nodes[segment.to_node];
                if (!from || !to) return;
                const samples = segmentSamples(segment, from, to);
                const distance = Space().outlineDistance(doorPoint, samples, false);
                if (distance <= bestDistance) {
                    bestDistance = distance;
                    best = { pathId: path.id, segmentId: segment.id, shapeId: null };
                }
            });
        });
        return best;
    }

    function segmentSamples(segment, from, to) {
        if (segment.kind === "line") {
            return [{ x: from.x_mm, y: from.y_mm }, { x: to.x_mm, y: to.y_mm }];
        }
        if (segment.kind === "bezier" && segment.controls && segment.controls.length === 2) {
            const points = [];
            for (let step = 0; step <= 16; step += 1) {
                const t = step / 16;
                const u = 1 - t;
                points.push({
                    x: u * u * u * from.x_mm
                        + 3 * u * u * t * segment.controls[0].x_mm
                        + 3 * u * t * t * segment.controls[1].x_mm
                        + t * t * t * to.x_mm,
                    y: u * u * u * from.y_mm
                        + 3 * u * u * t * segment.controls[0].y_mm
                        + 3 * u * t * t * segment.controls[1].y_mm
                        + t * t * t * to.y_mm,
                });
            }
            return points;
        }
        const chord = Space().lengthMm(from.x_mm, from.y_mm, to.x_mm, to.y_mm);
        const points = [{ x: from.x_mm, y: from.y_mm }];
        if (segment.kind === "arc" && chord > 0) {
            const radius = Number(segment.radius_mm);
            const mid = { x: (from.x_mm + to.x_mm) / 2, y: (from.y_mm + to.y_mm) / 2 };
            const offset = Math.sqrt(Math.max(0, radius * radius - (chord / 2) * (chord / 2)));
            const nx = -(to.y_mm - from.y_mm) / chord;
            const ny = (to.x_mm - from.x_mm) / chord;
            const sign = segment.sweep_clockwise ? 1 : -1;
            const center = segment.large_arc
                ? { x: mid.x - sign * nx * offset, y: mid.y - sign * ny * offset }
                : { x: mid.x + sign * nx * offset, y: mid.y + sign * ny * offset };
            const start = Math.atan2(from.y_mm - center.y, from.x_mm - center.x);
            let sweep = Math.atan2(to.y_mm - center.y, to.x_mm - center.x) - start;
            if (segment.sweep_clockwise && sweep < 0) sweep += Math.PI * 2;
            if (!segment.sweep_clockwise && sweep > 0) sweep -= Math.PI * 2;
            for (let step = 1; step <= 16; step += 1) {
                const angle = start + sweep * (step / 16);
                points.push({ x: center.x + radius * Math.cos(angle), y: center.y + radius * Math.sin(angle) });
            }
            return points;
        }
        points.push({ x: to.x_mm, y: to.y_mm });
        return points;
    }

    function segmentDistance(point, from, to) {
        const ax = from.x_mm;
        const ay = from.y_mm;
        const bx = to.x_mm;
        const by = to.y_mm;
        const dx = bx - ax;
        const dy = by - ay;
        const lengthSq = dx * dx + dy * dy;
        if (lengthSq <= 0) return Space().lengthMm(point.x, point.y, ax, ay);
        let t = ((point.x - ax) * dx + (point.y - ay) * dy) / lengthSq;
        t = Math.max(0, Math.min(1, t));
        return Space().lengthMm(point.x, point.y, ax + dx * t, ay + dy * t);
    }

    function applyLoaded(record, response) {
        if (!response || response.ok === false) {
            record.ready = true;
            record.errorCode = (response && response.code) || "load_failed";
            record.messageKey = loadMessage(record.errorCode);
            return;
        }
        if (response.storage_ready === false || response.code === "storage_not_installed") {
            record.ready = true;
            record.errorCode = "";
            record.messageKey = "";
            return;
        }
        if (documentDirty(record) || record.cursor) {
            record.ready = true;
            record.messageKey = "A saved drawing arrived after your edits. Your lines were kept.";
            return;
        }
        if (response.conflict === "source" || response.compatible === false) {
            record.ready = true;
            record.errorCode = "source_conflict";
            record.messageKey = "The source plan changed. Your drawing is still here.";
            return;
        }
        if (response.drawing) {
            record.document = clone(response.drawing);
            record.savedCanonical = canonical(record.document);
            record.seq = inferSeq(record.document);
        }
        record.drawingVersion = Number(response.drawing_version) || 0;
        record.ready = true;
        record.errorCode = "";
        record.messageKey = "";
    }

    function inferSeq(document) {
        let max = 0;
        (document.paths || []).forEach((path) => {
            [path.id].concat(
                (path.nodes || []).map((node) => node.id),
                (path.segments || []).map((segment) => segment.id)
            ).forEach((id) => {
                const match = String(id || "").match(/(\d+)$/);
                if (match) max = Math.max(max, Number(match[1]));
            });
        });
        (document.shapes || []).forEach((shape) => {
            const match = String(shape && shape.id || "").match(/(\d+)$/);
            if (match) max = Math.max(max, Number(match[1]));
        });
        return max + 1;
    }

    function loadMessage(code) {
        if (code === "storage_not_installed") return "Drawing storage is not installed. This drawing is still here.";
        if (code === "order_locked") return "This order is locked. The drawing was not saved.";
        return "Could not load the drawing. Your lines are still here.";
    }

    function applySave(record, response) {
        if (!response || response.ok === false) {
            record.errorCode = (response && response.code) || "save_failed";
            record.messageKey = saveMessage(record.errorCode);
            return false;
        }
        record.drawingVersion = Number(response.drawing_version) || record.drawingVersion;
        record.savedCanonical = canonical(record.document);
        record.errorCode = "";
        record.messageKey = "Drawing saved";
        return true;
    }

    function saveMessage(code) {
        if (code === "storage_not_installed") return "Drawing storage is not installed. This drawing is still here.";
        if (code === "version_conflict") return "This drawing was saved somewhere else. Your lines are still here.";
        if (code === "source_conflict") return "The source plan changed. Your drawing is still here.";
        if (code === "piece_not_drawable") return "This piece cannot store a drawing.";
        if (code === "blank_mismatch") return "The drawing blank does not match this piece.";
        if (code === "order_locked") return "This order is locked. The drawing was not saved.";
        return "Could not save the drawing. Your lines are still here.";
    }

    function metrics(path, segmentId) {
        const segment = path.segments.find((row) => row.id === segmentId);
        if (!segment) return null;
        const from = path.nodes.find((node) => node.id === segment.from_node);
        const to = path.nodes.find((node) => node.id === segment.to_node);
        if (!from || !to) return null;
        return {
            lengthMm: Space().lengthMm(from.x_mm, from.y_mm, to.x_mm, to.y_mm),
            angleDeg: Space().angleDeg(from.x_mm, from.y_mm, to.x_mm, to.y_mm),
        };
    }

    function shapeById(record, shapeId) {
        return (record.document.shapes || []).find((shape) => shape.id === shapeId) || null;
    }

    function nodeById(path, nodeId) {
        return path && path.nodes.find((node) => node.id === nodeId) || null;
    }

    function selectionOf(extra) {
        return Object.assign({ pathId: null, segmentId: null, shapeId: null, nodeId: null }, extra || {});
    }

    function installParts(record, parts) {
        const nodes = parts.nodes.map((node) => ({
            id: nextId(record, "n"),
            x_mm: node.x_mm,
            y_mm: node.y_mm,
        }));
        const segments = parts.segments.map((segment) => {
            const row = {
                id: nextId(record, "s"),
                kind: segment.kind,
                from_node: nodes[segment.from].id,
                to_node: nodes[segment.to].id,
            };
            if (segment.kind === "arc") {
                row.radius_mm = segment.radius_mm;
                row.large_arc = segment.large_arc === true;
                row.sweep_clockwise = segment.sweep_clockwise === true;
            }
            if (segment.kind === "bezier") row.controls = segment.controls.map((point) => ({ x_mm: point.x_mm, y_mm: point.y_mm }));
            return row;
        });
        return {
            id: nextId(record, "p"),
            role: "construction",
            closed: parts.closed === true,
            nodes,
            segments,
            source_shape_id: null,
        };
    }

    function createShape(record, kind, params) {
        if (!record.ready) return fail(record, "not_ready", "The drawing is still loading.");
        const built = Space().normalizeShape(kind, params);
        if (!built.ok) return fail(record, "invalid_shape", built.messageKey);
        remember(record);
        const shape = {
            id: nextId(record, "h"),
            kind,
            exploded: false,
            path_id: null,
            params: built.params,
        };
        record.document.shapes.push(shape);
        record.cursor = null;
        record.selection = selectionOf({ shapeId: shape.id });
        record.measureError = null;
        clearStatus(record);
        return true;
    }

    function createBezier(record, start, end) {
        if (!record.ready) return fail(record, "not_ready", "The drawing is still loading.");
        const built = Space().bezierFromPoints(start, end);
        if (!built.ok) return fail(record, "invalid_shape", built.messageKey);
        remember(record);
        const path = installParts(record, built.parts);
        record.document.paths.push(path);
        record.cursor = null;
        record.selection = selectionOf({ pathId: path.id, segmentId: path.segments[0].id });
        record.measureError = null;
        clearStatus(record);
        return true;
    }

    function updateShape(record, shapeId, params, options) {
        const shape = shapeById(record, shapeId);
        if (!shape || shape.exploded) return fail(record, "invalid_shape", "Edit the path nodes after converting the shape.");
        const built = Space().normalizeShape(shape.kind, params);
        if (!built.ok) return fail(record, "invalid_shape", built.messageKey);
        if (JSON.stringify(built.params) === JSON.stringify(shape.params)) {
            clearStatus(record);
            return true;
        }
        if (!options || options.history !== false) remember(record);
        shape.params = built.params;
        record.measureError = null;
        clearStatus(record);
        return true;
    }

    function shiftParams(kind, params, dx, dy) {
        const next = Object.assign({}, params);
        ["x_mm", "cx_mm"].forEach((key) => {
            if (next[key] != null) next[key] = quantize(Number(next[key]) + dx);
        });
        ["y_mm", "cy_mm"].forEach((key) => {
            if (next[key] != null) next[key] = quantize(Number(next[key]) + dy);
        });
        return next;
    }

    function moveShape(record, shapeId, dx, dy, options) {
        const shape = shapeById(record, shapeId);
        if (!shape || shape.exploded) return false;
        return updateShape(record, shapeId, shiftParams(shape.kind, shape.params, dx, dy), options);
    }

    function deleteShape(record, shapeId) {
        const shape = shapeById(record, shapeId);
        if (!shape) return false;
        remember(record);
        if (shape.exploded && shape.path_id) {
            record.document.paths = record.document.paths.filter((path) => path.id !== shape.path_id);
        }
        record.document.shapes = record.document.shapes.filter((row) => row.id !== shape.id);
        record.selection = null;
        clearStatus(record);
        return true;
    }

    function convertShape(record, shapeId) {
        const shape = shapeById(record, shapeId);
        if (!shape || shape.exploded) return fail(record, "invalid_shape", "This shape is already a path.");
        const parts = Space().shapePathParts(shape.kind, shape.params);
        if (!parts) return fail(record, "invalid_shape", "The shape could not be converted.");
        remember(record);
        const path = installParts(record, parts);
        path.source_shape_id = shape.id;
        shape.exploded = true;
        shape.path_id = path.id;
        record.document.paths.push(path);
        record.selection = selectionOf({ pathId: path.id, segmentId: path.segments[0] && path.segments[0].id });
        clearStatus(record);
        return true;
    }

    function duplicateSelection(record) {
        if (!record.selection) return false;
        if (record.selection.shapeId && !record.selection.pathId) {
            const shape = shapeById(record, record.selection.shapeId);
            if (!shape || shape.exploded) return false;
            return createShape(record, shape.kind, shiftParams(shape.kind, shape.params, 10, 10));
        }
        const path = pathById(record, record.selection.pathId);
        if (!path || path.source_shape_id) return false;
        remember(record);
        const copy = clone(path);
        const ids = {};
        copy.id = nextId(record, "p");
        copy.source_shape_id = null;
        copy.nodes.forEach((node) => {
            const id = nextId(record, "n");
            ids[node.id] = id;
            node.id = id;
            node.x_mm = quantize(node.x_mm + 10);
            node.y_mm = quantize(node.y_mm + 10);
        });
        copy.segments.forEach((segment) => {
            segment.id = nextId(record, "s");
            segment.from_node = ids[segment.from_node];
            segment.to_node = ids[segment.to_node];
            if (segment.controls) {
                segment.controls.forEach((point) => {
                    point.x_mm = quantize(point.x_mm + 10);
                    point.y_mm = quantize(point.y_mm + 10);
                });
            }
        });
        record.document.paths.push(copy);
        record.selection = selectionOf({ pathId: copy.id, segmentId: copy.segments[0] && copy.segments[0].id });
        clearStatus(record);
        return true;
    }

    function copySelection(record) {
        if (!record.selection) return false;
        if (record.selection.shapeId && !record.selection.pathId) {
            const shape = shapeById(record, record.selection.shapeId);
            if (!shape || shape.exploded) return false;
            record.clipboard = { type: "shape", kind: shape.kind, params: clone(shape.params) };
            return true;
        }
        const path = pathById(record, record.selection.pathId);
        if (!path) return false;
        record.clipboard = { type: "path", path: clone(path) };
        return true;
    }

    function pasteClipboard(record) {
        const clip = record.clipboard;
        if (!clip) return false;
        if (clip.type === "shape") {
            const pasted = createShape(record, clip.kind, shiftParams(clip.kind, clip.params, 10, 10));
            if (pasted) record.clipboard = { type: "shape", kind: clip.kind, params: shiftParams(clip.kind, clip.params, 10, 10) };
            return pasted;
        }
        if (clip.type !== "path" || !clip.path) return false;
        const source = clip.path;
        const indexOf = (id) => source.nodes.findIndex((node) => node.id === id);
        const parts = {
            closed: source.closed === true,
            nodes: source.nodes.map((node) => ({ x_mm: quantize(node.x_mm + 10), y_mm: quantize(node.y_mm + 10) })),
            segments: source.segments.map((segment) => {
                const row = { kind: segment.kind, from: indexOf(segment.from_node), to: indexOf(segment.to_node) };
                if (segment.kind === "arc") {
                    row.radius_mm = segment.radius_mm;
                    row.large_arc = segment.large_arc === true;
                    row.sweep_clockwise = segment.sweep_clockwise === true;
                }
                if (segment.kind === "bezier" && segment.controls) {
                    row.controls = segment.controls.map((point) => ({
                        x_mm: quantize(point.x_mm + 10),
                        y_mm: quantize(point.y_mm + 10),
                    }));
                }
                return row;
            }),
        };
        if (parts.segments.some((segment) => segment.from < 0 || segment.to < 0)) return false;
        remember(record);
        const path = installParts(record, parts);
        record.document.paths.push(path);
        record.selection = selectionOf({ pathId: path.id, segmentId: path.segments[0] && path.segments[0].id });
        record.clipboard = { type: "path", path: clone(path) };
        clearStatus(record);
        return true;
    }

    function neighborPoint(path, nodeId, segment) {
        const otherId = segment.from_node === nodeId ? segment.to_node : segment.from_node;
        return nodeById(path, otherId);
    }

    function moveNode(record, pathId, nodeId, x, y, options) {
        const path = pathById(record, pathId);
        const node = nodeById(path, nodeId);
        const point = pointOf(x, y);
        if (!path || !node || point.x == null) return fail(record, "invalid_point", "That point is outside the drawing range.");
        const touching = path.segments.filter((segment) => segment.from_node === nodeId || segment.to_node === nodeId);
        for (let index = 0; index < touching.length; index += 1) {
            const other = neighborPoint(path, nodeId, touching[index]);
            if (other && Space().samePoint({ x: other.x_mm, y: other.y_mm }, point)) {
                return fail(record, "zero_length", "A zero-length segment was not created.");
            }
            if (touching[index].kind === "arc" && other) {
                const chord = Space().lengthMm(other.x_mm, other.y_mm, point.x, point.y);
                if (touching[index].radius_mm + 1e-9 < chord / 2) {
                    return fail(record, "curve_inconsistent", "The arc radius no longer reaches both nodes.");
                }
            }
        }
        if (Space().samePoint({ x: node.x_mm, y: node.y_mm }, point)) {
            clearStatus(record);
            return true;
        }
        if (!options || options.history !== false) remember(record);
        node.x_mm = point.x;
        node.y_mm = point.y;
        if (record.cursor && record.cursor.nodeId === node.id) {
            record.cursor.x = point.x;
            record.cursor.y = point.y;
        }
        record.selection = selectionOf({ pathId: path.id, nodeId: node.id });
        clearStatus(record);
        return true;
    }

    function moveBezierControl(record, pathId, segmentId, controlIndex, x, y, options) {
        const path = pathById(record, pathId);
        const segment = path && path.segments.find((row) => row.id === segmentId);
        const point = pointOf(x, y);
        if (!segment || segment.kind !== "bezier" || !segment.controls || !segment.controls[controlIndex] || point.x == null) {
            return fail(record, "invalid_point", "That point is outside the drawing range.");
        }
        const current = segment.controls[controlIndex];
        if (current.x_mm === point.x && current.y_mm === point.y) return true;
        if (!options || options.history !== false) remember(record);
        current.x_mm = point.x;
        current.y_mm = point.y;
        record.selection = selectionOf({ pathId, segmentId, nodeId: `control:${controlIndex}` });
        clearStatus(record);
        return true;
    }

    function insertNode(record, pathId, segmentId, x, y) {
        const path = pathById(record, pathId);
        const segment = path && path.segments.find((row) => row.id === segmentId);
        if (!path || !segment || segment.kind !== "line") {
            return fail(record, "invalid_shape", "A node can be inserted on a straight segment.");
        }
        const point = pointOf(x, y);
        const from = nodeById(path, segment.from_node);
        const to = nodeById(path, segment.to_node);
        if (!from || !to || point.x == null) return fail(record, "invalid_point", "That point is outside the drawing range.");
        if (Space().samePoint({ x: from.x_mm, y: from.y_mm }, point) || Space().samePoint({ x: to.x_mm, y: to.y_mm }, point)) {
            return fail(record, "zero_length", "A zero-length segment was not created.");
        }
        remember(record);
        const node = { id: nextId(record, "n"), x_mm: point.x, y_mm: point.y };
        const fromIndex = path.nodes.findIndex((row) => row.id === from.id);
        path.nodes.splice(fromIndex + 1, 0, node);
        const segmentIndex = path.segments.findIndex((row) => row.id === segment.id);
        const first = { id: nextId(record, "s"), kind: "line", from_node: from.id, to_node: node.id };
        const second = { id: segment.id, kind: "line", from_node: node.id, to_node: to.id };
        path.segments.splice(segmentIndex, 1, first, second);
        record.selection = selectionOf({ pathId: path.id, nodeId: node.id });
        clearStatus(record);
        return true;
    }

    function deleteNode(record, pathId, nodeId) {
        const path = pathById(record, pathId);
        const node = nodeById(path, nodeId);
        if (!path || !node) return false;
        const minimum = path.closed ? 3 : 2;
        if (path.nodes.length <= minimum) {
            return fail(record, "inconsistent_path", path.closed
                ? "A closed path needs at least three nodes."
                : "A path needs at least two nodes.");
        }
        const incoming = path.segments.find((segment) => segment.to_node === nodeId);
        const outgoing = path.segments.find((segment) => segment.from_node === nodeId);
        if ((incoming && incoming.kind !== "line") || (outgoing && outgoing.kind !== "line")) {
            return fail(record, "invalid_shape", "Delete a node where both joined segments are straight.");
        }
        if (incoming && outgoing) {
            const previous = nodeById(path, incoming.from_node);
            const next = nodeById(path, outgoing.to_node);
            if (!previous || !next || previous.id === next.id || Space().samePoint(
                { x: previous.x_mm, y: previous.y_mm },
                { x: next.x_mm, y: next.y_mm }
            )) {
                return fail(record, "zero_length", "A zero-length segment was not created.");
            }
        }
        remember(record);
        path.nodes = path.nodes.filter((row) => row.id !== nodeId);
        if (incoming && outgoing) {
            incoming.to_node = outgoing.to_node;
            path.segments = path.segments.filter((segment) => segment.id !== outgoing.id);
        } else {
            path.segments = path.segments.filter((segment) => segment !== incoming && segment !== outgoing);
        }
        if (record.cursor && record.cursor.nodeId === nodeId) record.cursor = null;
        record.selection = selectionOf({ pathId: path.id, segmentId: path.segments[0] && path.segments[0].id });
        clearStatus(record);
        return true;
    }

    function hitNode(record, doorPoint, threshold) {
        let best = null;
        let bestDistance = Math.max(0, Number(threshold) || 0);
        (record.document.paths || []).forEach((path) => {
            path.nodes.forEach((node) => {
                const distance = Space().lengthMm(doorPoint.x, doorPoint.y, node.x_mm, node.y_mm);
                if (distance <= bestDistance) {
                    bestDistance = distance;
                    best = { pathId: path.id, nodeId: node.id, kind: "node" };
                }
            });
            path.segments.forEach((segment) => {
                if (segment.kind !== "bezier" || !segment.controls) return;
                segment.controls.forEach((control, index) => {
                    const distance = Space().lengthMm(doorPoint.x, doorPoint.y, control.x_mm, control.y_mm);
                    if (distance <= bestDistance) {
                        bestDistance = distance;
                        best = { pathId: path.id, segmentId: segment.id, controlIndex: index, kind: "control" };
                    }
                });
            });
        });
        return best;
    }

    function readShapeFields(kind, fields, anchor) {
        const defs = Space().shapeFieldDefs(kind);
        const source = fields || {};
        const params = {};
        for (let index = 0; index < defs.length; index += 1) {
            const key = defs[index].key;
            const text = source[key];
            if (key === "corner") {
                params.corner = text ? String(text) : "top_right";
                continue;
            }
            const parsed = parseMeasure(text);
            if (parsed.invalid) {
                return { ok: false, field: key, messageKey: key.endsWith("_deg") ? "Enter a valid angle." : "Enter a valid dimension." };
            }
            if (!parsed.empty) {
                params[key] = key === "sides" ? Math.round(parsed.value) : parsed.value;
                continue;
            }
            if (key === "end_x_mm") params[key] = anchor ? quantize(anchor.x + 100) : 100;
            else if (key === "end_y_mm") params[key] = anchor ? anchor.y : 0;
            else if ((key === "x_mm" || key === "cx_mm") && anchor) params[key] = anchor.x;
            else if ((key === "y_mm" || key === "cy_mm") && anchor) params[key] = anchor.y;
            else if (key === "x_mm" || key === "cx_mm") params[key] = 0;
            else if (key === "y_mm" || key === "cy_mm") params[key] = 0;
            else if (key === "rotation_deg" || key === "start_angle_deg") params[key] = 0;
            else if (key === "sweep_angle_deg") params[key] = 90;
            else if (key === "sides") params[key] = 6;
            else {
                return { ok: false, field: key, messageKey: "Enter a valid dimension." };
            }
        }
        return { ok: true, params };
    }

    function createSession() {
        const records = new Map();
        let activeId = "";

        function current() {
            return activeId ? records.get(activeId) || null : null;
        }

        function activate(spec) {
            const id = String((spec && spec.pieceInstanceId) || "");
            if (!id || spec.widthMm == null || spec.lengthMm == null) {
                activeId = "";
                return null;
            }
            let record = records.get(id);
            if (!record || record.widthMm !== spec.widthMm || record.lengthMm !== spec.lengthMm) {
                if (record && documentDirty(record)) {
                    activeId = id;
                    return record;
                }
                record = blankRecord(id, spec.widthMm, spec.lengthMm);
                records.set(id, record);
            }
            activeId = id;
            return record;
        }

        return {
            reset() {
                records.clear();
                activeId = "";
            },
            activate,
            current,
            activeId() { return activeId; },
            documentDirty(record) { return documentDirty(record || current() || { document: {}, savedCanonical: "" }); },
            anyDirty() {
                let dirty = false;
                records.forEach((record) => { if (documentDirty(record)) dirty = true; });
                return dirty;
            },
            dirtyRecords() {
                return Array.from(records.values()).filter(documentDirty);
            },
            placePoint(x, y) {
                const record = current();
                return Boolean(record && placePoint(record, x, y));
            },
            placePolar(length, angle) {
                const record = current();
                return Boolean(record && placePolar(record, length, angle));
            },
            commitNumeric(spec) {
                const record = current();
                if (!record) {
                    return {
                        ok: false,
                        field: "length",
                        messageKey: "Click a start point before entering a length.",
                    };
                }
                return commitNumeric(record, spec);
            },
            finish() { const record = current(); return Boolean(record && finish(record)); },
            close() { const record = current(); return Boolean(record && closePath(record)); },
            cancelPath() { const record = current(); return Boolean(record && cancelPath(record)); },
            escape() { const record = current(); return Boolean(record && escape(record)); },
            undo() { const record = current(); return Boolean(record && undo(record)); },
            redo() { const record = current(); return Boolean(record && redo(record)); },
            editSelected(length, angle) {
                const record = current();
                if (!record || !record.selection || !record.selection.segmentId) return false;
                return editSegment(record, record.selection.pathId, record.selection.segmentId, length, angle);
            },
            deleteSelection() { const record = current(); return Boolean(record && deleteSelection(record)); },
            selectHit(point, threshold) {
                const record = current();
                if (!record) return false;
                const hit = hitSegment(record, point, threshold);
                if (!hit) return false;
                if (hit.shapeId) {
                    record.selection = selectionOf({ shapeId: hit.shapeId });
                    clearStatus(record);
                    return true;
                }
                return selectPath(record, hit.pathId, hit.segmentId);
            },
            createShape(kind, params) {
                const record = current();
                return Boolean(record && createShape(record, kind, params));
            },
            createBezier(start, end) {
                const record = current();
                return Boolean(record && createBezier(record, start, end));
            },
            updateShape(shapeId, params, options) {
                const record = current();
                return Boolean(record && updateShape(record, shapeId, params, options));
            },
            moveShape(shapeId, dx, dy, options) {
                const record = current();
                return Boolean(record && moveShape(record, shapeId, dx, dy, options));
            },
            convertShape(shapeId) {
                const record = current();
                return Boolean(record && convertShape(record, shapeId));
            },
            duplicateSelection() {
                const record = current();
                return Boolean(record && duplicateSelection(record));
            },
            copySelection() {
                const record = current();
                return Boolean(record && copySelection(record));
            },
            pasteClipboard() {
                const record = current();
                return Boolean(record && pasteClipboard(record));
            },
            hasClipboard() {
                const record = current();
                return Boolean(record && record.clipboard);
            },
            commitShapeFields(kind, fields, anchor, mode) {
                const record = current();
                if (!record) return { ok: false, messageKey: "The drawing is still loading." };
                const read = readShapeFields(kind, fields, anchor);
                if (!read.ok) {
                    record.measureError = { field: read.field, messageKey: read.messageKey };
                    return read;
                }
                if (kind === "bezier") {
                    const origin = anchor || { x: 0, y: 0 };
                    const created = createBezier(record, origin, { x: read.params.end_x_mm, y: read.params.end_y_mm });
                    if (created) record.measureError = null;
                    return { ok: created === true, messageKey: created ? "" : (record.messageKey || "") };
                }
                const selected = mode === "edit" && record.selection && record.selection.shapeId
                    ? shapeById(record, record.selection.shapeId)
                    : null;
                const created = selected && selected.kind === kind && !selected.exploded
                    ? updateShape(record, selected.id, read.params)
                    : createShape(record, kind, read.params);
                if (created) record.measureError = null;
                return { ok: created === true, field: created ? "" : "width_mm", messageKey: created ? "" : (record.messageKey || "Enter a valid dimension.") };
            },
            moveNode(pathId, nodeId, x, y, options) {
                const record = current();
                return Boolean(record && moveNode(record, pathId, nodeId, x, y, options));
            },
            moveBezierControl(pathId, segmentId, index, x, y, options) {
                const record = current();
                return Boolean(record && moveBezierControl(record, pathId, segmentId, index, x, y, options));
            },
            insertNode(pathId, segmentId, x, y) {
                const record = current();
                return Boolean(record && insertNode(record, pathId, segmentId, x, y));
            },
            deleteNode(pathId, nodeId) {
                const record = current();
                return Boolean(record && deleteNode(record, pathId, nodeId));
            },
            hitNode(point, threshold) {
                const record = current();
                return record ? hitNode(record, point, threshold) : null;
            },
            selectNode(pathId, nodeId) {
                const record = current();
                const path = record && pathById(record, pathId);
                if (!path || !path.nodes.some((node) => node.id === nodeId)) return false;
                record.selection = selectionOf({ pathId, nodeId });
                clearStatus(record);
                return true;
            },
            clearSelection() {
                const record = current();
                if (!record) return;
                record.selection = null;
            },
            beginLoad() {
                const record = current();
                if (!record) return null;
                record.loadToken += 1;
                record.ready = false;
                record.messageKey = "Loading drawing";
                return { pieceInstanceId: record.pieceInstanceId, token: record.loadToken };
            },
            applyLoaded(pieceInstanceId, token, response) {
                const record = records.get(String(pieceInstanceId || ""));
                if (!record || token !== record.loadToken) return false;
                applyLoaded(record, response);
                return true;
            },
            markReady() {
                const record = current();
                if (record) record.ready = true;
            },
            applySave(pieceInstanceId, response) {
                const record = records.get(String(pieceInstanceId || ""));
                if (!record) return false;
                return applySave(record, response);
            },
            metrics(pathId, segmentId) {
                const record = current();
                const path = record && pathById(record, pathId);
                return path ? metrics(path, segmentId) : null;
            },
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.DrawingModel = Object.freeze({
        SCHEMA,
        createSession,
        emptyDocument,
        canonical,
        parseMeasure,
        resolveNumericSegment,
    });
})();
