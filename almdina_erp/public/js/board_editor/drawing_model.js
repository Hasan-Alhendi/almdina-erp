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
        if (path.closed) {
            return fail(
                record,
                "closed_edit",
                "Closed paths cannot be resized one segment at a time."
            );
        }
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
        if (Space().samePoint({ x: to.x_mm, y: to.y_mm }, next)) {
            clearStatus(record);
            return true;
        }
        const dx = next.x - to.x_mm;
        const dy = next.y - to.y_mm;
        remember(record);
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
        if (record.cursor && record.cursor.pathId === path.id && record.cursor.nodeId === to.id) {
            record.cursor.x = next.x;
            record.cursor.y = next.y;
        }
        clearStatus(record);
        return true;
    }

    function deleteSelection(record) {
        if (!record.selection) return false;
        remember(record);
        const pathId = record.selection.pathId;
        record.document.paths = record.document.paths.filter((path) => path.id !== pathId);
        if (record.cursor && record.cursor.pathId === pathId) record.cursor = null;
        record.selection = null;
        clearStatus(record);
        return true;
    }

    function selectPath(record, pathId, segmentId) {
        if (!pathById(record, pathId)) return false;
        record.selection = { pathId, segmentId: segmentId || null };
        clearStatus(record);
        return true;
    }

    function hitSegment(record, doorPoint, threshold) {
        let best = null;
        let bestDistance = Math.max(0, Number(threshold) || 0);
        record.document.paths.forEach((path) => {
            const nodes = {};
            path.nodes.forEach((node) => { nodes[node.id] = node; });
            path.segments.forEach((segment) => {
                if (segment.kind !== "line") return;
                const from = nodes[segment.from_node];
                const to = nodes[segment.to_node];
                if (!from || !to) return;
                const distance = segmentDistance(doorPoint, from, to);
                if (distance <= bestDistance) {
                    bestDistance = distance;
                    best = { pathId: path.id, segmentId: segment.id };
                }
            });
        });
        return best;
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
                return selectPath(record, hit.pathId, hit.segmentId);
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
