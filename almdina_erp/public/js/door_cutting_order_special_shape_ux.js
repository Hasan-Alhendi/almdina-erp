(() => {
    "use strict";

    const STYLE_LINKS = Object.freeze([
        Object.freeze({ id: "almdina-door-drawing-v3-css", href: "/assets/almdina_erp/css/door_drawing_v3.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-precision-css", href: "/assets/almdina_erp/css/door_drawing_v3_precision.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-magnetic-css", href: "/assets/almdina_erp/css/door_drawing_v3_magnetic.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-smart-pen-css", href: "/assets/almdina_erp/css/door_drawing_v3_smart_pen.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-smart-guides-css", href: "/assets/almdina_erp/css/door_drawing_v3_smart_guides.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-advanced-snap-css", href: "/assets/almdina_erp/css/door_drawing_v3_advanced_snap.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-text-css", href: "/assets/almdina_erp/css/door_drawing_v3_text.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-vector-editing-css", href: "/assets/almdina_erp/css/door_drawing_v3_vector_editing.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-bezier-css", href: "/assets/almdina_erp/css/door_drawing_v3_bezier.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-transform-css", href: "/assets/almdina_erp/css/door_drawing_v3_transform.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-professional-move-css", href: "/assets/almdina_erp/css/door_drawing_v3_professional_move.css" }),
        Object.freeze({ id: "almdina-door-drawing-v3-oriented-transform-css", href: "/assets/almdina_erp/css/door_drawing_v3_oriented_transform.css" }),
    ]);
    const SCRIPTS = Object.freeze([
        "/assets/almdina_erp/js/door_drawing_v3/domain/geometry.js",
        "/assets/almdina_erp/js/door_drawing_v3/domain/document.js",
        "/assets/almdina_erp/js/door_drawing_v3/domain/smart_path_domain.js",
        "/assets/almdina_erp/js/door_drawing_v3/domain/bezier_path_domain.js",
        "/assets/almdina_erp/js/door_drawing_v3/domain/vector_selection.js",
        "/assets/almdina_erp/js/door_drawing_v3/domain/bezier_selection_domain.js",
        "/assets/almdina_erp/js/door_drawing_v3/domain/text_annotation_domain.js",
        "/assets/almdina_erp/js/door_drawing_v3/domain/transform_domain.js",
        "/assets/almdina_erp/js/door_drawing_v3/domain/oriented_transform_domain.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/history.js",
        "/assets/almdina_erp/js/door_drawing_v3/infrastructure/persistence_adapter.js",
        "/assets/almdina_erp/js/door_drawing_v3/infrastructure/smart_path_persistence.js",
        "/assets/almdina_erp/js/door_drawing_v3/infrastructure/bezier_path_persistence.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/snapping.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/smart_path_snapping.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/move_snap_policy.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/smart_guides.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/unified_snap_engine.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/snap_candidate_engine.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/professional_move_policy.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/snap_axis_policy.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/advanced_snap_engine.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/shape_handles.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/precision_input.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/smart_freehand_policy.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/smart_stroke_intelligence.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/smart_stroke_corner_guard.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/tool_modifier_policy.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/canvas_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/canvas_policy.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/smart_path_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/bezier_path_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/smart_guides_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/advanced_snap_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/text_annotation_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/vector_editing_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/transform_box_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/professional_move_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/presentation/oriented_transform_view.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/editor_stage2.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/text_annotation_editor.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/magnetic_connection.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/tool_modifiers.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/smart_pen.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/bezier_path_editing.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/vector_editing.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/node_selection_policy.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/editor_shortcuts.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/transform_box.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/professional_move.js",
        "/assets/almdina_erp/js/door_drawing_v3/application/oriented_transform.js",
    ]);

    function ensureStyles() {
        STYLE_LINKS.forEach(item => {
            if (document.getElementById(item.id)) return;
            const link = document.createElement("link");
            link.id = item.id;
            link.rel = "stylesheet";
            link.href = item.href;
            document.head.appendChild(link);
        });
    }
    function loaded(src) { return Boolean(document.querySelector(`script[data-door-drawing-v3="${src}"]`)); }
    function loadScript(src) { return new Promise((resolve, reject) => { if (loaded(src)) return resolve(); const script = document.createElement("script"); script.src = src; script.async = false; script.dataset.doorDrawingV3 = src; script.onload = resolve; script.onerror = () => reject(new Error(`Failed to load Door Drawing V3 module: ${src}`)); document.head.appendChild(script); }); }
    function boot() {
        ensureStyles();
        if (window.__almdinaDoorDrawingV3BootPromise) return window.__almdinaDoorDrawingV3BootPromise;
        window.__almdinaDoorDrawingV3BootPromise = SCRIPTS.reduce((promise, src) => promise.then(() => loadScript(src)), Promise.resolve()).catch(error => { window.__almdinaDoorDrawingV3BootPromise = null; console.error("Door Drawing V3 bootstrap failed", error); throw error; });
        return window.__almdinaDoorDrawingV3BootPromise;
    }
    function editor() { const instance = window.AlmdinaDoorDrawingV3 && window.AlmdinaDoorDrawingV3.Editor; if (!instance) throw new Error("Door Drawing V3 editor is not ready"); return instance; }
    function open(frm, row, options = {}) { return boot().then(() => editor().open(frm, row, options)).catch(error => { console.error(error); if (window.frappe) frappe.msgprint("تعذر تحميل محرر رسم الدرفة الجديد. أعد تحميل الصفحة ثم حاول مرة أخرى."); return null; }); }
    function view(frm, row) { return open(frm, row, { readOnly: true }); }
    function parseDrawing(raw) { try { const parsed = typeof raw === "string" ? JSON.parse(raw) : raw; const document = parsed && parsed.meta && parsed.meta.door_drawing_v3; return document && Array.isArray(document.objects) ? document.objects : []; } catch (error) { return []; } }

    const facade = {
        open, view, parseDrawing,
        __doorDrawingV3: true,
        __doorDrawingV3Shapes: true,
        __doorDrawingV3Snapping: true,
        __doorDrawingV3Handles: true,
        __doorDrawingV3PrecisionInput: true,
        __doorDrawingV3MagneticConnection: true,
        __doorDrawingV3EasyMoveSnap: true,
        __doorDrawingV3SmartGuides: true,
        __doorDrawingV3UnifiedSnapEngine: true,
        __doorDrawingV3SnapCandidateEngine: true,
        __doorDrawingV3DuplicateSnapTargets: true,
        __doorDrawingV3GeometryPointSnap: true,
        __doorDrawingV3EndpointSurfaceSnap: true,
        __doorDrawingV3CollinearContinuation: true,
        __doorDrawingV3RepeatedSpacingGuides: true,
        __doorDrawingV3OperatorAssistLabels: true,
        __doorDrawingV3ExactLinearSnapSafety: true,
        __doorDrawingV3StickyMoveSnap: true,
        __doorDrawingV3AxisSafeSnap: true,
        __doorDrawingV3IntersectionSnap: true,
        __doorDrawingV3PerpendicularSnap: true,
        __doorDrawingV3ParallelSnap: true,
        __doorDrawingV3MultiIntentSnap: true,
        __doorDrawingV3MoveSurfaceSnap: true,
        __doorDrawingV3MidpointSnap: true,
        __doorDrawingV3MoveAlignmentSnap: true,
        __doorDrawingV3SurfaceSnap: true,
        __doorDrawingV3EqualLengthSnap: true,
        __doorDrawingV3TextAnnotations: true,
        __doorDrawingV3InlineTextEditing: true,
        __doorDrawingV3CanvasPolicy: true,
        __doorDrawingV3SmartPen: true,
        __doorDrawingV3SmartFreehand: true,
        __doorDrawingV3LiveStabilizer: true,
        __doorDrawingV3MixedStrokeRecognition: true,
        __doorDrawingV3SharpCornerRecognition: true,
        __doorDrawingV3PersistentTools: true,
        __doorDrawingV3ModifierConstraints: true,
        __doorDrawingV3TemporarySelect: true,
        __doorDrawingV3SmartPath: true,
        __doorDrawingV3NodeEditing: true,
        __doorDrawingV3MultiSelect: true,
        __doorDrawingV3AlignmentDistribution: true,
        __doorDrawingV3MultiNodeEditing: true,
        __doorDrawingV3MultiSegmentEditing: true,
        __doorDrawingV3VectorPathPen: true,
        __doorDrawingV3BezierPaths: true,
        __doorDrawingV3BezierPen: true,
        __doorDrawingV3AdvancedNodeEditing: true,
        __doorDrawingV3BezierPersistence: true,
        __doorDrawingV3SelectionNodeDrag: true,
        __doorDrawingV3ProfessionalShortcuts: true,
        __doorDrawingV3MultiClipboard: true,
        __doorDrawingV3TransformBox: true,
        __doorDrawingV3TransformResize: true,
        __doorDrawingV3TransformFlip: true,
        __doorDrawingV3TransformInspector: true,
        __doorDrawingV3AltDragDuplicate: true,
        __doorDrawingV3ShiftAxisMove: true,
        __doorDrawingV3EqualSpacingGuides: true,
        __doorDrawingV3OrientedTransform: true,
        __doorDrawingV3RotationHandle: true,
        __doorDrawingV3RotationSnap: true,
        __doorDrawingV3TransformPivot: true,
        __referenceImageIntegrated: true,
        __smartTemplatePaletteIntegrated: true,
        __templateSilhouettePreviewIntegrated: true,
        __smartTemplateEdgesIntegrated: true,
        __smartEdgeFeaturesIntegrated: true,
        __exactLineIntegrated: true,
        __exactLineInspectorIntegrated: true,
        __exactArcIntegrated: true,
        __exactSegmentDimensionsIntegrated: true,
        __exactShapeChainIntegrated: true,
        __drawingWorkspaceIntegrated: true,
        __figmaEditorIntegrated: true,
        __figmaGenericHandlesIntegrated: true,
        __doorDrawingV2ShellIntegrated: true,
        __doorDrawingV2SelectionIntegrated: true,
        __doorDrawingV2LineUXIntegrated: true,
        __doorDrawingV2FigmaExactIntegrated: true,
    };
    window.AlmdinaSpecialShapeEditor = Object.freeze(facade);
    window.AlmdinaDoorDrawingV3Bootstrap = Object.freeze({ STYLE_LINKS, SCRIPTS, boot });
    window.AlmdinaDoorDrawingV2Bootstrap = Object.freeze({ SCRIPTS: Object.freeze([]), boot: () => Promise.resolve() });
})();
