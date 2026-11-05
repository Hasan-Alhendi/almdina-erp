(() => {
    "use strict";

    // Display engine: native SVG.
    // Chosen because the cutting-plan preview already uses SVG paths, no CDN is
    // required, pan/zoom map cleanly to a root transform, and session moves
    // attach to <g> transforms without inventing a second geometry model.

    const ACI = Object.freeze({
        1: "#ff0000",
        2: "#ffff00",
        3: "#00ff00",
        4: "#00ffff",
        5: "#0000ff",
        6: "#ff00ff",
        7: "#ffffff",
        8: "#808080",
    });

    function esc(value) {
        return frappe.utils.escape_html(String(value == null ? "" : value));
    }

    function frappeIcon(name) {
        if (window.frappe && frappe.utils && typeof frappe.utils.icon === "function") {
            return frappe.utils.icon(name, "sm", "", "", "currentColor", true);
        }
        return `<svg class="icon icon-sm abe-tool-icon" viewBox="0 0 24 24" aria-hidden="true"><use href="#icon-${esc(name)}"></use></svg>`;
    }

    function toolButton(className, iconName, label, options) {
        const extra = options || {};
        const disabled = extra.disabled ? " disabled" : "";
        const pressed = extra.pressed == null ? "" : ` aria-pressed="${extra.pressed ? "true" : "false"}"`;
        const title = extra.title || label;
        const attrs = extra.attrs || "";
        const icon = extra.iconHtml || frappeIcon(iconName);
        return `<button type="button" class="alm-btn-secondary ${className} abe-tool-btn"${disabled}${pressed}${attrs} title="${esc(title)}" aria-label="${esc(label)}">${icon}</button>`;
    }

    function saveStatusText(storeView) {
        const state = (storeView && storeView.saveState) || "clean";
        if (state === "dirty") return __("Unsaved changes");
        if (state === "saving") return __("Saving layout");
        if (state === "saved") return __("Layout saved");
        if (state === "failed") return __("Save failed. Your changes are still here.");
        if (state === "conflict") {
            const code = storeView && storeView.saveConflictCode;
            if (code === "version_conflict") {
                return __("A newer draft was saved. Your local edits are still here.");
            }
            if (code === "source_conflict") {
                return __("The source cutting plan data changed. Your local edits are still here.");
            }
            return __("This layout conflicts with another save or a changed source. Your changes are still here.");
        }
        return __("No unsaved changes");
    }

    function saveDisabled(storeView) {
        const state = (storeView && storeView.saveState) || "clean";
        if (!storeView || storeView.canSaveLayout === false || storeView.sourceOnly) return true;
        return state === "saving" || state === "saved" || state === "clean";
    }

    function saveTitle(storeView) {
        if (storeView && storeView.sourceOnly) {
            return __("This view shows the source plan. The saved draft is unchanged.");
        }
        if (storeView && storeView.canSaveLayout === false) {
            return __("You do not have permission to save this layout.");
        }
        return `${__("Save layout")}. ${saveStatusText(storeView)}`;
    }

    function pageActionsHtml(storeView) {
        const createDisabled = Boolean(
            storeView.createPlanInFlight
            || storeView.distributionDirty
            || !(Number(storeView.draftVersion) > 0)
            || storeView.sourceOnly
            || storeView.canSaveLayout === false
        );
        const createTitle = storeView.distributionDirty
            ? __("Save the current distribution before applying it to the cutting plan.")
            : __("Apply this layout as an unapproved edited cutting plan copy.");
        return `
            <div class="abe-page-actions" role="toolbar" aria-label="${esc(__("Board editor page actions"))}">
                ${toolButton("abe-save", "save", saveTitle(storeView), {
                    disabled: saveDisabled(storeView),
                    attrs: ` data-abe-save-state="${esc(storeView.saveState || "clean")}"`,
                })}
                <span class="abe-save-state" data-abe-save-state="${esc(storeView.saveState || "clean")}" role="status">${esc(saveStatusText(storeView))}</span>
                ${toolButton("abe-create-plan", "copy", __("Apply to cutting plan"), {
                    disabled: createDisabled,
                    title: createTitle,
                })}
                ${toolButton("abe-review", "clipboard-check", __("Review distribution"), {
                    disabled: Boolean(storeView.reviewInFlight),
                    title: __("Review distribution"),
                })}
                ${toolButton("abe-back", "arrow-left", __("Back to order"))}
            </div>
        `;
    }

    function bindPageActions(host, handlers) {
        if (!host) return;
        const save = host.querySelector(".abe-save");
        const review = host.querySelector(".abe-review");
        const createPlan = host.querySelector(".abe-create-plan");
        const back = host.querySelector(".abe-back");
        if (save) save.onclick = () => handlers && handlers.saveDraft && handlers.saveDraft();
        if (review) review.onclick = () => handlers && handlers.reviewDraft && handlers.reviewDraft();
        if (createPlan) {
            createPlan.onclick = () => handlers && handlers.createPlanCopy && handlers.createPlanCopy();
        }
        if (back) back.onclick = () => handlers && handlers.onBack && handlers.onBack();
    }

    function renderPageActions(host, storeView, handlers) {
        if (!host) return null;
        host.innerHTML = pageActionsHtml(storeView || {});
        bindPageActions(host, handlers || {});
        return host;
    }

    function aciToCss(aci, fallback) {
        const key = Number(aci);
        if (Number.isFinite(key) && ACI[key]) return ACI[key];
        return fallback || "var(--alm-text, #172033)";
    }

    function layerColor(storeView, matchKey) {
        const layers = (storeView.projection && storeView.projection.layers) || [];
        const row = layers.find((layer) => String(layer.match_key) === String(matchKey));
        return aciToCss(row && row.aci_color, "var(--alm-text, #172033)");
    }

    function clickTargetKeepsSelection(target) {
        if (!target || typeof target.closest !== "function") return false;
        return Boolean(target.closest(
            "[data-piece-id], [data-piece-key], [data-abe-rotate-handle], [data-abe-angle-mirror], [data-board-drag], [data-sheet]"
        ));
    }

    function leftOuterEdgeMidpoint(points) {
        if (!Array.isArray(points) || points.length < 2) return null;
        let best = null;
        for (let index = 0; index < points.length; index += 1) {
            const a = points[index];
            const b = points[(index + 1) % points.length];
            const ax = Number(a[0]);
            const ay = Number(a[1]);
            const bx = Number(b[0]);
            const by = Number(b[1]);
            if (![ax, ay, bx, by].every(Number.isFinite)) continue;
            const dx = bx - ax;
            const dy = by - ay;
            const length = Math.hypot(dx, dy);
            if (length < 1e-6) continue;
            const midX = (ax + bx) * 0.5;
            const midY = (ay + by) * 0.5;
            const verticalness = Math.abs(dy) / length;
            const score = midX - (verticalness * 0.01);
            if (
                !best
                || score < best.score - 1e-9
                || (Math.abs(score - best.score) < 1e-9 && length > best.length)
            ) {
                best = { x: midX, y: midY, score, length };
            }
        }
        return best;
    }

    function lCornerMirrorControlSvg(session, sessionPiece, framePoints, scale) {
        if (!sessionPiece || String(sessionPiece.piece_type || "") !== "L-Shaped Corner") return "";
        if (sessionPiece.distribution === "excluded" || !sessionPiece.editable) return "";
        const TG = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.TransformGeometry;
        if (!TG || typeof TG.angleMirrorEligibility !== "function") return "";
        const eligibility = TG.angleMirrorEligibility(session, sessionPiece.piece_key);
        if (!eligibility || !eligibility.allowed) return "";
        const anchor = leftOuterEdgeMidpoint(framePoints);
        if (!anchor) return "";
        const safeScale = Math.max(Number(scale) || 1, 0.05);
        const half = Math.max(10, 12 / safeScale);
        const offset = Math.max(14, 16 / safeScale);
        const cx = anchor.x - offset;
        const cy = anchor.y;
        const iconScale = (half * 1.15) / 12;
        const title = __("Mirror angle");
        return `<g class="abe-l-mirror-btn" data-abe-angle-mirror="${esc(sessionPiece.piece_key)}" transform="translate(${cx},${cy})" style="pointer-events:all;cursor:pointer">
            <title>${esc(title)}</title>
            <rect class="abe-l-mirror-hit" x="${-half}" y="${-half}" width="${half * 2}" height="${half * 2}" rx="${Math.max(3, 4 / safeScale)}" ry="${Math.max(3, 4 / safeScale)}" fill="#ffffff" stroke="#c9d2e3" stroke-width="${1.5 / safeScale}" vector-effect="non-scaling-stroke"/>
            <g transform="translate(${-12 * iconScale},${-12 * iconScale}) scale(${iconScale})" fill="none" stroke="#172033" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" pointer-events="none">
                <path d="m3 7 5 5-5 5"/>
                <path d="M21 12H8"/>
                <path d="M21 19V5a2 2 0 0 0-2-2H8"/>
                <path d="M8 5v14"/>
            </g>
        </g>`;
    }

    function selectedPieceKeys(storeView, session) {
        const listed = Array.isArray(storeView && storeView.selectedPieceKeys)
            ? storeView.selectedPieceKeys.filter((key) => session && session.pieces && session.pieces[key])
            : [];
        if (listed.length) return listed;
        if (storeView && storeView.selectedPieceKey && session && session.pieces && session.pieces[storeView.selectedPieceKey]) {
            return [storeView.selectedPieceKey];
        }
        if (!session || storeView.selectedPieceId == null) return [];
        const match = Object.values(session.pieces || {}).find(
            (row) => Number(row.piece_id) === Number(storeView.selectedPieceId)
        );
        return match ? [match.piece_key] : [];
    }

    function selectionChromeForPiece(session, sessionPiece, scale, showHandle) {
        if (!sessionPiece || sessionPiece.distribution === "excluded") return "";
        const RG = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.RotationGeometry;
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        if (!RG || !MoveGeometry) return "";
        RG.ensureBaseGeometry(sessionPiece);
        const worldFp = MoveGeometry.worldFootprint(sessionPiece, session.boards);
        const framePoints = (worldFp.points && worldFp.points.length >= 3)
            ? worldFp.points
            : [
                [worldFp.bounds.x, worldFp.bounds.y],
                [worldFp.bounds.x + worldFp.bounds.w, worldFp.bounds.y],
                [worldFp.bounds.x + worldFp.bounds.w, worldFp.bounds.y + worldFp.bounds.h],
                [worldFp.bounds.x, worldFp.bounds.y + worldFp.bounds.h],
            ];
        const framePath = pointsToPath(framePoints, true);
        if (!framePath) return "";
        const safeScale = Math.max(Number(scale) || 1, 0.05);
        const handleOffsetMm = Math.max(18, 28 / safeScale);
        const handle = RG.handleWorldPosition(sessionPiece, session.boards, handleOffsetMm);
        const eligibility = RG.pieceRotationEligibility(session, sessionPiece.piece_key);
        const handleRadius = Math.max(5, 7 / safeScale);
        let chrome = `<g class="abe-selection-chrome" data-abe-selection-chrome="1" data-abe-selection-for="${esc(sessionPiece.piece_key)}" data-rotation-deg="${esc(String(Number(sessionPiece.rotation_deg) || 0))}" style="pointer-events:none">
            <path class="abe-selection-outline" d="${esc(framePath)}" fill="none" stroke="#0b5fff" stroke-width="2" vector-effect="non-scaling-stroke" pointer-events="none"/>`;
        if (showHandle && eligibility.rotatable) {
            chrome += `<line x1="${handle.pivotWorld.x}" y1="${handle.pivotWorld.y}" x2="${handle.handleWorld.x}" y2="${handle.handleWorld.y}" stroke="#0b5fff" stroke-width="${1.4 / safeScale}" pointer-events="none"/>
            <circle class="abe-rotate-handle" data-abe-rotate-handle="${esc(sessionPiece.piece_key)}" cx="${handle.handleWorld.x}" cy="${handle.handleWorld.y}" r="${handleRadius}" fill="#fff" stroke="#0b5fff" stroke-width="2" style="pointer-events:all;cursor:grab"/>`;
        }
        if (showHandle) {
            chrome += lCornerMirrorControlSvg(session, sessionPiece, framePoints, safeScale);
        }
        chrome += `</g>`;
        return chrome;
    }

    function selectionChromeSvg(session, storeView, scale) {
        if (!session || !storeView) return "";
        const keys = selectedPieceKeys(storeView, session);
        if (!keys.length) return "";
        const showHandle = keys.length === 1;
        return keys.map((key) => selectionChromeForPiece(session, session.pieces[key], scale, showHandle)).join("");
    }

    function pointsToPath(points, closed) {
        if (!Array.isArray(points) || points.length < 2) return "";
        const parts = points.map((point, index) => {
            const x = Number(point[0]);
            const y = Number(point[1]);
            const cmd = index === 0 ? "M" : "L";
            return `${cmd}${x} ${y}`;
        });
        if (closed) parts.push("Z");
        return parts.join(" ");
    }

    function geometryPath(geometry) {
        if (!geometry || typeof geometry !== "object") return "";
        if (Array.isArray(geometry.outer)) {
            let d = pointsToPath(geometry.outer, true);
            (geometry.holes || []).forEach((hole) => {
                d += " " + pointsToPath(hole, true);
            });
            return d;
        }
        if (Array.isArray(geometry.path)) {
            return pointsToPath(geometry.path, Boolean(geometry.closed));
        }
        return "";
    }

    function placementRectMm(payload) {
        const placement = (payload && payload.placement_cm) || {};
        let w = Number(placement.w) || 0;
        let h = Number(placement.h) || 0;
        if (payload && payload.apply_rotated_to_dimensions && placement.rotated) {
            const swap = w;
            w = h;
            h = swap;
        }
        const x = (Number(placement.x) || 0) * 10;
        const y = (Number(placement.y) || 0) * 10;
        return { x, y, w: w * 10, h: h * 10 };
    }

    function displayStyle() {
        return (window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.PlanDisplayStyle) || null;
    }

    function defaultEdgeTypeOf(storeView) {
        const display = storeView && storeView.projection && storeView.projection.edge_display;
        return String((display && display.default_edge_type) || "").trim();
    }

    function screenFontMm(px, scale) {
        const display = window.AlmdinaEdgeDisplay;
        if (display && typeof display.screenFontMm === "function") return display.screenFontMm(px, scale);
        return Number(px) / Math.max(Number(scale) || 0, 0.02);
    }

    function fillRoleOf(element, sessionPiece, storeView) {
        const payload = (element && element.payload) || {};
        if (payload.fill_role) return String(payload.fill_role);
        if (payload.classification === "OFFCUT") return "offcut";
        const piece = ((storeView.projection && storeView.projection.pieces) || []).find((row) => (
            (sessionPiece && sessionPiece.piece_key && String(row.piece_instance_id || "") === String(sessionPiece.piece_instance_id || ""))
            || (element.piece_id != null && Number(row.piece_id) === Number(element.piece_id))
        ));
        if (piece && piece.fill_role) return String(piece.fill_role);
        const type = String((piece && piece.piece_type) || (sessionPiece && sessionPiece.piece_type) || "");
        if (type === "Special") return "special";
        if (type === "Glass") return "glass";
        if (type === "L-Shaped Corner") return "l_shaped";
        if (type === "Clipped Corner") return "clipped_corner";
        return "regular";
    }

    function pieceRecord(element, sessionPiece, storeView) {
        return ((storeView.projection && storeView.projection.pieces) || []).find((row) => (
            (sessionPiece && String(row.piece_instance_id || "") === String(sessionPiece.piece_instance_id || ""))
            || (element.piece_id != null && Number(row.piece_id) === Number(element.piece_id))
        )) || null;
    }

    function materialPaint(role, shaped, exactSpecial) {
        const style = displayStyle();
        if (style && typeof style.piecePaint === "function") {
            return style.piecePaint(role, { shaped, exactSpecial });
        }
        return { fill: "#e4f5ff", stroke: "#111111", strokeWidth: 1 };
    }

    function edgeBandsVisible(storeView, sessionPiece) {
        const api = window.AlmdinaBoardEditor;
        const pieceKey = sessionPiece && sessionPiece.piece_key;
        if (api && typeof api.isPieceEdgeBandVisibleInView === "function") {
            return api.isPieceEdgeBandVisibleInView(storeView, pieceKey);
        }
        return Boolean(storeView && storeView.showEdgeBands);
    }

    function edgeMarkSvg(piece, edges, geometrySource, sessionPiece, boards, origin, scale, defaultType, storeView) {
        // Visual gate only — manufacturing edges stay on the piece/projection.
        if (!edgeBandsVisible(storeView, sessionPiece)) return "";
        const marks = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.PlanEdgeMarks;
        if (!marks || !piece || !edges) return "";
        const bands = marks.bandsForPiece(piece, edges, scale, geometrySource, defaultType);
        return bands.map((band) => {
            const points = (band.points || []).map((point) => {
                const world = sessionPiece
                    ? entryPointToWorld(point, sessionPiece, boards)
                    : [Number(point[0]) + (origin.ox || 0), Number(point[1]) + (origin.oy || 0)];
                return `${world[0]},${world[1]}`;
            }).join(" ");
            if (!points) return "";
            const paint = (window.AlmdinaEdgeDisplay && window.AlmdinaEdgeDisplay.bandPaint)
                ? window.AlmdinaEdgeDisplay.bandPaint(band.custom)
                : { color: band.custom ? "#1d4ed8" : "#d00000", dash: band.custom ? "5 2.5 1.5 2.5" : "" };
            const color = paint.color;
            const dash = paint.dash ? ` stroke-dasharray="${paint.dash}"` : "";
            const side = band.side ? ` data-edge-side="${esc(band.side)}"` : "";
            return `<polyline class="abe-edge-band"${side} fill="none" stroke="${color}" stroke-width="3"${dash} vector-effect="non-scaling-stroke" stroke-linecap="butt" pointer-events="none" points="${points}"/>`;
        }).join("");
    }

    function doubleEdgeMarkup(corners, edges) {
        if (!edges || !edges.extra_double || !Array.isArray(corners) || corners.length < 4) return "";
        const sides = String(edges.extra_double_reference_sides || "");
        const active = {
            top: sides.includes("edge_width_top"),
            bottom: sides.includes("edge_width_bottom"),
            left: sides.includes("edge_long_left"),
            right: sides.includes("edge_long_right"),
        };
        if (!(active.top || active.bottom || active.left || active.right)) return "";
        const xs = corners.map((point) => Number(point[0]) || 0);
        const ys = corners.map((point) => Number(point[1]) || 0);
        const minX = Math.min(...xs);
        const maxX = Math.max(...xs);
        const minY = Math.min(...ys);
        const maxY = Math.max(...ys);
        const w = maxX - minX;
        const h = maxY - minY;
        const span0 = 0.16667;
        const span1 = 0.83333;
        const insets = [0.035, 0.07];
        const color = (displayStyle() && displayStyle().DOUBLE) || "#5a2d82";
        const lines = [];
        insets.forEach((inset) => {
            if (active.top) lines.push(`<line x1="${minX + w * span0}" y1="${minY + h * inset}" x2="${minX + w * span1}" y2="${minY + h * inset}" stroke="${color}" stroke-width="1.4" vector-effect="non-scaling-stroke" pointer-events="none"/>`);
            if (active.bottom) lines.push(`<line x1="${minX + w * span0}" y1="${maxY - h * inset}" x2="${minX + w * span1}" y2="${maxY - h * inset}" stroke="${color}" stroke-width="1.4" vector-effect="non-scaling-stroke" pointer-events="none"/>`);
            if (active.left) lines.push(`<line x1="${minX + w * inset}" y1="${minY + h * span0}" x2="${minX + w * inset}" y2="${minY + h * span1}" stroke="${color}" stroke-width="1.4" vector-effect="non-scaling-stroke" pointer-events="none"/>`);
            if (active.right) lines.push(`<line x1="${maxX - w * inset}" y1="${minY + h * span0}" x2="${maxX - w * inset}" y2="${minY + h * span1}" stroke="${color}" stroke-width="1.4" vector-effect="non-scaling-stroke" pointer-events="none"/>`);
        });
        return lines.join("");
    }

    function pieceCaption(element, sessionPiece, storeView, sessionBoards, origin, scale) {
        const style = displayStyle();
        const marks = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.PlanEdgeMarks;
        const piece = pieceRecord(element, sessionPiece, storeView);
        if (!style || !marks || !piece) return "";
        const placement = piece.placement_cm || {};
        const widthMm = (Number(placement.w) || 0) * 10;
        const heightMm = (Number(placement.h) || 0) * 10;
        if (!(widthMm > 0) || !(heightMm > 0)) return "";
        const role = fillRoleOf(element, sessionPiece, storeView);
        const exact = Boolean(piece.exact_geometry && role === "special");
        const badge = style.kindBadge(role, exact);
        const size = style.sizeLabel(piece.original_w, piece.original_h, placement.w, placement.h);
        const font = marks.measurementFontMm(Math.min(widthMm, heightMm), scale);
        const local = [
            (Number(placement.x) || 0) * 10 + widthMm / 2,
            (Number(placement.y) || 0) * 10 + heightMm / 2,
        ];
        const world = sessionPiece
            ? entryPointToWorld(local, sessionPiece, sessionBoards)
            : [local[0] + (origin.ox || 0), local[1] + (origin.oy || 0)];
        const angle = Number(sessionPiece && sessionPiece.rotation_deg) || 0;
        const badgeFill = role === "special" ? "#7a4c13" : "#8a5700";
        const badgeLine = badge
            ? `<text x="${world[0]}" y="${world[1] - font.mm}" text-anchor="middle" font-size="${font.mm * 0.8}" font-weight="900" fill="${badgeFill}">${esc(badge)}</text>`
            : "";
        return `<g class="abe-piece-caption" data-measure-px="${font.px}" transform="rotate(${angle} ${world[0]} ${world[1]})" pointer-events="none">${badgeLine}<text class="abe-piece-size" x="${world[0]}" y="${world[1]}" text-anchor="middle" dominant-baseline="middle" font-size="${font.mm}" font-family="Tahoma,Arial,sans-serif" fill="#111">${esc(size)}</text></g>`;
    }

    const BOARD_GAP_MM = 48;
    const BOARD_TITLE_MM = 36;
    const FIT_PADDING_PX = 28;
    const SCENE_PAD_PX = 16;
    const FLOAT_CLEARANCE_PX = 56;
    const SCALE_MIN = 0.02;
    const SCALE_MAX = 8;
    const GRID_WIDTH_RATIO = 0.625;
    // Opening boards render denser than the old fit-to-grid scale (~30% smaller).
    const OPENING_SCALE_FACTOR = 0.7;
    // Must match --abe-ui-zoom in board_editor.css (visual chrome only).
    const UI_ZOOM = 0.9;
    const BOARD_SCREEN_MIN_PX = 300;
    const BOARD_SCREEN_MAX_PX = 380;

    function declaredUiZoom(element) {
        const page = element && element.closest
            ? element.closest(".abe-page")
            : null;
        if (page && typeof window.getComputedStyle === "function") {
            const raw = String(window.getComputedStyle(page).getPropertyValue("--abe-ui-zoom") || "").trim();
            const parsed = Number(raw);
            if (Number.isFinite(parsed) && parsed > 0.05 && parsed < 8) return parsed;
        }
        return UI_ZOOM;
    }

    function elementCssZoom(element) {
        // UI chrome scale (transform:scale / CSS zoom / Browser Zoom) makes
        // getBoundingClientRect visual while clientWidth stays in layout units.
        if (!element || typeof element.getBoundingClientRect !== "function") {
            return declaredUiZoom(element);
        }
        const layout = Math.max(0, Number(element.clientWidth) || 0);
        if (!(layout > 0)) return declaredUiZoom(element);
        const visual = Number(element.getBoundingClientRect().width) || 0;
        if (!(visual > 0)) return declaredUiZoom(element);
        const ratio = visual / layout;
        if (!(ratio > 0.05) || !(ratio < 8)) return declaredUiZoom(element);
        return ratio;
    }

    function clientPointToLocal(element, clientX, clientY) {
        const rect = element && typeof element.getBoundingClientRect === "function"
            ? element.getBoundingClientRect()
            : { left: 0, top: 0, width: 1, height: 1 };
        const zoom = elementCssZoom(element);
        return {
            x: (Number(clientX) - Number(rect.left)) / zoom,
            y: (Number(clientY) - Number(rect.top)) / zoom,
            zoom,
            rect,
        };
    }

    function clientDeltaToLocal(element, deltaX, deltaY) {
        const zoom = elementCssZoom(element);
        return {
            x: Number(deltaX) / zoom,
            y: Number(deltaY) / zoom,
            zoom,
        };
    }

    function sheetSize(sheet) {
        return {
            widthMm: (Number(sheet.full_width_cm) || Number(sheet.w) || 122) * 10,
            heightMm: (Number(sheet.full_length_cm) || Number(sheet.h) || 244) * 10,
            trimX: (Number(sheet.applied_trim_width_cm) || 0) * 10,
            trimY: (Number(sheet.applied_trim_length_cm) || 0) * 10,
        };
    }

    function columnCount(maxBoardMm, viewportWidth) {
        const width = Number(viewportWidth) || 0;
        const boardMm = Math.max(1, Number(maxBoardMm) || 1);
        if (width < 40) return 2;
        const twoColumnMm = boardMm * 2 + BOARD_GAP_MM;
        const scale = (width * GRID_WIDTH_RATIO) / twoColumnMm;
        return boardMm * scale < BOARD_SCREEN_MIN_PX ? 1 : 2;
    }

    function shouldZoomWheel(event) {
        return Boolean(event && event.ctrlKey);
    }

    function normalizedWheelPixels(deltaY, deltaMode, viewportSize) {
        const delta = Number(deltaY) || 0;
        const mode = Number(deltaMode) || 0;
        if (mode === 1) return delta * 16;
        if (mode === 2) return delta * Math.max(1, Number(viewportSize) || 1);
        return delta;
    }

    function wheelZoomFactor(deltaY, deltaMode, viewportSize) {
        const pixels = normalizedWheelPixels(deltaY, deltaMode, viewportSize);
        return Math.exp(-pixels * 0.0016);
    }

    function cameraPads(camera) {
        const fallback = SCENE_PAD_PX;
        if (!camera || typeof camera !== "object") {
            return { padX: fallback, padY: fallback, minX: 0, minY: 0 };
        }
        const shared = camera.pad != null ? Number(camera.pad) : null;
        const padX = camera.padX != null ? Number(camera.padX) : (shared != null ? shared : fallback);
        const padY = camera.padY != null ? Number(camera.padY) : (shared != null ? shared : fallback);
        const minX = Number(camera.minX);
        const minY = Number(camera.minY);
        return {
            padX: Number.isFinite(padX) ? padX : fallback,
            padY: Number.isFinite(padY) ? padY : fallback,
            minX: Number.isFinite(minX) ? minX : 0,
            minY: Number.isFinite(minY) ? minY : 0,
        };
    }

    function cameraPointToWorld(scrollX, scrollY, focalX, focalY, scale, padOrCamera) {
        // SVG contract (must stay in sync with render()):
        //   viewBox = "0 0 contentW contentH"
        //   .abe-world = translate(padX - minX*scale, padY - minY*scale) scale(scale)
        //   stage.scrollLeft/Top shifts the SVG inside the viewport
        // screen = pad - min*scale + world*scale - scroll
        // world  = (scroll + screen - pad) / scale + min
        const safeScale = Number(scale) || 1;
        let padX = SCENE_PAD_PX;
        let padY = SCENE_PAD_PX;
        let minX = 0;
        let minY = 0;
        if (padOrCamera && typeof padOrCamera === "object") {
            const pads = cameraPads(padOrCamera);
            padX = pads.padX;
            padY = pads.padY;
            minX = pads.minX;
            minY = pads.minY;
        } else if (padOrCamera != null) {
            padX = Number(padOrCamera) || 0;
            padY = padX;
        }
        return {
            x: ((Number(scrollX) || 0) + Number(focalX) - padX) / safeScale + minX,
            y: ((Number(scrollY) || 0) + Number(focalY) - padY) / safeScale + minY,
        };
    }

    function worldToScreen(worldX, worldY, camera) {
        const scale = Number(camera && camera.scale) || 1;
        const pads = cameraPads(camera);
        const scrollX = Number(camera && camera.scrollX) || 0;
        const scrollY = Number(camera && camera.scrollY) || 0;
        return {
            x: pads.padX - pads.minX * scale + Number(worldX) * scale - scrollX,
            y: pads.padY - pads.minY * scale + Number(worldY) * scale - scrollY,
        };
    }

    function contentSizeForCamera(camera, viewSize, worldSize) {
        const scale = Math.max(Number(camera && camera.scale) || 1, 1e-9);
        const viewW = Math.max(1, Number(viewSize && viewSize.width) || 1);
        const viewH = Math.max(1, Number(viewSize && viewSize.height) || 1);
        const worldW = Math.max(0, Number(worldSize && worldSize.width) || 0);
        const worldH = Math.max(0, Number(worldSize && worldSize.height) || 0);
        const pads = cameraPads(camera);
        const scrollX = Math.max(0, Number(camera && camera.scrollX) || 0);
        const scrollY = Math.max(0, Number(camera && camera.scrollY) || 0);
        const worldPxW = worldW * scale;
        const worldPxH = worldH * scale;
        // Trail is derived, never an accumulating input: content must cover the
        // world+default pad and the requested scroll, then trail is the remainder.
        const contentW = Math.max(
            viewW,
            Math.ceil(worldPxW + pads.padX + SCENE_PAD_PX),
            Math.ceil(scrollX + viewW)
        );
        // FLOAT_CLEARANCE is always outside the scrollable world+pad+trail block
        // (matches historical render: max(stage, worldBlock) + clearance).
        const contentH = Math.max(
            viewH,
            Math.ceil(worldPxH + pads.padY + SCENE_PAD_PX),
            Math.ceil(scrollY + viewH)
        ) + FLOAT_CLEARANCE_PX;
        return {
            contentW,
            contentH,
            maxScrollX: Math.max(0, contentW - viewW),
            maxScrollY: Math.max(0, contentH - viewH),
            trailX: Math.max(SCENE_PAD_PX, contentW - worldPxW - pads.padX),
            trailY: Math.max(SCENE_PAD_PX, contentH - FLOAT_CLEARANCE_PX - worldPxH - pads.padY),
        };
    }

    function fitCameraScroll(camera, viewSize, worldSize) {
        // Make pad/scroll/trail mutually achievable in the browser scrollport.
        const scale = Math.max(Number(camera && camera.scale) || 1, 1e-9);
        const pads = cameraPads(camera);
        let padX = pads.padX;
        let padY = pads.padY;
        let scrollX = Number(camera && camera.scrollX) || 0;
        let scrollY = Number(camera && camera.scrollY) || 0;
        let adjusted = false;
        if (scrollX < 0) {
            padX -= scrollX;
            scrollX = 0;
            adjusted = true;
        }
        if (scrollY < 0) {
            padY -= scrollY;
            scrollY = 0;
            adjusted = true;
        }
        const sized = contentSizeForCamera({
            scale,
            scrollX,
            scrollY,
            padX,
            padY,
            trailX: camera && camera.trailX,
            trailY: camera && camera.trailY,
            minX: pads.minX,
            minY: pads.minY,
        }, viewSize, worldSize);
        if (
            Math.abs(sized.trailX - (Number(camera && camera.trailX) || SCENE_PAD_PX)) > 1e-9
            || Math.abs(sized.trailY - (Number(camera && camera.trailY) || SCENE_PAD_PX)) > 1e-9
        ) {
            adjusted = true;
        }
        return {
            scale,
            scrollX,
            scrollY,
            padX,
            padY,
            trailX: sized.trailX,
            trailY: sized.trailY,
            minX: pads.minX,
            minY: pads.minY,
            contentW: sized.contentW,
            contentH: sized.contentH,
            maxScrollX: sized.maxScrollX,
            maxScrollY: sized.maxScrollY,
            adjusted,
        };
    }

    function zoomAroundFocal(camera, focal, factor, viewSize, worldSize) {
        const previous = Number(camera && camera.scale) || 1;
        const next = Math.min(SCALE_MAX, Math.max(SCALE_MIN, previous * (Number(factor) || 1)));
        const pads = cameraPads(camera);
        const scrollX = Number(camera && camera.scrollX) || 0;
        const scrollY = Number(camera && camera.scrollY) || 0;
        const focalX = Number(focal && focal.x) || 0;
        const focalY = Number(focal && focal.y) || 0;
        const world = cameraPointToWorld(scrollX, scrollY, focalX, focalY, previous, {
            padX: pads.padX,
            padY: pads.padY,
            minX: pads.minX,
            minY: pads.minY,
        });
        if (!(Math.abs(next - previous) > 1e-12)) {
            return {
                scale: previous,
                scrollX,
                scrollY,
                padX: pads.padX,
                padY: pads.padY,
                trailX: Number(camera && camera.trailX) || SCENE_PAD_PX,
                trailY: Number(camera && camera.trailY) || SCENE_PAD_PX,
                minX: pads.minX,
                minY: pads.minY,
                worldX: world.x,
                worldY: world.y,
                changed: false,
            };
        }
        // Keep the same world point under the focal, then expand content/trail so
        // the required scroll is actually attainable (not browser-clamped).
        let nextPadX = pads.padX;
        let nextPadY = pads.padY;
        let nextScrollX = nextPadX - pads.minX * next + world.x * next - focalX;
        let nextScrollY = nextPadY - pads.minY * next + world.y * next - focalY;
        const fitted = fitCameraScroll({
            scale: next,
            scrollX: nextScrollX,
            scrollY: nextScrollY,
            padX: nextPadX,
            padY: nextPadY,
            trailX: camera && camera.trailX,
            trailY: camera && camera.trailY,
            minX: pads.minX,
            minY: pads.minY,
        }, viewSize || {}, worldSize || {});
        return {
            scale: next,
            scrollX: fitted.scrollX,
            scrollY: fitted.scrollY,
            padX: fitted.padX,
            padY: fitted.padY,
            trailX: fitted.trailX,
            trailY: fitted.trailY,
            minX: pads.minX,
            minY: pads.minY,
            contentW: fitted.contentW,
            contentH: fitted.contentH,
            worldX: world.x,
            worldY: world.y,
            changed: true,
        };
    }

    function reconcileCameraWorldOrigin(camera, nextMinX, nextMinY, viewSize, worldSize) {
        const pads = cameraPads(camera);
        const scale = Number(camera && camera.scale) || 1;
        const prevMinX = camera && camera.minX != null ? Number(camera.minX) : pads.minX;
        const prevMinY = camera && camera.minY != null ? Number(camera.minY) : pads.minY;
        const minX = Number(nextMinX);
        const minY = Number(nextMinY);
        const safeMinX = Number.isFinite(minX) ? minX : 0;
        const safeMinY = Number.isFinite(minY) ? minY : 0;
        let scrollX = Number(camera && camera.scrollX) || 0;
        let scrollY = Number(camera && camera.scrollY) || 0;
        let changed = false;
        if (Number.isFinite(prevMinX) && Math.abs(prevMinX - safeMinX) > 1e-9) {
            // translate(pad - min*scale) shifts by (prevMin - nextMin)*scale; compensate via scroll.
            scrollX += (prevMinX - safeMinX) * scale;
            changed = true;
        }
        if (Number.isFinite(prevMinY) && Math.abs(prevMinY - safeMinY) > 1e-9) {
            scrollY += (prevMinY - safeMinY) * scale;
            changed = true;
        }
        const fitted = fitCameraScroll({
            scale,
            scrollX,
            scrollY,
            padX: pads.padX,
            padY: pads.padY,
            trailX: camera && camera.trailX,
            trailY: camera && camera.trailY,
            minX: safeMinX,
            minY: safeMinY,
        }, viewSize || {}, worldSize || {});
        if (
            !changed
            && !fitted.adjusted
            && camera
            && camera.minX != null
            && camera.minY != null
            && Math.abs(Number(camera.minX) - safeMinX) <= 1e-9
            && Math.abs(Number(camera.minY) - safeMinY) <= 1e-9
        ) {
            return null;
        }
        return {
            scale,
            scrollX: fitted.scrollX,
            scrollY: fitted.scrollY,
            padX: fitted.padX,
            padY: fitted.padY,
            trailX: fitted.trailX,
            trailY: fitted.trailY,
            minX: safeMinX,
            minY: safeMinY,
            changed: true,
        };
    }

    function openingScale(maxBoardMm, columns, viewportWidth) {
        const width = Math.max(1, Number(viewportWidth) || 0);
        const boardMm = Math.max(1, Number(maxBoardMm) || 1);
        const cols = columns === 1 ? 1 : 2;
        const gridMm = boardMm * cols + BOARD_GAP_MM * (cols - 1);
        let scale = (width * GRID_WIDTH_RATIO) / gridMm;
        if (boardMm * scale > BOARD_SCREEN_MAX_PX) scale = BOARD_SCREEN_MAX_PX / boardMm;
        return scale * OPENING_SCALE_FACTOR;
    }

    function contentFrame(metrics, fitBounds, scale, stageW, stageH) {
        const safeScale = Math.max(Number(scale) || 1, 1e-9);
        const minX = Number(metrics && metrics.minX) || 0;
        const minY = Number(metrics && metrics.minY) || 0;
        const worldPxW = Math.max(1, (Number(metrics && metrics.width) || 1) * safeScale);
        const worldPxH = Math.max(1, (Number(metrics && metrics.height) || 1) * safeScale);
        const bounds = fitBounds || { x: 0, y: 0, width: 1, height: 1 };
        const boardPxW = Math.max(1, Number(bounds.width) || 1) * safeScale;
        const boardPxH = Math.max(1, Number(bounds.height) || 1) * safeScale;
        const boardOffsetX = (Number(bounds.x) - minX) * safeScale;
        const boardOffsetY = (Number(bounds.y) - minY) * safeScale;
        const viewW = Math.max(1, Number(stageW) || 1);
        const viewH = Math.max(1, Number(stageH) || 1);
        const minContentW = Math.ceil(worldPxW + SCENE_PAD_PX * 2);
        const minContentH = Math.ceil(worldPxH + SCENE_PAD_PX * 2) + FLOAT_CLEARANCE_PX;
        const contentW = Math.max(viewW, minContentW);
        const contentH = Math.max(viewH, minContentH);
        let padX = SCENE_PAD_PX;
        let padY = SCENE_PAD_PX;
        if (contentW <= viewW + 0.5) {
            padX = Math.max(SCENE_PAD_PX, (viewW - boardPxW) / 2 - boardOffsetX);
        }
        if (contentH <= viewH + 0.5) {
            padY = Math.max(
                SCENE_PAD_PX,
                (viewH - FLOAT_CLEARANCE_PX - boardPxH) / 2 - boardOffsetY
            );
        }
        let scrollX = 0;
        let scrollY = 0;
        if (contentW > viewW) {
            const boardCenterX = padX + boardOffsetX + boardPxW / 2;
            scrollX = Math.max(0, Math.min(contentW - viewW, boardCenterX - viewW / 2));
        }
        if (contentH > viewH) {
            const boardCenterY = padY + boardOffsetY + boardPxH / 2;
            scrollY = Math.max(0, Math.min(contentH - viewH, boardCenterY - viewH / 2));
        }
        return {
            contentW,
            contentH,
            padX,
            padY,
            scrollX,
            scrollY,
        };
    }

    function frameCamera(fitBounds, scale, viewportWidth, viewportHeight, metrics) {
        const viewW = Number(viewportWidth) || 0;
        const viewH = Number(viewportHeight) || 0;
        if (viewW < 40 || viewH < 40) return null;
        const bounds = fitBounds || { x: 0, y: 0, width: 1, height: 1 };
        const frameMetrics = metrics || {
            minX: Number(bounds.x) || 0,
            minY: Number(bounds.y) || 0,
            width: Math.max(1, Number(bounds.width) || 1),
            height: Math.max(1, Number(bounds.height) || 1),
        };
        const frame = contentFrame(frameMetrics, bounds, scale, viewW, viewH);
        return {
            scale: Number(scale) || 1,
            scrollX: frame.scrollX,
            scrollY: frame.scrollY,
            padX: frame.padX,
            padY: frame.padY,
            fitted: true,
        };
    }

    function sheetLayout(sheets, columns) {
        // Editor display positions only. Piece coordinates stay in usable-sheet
        // millimetres and are translated by origin + applied trim.
        const list = sheets || [];
        const cols = columns === 1 ? 1 : 2;
        const sizes = list.map((sheet) => sheetSize(sheet));
        let maxWidth = 1;
        sizes.forEach((size) => {
            maxWidth = Math.max(maxWidth, size.widthMm);
        });
        const stride = maxWidth + BOARD_GAP_MM;
        const rowCount = Math.max(1, Math.ceil(list.length / cols) || 1);
        const rowHeightMm = [];
        for (let row = 0; row < rowCount; row += 1) {
            let height = 1;
            for (let col = 0; col < cols; col += 1) {
                const size = sizes[row * cols + col];
                if (size) height = Math.max(height, size.heightMm);
            }
            rowHeightMm.push(height);
        }
        const rowOriginY = (row) => {
            let y = 0;
            for (let index = 0; index < row; index += 1) {
                y += BOARD_TITLE_MM + rowHeightMm[index] + BOARD_GAP_MM;
            }
            return y;
        };
        const positions = {};
        list.forEach((sheet, index) => {
            const size = sizes[index];
            const row = Math.floor(index / cols);
            const top = rowOriginY(row);
            positions[String(sheet.sheet_no)] = {
                originX: (index % cols) * stride,
                originY: top + BOARD_TITLE_MM,
                titleY: top + 26,
                widthMm: size.widthMm,
                heightMm: size.heightMm,
                trimX: size.trimX,
                trimY: size.trimY,
                sheetNo: sheet.sheet_no,
            };
        });
        const occupied = Math.min(cols, Math.max(list.length, 1));
        const gridWidth = occupied * maxWidth + Math.max(0, occupied - 1) * BOARD_GAP_MM;
        const gridHeight = list.length
            ? rowOriginY(rowCount - 1) + BOARD_TITLE_MM + rowHeightMm[rowCount - 1]
            : 1;
        const fitBounds = { x: 0, y: 0, width: Math.max(gridWidth, 1), height: Math.max(gridHeight, 1) };
        return {
            positions,
            columns: cols,
            maxBoardMm: maxWidth,
            fitBounds,
            staging: {
                x: fitBounds.width,
                y: 0,
                width: fitBounds.width * ((1 - GRID_WIDTH_RATIO) / GRID_WIDTH_RATIO),
                height: fitBounds.height,
            },
        };
    }

    function mergeSessionLayout(layout, session) {
        if (!session || !session.boards) return layout;
        const positions = { ...layout.positions };
        let minX = 0;
        let minY = 0;
        let maxX = layout.fitBounds.width;
        let maxY = layout.fitBounds.height;
        Object.values(session.boards).forEach((board) => {
            const key = String(board.sheet_no);
            const base = positions[key] || {};
            const originX = Number(board.origin_x_mm);
            const originY = Number(board.origin_y_mm);
            const widthMm = Number(board.width_mm) || base.widthMm || 1;
            const heightMm = Number(board.height_mm) || base.heightMm || 1;
            const titleBand = Number(board.title_band_mm) || BOARD_TITLE_MM;
            positions[key] = {
                ...base,
                originX,
                originY,
                titleY: originY - 10,
                widthMm,
                heightMm,
                trimX: Number(board.trim_x_mm) || base.trimX || 0,
                trimY: Number(board.trim_y_mm) || base.trimY || 0,
                sheetNo: board.sheet_no,
                userMoved: Boolean(board.user_moved),
            };
            minX = Math.min(minX, originX);
            minY = Math.min(minY, originY - titleBand);
            maxX = Math.max(maxX, originX + widthMm);
            maxY = Math.max(maxY, originY + heightMm);
        });
        Object.values(session.pieces || {}).forEach((piece) => {
            if (piece.sheet_no != null && piece.sheet_no !== "") return;
            const fp = window.AlmdinaBoardEditor.MoveGeometry
                ? window.AlmdinaBoardEditor.MoveGeometry.footprint(piece)
                : null;
            if (!fp) return;
            minX = Math.min(minX, fp.bounds.x);
            minY = Math.min(minY, fp.bounds.y);
            maxX = Math.max(maxX, fp.bounds.x + fp.bounds.w);
            maxY = Math.max(maxY, fp.bounds.y + fp.bounds.h);
        });
        const fitBounds = {
            x: minX,
            y: minY,
            width: Math.max(1, maxX - minX),
            height: Math.max(1, maxY - minY),
        };
        return {
            ...layout,
            positions,
            fitBounds,
            staging: {
                x: fitBounds.x + fitBounds.width,
                y: fitBounds.y,
                width: Math.max(layout.staging.width, fitBounds.width * 0.35),
                height: fitBounds.height,
            },
            worldMinX: minX,
            worldMinY: minY,
        };
    }

    function fitBoards(fitBounds, viewportWidth, viewportHeight) {
        const viewW = Number(viewportWidth) || 0;
        const viewH = Number(viewportHeight) || 0;
        if (viewW < 40 || viewH < 40) return null;
        const bounds = fitBounds || { x: 0, y: 0, width: 1, height: 1 };
        const innerW = Math.max(1, viewW - FIT_PADDING_PX * 2);
        const innerH = Math.max(1, viewH - FIT_PADDING_PX * 2 - FLOAT_CLEARANCE_PX);
        const scale = Math.min(innerW / Math.max(bounds.width, 1), innerH / Math.max(bounds.height, 1));
        return frameCamera(bounds, scale, viewW, viewH);
    }

    function sessionPieceForElement(session, element) {
        if (!session || !session.pieces) return null;
        const instanceId = String(element.piece_instance_id || "").trim();
        if (instanceId && session.pieces[`instance:${instanceId}`]) {
            return session.pieces[`instance:${instanceId}`];
        }
        if (element.piece_id == null || element.piece_id === "") return null;
        return Object.values(session.pieces).find((piece) => Number(piece.piece_id) === Number(element.piece_id)) || null;
    }

    function pieceOrigin(session, piece, layout) {
        // Board usable origin in world space. Geometry paths are converted to world
        // separately so translation/rotation are applied once.
        if (!piece) {
            return {
                ox: 0,
                oy: 0,
                dx: 0,
                dy: 0,
                rotationDeg: 0,
                pivotX: 0,
                pivotY: 0,
                entryPivotX: 0,
                entryPivotY: 0,
            };
        }
        const entryPivot = piece.entry_pivot_mm || piece.pivot_mm || {};
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        const boards = (session && session.boards) || {};
        const worldPivot = MoveGeometry
            ? MoveGeometry.pivotInWorld(piece, boards)
            : { x: Number(piece.pivot_mm && piece.pivot_mm.x) || 0, y: Number(piece.pivot_mm && piece.pivot_mm.y) || 0 };
        if (piece.sheet_no == null || piece.sheet_no === "") {
            return {
                ox: 0,
                oy: 0,
                dx: 0,
                dy: 0,
                rotationDeg: Number(piece.rotation_deg) || 0,
                pivotX: worldPivot.x,
                pivotY: worldPivot.y,
                entryPivotX: Number(entryPivot.x) || 0,
                entryPivotY: Number(entryPivot.y) || 0,
            };
        }
        const sheetPos = layout.positions[String(piece.sheet_no)] || { originX: 0, originY: 0, trimX: 0, trimY: 0 };
        return {
            ox: sheetPos.originX + (sheetPos.trimX || 0),
            oy: sheetPos.originY + (sheetPos.trimY || 0),
            dx: 0,
            dy: 0,
            rotationDeg: Number(piece.rotation_deg) || 0,
            pivotX: worldPivot.x,
            pivotY: worldPivot.y,
            entryPivotX: Number(entryPivot.x) || 0,
            entryPivotY: Number(entryPivot.y) || 0,
        };
    }

    function entryPointToWorld(point, piece, boards) {
        // Projection geometry stays in the immutable entry usable-sheet frame.
        // Map once: rotate about entry_pivot, then place that pivot at the live world pivot.
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        const RG = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.RotationGeometry;
        const entryPivot = piece.entry_pivot_mm || piece.pivot_mm || { x: 0, y: 0 };
        const worldPivot = MoveGeometry
            ? MoveGeometry.pivotInWorld(piece, boards)
            : { x: Number(piece.pivot_mm && piece.pivot_mm.x) || 0, y: Number(piece.pivot_mm && piece.pivot_mm.y) || 0 };
        let x = Number(point[0]) || 0;
        let y = Number(point[1]) || 0;
        const angle = Number(piece.rotation_deg) || 0;
        if (RG && angle) {
            const rotated = RG.rotatePoint([x, y], entryPivot, angle);
            x = rotated[0];
            y = rotated[1];
        }
        return [
            x - (Number(entryPivot.x) || 0) + worldPivot.x,
            y - (Number(entryPivot.y) || 0) + worldPivot.y,
        ];
    }

    function sessionPointsToWorld(points, piece, boards) {
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        if (!MoveGeometry || !Array.isArray(points)) return points;
        return MoveGeometry.pointsToWorld(points, piece.sheet_no, boards);
    }

    function worldMetricsFor(layout, scale) {
        const minX = Number(layout.worldMinX) || 0;
        const minY = Number(layout.worldMinY) || 0;
        const width = Math.max(
            layout.fitBounds.width + layout.staging.width,
            1
        );
        const height = Math.max(layout.fitBounds.height, 1);
        return {
            minX,
            minY,
            width,
            height,
            scale: Number(scale) || 1,
            pad: SCENE_PAD_PX,
        };
    }

    function patchDragPreview(host, preview) {
        const world = host.querySelector(".abe-world");
        if (!world) return;
        let ghost = world.querySelector("[data-abe-ghost]");
        let angleBadge = world.querySelector("[data-abe-angle-badge]");
        world.querySelectorAll("[data-abe-drag-shift]").forEach((node) => {
            const base = node.getAttribute("data-abe-base-transform");
            if (base != null) node.setAttribute("transform", base);
            else node.removeAttribute("transform");
            node.removeAttribute("data-abe-base-transform");
            node.removeAttribute("data-abe-drag-shift");
        });
        world.querySelectorAll("[data-abe-guide]").forEach((node) => node.remove());
        world.querySelectorAll("[data-abe-rotate-preview]").forEach((node) => node.remove());
        if (!preview) {
            if (ghost) ghost.remove();
            if (angleBadge) angleBadge.remove();
            return;
        }
        const dx = Number(preview.dx) || 0;
        const dy = Number(preview.dy) || 0;
        function attrSel(value) {
            return String(value || "").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
        }
        if (preview.kind === "rotate" && Array.isArray(preview.ids)) {
            const angle = Number(preview.rotation_deg) || 0;
            const pivotWorldX = Number(preview.pivotX) || 0;
            const pivotWorldY = Number(preview.pivotY) || 0;
            // Material paths are already in world millimetres; rotate about the world pivot.
            const px = pivotWorldX;
            const py = pivotWorldY;
            preview.ids.forEach((pieceKey) => {
                const instanceId = String(pieceKey).replace(/^instance:/, "");
                world.querySelectorAll(`[data-piece-key="${attrSel(pieceKey)}"], [data-piece-instance="${attrSel(instanceId)}"]`).forEach((node) => {
                    if (node.getAttribute("data-abe-base-transform") == null) {
                        node.setAttribute("data-abe-base-transform", node.getAttribute("transform") || "");
                    }
                    const base = node.getAttribute("data-abe-base-transform") || "";
                    // Preview delta from the committed session angle already in the base transform.
                    const committed = Number(node.getAttribute("data-rotation-deg")) || 0;
                    const delta = angle - committed;
                    node.setAttribute(
                        "transform",
                        `${base} rotate(${delta},${px},${py})`.trim()
                    );
                    node.setAttribute("data-abe-drag-shift", "1");
                });
            });
            world.querySelectorAll("[data-abe-selection-chrome]").forEach((node) => {
                if (node.getAttribute("data-abe-base-transform") == null) {
                    node.setAttribute("data-abe-base-transform", node.getAttribute("transform") || "");
                }
                const base = node.getAttribute("data-abe-base-transform") || "";
                const committed = Number(node.getAttribute("data-rotation-deg")) || 0;
                node.setAttribute("transform", `${base} rotate(${angle - committed},${px},${py})`.trim());
                node.setAttribute("data-abe-drag-shift", "1");
            });
            if (!angleBadge) {
                angleBadge = document.createElementNS("http://www.w3.org/2000/svg", "text");
                angleBadge.setAttribute("data-abe-angle-badge", "1");
                angleBadge.setAttribute("pointer-events", "none");
                angleBadge.setAttribute("fill", preview.valid ? "#12b76a" : "#f04438");
                angleBadge.setAttribute("font-size", "14");
                world.appendChild(angleBadge);
            }
            const display = Number(preview.display_deg != null ? preview.display_deg : preview.rotation_deg) || 0;
            angleBadge.textContent = `${Math.round(display * 10) / 10}°`;
            angleBadge.setAttribute("x", String(pivotWorldX + 12));
            angleBadge.setAttribute("y", String(pivotWorldY - 12));
            angleBadge.setAttribute("fill", preview.valid ? "#12b76a" : "#f04438");
            if (ghost) ghost.style.display = "none";
            return;
        }
        if (angleBadge) angleBadge.remove();
        if (preview.kind === "piece" && Array.isArray(preview.ids)) {
            preview.ids.forEach((pieceKey) => {
                const instanceId = String(pieceKey).replace(/^instance:/, "");
                world.querySelectorAll(`[data-piece-key="${attrSel(pieceKey)}"], [data-piece-instance="${attrSel(instanceId)}"], [data-abe-selection-for="${attrSel(pieceKey)}"]`).forEach((node) => {
                    if (node.getAttribute("data-abe-base-transform") == null) {
                        node.setAttribute("data-abe-base-transform", node.getAttribute("transform") || "");
                    }
                    const base = node.getAttribute("data-abe-base-transform") || "";
                    node.setAttribute("transform", `${base} translate(${dx},${dy})`.trim());
                    node.setAttribute("data-abe-drag-shift", "1");
                });
            });
        } else if (preview.kind === "board") {
            const sheet = String(preview.sheetNo);
            world.querySelectorAll(`[data-sheet-group="${attrSel(sheet)}"]`).forEach((node) => {
                // Outer host only: nested matches would inherit this translate and
                // receive a second one if also selected.
                if (node.parentNode !== world) return;
                if (node.getAttribute("data-abe-base-transform") == null) {
                    node.setAttribute("data-abe-base-transform", node.getAttribute("transform") || "");
                }
                const base = node.getAttribute("data-abe-base-transform") || "";
                node.setAttribute("transform", `${base} translate(${dx},${dy})`.trim());
                node.setAttribute("data-abe-drag-shift", "1");
            });
        }
        if (!ghost) {
            ghost = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            ghost.setAttribute("data-abe-ghost", "1");
            ghost.setAttribute("fill", "none");
            ghost.setAttribute("stroke-dasharray", "8 6");
            ghost.setAttribute("stroke-width", "2");
            ghost.setAttribute("pointer-events", "none");
            world.appendChild(ghost);
        }
        ghost.setAttribute("stroke", preview.valid ? "#12b76a" : "#f04438");
        ghost.setAttribute("x", String((Number(preview.ghostX) || 0)));
        ghost.setAttribute("y", String((Number(preview.ghostY) || 0)));
        ghost.setAttribute("width", String(Math.max(1, Number(preview.ghostW) || 40)));
        ghost.setAttribute("height", String(Math.max(1, Number(preview.ghostH) || 40)));
        ghost.style.display = preview.kind === "piece" ? "block" : "none";

        if (preview.snapped && Array.isArray(preview.guides)) {
            preview.guides.forEach((guide) => {
                const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                line.setAttribute("data-abe-guide", "1");
                line.setAttribute("x1", String(Number(guide.x1) || 0));
                line.setAttribute("y1", String(Number(guide.y1) || 0));
                line.setAttribute("x2", String(Number(guide.x2) || 0));
                line.setAttribute("y2", String(Number(guide.y2) || 0));
                line.setAttribute("stroke", "#0b5fff");
                line.setAttribute("stroke-width", "1.25");
                line.setAttribute("stroke-dasharray", "6 4");
                line.setAttribute("vector-effect", "non-scaling-stroke");
                line.setAttribute("pointer-events", "none");
                world.appendChild(line);
            });
        }
    }

    function patchMeasureOverlay(host, lines, scale) {
        const world = host && host.querySelector(".abe-world");
        if (!world) return;
        world.querySelectorAll("[data-abe-measure]").forEach((node) => node.remove());
        const rows = Array.isArray(lines) ? lines : [];
        host.__abeMeasureLines = rows;
        const safeScale = Math.max(0.05, Number(scale) || Number((host.__abeWorldMetrics || {}).scale) || 1);
        const fontMm = Math.max(10 / safeScale, 2.4);
        rows.forEach((row) => {
            if (!row || !row.start || !row.end) return;
            const color = row.style === "alt" ? "#c026d3" : "#ea580c";
            const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
            group.setAttribute("data-abe-measure", "1");
            group.setAttribute("pointer-events", "none");
            const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
            line.setAttribute("x1", String(row.start[0]));
            line.setAttribute("y1", String(row.start[1]));
            line.setAttribute("x2", String(row.end[0]));
            line.setAttribute("y2", String(row.end[1]));
            line.setAttribute("stroke", color);
            line.setAttribute("stroke-width", "1.35");
            line.setAttribute("vector-effect", "non-scaling-stroke");
            line.setAttribute("pointer-events", "none");
            if (row.dashed !== false || row.style === "committed" || row.style === "alt") {
                line.setAttribute("stroke-dasharray", "7 5");
            }
            group.appendChild(line);
            [[row.start, "start"], [row.end, "end"]].forEach((entry) => {
                const tick = document.createElementNS("http://www.w3.org/2000/svg", "circle");
                tick.setAttribute("cx", String(entry[0][0]));
                tick.setAttribute("cy", String(entry[0][1]));
                tick.setAttribute("r", String(2.2 / safeScale));
                tick.setAttribute("fill", color);
                tick.setAttribute("pointer-events", "none");
                group.appendChild(tick);
            });
            if (row.label) {
                const midX = (Number(row.start[0]) + Number(row.end[0])) / 2;
                const midY = (Number(row.start[1]) + Number(row.end[1])) / 2;
                const dx = Number(row.end[0]) - Number(row.start[0]);
                const dy = Number(row.end[1]) - Number(row.start[1]);
                const len = Math.hypot(dx, dy) || 1;
                const ox = (-dy / len) * (8 / safeScale);
                const oy = (dx / len) * (8 / safeScale);
                const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
                text.setAttribute("x", String(midX + ox));
                text.setAttribute("y", String(midY + oy));
                text.setAttribute("text-anchor", "middle");
                text.setAttribute("dominant-baseline", "middle");
                text.setAttribute("font-size", String(fontMm));
                text.setAttribute("font-family", "Tahoma,Arial,sans-serif");
                text.setAttribute("font-weight", "700");
                text.setAttribute("fill", color);
                text.setAttribute("paint-order", "stroke");
                text.setAttribute("stroke", "#fff");
                text.setAttribute("stroke-width", String(3 / safeScale));
                text.setAttribute("pointer-events", "none");
                text.setAttribute("direction", "ltr");
                text.textContent = String(row.label);
                group.appendChild(text);
            }
            world.appendChild(group);
        });
    }

    function render(host, storeView, handlers) {
        const projection = storeView.projection || {};
        const session = storeView.session || null;
        const sheets = projection.sheets || [];
        const elements = projection.elements || [];
        const previousStage = host.querySelector("[data-abe-stage]");
        const stageW = Math.max(
            (previousStage && previousStage.clientWidth) || host.clientWidth || 640,
            1
        );
        const stageH = Math.max(
            (previousStage && previousStage.clientHeight) || host.clientHeight || 480,
            1
        );
        const boardWidths = sheets.map((sheet) => sheetSize(sheet).widthMm);
        const columns = storeView.viewport.columns || columnCount(
            boardWidths.length ? Math.max(...boardWidths) : 1,
            stageW
        );
        let layout = sheetLayout(sheets, columns);
        layout = mergeSessionLayout(layout, session);
        let scale = Number(storeView.viewport.scale) || 0;
        if (!storeView.viewport.opened && !storeView.viewport.userAdjusted) {
            scale = openingScale(layout.maxBoardMm, columns, stageW);
        }
        if (!(scale > 0)) scale = openingScale(layout.maxBoardMm, columns, stageW);
        const metrics = worldMetricsFor(layout, scale);
        const viewportPads = cameraPads(storeView.viewport);
        const openingFrame = (!storeView.viewport.opened && !storeView.viewport.userAdjusted)
            ? contentFrame(metrics, layout.fitBounds, scale, stageW, stageH)
            : null;
        let padX = openingFrame
            ? openingFrame.padX
            : (storeView.viewport.padX != null ? viewportPads.padX : SCENE_PAD_PX);
        let padY = openingFrame
            ? openingFrame.padY
            : (storeView.viewport.padY != null ? viewportPads.padY : SCENE_PAD_PX);
        let scrollX = openingFrame
            ? openingFrame.scrollX
            : (Number(storeView.viewport.scrollX) || 0);
        let scrollY = openingFrame
            ? openingFrame.scrollY
            : (Number(storeView.viewport.scrollY) || 0);
        let trailX = Number(storeView.viewport.trailX);
        let trailY = Number(storeView.viewport.trailY);
        if (!(trailX >= 0)) trailX = SCENE_PAD_PX;
        if (!(trailY >= 0)) trailY = SCENE_PAD_PX;

        // Keep on-screen world stable when mergeSessionLayout expands/shrinks mins.
        if (storeView.viewport.opened || storeView.viewport.userAdjusted) {
            const originFix = reconcileCameraWorldOrigin({
                scale,
                scrollX,
                scrollY,
                padX,
                padY,
                trailX,
                trailY,
                minX: storeView.viewport.minX != null ? storeView.viewport.minX : metrics.minX,
                minY: storeView.viewport.minY != null ? storeView.viewport.minY : metrics.minY,
            }, metrics.minX, metrics.minY, { width: stageW, height: stageH }, {
                width: metrics.width,
                height: metrics.height,
            });
            if (originFix) {
                scrollX = originFix.scrollX;
                scrollY = originFix.scrollY;
                padX = originFix.padX;
                padY = originFix.padY;
                trailX = originFix.trailX;
                trailY = originFix.trailY;
                if (handlers && handlers.persistCamera) {
                    handlers.persistCamera({
                        scrollX,
                        scrollY,
                        padX,
                        padY,
                        trailX,
                        trailY,
                        minX: metrics.minX,
                        minY: metrics.minY,
                    });
                }
            }
        }

        const sized = contentSizeForCamera({
            scale,
            scrollX,
            scrollY,
            padX,
            padY,
            trailX,
            trailY,
            minX: metrics.minX,
            minY: metrics.minY,
        }, { width: stageW, height: stageH }, {
            width: metrics.width,
            height: metrics.height,
        });
        trailX = sized.trailX;
        trailY = sized.trailY;
        const contentW = sized.contentW;
        const contentH = sized.contentH;
        metrics.pad = padX;
        metrics.padX = padX;
        metrics.padY = padY;
        metrics.trailX = trailX;
        metrics.trailY = trailY;
        metrics.scrollX = scrollX;
        metrics.scrollY = scrollY;
        if (
            handlers && handlers.persistCamera
            && (
                Math.abs(trailX - (Number(storeView.viewport.trailX) || SCENE_PAD_PX)) > 1e-9
                || Math.abs(trailY - (Number(storeView.viewport.trailY) || SCENE_PAD_PX)) > 1e-9
                || storeView.viewport.minX == null
                || storeView.viewport.minY == null
                || Math.abs(Number(storeView.viewport.minX) - metrics.minX) > 1e-9
                || Math.abs(Number(storeView.viewport.minY) - metrics.minY) > 1e-9
            )
        ) {
            handlers.persistCamera({
                trailX,
                trailY,
                minX: metrics.minX,
                minY: metrics.minY,
            });
        }

        const selectedKeys = new Set(selectedPieceKeys(storeView, session));
        const multiSelection = selectedKeys.size > 1;
        const staleCut = new Set((session && session.stale_cut_path_sheets) || []);
        const staleText = new Set((session && session.stale_unbound_text_sheets) || []);
        const body = [];
        const sheetGroups = {};

        sheets.forEach((sheet) => {
            const key = String(sheet.sheet_no);
            sheetGroups[key] = [];
        });
        sheetGroups.__outside = [];

        elements.forEach((element) => {
            const matchKey = String(element.layer_match_key || "");
            const visible = storeView.layerVisibility[matchKey] !== false;
            const sessionPiece = sessionPieceForElement(session, element);
            if (sessionPiece && sessionPiece.distribution === "excluded") return;
            if (
                session
                && session.boards
                && element.sheet_no != null
                && element.sheet_no !== ""
                && !session.boards[String(element.sheet_no)]
                && !(sessionPiece && (sessionPiece.sheet_no == null || sessionPiece.sheet_no === ""))
            ) {
                return;
            }
            const sheetKey = sessionPiece
                ? (sessionPiece.sheet_no == null || sessionPiece.sheet_no === ""
                    ? "__outside"
                    : String(sessionPiece.sheet_no))
                : String(element.sheet_no == null ? "__outside" : element.sheet_no);
            const sheetPos = layout.positions[sheetKey] || { originX: 0, originY: 0, trimX: 0, trimY: 0 };
            const color = element.aci_color != null
                ? aciToCss(element.aci_color, layerColor(storeView, matchKey))
                : layerColor(storeView, matchKey);
            const selectedPiece = sessionPiece
                ? selectedKeys.has(sessionPiece.piece_key)
                : (storeView.selectedPieceId != null
                    && Number(element.piece_id) === Number(storeView.selectedPieceId));
            const selectedSheet = storeView.selectedSheetNo != null
                && Number(element.sheet_no) === Number(storeView.selectedSheetNo)
                && element.kind === "sheet_outline";
            const selected = selectedPiece || selectedSheet
                || (storeView.selectedElementId && storeView.selectedElementId === element.element_id);

            if (!visible) return;

            const origin = sessionPiece
                ? pieceOrigin(session, sessionPiece, layout)
                : {
                    ox: sheetPos.originX + (sheetPos.trimX || 0),
                    oy: sheetPos.originY + (sheetPos.trimY || 0),
                    dx: 0,
                    dy: 0,
                    rotationDeg: 0,
                    pivotX: 0,
                    pivotY: 0,
                    entryPivotX: 0,
                    entryPivotY: 0,
                };
            const pointer = "all";
            const opacity = 1;

            const pieceKeyAttr = sessionPiece
                ? ` data-piece-key="${esc(sessionPiece.piece_key)}" data-piece-instance="${esc(sessionPiece.piece_instance_id)}" data-editable="${sessionPiece.editable ? "1" : "0"}" data-rotation-deg="${esc(String(Number(sessionPiece.rotation_deg) || 0))}"`
                : "";
            const pieceIdAttr = element.piece_id != null ? ` data-piece-id="${esc(element.piece_id)}"` : "";

            if (element.kind === "sheet_outline") {
                const fullW = (Number(element.payload.full_width_cm) || 122) * 10;
                const fullH = (Number(element.payload.full_length_cm) || 244) * 10;
                const usableW = (Number(element.payload.usable_width_cm) || fullW / 10) * 10;
                const usableH = (Number(element.payload.usable_length_cm) || fullH / 10) * 10;
                const trimX = (Number(element.payload.applied_trim_width_cm) || ((fullW - usableW) / 20)) * 10;
                const trimY = (Number(element.payload.applied_trim_length_cm) || ((fullH - usableH) / 20)) * 10;
                const pos = layout.positions[String(element.sheet_no)] || sheetPos;
                const isOffcut = String((element.payload && element.payload.resource_kind) || "").toUpperCase() === "OFFCUT";
                const style = displayStyle();
                const boardPieces = ((storeView.projection && storeView.projection.pieces) || []).filter((row) => {
                    if (Number(row.sheet_no) !== Number(element.sheet_no)) return false;
                    if (!session || !session.pieces) return true;
                    const instanceId = String(row.piece_instance_id || "").trim();
                    const live = instanceId ? session.pieces[`instance:${instanceId}`] : null;
                    if (!live) return true;
                    if (live.distribution === "excluded") return false;
                    return Number(live.sheet_no) === Number(element.sheet_no);
                });
                const waste = style ? style.sheetWaste(storeView.projection.board || {}, boardPieces) : null;
                const title = isOffcut
                    ? __("Offcut")
                    : __("Board {0}", [String(element.sheet_no)]);
                const stats = waste
                    ? __("Pieces: {0} | waste: {1} m² ({2}%)", [String(waste.pieces), String(waste.waste), String(waste.percent)])
                    : "";
                const edgeDisplay = window.AlmdinaEdgeDisplay;
                const titlePx = (edgeDisplay && edgeDisplay.BOARD_TITLE_PX) || 11.5;
                const statsPx = (edgeDisplay && edgeDisplay.BOARD_STATS_PX) || 9;
                const edgePx = (edgeDisplay && edgeDisplay.BOARD_ORIGINAL_EDGE_PX) || 9;
                const edgeNames = edgeDisplay && typeof edgeDisplay.originalEdges === "function"
                    ? edgeDisplay.originalEdges(
                        projection.board || {},
                        {
                            pieces: boardPieces.map((row) => {
                                const placement = (row && row.placement_cm) || {};
                                return { x: placement.x, y: placement.y, w: placement.w, h: placement.h };
                            }),
                            full_width_cm: element.payload.full_width_cm,
                            full_length_cm: element.payload.full_length_cm,
                            usable_width_cm: element.payload.usable_width_cm,
                            usable_length_cm: element.payload.usable_length_cm,
                            applied_trim_width_cm: element.payload.applied_trim_width_cm,
                            applied_trim_length_cm: element.payload.applied_trim_length_cm,
                        }
                    )
                    : [];
                const edgeOrder = ["top", "bottom", "right", "left"].filter((name) => edgeNames.indexOf(name) >= 0);
                const edgeLabels = {
                    top: __("Original edge · top"),
                    bottom: __("Original edge · bottom"),
                    right: __("Original edge · right"),
                    left: __("Original edge · left"),
                };
                const edgeText = edgeOrder.map((name) => edgeLabels[name]).join("  ");
                const titleLift = screenFontMm(edgeOrder.length ? 16 : 4, scale);
                const titleY = pos.originY - titleLift;
                const edgeY = pos.originY - screenFontMm(3, scale);
                // data-sheet identifies the frame for selection. data-sheet-group
                // belongs only on the outer host that wraps frame + pieces so
                // board-drag preview translate applies once (never double-shift).
                const html = `<g data-sheet="${esc(String(element.sheet_no))}" data-element-id="${esc(element.element_id)}" class="abe-sheet${selected ? " is-selected" : ""}${isOffcut ? " is-offcut" : ""}" style="pointer-events:${pointer};opacity:${opacity}">
                    <text class="abe-board-title" data-screen-px="${titlePx}" data-board-drag="${esc(String(element.sheet_no))}" x="${pos.originX}" y="${titleY}" font-size="${screenFontMm(titlePx, scale)}" font-weight="900" fill="#101828" style="pointer-events:all;cursor:default">${esc(title)}</text>
                    <text class="abe-board-stats" data-screen-px="${statsPx}" x="${pos.originX + fullW}" y="${titleY}" text-anchor="end" font-size="${screenFontMm(statsPx, scale)}" fill="#667085" pointer-events="none">${esc(stats)}</text>
                    ${edgeText ? `<text class="abe-board-original-edges" data-screen-px="${edgePx}" x="${pos.originX}" y="${edgeY}" font-size="${screenFontMm(edgePx, scale)}" font-weight="700" fill="#8a5a00" pointer-events="none">${esc(edgeText)}</text>` : ""}
                    <rect x="${pos.originX}" y="${pos.originY}" width="${fullW}" height="${fullH}" fill="#ffffff" stroke="#111111" stroke-width="2" vector-effect="non-scaling-stroke"/>
                    <rect class="abe-board-waste-hatch" x="${pos.originX}" y="${pos.originY}" width="${fullW}" height="${fullH}" fill="url(#abe-waste-hatch)" pointer-events="none"/>
                </g>`;
                (sheetGroups[String(element.sheet_no)] || body).push(html);
                return;
            }

            if (element.kind === "cut_path" || String(element.layer_role || "").toUpperCase() === "CUT_PATH") {
                const sheetForStale = String(element.sheet_no == null ? "" : element.sheet_no);
                if (staleCut.has(sheetForStale)) {
                    // Shared cut paths are not moved with a single piece; hide
                    // stale uploaded paths from the experimental layout preview.
                    return;
                }
            }

            const boards = (session && session.boards) || {};

            if (element.kind === "text_label") {
                const boundInstance = String(element.piece_instance_id || "").trim();
                if (!boundInstance && staleText.has(String(element.sheet_no == null ? "" : element.sheet_no))) {
                    return;
                }
                if (boundInstance && sessionPiece) {
                    // Bound system labels travel with the piece identity. Uploaded
                    // free text without piece_instance_id stays reference-only.
                    const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
                    const world = MoveGeometry.worldFootprint(sessionPiece, boards);
                    const absX = world.bounds.x + 4;
                    const absY = world.bounds.y + 14;
                    const height = Number(element.payload.height_mm) || 12;
                    const html = `<text${pieceKeyAttr}${pieceIdAttr} x="${absX}" y="${absY}" font-size="${height}" fill="${esc(color)}" style="pointer-events:none;opacity:${opacity}" direction="ltr">${esc(element.payload.text || sessionPiece.label || "")}</text>`;
                    (sheetGroups[sheetKey] || sheetGroups.__outside).push(html);
                    return;
                }
                const x = (sheetPos.originX + (sheetPos.trimX || 0)) + (Number(element.payload.x_mm) || 0);
                const y = (sheetPos.originY + (sheetPos.trimY || 0)) + (Number(element.payload.y_mm) || 0);
                const height = Number(element.payload.height_mm) || 12;
                const html = `<text x="${x}" y="${y}" font-size="${height}" fill="${esc(color)}" style="pointer-events:none;opacity:${opacity * 0.85}" direction="ltr">${esc(element.payload.text || "")}</text>`;
                (sheetGroups[sheetKey] || sheetGroups.__outside).push(html);
                return;
            }

            // Piece geometry is emitted in world millimetres. One conversion only —
            // never translate by board origin again on the SVG node.
            if (element.kind === "placement_rect") {
                const rect = placementRectMm(element.payload);
                const corners = [
                    [rect.x, rect.y],
                    [rect.x + rect.w, rect.y],
                    [rect.x + rect.w, rect.y + rect.h],
                    [rect.x, rect.y + rect.h],
                ].map((point) => (
                    sessionPiece
                        ? entryPointToWorld(point, sessionPiece, boards)
                        : [point[0] + origin.ox, point[1] + origin.oy]
                ));
                const d = pointsToPath(corners, true);
                const role = fillRoleOf(element, sessionPiece, storeView);
                const piece = pieceRecord(element, sessionPiece, storeView);
                const exact = role === "special" && Boolean(piece && piece.exact_geometry);
                const paint = materialPaint(role, false, exact);
                const edges = edgeMarkSvg(
                    piece,
                    (element.payload && element.payload.display_edges) || (piece && piece.display_edges) || null,
                    (element.payload && element.payload.geometry_source) || (piece && piece.geometry_source) || "",
                    sessionPiece,
                    boards,
                    origin,
                    scale,
                    defaultEdgeTypeOf(storeView),
                    storeView
                );
                const caption = pieceCaption(element, sessionPiece, storeView, boards, origin, scale);
                const html = `<g${pieceKeyAttr}${pieceIdAttr} data-element-id="${esc(element.element_id)}" data-fill-role="${esc(role)}" class="abe-piece${selected ? " is-selected" : ""}${sessionPiece && !sessionPiece.editable ? " is-locked" : ""}" style="pointer-events:${pointer};opacity:${opacity}">
                    <path d="${esc(d)}" fill="${esc(paint.fill)}" stroke="${esc(paint.stroke)}" stroke-width="${paint.strokeWidth}" vector-effect="non-scaling-stroke"/>
                    ${edges}
                    ${doubleEdgeMarkup(corners, (element.payload && element.payload.display_edges) || null)}
                    ${caption}
                </g>`;
                (sheetGroups[sheetKey] || sheetGroups.__outside).push(html);
                return;
            }

            if (element.kind === "unresolved" && element.payload && element.payload.reason === "special_geometry_unavailable") {
                const rect = placementRectMm(element.payload);
                const corners = [
                    [rect.x, rect.y],
                    [rect.x + rect.w, rect.y],
                    [rect.x + rect.w, rect.y + rect.h],
                    [rect.x, rect.y + rect.h],
                ].map((point) => (
                    sessionPiece
                        ? entryPointToWorld(point, sessionPiece, boards)
                        : [point[0] + origin.ox, point[1] + origin.oy]
                ));
                const xs = corners.map((point) => point[0]);
                const ys = corners.map((point) => point[1]);
                const html = `<g${pieceKeyAttr}${pieceIdAttr} data-element-id="${esc(element.element_id)}" class="abe-piece is-unavailable${selected ? " is-selected" : ""}" style="pointer-events:${pointer};opacity:${Math.max(opacity, selected ? 0.5 : 0)}" title="${esc(__("Special geometry unavailable — not editable"))}">
                    <rect x="${Math.min(...xs)}" y="${Math.min(...ys)}" width="${Math.max(...xs) - Math.min(...xs)}" height="${Math.max(...ys) - Math.min(...ys)}" fill="none" stroke="${selected ? "#0b5fff" : "#98a2b3"}" stroke-dasharray="10 8" stroke-width="1.6"/>
                </g>`;
                (sheetGroups[sheetKey] || sheetGroups.__outside).push(html);
                return;
            }

            let geometry = element.geometry;
            if (
                sessionPiece
                && element.kind === "finished_outline"
                && Array.isArray(sessionPiece.outline_mm)
                && sessionPiece.outline_mm.length >= 3
            ) {
                // Authoritative session outline already carries pose; lift to world once.
                geometry = {
                    outer: sessionPointsToWorld(sessionPiece.outline_mm, sessionPiece, boards),
                    holes: Array.isArray(sessionPiece.glass_hole_local_mm)
                        ? [sessionPointsToWorld(sessionPiece.glass_hole_local_mm, sessionPiece, boards)]
                        : [],
                };
            } else if (
                sessionPiece
                && element.kind === "hole"
                && Array.isArray(sessionPiece.glass_hole_local_mm)
                && sessionPiece.glass_hole_local_mm.length >= 3
            ) {
                geometry = {
                    outer: sessionPointsToWorld(sessionPiece.glass_hole_local_mm, sessionPiece, boards),
                    holes: [],
                };
            } else if (sessionPiece && geometry && Array.isArray(geometry.outer)) {
                geometry = {
                    outer: geometry.outer.map((point) => entryPointToWorld(point, sessionPiece, boards)),
                    holes: (geometry.holes || []).map((hole) => (
                        hole.map((point) => entryPointToWorld(point, sessionPiece, boards))
                    )),
                };
            } else if (sessionPiece && geometry && Array.isArray(geometry.path)) {
                geometry = {
                    path: geometry.path.map((point) => entryPointToWorld(point, sessionPiece, boards)),
                    closed: geometry.closed,
                };
            } else if (geometry && Array.isArray(geometry.outer)) {
                geometry = {
                    outer: geometry.outer.map((point) => [Number(point[0]) + origin.ox, Number(point[1]) + origin.oy]),
                    holes: (geometry.holes || []).map((hole) => (
                        hole.map((point) => [Number(point[0]) + origin.ox, Number(point[1]) + origin.oy])
                    )),
                };
            } else if (geometry && Array.isArray(geometry.path)) {
                geometry = {
                    path: geometry.path.map((point) => [Number(point[0]) + origin.ox, Number(point[1]) + origin.oy]),
                    closed: geometry.closed,
                };
            }

            const d = geometryPath(geometry);
            if (!d && element.payload && element.payload.start && element.payload.end) {
                const a = sessionPiece
                    ? entryPointToWorld(element.payload.start, sessionPiece, boards)
                    : [Number(element.payload.start[0]) + origin.ox, Number(element.payload.start[1]) + origin.oy];
                const b = sessionPiece
                    ? entryPointToWorld(element.payload.end, sessionPiece, boards)
                    : [Number(element.payload.end[0]) + origin.ox, Number(element.payload.end[1]) + origin.oy];
                const html = `<line data-element-id="${esc(element.element_id)}"${pieceKeyAttr}${pieceIdAttr} x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="${esc(color)}" stroke-width="${selected ? 2.2 : 1.2}" style="pointer-events:${pointer};opacity:${opacity}"/>`;
                (sheetGroups[sheetKey] || sheetGroups.__outside).push(html);
                return;
            }
            if (!d) return;
            const role = fillRoleOf(element, sessionPiece, storeView);
            const style = displayStyle();
            let fill = "none";
            let stroke = color;
            let strokeWidth = 1.3;
            let dash = "";
            const shaped = element.kind === "finished_outline" && geometry && style
                && style.isShaped(geometry.outer, geometry.holes);
            if (element.kind === "hole") {
                fill = "#ffffff";
                stroke = "#111111";
                strokeWidth = 1;
            } else if (element.kind === "finished_outline") {
                const exact = role === "special" && Boolean((pieceRecord(element, sessionPiece, storeView) || {}).exact_geometry);
                const paint = materialPaint(role, shaped, exact);
                fill = paint.fill;
                stroke = paint.stroke;
                strokeWidth = paint.strokeWidth;
            } else if (element.kind === "addon_overlay") {
                const overlay = style
                    ? style.overlayPaint(element.payload && element.payload.kind)
                    : { stroke: "#1d6fbf", fill: "none", dash: "3 2.2", width: 0.7 };
                stroke = overlay.stroke;
                fill = overlay.fill;
                strokeWidth = overlay.width;
                dash = overlay.dash ? ` stroke-dasharray="${overlay.dash}"` : "";
            }
            let edges = "";
            let caption = "";
            if (element.kind === "finished_outline" && geometry && Array.isArray(geometry.outer)) {
                const piece = pieceRecord(element, sessionPiece, storeView);
                edges = edgeMarkSvg(
                    piece,
                    (element.payload && element.payload.display_edges) || (piece && piece.display_edges) || null,
                    (element.payload && element.payload.geometry_source) || (piece && piece.geometry_source) || "",
                    sessionPiece,
                    boards,
                    origin,
                    scale,
                    defaultEdgeTypeOf(storeView),
                    storeView
                );
                caption = pieceCaption(element, sessionPiece, storeView, boards, origin, scale);
            }
            const html = (edges || caption)
                ? `<g data-element-id="${esc(element.element_id)}"${pieceKeyAttr}${pieceIdAttr} data-fill-role="${esc(role)}" class="abe-piece${selected ? " is-selected" : ""}${sessionPiece && !sessionPiece.editable ? " is-locked" : ""}" style="pointer-events:${pointer};opacity:${opacity}"><path d="${esc(d)}" fill="${esc(fill)}" fill-rule="evenodd" stroke="${esc(stroke)}" stroke-width="${strokeWidth}"${dash} vector-effect="non-scaling-stroke"/>${edges}${doubleEdgeMarkup(geometry && geometry.outer, (element.payload && element.payload.display_edges) || null)}${caption}</g>`
                : `<path data-element-id="${esc(element.element_id)}"${pieceKeyAttr}${pieceIdAttr} data-fill-role="${esc(role)}" d="${esc(d)}" fill="${esc(fill)}" fill-rule="evenodd" stroke="${esc(stroke)}" stroke-width="${strokeWidth}"${dash} vector-effect="non-scaling-stroke" style="pointer-events:${pointer};opacity:${opacity}" class="abe-piece${selected ? " is-selected" : ""}${sessionPiece && !sessionPiece.editable ? " is-locked" : ""}"/>`;
            (sheetGroups[sheetKey] || sheetGroups.__outside).push(html);
        });

        Object.keys(sheetGroups).forEach((key) => {
            if (key === "__outside") return;
            const parts = sheetGroups[key] || [];
            if (!parts.length) return;
            body.push(`<g data-sheet-group="${esc(key)}">${parts.join("")}</g>`);
        });
        if ((sheetGroups.__outside || []).length) {
            body.push(`<g data-sheet-group="outside" class="abe-outside-group">${sheetGroups.__outside.join("")}</g>`);
        }
        const selectionChrome = selectionChromeSvg(session, storeView, metrics.scale || 1);
        if (selectionChrome) body.push(selectionChrome);

        const dropNote = storeView.dropMessage
            ? `<div class="abe-drop-message" role="status">${esc(storeView.dropMessage)}</div>`
            : "";

        const selectedKeyList = selectedPieceKeys(storeView, session);
        const selectedSessionPiece = !multiSelection && selectedKeyList.length === 1
            ? session.pieces[selectedKeyList[0]]
            : null;
        const RG = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.RotationGeometry;
        const angleEligibility = selectedSessionPiece && RG
            ? RG.pieceRotationEligibility(session, selectedSessionPiece.piece_key)
            : { rotatable: false, reason: multiSelection ? "multi_selection" : "no_selection" };
        const angleEditable = Boolean(selectedSessionPiece && angleEligibility.rotatable);
        const angleValue = selectedSessionPiece
            ? (Number(selectedSessionPiece.rotation_deg) || 0)
            : 0;
        const angleTitle = multiSelection
            ? __("Select one piece to set its rotation angle. Group rotation is not available.")
            : (angleEditable
                ? __("Rotation angle in degrees")
                : __(
                    RG && typeof RG.reasonMessage === "function"
                        ? RG.reasonMessage(angleEligibility.reason)
                        : "This piece cannot be rotated."
                ));
        const TG = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.TransformGeometry;
        const transformReason = multiSelection
            ? "multi_selection"
            : (!selectedSessionPiece ? "no_selection" : null);
        const mirrorEligibility = (!transformReason && selectedSessionPiece && TG && session)
            ? TG.angleMirrorEligibility(session, selectedSessionPiece.piece_key)
            : { allowed: false, reason: transformReason || "no_selection" };
        const transformMirrorEnabled = Boolean(mirrorEligibility.allowed);
        const anglePairTitle = angleEditable
            ? null
            : angleTitle;
        const angle0_180Label = __("Toggle rotation 0° ↔ 180°");
        const angle90_270Label = __("Toggle rotation 90° ↔ 270°");
        const transformMirrorTitle = transformMirrorEnabled
            ? __("Mirror this corner or L piece horizontally in its local axes. Apply twice to restore the original shape.")
            : __(
                TG && typeof TG.reasonMessage === "function"
                    ? TG.reasonMessage(mirrorEligibility.reason)
                    : "Angle mirror is only available for corner-break and L pieces."
            );
        const canRemovePiece = Boolean(
            !multiSelection
            && selectedSessionPiece
            && selectedSessionPiece.editable
            && selectedSessionPiece.distribution !== "excluded"
        );
        const removePieceTitle = multiSelection
            ? __("Select one piece to remove it.")
            : __("Remove the selected piece from this session layout. The order row stays unchanged.");
        const canRemoveBoard = Boolean(
            session
            && session.boards
            && storeView.selectedSheetNo != null
            && session.boards[String(storeView.selectedSheetNo)]
        );

        const magnetOn = storeView.magnetEnabled !== false;
        const measureOn = storeView.measureToolActive === true;
        const toolSep = `<span class="abe-tool-sep" aria-hidden="true"></span>`;
        host.innerHTML = `
            ${dropNote}
            <div class="abe-canvas-stage${measureOn ? " is-measuring" : ""}" data-abe-stage="1">
                <svg class="abe-svg" xmlns="http://www.w3.org/2000/svg" width="${contentW}" height="${contentH}" viewBox="0 0 ${contentW} ${contentH}" role="img" aria-label="${esc(__("Board layout canvas"))}" style="direction:ltr;touch-action:pan-x pan-y">
                    <defs>${(displayStyle() && displayStyle().defs(scale)) || ""}</defs>
                    <g class="abe-world" transform="translate(${padX - metrics.minX * scale},${padY - metrics.minY * scale}) scale(${scale})">
                        ${body.join("")}
                    </g>
                </svg>
            </div>
            <div class="abe-float-dock">
                <div class="abe-float-stack">
                <div class="abe-canvas-tools abe-float-tools" role="toolbar" aria-label="${esc(__("Canvas tools"))}">
                    ${toolButton("abe-zoom-in", "zoom-in", __("Zoom in"))}
                    ${toolButton("abe-zoom-out", "zoom-out", __("Zoom out"))}
                    ${toolButton("abe-fit-all", "maximize-2", __("Fit all"))}
                    ${toolSep}
                    ${toolButton("abe-undo", "undo-2", __("Undo"), { disabled: !storeView.canUndo })}
                    ${toolButton("abe-redo", "redo-2", __("Redo"), { disabled: !storeView.canRedo })}
                    ${toolButton("abe-restore", "refresh-ccw", __("Restore entry layout"))}
                    ${toolSep}
                    ${toolButton("abe-magnet" + (magnetOn ? " is-active" : ""), "magnet", __("Magnet"), {
                        pressed: magnetOn,
                        attrs: ` data-abe-magnet="1"`,
                        title: __("Magnet: snap pieces to board edges and neighbouring pieces while dragging. Hold Alt to bypass."),
                    })}
                    ${toolButton("abe-measure" + (measureOn ? " is-active" : ""), "ruler", __("Measure"), {
                        pressed: measureOn,
                        attrs: ` data-abe-measure-tool="1"`,
                        title: __("Measure tool: drag a straight line on a board to read its length in millimetres. Esc clears the line."),
                    })}
                    <label class="abe-angle-field${angleEditable ? "" : " is-disabled"}" title="${esc(angleTitle)}">
                        <input type="text" inputmode="decimal" class="abe-angle-input" value="${esc(String(Math.round(angleValue * 1000) / 1000))}" ${angleEditable ? "" : "disabled"} aria-label="${esc(angleTitle)}" title="${esc(angleTitle)}" />
                        <span aria-hidden="true">°</span>
                    </label>
                    ${toolButton("abe-angle-0-180", "arrow-left-right", angle0_180Label, {
                        disabled: !angleEditable,
                        title: anglePairTitle || angle0_180Label,
                    })}
                    ${toolButton("abe-angle-90-270", "arrow-up-down", angle90_270Label, {
                        disabled: !angleEditable,
                        title: anglePairTitle || angle90_270Label,
                    })}
                    ${toolButton("abe-rotate-30", "refresh", __("Rotate +30°"), {
                        disabled: !angleEditable,
                        title: angleEditable
                            ? __("Add 30 degrees in the positive rotation direction.")
                            : angleTitle,
                    })}
                    ${toolButton("abe-angle-mirror", "flip-horizontal-2", __("Mirror angle"), {
                        disabled: !transformMirrorEnabled,
                        title: transformMirrorTitle,
                    })}
                    ${toolSep}
                    ${toolButton("abe-remove-piece", "trash-2", __("Remove from distribution"), {
                        disabled: !canRemovePiece,
                        title: removePieceTitle,
                    })}
                    ${toolButton("abe-remove-board", "square-x", __("Remove board from distribution"), { disabled: !canRemoveBoard })}
                </div>
                </div>
            </div>
        `;

        const stage = host.querySelector("[data-abe-stage]");
        const svg = host.querySelector(".abe-svg");
        host.__abeWorldMetrics = metrics;
        host.__abeLayout = layout;
        const cameraToken = Number(storeView.viewport.cameraToken) || 0;
        const takeOwned = handlers && handlers.takeCamera && handlers.takeCamera(cameraToken);
        let targetScrollX = takeOwned
            ? scrollX
            : (handlers && handlers.readScroll
                ? Number((handlers.readScroll() || {}).x) || 0
                : scrollX);
        let targetScrollY = takeOwned
            ? scrollY
            : (handlers && handlers.readScroll
                ? Number((handlers.readScroll() || {}).y) || 0
                : scrollY);
        // Content was sized for the camera scroll; still verify browser acceptance once.
        stage.scrollLeft = targetScrollX;
        stage.scrollTop = targetScrollY;
        const appliedX = Number(stage.scrollLeft) || 0;
        const appliedY = Number(stage.scrollTop) || 0;
        if (
            takeOwned
            && handlers
            && handlers.persistCamera
            && (
                Math.abs(appliedX - targetScrollX) > 0.5
                || Math.abs(appliedY - targetScrollY) > 0.5
            )
        ) {
            // Expand trail so the intended scroll becomes attainable on next paint.
            const rescue = fitCameraScroll({
                scale,
                scrollX: targetScrollX,
                scrollY: targetScrollY,
                padX,
                padY,
                trailX: Math.max(trailX, targetScrollX + stageW - metrics.width * scale - padX),
                trailY: Math.max(trailY, targetScrollY + stageH - FLOAT_CLEARANCE_PX - metrics.height * scale - padY),
                minX: metrics.minX,
                minY: metrics.minY,
            }, { width: stageW, height: stageH }, {
                width: metrics.width,
                height: metrics.height,
            });
            handlers.persistCamera({
                scrollX: rescue.scrollX,
                scrollY: rescue.scrollY,
                padX: rescue.padX,
                padY: rescue.padY,
                trailX: rescue.trailX,
                trailY: rescue.trailY,
                minX: metrics.minX,
                minY: metrics.minY,
            });
            svg.setAttribute("width", String(rescue.contentW));
            svg.setAttribute("height", String(rescue.contentH));
            svg.setAttribute("viewBox", `0 0 ${rescue.contentW} ${rescue.contentH}`);
            stage.scrollLeft = rescue.scrollX;
            stage.scrollTop = rescue.scrollY;
            metrics.contentWidth = rescue.contentW;
            metrics.contentHeight = rescue.contentH;
            metrics.trailX = rescue.trailX;
            metrics.trailY = rescue.trailY;
        } else if (takeOwned && handlers && handlers.onScroll) {
            handlers.onScroll(appliedX, appliedY);
        }
        stage.addEventListener("scroll", () => {
            handlers && handlers.onScroll && handlers.onScroll(stage.scrollLeft, stage.scrollTop);
        });
        host.querySelector(".abe-fit-all").onclick = () => handlers && handlers.fitAll && handlers.fitAll(layout);
        host.querySelector(".abe-zoom-in").onclick = () => handlers && handlers.zoom && handlers.zoom(1.2);
        host.querySelector(".abe-zoom-out").onclick = () => handlers && handlers.zoom && handlers.zoom(1 / 1.2);
        const floatDock = host.querySelector(".abe-float-dock");
        if (floatDock) {
            floatDock.addEventListener("pointerdown", (event) => {
                event.stopPropagation();
            });
            floatDock.addEventListener("wheel", (event) => {
                event.stopPropagation();
            });
        }
        const magnet = host.querySelector("[data-abe-magnet]");
        if (magnet) {
            magnet.onclick = () => handlers && handlers.toggleMagnet && handlers.toggleMagnet();
        }
        const measure = host.querySelector("[data-abe-measure-tool]");
        if (measure) {
            measure.onclick = () => handlers && handlers.toggleMeasureTool && handlers.toggleMeasureTool();
        }
        const undo = host.querySelector(".abe-undo");
        const redo = host.querySelector(".abe-redo");
        const restore = host.querySelector(".abe-restore");
        if (undo) undo.onclick = () => handlers && handlers.undo && handlers.undo();
        if (redo) redo.onclick = () => handlers && handlers.redo && handlers.redo();
        if (restore) restore.onclick = () => handlers && handlers.restoreEntry && handlers.restoreEntry();
        const removePiece = host.querySelector(".abe-remove-piece");
        const removeBoard = host.querySelector(".abe-remove-board");
        if (removePiece) {
            removePiece.onclick = () => handlers && handlers.removePiece && handlers.removePiece(
                selectedSessionPiece && selectedSessionPiece.piece_key
            );
        }
        if (removeBoard) {
            removeBoard.onclick = () => handlers && handlers.removeBoard && handlers.removeBoard(
                storeView.selectedSheetNo
            );
        }
        const angle0180 = host.querySelector(".abe-angle-0-180");
        const angle90270 = host.querySelector(".abe-angle-90-270");
        const rotate30 = host.querySelector(".abe-rotate-30");
        const angleMirror = host.querySelector(".abe-angle-mirror");
        if (angle0180) {
            angle0180.onclick = () => handlers && handlers.toggleAngle0_180 && handlers.toggleAngle0_180(
                selectedSessionPiece && selectedSessionPiece.piece_key
            );
        }
        if (angle90270) {
            angle90270.onclick = () => handlers && handlers.toggleAngle90_270 && handlers.toggleAngle90_270(
                selectedSessionPiece && selectedSessionPiece.piece_key
            );
        }
        if (rotate30) {
            rotate30.onclick = () => handlers && handlers.rotateByDegrees && handlers.rotateByDegrees(
                selectedSessionPiece && selectedSessionPiece.piece_key,
                30
            );
        }
        if (angleMirror) {
            angleMirror.onclick = () => handlers && handlers.mirrorAngle && handlers.mirrorAngle(
                selectedSessionPiece && selectedSessionPiece.piece_key
            );
        }

        const suppressed = () => handlers && handlers.consumeClickSuppression && handlers.consumeClickSuppression();

        const angleInput = host.querySelector(".abe-angle-input");
        if (angleInput && selectedSessionPiece) {
            const commitAngle = () => {
                if (handlers && handlers.applyAngle) {
                    handlers.applyAngle(selectedSessionPiece.piece_key, angleInput.value);
                }
            };
            angleInput.addEventListener("keydown", (event) => {
                if (event.key === " " || event.code === "Space" || event.key === "Delete") {
                    event.stopPropagation();
                }
                if (event.key === "Enter") {
                    event.preventDefault();
                    commitAngle();
                    angleInput.blur();
                }
            });
            angleInput.addEventListener("wheel", (event) => {
                event.stopPropagation();
            });
            angleInput.addEventListener("change", commitAngle);
        }

        svg.querySelectorAll("[data-abe-rotate-handle]").forEach((node) => {
            node.addEventListener("pointerdown", (event) => {
                if (handlers && handlers.isPanKey && handlers.isPanKey()) return;
                if (event.button === 1) return;
                const pieceKey = node.getAttribute("data-abe-rotate-handle");
                if (handlers && handlers.beginRotateGesture) {
                    handlers.beginRotateGesture(pieceKey, event);
                }
                event.preventDefault();
                event.stopPropagation();
            });
        });

        svg.querySelectorAll("[data-abe-angle-mirror]").forEach((node) => {
            const stopGesture = (event) => {
                event.preventDefault();
                event.stopPropagation();
            };
            node.addEventListener("pointerdown", stopGesture);
            node.addEventListener("click", (event) => {
                stopGesture(event);
                if (suppressed()) return;
                const pieceKey = node.getAttribute("data-abe-angle-mirror");
                if (handlers && handlers.mirrorAngle) handlers.mirrorAngle(pieceKey);
            });
        });

        svg.querySelectorAll("[data-piece-id], [data-piece-key]").forEach((node) => {
            node.addEventListener("pointerdown", (event) => {
                if (handlers && handlers.isPanKey && handlers.isPanKey()) return;
                if (event.button === 1) return;
                const pieceKey = node.getAttribute("data-piece-key");
                const pieceId = node.getAttribute("data-piece-id");
                if (handlers && handlers.beginPieceGesture) {
                    handlers.beginPieceGesture(pieceKey || pieceId, event, {
                        pieceId,
                        elementId: node.getAttribute("data-element-id"),
                    });
                }
            });
            node.addEventListener("click", (event) => {
                event.stopPropagation();
                if (suppressed()) return;
                // Selection is applied on pointerup by the gesture owner.
            });
        });
        svg.querySelectorAll("[data-board-drag]").forEach((node) => {
            node.addEventListener("pointerdown", (event) => {
                if (handlers && handlers.isPanKey && handlers.isPanKey()) return;
                if (event.button === 1) return;
                const sheetNo = node.getAttribute("data-board-drag");
                if (handlers && handlers.beginBoardGesture) {
                    handlers.beginBoardGesture(sheetNo, event);
                }
            });
            node.addEventListener("click", (event) => {
                event.stopPropagation();
                if (suppressed()) return;
            });
        });
        svg.querySelectorAll("[data-sheet]").forEach((node) => {
            node.addEventListener("click", (event) => {
                event.stopPropagation();
                if (suppressed()) return;
                // Title long-press owns board selection; body click still selects.
                if (event.target && event.target.closest && event.target.closest("[data-board-drag]")) return;
                handlers && handlers.selectSheet && handlers.selectSheet(node.getAttribute("data-sheet"));
            });
        });

        let panning = false;
        let ignoreBackgroundClick = false;
        let lastX = 0;
        let lastY = 0;
        const panRequested = (event) => event.button === 1
            || (event.button === 0 && handlers && handlers.isPanKey && handlers.isPanKey());
        svg.addEventListener("click", (event) => {
            if (ignoreBackgroundClick) {
                ignoreBackgroundClick = false;
                return;
            }
            if (suppressed()) return;
            if (event.shiftKey) return;
            if (clickTargetKeepsSelection(event.target)) return;
            if (handlers && handlers.clearSelection) handlers.clearSelection();
        });
        stage.addEventListener("pointerdown", (event) => {
            if (panRequested(event)) {
                ignoreBackgroundClick = true;
                // Pan has priority: cancel any pending long-press on a piece/board.
                if (handlers && handlers.onPanIntent) handlers.onPanIntent();
                panning = true;
                lastX = event.clientX;
                lastY = event.clientY;
                stage.classList.add("is-panning");
                event.preventDefault();
                stage.setPointerCapture(event.pointerId);
                return;
            }
            if (measureOn && event.button === 0 && handlers && handlers.beginMeasureGesture) {
                ignoreBackgroundClick = true;
                if (handlers.beginMeasureGesture(event)) {
                    stage.setPointerCapture(event.pointerId);
                }
            }
        });
        stage.addEventListener("pointermove", (event) => {
            if (handlers && handlers.onCanvasPointerMove) handlers.onCanvasPointerMove(event);
            if (handlers && handlers.onStagePointerMove) handlers.onStagePointerMove(event);
            if (!panning) return;
            const delta = clientDeltaToLocal(stage, event.clientX - lastX, event.clientY - lastY);
            lastX = event.clientX;
            lastY = event.clientY;
            stage.scrollLeft -= delta.x;
            stage.scrollTop -= delta.y;
        });
        stage.addEventListener("pointerup", (event) => {
            if (panning) {
                panning = false;
                stage.classList.remove("is-panning");
                return;
            }
            if (handlers && handlers.onStagePointerUp) handlers.onStagePointerUp(event);
        });
        stage.addEventListener("pointercancel", (event) => {
            panning = false;
            stage.classList.remove("is-panning");
            if (handlers && handlers.onStagePointerCancel) handlers.onStagePointerCancel(event);
        });

        if (storeView.dragPreview) patchDragPreview(host, storeView.dragPreview);
        if (Array.isArray(host.__abeMeasureLines) && host.__abeMeasureLines.length) {
            patchMeasureOverlay(host, host.__abeMeasureLines, scale);
        }

        metrics.contentWidth = contentW;
        metrics.contentHeight = contentH;

        return {
            layout,
            metrics,
            patchDragPreview: (preview) => patchDragPreview(host, preview),
            patchMeasureOverlay: (lines) => patchMeasureOverlay(host, lines, scale),
        };
    }

    function matrixTransformPoint(matrix, x, y) {
        return {
            x: matrix.a * x + matrix.c * y + matrix.e,
            y: matrix.b * x + matrix.d * y + matrix.f,
        };
    }

    function clientToWorldViaCtm(svg, clientX, clientY) {
        if (!svg) return null;
        const worldGroup = typeof svg.querySelector === "function"
            ? svg.querySelector(".abe-world")
            : null;
        const target = worldGroup || svg;
        if (!target || typeof target.getScreenCTM !== "function") return null;
        const ctm = target.getScreenCTM();
        if (!ctm || typeof ctm.inverse !== "function") return null;
        let inverse = null;
        try {
            inverse = ctm.inverse();
        } catch (err) {
            return null;
        }
        if (!inverse) return null;
        const root = (svg.ownerSVGElement && svg.ownerSVGElement.createSVGPoint)
            ? svg.ownerSVGElement
            : (typeof svg.createSVGPoint === "function" ? svg : null);
        if (root) {
            try {
                const point = root.createSVGPoint();
                point.x = clientX;
                point.y = clientY;
                const local = point.matrixTransform(inverse);
                if (local && Number.isFinite(local.x) && Number.isFinite(local.y)) {
                    return { x: local.x, y: local.y };
                }
            } catch (err) {
                /* fall through */
            }
        }
        const local = matrixTransformPoint(inverse, clientX, clientY);
        if (!Number.isFinite(local.x) || !Number.isFinite(local.y)) return null;
        return local;
    }

    function clientToWorldViaMetrics(svg, metrics, clientX, clientY) {
        if (!svg || !metrics || !(metrics.width > 0) || !(metrics.height > 0)) return null;
        if (typeof svg.getBoundingClientRect !== "function") return null;
        const rect = svg.getBoundingClientRect();
        if (!(rect.width > 0) || !(rect.height > 0)) return null;
        const scale = Math.max(Number(metrics.scale) || 1, 1e-9);
        const pads = cameraPads(metrics);
        const minX = Number(metrics.minX) || 0;
        const minY = Number(metrics.minY) || 0;
        const attrW = Number(svg.getAttribute && svg.getAttribute("width"));
        const attrH = Number(svg.getAttribute && svg.getAttribute("height"));
        const contentW = Number(metrics.contentWidth) > 0
            ? Number(metrics.contentWidth)
            : (attrW > 0 ? attrW : rect.width);
        const contentH = Number(metrics.contentHeight) > 0
            ? Number(metrics.contentHeight)
            : (attrH > 0 ? attrH : rect.height);
        // viewBox is "0 0 contentW contentH" — map client → SVG local → world.
        const nx = (clientX - rect.left) / rect.width;
        const ny = (clientY - rect.top) / rect.height;
        const svgX = nx * contentW;
        const svgY = ny * contentH;
        return {
            x: (svgX - pads.padX) / scale + minX,
            y: (svgY - pads.padY) / scale + minY,
        };
    }

    function clientToWorld(svg, metrics, clientX, clientY) {
        const viaCtm = clientToWorldViaCtm(svg, clientX, clientY);
        if (viaCtm) return viaCtm;
        return clientToWorldViaMetrics(svg, metrics, clientX, clientY);
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.CanvasRenderer = Object.freeze({
        render,
        renderPageActions,
        sheetLayout,
        mergeSessionLayout,
        fitBoards,
        frameCamera,
        contentFrame,
        columnCount,
        openingScale,
        shouldZoomWheel,
        normalizedWheelPixels,
        wheelZoomFactor,
        cameraPointToWorld,
        worldToScreen,
        contentSizeForCamera,
        fitCameraScroll,
        zoomAroundFocal,
        reconcileCameraWorldOrigin,
        clientToWorld,
        clientToWorldViaCtm,
        clientToWorldViaMetrics,
        SCALE_MIN,
        SCALE_MAX,
        patchDragPreview,
        patchMeasureOverlay,
        clickTargetKeepsSelection,
        leftOuterEdgeMidpoint,
        FIT_PADDING_PX,
        SCENE_PAD_PX,
        FLOAT_CLEARANCE_PX,
        GRID_WIDTH_RATIO,
        OPENING_SCALE_FACTOR,
        UI_ZOOM,
        declaredUiZoom,
        elementCssZoom,
        clientPointToLocal,
        clientDeltaToLocal,
        BOARD_SCREEN_MIN_PX,
        BOARD_SCREEN_MAX_PX,
        BOARD_TITLE_MM,
    });
})();
