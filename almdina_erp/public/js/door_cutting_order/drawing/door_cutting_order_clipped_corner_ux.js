(() => {
    "use strict";

    const CLIPPED_TYPE = "Clipped Corner";
    const L_TYPE = "L-Shaped Corner";
    const CORNER_TYPES = Object.freeze([CLIPPED_TYPE, L_TYPE]);
    const DEFAULT_POSITION = "Top Right";
    const ROTATED_POSITION = {
        "Top Left": "Top Right",
        "Top Right": "Bottom Right",
        "Bottom Right": "Bottom Left",
        "Bottom Left": "Top Left",
    };
    const MIRRORED_POSITION = {
        "Top Left": "Top Right",
        "Top Right": "Top Left",
        "Bottom Left": "Bottom Right",
        "Bottom Right": "Bottom Left",
    };
    const ROTATED_SIDE = {
        width_top: "long_left",
        width_bottom: "long_right",
        long_right: "width_top",
        long_left: "width_bottom",
    };
    const MIRRORED_SIDE = {
        width_top: "width_top",
        width_bottom: "width_bottom",
        long_left: "long_right",
        long_right: "long_left",
    };
    const SIDE_FLAG = {
        width_top: "edge_width_top",
        width_bottom: "edge_width_bottom",
        long_left: "edge_long_left",
        long_right: "edge_long_right",
    };
    const SIDE_OVERRIDE = {
        width_top: "edge_width_top_type_override",
        width_bottom: "edge_width_bottom_type_override",
        long_left: "edge_long_left_type_override",
        long_right: "edge_long_right_type_override",
    };
    const POSITIONS = [
        { value: "Top Right", ar: "أعلى اليمين", en: "Top right" },
        { value: "Top Left", ar: "أعلى اليسار", en: "Top left" },
        { value: "Bottom Right", ar: "أسفل اليمين", en: "Bottom right" },
        { value: "Bottom Left", ar: "أسفل اليسار", en: "Bottom left" },
    ];
    const BREAK_ADJACENT_SIDES = Object.freeze({
        "Top Right": Object.freeze(["edge_width_top", "edge_long_right"]),
        "Top Left": Object.freeze(["edge_width_top", "edge_long_left"]),
        "Bottom Right": Object.freeze(["edge_width_bottom", "edge_long_right"]),
        "Bottom Left": Object.freeze(["edge_width_bottom", "edge_long_left"]),
    });

    function num(value) {
        const result = Number(String(value ?? "").replace(",", "."));
        return Number.isFinite(result) ? result : 0;
    }

    function rounded(value) {
        return Math.round(num(value) * 1000) / 1000;
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function pieceType(piece) {
        return (piece && piece.piece_type) || "";
    }

    function isCornerCut(piece) {
        return CORNER_TYPES.includes(pieceType(piece));
    }

    function isClipped(piece) {
        return pieceType(piece) === CLIPPED_TYPE;
    }

    function isLShaped(piece) {
        return pieceType(piece) === L_TYPE;
    }

    function cutStyle(piece) {
        return isLShaped(piece) ? "L" : "diagonal";
    }

    function typeLabel(piece) {
        if (isLShaped(piece)) return __("L-shaped corner");
        return __("Clipped corner");
    }

    function typeIcon(piece) {
        return isLShaped(piece) ? "⌐" : "⌑";
    }

    function defaultCut(total) {
        total = num(total);
        if (total <= 0) return 0;
        return rounded(Math.min(Math.max(total * 0.2, 1), total * 0.45));
    }

    function defaultRemaining(total) {
        total = num(total);
        if (total <= 0) return 0;
        return rounded(Math.max(total - defaultCut(total), 0.1));
    }

    function remainingFromCut(total, cut) {
        total = num(total);
        cut = num(cut);
        if (total <= 0) return 0;
        if (cut <= 0) return defaultRemaining(total);
        return rounded(Math.max(0, total - cut));
    }

    function cutFromRemaining(total, remaining) {
        total = num(total);
        remaining = num(remaining);
        if (total <= 0) return 0;
        return rounded(Math.max(0, total - remaining));
    }

    function clampRemaining(total, remaining) {
        total = num(total);
        remaining = num(remaining);
        if (total <= 0) return 0;
        // Keep a positive remaining that still leaves a positive cut distance.
        const maxRemaining = rounded(Math.max(0.1, total - 0.1));
        return rounded(clamp(remaining, 0.1, maxRemaining));
    }

    function adjustCutForNewTotal(previousTotal, previousCut, nextTotal) {
        previousTotal = num(previousTotal);
        previousCut = num(previousCut);
        nextTotal = num(nextTotal);
        if (previousTotal <= 0 || nextTotal <= 0 || previousCut <= 0) return null;
        if (previousTotal === nextTotal) return rounded(previousCut);
        const remaining = remainingFromCut(previousTotal, previousCut);
        return cutFromRemaining(nextTotal, clampRemaining(nextTotal, remaining));
    }

    /**
     * When outer width/length change after the operator already set remaining
     * lengths, keep those remaining lengths and rewrite stored cut distances.
     * `previous` must be a snapshot taken before the committed dimension edit.
     */
    function preserveRemainingOnResize(row, previous) {
        if (!isCornerCut(row) || !previous) return false;
        let changed = false;
        const nextWidth = num(row.width_cm);
        const nextLength = num(row.length_cm);
        const nextCutWidth = adjustCutForNewTotal(
            previous.width,
            previous.cutWidth,
            nextWidth
        );
        const nextCutLength = adjustCutForNewTotal(
            previous.length,
            previous.cutLength,
            nextLength
        );
        if (nextCutWidth != null && nextCutWidth !== num(row.clipped_corner_width_cm)) {
            row.clipped_corner_width_cm = nextCutWidth;
            changed = true;
        }
        if (nextCutLength != null && nextCutLength !== num(row.clipped_corner_length_cm)) {
            row.clipped_corner_length_cm = nextCutLength;
            changed = true;
        }
        return changed;
    }

    function resizeSnapshot(row) {
        if (!isCornerCut(row)) return null;
        return {
            width: num(row.width_cm),
            length: num(row.length_cm),
            cutWidth: num(row.clipped_corner_width_cm),
            cutLength: num(row.clipped_corner_length_cm),
        };
    }

    function originalDimensions(piece) {
        return {
            width: num(piece.original_w || piece.original_width_cm || piece.width_cm),
            length: num(piece.original_h || piece.original_length_cm || piece.length_cm),
        };
    }

    function baseConfig(piece) {
        const dimensions = originalDimensions(piece || {});
        const cutWidth = num(piece.clipped_corner_width_cm) || defaultCut(dimensions.width);
        const cutLength = num(piece.clipped_corner_length_cm) || defaultCut(dimensions.length);
        return {
            position: POSITIONS.some(item => item.value === piece.clipped_corner_position)
                ? piece.clipped_corner_position
                : DEFAULT_POSITION,
            // Stored fields remain cut-from-corner distances used by geometry/DXF.
            cutWidth,
            cutLength,
            // Entry UI uses the remaining length of each outer side.
            remainingWidth: remainingFromCut(dimensions.width, cutWidth),
            remainingLength: remainingFromCut(dimensions.length, cutLength),
            originalWidth: dimensions.width,
            originalLength: dimensions.length,
        };
    }

    function effectiveConfig(piece) {
        const base = baseConfig(piece || {});
        const rotated = Boolean(piece && piece.rotated);
        return {
            position: rotated ? (ROTATED_POSITION[base.position] || DEFAULT_POSITION) : base.position,
            cutWidth: rotated ? base.cutLength : base.cutWidth,
            cutLength: rotated ? base.cutWidth : base.cutLength,
            width: num(piece && piece.w) || (rotated ? base.originalLength : base.originalWidth),
            length: num(piece && piece.h) || (rotated ? base.originalWidth : base.originalLength),
            rotated,
        };
    }

    function mirrorFlag(value) {
        if (value === undefined || value === null || value === false || value === 0 || value === "0") {
            return false;
        }
        if (value === true || value === 1 || value === "1") return true;
        return null;
    }

    function permuteSideState(state, mapping) {
        const nextFlags = {};
        const nextOverrides = {};
        const nextProfiles = {};
        Object.keys(mapping).forEach((side) => {
            const sourceSide = mapping[side];
            nextFlags[SIDE_FLAG[side]] = state.flags[SIDE_FLAG[sourceSide]] ? 1 : 0;
            nextOverrides[SIDE_OVERRIDE[side]] = state.overrides[SIDE_OVERRIDE[sourceSide]] || "";
            if (state.profiles[sourceSide]) {
                nextProfiles[side] = { ...state.profiles[sourceSide], side };
            }
        });
        return {
            flags: nextFlags,
            overrides: nextOverrides,
            profiles: nextProfiles,
        };
    }

    function pieceForQuarterTurns(piece, quarterTurns, mirrored) {
        const turns = Number(quarterTurns);
        const source = piece || {};
        const reflected = mirrorFlag(mirrored === undefined ? source.corner_mirrored : mirrored);
        if (reflected === null) return null;
        if (!Number.isInteger(turns) || turns < 0 || turns > 3) return null;
        if (!POSITIONS.some(item => item.value === source.clipped_corner_position)) return null;
        let position = source.clipped_corner_position;
        let cutWidth = num(source.clipped_corner_width_cm);
        let cutLength = num(source.clipped_corner_length_cm);
        if (!(cutWidth > 0) || !(cutLength > 0)) return null;
        let sideState = {
            flags: {
                edge_width_top: source.edge_width_top ? 1 : 0,
                edge_width_bottom: source.edge_width_bottom ? 1 : 0,
                edge_long_left: source.edge_long_left ? 1 : 0,
                edge_long_right: source.edge_long_right ? 1 : 0,
            },
            overrides: {
                edge_width_top_type_override: source.edge_width_top_type_override || "",
                edge_width_bottom_type_override: source.edge_width_bottom_type_override || "",
                edge_long_left_type_override: source.edge_long_left_type_override || "",
                edge_long_right_type_override: source.edge_long_right_type_override || "",
            },
            profiles: (source.edge_profiles && typeof source.edge_profiles === "object")
                ? source.edge_profiles
                : {},
        };
        // Reflection is applied once, before rotation, matching the domain matcher.
        // The DXF contour is already drawn; this copy only renames its edges.
        if (reflected) {
            position = MIRRORED_POSITION[position] || position;
            sideState = permuteSideState(sideState, MIRRORED_SIDE);
        }
        for (let index = 0; index < turns; index += 1) {
            position = ROTATED_POSITION[position] || position;
            const nextCutWidth = cutLength;
            cutLength = cutWidth;
            cutWidth = nextCutWidth;
            sideState = permuteSideState(sideState, ROTATED_SIDE);
        }
        return {
            ...source,
            rotated: false,
            clipped_corner_position: position,
            clipped_corner_width_cm: cutWidth,
            clipped_corner_length_cm: cutLength,
            edge_width_top: sideState.flags.edge_width_top,
            edge_width_bottom: sideState.flags.edge_width_bottom,
            edge_long_left: sideState.flags.edge_long_left,
            edge_long_right: sideState.flags.edge_long_right,
            edge_width_top_type_override: sideState.overrides.edge_width_top_type_override,
            edge_width_bottom_type_override: sideState.overrides.edge_width_bottom_type_override,
            edge_long_left_type_override: sideState.overrides.edge_long_left_type_override,
            edge_long_right_type_override: sideState.overrides.edge_long_right_type_override,
            edge_profiles: sideState.profiles,
        };
    }

    function breakAdjacentSides(position) {
        return BREAK_ADJACENT_SIDES[position || DEFAULT_POSITION] || BREAK_ADJACENT_SIDES[DEFAULT_POSITION];
    }

    function applyEdgeBreakPolicy(piece) {
        const row = piece || {};
        if (!isCornerCut(row)) {
            row.edge_break = 0;
            row.edge_break_only = 0;
            return row;
        }
        if (!isClipped(row)) row.edge_break_only = 0;
        if (row.edge_break) row.edge_break_only = 0;
        if (isClipped(row) && row.edge_break_only) {
            const adjacentSides = breakAdjacentSides(row.clipped_corner_position);
            if (adjacentSides.every((side) => Boolean(row[side]))) {
                row.edge_break = 1;
                row.edge_break_only = 0;
            }
        }
        // L-shaped corner strap is only the inner notch; outer sides stay free.
        if (!row.edge_break || isLShaped(row)) return row;
        breakAdjacentSides(row.clipped_corner_position).forEach((side) => {
            row[side] = 0;
            row[`${side}_type_override`] = "";
        });
        return row;
    }

    function toggleEdgeSelection(piece, fieldname) {
        const draft = piece || {};
        draft[fieldname] = draft[fieldname] ? 0 : 1;
        if (draft[fieldname] && fieldname === "edge_break") {
            draft.edge_break_only = 0;
        } else if (draft[fieldname] && fieldname === "edge_break_only") {
            draft.edge_break = 0;
        }
        return applyEdgeBreakPolicy(draft);
    }

    function locksAdjacentSidesForBreak(piece) {
        return Boolean(isClipped(piece) && piece && piece.edge_break);
    }

    function breakEdgeLabel(piece) {
        if (isLShaped(piece)) return __("Corner banding");
        return __("Full corner path");
    }

    function offsetBoundaryLine(start, end, amount, orientation) {
        const dx = end[0] - start[0];
        const dy = end[1] - start[1];
        const length = Math.hypot(dx, dy) || 1;
        const normalX = orientation * -dy / length * amount;
        const normalY = orientation * dx / length * amount;
        return {
            start: [start[0] + normalX, start[1] + normalY],
            end: [end[0] + normalX, end[1] + normalY],
        };
    }

    function lineIntersection(first, second) {
        const x1 = first.start[0];
        const y1 = first.start[1];
        const x2 = first.end[0];
        const y2 = first.end[1];
        const x3 = second.start[0];
        const y3 = second.start[1];
        const x4 = second.end[0];
        const y4 = second.end[1];
        const denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
        if (Math.abs(denominator) < 1e-9) return null;
        const firstCross = x1 * y2 - y1 * x2;
        const secondCross = x3 * y4 - y3 * x4;
        return [
            (firstCross * (x3 - x4) - (x1 - x2) * secondCross) / denominator,
            (firstCross * (y3 - y4) - (y1 - y2) * secondCross) / denominator,
        ];
    }

    function insetBoundary(boundary, amount) {
        const polygon = boundary || [];
        if (polygon.length < 3) return polygon.map(point => [...point]);
        const signedArea = polygon.reduce((total, point, index) => {
            const next = polygon[(index + 1) % polygon.length];
            return total + point[0] * next[1] - next[0] * point[1];
        }, 0);
        // Screen coordinates make clockwise polygons positive. Their interior
        // lies to the right of every directed boundary edge.
        const orientation = signedArea >= 0 ? 1 : -1;
        const lines = polygon.map((point, index) => offsetBoundaryLine(
            point,
            polygon[(index + 1) % polygon.length],
            amount,
            orientation
        ));
        const maxMiter = amount * 6;
        return polygon.map((point, index) => {
            const previous = lines[(index + lines.length - 1) % lines.length];
            const next = lines[index];
            const intersection = lineIntersection(previous, next);
            if (intersection && Math.hypot(intersection[0] - point[0], intersection[1] - point[1]) <= maxMiter) {
                return { miter: intersection, incoming: intersection, outgoing: intersection };
            }
            // Extremely shallow corners use a bevel instead of an unbounded
            // miter. Both points still lie on their exact parallel edge.
            return { miter: null, incoming: previous.end, outgoing: next.start };
        });
    }

    function insetBoundaryPath(path, boundary, inset) {
        const indices = (path || []).map((point) => boundary.findIndex(
            candidate => Math.abs(candidate[0] - point[0]) < 1e-7
                && Math.abs(candidate[1] - point[1]) < 1e-7
        ));
        if (indices.some(index => index < 0)) return (path || []).map(point => [...point]);
        const forward = indices.length < 2
            || (indices[1] - indices[0] + boundary.length) % boundary.length === 1;
        return indices.flatMap((index, pathIndex) => {
            const join = inset[index];
            if (join.miter) return [join.miter];
            if (pathIndex === 0) return [forward ? join.outgoing : join.incoming];
            if (pathIndex === indices.length - 1) return [forward ? join.incoming : join.outgoing];
            return forward
                ? [join.incoming, join.outgoing]
                : [join.outgoing, join.incoming];
        });
    }

    function clippedEdgePaths(piece, viewportWidth = 100, viewportHeight = 100, options = {}) {
        const width = Math.max(0, num(viewportWidth));
        const height = Math.max(0, num(viewportHeight));
        const empty = {
            top: null,
            bottom: null,
            left: null,
            right: null,
            break: null,
            breakOnly: null,
        };
        if (!isCornerCut(piece) || !width || !height) return empty;

        const config = effectiveConfig(piece || {});
        if (!config.width || !config.length) return empty;
        const cutX = clamp(config.cutWidth / config.width * width, 0, width * 0.95);
        const cutY = clamp(config.cutLength / config.length * height, 0, height * 0.95);
        const requestedInset = Number(options.insetPx);
        const amount = Number.isFinite(requestedInset)
            ? Math.max(0, requestedInset)
            : Math.min(width, height) * 0.035;
        const source = edgePathSource(cutStyle(piece), config.position, width, height, cutX, cutY)
            || edgePathSource(cutStyle(piece), DEFAULT_POSITION, width, height, cutX, cutY);
        if (!source) return empty;
        const boundary = points(piece, width, height);
        const inset = insetBoundary(boundary, amount);
        const insetPath = path => insetBoundaryPath(path, boundary, inset);
        return {
            top: insetPath(source.top),
            bottom: insetPath(source.bottom),
            left: insetPath(source.left),
            right: insetPath(source.right),
            break: insetPath(source.break),
            breakOnly: isClipped(piece) && source.breakOnly
                ? insetPath(source.breakOnly)
                : null,
        };
    }

    function edgePathSource(style, position, width, height, cutX, cutY) {
        const diagonalByPosition = {
            "Top Right": {
                top: [[0, 0], [width - cutX, 0]],
                right: [[width, cutY], [width, height]],
                bottom: [[width, height], [0, height]],
                left: [[0, height], [0, 0]],
                break: [[0, 0], [width - cutX, 0], [width, cutY], [width, height]],
                breakOnly: [[width - cutX, 0], [width, cutY]],
            },
            "Top Left": {
                top: [[cutX, 0], [width, 0]],
                right: [[width, 0], [width, height]],
                bottom: [[width, height], [0, height]],
                left: [[0, height], [0, cutY]],
                break: [[width, 0], [cutX, 0], [0, cutY], [0, height]],
                breakOnly: [[cutX, 0], [0, cutY]],
            },
            "Bottom Right": {
                top: [[0, 0], [width, 0]],
                right: [[width, 0], [width, height - cutY]],
                bottom: [[width - cutX, height], [0, height]],
                left: [[0, height], [0, 0]],
                break: [[width, 0], [width, height - cutY], [width - cutX, height], [0, height]],
                breakOnly: [[width, height - cutY], [width - cutX, height]],
            },
            "Bottom Left": {
                top: [[0, 0], [width, 0]],
                right: [[width, 0], [width, height]],
                bottom: [[width, height], [cutX, height]],
                left: [[0, height - cutY], [0, 0]],
                break: [[0, 0], [0, height - cutY], [cutX, height], [width, height]],
                breakOnly: [[0, height - cutY], [cutX, height]],
            },
        };
        // L corner strap covers only the inner notch (two orthogonal cut edges).
        const lByPosition = {
            "Top Right": {
                top: [[0, 0], [width - cutX, 0]],
                right: [[width, cutY], [width, height]],
                bottom: [[width, height], [0, height]],
                left: [[0, height], [0, 0]],
                break: [[width - cutX, 0], [width - cutX, cutY], [width, cutY]],
                breakOnly: null,
            },
            "Top Left": {
                top: [[cutX, 0], [width, 0]],
                right: [[width, 0], [width, height]],
                bottom: [[width, height], [0, height]],
                left: [[0, height], [0, cutY]],
                break: [[cutX, 0], [cutX, cutY], [0, cutY]],
                breakOnly: null,
            },
            "Bottom Right": {
                top: [[0, 0], [width, 0]],
                right: [[width, 0], [width, height - cutY]],
                bottom: [[width - cutX, height], [0, height]],
                left: [[0, height], [0, 0]],
                break: [[width, height - cutY], [width - cutX, height - cutY], [width - cutX, height]],
                breakOnly: null,
            },
            "Bottom Left": {
                top: [[0, 0], [width, 0]],
                right: [[width, 0], [width, height]],
                bottom: [[width, height], [cutX, height]],
                left: [[0, height - cutY], [0, 0]],
                break: [[0, height - cutY], [cutX, height - cutY], [cutX, height]],
                breakOnly: null,
            },
        };
        const byPosition = style === "L" ? lByPosition : diagonalByPosition;
        return byPosition[position] || null;
    }

    function remainingSideSegments(position, width, height, cutX, cutY) {
        // Remaining outer sides from the editor fields, not the short cut legs.
        const byPosition = {
            "Top Right": {
                width: [[0, 0], [width - cutX, 0]],
                length: [[width, cutY], [width, height]],
            },
            "Top Left": {
                width: [[cutX, 0], [width, 0]],
                length: [[0, height], [0, cutY]],
            },
            "Bottom Right": {
                width: [[width - cutX, height], [0, height]],
                length: [[width, 0], [width, height - cutY]],
            },
            "Bottom Left": {
                width: [[width, height], [cutX, height]],
                length: [[0, height - cutY], [0, 0]],
            },
        };
        return byPosition[position] || null;
    }

    function orderCornerMetrics(piece) {
        if (!isCornerCut(piece)) return null;
        const width = num(piece.width_cm);
        const length = num(piece.length_cm);
        const cutWidth = num(piece.clipped_corner_width_cm);
        const cutLength = num(piece.clipped_corner_length_cm);
        const position = String(piece.clipped_corner_position || "").trim();
        if (!(width > 0) || !(length > 0)) return null;
        if (!(cutWidth > 0) || !(cutLength > 0)) return null;
        if (cutWidth >= width || cutLength >= length) return null;
        if (!POSITIONS.some(item => item.value === position)) return null;
        return {
            style: cutStyle(piece),
            position,
            width,
            length,
            cutWidth,
            cutLength,
            remainingWidth: remainingFromCut(width, cutWidth),
            remainingLength: remainingFromCut(length, cutLength),
        };
    }

    // Print-space edge paths in centimetres. inset is in the same units as the
    // outline (cm), never editor pixel insets reinterpreted as centimetres.
    function orderEdgePaths(piece, options = {}) {
        const empty = {
            top: null,
            bottom: null,
            left: null,
            right: null,
            break: null,
            breakOnly: null,
        };
        const metrics = orderCornerMetrics(piece);
        if (!metrics) return empty;
        const { style, position, width, length, cutWidth, cutLength } = metrics;
        const source = edgePathSource(style, position, width, length, cutWidth, cutLength);
        if (!source) return empty;
        const boundary = cornerPolygonPoints(style, position, width, length, cutWidth, cutLength) || [];
        const requestedInset = Number(options.inset);
        const amount = Number.isFinite(requestedInset)
            ? Math.max(0, requestedInset)
            : Math.min(width, length) * 0.035;
        const inset = insetBoundary(boundary, amount);
        const insetPath = path => (path ? insetBoundaryPath(path, boundary, inset) : null);
        return {
            top: insetPath(source.top),
            bottom: insetPath(source.bottom),
            left: insetPath(source.left),
            right: insetPath(source.right),
            break: insetPath(source.break),
            breakOnly: isClipped(piece) ? insetPath(source.breakOnly) : null,
        };
    }

    function orderEdgeBandSvgMarkup(piece, options = {}) {
        const paths = orderEdgePaths(piece, options);
        if (!paths.top && !paths.bottom && !paths.left && !paths.right && !paths.break && !paths.breakOnly) {
            return "";
        }
        const color = options.color || "#d00000";
        const strokeWidth = options.strokeWidth || 2.2;
        const toPoints = (path) => (path || [])
            .map(([x, y]) => `${rounded(x)},${rounded(y)}`)
            .join(" ");
        const polyline = (path) => {
            if (!path || path.length < 2) return "";
            return `<polyline fill="none" stroke="${color}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" points="${toPoints(path)}"/>`;
        };
        const lines = [];
        if (piece && piece.edge_width_top && paths.top) lines.push(polyline(paths.top));
        if (piece && piece.edge_width_bottom && paths.bottom) lines.push(polyline(paths.bottom));
        if (piece && piece.edge_long_left && paths.left) lines.push(polyline(paths.left));
        if (piece && piece.edge_long_right && paths.right) lines.push(polyline(paths.right));
        if (piece && piece.edge_break && paths.break) lines.push(polyline(paths.break));
        if (piece && piece.edge_break_only && paths.breakOnly) lines.push(polyline(paths.breakOnly));
        return lines.join("");
    }

    function orderRemainingDimensionAnchors(piece, options = {}) {
        const metrics = orderCornerMetrics(piece);
        if (!metrics) return [];
        const segments = remainingSideSegments(
            metrics.position,
            metrics.width,
            metrics.length,
            metrics.cutWidth,
            metrics.cutLength
        );
        if (!segments) return [];
        const offset = Number.isFinite(Number(options.offset))
            ? Math.max(0, Number(options.offset))
            : Math.min(metrics.width, metrics.length) * 0.08;
        const center = [metrics.width / 2, metrics.length / 2];
        const place = (axis, segment, value) => {
            if (!segment || segment.length < 2 || !(value > 0)) return null;
            const start = segment[0];
            const end = segment[1];
            const midX = (start[0] + end[0]) / 2;
            const midY = (start[1] + end[1]) / 2;
            let nx = start[1] - end[1];
            let ny = end[0] - start[0];
            const length = Math.hypot(nx, ny) || 1;
            nx /= length;
            ny /= length;
            if ((midX - center[0]) * nx + (midY - center[1]) * ny < 0) {
                nx = -nx;
                ny = -ny;
            }
            const sideLength = Math.hypot(end[0] - start[0], end[1] - start[1]);
            // Length labels sit beside a vertical edge with middle text-anchor, so they
            // need more outward room than the width label above/below a horizontal edge.
            let labelOffset = sideLength < Math.min(metrics.width, metrics.length) * 0.22
                ? offset * 1.35
                : offset;
            if (axis === "length") labelOffset *= 2.9;
            return {
                axis,
                value,
                midX,
                midY,
                x: midX + nx * labelOffset,
                y: midY + ny * labelOffset,
                nx,
                ny,
                short: sideLength < Math.min(metrics.width, metrics.length) * 0.22,
            };
        };
        return [
            place("width", segments.width, metrics.remainingWidth),
            place("length", segments.length, metrics.remainingLength),
        ].filter(Boolean);
    }

    function trimPathEnds(path, trimPx) {
        if (!Array.isArray(path) || path.length < 2 || !(trimPx > 0)) return path;
        const distances = [0];
        for (let index = 1; index < path.length; index += 1) {
            distances.push(distances[index - 1] + Math.hypot(
                path[index][0] - path[index - 1][0],
                path[index][1] - path[index - 1][1],
            ));
        }
        const total = distances[distances.length - 1];
        const trim = Math.min(trimPx, total * 0.45);
        if (!(total > 0) || !(trim > 0)) return path;
        const pointAt = target => {
            for (let index = 1; index < distances.length; index += 1) {
                if (target > distances[index]) continue;
                const segment = distances[index] - distances[index - 1];
                const ratio = segment ? (target - distances[index - 1]) / segment : 0;
                return [
                    path[index - 1][0] + (path[index][0] - path[index - 1][0]) * ratio,
                    path[index - 1][1] + (path[index][1] - path[index - 1][1]) * ratio,
                ];
            }
            return [...path[path.length - 1]];
        };
        const result = [pointAt(trim)];
        for (let index = 1; index < path.length - 1; index += 1) {
            if (distances[index] > trim && distances[index] < total - trim) result.push([...path[index]]);
        }
        result.push(pointAt(total - trim));
        return result;
    }

    function edgeBandSvgMarkup(piece, viewportWidth = 100, viewportHeight = 100, options = {}) {
        const paths = clippedEdgePaths(piece, viewportWidth, viewportHeight, options);
        if (!paths.top && !paths.bottom && !paths.left && !paths.right && !paths.break && !paths.breakOnly) return "";
        if (Number(options.endTrimPx) > 0) {
            Object.keys(paths).forEach(key => {
                if (paths[key]) paths[key] = trimPathEnds(paths[key], Number(options.endTrimPx));
            });
        }
        // Match regular-door plan edges: inherit stroke from the parent <g> and keep
        // screen-space thickness via non-scaling-stroke (avoids fat diagonals under
        // preserveAspectRatio="none").
        const inheritStroke = options.inheritStroke !== false;
        const color = options.color || "#d00000";
        const strokeWidth = options.strokeWidth || 3;
        const offsetX = num(options.offsetX);
        const offsetY = num(options.offsetY);
        const toPoints = (path) => (path || [])
            .map(([x, y]) => `${rounded(x + offsetX)},${rounded(y + offsetY)}`)
            .join(" ");
        const polyline = (path, extraClass = "") => {
            if (inheritStroke) {
                return `<polyline class="dco-edge-line-svg ${extraClass}" fill="none" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" points="${toPoints(path)}"/>`;
            }
            return `<polyline class="dco-edge-line-svg ${extraClass}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke" points="${toPoints(path)}"/>`;
        };
        const lines = [];
        const flags = {
            top: Boolean(piece && piece.edge_width_top),
            bottom: Boolean(piece && piece.edge_width_bottom),
            left: Boolean(piece && piece.edge_long_left),
            right: Boolean(piece && piece.edge_long_right),
        };
        if (flags.top && paths.top) lines.push(polyline(paths.top));
        if (flags.bottom && paths.bottom) lines.push(polyline(paths.bottom));
        if (flags.left && paths.left) lines.push(polyline(paths.left));
        if (flags.right && paths.right) lines.push(polyline(paths.right));
        if (piece && piece.edge_break && paths.break) {
            lines.push(polyline(paths.break, "dco-edge-break-svg"));
        }
        if (piece && piece.edge_break_only && paths.breakOnly) {
            lines.push(polyline(paths.breakOnly, "dco-edge-break-only-svg"));
        }
        return lines.join("");
    }

    function cornerPolygonPoints(style, position, width, height, cutX, cutY) {
        const byPosition = style === "L"
            ? {
                "Top Right": [[0, 0], [width - cutX, 0], [width - cutX, cutY], [width, cutY], [width, height], [0, height]],
                "Top Left": [[cutX, 0], [width, 0], [width, height], [0, height], [0, cutY], [cutX, cutY]],
                "Bottom Right": [[0, 0], [width, 0], [width, height - cutY], [width - cutX, height - cutY], [width - cutX, height], [0, height]],
                "Bottom Left": [[0, 0], [width, 0], [width, height], [cutX, height], [cutX, height - cutY], [0, height - cutY]],
            }
            : {
                "Top Right": [[0, 0], [width - cutX, 0], [width, cutY], [width, height], [0, height]],
                "Top Left": [[cutX, 0], [width, 0], [width, height], [0, height], [0, cutY]],
                "Bottom Right": [[0, 0], [width, 0], [width, height - cutY], [width - cutX, height], [0, height]],
                "Bottom Left": [[0, 0], [width, 0], [width, height], [cutX, height], [0, height - cutY]],
            };
        return byPosition[position] || null;
    }

    function points(piece, viewportWidth = 100, viewportHeight = 100) {
        const config = effectiveConfig(piece || {});
        const width = Math.max(0, num(viewportWidth));
        const height = Math.max(0, num(viewportHeight));
        if (!width || !height || !config.width || !config.length) {
            return [[0, 0], [width, 0], [width, height], [0, height]];
        }

        const cutX = clamp(config.cutWidth / config.width * width, 0, width * 0.95);
        const cutY = clamp(config.cutLength / config.length * height, 0, height * 0.95);
        return cornerPolygonPoints(cutStyle(piece), config.position, width, height, cutX, cutY)
            || cornerPolygonPoints(cutStyle(piece), DEFAULT_POSITION, width, height, cutX, cutY);
    }

    // Print outline of the piece as entered. Stored cuts are distances from the
    // saved corner, not the remaining lengths shown in the editor. Missing or
    // impossible cuts produce no outline so print does not invent a corner.
    function orderOutlinePoints(piece) {
        if (!isCornerCut(piece)) return [];
        const width = num(piece.width_cm);
        const length = num(piece.length_cm);
        const cutWidth = num(piece.clipped_corner_width_cm);
        const cutLength = num(piece.clipped_corner_length_cm);
        const position = String(piece.clipped_corner_position || "").trim();
        if (!(width > 0) || !(length > 0)) return [];
        if (!(cutWidth > 0) || !(cutLength > 0)) return [];
        if (cutWidth >= width || cutLength >= length) return [];
        if (!POSITIONS.some(item => item.value === position)) return [];
        return cornerPolygonPoints(
            cutStyle(piece),
            position,
            width,
            length,
            cutWidth,
            cutLength
        ) || [];
    }

    const PREVIEW_CANVAS_WIDTH = 360;
    const PREVIEW_CANVAS_HEIGHT = 220;
    const PREVIEW_PADDING = 30;

    function previewFrame(widthCm, lengthCm) {
        const pieceWidth = Math.max(num(widthCm), 0.001);
        const pieceLength = Math.max(num(lengthCm), 0.001);
        const scale = Math.min(
            PREVIEW_CANVAS_WIDTH / pieceWidth,
            PREVIEW_CANVAS_HEIGHT / pieceLength
        );
        const width = rounded(pieceWidth * scale);
        const height = rounded(pieceLength * scale);
        return {
            x: rounded(PREVIEW_PADDING + (PREVIEW_CANVAS_WIDTH - width) / 2),
            y: rounded(PREVIEW_PADDING + (PREVIEW_CANVAS_HEIGHT - height) / 2),
            width,
            height,
            scale: rounded(scale),
        };
    }

    function pointsAttribute(piece, width = 100, height = 100) {
        return points(piece, width, height)
            .map(point => `${rounded(point[0])},${rounded(point[1])}`)
            .join(" ");
    }

    function dxfPoints(piece, x, y, width, height) {
        return points(piece, width, height).map(point => [
            num(x) + point[0],
            num(y) + height - point[1],
        ]);
    }

    function positionLabel(value) {
        const item = POSITIONS.find(position => position.value === value) || POSITIONS[0];
        return __(item.en);
    }

    function prepareRow(row) {
        if (!isCornerCut(row)) return false;
        const config = baseConfig(row);
        let changed = false;
        if (!POSITIONS.some(item => item.value === row.clipped_corner_position)) {
            row.clipped_corner_position = config.position;
            changed = true;
        }
        if (num(row.clipped_corner_width_cm) <= 0 && config.cutWidth > 0) {
            row.clipped_corner_width_cm = config.cutWidth;
            changed = true;
        }
        if (num(row.clipped_corner_length_cm) <= 0 && config.cutLength > 0) {
            row.clipped_corner_length_cm = config.cutLength;
            changed = true;
        }
        return changed;
    }

    function summary(row) {
        if (!isCornerCut(row)) return "";
        const config = baseConfig(row);
        const size = config.remainingWidth && config.remainingLength
            ? `${rounded(config.remainingWidth)}×${rounded(config.remainingLength)} ${__("cm remaining")}`
            : __("after dimensions");
        return `${positionLabel(config.position)} · ${size}`;
    }

    function edgeSelectionSummary(row) {
        if (!isCornerCut(row)) return "";
        const labels = [];
        if (row.edge_width_top) labels.push(__("Top edge"));
        if (row.edge_width_bottom) labels.push(__("Bottom edge"));
        if (row.edge_long_right) labels.push(__("Right edge"));
        if (row.edge_long_left) labels.push(__("Left edge"));
        if (row.edge_break) labels.push(isLShaped(row) ? __("Corner") : __("Break"));
        if (row.edge_break_only) labels.push(__("Break only"));
        if (!labels.length) return __("No banding");
        return labels.join(" · ");
    }

    function cloneEdgeDraft(row) {
        return {
            edge_width_top: row.edge_width_top ? 1 : 0,
            edge_width_bottom: row.edge_width_bottom ? 1 : 0,
            edge_long_right: row.edge_long_right ? 1 : 0,
            edge_long_left: row.edge_long_left ? 1 : 0,
            edge_break: row.edge_break ? 1 : 0,
            edge_break_only: row.edge_break_only ? 1 : 0,
            clipped_corner_position: row.clipped_corner_position || DEFAULT_POSITION,
            piece_type: pieceType(row) || CLIPPED_TYPE,
        };
    }

    function edgeToggleHtml(field, label, draft, locked, extra = "") {
        const checked = Boolean(draft[field]);
        return `
            <button type="button" class="dco-corner-edge-toggle ${checked ? "is-checked" : ""} ${locked ? "is-break-locked" : ""} ${extra}" data-corner-edge="${field}" aria-pressed="${checked ? "true" : "false"}" ${locked ? "disabled" : ""} title="${locked ? (__("Included in break banding")) : ""}">
                <span class="dco-check-mark">${checked ? "✓" : ""}</span>
                <span>${label}</span>
            </button>`;
    }

    function edgeControlsHtml(row) {
        if (!isCornerCut(row)) return "";
        const draft = applyEdgeBreakPolicy(cloneEdgeDraft(row));
        const locked = locksAdjacentSidesForBreak(draft)
            ? new Set(breakAdjacentSides(draft.clipped_corner_position))
            : new Set();
        return `
            <div data-corner-edges-section>
                <div class="dco-corner-section-label">${__("3. Choose banding sides on the shape")}</div>
                <div class="dco-corner-edges has-break" data-corner-edges>
                    ${edgeToggleHtml("edge_width_top", __("Top"), draft, locked.has("edge_width_top"))}
                    ${edgeToggleHtml("edge_width_bottom", __("Bottom"), draft, locked.has("edge_width_bottom"))}
                    ${edgeToggleHtml("edge_long_right", __("Right"), draft, locked.has("edge_long_right"))}
                    ${edgeToggleHtml("edge_long_left", __("Left"), draft, locked.has("edge_long_left"))}
                    ${edgeToggleHtml("edge_break", breakEdgeLabel(row), draft, false, "dco-edge-break-toggle")}
                    ${isClipped(row) ? edgeToggleHtml("edge_break_only", __("Break only"), draft, false, "dco-edge-break-toggle") : ""}
                </div>
            </div>`;
    }

    function syncEdgeToggleVisuals(root, draft) {
        const locked = locksAdjacentSidesForBreak(draft)
            ? new Set(breakAdjacentSides(draft.clipped_corner_position))
            : new Set();
        root.querySelectorAll("[data-corner-edge]").forEach((button) => {
            const field = button.dataset.cornerEdge;
            const checked = Boolean(draft[field]);
            const isLocked = !["edge_break", "edge_break_only"].includes(field) && locked.has(field);
            button.classList.toggle("is-checked", checked);
            button.classList.toggle("is-break-locked", isLocked);
            button.setAttribute("aria-pressed", checked ? "true" : "false");
            button.disabled = isLocked;
            const mark = button.querySelector(".dco-check-mark");
            if (mark) mark.textContent = checked ? "✓" : "";
        });
    }

    function cornerValueUpdates(config, edgeDraft) {
        const updates = [
            ["clipped_corner_position", config.position],
            ["clipped_corner_width_cm", rounded(config.cutWidth)],
            ["clipped_corner_length_cm", rounded(config.cutLength)],
            ["edge_width_top", edgeDraft.edge_width_top],
            ["edge_width_bottom", edgeDraft.edge_width_bottom],
            ["edge_long_right", edgeDraft.edge_long_right],
            ["edge_long_left", edgeDraft.edge_long_left],
        ];
        if (locksAdjacentSidesForBreak(edgeDraft)) {
            breakAdjacentSides(config.position).forEach((side) => {
                updates.push([`${side}_type_override`, ""]);
            });
        }
        // Keep a deterministic trigger order inside the atomic model update:
        // clear the opposite mode before notifying handlers about the selected one.
        if (edgeDraft.edge_break) {
            updates.push(["edge_break_only", 0], ["edge_break", 1]);
        } else if (edgeDraft.edge_break_only) {
            updates.push(["edge_break", 0], ["edge_break_only", 1]);
        } else {
            updates.push(["edge_break", 0], ["edge_break_only", 0]);
        }
        return updates;
    }

    function captureRowLocator(row) {
        return {
            reference: row,
            doctype: row && row.doctype,
            name: row && row.name,
            pieceInstanceId: String(row && row.piece_instance_id || "").trim(),
        };
    }

    function mappedRowName(name) {
        const names = frappe.model && frappe.model.new_names || {};
        let current = String(name || "").trim();
        const visited = new Set();
        while (current && names[current] && !visited.has(current)) {
            visited.add(current);
            current = String(names[current] || "").trim();
        }
        return current;
    }

    function resolveCurrentRow(frm, locator) {
        const rows = frm && frm.doc && Array.isArray(frm.doc.pieces)
            ? frm.doc.pieces
            : [];
        if (!locator || !rows.length) return null;

        let current = null;
        if (locator.pieceInstanceId) {
            current = rows.find((candidate) => (
                String(candidate && candidate.piece_instance_id || "").trim()
                === locator.pieceInstanceId
            )) || null;
        }
        if (!current && locator.reference && rows.includes(locator.reference)) {
            current = locator.reference;
        }
        if (!current) {
            const names = new Set([
                locator.name,
                locator.reference && locator.reference.name,
                mappedRowName(locator.name),
                mappedRowName(locator.reference && locator.reference.name),
            ].map((value) => String(value || "").trim()).filter(Boolean));
            current = rows.find((candidate) => names.has(String(candidate && candidate.name || "").trim())) || null;
        }
        if (!current) return null;

        locator.reference = current;
        locator.doctype = current.doctype || locator.doctype;
        locator.name = current.name || locator.name;
        locator.pieceInstanceId = String(
            current.piece_instance_id || locator.pieceInstanceId || ""
        ).trim();
        return current;
    }

    async function persistCornerValues(frm, locator, config, edgeDraft) {
        const current = resolveCurrentRow(frm, locator);
        if (!current) throw new Error("The corner piece is no longer available in the current order.");
        // Frappe assigns every key from an object-form set_value before running
        // any field handler. Commit one final snapshot so handlers never observe
        // edge_break and edge_break_only in a transient/previous combination.
        const values = Object.fromEntries(cornerValueUpdates(config, edgeDraft));
        await frappe.model.set_value(current.doctype, current.name, values);
        return resolveCurrentRow(frm, locator);
    }

    const pendingApplyStates = new WeakMap();

    function applyState(frm) {
        let state = pendingApplyStates.get(frm);
        if (!state) {
            state = { tail: Promise.resolve({ ok: true, value: null }), failure: null };
            pendingApplyStates.set(frm, state);
        }
        return state;
    }

    function queueCornerApply(frm, task) {
        const state = applyState(frm);
        const queued = state.tail.then(async () => {
            try {
                const value = await task();
                state.failure = null;
                return { ok: true, value };
            } catch (error) {
                state.failure = error;
                return { ok: false, error };
            }
        });
        state.tail = queued;
        return queued;
    }

    function flushPendingCornerApply(frm) {
        const state = pendingApplyStates.get(frm);
        if (!state) return Promise.resolve();
        const pending = state.tail;
        return pending.then((result) => {
            if (state.tail !== pending) return flushPendingCornerApply(frm);
            if (state.failure) throw state.failure;
            return result && result.value;
        });
    }

    function installStyles() {
        if (document.getElementById("dco-clipped-corner-css")) return;
        const style = document.createElement("style");
        style.id = "dco-clipped-corner-css";
        style.textContent = `
            .dco-clipped-corner-modal .modal-dialog{max-width:min(860px,94vw)!important;width:860px!important}
            .dco-clipped-corner-modal .modal-content{border:0;border-radius:18px;overflow:hidden;box-shadow:0 24px 80px rgba(15,23,42,.24)}
            .dco-clipped-corner-modal .modal-body{padding:0!important;background:var(--subtle-fg,#f6f8fa)}
            .dco-corner-editor{direction:rtl;display:grid;grid-template-columns:minmax(0,1.18fr) minmax(290px,.82fr);min-height:430px}
            .dco-corner-editor .dco-corner-preview-panel{padding:24px;background:linear-gradient(150deg,#f8fbff,#edf5fb);display:flex;flex-direction:column;gap:14px}
            .dco-corner-editor .dco-corner-preview-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
            .dco-corner-editor .dco-corner-preview-head strong{display:block;font-size:16px;color:#172033}
            .dco-corner-editor .dco-corner-preview-head span{font-size:11px;color:#64748b;line-height:1.6}
            .dco-corner-editor .dco-corner-badge{display:inline-flex!important;align-items:center;gap:5px;padding:5px 9px;border-radius:999px;background:#fff3d6;color:#825314!important;border:1px solid #efd39b;font-weight:800;white-space:nowrap}
            .dco-corner-editor .dco-corner-preview{flex:1;min-height:280px;border:1px solid #d7e2ea;border-radius:16px;background:#fff;display:flex;align-items:center;justify-content:center;padding:18px;box-shadow:0 8px 28px rgba(15,23,42,.06)}
            .dco-corner-editor .dco-corner-preview svg{width:100%;height:100%;min-height:240px;overflow:visible}
            .dco-corner-editor .dco-corner-controls{padding:21px 20px;background:var(--card-bg,#fff);border-right:1px solid var(--border-color,#e2e8f0);display:flex;flex-direction:column;gap:16px}
            .dco-corner-editor .dco-corner-section-label{font-size:11px;font-weight:900;color:#475569;margin-bottom:7px}
            .dco-corner-editor .dco-corner-position-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}
            .dco-corner-editor .dco-corner-position{border:1px solid var(--border-color,#d9e0e6);border-radius:11px;background:var(--card-bg,#fff);min-height:66px;padding:7px;cursor:pointer;display:flex;align-items:center;gap:8px;text-align:right;color:inherit}
            .dco-corner-editor .dco-corner-position:hover{border-color:#d09a35;background:#fffaf0}
            .dco-corner-editor .dco-corner-position.is-active{border-color:#c68519;background:#fff5de;color:#754900;box-shadow:0 0 0 2px rgba(198,133,25,.12)}
            .dco-corner-editor .dco-corner-position svg{width:38px;height:38px;flex:0 0 38px}
            .dco-corner-editor .dco-corner-position span{font-size:11px;font-weight:800;line-height:1.4}
            .dco-corner-editor .dco-corner-input-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px}
            .dco-corner-editor .dco-corner-input-wrap label{display:block;font-size:10px;font-weight:800;color:#64748b;margin-bottom:5px}
            .dco-corner-editor .dco-corner-input-shell{display:flex;align-items:center;border:1px solid var(--border-color,#d9e0e6);border-radius:10px;overflow:hidden;background:#fff}
            .dco-corner-editor .dco-corner-input-shell input{width:100%;border:0!important;box-shadow:none!important;min-height:40px;padding:7px 10px;font-size:16px;font-weight:800;text-align:center}
            .dco-corner-editor .dco-corner-input-shell span{padding:0 9px;color:#64748b;font-size:10px;border-right:1px solid #e7ebef;white-space:nowrap}
            .dco-corner-editor .dco-corner-equal{align-self:flex-start;border:0;background:transparent;color:var(--alm-primary, #172033);font-size:11px;font-weight:800;padding:0;cursor:pointer}
            .dco-corner-editor .dco-corner-edges{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
            .dco-corner-editor .dco-corner-edges.has-break{grid-template-columns:repeat(3,minmax(0,1fr))}
            .dco-corner-editor .dco-corner-edge-toggle{border:1px solid var(--border-color,#d9e0e6);border-radius:10px;background:var(--card-bg,#fff);min-height:40px;padding:7px 8px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px;font-size:11px;font-weight:800;color:#334155}
            .dco-corner-editor .dco-corner-edge-toggle .dco-check-mark{width:14px;text-align:center}
            .dco-corner-editor .dco-corner-edge-toggle.is-checked{background:#172033;border-color:#172033;color:#fff}
            .dco-corner-editor .dco-corner-edge-toggle.is-break-locked{opacity:.45;cursor:not-allowed}
            .dco-corner-editor .dco-corner-edge-toggle.dco-edge-break-toggle.is-checked{background:#b42318;border-color:#912018}
            .dco-corner-editor .dco-corner-help{margin-top:auto;border-radius:11px;padding:10px 11px;background:#f8fafc;border:1px solid #e2e8f0;font-size:10px;line-height:1.65;color:#52606d}
            .dco-corner-editor .dco-corner-help.is-error{background:#fff3f1;border-color:#efb5ad;color:#9d2e23}
            .dco-corner-edges-summary{display:flex;flex-direction:column;align-items:stretch;gap:3px;width:100%;border:1px dashed rgba(176,112,28,.4);border-radius:10px;background:#fffaf0;color:#8a5700;padding:6px 8px;font-size:10px;font-weight:800;line-height:1.35;cursor:pointer;text-align:right;opacity:.85}
            .dco-corner-edges-summary:hover{background:#fff3d6;border-color:rgba(176,112,28,.65);opacity:1}
            .dco-corner-edges-summary[disabled]{opacity:.7;cursor:default}
            .dco-corner-edges-summary small{font-weight:700;color:#a16207;opacity:.9}
            .dco-fast-table tr.dco-clipped-corner-row td{background:rgba(224,151,24,.045)}
            .dco-fast-table tr.dco-clipped-corner-row .dco-col-edges{background:linear-gradient(135deg,rgba(255,248,229,.78),rgba(255,252,244,.42))}
            .dco-fast-table tr.dco-clipped-corner-row:focus-within td{background:rgba(224,151,24,.085)!important}
            .dco-special-sketch-button.is-clipped-corner{border-style:solid!important;border-color:rgba(198,133,25,.5)!important;background:#fff7e6!important;color:#8a5700!important}
            .dco-special-sketch-button.is-clipped-corner>span:first-child{font-size:19px!important}
            @media(max-width:720px){.dco-clipped-corner-modal .modal-dialog{width:100vw!important;margin:0!important}.dco-corner-editor{display:flex;flex-direction:column}.dco-corner-editor .dco-corner-preview-panel{padding:14px}.dco-corner-editor .dco-corner-preview{min-height:220px}.dco-corner-editor .dco-corner-preview svg{min-height:190px}.dco-corner-editor .dco-corner-controls{border:0;border-top:1px solid #e2e8f0;padding:15px}}
        `;
        document.head.appendChild(style);
    }

    function cornerIcon(position, row) {
        const piece = {
            piece_type: pieceType(row) || CLIPPED_TYPE,
            width_cm: 100,
            length_cm: 100,
            clipped_corner_position: position,
            clipped_corner_width_cm: 34,
            clipped_corner_length_cm: 34,
        };
        return `<svg viewBox="0 0 44 44" aria-hidden="true"><polygon points="${pointsAttribute(piece, 38, 38).split(" ").map(pair => {
            const [x, y] = pair.split(",").map(Number);
            return `${x + 3},${y + 3}`;
        }).join(" ")}" fill="#fff1d1" stroke="#9a6207" stroke-width="2"/></svg>`;
    }

    function editorHtml(row) {
        const config = baseConfig(row);
        const dimensions = originalDimensions(row);
        return `
            <div class="dco-corner-editor">
                <section class="dco-corner-preview-panel">
                    <div class="dco-corner-preview-head">
                        <div>
                            <strong>${__("Piece preview on the board")}</strong>
                            <span>${__("Outer size")}: ${rounded(dimensions.width)} × ${rounded(dimensions.length)} ${__("cm")}</span>
                        </div>
                        <span class="dco-corner-badge">${typeIcon(row)} ${__("Real cut path")}</span>
                    </div>
                    <div class="dco-corner-preview" data-corner-preview></div>
                </section>
                <section class="dco-corner-controls">
                    <div>
                        <div class="dco-corner-section-label">${__("1. Choose the corner")}</div>
                        <div class="dco-corner-position-grid">
                            ${POSITIONS.map(position => `
                                <button type="button" class="dco-corner-position ${position.value === config.position ? "is-active" : ""}" data-position="${position.value}">
                                    ${cornerIcon(position.value, row)}
                                    <span>${__(position.en)}</span>
                                </button>`).join("")}
                        </div>
                    </div>
                    <div>
                        <div class="dco-corner-section-label">${__("2. Enter the remaining length of each side")}</div>
                        <div class="dco-corner-input-grid">
                            <div class="dco-corner-input-wrap">
                                <label>${__("Remaining on width side")}</label>
                                <div class="dco-corner-input-shell"><input type="number" min="0.1" step="0.1" data-corner-remaining="width" value="${rounded(config.remainingWidth)}"><span>${__("cm")}</span></div>
                            </div>
                            <div class="dco-corner-input-wrap">
                                <label>${__("Remaining on length side")}</label>
                                <div class="dco-corner-input-shell"><input type="number" min="0.1" step="0.1" data-corner-remaining="length" value="${rounded(config.remainingLength)}"><span>${__("cm")}</span></div>
                            </div>
                        </div>
                        <button type="button" class="dco-corner-equal">${__("Make both remaining lengths equal")}</button>
                    </div>
                    ${edgeControlsHtml(row)}
                    <div class="dco-corner-help" data-corner-help></div>
                </section>
            </div>`;
    }

    function readEditor(root, row) {
        const dimensions = originalDimensions(row);
        const remainingWidth = num(root.querySelector("[data-corner-remaining='width']")?.value);
        const remainingLength = num(root.querySelector("[data-corner-remaining='length']")?.value);
        return {
            position: root.querySelector(".dco-corner-position.is-active")?.dataset.position || DEFAULT_POSITION,
            remainingWidth,
            remainingLength,
            cutWidth: cutFromRemaining(dimensions.width, remainingWidth),
            cutLength: cutFromRemaining(dimensions.length, remainingLength),
            ...dimensions,
        };
    }

    function validationMessage(config) {
        if (!config.width || !config.length) {
            return __("Enter the piece width and length before editing the corner.");
        }
        if (config.remainingWidth <= 0 || config.remainingLength <= 0) {
            return __("The remaining length of each side must be greater than zero.");
        }
        if (config.remainingWidth >= config.width) {
            return __("The remaining width-side length must be smaller than the piece width.");
        }
        if (config.remainingLength >= config.length) {
            return __("The remaining length-side length must be smaller than the piece length.");
        }
        return "";
    }

    function renderPreview(root, row) {
        const config = readEditor(root, row);
        const message = validationMessage(config);
        const preview = root.querySelector("[data-corner-preview]");
        const help = root.querySelector("[data-corner-help]");
        if (help) {
            help.classList.toggle("is-error", Boolean(message));
            help.textContent = message || (__("The preview is the final cut shape. The outer rectangle remains the safe reserved area during nesting."));
        }
        if (!preview) return;

        const edgeDraft = root._cornerEdgeDraft || cloneEdgeDraft(row);
        edgeDraft.clipped_corner_position = config.position;
        edgeDraft.piece_type = pieceType(row) || CLIPPED_TYPE;
        applyEdgeBreakPolicy(edgeDraft);
        root._cornerEdgeDraft = edgeDraft;
        syncEdgeToggleVisuals(root, edgeDraft);

        const sample = {
            piece_type: pieceType(row) || CLIPPED_TYPE,
            width_cm: config.width || 100,
            length_cm: config.length || 100,
            clipped_corner_position: config.position,
            clipped_corner_width_cm: config.cutWidth,
            clipped_corner_length_cm: config.cutLength,
            edge_width_top: edgeDraft.edge_width_top,
            edge_width_bottom: edgeDraft.edge_width_bottom,
            edge_long_right: edgeDraft.edge_long_right,
            edge_long_left: edgeDraft.edge_long_left,
            edge_break: edgeDraft.edge_break,
            edge_break_only: edgeDraft.edge_break_only,
        };
        const frame = previewFrame(sample.width_cm, sample.length_cm);
        const polygon = points(sample, frame.width, frame.height)
            .map(([x, y]) => `${rounded(x + frame.x)},${rounded(y + frame.y)}`)
            .join(" ");
        const edgeMarkup = edgeBandSvgMarkup(sample, frame.width, frame.height, {
            offsetX: frame.x,
            offsetY: frame.y,
            inheritStroke: false,
            strokeWidth: 3,
        });
        const labelX = rounded(frame.x + frame.width / 2);
        const labelY = rounded(frame.y + frame.height / 2);
        preview.innerHTML = `
            <svg viewBox="0 0 420 280" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${__("{0} preview", [typeLabel(row)])}">
                <defs><pattern id="dco-corner-grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="#dfe8ef" stroke-width="1"/></pattern></defs>
                <rect x="10" y="10" width="400" height="260" rx="12" fill="url(#dco-corner-grid)" stroke="#e2e8f0"/>
                <rect x="${frame.x}" y="${frame.y}" width="${frame.width}" height="${frame.height}" fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="6 4"/>
                <polygon points="${polygon}" fill="#dff1fb" stroke="#172033" stroke-width="3" stroke-linejoin="round"/>
                ${edgeMarkup}
                <text x="${labelX}" y="${labelY - 6}" text-anchor="middle" font-size="18" font-weight="800" fill="#172033">${__("PIECE")}</text>
                <text x="${labelX}" y="${labelY + 14}" text-anchor="middle" font-size="12" fill="#536577">${rounded(config.width)} × ${rounded(config.length)} ${__("cm")}</text>
                <text x="210" y="258" text-anchor="middle" font-size="11" font-weight="700" fill="#9a6207">${positionLabel(config.position)} · ${__("remaining")} ${rounded(config.remainingWidth)} × ${rounded(config.remainingLength)} ${__("cm")}</text>
            </svg>`;
    }

    function refreshFastTable(frm) {
        if (window.AlmdinaDoorCuttingFastEntry && window.AlmdinaDoorCuttingFastEntry.render) {
            window.AlmdinaDoorCuttingFastEntry.render(frm);
        }
    }

    let activeDialog = null;

    function open(frm, row, options = {}) {
        if (!frm || !isCornerCut(row)) return;
        const locator = captureRowLocator(row);
        const currentRow = () => resolveCurrentRow(frm, locator);
        let liveRow = currentRow() || row;
        const dimensions = originalDimensions(liveRow);
        if (!dimensions.width || !dimensions.length) {
            frappe.msgprint({
                title: __("Enter dimensions first"),
                message: __("Enter the piece width and length before editing the corner."),
                indicator: "orange",
            });
            return;
        }
        liveRow = currentRow();
        if (!liveRow || !isCornerCut(liveRow)) {
            frappe.msgprint({
                title: __("Could not open corner"),
                message: __("The piece is no longer in the current measurements table. Reopen it from the table."),
                indicator: "orange",
            });
            return;
        }
        installStyles();
        const readOnly = Boolean(options.readOnly);
        // A viewer must not normalize or mutate saved row values.
        if (!readOnly) prepareRow(liveRow);

        // Prevent stacked corner dialogs from duplicate click handlers.
        if (activeDialog) {
            try { activeDialog.hide(); } catch (error) { /* closing previous dialog */ }
            activeDialog = null;
        }

        const dialog = new frappe.ui.Dialog({
            title: __("{0} {1} — {2}", [
                readOnly ? __("View") : __("Edit"),
                typeLabel(liveRow),
                __("Door piece {0}", [liveRow.piece_no || liveRow.idx || ""]),
            ]),
            fields: [{ fieldname: "corner_editor", fieldtype: "HTML" }],
            primary_action_label: readOnly
                ? (__("Close"))
                : (__("Apply corner")),
            primary_action() {
                if (readOnly) {
                    dialog.hide();
                    return Promise.resolve();
                }
                const root = dialog.$wrapper.find(".dco-corner-editor").get(0);
                if (!root) return;
                const latestRow = currentRow();
                if (!latestRow) {
                    frappe.msgprint({
                        title: __("Could not apply corner"),
                        message: __("The piece is no longer in the current measurements table. Reopen it from the table."),
                        indicator: "orange",
                    });
                    return Promise.resolve(false);
                }
                const config = readEditor(root, latestRow);
                const message = validationMessage(config);
                if (message) {
                    frappe.msgprint({ title: __("Check corner size"), message, indicator: "orange" });
                    return Promise.resolve(false);
                }

                const edgeDraft = applyEdgeBreakPolicy(
                    Object.assign(
                        cloneEdgeDraft(latestRow),
                        root._cornerEdgeDraft || {},
                        {
                            clipped_corner_position: config.position,
                            piece_type: pieceType(latestRow) || CLIPPED_TYPE,
                        }
                    )
                );
                if (typeof dialog.disable_primary_action === "function") {
                    dialog.disable_primary_action();
                }
                const apply = queueCornerApply(frm, async () => {
                    const committedRow = await persistCornerValues(frm, locator, config, edgeDraft);
                    if (!committedRow) {
                        throw new Error("The corner piece changed while its values were being applied.");
                    }
                    frm.dirty();
                    dialog.hide();
                    refreshFastTable(frm);
                    frappe.show_alert({
                        message: __("Corner and banding applied and will appear in the cutting plan."),
                        indicator: "green",
                    });
                    return committedRow;
                });
                apply.then((result) => {
                    if (typeof dialog.enable_primary_action === "function") {
                        dialog.enable_primary_action();
                    }
                    if (!result.ok) {
                        frappe.msgprint({
                            title: __("Could not apply corner"),
                            message: __("The banding changes were not fully applied. They were not saved; try again."),
                            indicator: "red",
                        });
                    }
                });
                return apply;
            },
        });
        dialog.$wrapper.addClass("dco-clipped-corner-modal");
        activeDialog = dialog;
        dialog.$wrapper.on("hidden.bs.modal.dco-clipped-corner-active", () => {
            if (activeDialog === dialog) activeDialog = null;
        });
        dialog.show();

        const field = dialog.fields_dict.corner_editor;
        field.$wrapper.html(editorHtml(liveRow));
        const root = field.$wrapper.find(".dco-corner-editor").get(0);
        root._cornerEdgeDraft = applyEdgeBreakPolicy(cloneEdgeDraft(liveRow));
        const renderCurrentPreview = () => {
            const latestRow = currentRow();
            if (latestRow) renderPreview(root, latestRow);
        };
        if (readOnly) {
            root.querySelectorAll("input,button").forEach(control => {
                control.disabled = true;
            });
            renderCurrentPreview();
            return;
        }
        root.querySelectorAll(".dco-corner-position").forEach(button => {
            button.addEventListener("click", () => {
                root.querySelectorAll(".dco-corner-position").forEach(item => item.classList.remove("is-active"));
                button.classList.add("is-active");
                if (root._cornerEdgeDraft) {
                    root._cornerEdgeDraft.clipped_corner_position = button.dataset.position || DEFAULT_POSITION;
                    applyEdgeBreakPolicy(root._cornerEdgeDraft);
                }
                renderCurrentPreview();
            });
        });
        root.querySelectorAll("[data-corner-remaining]").forEach(input => {
            input.addEventListener("input", renderCurrentPreview);
            input.addEventListener("focus", () => input.select());
        });
        root.querySelector(".dco-corner-equal")?.addEventListener("click", () => {
            const widthInput = root.querySelector("[data-corner-remaining='width']");
            const lengthInput = root.querySelector("[data-corner-remaining='length']");
            if (widthInput && lengthInput) lengthInput.value = widthInput.value;
            renderCurrentPreview();
        });
        root.querySelectorAll("[data-corner-edge]").forEach((button) => {
            button.addEventListener("click", () => {
                if (button.disabled || button.classList.contains("is-break-locked")) return;
                const latestRow = currentRow();
                if (!latestRow) return;
                const fieldname = button.dataset.cornerEdge;
                const draft = root._cornerEdgeDraft || applyEdgeBreakPolicy(cloneEdgeDraft(latestRow));
                toggleEdgeSelection(draft, fieldname);
                draft.clipped_corner_position = (
                    root.querySelector(".dco-corner-position.is-active")?.dataset.position
                    || draft.clipped_corner_position
                    || DEFAULT_POSITION
                );
                draft.piece_type = pieceType(latestRow) || CLIPPED_TYPE;
                applyEdgeBreakPolicy(draft);
                root._cornerEdgeDraft = draft;
                renderCurrentPreview();
            });
        });
        renderCurrentPreview();
    }

    function view(frm, row) {
        open(frm, row, { readOnly: true });
    }

    if (frappe.ui && frappe.ui.form && typeof frappe.ui.form.on === "function") {
        frappe.ui.form.on("Door Cutting Order", {
            before_save(frm) {
                return flushPendingCornerApply(frm);
            },
        });
    }

    window.AlmdinaClippedCornerGeometry = Object.freeze({
        TYPE: CLIPPED_TYPE,
        L_TYPE,
        positions: POSITIONS.map(position => position.value),
        breakAdjacentSides,
        applyEdgeBreakPolicy,
        toggleEdgeSelection,
        locksAdjacentSidesForBreak,
        breakEdgeLabel,
        clippedEdgePaths,
        edgeBandSvgMarkup,
        edgeSelectionSummary,
        isClipped,
        isLShaped,
        isCornerCut,
        cutStyle,
        typeLabel,
        typeIcon,
        baseConfig,
        effectiveConfig,
        pieceForQuarterTurns,
        remainingFromCut,
        cutFromRemaining,
        clampRemaining,
        adjustCutForNewTotal,
        preserveRemainingOnResize,
        resizeSnapshot,
        points,
        orderOutlinePoints,
        orderEdgePaths,
        orderEdgeBandSvgMarkup,
        orderRemainingDimensionAnchors,
        pointsAttribute,
        previewFrame,
        dxfPoints,
        positionLabel,
        summary,
    });
    window.AlmdinaClippedCornerEditor = Object.freeze({
        open,
        view,
        prepare: prepareRow,
        cornerValueUpdates,
        ensureStyles: installStyles,
        resolveChildRow(frm, row) {
            return resolveCurrentRow(frm, captureRowLocator(row));
        },
        queueChildApply: queueCornerApply,
        commitChildValues(frm, row, values) {
            const locator = captureRowLocator(row);
            return (async () => {
                const current = resolveCurrentRow(frm, locator);
                if (!current) {
                    throw new Error("The piece is no longer available in the current order.");
                }
                await frappe.model.set_value(current.doctype, current.name, values);
                return resolveCurrentRow(frm, locator);
            })();
        },
    });
})();
