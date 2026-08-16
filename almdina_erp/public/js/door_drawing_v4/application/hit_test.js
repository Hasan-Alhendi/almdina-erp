(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    if (!geometry || !documentModel) throw new Error("Drawing V4 domain must load before hit testing");

    function distanceToSegment(point, start, end) {
        const px = Number(point.xMm);
        const py = Number(point.yMm);
        const ax = Number(start.xMm);
        const ay = Number(start.yMm);
        const bx = Number(end.xMm);
        const by = Number(end.yMm);
        const dx = bx - ax;
        const dy = by - ay;
        const lengthSquared = dx * dx + dy * dy;
        if (lengthSquared <= geometry.EPSILON_MM * geometry.EPSILON_MM) return geometry.distance(point, start);
        const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lengthSquared));
        const projection = { xMm: ax + t * dx, yMm: ay + t * dy };
        return geometry.distance(point, projection);
    }

    function node(document, point, toleranceMm) {
        const tolerance = Math.max(0, Number(toleranceMm) || 0);
        let winner = null;
        (document.nodes || []).forEach(candidate => {
            const distanceMm = geometry.distance(point, candidate);
            if (distanceMm > tolerance) return;
            if (!winner || distanceMm < winner.distanceMm) {
                winner = Object.freeze({ kind: "node", id: candidate.id, distanceMm });
            }
        });
        return winner;
    }

    function segment(document, point, toleranceMm) {
        const tolerance = Math.max(0, Number(toleranceMm) || 0);
        let winner = null;
        (document.segments || []).forEach(candidate => {
            const start = documentModel.nodeById(document, candidate.startNodeId);
            const end = documentModel.nodeById(document, candidate.endNodeId);
            if (!start || !end) return;
            const distanceMm = distanceToSegment(point, start, end);
            if (distanceMm > tolerance) return;
            if (!winner || distanceMm < winner.distanceMm) {
                winner = Object.freeze({ kind: "segment", id: candidate.id, distanceMm });
            }
        });
        return winner;
    }

    function pathForSegment(document, segmentId) {
        const id = String(segmentId || "");
        const path = (document.paths || []).find(candidate => candidate.segmentIds.includes(id));
        return path ? Object.freeze({ kind: "path", id: path.id, segmentId: id }) : null;
    }

    function selectPath(document, point, toleranceMm) {
        const segmentHit = segment(document, point, toleranceMm);
        return segmentHit ? pathForSegment(document, segmentHit.id) : null;
    }

    root.HitTest = Object.freeze({
        distanceToSegment,
        node,
        segment,
        pathForSegment,
        selectPath,
    });
})();