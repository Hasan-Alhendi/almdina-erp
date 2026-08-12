(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.Snapping;
    if (!Base || typeof Base.resolveObjectMove !== "function") {
        throw new Error("Door Drawing V3 snapping must load before move snap policy");
    }

    // Live tuning: whole-object magnetic joining should help only when edges are
    // genuinely close. Drawing-start/endpoint snapping uses separate tolerances.
    const EASY_MOVE_JOIN_SNAP_PX = 20;

    function resolveObjectMove(document, object, deltaX, deltaY, options = {}) {
        const requested = Number(options.moveJoinSnapPx);
        const moveJoinSnapPx = Number.isFinite(requested) && requested > 0
            ? requested
            : EASY_MOVE_JOIN_SNAP_PX;
        return Base.resolveObjectMove(document, object, deltaX, deltaY, {
            ...options,
            moveJoinSnapPx,
        });
    }

    root.Snapping = Object.freeze({
        ...Base,
        EASY_MOVE_JOIN_SNAP_PX,
        resolveObjectMove,
    });
})();
