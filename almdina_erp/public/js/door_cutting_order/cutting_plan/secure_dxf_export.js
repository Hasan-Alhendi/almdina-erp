(() => {
    "use strict";

    if (window.__almdinaSecureDxfExportLoaded) return;
    window.__almdinaSecureDxfExportLoaded = true;

    // AutoCAD 2000. LWPOLYLINE is not a valid R12 entity, and ezdxf drops its
    // layer when the header stays AC1009. The server still rebuilds the
    // downloaded file as AutoCAD 2010.
    const DXF_VERSION = "AC1015";
    const TOPOLOGY_SCHEMA_VERSION = 1;
    const TOPOLOGY_UNIT = "mm";
    // R12 TABLE records must declare the exact number of entries. The exporter
    // writes the base layers, GEOMETRY, three manufacturing overlay layers, and TEXT.
    const DXF_LAYER_COUNT = 9;
    const TEXT_LABEL_LAYER = "TEXT";
    const FINISHED_GEOMETRY_LAYER = "GEOMETRY";
    const SAW_CENTER_LAYER = "CUT_PATH";
    const COLLINEAR_TOLERANCE_MM = 0.05;
    const EXTRA_DOUBLE_DXF_TEXT = "دبل القشاط";
    const EXTRA_FULL_DOOR_DOUBLE_DXF_TEXT = "دبل كامل";
    const TOPOLOGY_COORDINATE_SPACE = "usable_sheet";
    const ORIGINAL_UPLOAD_SOURCES = new Set([
        "custom",
        "uploaded",
        "uploaded dxf",
        "uploaded_dxf",
        "dxf",
    ]);
    const EXTRA_OVERLAY_LAYER_BY_KIND = Object.freeze({
        liner: "Liner",
        back_groove: "Rear Groove",
        recessed_handle_cutout: "Handle Recess",
    });
    const EXTRA_OVERLAY_LAYER_COLORS = Object.freeze({
        OFFCUT: 2,
        Liner: 5,
        "Rear Groove": 3,
        "Handle Recess": 6,
    });
    const ORIGINAL_DXF_METHOD =
        "almdina_erp.almdina_erp.services.dxf_export_service.download_uploaded_dxf";
    const VALIDATED_PLAN_METHOD =
        "almdina_erp.almdina_erp.services.dxf_export_service.get_validated_dxf_plan";
    const NORMALIZE_DXF_METHOD =
        "almdina_erp.almdina_erp.services.dxf_export_service.normalize_dxf_for_autocad";

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split("{" + index + "}").join(String(value));
            });
        }
        return text;
    }

    function canExportDxf(frm = window.cur_frm) {
        const permissions = window.AlmdinaPermissions;
        return Boolean(
            permissions &&
            (
                frm && typeof permissions.canDocument === "function"
                    ? permissions.canDocument(frm, "export_dxf")
                    : permissions.can("export_dxf")
            )
        );
    }


    function buttonLabel() {
        return __("Export DXF for AutoCAD");
    }

    function num(value) {
        const result = Number(value);
        return Number.isFinite(result) ? result : 0;
    }

    function finiteCoordinate(value, field) {
        const result = Number(value);
        if (!Number.isFinite(result)) {
            throw new Error(`${field} must be a finite number.`);
        }
        return result;
    }

    function pair(code, value) {
        return `${code}\r\n${value}\r\n`;
    }

    function dxfNumber(value) {
        const number = num(value);
        return String(Math.round(number * 1000) / 1000);
    }

    function layer(name, color) {
        return (
            pair(0, "LAYER") +
            pair(2, name) +
            pair(70, 0) +
            pair(62, color) +
            pair(6, "CONTINUOUS")
        );
    }

    function line(layerName, x1, y1, x2, y2) {
        return (
            pair(0, "LINE") +
            pair(8, layerName || "0") +
            pair(10, dxfNumber(x1)) +
            pair(20, dxfNumber(y1)) +
            pair(30, 0) +
            pair(11, dxfNumber(x2)) +
            pair(21, dxfNumber(y2)) +
            pair(31, 0)
        );
    }

    function rectangle(layerName, x, y, width, height) {
        const x2 = x + width;
        const y2 = y + height;
        return (
            line(layerName, x, y, x2, y) +
            line(layerName, x2, y, x2, y2) +
            line(layerName, x2, y2, x, y2) +
            line(layerName, x, y2, x, y)
        );
    }

    function doorNumberText(piece) {
        const label = String((piece && piece.label) || "").trim();
        const primary = label.split(".")[0].trim().replace(/[^\x20-\x7E]/g, "");
        return primary || "0";
    }

    function doorNumberHeight(widthMm, heightMm) {
        const size = Math.min(Math.max(0, widthMm), Math.max(0, heightMm));
        return Math.max(8, Math.min(40, size * 0.12));
    }

    function extraAddonTextHeight(widthMm, heightMm) {
        const size = Math.min(Math.max(0, widthMm), Math.max(0, heightMm));
        return Math.max(6, Math.min(16, size * 0.08));
    }

    function extraAddonFlags(piece) {
        return {
            double: Boolean(Number(piece && piece.extra_double)),
            fullDoorDouble: Boolean(Number(piece && piece.extra_full_door_double)),
        };
    }

    function dxfAsciiText(value) {
        return Array.from(String(value || "")).map(character => {
            const code = character.codePointAt(0);
            if (code >= 0x20 && code <= 0x7E && character !== "\\") {
                return character;
            }
            return `\\U+${code.toString(16).toUpperCase().padStart(4, "0")}`;
        }).join("");
    }

    function extraAddonTextEntities(minX, minY, maxX, maxY, piece) {
        const flags = extraAddonFlags(piece);
        if (!flags.double && !flags.fullDoorDouble) return "";
        const width = Math.max(0, maxX - minX);
        const height = Math.max(0, maxY - minY);
        const textHeight = extraAddonTextHeight(width, height);
        const pad = Math.max(textHeight * 0.6, Math.min(width, height) * 0.08);
        // AutoCAD TEXT uses a baseline insert. Keep the whole glyph inside the
        // piece so the label sits on the door, not on the CUT_PATH outline.
        const baselineY = maxY - pad - textHeight;
        const leftX = minX + pad;
        const align = { halign: 0, valign: 0 };
        let entities = "";
        if (flags.fullDoorDouble) {
            entities += textEntity(
                TEXT_LABEL_LAYER,
                leftX,
                baselineY,
                textHeight,
                dxfAsciiText(EXTRA_FULL_DOOR_DOUBLE_DXF_TEXT),
                align
            );
        }
        if (flags.double) {
            const estimatedWidth = Math.min(
                Math.max(0, width - pad * 2),
                EXTRA_DOUBLE_DXF_TEXT.length * textHeight * 0.85
            );
            entities += textEntity(
                TEXT_LABEL_LAYER,
                Math.max(leftX, maxX - pad - estimatedWidth),
                baselineY,
                textHeight,
                dxfAsciiText(EXTRA_DOUBLE_DXF_TEXT),
                align
            );
        }
        return entities;
    }

    function polygonBounds(points) {
        const xs = points.map(point => point[0]);
        const ys = points.map(point => point[1]);
        return {
            minX: Math.min(...xs),
            minY: Math.min(...ys),
            maxX: Math.max(...xs),
            maxY: Math.max(...ys),
        };
    }

    function textEntity(layerName, x, y, height, content, align) {
        const halign = align && Number.isFinite(Number(align.halign)) ? Number(align.halign) : 1;
        const valign = align && Number.isFinite(Number(align.valign)) ? Number(align.valign) : 2;
        let entity = (
            pair(0, "TEXT") +
            pair(8, layerName || TEXT_LABEL_LAYER) +
            pair(10, dxfNumber(x)) +
            pair(20, dxfNumber(y)) +
            pair(30, 0) +
            pair(40, dxfNumber(height)) +
            pair(1, content) +
            pair(50, 0)
        );
        if (halign || valign) {
            entity += (
                pair(72, halign) +
                pair(11, dxfNumber(x)) +
                pair(21, dxfNumber(y)) +
                pair(31, 0) +
                pair(73, valign)
            );
        }
        return entity;
    }

    function closedPath(layerName, points) {
        if (!Array.isArray(points) || points.length < 3) return "";
        let result = "";
        points.forEach((point, index) => {
            const next = points[(index + 1) % points.length];
            result += line(layerName, point[0], point[1], next[0], next[1]);
        });
        return result;
    }

    function lwpolyline(layerName, points, closed) {
        if (!Array.isArray(points) || points.length < 2) return "";
        let result = pair(0, "LWPOLYLINE")
            + pair(100, "AcDbEntity")
            + pair(8, layerName || "0")
            + pair(100, "AcDbPolyline")
            + pair(90, points.length)
            + pair(70, closed ? 1 : 0);
        points.forEach(point => {
            result += pair(10, dxfNumber(point[0])) + pair(20, dxfNumber(point[1]));
        });
        return result;
    }

    function overlayPath(layerName, points, closed) {
        if (!Array.isArray(points) || points.length < 2) return "";
        let result = "";
        for (let index = 0; index < points.length - 1; index += 1) {
            const point = points[index];
            const next = points[index + 1];
            result += line(layerName, point[0], point[1], next[0], next[1]);
        }
        if (closed && points.length >= 3) {
            const last = points[points.length - 1];
            const first = points[0];
            result += line(layerName, last[0], last[1], first[0], first[1]);
        }
        return result;
    }

    function overlayPolyline(points, field) {
        if (!Array.isArray(points) || points.length < 2) {
            throw new Error(`${field} must contain at least two points.`);
        }
        return points.map((point, index) => {
            if (!Array.isArray(point) || point.length !== 2) {
                throw new Error(`${field}[${index}] must be an [x, y] point.`);
            }
            return [
                finiteCoordinate(point[0], `${field}[${index}][0]`),
                finiteCoordinate(point[1], `${field}[${index}][1]`),
            ];
        });
    }

    function cutLayerForPiece(piece) {
        return String(piece && piece.resource_kind || "FULL_BOARD").toUpperCase() === "OFFCUT"
            ? "OFFCUT"
            : "CUT_PATH";
    }

    function topologyPolygon(points, field) {
        if (!Array.isArray(points) || points.length < 3) {
            throw new Error(`${field} must contain at least three points.`);
        }
        return points.map((point, index) => {
            if (!Array.isArray(point) || point.length !== 2) {
                throw new Error(`${field}[${index}] must be an [x, y] point.`);
            }
            return [
                finiteCoordinate(point[0], `${field}[${index}][0]`),
                finiteCoordinate(point[1], `${field}[${index}][1]`),
            ];
        });
    }

    function persistedTopology(piece) {
        if (!Object.prototype.hasOwnProperty.call(piece || {}, "geometry")) return null;
        const geometry = piece.geometry;
        if (!geometry || typeof geometry !== "object" || Array.isArray(geometry)) {
            throw new Error("Persisted DXF geometry must be an object.");
        }
        if (geometry.schema_version !== TOPOLOGY_SCHEMA_VERSION) {
            throw new Error("Persisted DXF geometry schema version is unsupported.");
        }
        if (geometry.unit !== TOPOLOGY_UNIT) {
            throw new Error("Persisted DXF geometry unit must be mm.");
        }
        if (geometry.coordinate_space !== TOPOLOGY_COORDINATE_SPACE) {
            throw new Error("Persisted DXF geometry coordinate space is unsupported.");
        }
        if (!Array.isArray(geometry.holes)) {
            throw new Error("Persisted DXF geometry holes must be an array.");
        }
        return {
            outer: topologyPolygon(geometry.outer, "geometry.outer"),
            holes: geometry.holes.map((hole, index) =>
                topologyPolygon(hole, `geometry.holes[${index}]`)
            ),
        };
    }

    function overlayLayerName(overlay) {
        const kind = String((overlay && overlay.kind) || "").trim();
        const mapped = EXTRA_OVERLAY_LAYER_BY_KIND[kind];
        if (mapped) return mapped;
        const layer = String((overlay && overlay.layer) || "").trim();
        return layer || "";
    }

    function positiveKerf(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
    }

    function cutterDiameterMm(plan) {
        const millimetres = positiveKerf(plan && plan.kerf_mm);
        const centimetres = positiveKerf(plan && plan.kerf_cm);
        const fromCentimetres = centimetres == null ? null : centimetres * 10;
        if (millimetres != null && fromCentimetres != null && Math.abs(millimetres - fromCentimetres) > 0.05) {
            const error = new Error(translate(
                "Saw blade thickness conflict: {0} mm versus {1} mm in the cutting plan. DXF was not exported.",
                [millimetres, fromCentimetres]
            ));
            error.linerExport = true;
            error.code = "cutter_diameter_conflict";
            return error;
        }
        if (millimetres != null) return millimetres;
        if (fromCentimetres != null) return fromCentimetres;
        return 0;
    }

    function linerExportError(piece, code, addon) {
        const noun = translate(addon && addon.nounMessageId || "the liner");
        const messages = {
            cutter_diameter_invalid: "Specify a saw blade thickness above zero before exporting {0} toolpaths.",
            liner_narrower_than_cutter: "The width of {0} is less than the saw blade thickness.",
            liner_extension_hits_piece: "The {0} cutter extension overlaps an adjacent piece.",
            liner_extension_unsafe: "Could not extend the {0} toolpath to the cutting line.",
            strip_outside: "The {0} strip extends beyond the door.",
            offset_invalid: "The {0} offset is invalid.",
            width_invalid: "The {0} width is invalid.",
            side_unavailable: "The {0} side is unavailable for this door.",
            liner_start_invalid: "The {0} start position is invalid.",
            liner_length_invalid: "The {0} length is invalid.",
            liner_span_exceeds_edge: "The start and length of {0} exceed the side length.",
            liner_flat_end_unmachinable: "The flat end cannot be machined by a circular cutter in one pass, or the region is shorter than the cutter diameter.",
            liner_span_on_corner: "The {0} start or end falls on a corner without a single direction for a flat end.",
        };
        const label = String((piece && (piece.label || piece.piece_no || piece.id)) || "").split(".")[0] || "?";
        const message = translate(messages[code] || code, [noun]);
        const error = new Error(translate("Door {0}: {1}", [label, message]));
        error.linerExport = true;
        error.code = code;
        return error;
    }

    function usableBoardMm(plan, sheet, appliedTrim) {
        const fullW = num(sheet.full_width_cm || plan.full_board_width_cm) * 10;
        const fullH = num(sheet.full_length_cm || plan.full_board_length_cm) * 10;
        const trim = appliedTrim || { width: 0, length: 0 };
        return {
            minX: -num(trim.width),
            minY: -num(trim.length),
            maxX: fullW - num(trim.width),
            maxY: fullH - num(trim.length),
        };
    }

    function exportOverlays(piece, kerfMm, board) {
        const overlays = Array.isArray(piece && piece.overlays) ? piece.overlays.slice() : [];
        const engine = window.AlmdinaMachiningOverlay;
        if (engine && typeof engine.completeToolpaths === "function") {
            const completed = engine.completeToolpaths(piece, overlays, kerfMm, board);
            if (completed && completed.error) {
                throw linerExportError(piece, completed.error.code, completed.error.addon);
            }
            return (completed && completed.overlays) || overlays;
        }
        if (overlays.some(item => item && item.kind === "liner")) return overlays;
        const requiresLiner = Boolean(String(piece && piece.liner_reference_side || "").trim())
            && num(piece && piece.liner_width_cm) > 0;
        const liner = window.AlmdinaLinerGeometry;
        if (!liner || typeof liner.syntheticOverlay !== "function") {
            if (requiresLiner) throw linerExportError(piece, "liner_extension_unsafe");
            return overlays;
        }
        const synthetic = liner.syntheticOverlay(Object.assign({}, piece, {
            kerf_mm: num(kerfMm),
            board: board || null,
        }));
        if (requiresLiner && (!synthetic || synthetic.error)) {
            throw linerExportError(piece, (synthetic && synthetic.error) || "liner_extension_unsafe");
        }
        if (!synthetic || synthetic.error) return overlays;
        return overlays.concat(synthetic);
    }

    function persistedOverlays(piece, kerfMm, board) {
        const overlays = exportOverlays(piece, kerfMm, board);
        return overlays.map((overlay, index) => {
            const layerName = overlayLayerName(overlay);
            if (!layerName) {
                throw new Error(`overlays[${index}].kind must map to a DXF overlay layer.`);
            }
            const geometry = overlay && overlay.geometry;
            if (!geometry || typeof geometry !== "object" || Array.isArray(geometry)) {
                throw new Error(`overlays[${index}].geometry must be an object.`);
            }
            if (geometry.schema_version !== TOPOLOGY_SCHEMA_VERSION) {
                throw new Error(`overlays[${index}] geometry schema version is unsupported.`);
            }
            if (geometry.unit !== TOPOLOGY_UNIT) {
                throw new Error(`overlays[${index}] geometry unit must be mm.`);
            }
            if (geometry.coordinate_space !== TOPOLOGY_COORDINATE_SPACE) {
                throw new Error(`overlays[${index}] geometry coordinate space is unsupported.`);
            }
            if (Array.isArray(geometry.holes) && geometry.holes.length) {
                throw new Error(`overlays[${index}] must not use holes.`);
            }
            const usesPath = Array.isArray(geometry.path);
            const path = usesPath ? geometry.path : geometry.outer;
            return {
                kind: String(overlay.kind || ""),
                layer: layerName,
                closed: usesPath
                    ? Boolean(geometry.closed) && Array.isArray(path) && path.length >= 3
                    : Array.isArray(path) && path.length >= 3,
                toolpath: Boolean(geometry.toolpath) && !geometry.closed,
                path: overlayPolyline(path, `overlays[${index}].geometry.path`),
            };
        });
    }

    function hasOwn(source, key) {
        return Boolean(source) && Object.prototype.hasOwnProperty.call(source, key);
    }

    function sheetTrimCm(plan, sheet, axis) {
        // Same contract as the preview: piece x/y are usable-frame centimetres.
        // Physical millimetres add this trim once. A stored 0 is real. A missing
        // sheet trim is recovered from full - usable before the plan-level 0,
        // which is the adaptive decision and not each board's realized margin.
        const trimKey = axis === "x" ? "applied_trim_width_cm" : "applied_trim_length_cm";
        const fullKey = axis === "x" ? "full_width_cm" : "full_length_cm";
        const usableKey = axis === "x" ? "usable_width_cm" : "usable_length_cm";
        const sizeKey = axis === "x" ? "w" : "h";
        const planFullKey = axis === "x" ? "full_board_width_cm" : "full_board_length_cm";
        const planUsableKey = axis === "x" ? "usable_board_width_cm" : "usable_board_length_cm";
        if (hasOwn(sheet, trimKey)) return Math.max(0, num(sheet[trimKey]));
        const sheetFull = num(sheet && sheet[fullKey]);
        const sheetUsable = num(sheet && sheet[usableKey]) || num(sheet && sheet[sizeKey]);
        if (sheetFull > sheetUsable && sheetUsable > 0) return (sheetFull - sheetUsable) / 2;
        if (hasOwn(plan, trimKey)) return Math.max(0, num(plan[trimKey]));
        const planFull = num(plan && plan[planFullKey]);
        const planUsable = num(plan && plan[planUsableKey]);
        if (planFull > planUsable && planUsable > 0) return (planFull - planUsable) / 2;
        return Math.max(0, num(plan && plan.trim_cm));
    }

    function appliedTrimMm(plan, sheet) {
        return {
            width: sheetTrimCm(plan, sheet, "x") * 10,
            length: sheetTrimCm(plan, sheet, "y") * 10,
        };
    }

    function topologyDxfPoints(points, { offsetX, offsetY, fullHeight, appliedTrim }) {
        // Persisted topology uses usable-sheet coordinates: top-left origin, x right,
        // y down. DXF uses the physical sheet's bottom-left origin, x right, y up.
        return points.map(([x, y]) => [
            offsetX + appliedTrim.width + x,
            offsetY + fullHeight - appliedTrim.length - y,
        ]);
    }

    function openRing(points) {
        const ring = (points || []).map(point => [num(point[0]), num(point[1])]);
        if (ring.length >= 2 && Math.hypot(ring[0][0] - ring[ring.length - 1][0], ring[0][1] - ring[ring.length - 1][1]) <= 1e-9) {
            ring.pop();
        }
        const cleaned = [];
        ring.forEach(point => {
            const previous = cleaned[cleaned.length - 1];
            if (!previous || Math.hypot(point[0] - previous[0], point[1] - previous[1]) > 1e-6) {
                cleaned.push(point);
            }
        });
        if (cleaned.length >= 2) {
            const first = cleaned[0];
            const last = cleaned[cleaned.length - 1];
            if (Math.hypot(first[0] - last[0], first[1] - last[1]) <= 1e-6) cleaned.pop();
        }
        return cleaned;
    }

    function leftNormal(start, end) {
        const dx = end[0] - start[0];
        const dy = end[1] - start[1];
        const length = Math.hypot(dx, dy) || 1;
        return [-dy / length, dx / length];
    }

    function pointInRing(point, ring) {
        const x = point[0];
        const y = point[1];
        let inside = false;
        for (let index = 0; index < ring.length; index += 1) {
            const start = ring[index];
            const end = ring[(index + 1) % ring.length];
            const dx = end[0] - start[0];
            const dy = end[1] - start[1];
            const length = Math.hypot(dx, dy) || 1;
            const along = ((x - start[0]) * dx + (y - start[1]) * dy) / (length * length);
            if (along >= -1e-9 && along <= 1 + 1e-9) {
                const px = start[0] + along * dx;
                const py = start[1] + along * dy;
                if (Math.hypot(x - px, y - py) <= 1e-6) return true;
            }
            if ((start[1] > y) === (end[1] > y)) continue;
            const crossing = start[0] + (y - start[1]) * (end[0] - start[0]) / (end[1] - start[1]);
            if (crossing > x) inside = !inside;
        }
        return inside;
    }

    function isMaterial(point, shapes) {
        return shapes.some(shape => (
            pointInRing(point, shape.outer)
            && !shape.holes.some(hole => pointInRing(point, hole))
        ));
    }

    function wasteSign(ring, shapes, radius) {
        let start = ring[0];
        let end = ring[1];
        let best = -1;
        ring.forEach((point, index) => {
            const next = ring[(index + 1) % ring.length];
            const length = Math.hypot(next[0] - point[0], next[1] - point[1]);
            if (length > best) {
                best = length;
                start = point;
                end = next;
            }
        });
        const normal = leftNormal(start, end);
        const midpoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
        const probe = Math.min(1, radius * 0.5);
        const left = [midpoint[0] + normal[0] * probe, midpoint[1] + normal[1] * probe];
        const right = [midpoint[0] - normal[0] * probe, midpoint[1] - normal[1] * probe];
        const leftMaterial = isMaterial(left, shapes);
        const rightMaterial = isMaterial(right, shapes);
        if (leftMaterial && !rightMaterial) return -1;
        if (rightMaterial && !leftMaterial) return 1;
        if (pointInRing(left, ring)) return leftMaterial ? -1 : 1;
        return rightMaterial ? 1 : -1;
    }

    function offsetClosed(ring, distance, sign) {
        const shifted = ring.map((point, index) => {
            const next = ring[(index + 1) % ring.length];
            const normal = leftNormal(point, next);
            const shift = [sign * normal[0] * distance, sign * normal[1] * distance];
            return [
                [point[0] + shift[0], point[1] + shift[1]],
                [next[0] + shift[0], next[1] + shift[1]],
            ];
        });
        return shifted.map((segment, index) => {
            const previous = shifted[(index - 1 + shifted.length) % shifted.length];
            const joint = offsetIntersection(previous, segment);
            return joint || segment[0];
        });
    }

    function offsetIntersection(first, second) {
        const start = first[0];
        const end = first[1];
        const otherStart = second[0];
        const otherEnd = second[1];
        const direction = [end[0] - start[0], end[1] - start[1]];
        const other = [otherEnd[0] - otherStart[0], otherEnd[1] - otherStart[1]];
        const denominator = direction[0] * other[1] - direction[1] * other[0];
        if (Math.abs(denominator) <= 1e-9) return null;
        const step = (
            (otherStart[0] - start[0]) * other[1]
            - (otherStart[1] - start[1]) * other[0]
        ) / denominator;
        return [start[0] + direction[0] * step, start[1] + direction[1] * step];
    }

    function finishedEdgeOnBoard(start, end, board) {
        if (!board) return false;
        const sides = [
            [0, num(board.minX)],
            [0, num(board.maxX)],
            [1, num(board.minY)],
            [1, num(board.maxY)],
        ];
        return sides.some(([axis, value]) => (
            Math.abs(start[axis] - value) <= COLLINEAR_TOLERANCE_MM
            && Math.abs(end[axis] - value) <= COLLINEAR_TOLERANCE_MM
        ));
    }

    function cutterCenterSegments(shapes, radius, board) {
        const safeRadius = Math.max(0, num(radius));
        const prepared = shapes.map(shape => ({
            outer: openRing(shape.outer),
            holes: (shape.holes || []).map(openRing).filter(hole => hole.length >= 3),
        })).filter(shape => shape.outer.length >= 3);
        const segments = [];
        prepared.forEach(shape => {
            [shape.outer].concat(shape.holes).forEach(ring => {
                const offset = safeRadius <= COLLINEAR_TOLERANCE_MM
                    ? ring
                    : offsetClosed(ring, safeRadius, wasteSign(ring, prepared, safeRadius));
                if (offset.length < 3) return;
                ring.forEach((start, index) => {
                    const finishedEnd = ring[(index + 1) % ring.length];
                    if (finishedEdgeOnBoard(start, finishedEnd, board)) return;
                    const offsetStart = offset[index];
                    const offsetEnd = offset[(index + 1) % offset.length];
                    if (Math.hypot(offsetEnd[0] - offsetStart[0], offsetEnd[1] - offsetStart[1]) > COLLINEAR_TOLERANCE_MM) {
                        segments.push([offsetStart, offsetEnd]);
                    }
                });
            });
        });
        return mergeCollinear(segments);
    }

    function mergeCollinear(segments) {
        const unused = new Set(segments.map((_, index) => index));
        const merged = [];
        while (unused.size) {
            const seedIndex = unused.values().next().value;
            unused.delete(seedIndex);
            const origin = segments[seedIndex][0];
            const end = segments[seedIndex][1];
            const dx = end[0] - origin[0];
            const dy = end[1] - origin[1];
            const length = Math.hypot(dx, dy);
            if (length <= COLLINEAR_TOLERANCE_MM) continue;
            const direction = [dx / length, dy / length];
            const normal = [-direction[1], direction[0]];
            const cluster = [[origin, end]];
            Array.from(unused).forEach(otherIndex => {
                const start = segments[otherIndex][0];
                const finish = segments[otherIndex][1];
                const lineDistance = point => Math.abs(
                    (point[0] - origin[0]) * normal[0] + (point[1] - origin[1]) * normal[1]
                );
                if (lineDistance(start) > COLLINEAR_TOLERANCE_MM || lineDistance(finish) > COLLINEAR_TOLERANCE_MM) return;
                const otherDx = finish[0] - start[0];
                const otherDy = finish[1] - start[1];
                const otherLength = Math.hypot(otherDx, otherDy);
                if (otherLength <= COLLINEAR_TOLERANCE_MM) {
                    unused.delete(otherIndex);
                    return;
                }
                const sine = Math.abs(direction[0] * otherDy - direction[1] * otherDx) / otherLength;
                if (sine > COLLINEAR_TOLERANCE_MM) return;
                cluster.push([start, finish]);
                unused.delete(otherIndex);
            });
            const intervals = cluster.map(([start, finish]) => {
                const startT = (start[0] - origin[0]) * direction[0] + (start[1] - origin[1]) * direction[1];
                const endT = (finish[0] - origin[0]) * direction[0] + (finish[1] - origin[1]) * direction[1];
                return [Math.min(startT, endT), Math.max(startT, endT)];
            }).sort((left, right) => left[0] - right[0]);
            const spans = [];
            intervals.forEach(([startT, endT]) => {
                const current = spans[spans.length - 1];
                if (!current || startT > current[1] + COLLINEAR_TOLERANCE_MM) spans.push([startT, endT]);
                else current[1] = Math.max(current[1], endT);
            });
            spans.forEach(([startT, endT]) => {
                if (endT - startT <= COLLINEAR_TOLERANCE_MM) return;
                merged.push([
                    [origin[0] + direction[0] * startT, origin[1] + direction[1] * startT],
                    [origin[0] + direction[0] * endT, origin[1] + direction[1] * endT],
                ]);
            });
        }
        return merged;
    }

    function glassOpeningMissing(piece) {
        if (String((piece && piece.piece_type) || "") !== "Glass") return false;
        const margin = Number(piece && piece.glass_margin_mm);
        if (!(margin > 0)) return false;
        const persisted = piece.geometry && Array.isArray(piece.geometry.holes)
            ? piece.geometry.holes
            : null;
        if (persisted && persisted.length) return false;
        const local = piece.glass_hole_local_mm;
        return !(Array.isArray(local) && local.length >= 3);
    }

    function assertRequiredGlassOpenings(plan) {
        (plan.sheets || []).forEach(sheet => {
            (sheet.pieces || []).forEach(piece => {
                if (!glassOpeningMissing(piece)) return;
                const error = new Error(
                    "The Glass opening is missing from this cutting plan. Recalculate the system plan before exporting DXF."
                );
                error.glassOpening = true;
                throw error;
            });
        });
    }

    function finishedRings(piece, placement) {
        const topology = persistedTopology(piece);
        if (topology) {
            return {
                outer: topologyDxfPoints(topology.outer, placement),
                holes: topology.holes.map(hole => topologyDxfPoints(hole, placement)),
            };
        }
        const pieceWidth = num(piece.w) * 10;
        const pieceHeight = num(piece.h) * 10;
        const { offsetX, offsetY, fullHeight, appliedTrim } = placement;
        const x = offsetX + appliedTrim.width + num(piece.x) * 10;
        const y = offsetY + fullHeight - appliedTrim.length - num(piece.y) * 10 - pieceHeight;
        const clippedGeometry = window.AlmdinaClippedCornerGeometry;
        const shapeOutput = window.AlmdinaShapeOutputContract;
        const clipped = clippedGeometry && clippedGeometry.isCornerCut(piece);
        const exactSpecial = shapeOutput && shapeOutput.hasExactCutPath(piece);
        const cutPath = clipped
            ? clippedGeometry.dxfPoints(piece, x, y, pieceWidth, pieceHeight)
            : (exactSpecial
                ? shapeOutput.dxfPoints(piece, x, y, pieceWidth, pieceHeight)
                : null);
        const outer = cutPath || [
            [x, y],
            [x + pieceWidth, y],
            [x + pieceWidth, y + pieceHeight],
            [x, y + pieceHeight],
        ];
        const ring = piece && piece.glass_hole_local_mm;
        const holes = !cutPath && Array.isArray(ring) && ring.length >= 3
            ? [ring.map(point => [x + num(point[0]), y + pieceHeight - num(point[1])])]
            : [];
        return { outer, holes };
    }

    function linerRegionPoints(piece, placement, spec) {
        const liner = window.AlmdinaLinerGeometry;
        const side = spec ? spec.side : piece && piece.liner_reference_side;
        const offset = spec ? spec.offsetCm : piece && piece.liner_offset_cm;
        const width = spec ? spec.widthCm : piece && piece.liner_width_cm;
        const start = spec ? spec.startCm : piece && piece.liner_start_cm;
        const length = spec ? spec.lengthCm : piece && piece.liner_length_cm;
        if (!liner || typeof liner.regionPolygonMm !== "function" || typeof liner.pieceFromRow !== "function") return null;
        if (!String(side || "").trim() || !(num(width) > 0)) return null;
        let linerPiece;
        let local;
        try {
            linerPiece = liner.pieceFromRow(Object.assign({}, piece, {
                liner_reference_side: side,
                liner_offset_cm: offset,
                liner_width_cm: width,
            }));
            local = liner.regionPolygonMm(linerPiece, side, offset, width, start, length);
        } catch (error) {
            return null;
        }
        if (!Array.isArray(local) || local.length < 3 || typeof liner.transformPoint !== "function") return null;
        // A saved physical orientation is authoritative for imported DXF.
        // The legacy bbox flag remains the fallback for old/System plans.
        const turns = Number.isInteger(piece.rotation_quarter_turns)
            ? piece.rotation_quarter_turns
            : (Number.isInteger(piece.corner_rotation_quarter_turns)
                ? piece.corner_rotation_quarter_turns : (piece.rotated ? 1 : 0));
        const mirrored = Boolean(piece.corner_mirrored);
        const originX = num(piece.x) * 10;
        const originY = num(piece.y) * 10;
        const placed = local.map(point => {
            const next = liner.transformPoint(point, mirrored, turns, linerPiece.widthCm * 10, linerPiece.lengthCm * 10);
            return [next[0] + originX, next[1] + originY];
        });
        return topologyDxfPoints(placed, placement);
    }

    function buildDxf(plan, options) {
        const includeSawCenters = Boolean(options && options.includeSawCenters);
        const cutterMm = cutterDiameterMm(plan);
        if (cutterMm && cutterMm.linerExport) throw cutterMm;
        assertRequiredGlassOpenings(plan);
        const sheets = plan.sheets || [];
        const perRow = 2;
        const gapMm = 200;
        const maxWidth = Math.max(0, ...sheets.map(sheet => num(sheet.full_width_cm || plan.full_board_width_cm) * 10));
        const maxHeight = Math.max(0, ...sheets.map(sheet => num(sheet.full_length_cm || plan.full_board_length_cm) * 10));
        let entities = "";
        let extmaxX = 0;
        let extmaxY = 0;

        function overlayObstacles(sheet, piece) {
            const liner = window.AlmdinaLinerGeometry;
            const samePiece = liner && typeof liner.samePlacedPiece === "function"
                ? liner.samePlacedPiece
                : ((left, right) => left === right);
            return (sheet.pieces || []).filter(other => !samePiece(other, piece)).map(other => {
                const polygon = liner && typeof liner.obstaclePolygonMm === "function"
                    ? liner.obstaclePolygonMm(other)
                    : (liner && typeof liner.placedPolygonMm === "function"
                        ? liner.placedPolygonMm(other)
                        : []);
                if (polygon.length >= 3) return { polygon };
                return {
                    minX: num(other.x) * 10,
                    minY: num(other.y) * 10,
                    maxX: (num(other.x) + num(other.w)) * 10,
                    maxY: (num(other.y) + num(other.h)) * 10,
                };
            });
        }

        function emitOverlayEntity(overlay, transform, sheet, piece) {
            const points = topologyDxfPoints(overlay.path, transform);
            if (!overlay.toolpath) return overlayPath(overlay.layer, points, overlay.closed);
            const liner = window.AlmdinaLinerGeometry;
            // Design and manufacturing both refuse unsafe liner extensions.
            // CUT_PATH separation/trim stays manufacturing-only via includeSawCenters.
            if (liner && typeof liner.extensionConflict === "function") {
                const trim = transform.appliedTrim || { width: 0, length: 0 };
                const conflict = liner.extensionConflict(
                    overlay.path,
                    cutterMm,
                    usableBoardMm(plan, sheet, trim),
                    overlayObstacles(sheet, piece)
                );
                if (conflict) throw linerExportError(piece, conflict);
            }
            return lwpolyline(overlay.layer, points);
        }

        sheets.forEach((sheet, index) => {
            const fullWidth = num(sheet.full_width_cm || plan.full_board_width_cm) * 10;
            const fullHeight = num(sheet.full_length_cm || plan.full_board_length_cm) * 10;
            const offsetX = (index % perRow) * (maxWidth + gapMm);
            const offsetY = Math.floor(index / perRow) * (maxHeight + gapMm);
            const appliedTrim = appliedTrimMm(plan, sheet);
            extmaxX = Math.max(extmaxX, offsetX + fullWidth);
            extmaxY = Math.max(extmaxY, offsetY + fullHeight);

            entities += rectangle("SHEET_OUTLINE", offsetX, offsetY, fullWidth, fullHeight);
            const placement = { offsetX, offsetY, fullHeight, appliedTrim };
            const shapes = [];

            (sheet.pieces || []).forEach(piece => {
                // Finished size stays on the optimizer coordinates. The saw center
                // is derived from that ring; the kerf gap itself is not rewritten.
                const rings = finishedRings(piece, placement);
                shapes.push(rings);
                entities += closedPath(FINISHED_GEOMETRY_LAYER, rings.outer);
                rings.holes.forEach(hole => {
                    entities += closedPath(FINISHED_GEOMETRY_LAYER, hole);
                });
                if (cutLayerForPiece(piece) === "OFFCUT") {
                    entities += closedPath("OFFCUT", rings.outer);
                    rings.holes.forEach(hole => {
                        entities += closedPath("OFFCUT", hole);
                    });
                }
                const overlays = persistedOverlays(
                    piece,
                    cutterMm,
                    usableBoardMm(plan, sheet, appliedTrim)
                );
                overlays.forEach(overlay => {
                    entities += emitOverlayEntity(overlay, placement, sheet, piece);
                });
                const regionEngine = window.AlmdinaMachiningOverlay;
                const regionAddons = regionEngine && Array.isArray(regionEngine.ADDONS)
                    ? regionEngine.ADDONS
                    : [{ kind: "liner" }];
                const regionEmitted = new Set();
                regionAddons.forEach(addon => {
                    const spec = regionEngine && typeof regionEngine.specFrom === "function"
                        ? regionEngine.specFrom(piece, addon.kind)
                        : null;
                    const region = linerRegionPoints(piece, placement, spec);
                    if (!region) return;
                    entities += lwpolyline(FINISHED_GEOMETRY_LAYER, region, true);
                    regionEmitted.add(addon.kind);
                });
                overlays.forEach(overlay => {
                    if (overlay.toolpath || !overlay.closed) return;
                    if (overlay.kind && regionEmitted.has(overlay.kind)) return;
                    entities += lwpolyline(
                        FINISHED_GEOMETRY_LAYER,
                        topologyDxfPoints(overlay.path, placement),
                        true
                    );
                });
                const bounds = polygonBounds(rings.outer);
                entities += textEntity(
                    TEXT_LABEL_LAYER,
                    (bounds.minX + bounds.maxX) / 2,
                    (bounds.minY + bounds.maxY) / 2,
                    doorNumberHeight(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY),
                    doorNumberText(piece)
                );
                entities += extraAddonTextEntities(
                    bounds.minX,
                    bounds.minY,
                    bounds.maxX,
                    bounds.maxY,
                    piece
                );
            });
            const physicalBoard = {
                minX: offsetX,
                minY: offsetY,
                maxX: offsetX + fullWidth,
                maxY: offsetY + fullHeight,
            };
            // Separation/trim CUT_PATH is manufacturing-only after plan approval.
            if (includeSawCenters) {
                cutterCenterSegments(shapes, num(cutterMm) / 2, physicalBoard).forEach(segment => {
                    entities += line(SAW_CENTER_LAYER, segment[0][0], segment[0][1], segment[1][0], segment[1][1]);
                });
            }
        });

        let dxf = "";
        dxf += pair(0, "SECTION") + pair(2, "HEADER");
        dxf += pair(9, "$ACADVER") + pair(1, DXF_VERSION);
        dxf += pair(9, "$EXTMIN") + pair(10, 0) + pair(20, 0) + pair(30, 0);
        dxf += pair(9, "$EXTMAX") + pair(10, dxfNumber(extmaxX)) + pair(20, dxfNumber(extmaxY)) + pair(30, 0);
        dxf += pair(0, "ENDSEC");

        dxf += pair(0, "SECTION") + pair(2, "TABLES");
        dxf += pair(0, "TABLE") + pair(2, "LTYPE") + pair(70, 1);
        dxf += pair(0, "LTYPE") + pair(2, "CONTINUOUS") + pair(70, 0) + pair(3, "Solid line") + pair(72, 65) + pair(73, 0) + pair(40, 0);
        dxf += pair(0, "ENDTAB");
        dxf += pair(0, "TABLE") + pair(2, "LAYER") + pair(70, DXF_LAYER_COUNT);
        dxf += layer("0", 7) + layer("SHEET_OUTLINE", 8) + layer("CUT_PATH", 1)
            + layer("OFFCUT", EXTRA_OVERLAY_LAYER_COLORS.OFFCUT)
            + layer(FINISHED_GEOMETRY_LAYER, 4);
        dxf += layer("Liner", EXTRA_OVERLAY_LAYER_COLORS.Liner)
            + layer("Rear Groove", EXTRA_OVERLAY_LAYER_COLORS["Rear Groove"])
            + layer("Handle Recess", EXTRA_OVERLAY_LAYER_COLORS["Handle Recess"]);
        dxf += layer(TEXT_LABEL_LAYER, 7);
        dxf += pair(0, "ENDTAB") + pair(0, "ENDSEC");

        dxf += pair(0, "SECTION") + pair(2, "BLOCKS") + pair(0, "ENDSEC");
        dxf += pair(0, "SECTION") + pair(2, "ENTITIES") + entities + pair(0, "ENDSEC");
        dxf += pair(0, "EOF");
        return dxf;
    }

    function validateDxfText(content) {
        if (!content || typeof content !== "string") {
            throw new Error("DXF content is empty.");
        }
        if (content.includes("NaN") || content.includes("Infinity") || content.includes("undefined") || content.includes("null")) {
            throw new Error("DXF contains an invalid numeric/value token.");
        }
        if (!content.includes(`$ACADVER\r\n1\r\n${DXF_VERSION}\r\n`)) {
            throw new Error("DXF AutoCAD version header is missing.");
        }
        if (!content.includes("0\r\nSECTION\r\n2\r\nENTITIES\r\n")) {
            throw new Error("DXF ENTITIES section is missing.");
        }
        if (!content.includes("0\r\nLINE\r\n")) {
            throw new Error("DXF contains no LINE geometry.");
        }
        if (!content.endsWith("0\r\nEOF\r\n")) {
            throw new Error("DXF EOF marker is missing.");
        }
        const lines = content.split("\r\n");
        if (lines[lines.length - 1] === "") lines.pop();
        if (lines.length % 2 !== 0) {
            throw new Error("DXF group-code/value pairs are incomplete.");
        }
    }

    function preferOriginalUpload(options) {
        // Server workspace contract is authoritative. Missing flag keeps the
        // historical "download attached bytes" path for older payloads.
        if (options && Object.prototype.hasOwnProperty.call(options, "preferOriginalUpload")) {
            return options.preferOriginalUpload !== false;
        }
        if (options && options.originalIsManufacturingReady === false) {
            return false;
        }
        return true;
    }

    function shouldDownloadOriginalUpload(planSource, options) {
        const normalized = String(planSource || "").trim().toLowerCase();
        if (ORIGINAL_UPLOAD_SOURCES.has(normalized)) {
            // Custom/uploaded tab: original design file before approval, or when
            // the approved upload already embeds manufacturing-ready cut paths.
            // After approval with Absent saw centers, regenerate instead.
            return preferOriginalUpload(options);
        }
        if (normalized === "approved") {
            if (!(options && options.hasOriginalFile)) return false;
            return preferOriginalUpload(options);
        }
        return false;
    }

    function decodeBase64Bytes(value) {
        const binary = atob(String(value || ""));
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) {
            bytes[index] = binary.charCodeAt(index);
        }
        return bytes;
    }

    function download(filename, content, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        setTimeout(() => {
            document.body.removeChild(anchor);
            URL.revokeObjectURL(url);
        }, 500);
    }

    function safeName(value) {
        return String(value || "door_cutting_order").replace(/[^\w\-]+/g, "_");
    }

    function orderRowForPlanPiece(rows, piece) {
        const sourceNo = Math.floor(Number(piece && piece.source_piece_no));
        const group = sourceNo >= 1
            ? sourceNo
            : Math.floor(Number(String((piece && piece.label) || "").split(".")[0]));
        if (!(group >= 1) || group > rows.length) return null;
        return rows[group - 1] || null;
    }

    function applyManufacturingNotch(piece, frm, row) {
        const liner = window.AlmdinaLinerGeometry;
        if (!row || !liner || typeof liner.contourNotchFromOrder !== "function") return;
        if (String(row.piece_type || "") !== "L-Shaped Corner") return;
        if (piece.geometry && Array.isArray(piece.geometry.outer)) return;
        const notch = liner.contourNotchFromOrder(frm, row);
        piece.piece_type = row.piece_type;
        piece.clipped_corner_position = row.clipped_corner_position || piece.clipped_corner_position;
        piece.clipped_corner_width_cm = notch.cutWidthCm;
        piece.clipped_corner_length_cm = notch.cutLengthCm;
    }

    function applyOrderLinerSpecs(plan, frm) {
        const rows = (frm && frm.doc && frm.doc.pieces) || [];
        if (!rows.length) return;
        (plan.sheets || []).forEach(sheet => {
            (sheet.pieces || []).forEach(piece => {
                const row = orderRowForPlanPiece(rows, piece);
                applyManufacturingNotch(piece, frm, row);
                const engine = window.AlmdinaMachiningOverlay;
                const addons = engine && Array.isArray(engine.ADDONS) ? engine.ADDONS : null;
                if (!addons) {
                    if ((piece.overlays || []).some(item => item && item.kind === "liner")) return;
                    if (!row || !num(row.extra_liner)) return;
                    const side = String(row.liner_reference_side || "").trim();
                    if (!side || !(num(row.liner_width_cm) > 0)) return;
                    piece.extra_liner = 1;
                    if (!String(piece.liner_reference_side || "").trim()) {
                        piece.liner_reference_side = side;
                        piece.liner_offset_cm = row.liner_offset_cm;
                        piece.liner_width_cm = row.liner_width_cm;
                    }
                    if (String(piece.liner_reference_side || "") === side) {
                        piece.liner_start_cm = row.liner_start_cm;
                        piece.liner_length_cm = row.liner_length_cm;
                    }
                } else if (row) {
                    addons.forEach(addon => {
                        if ((piece.overlays || []).some(item => item && item.kind === addon.kind)) return;
                        if (!num(row[addon.enabled])) return;
                        const side = String(row[addon.side] || "").trim();
                        if (!side || !(num(row[addon.width]) > 0)) return;
                        piece[addon.enabled] = 1;
                        if (!String(piece[addon.side] || "").trim()) {
                            piece[addon.side] = side;
                            piece[addon.offset] = row[addon.offset];
                            piece[addon.width] = row[addon.width];
                        }
                        if (String(piece[addon.side] || "") === side) {
                            piece[addon.start] = row[addon.start];
                            piece[addon.length] = row[addon.length];
                        }
                    });
                }
                if (!piece.piece_type && row && row.piece_type) piece.piece_type = row.piece_type;
            });
        });
    }

    function downloadValidatedPlan(data, orderName, frm, ownsExport = null) {
        if (ownsExport && !ownsExport()) return null;
        const plan = (data && data.plan) || {};
        applyOrderLinerSpecs(plan, frm);
        if (!(plan.sheets || []).length) {
            frappe.throw(__("Validated cutting plan contains no sheets to export."));
        }

        let dxf;
        try {
            dxf = buildDxf(plan, {
                includeSawCenters: Boolean(data && data.include_saw_centers),
            });
            validateDxfText(dxf);
        } catch (error) {
            if (error && (error.linerExport || error.glassOpening)) {
                frappe.throw(__(error.message));
            }
            console.error("DXF self-check failed", error);
            frappe.throw(__("DXF export failed its compatibility self-check and was not downloaded."));
        }

        return frappe.call({
            method: NORMALIZE_DXF_METHOD,
            args: {
                order_name: orderName || null,
                content_b64: btoa(dxf),
            },
            freeze: true,
            freeze_message: __("Preparing an AutoCAD-compatible DXF..."),
        }).then(response => {
            if (ownsExport && !ownsExport()) return null;
            const output = (response && response.message) || {};
            if (!output.filename || !output.content_b64) {
                throw new Error("AutoCAD DXF normalization response is incomplete.");
            }
            download(
                output.filename,
                decodeBase64Bytes(output.content_b64),
                "application/dxf;charset=utf-8"
            );
            frappe.show_alert({
                message: __("Validated AutoCAD-compatible DXF exported successfully."),
                indicator: "green",
            });
        });
    }

    function fetchValidatedPlan(args) {
        return frappe.call({
            method: VALIDATED_PLAN_METHOD,
            args,
            freeze: true,
            freeze_message: __("Validating DXF geometry on server..."),
        });
    }

    function fetchOriginalUploadedDxf(args) {
        return frappe.call({
            method: ORIGINAL_DXF_METHOD,
            args,
            freeze: true,
            freeze_message: __("Downloading the uploaded DXF file..."),
        });
    }

    function downloadOriginalUpload(data) {
        const filename = String((data && data.filename) || "").trim();
        const contentB64 = String((data && data.content_b64) || "");
        if (!filename || !contentB64) {
            throw new Error("Uploaded DXF payload is missing.");
        }
        download(filename, decodeBase64Bytes(contentB64), "application/dxf");
        frappe.show_alert({
            message: __("Uploaded DXF downloaded successfully."),
            indicator: "green",
        });
    }

    function manufacturingSourceForm(frm, serializedDoc) {
        const profiles = frm && frm._dco_side_edge_profiles;
        return {
            doc: JSON.parse(serializedDoc),
            // L-shaped notch compensation also reads the form's edge profile cache.
            // Capture it with the document so a later route change cannot alter cuts.
            _dco_side_edge_profiles: profiles instanceof Map
                ? new Map([...profiles].map(([key, value]) => [key, { ...value }]))
                : new Map(),
            _dco_side_edge_profiles_financial: frm && frm._dco_side_edge_profiles_financial === true,
        };
    }

    function validatedExport(frm) {
        const serializedDoc = JSON.stringify(frm.doc);
        const sourceForm = manufacturingSourceForm(frm, serializedDoc);
        const args = { doc: serializedDoc };
        if (!frm.is_new()) args.order_name = sourceForm.doc.name;
        const context = window.AlmdinaDocumentContext;
        const owner = context && typeof context.capture === "function" ? context.capture(frm) : null;
        const initialDoc = frm.doc;
        const ownsExport = () => context && typeof context.isCurrent === "function"
            ? Boolean(owner && context.isCurrent(frm, owner))
            : Boolean(frm.doc === initialDoc && (!window.cur_frm || window.cur_frm === frm));

        return fetchValidatedPlan(args).then(r => {
            if (!ownsExport()) return null;
            return downloadValidatedPlan(r.message, sourceForm.doc.name, sourceForm, ownsExport);
        });
    }

    function exportOrderDxf(orderName, planSource = null, options = null) {
        const args = { order_name: orderName };
        // By-name exports are independent of the visible Desk form. If a caller
        // supplies form-only add-on data, freeze the matching order at invocation.
        const sourceDoc = options && options.frm && options.frm.doc;
        const sourceForm = sourceDoc && String(sourceDoc.name || "") === String(orderName || "")
            ? manufacturingSourceForm(options.frm, JSON.stringify(sourceDoc))
            : null;
        if (planSource) args.plan_source = planSource;
        if (shouldDownloadOriginalUpload(planSource, options)) {
            return fetchOriginalUploadedDxf(args).then(r => {
                try {
                    downloadOriginalUpload(r && r.message);
                } catch (error) {
                    console.error("Uploaded DXF download failed", error);
                    frappe.throw(__("Could not download the uploaded DXF file."));
                }
            });
        }
        return fetchValidatedPlan(args).then(r =>
            downloadValidatedPlan(r.message, orderName, sourceForm)
        );
    }

    frappe.provide("frappe.almdina");
    frappe.almdina.export_order_dxf = exportOrderDxf;
    frappe.almdina.can_export_dxf = canExportDxf;
    frappe.almdina.export_validated_dxf = validatedExport;

    // Compatibility: historical toolbar labels and title patterns used only to find and remove legacy buttons.
    const LEGACY_DXF_BUTTON_GROUPS = Object.freeze(["الرسم / DXF", "دورة الطلب"]);
    const STRIP_EXPORT_LABELS = [
        "تصدير DXF",
        "Export DXF",
        "تصدير DXF للرسم",
        "تصدير DXF للتعديل",
        "تصدير DXF لأوتوكاد",
        "Export DXF for AutoCAD",
        "تنزيل DXF المرفوع",
        "Download uploaded DXF",
        "تنزيل DXF للإنتاج",
        "رفع ملف DXF",
        "استبدال ملف DXF",
        "اعتماد الرسم",
        "إعادة اعتماد الرسم",
    ];

    function isExportButtonLabel(text) {
        const value = String(text || "").trim();
        if (STRIP_EXPORT_LABELS.includes(value)) return true;
        return /تصدير\s*DXF/i.test(value) || /تنزيل\s*DXF/i.test(value) || /^export\s*dxf/i.test(value) || /^download\s*uploaded\s*dxf/i.test(value);
    }

    function stripUnauthorizedExportButtons(frm) {
        if (!frm || frm.doctype !== "Door Cutting Order") return;

        // All DXF export actions live in the cutting-plan section only.
        STRIP_EXPORT_LABELS.forEach(label => {
            try {
                frm.remove_custom_button(label);
                LEGACY_DXF_BUTTON_GROUPS.forEach((group) => frm.remove_custom_button(label, group));
            } catch (error) {
                void error;
            }
        });

        const root = frm.page && frm.page.wrapper ? frm.page.wrapper : frm.wrapper;
        if (!root) return;
        $(root).find("button, a.btn").filter(function () {
            if ($(this).closest("[data-fieldname='plan_control_actions']").length) return false;
            if ($(this).hasClass("dco-export-dxf")) return false;
            if ($(this).hasClass("dco-print-cutting-plan")) return false;
            const label = String($(this).text() || "").trim();
            return isExportButtonLabel(label);
        }).each(function () {
            $(this).remove();
        });
    }

    function ensureExportStripObserver(frm) {
        if (frm._almdina_secure_dxf_observer) return;
        const root = frm.page && frm.page.wrapper ? frm.page.wrapper : frm.wrapper;
        const node = root && (root[0] || root);
        if (!node || typeof MutationObserver === "undefined") return;

        const observer = new MutationObserver(() => stripUnauthorizedExportButtons(frm));
        observer.observe(node, { childList: true, subtree: true });
        frm._almdina_secure_dxf_observer = observer;
    }

    function installToolbarGuard(frm) {
        if (frm.doctype !== "Door Cutting Order") return;
        stripUnauthorizedExportButtons(frm);
        ensureExportStripObserver(frm);
        [
            buttonLabel(),
            // Compatibility: historical print button label, used only for removal.
            "طباعة خطة القص",
            "Print Cutting Plan",
        ].forEach(label => {
            try {
                frm.remove_custom_button(label);
                LEGACY_DXF_BUTTON_GROUPS.forEach((group) => frm.remove_custom_button(label, group));
            } catch (error) {
                void error;
            }
        });
    }

    frappe.ui.form.on("Door Cutting Order", {
        refresh(frm) {
            installToolbarGuard(frm);
            [250, 900, 1600].forEach(delay => setTimeout(() => installToolbarGuard(frm), delay));
            if (frappe.after_ajax) {
                frappe.after_ajax(() => setTimeout(() => installToolbarGuard(frm), 0));
            }
        },
    });
})();
