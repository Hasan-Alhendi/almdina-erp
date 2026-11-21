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

    function setPathRole(record, pathId, role) {
        const path = pathById(record, pathId);
        const allowed = role === "construction" || role === "annotation" || role === "manufacturing_outer";
        if (!path || !allowed) {
            return fail(record, role === "manufacturing_hole" ? "holes_unsupported" : "invalid_role", role === "manufacturing_hole"
                ? "Internal cutouts are not supported. This path was left unchanged."
                : "Choose a guide line, a note, or one cut outline.");
        }
        if (path.role === role) return true;
        remember(record);
        path.role = role;
        clearStatus(record);
        return true;
    }

    function translatePath(record, pathId, dx, dy, options) {
        const path = pathById(record, pathId);
        const base = options && options.base;
        const shiftX = quantize(dx);
        const shiftY = quantize(dy);
        if (!path || shiftX == null || shiftY == null) {
            return fail(record, "invalid_point", "Enter a numeric move in millimetres.");
        }
        const sourceNodes = (base && base.nodes) || path.nodes;
        const sourceSegments = (base && base.segments) || path.segments;
        if (shiftX === 0 && shiftY === 0 && !base) return true;
        const moved = sourceNodes.map((node) => pointOf(node.x_mm + shiftX, node.y_mm + shiftY));
        const movedControls = sourceSegments.map((segment) => {
            if (segment.kind !== "bezier" || !segment.controls) return null;
            return segment.controls.map((control) => pointOf(control.x_mm + shiftX, control.y_mm + shiftY));
        });
        if (moved.some((point) => point.x == null) || movedControls.some((row) => row && row.some((point) => point.x == null))) {
            return fail(record, "invalid_point", "That move puts the path outside the drawing range.");
        }
        const same = sourceNodes.every((node, index) => node.x_mm === moved[index].x && node.y_mm === moved[index].y)
            && path.nodes.every((node, index) => node.x_mm === moved[index].x && node.y_mm === moved[index].y);
        if (same) {
            clearStatus(record);
            return true;
        }
        if (!options || options.history !== false) remember(record);
        path.nodes.forEach((node, index) => {
            node.x_mm = moved[index].x;
            node.y_mm = moved[index].y;
        });
        path.segments.forEach((segment, index) => {
            if (!movedControls[index]) return;
            segment.controls.forEach((control, controlIndex) => {
                control.x_mm = movedControls[index][controlIndex].x;
                control.y_mm = movedControls[index][controlIndex].y;
            });
        });
        if (path.source_shape_id) {
            const shape = shapeById(record, path.source_shape_id);
            const params = (base && base.shapeParams) || (shape && shape.params);
            if (shape && params) shape.params = shiftParams(shape.kind, params, shiftX, shiftY);
        }
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

    function referenceById(record, referenceId) {
        return (record.document.references || []).find((row) => row.id === referenceId) || null;
    }

    function addReference(record, spec) {
        if (!record.ready) return fail(record, "not_ready", "The drawing is still loading.");
        const placed = spec || {};
        const rows = record.document.references || [];
        if (rows.length >= 32) {
            return fail(record, "too_many_elements", "This drawing already has the maximum number of reference images.");
        }
        const width = quantize(placed.width_mm);
        const height = quantize(placed.height_mm);
        const fileId = String(placed.file_id || "");
        if (!(width > 0) || !(height > 0) || !fileId || /\s/.test(fileId)) {
            return fail(record, "invalid_reference", "The reference image could not be placed.");
        }
        remember(record);
        const reference = {
            id: nextId(record, "r"),
            file_id: fileId,
            x_mm: quantize(placed.x_mm) || 0,
            y_mm: quantize(placed.y_mm) || 0,
            width_mm: width,
            height_mm: height,
            rotation_deg: quantize(placed.rotation_deg) || 0,
            opacity: placed.opacity == null ? 0.5 : Math.round(Number(placed.opacity) * 1000) / 1000,
            locked: false,
            hidden: false,
            calibration: null,
        };
        record.document.references = rows.concat([reference]);
        record.selection = selectionOf({ referenceId: reference.id });
        clearStatus(record);
        return reference.id;
    }

    function updateReference(record, referenceId, patch, options) {
        const reference = referenceById(record, referenceId);
        const changes = patch || {};
        if (!reference) return false;
        if (!options || options.history !== false) remember(record);
        let geometryChanged = false;
        ["x_mm", "y_mm", "width_mm", "height_mm", "rotation_deg"].forEach((key) => {
            if (changes[key] == null) return;
            const next = quantize(changes[key]);
            if (next == null) return;
            if (reference[key] !== next) geometryChanged = true;
            reference[key] = next;
        });
        if (changes.opacity != null && changes.opacity >= 0 && changes.opacity <= 1) {
            reference.opacity = Math.round(Number(changes.opacity) * 1000) / 1000;
        }
        if (typeof changes.locked === "boolean") reference.locked = changes.locked;
        if (typeof changes.hidden === "boolean") reference.hidden = changes.hidden;
        if (Object.prototype.hasOwnProperty.call(changes, "calibration")) reference.calibration = changes.calibration;
        else if (geometryChanged) reference.calibration = null;
        clearStatus(record);
        return true;
    }

    function deleteReference(record, referenceId) {
        const rows = record.document.references || [];
        const index = rows.findIndex((row) => row.id === referenceId);
        if (index < 0) return false;
        remember(record);
        const remaining = rows.filter((row) => row.id !== referenceId);
        record.document.references = remaining;
        if (record.selection && record.selection.referenceId === referenceId) {
            const next = remaining[Math.min(index, remaining.length - 1)];
            record.selection = next ? selectionOf({ referenceId: next.id }) : null;
        }
        clearStatus(record);
        return true;
    }

    function selectReference(record, referenceId) {
        if (!referenceById(record, referenceId)) return false;
        record.selection = selectionOf({ referenceId });
        clearStatus(record);
        return true;
    }

    function deleteSelection(record) {
        if (!record.selection) return false;
        if (record.selection.textId && !record.selection.pathId && !record.selection.shapeId && !record.selection.nodeId) {
            return deleteText(record, record.selection.textId);
        }
        if (record.selection.referenceId && !record.selection.pathId && !record.selection.nodeId && !record.selection.shapeId) {
            return deleteReference(record, record.selection.referenceId);
        }
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
        (record.document.texts || []).slice().reverse().forEach((text) => {
            const distance = textHit(text, doorPoint, bestDistance);
            if (distance == null) return;
            bestDistance = distance;
            best = { textId: text.id, pathId: null, segmentId: null, shapeId: null };
        });
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
        (document.texts || []).forEach((text) => {
            [text && text.id].concat((text && text.outlines || []).map((ring) => ring.id)).forEach((id) => {
                const match = String(id || "").match(/(\d+)$/);
                if (match) max = Math.max(max, Number(match[1]));
            });
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
        return Object.assign({ pathId: null, segmentId: null, shapeId: null, nodeId: null, textId: null }, extra || {});
    }

    function textById(record, textId) {
        return (record.document.texts || []).find((row) => row.id === textId) || null;
    }

    function textPointList(text) {
        const points = [];
        (text && text.outlines || []).forEach((ring) => {
            (ring.points || []).forEach((point) => points.push(point));
        });
        return points;
    }

    function textBounds(text) {
        const points = textPointList(text);
        if (!points.length) return null;
        let minX = points[0].x_mm;
        let minY = points[0].y_mm;
        let maxX = minX;
        let maxY = minY;
        points.forEach((point) => {
            minX = Math.min(minX, point.x_mm);
            minY = Math.min(minY, point.y_mm);
            maxX = Math.max(maxX, point.x_mm);
            maxY = Math.max(maxY, point.y_mm);
        });
        return { minX, minY, maxX, maxY, width: maxX - minX, height: maxY - minY };
    }

    function mapTextPoints(text, mapper) {
        (text.outlines || []).forEach((ring) => {
            ring.points = (ring.points || []).map((point) => {
                const next = mapper(point.x_mm, point.y_mm);
                return { x_mm: quantize(next.x), y_mm: quantize(next.y) };
            });
        });
    }

    function syncTextOrigin(text) {
        const bounds = textBounds(text);
        if (!bounds) return;
        text.x_mm = quantize(bounds.minX);
        text.y_mm = quantize(bounds.minY);
    }

    function textHit(text, doorPoint, threshold) {
        const bounds = textBounds(text);
        if (!bounds || !doorPoint) return null;
        const pad = Math.max(0, Number(threshold) || 0);
        if (doorPoint.x < bounds.minX - pad || doorPoint.x > bounds.maxX + pad || doorPoint.y < bounds.minY - pad || doorPoint.y > bounds.maxY + pad) {
            return null;
        }
        const rings = (text.outlines || []).map((ring) => (ring.points || []).map((point) => ({ x: point.x_mm, y: point.y_mm })));
        const inside = rings.some((ring) => ring.length >= 3 && Space().pointInPolygon(doorPoint, ring));
        if (inside) return 0;
        let best = pad;
        rings.forEach((ring) => {
            const distance = Space().outlineDistance(doorPoint, ring, true);
            if (distance < best) best = distance;
        });
        return best <= pad ? best : null;
    }

    function storeTextOutlines(record, text, rings) {
        text.outlines = (rings || []).map((ring, index) => ({
            id: `${text.id}-r${index + 1}`,
            points: (Array.isArray(ring) ? ring : ring.points || []).map((point) => ({
                x_mm: quantize(point.x_mm != null ? point.x_mm : point.x),
                y_mm: quantize(point.y_mm != null ? point.y_mm : point.y),
            })),
        })).filter((ring) => ring.points.length >= 3 && ring.points.every((point) => point.x_mm != null && point.y_mm != null));
        if (!text.outlines.length) return fail(record, "invalid_text", "The text outline is not valid.");
        return true;
    }

    function applyText(record, spec) {
        const input = spec || {};
        const content = String(input.text == null ? "" : input.text);
        if (!content.trim() || content.length > 80 || /[<>{}\\&]/.test(content)) {
            return fail(record, "invalid_text", "Enter text without markup.");
        }
        if (!record.ready) return fail(record, "not_ready", "The drawing is still loading.");
        const existing = input.id ? textById(record, input.id) : null;
        if (!input || input.history !== false) remember(record);
        if (!record.document.texts) record.document.texts = [];
        const text = existing || {
            id: nextId(record, "t"),
            role: "manufacturing_text",
            font_id: "noto-naskh-arabic",
            font_version: "1",
            aspect_locked: true,
            state: "editable",
            export_approved: false,
            outlines: [],
        };
        const contentChanged = existing && existing.text !== content;
        const typeChanged = existing && (
            existing.font_size_mm !== Number(input.font_size_mm)
            || existing.font_weight !== (input.font_weight || "regular")
            || existing.direction !== (input.direction || "auto")
            || existing.align !== (input.align || "right")
        );
        text.text = content;
        text.font_id = input.font_id || "noto-naskh-arabic";
        text.font_version = String(input.font_version || "1");
        text.font_size_mm = quantize(input.font_size_mm);
        text.font_weight = input.font_weight === "bold" ? "bold" : "regular";
        text.direction = input.direction || "auto";
        text.align = input.align || "right";
        text.rotation_deg = quantize(input.rotation_deg || 0);
        text.aspect_locked = input.aspect_locked !== false;
        if (input.x_mm != null) text.x_mm = quantize(input.x_mm);
        if (input.y_mm != null) text.y_mm = quantize(input.y_mm);
        if (!existing) {
            text.state = input.state === "vector" ? "vector" : "editable";
            text.export_approved = false;
            record.document.texts.push(text);
        }
        if (!storeTextOutlines(record, text, input.outlines || [])) {
            if (!existing) record.document.texts.pop();
            return false;
        }
        if (text.x_mm == null || text.y_mm == null) syncTextOrigin(text);
        if (contentChanged || typeChanged) {
            text.state = "editable";
            text.export_approved = false;
        }
        record.selection = selectionOf({ textId: text.id });
        clearStatus(record);
        return text.id;
    }

    function moveText(record, textId, dx, dy, options) {
        const text = textById(record, textId);
        const shiftX = quantize(dx);
        const shiftY = quantize(dy);
        const base = options && options.base && options.base.outlines ? options.base : null;
        if (!text || shiftX == null || shiftY == null) return false;
        if (!options || options.history !== false) remember(record);
        const source = base ? base.outlines : text.outlines;
        text.outlines = source.map((ring) => ({
            id: ring.id,
            points: (ring.points || []).map((point) => ({
                x_mm: quantize(point.x_mm + shiftX),
                y_mm: quantize(point.y_mm + shiftY),
            })),
        }));
        const originX = base ? base.x_mm : text.x_mm;
        const originY = base ? base.y_mm : text.y_mm;
        text.x_mm = quantize((originX || 0) + shiftX);
        text.y_mm = quantize((originY || 0) + shiftY);
        clearStatus(record);
        return true;
    }

    function scaleText(record, textId, factor, options) {
        const text = textById(record, textId);
        const scale = Number(factor);
        const bounds = text && textBounds(text);
        if (!bounds || !(scale > 0) || !Number.isFinite(scale)) return false;
        const base = options && options.base && options.base.outlines ? options.base : null;
        const sourceBounds = base ? textBounds(base) : bounds;
        if (!sourceBounds) return false;
        if (!options || options.history !== false) remember(record);
        const anchor = options && options.anchor
            ? options.anchor
            : { x: (sourceBounds.minX + sourceBounds.maxX) / 2, y: (sourceBounds.minY + sourceBounds.maxY) / 2 };
        const source = base ? base.outlines : text.outlines;
        const scaleX = options && options.axis === "y" ? 1 : scale;
        const scaleY = options && options.axis === "x" ? 1 : scale;
        text.outlines = source.map((ring) => ({
            id: ring.id,
            points: (ring.points || []).map((point) => ({
                x_mm: quantize(anchor.x + (point.x_mm - anchor.x) * scaleX),
                y_mm: quantize(anchor.y + (point.y_mm - anchor.y) * scaleY),
            })),
        }));
        const originX = base ? base.x_mm : text.x_mm;
        const originY = base ? base.y_mm : text.y_mm;
        text.x_mm = quantize(anchor.x + ((originX || 0) - anchor.x) * scaleX);
        text.y_mm = quantize(anchor.y + ((originY || 0) - anchor.y) * scaleY);
        const sourceSize = base ? base.font_size_mm : text.font_size_mm;
        if (sourceSize != null && scaleX === scaleY) text.font_size_mm = quantize(sourceSize * scale);
        clearStatus(record);
        return true;
    }

    function rotateText(record, textId, degrees, options) {
        const text = textById(record, textId);
        const angle = Number(degrees);
        const bounds = text && textBounds(text);
        if (!bounds || !Number.isFinite(angle)) return false;
        if (!options || options.history !== false) remember(record);
        const cx = (bounds.minX + bounds.maxX) / 2;
        const cy = (bounds.minY + bounds.maxY) / 2;
        const radians = angle * Math.PI / 180;
        const cos = Math.cos(radians);
        const sin = Math.sin(radians);
        mapTextPoints(text, (x, y) => {
            const dx = x - cx;
            const dy = y - cy;
            return { x: cx + dx * cos + dy * sin, y: cy - dx * sin + dy * cos };
        });
        text.rotation_deg = quantize((Number(text.rotation_deg) || 0) + angle);
        clearStatus(record);
        return true;
    }

    function convertText(record, textId) {
        const text = textById(record, textId);
        if (!text || !(text.outlines || []).length) return fail(record, "invalid_text", "The text outline is not valid.");
        remember(record);
        text.state = "vector";
        record.selection = selectionOf({ textId: text.id });
        clearStatus(record);
        return true;
    }

    function setTextExport(record, textId, approved) {
        const text = textById(record, textId);
        if (!text) return false;
        if (approved && text.state !== "vector") return fail(record, "text_not_vector", "Convert the text to a path before approving it.");
        remember(record);
        text.export_approved = approved === true && text.state === "vector";
        clearStatus(record);
        return true;
    }

    function deleteText(record, textId) {
        if (!textById(record, textId)) return false;
        remember(record);
        record.document.texts = (record.document.texts || []).filter((row) => row.id !== textId);
        if (!record.document.texts.length) delete record.document.texts;
        if (record.selection && record.selection.textId === textId) record.selection = null;
        clearStatus(record);
        return true;
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

    const PEN_LIMITS = Object.freeze({
        maxNodes: 12000,
        maxNodesPerPath: 4000,
        maxSegments: 12000,
        maxPaths: 256,
        maxBytes: 1000000,
    });

    function documentUsage(record) {
        let nodes = 0;
        let segments = 0;
        (record.document.paths || []).forEach((path) => {
            nodes += path.nodes.length;
            segments += path.segments.length;
        });
        return { nodes, segments, paths: record.document.paths.length };
    }

    function createPenPath(record, built, limits) {
        if (!record.ready) return fail(record, "not_ready", "The drawing is still loading.");
        const caps = Object.assign({}, PEN_LIMITS, limits || {});
        if (!built || built.ok !== true || !built.parts || !built.parts.segments || !built.parts.segments.length) {
            return fail(
                record,
                (built && built.code) || "short_stroke",
                (built && built.messageKey) || "The stroke is too short."
            );
        }
        const usage = documentUsage(record);
        const addNodes = built.parts.nodes.length;
        const addSegments = built.parts.segments.length;
        if (
            usage.paths >= caps.maxPaths
            || addNodes > caps.maxNodesPerPath
            || usage.nodes + addNodes > caps.maxNodes
            || usage.segments + addSegments > caps.maxSegments
        ) {
            return fail(record, "too_many_elements", "This stroke has too many points to store. The existing drawing was kept.");
        }
        const path = installParts(record, built.parts);
        path.closed = false;
        path.role = "construction";
        path.source_shape_id = null;
        const trial = clone(record.document);
        trial.paths = trial.paths.concat([path]);
        if (JSON.stringify(trial).length > caps.maxBytes) {
            return fail(record, "too_many_elements", "This stroke has too many points to store. The existing drawing was kept.");
        }
        remember(record);
        record.document.paths.push(path);
        record.cursor = null;
        record.selection = selectionOf({ pathId: path.id, segmentId: path.segments[0] && path.segments[0].id });
        record.measureError = null;
        record.messageKey = built.suggestClose ? "The stroke ends near its start. Close the path if you want a loop." : "";
        record.errorCode = "";
        return true;
    }

    function closePenPath(record, pathId) {
        const path = pathById(record, pathId);
        if (!path || path.closed || path.source_shape_id || path.nodes.length < 2 || !path.segments.length) {
            return fail(record, "cannot_close", "Finish at least one segment before closing the path.");
        }
        const first = path.nodes[0];
        const last = path.nodes[path.nodes.length - 1];
        if (path.segments[0].from_node !== first.id || path.segments[path.segments.length - 1].to_node !== last.id) {
            return fail(record, "cannot_close", "The path could not be closed.");
        }
        if (Space().samePoint({ x: first.x_mm, y: first.y_mm }, { x: last.x_mm, y: last.y_mm })) {
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
        record.selection = selectionOf({ pathId: path.id, segmentId: path.segments[path.segments.length - 1].id });
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
        const params = (options && options.base) || shape.params;
        return updateShape(record, shapeId, shiftParams(shape.kind, params, dx, dy), options);
    }

    function applyShapeFrame(record, shape, previous, frame, options) {
        const built = Space().frameToShapeParams(shape.kind, previous, frame);
        if (!built || !built.ok) return false;
        if (JSON.stringify(built.params) === JSON.stringify(shape.params)) {
            clearStatus(record);
            return true;
        }
        if (!options || options.history !== false) remember(record);
        shape.params = built.params;
        clearStatus(record);
        return true;
    }

    function resizeShape(record, shapeId, handle, door, options) {
        const shape = shapeById(record, shapeId);
        const previous = (options && options.base) || (shape && shape.params);
        if (!shape || shape.exploded || !previous || !door) return false;
        const frame = Space().shapeFrame(shape.kind, previous);
        const next = frame && Space().resizeFrame(frame, handle, door, Boolean(options && options.aspect));
        if (!next) return false;
        return applyShapeFrame(record, shape, previous, next, options);
    }

    function transformShape(record, shapeId, patch, options) {
        const shape = shapeById(record, shapeId);
        const previous = (options && options.base) || (shape && shape.params);
        if (!shape || shape.exploded || !previous || !patch) return false;
        let frame = Space().shapeFrame(shape.kind, previous);
        if (!frame) return false;
        const aspect = Boolean(options && options.aspect) || frame.uniform;
        if (patch.x != null || patch.y != null) {
            const x = patch.x != null ? patch.x : frame.center.x;
            const y = patch.y != null ? patch.y : frame.center.y;
            frame = Space().placeFrame(frame, x, y);
        }
        if (frame && (patch.width != null || patch.height != null)) {
            let width = patch.width != null ? patch.width : frame.width;
            let height = patch.height != null ? patch.height : frame.height;
            if (aspect) {
                if (patch.width != null && patch.height == null) height = width * (frame.height / frame.width);
                if (patch.height != null && patch.width == null) width = height * (frame.width / frame.height);
            }
            frame = Space().sizeFrame(frame, width, height);
        }
        if (frame && patch.rotation != null && !frame.uniform) {
            frame = Space().rotateFrame(frame, patch.rotation);
        } else if (frame && patch.rotation != null && shape.kind === "arc") {
            frame = Space().rotateFrame(frame, patch.rotation);
        } else if (frame && patch.rotation != null && shape.kind === "polygon") {
            frame = Space().rotateFrame(frame, patch.rotation);
        }
        if (!frame) return false;
        return applyShapeFrame(record, shape, previous, frame, options);
    }

    function pathDoorPoints(path) {
        const points = (path.nodes || []).map((node) => ({ x: node.x_mm, y: node.y_mm }));
        (path.segments || []).forEach((segment) => {
            (segment.controls || []).forEach((control) => points.push({ x: control.x_mm, y: control.y_mm }));
        });
        return points;
    }

    function pathUsesArc(path) {
        return (path.segments || []).some((segment) => segment && segment.kind === "arc");
    }

    function writeResizedPath(path, source, next) {
        const movedNodes = source.nodes.map((node) => Space().resizePoint({ x: node.x_mm, y: node.y_mm }, next));
        const movedControls = source.segments.map((segment) => {
            if (segment.kind !== "bezier" || !segment.controls) return null;
            return segment.controls.map((control) => Space().resizePoint({ x: control.x_mm, y: control.y_mm }, next));
        });
        if (movedNodes.some((point) => !point) || movedControls.some((row) => row && row.some((point) => !point))) {
            return false;
        }
        const radii = [];
        for (let index = 0; index < path.segments.length; index += 1) {
            const segment = path.segments[index];
            const sourceSegment = source.segments[index];
            if (segment.kind !== "arc" || !sourceSegment || sourceSegment.radius_mm == null) continue;
            const radius = quantize(Number(sourceSegment.radius_mm) * next.scaleX);
            if (radius == null || !(radius > 0)) return false;
            radii[index] = radius;
        }
        path.nodes.forEach((node, index) => {
            node.x_mm = movedNodes[index].x;
            node.y_mm = movedNodes[index].y;
        });
        path.segments.forEach((segment, index) => {
            if (radii[index] != null) segment.radius_mm = radii[index];
            if (!movedControls[index]) return;
            segment.controls.forEach((control, controlIndex) => {
                control.x_mm = movedControls[index][controlIndex].x;
                control.y_mm = movedControls[index][controlIndex].y;
            });
        });
        const rotation = quantize(next.rotation || 0);
        if (rotation) path.rotation_deg = rotation;
        else delete path.rotation_deg;
        return true;
    }

    function resizePath(record, pathId, handle, door, options) {
        const path = pathById(record, pathId);
        const source = (options && options.base) || path;
        if (!path || !source || !source.nodes || !door) return false;
        const uniform = pathUsesArc(source);
        const frame = Space().pointsFrame(pathDoorPoints(source), Number(source.rotation_deg) || 0, uniform);
        const next = frame && Space().resizeFrame(frame, handle, door, Boolean(options && options.aspect) || uniform);
        if (!next) return false;
        if (!options || options.history !== false) remember(record);
        if (!writeResizedPath(path, source, next)) {
            if (!options || options.history !== false) undo(record);
            return fail(record, "invalid_point", "That resize puts the path outside the drawing range.");
        }
        clearStatus(record);
        return true;
    }

    function rotatePathGeometry(path, center, delta, rotation) {
        const turned = (point) => {
            const next = Space().rotate(point, center, delta);
            return pointOf(next.x, next.y);
        };
        const nodes = path.nodes.map((node) => turned({ x: node.x_mm, y: node.y_mm }));
        const controls = path.segments.map((segment) => {
            if (segment.kind !== "bezier" || !segment.controls) return null;
            return segment.controls.map((control) => turned({ x: control.x_mm, y: control.y_mm }));
        });
        if (nodes.some((point) => point.x == null) || controls.some((row) => row && row.some((point) => point.x == null))) {
            return false;
        }
        path.nodes.forEach((node, index) => {
            node.x_mm = nodes[index].x;
            node.y_mm = nodes[index].y;
        });
        path.segments.forEach((segment, index) => {
            if (!controls[index]) return;
            segment.controls.forEach((control, controlIndex) => {
                control.x_mm = controls[index][controlIndex].x;
                control.y_mm = controls[index][controlIndex].y;
            });
        });
        if (rotation) path.rotation_deg = rotation;
        else delete path.rotation_deg;
        return true;
    }

    function transformPath(record, pathId, patch, options) {
        const path = pathById(record, pathId);
        const source = (options && options.base) || path;
        if (!path || !source || !source.nodes || !patch) return false;
        const uniform = pathUsesArc(source);
        const base = Space().pointsFrame(pathDoorPoints(source), Number(source.rotation_deg) || 0, uniform);
        if (!base) return false;
        const aspect = Boolean(options && options.aspect) || uniform;
        let sized = null;
        if (patch.width != null || patch.height != null) {
            let width = patch.width != null ? patch.width : base.width;
            let height = patch.height != null ? patch.height : base.height;
            if (aspect) {
                if (patch.width != null && patch.height == null) height = width * base.height / base.width;
                if (patch.height != null && patch.width == null) width = height * base.width / base.height;
            }
            sized = Space().sizeFrame(base, width, height);
            if (!sized) return false;
            sized.base = base;
            sized.anchorU = base.width / 2;
            sized.anchorV = base.height / 2;
            sized.scaleX = sized.width / base.width;
            sized.scaleY = sized.height / base.height;
        }
        const rotation = patch.rotation == null ? null : quantize(patch.rotation);
        const dx = patch.x == null ? 0 : quantize(patch.x - base.center.x);
        const dy = patch.y == null ? 0 : quantize(patch.y - base.center.y);
        if (!sized && rotation == null && !dx && !dy) return true;
        if (dx == null || dy == null) return false;
        if (!options || options.history !== false) remember(record);
        if (sized && !writeResizedPath(path, source, sized)) {
            if (!options || options.history !== false) undo(record);
            return fail(record, "invalid_point", "That resize puts the path outside the drawing range.");
        }
        if (rotation != null) {
            const center = sized ? sized.center : base.center;
            const delta = rotation - (Number(source.rotation_deg) || 0);
            if (!rotatePathGeometry(path, center, delta, rotation)) {
                if (!options || options.history !== false) undo(record);
                return fail(record, "invalid_point", "That rotation puts the path outside the drawing range.");
            }
        }
        if ((dx || dy) && translatePath(record, pathId, dx, dy, { history: false, base: sized || rotation != null ? null : source }) !== true) {
            if (!options || options.history !== false) undo(record);
            return false;
        }
        clearStatus(record);
        return true;
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
        if (record.selection.textId && !record.selection.pathId && !record.selection.shapeId) {
            const text = textById(record, record.selection.textId);
            if (!text) return false;
            return applyText(record, Object.assign({}, text, {
                id: null,
                x_mm: text.x_mm + 10,
                y_mm: text.y_mm + 10,
                outlines: (text.outlines || []).map((ring) => ring.points.map((point) => ({
                    x_mm: point.x_mm + 10,
                    y_mm: point.y_mm + 10,
                }))),
                export_approved: false,
                state: text.state,
            }));
        }
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
        if (record.selection.textId && !record.selection.pathId && !record.selection.shapeId) {
            const text = textById(record, record.selection.textId);
            if (!text) return false;
            record.clipboard = { type: "text", text: clone(text) };
            return true;
        }
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
        if (clip.type === "text" && clip.text) {
            const pasted = applyText(record, Object.assign({}, clip.text, {
                id: null,
                outlines: (clip.text.outlines || []).map((ring) => (ring.points || []).map((point) => ({
                    x_mm: point.x_mm + 10,
                    y_mm: point.y_mm + 10,
                }))),
                export_approved: false,
            }));
            if (pasted) {
                const created = textById(record, pasted);
                record.clipboard = { type: "text", text: clone(created) };
            }
            return Boolean(pasted);
        }
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
        let seenVersions = {};

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
                seenVersions = {};
            },
            captureSeenVersions(saved) {
                seenVersions = {};
                if (!saved || typeof saved !== "object") return;
                Object.keys(saved).forEach((key) => {
                    const version = Number(saved[key]);
                    if (!key || !Number.isFinite(version) || version < 0) return;
                    seenVersions[String(key)] = version;
                });
            },
            seenVersionPayload() {
                return JSON.stringify(seenVersions);
            },
            activate,
            current,
            activeId() { return activeId; },
            documentDirty(record) { return documentDirty(record || current() || { document: {}, savedCanonical: "" }); },
            documentCanonical() {
                const record = current();
                return record ? canonical(record.document) : "";
            },
            anyDirty() {
                let dirty = false;
                records.forEach((record) => { if (documentDirty(record)) dirty = true; });
                return dirty;
            },
            dirtyRecords() {
                return Array.from(records.values()).filter(documentDirty);
            },
            loadedRecords() {
                return Array.from(records.values());
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
            addReference(spec) {
                const record = current();
                return record ? addReference(record, spec) : false;
            },
            updateReference(referenceId, patch, options) {
                const record = current();
                return Boolean(record && updateReference(record, referenceId, patch, options));
            },
            deleteReference(referenceId) {
                const record = current();
                return Boolean(record && deleteReference(record, referenceId));
            },
            selectReference(referenceId) {
                const record = current();
                return Boolean(record && selectReference(record, referenceId));
            },
            selectHit(point, threshold) {
                const record = current();
                if (!record) return false;
                const hit = hitSegment(record, point, threshold);
                if (!hit) return false;
                if (hit.textId) {
                    record.selection = selectionOf({ textId: hit.textId });
                    clearStatus(record);
                    return true;
                }
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
            createPenPath(built, limits) {
                const record = current();
                return Boolean(record && createPenPath(record, built, limits));
            },
            setPathRole(pathId, role) {
                const record = current();
                return Boolean(record && setPathRole(record, pathId, role));
            },
            translatePath(pathId, dx, dy, options) {
                const record = current();
                return Boolean(record && translatePath(record, pathId, dx, dy, options));
            },
            closePenPath(pathId) {
                const record = current();
                return Boolean(record && closePenPath(record, pathId));
            },
            updateShape(shapeId, params, options) {
                const record = current();
                return Boolean(record && updateShape(record, shapeId, params, options));
            },
            moveShape(shapeId, dx, dy, options) {
                const record = current();
                return Boolean(record && moveShape(record, shapeId, dx, dy, options));
            },
            resizeShape(shapeId, handle, door, options) {
                const record = current();
                return Boolean(record && resizeShape(record, shapeId, handle, door, options));
            },
            transformShape(shapeId, patch, options) {
                const record = current();
                return Boolean(record && transformShape(record, shapeId, patch, options));
            },
            resizePath(pathId, handle, door, options) {
                const record = current();
                return record ? resizePath(record, pathId, handle, door, options) === true : false;
            },
            transformPath(pathId, patch, options) {
                const record = current();
                return record ? transformPath(record, pathId, patch, options) === true : false;
            },
            convertShape(shapeId) {
                const record = current();
                return Boolean(record && convertShape(record, shapeId));
            },
            applyText(spec) {
                const record = current();
                return record ? applyText(record, spec) : false;
            },
            moveText(textId, dx, dy, options) {
                const record = current();
                return Boolean(record && moveText(record, textId, dx, dy, options));
            },
            scaleText(textId, factor, options) {
                const record = current();
                return Boolean(record && scaleText(record, textId, factor, options));
            },
            rotateText(textId, degrees, options) {
                const record = current();
                return Boolean(record && rotateText(record, textId, degrees, options));
            },
            convertText(textId) {
                const record = current();
                return Boolean(record && convertText(record, textId));
            },
            setTextExport(textId, approved) {
                const record = current();
                return Boolean(record && setTextExport(record, textId, approved));
            },
            textBounds(textId) {
                const record = current();
                const text = record && textById(record, textId);
                return text ? textBounds(text) : null;
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
            isCurrent(pieceInstanceId, token) {
                const record = current();
                return Boolean(
                    record
                    && record.ready
                    && record.pieceInstanceId === String(pieceInstanceId || "")
                    && record.loadToken === token
                );
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
                const saved = applySave(record, response);
                if (saved && Number(record.drawingVersion) > 0) {
                    seenVersions[String(record.pieceInstanceId)] = Number(record.drawingVersion);
                }
                return saved;
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
