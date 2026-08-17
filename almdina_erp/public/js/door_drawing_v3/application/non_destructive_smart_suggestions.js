(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    const S = root.Snapping;
    const V = root.ShapeView;
    const F = root.SmartFreehandPolicy;
    const I = root.SmartStrokeIntelligence;
    const Reconstructor = root.AdaptiveStrokeReconstructor;
    const Suggest = root.SmartSuggestionPolicy;
    const SmartPen = root.SmartPen;
    const Editor = root.Editor;
    if (!G || !D || !S || !V || !F || !I || !Reconstructor || !Suggest || !SmartPen || !Editor) {
        throw new Error("Door Drawing V3 smart pen stack must load before non-destructive suggestions");
    }

    function render(c) { V.render(c); }

    function clearSuggestion(c, shouldRender = false) {
        if (!c || !c.smartSuggestion) return false;
        c.smartSuggestion = null;
        if (shouldRender) render(c);
        return true;
    }

    function resetCompetingPenState(c) {
        if (!c) return false;
        const transientKeys = [
            "bezierPathDraft",
            "bezierPenGesture",
            "bezierGesture",
            "vectorPathDraft",
            "vectorGesture",
            "vectorMarquee",
            "vectorSnapState",
            "vectorActiveTranslation",
            "previewObject",
        ];
        let changed = false;
        transientKeys.forEach(key => {
            if (c[key] !== null && c[key] !== undefined) changed = true;
            c[key] = null;
        });
        return changed;
    }

    function execute(c, document, label) {
        c.history.execute(document, label);
        c.dirty = true;
        render(c);
    }

    function pxToMm(c, px) {
        return S.worldTolerance(c.viewport.scale, px);
    }

    function resolveEndpoint(c, raw, stickyTarget = null) {
        return S.resolvePoint(c.history.current(), raw, {
            viewportScale: c.viewport.scale,
            snapPx: SmartPen.FREEHAND_ENDPOINT_SNAP_PX,
            stickyTarget,
        });
    }

    function closeToleranceMm(c) {
        return pxToMm(c, SmartPen.CLOSE_CAPTURE_PX);
    }

    function closeCandidate(c, point) {
        const stroke = c.penStroke;
        if (!stroke || stroke.rawPoints.length < 5) return false;
        const travelled = F.polylineLength(stroke.rawPoints);
        return travelled > closeToleranceMm(c) * 2.5
            && G.distance(stroke.startPoint, point) <= closeToleranceMm(c);
    }

    function appendEventSamples(c, event) {
        const stroke = c.penStroke;
        if (!stroke || stroke.pointerId !== event.pointerId) return null;
        const events = typeof event.getCoalescedEvents === "function" ? event.getCoalescedEvents() : [event];
        const profile = stroke.profile || SmartPen.inputProfile(stroke.pointerType);
        const minSampleMm = Math.max(G.EPSILON_MM, pxToMm(c, profile.sampleSpacingPx));
        const motionScaleMm = Math.max(G.EPSILON_MM, pxToMm(c, profile.stabilizerMotionPx));
        for (const sampleEvent of events.length ? events : [event]) {
            const point = V.eventWorld(c, sampleEvent);
            const before = stroke.rawPoints.length;
            stroke.rawPoints = F.appendSample(stroke.rawPoints, point, minSampleMm);
            if (stroke.rawPoints.length > before) {
                const stabilized = I.pushStabilized(stroke.stabilizer, point, { motionScaleMm });
                stroke.stablePoints = F.appendSample(
                    stroke.stablePoints,
                    stabilized,
                    Math.max(G.EPSILON_MM, minSampleMm * 0.45)
                );
                stroke.lastStablePoint = stabilized;
            }
            stroke.lastPoint = point;
        }
        return stroke.lastPoint || V.eventWorld(c, event);
    }

    function updateDraft(c, pointer, closeReady = false) {
        const stroke = c.penStroke;
        if (!stroke) return;
        const source = stroke.stablePoints && stroke.stablePoints.length
            ? stroke.stablePoints
            : stroke.rawPoints;
        const previewPoints = source.slice();
        if (
            pointer
            && (!previewPoints.length || G.distance(previewPoints[previewPoints.length - 1], pointer) >= G.EPSILON_MM)
        ) {
            previewPoints.push(pointer);
        }
        c.penDraft = {
            points: previewPoints,
            pointer: pointer || previewPoints[previewPoints.length - 1] || stroke.startPoint,
            closeReady: Boolean(closeReady),
            freehand: true,
            stabilized: false,
            inputKind: stroke.pointerType,
        };
    }

    function moveFreehand(c, event) {
        const stroke = c.penStroke;
        if (!stroke || stroke.pointerId !== event.pointerId) return false;
        const raw = appendEventSamples(c, event);
        const stable = stroke.lastStablePoint || raw;
        const snap = resolveEndpoint(c, raw, c.snapState && c.snapState.target);
        const closeReady = closeCandidate(c, raw);

        const previewPoint = closeReady ? raw : (snap.snapped ? snap.point : stable);
        c.snapState = closeReady
            ? Object.freeze({
                ...snap,
                point: stroke.startPoint,
                snapped: true,
                target: Object.freeze({
                    objectId: "__stroke__",
                    role: "start",
                    point: stroke.startPoint,
                    priority: 1000,
                    kind: "joint",
                }),
                kind: "joint",
            })
            : snap;
        updateDraft(c, previewPoint, closeReady);
        render(c);
        return true;
    }

    function recognitionOptions(c, stroke) {
        const profile = stroke.profile || SmartPen.inputProfile(stroke.pointerType);
        return {
            closed: false,
            simplifyToleranceMm: Math.max(G.EPSILON_MM, pxToMm(c, profile.simplifyTolerancePx)),
            straightToleranceMm: Math.max(G.EPSILON_MM, pxToMm(c, profile.straightTolerancePx)),
            smoothingPasses: profile.smoothingPasses,
            pathSmoothingPasses: profile.pathSmoothingPasses,
            straightRatio: profile.straightRatio,
            circleResidualRatio: profile.circleResidualRatio,
            arcResidualRatio: profile.arcResidualRatio,
            collinearAngleToleranceDeg: profile.collinearAngleToleranceDeg,
            orthogonalAngleToleranceDeg: profile.orthogonalAngleToleranceDeg,
            minimumSegmentMm: Math.max(G.EPSILON_MM, pxToMm(c, profile.minimumMixedSegmentPx)),
            preserveEndpoints: true,
            orthogonalize: true,
            inputKind: stroke.pointerType,
        };
    }

    function propose(c, source, points, options, closeReady) {
        if (!source || source.type !== G.PATH_TYPE || c.readOnly) return false;
        const suggestion = Suggest.analyze(points, { ...options, closeReady: Boolean(closeReady) });
        if (!suggestion) {
            c.smartSuggestion = null;
            return false;
        }
        let candidate = null;
        try { candidate = Suggest.candidateObject(suggestion, source.id, source.style || {}); }
        catch (error) { candidate = null; }
        if (!candidate) return false;
        c.smartSuggestion = Object.freeze({
            sourceId: source.id,
            sourceGeometry: JSON.stringify(source.geometry),
            suggestion,
            candidate,
        });
        render(c);
        return true;
    }

    function freehandPathObject(points) {
        let objects = [];
        try {
            objects = SmartPen.objectsFromRecognition({ type: "path", points, closed: false });
        } catch (error) {
            objects = [];
        }
        return objects.length === 1 && objects[0].type === G.PATH_TYPE ? objects[0] : null;
    }

    function commitRawThenClean(c, points, pointerType) {
        const rawObject = freehandPathObject(points);
        if (!rawObject) return null;

        const rawDocument = D.addObject(c.history.current(), rawObject);
        c.history.execute(rawDocument, "Draw freehand stroke");

        const reconstruction = Reconstructor.reconstruct(points, pointerType);
        let finalObject = rawObject;
        if (reconstruction.changed && reconstruction.points.length >= 2) {
            finalObject = G.path(
                rawObject.id,
                reconstruction.points,
                false,
                rawObject.style || {},
                reconstruction.nodes
            );
            c.history.execute(
                D.replaceObject(c.history.current(), finalObject),
                "Smart reconstruct freehand stroke"
            );
        }

        c.lastSmartClean = Object.freeze({
            sourceId: rawObject.id,
            changed: Boolean(reconstruction.changed),
            cornerCount: reconstruction.cornerCount,
            straightSegmentCount: reconstruction.straightSegmentCount,
            curveSegmentCount: reconstruction.curveSegmentCount,
            spans: reconstruction.spans,
        });
        c.dirty = true;
        return Object.freeze({ rawObject, finalObject, reconstruction });
    }

    function finishFreehand(c, event) {
        const stroke = c.penStroke;
        if (!stroke || stroke.pointerId !== event.pointerId) return false;
        const rawEnd = appendEventSamples(c, event) || stroke.lastPoint || stroke.startPoint;
        const endSnap = resolveEndpoint(c, rawEnd, c.snapState && c.snapState.target);
        const closeReady = closeCandidate(c, rawEnd);
        let points = stroke.rawPoints.slice();
        if (points.length < 2) {
            SmartPen.cancelFreehandGesture(c, event.pointerId);
            return true;
        }

        points[0] = stroke.startPoint;
        points[points.length - 1] = closeReady ? rawEnd : endSnap.point;
        points = F.dedupe(points);
        if (points.length < 2) {
            SmartPen.cancelFreehandGesture(c, event.pointerId);
            return true;
        }

        const options = recognitionOptions(c, stroke);
        const pointerType = stroke.pointerType || "mouse";
        c.penStroke = null;
        c.penDraft = null;
        c.snapState = null;
        try { c.canvas.releasePointerCapture(event.pointerId); } catch (error) { /* optional */ }

        const committed = commitRawThenClean(c, points, pointerType);
        if (!committed) {
            render(c);
            return true;
        }

        c.selectedId = committed.finalObject.id;
        c.nodeEditId = "";
        c.selectedNodeIndex = null;
        c.tool = "pen";
        render(c);

        propose(c, committed.finalObject, points, options, closeReady);
        return true;
    }

    function acceptSuggestion(c) {
        const state = c && c.smartSuggestion;
        if (!state || c.readOnly) return false;
        const source = D.objectById(c.history.current(), state.sourceId);
        if (!source || JSON.stringify(source.geometry) !== state.sourceGeometry) {
            c.smartSuggestion = null;
            render(c);
            return true;
        }
        c.smartSuggestion = null;
        c.selectedId = state.candidate.id;
        c.nodeEditId = "";
        c.selectedNodeIndex = null;
        execute(
            c,
            D.replaceObject(c.history.current(), state.candidate),
            `Accept smart suggestion: ${state.suggestion.type}`
        );
        return true;
    }

    function dismissSuggestion(c) {
        return clearSuggestion(c, true);
    }

    function install(c) {
        if (!c || !c.canvas || c.__nonDestructiveSuggestionInstalled) return c;
        c.__nonDestructiveSuggestionInstalled = true;
        c.smartSuggestion = null;
        c.lastSmartClean = null;

        const onPointerDown = event => {
            if (c.readOnly || c.tool !== "pen" || c.spaceHeld || event.button !== 0) return;
            resetCompetingPenState(c);
            clearSuggestion(c);
        };
        const onPointerMove = event => {
            if (!c.penStroke || c.penStroke.pointerId !== event.pointerId) return;
            if (moveFreehand(c, event)) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        };
        const onPointerUp = event => {
            if (!c.penStroke || c.penStroke.pointerId !== event.pointerId) return;
            if (finishFreehand(c, event)) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        };
        const onRootClick = event => {
            const accept = event.target.closest && event.target.closest("[data-ddv3-suggestion-accept]");
            if (accept && acceptSuggestion(c)) {
                event.preventDefault();
                event.stopImmediatePropagation();
                return;
            }
            const dismiss = event.target.closest && event.target.closest("[data-ddv3-suggestion-dismiss]");
            if (dismiss && dismissSuggestion(c)) {
                event.preventDefault();
                event.stopImmediatePropagation();
                return;
            }
            const tool = event.target.closest && event.target.closest("[data-ddv3-tool]");
            if (tool && tool.dataset.ddv3Tool === "pen") resetCompetingPenState(c);
            else if (tool) clearSuggestion(c);
        };

        window.addEventListener("pointerdown", onPointerDown, true);
        window.addEventListener("pointermove", onPointerMove, true);
        window.addEventListener("pointerup", onPointerUp, true);
        c.root.addEventListener("click", onRootClick, true);

        if (c.dialog && c.dialog.$wrapper) {
            c.dialog.$wrapper.one("hidden.bs.modal.ddv3-smart-suggestion-cleanup", () => {
                window.removeEventListener("pointerdown", onPointerDown, true);
                window.removeEventListener("pointermove", onPointerMove, true);
                window.removeEventListener("pointerup", onPointerUp, true);
                c.root.removeEventListener("click", onRootClick, true);
            });
        }
        render(c);
        return c;
    }

    const originalOpen = Editor.open.bind(Editor);
    const originalView = Editor.view.bind(Editor);
    root.Editor = Object.freeze({
        open(frm, row, options = {}) { return install(originalOpen(frm, row, options)); },
        view(frm, row) { return install(originalView(frm, row)); },
    });
    root.NonDestructiveSmartSuggestions = Object.freeze({
        clearSuggestion,
        resetCompetingPenState,
        closeCandidate,
        moveFreehand,
        finishFreehand,
        freehandPathObject,
        commitRawThenClean,
        propose,
        acceptSuggestion,
        dismissSuggestion,
        install,
    });
})();