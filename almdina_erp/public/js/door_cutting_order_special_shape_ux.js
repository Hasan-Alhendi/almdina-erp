(() => {
    "use strict";

    const sketchEngine = window.AlmdinaSketchEngine;
    const sketchRenderer = window.AlmdinaSketchRenderer;
    const inlineNoteEditor = window.AlmdinaInlineNoteEditor;
    if (!sketchEngine || !sketchRenderer || !inlineNoteEditor) {
        console.error(
            "Sketch engine, renderer, and inline note editor must load before the special-shape editor"
        );
        return;
    }
    const CANVAS_WIDTH = sketchEngine.DEFAULT_CANVAS.width;
    const CANVAS_HEIGHT = sketchEngine.DEFAULT_CANVAS.height;
    const DEFAULT_ERASER_RADIUS = sketchEngine.DEFAULT_ERASER_RADIUS;
    const MIN_ERASER_RADIUS = sketchEngine.MIN_ERASER_RADIUS;
    const MAX_ERASER_RADIUS = sketchEngine.MAX_ERASER_RADIUS;
    const MIN_ZOOM = 1;
    const MAX_ZOOM = 4;
    const ZOOM_STEP = 1.25;
    const ENDPOINT_SNAP_RADIUS = sketchEngine.DEFAULT_SNAP_RADIUS;
    const DEFAULT_NOTE_FONT_SIZE = inlineNoteEditor.DEFAULT_FONT_SIZE;
    const COLORS = ["#172033", "#c2352a", "#1769aa"];
    const TOOLS = [
        { key: "pen", group: "draw", icon: "✎", label: "قلم ذكي", hint: "ينعّم ويغلق الزوايا" },
        { key: "line", group: "draw", icon: "╱", label: "خط مستقيم", hint: "محاذاة تلقائية" },
        { key: "rectangle", group: "draw", icon: "□", label: "مستطيل", hint: "اسحب من زاوية لأخرى" },
        { key: "ellipse", group: "draw", icon: "○", label: "دائرة", hint: "دائرة أو بيضاوي" },
        { key: "dimension", group: "explain", icon: "↔", label: "إضافة قياس", hint: "سهم مع القيمة الحقيقية" },
        { key: "note", group: "explain", icon: "T", label: "إضافة ملاحظة", hint: "تعليمات للمصمم" },
        { key: "select", group: "edit", icon: "↖", label: "تحديد وتحريك", hint: "اختر عنصرًا لتعديله" },
        { key: "eraser", group: "edit", icon: "⌫", label: "ممحاة دقيقة", hint: "تمسح جزءًا من القلم" },
    ];
    const TOOL_GROUPS = [
        { key: "draw", title: "1. ارسم حدود الدرفة" },
        { key: "explain", title: "2. أضف المعلومات" },
        { key: "edit", title: "3. راجع وصحح" },
    ];
    let sequence = 0;

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    const clampNoteFontSize = inlineNoteEditor.clampFontSize;
    const pointDistance = sketchEngine.pointDistance;
    const sanitizePoints = sketchEngine.sanitizePoints;
    const normalizePenStroke = sketchEngine.normalizePenStroke;
    const erasePenStroke = sketchEngine.erasePenStroke;
    const nearestAnchor = sketchEngine.nearestAnchor;
    const snapLineEnd = sketchEngine.snapLineEnd;
    const polylineLength = sketchEngine.polylineLength;
    const snapPenEndpoints = sketchEngine.snapPenEndpoints;
    const templatePoints = sketchEngine.templatePoints;
    const translateElement = (element, dx, dy) => sketchEngine.translateElement(
        element,
        dx,
        dy,
        { width: CANVAS_WIDTH, height: CANVAS_HEIGHT }
    );
    const elementBounds = element => sketchEngine.elementBounds(
        element,
        { noteFontSize: clampNoteFontSize }
    );
    const clampViewBox = viewBox => sketchEngine.clampViewBox(
        viewBox,
        { width: CANVAS_WIDTH, height: CANVAS_HEIGHT, maxZoom: MAX_ZOOM }
    );

    function parseDrawing(raw) {
        if (!raw) return [];
        try {
            const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
            return parsed && parsed.version === 1 && Array.isArray(parsed.elements)
                ? clone(parsed.elements)
                : [];
        } catch (error) {
            console.warn("Invalid special shape drawing JSON", error);
            return [];
        }
    }

    function id(prefix) {
        sequence += 1;
        return `${prefix}-${Date.now()}-${sequence}`;
    }

    function installStyles() {
        inlineNoteEditor.installStyles();
        if (document.getElementById("dco-special-shape-ux-css")) return;
        const style = document.createElement("style");
        style.id = "dco-special-shape-ux-css";
        style.textContent = `
            .dco-special-shape-modal .modal-dialog{max-width:min(1480px,96vw)!important;width:96vw!important}
            .dco-special-shape-modal .modal-content{border:0;border-radius:18px;overflow:hidden;box-shadow:0 28px 90px rgba(20,28,38,.24)}
            .dco-special-shape-modal .modal-header{padding:15px 20px;border-bottom:1px solid var(--border-color,#e1e6eb)}
            .dco-special-shape-modal .modal-body{padding:0!important;background:var(--subtle-fg,#f5f7f9)}
            .dco-special-shape-modal .modal-footer{padding:12px 18px;background:var(--card-bg,#fff)}
            .dco-special-shape-modal.dco-sketch-fullscreen .modal-dialog{max-width:100vw!important;width:100vw!important;height:100vh!important;margin:0!important}
            .dco-special-shape-modal.dco-sketch-fullscreen .modal-content{height:100vh;border-radius:0}
            .dco-special-sketch-shell{direction:rtl;display:grid;grid-template-columns:188px minmax(0,1fr) 238px;min-height:690px;color:var(--text-color,#172033)}
            .dco-sketch-toolbar{padding:12px 10px;background:var(--card-bg,#fff);border-left:1px solid var(--border-color,#e1e6eb);display:flex;flex-direction:column;gap:6px;overflow:auto}
            .dco-sketch-toolbar-title{display:flex;align-items:center;gap:6px;font-size:10px;color:var(--text-muted,#6c7680);font-weight:900;margin:7px 4px 3px}
            .dco-sketch-toolbar-title:first-child{margin-top:1px}
            .dco-sketch-toolbar-title::before{content:"";width:5px;height:5px;border-radius:50%;background:var(--primary,#2490ef)}
            .dco-sketch-tool{display:flex;align-items:center;gap:9px;width:100%;min-height:40px;border:1px solid transparent;border-radius:10px;background:transparent;color:inherit;padding:6px 8px;cursor:pointer;text-align:right;transition:.12s ease}
            .dco-sketch-tool:hover{background:var(--subtle-fg,#f6f8fa);border-color:var(--border-color,#e1e6eb)}
            .dco-sketch-tool.is-active{background:rgba(36,144,239,.11);border-color:rgba(36,144,239,.34);color:var(--primary,#1674c5);font-weight:900}
            .dco-sketch-tool-icon{display:grid;place-items:center;width:26px;height:26px;border-radius:8px;background:var(--subtle-fg,#f0f3f5);font-size:16px;font-weight:900;flex:0 0 auto}
            .dco-sketch-tool small{display:block;font-size:9px;font-weight:400;opacity:.64;margin-top:1px}
            .dco-sketch-template-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px}
            .dco-sketch-template{min-height:38px;border:1px solid var(--border-color,#dce2e7);border-radius:9px;background:var(--card-bg,#fff);cursor:pointer;font-size:9px;font-weight:800;padding:4px}
            .dco-sketch-template:hover{border-color:var(--primary,#2490ef);color:var(--primary,#1674c5);background:rgba(36,144,239,.05)}
            .dco-sketch-template b{display:block;font-size:17px;line-height:15px;margin-bottom:3px}
            .dco-sketch-divider{height:1px;background:var(--border-color,#e4e7ea);margin:5px 0}
            .dco-sketch-history{display:grid;grid-template-columns:1fr 1fr;gap:6px}
            .dco-sketch-icon-button{min-height:38px;border:1px solid var(--border-color,#d8dde2);border-radius:9px;background:var(--card-bg,#fff);cursor:pointer;font-weight:800}
            .dco-sketch-icon-button:hover:not(:disabled){border-color:var(--primary,#2490ef);color:var(--primary,#1674c5)}
            .dco-sketch-icon-button:disabled{opacity:.38;cursor:not-allowed}
            .dco-sketch-colors{display:flex;gap:9px;padding:3px 5px}
            .dco-sketch-color{width:27px;height:27px;border:3px solid var(--card-bg,#fff);border-radius:999px;box-shadow:0 0 0 1px var(--border-color,#cfd6dc);cursor:pointer}
            .dco-sketch-color.is-active{box-shadow:0 0 0 3px rgba(36,144,239,.27)}
            .dco-sketch-eraser-controls{display:none;padding:9px 8px;border:1px solid var(--border-color,#e1e6eb);border-radius:10px;background:var(--subtle-fg,#f7f9fa)}
            .dco-sketch-eraser-controls.is-visible{display:block}
            .dco-sketch-eraser-label{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px;font-size:10px;font-weight:800}
            .dco-sketch-eraser-label b{color:var(--primary,#1674c5)}
            .dco-sketch-eraser-size{width:100%;height:5px;accent-color:var(--primary,#1674c5);cursor:pointer}
            .dco-sketch-eraser-scale{display:flex;justify-content:space-between;color:var(--text-muted,#71808e);font-size:8px;margin-top:3px}
            .dco-sketch-selection-controls{display:none;padding:8px;border:1px solid rgba(36,144,239,.28);border-radius:10px;background:rgba(36,144,239,.06)}
            .dco-sketch-selection-controls.is-visible{display:grid;grid-template-columns:1fr 1fr;gap:5px}
            .dco-sketch-selection-controls small{grid-column:1/-1;color:var(--text-muted,#65727e);font-size:9px}
            .dco-sketch-selection-action{min-height:32px;border:1px solid var(--border-color,#d9dfe5);border-radius:8px;background:#fff;cursor:pointer;font-size:10px;font-weight:900}
            .dco-sketch-selection-action.is-danger{color:#b42318;border-color:#efc2bd}
            .dco-sketch-center{min-width:0;padding:14px;display:flex;flex-direction:column;gap:10px}
            .dco-sketch-topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:10px 12px;border:1px solid var(--border-color,#e0e5e9);border-radius:12px;background:var(--card-bg,#fff)}
            .dco-sketch-piece-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
            .dco-sketch-meta-pill{display:inline-flex;align-items:center;gap:5px;padding:5px 9px;border-radius:999px;background:var(--subtle-fg,#f2f5f7);font-size:11px}
            .dco-sketch-meta-pill b{font-variant-numeric:tabular-nums}
            .dco-sketch-save-state{color:#49616f}
            .dco-sketch-save-state.is-dirty{background:#fff3d6;color:#8a5a12}
            .dco-sketch-notice{display:flex;align-items:center;gap:7px;color:#8a5a12;background:#fff7df;border:1px solid #efd89a;border-radius:9px;padding:6px 10px;font-size:10px;font-weight:700}
            .dco-sketch-paper-wrap{position:relative;flex:1;display:grid;place-items:center;min-height:570px;padding:13px;border:1px solid var(--border-color,#d9dfe5);border-radius:15px;background:#e8ecef;overflow:hidden}
            .dco-sketch-paper{display:block;width:100%;height:auto;min-height:0;max-height:calc(100vh - 250px);aspect-ratio:${CANVAS_WIDTH}/${CANVAS_HEIGHT};background:#fff;border-radius:5px;box-shadow:0 9px 28px rgba(28,38,50,.14);touch-action:none;cursor:none;user-select:none}
            .dco-sketch-paper[data-tool="note"]{cursor:text}
            .dco-sketch-paper[data-tool="select"]{cursor:default}
            .dco-sketch-paper.is-pan-ready{cursor:grab!important}
            .dco-sketch-paper.is-panning{cursor:grabbing!important}
            .dco-sketch-element{pointer-events:all}
            .dco-sketch-cursor-preview{pointer-events:none}
            .dco-sketch-selection-box{pointer-events:none;fill:rgba(36,144,239,.06);stroke:#2490ef;stroke-width:2;stroke-dasharray:8 6;vector-effect:non-scaling-stroke}
            .dco-sketch-selection-handle{pointer-events:none;fill:#fff;stroke:#2490ef;stroke-width:2;vector-effect:non-scaling-stroke}
            .dco-sketch-snap-point{pointer-events:none;fill:rgba(21,142,91,.14);stroke:#158e5b;stroke-width:2;vector-effect:non-scaling-stroke}
            .dco-sketch-zoom{position:absolute;direction:ltr;left:24px;bottom:24px;display:flex;align-items:center;gap:4px;padding:5px;border:1px solid rgba(30,42,56,.16);border-radius:11px;background:rgba(255,255,255,.94);box-shadow:0 5px 18px rgba(24,34,45,.12)}
            .dco-sketch-zoom button{width:34px;height:32px;border:0;border-radius:7px;background:transparent;cursor:pointer;font-size:17px;font-weight:900}
            .dco-sketch-zoom button:hover:not(:disabled){background:#edf4fb;color:#1674c5}
            .dco-sketch-zoom button:disabled{opacity:.35;cursor:not-allowed}
            .dco-sketch-zoom-value{min-width:48px;text-align:center;font-size:10px;font-weight:900;font-variant-numeric:tabular-nums}
            .dco-sketch-key-hint{position:absolute;direction:rtl;right:24px;bottom:24px;padding:6px 9px;border-radius:9px;background:rgba(23,32,51,.76);color:#fff;font-size:9px;pointer-events:none}
            .dco-sketch-sidebar{padding:14px 13px;background:var(--card-bg,#fff);border-right:1px solid var(--border-color,#e1e6eb);display:flex;flex-direction:column;gap:11px}
            .dco-sketch-side-card{border:1px solid var(--border-color,#e0e5e9);border-radius:12px;overflow:hidden}
            .dco-sketch-side-title{padding:9px 11px;background:var(--subtle-fg,#f7f9fa);font-size:11px;font-weight:900;border-bottom:1px solid var(--border-color,#e5e8eb)}
            .dco-sketch-side-content{padding:10px;max-height:250px;overflow:auto}
            .dco-sketch-empty{padding:12px 5px;text-align:center;color:var(--text-muted,#71808e);font-size:10px;line-height:1.7}
            .dco-sketch-list-item{display:flex;align-items:flex-start;gap:7px;padding:7px 3px;border-bottom:1px solid var(--border-color,#edf0f2);font-size:10px;line-height:1.5}
            button.dco-sketch-list-item{width:100%;text-align:right;background:transparent;border-width:0 0 1px;cursor:pointer;color:inherit}
            button.dco-sketch-list-item:hover{background:var(--subtle-fg,#f7f9fa)}
            .dco-sketch-list-item:last-child{border-bottom:0}
            .dco-sketch-list-badge{display:grid;place-items:center;min-width:22px;height:22px;border-radius:7px;background:rgba(36,144,239,.1);color:var(--primary,#1674c5);font-weight:900}
            .dco-sketch-progress{display:flex;flex-direction:column;gap:7px}
            .dco-sketch-progress-item{display:flex;align-items:center;gap:8px;padding:7px 8px;border-radius:9px;background:var(--subtle-fg,#f6f8fa);font-size:10px;font-weight:800}
            .dco-sketch-progress-dot{display:grid;place-items:center;width:21px;height:21px;border-radius:50%;background:#dce3e8;color:#64717d;font-size:10px}
            .dco-sketch-progress-item.is-done{background:#eaf8f1;color:#12633f}
            .dco-sketch-progress-item.is-done .dco-sketch-progress-dot{background:#158e5b;color:#fff}
            .dco-sketch-guide{font-size:10px;line-height:1.75;color:var(--text-muted,#64717d);padding:2px 3px}
            .dco-sketch-guide b{color:var(--text-color,#172033)}
            .dco-sketch-fullscreen-button{border:1px solid var(--border-color,#d8dde2);border-radius:8px;background:var(--card-bg,#fff);min-height:34px;padding:5px 10px;cursor:pointer;font-size:11px;font-weight:800}
            @media(max-width:1050px){.dco-special-sketch-shell{grid-template-columns:145px minmax(0,1fr)}.dco-sketch-sidebar{display:none}}
            @media(max-width:700px){.dco-special-shape-modal .modal-dialog{width:100vw!important;margin:0!important}.dco-special-shape-modal .modal-content{min-height:100vh;border-radius:0}.dco-special-sketch-shell{display:flex;flex-direction:column;min-height:0}.dco-sketch-toolbar{order:2;flex-direction:row;overflow:auto;border:0;border-top:1px solid var(--border-color,#ddd);padding:8px}.dco-sketch-toolbar-title,.dco-sketch-divider,.dco-sketch-colors,.dco-sketch-template-grid{display:none}.dco-sketch-tool{min-width:82px;flex-direction:column;justify-content:center;text-align:center}.dco-sketch-tool small{display:none}.dco-sketch-eraser-controls,.dco-sketch-selection-controls{min-width:145px}.dco-sketch-history{display:flex}.dco-sketch-icon-button{min-width:56px}.dco-sketch-center{padding:8px}.dco-sketch-paper-wrap{min-height:430px}.dco-sketch-key-hint{display:none}}
        `;
        document.head.appendChild(style);
    }

    function shellHtml(row) {
        return `
            <div class="dco-special-sketch-shell">
                <aside class="dco-sketch-toolbar" aria-label="أدوات الرسم">
                    ${TOOL_GROUPS.map(group => `
                        <div class="dco-sketch-toolbar-title">${group.title}</div>
                        ${TOOLS.filter(tool => tool.group === group.key).map(tool => `
                            <button type="button" class="dco-sketch-tool ${tool.key === "pen" ? "is-active" : ""}" data-tool="${tool.key}" aria-pressed="${tool.key === "pen" ? "true" : "false"}">
                                <span class="dco-sketch-tool-icon" aria-hidden="true">${tool.icon}</span>
                                <span>${tool.label}<small>${tool.hint}</small></span>
                            </button>`).join("")}
                        ${group.key === "draw" ? `
                            <div class="dco-sketch-template-grid" aria-label="أشكال جاهزة">
                                <button type="button" class="dco-sketch-template" data-template="single-slope"><b>◩</b>طرف مائل</button>
                                <button type="button" class="dco-sketch-template" data-template="double-clipped"><b>⬡</b>قصتان علويتان</button>
                                <button type="button" class="dco-sketch-template" data-template="clipped-corner"><b>⌑</b>زاوية مقصوصة</button>
                                <button type="button" class="dco-sketch-template" data-template="arch"><b>⌒</b>قوس علوي</button>
                                <button type="button" class="dco-sketch-template" data-template="lshape"><b>⌞</b>شكل L</button>
                                <button type="button" class="dco-sketch-template" data-template="trapezoid"><b>⬠</b>شبه منحرف</button>
                            </div>` : ""}
                    `).join("")}
                    <div class="dco-sketch-divider"></div>
                    <div class="dco-sketch-toolbar-title">لون القلم</div>
                    <div class="dco-sketch-colors">
                        ${COLORS.map((color, index) => `<button type="button" class="dco-sketch-color ${index === 0 ? "is-active" : ""}" data-color="${color}" style="background:${color}" title="اختيار اللون"></button>`).join("")}
                    </div>
                    ${inlineNoteEditor.controlsHtml()}
                    <div class="dco-sketch-eraser-controls" aria-hidden="true">
                        <div class="dco-sketch-eraser-label">
                            <span>حجم الممحاة</span>
                            <b class="dco-sketch-eraser-value">صغيرة</b>
                        </div>
                        <input class="dco-sketch-eraser-size" type="range" min="${MIN_ERASER_RADIUS}" max="${MAX_ERASER_RADIUS}" step="2" value="${DEFAULT_ERASER_RADIUS}" aria-label="حجم الممحاة">
                        <div class="dco-sketch-eraser-scale"><span>دقيقة</span><span>كبيرة</span></div>
                    </div>
                    <div class="dco-sketch-selection-controls" aria-hidden="true">
                        <small>اسحب العنصر المحدد لتحريكه</small>
                        <button type="button" class="dco-sketch-selection-action dco-sketch-edit-selected">تعديل النص</button>
                        <button type="button" class="dco-sketch-selection-action is-danger dco-sketch-delete-selected">حذف العنصر</button>
                    </div>
                    <div class="dco-sketch-history">
                        <button type="button" class="dco-sketch-icon-button dco-sketch-undo" title="تراجع (Ctrl+Z)">↶ تراجع</button>
                        <button type="button" class="dco-sketch-icon-button dco-sketch-redo" title="إعادة (Ctrl+Y)">↷ إعادة</button>
                    </div>
                    <button type="button" class="dco-sketch-icon-button dco-sketch-clear">مسح الورقة</button>
                </aside>
                <main class="dco-sketch-center">
                    <div class="dco-sketch-topbar">
                        <div class="dco-sketch-piece-meta">
                            <span class="dco-sketch-meta-pill">الدرفة <b>#${esc(row.idx || row.piece_no || "—")}</b></span>
                            <span class="dco-sketch-meta-pill">الخام <b dir="ltr">${esc(row.width_cm || 0)} × ${esc(row.length_cm || 0)} سم</b></span>
                            <span class="dco-sketch-meta-pill">العدد <b>${esc(row.qty || 1)}</b></span>
                            <span class="dco-sketch-meta-pill dco-sketch-save-state">✓ الرسم محفوظ</span>
                        </div>
                        <div style="display:flex;align-items:center;gap:8px">
                            <div class="dco-sketch-notice"><span>✓</span><span class="dco-sketch-notice-text">المؤشر يحدد نقطة الرسم بدقة، والتنعيم يعمل تلقائيًا</span></div>
                            <button type="button" class="dco-sketch-fullscreen-button">⛶ ملء الشاشة</button>
                        </div>
                    </div>
                    <div class="dco-sketch-paper-wrap">
                        <svg class="dco-sketch-paper" data-tool="pen" width="${CANVAS_WIDTH}" height="${CANVAS_HEIGHT}" viewBox="0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="ورقة رسم الدرفة الخاصة"></svg>
                        <div class="dco-sketch-zoom" aria-label="تكبير الرسم">
                            <button type="button" class="dco-sketch-zoom-out" title="تصغير">−</button>
                            <span class="dco-sketch-zoom-value">100%</span>
                            <button type="button" class="dco-sketch-zoom-in" title="تكبير">+</button>
                            <button type="button" class="dco-sketch-zoom-reset" title="إظهار الورقة كاملة">⌂</button>
                        </div>
                        <div class="dco-sketch-key-hint">Ctrl + عجلة: تكبير · Space + سحب: تحريك · Esc: إلغاء التحديد</div>
                    </div>
                </main>
                <aside class="dco-sketch-sidebar">
                    <div class="dco-sketch-side-card">
                        <div class="dco-sketch-side-title">اكتمال التوثيق</div>
                        <div class="dco-sketch-side-content dco-sketch-progress"></div>
                    </div>
                    <div class="dco-sketch-side-card">
                        <div class="dco-sketch-side-title">القياسات المكتوبة</div>
                        <div class="dco-sketch-side-content dco-sketch-dimensions"></div>
                    </div>
                    <div class="dco-sketch-side-card">
                        <div class="dco-sketch-side-title">الملاحظات على الرسم</div>
                        <div class="dco-sketch-side-content dco-sketch-notes"></div>
                    </div>
                    <div class="dco-sketch-guide">
                        <b>الأسهل:</b> اختر شكلًا جاهزًا ثم عدّله بأداة «تحديد وتحريك».<br><br>
                        قلمك يُنعّم أثناء الحركة، وتلتقط نهايات الخطوط بعضها تلقائيًا لإغلاق الشكل.<br><br>
                        انقر مرتين على القياس أو الملاحظة لتعديل النص. القياسات المكتوبة هي المرجع وليست نسبة الرسم.
                    </div>
                </aside>
            </div>`;
    }

    function renderCanvas(state) {
        const view = sketchRenderer.canvasView(state, {
            width: CANVAS_WIDTH,
            height: CANVAS_HEIGHT,
            noteFontSize: clampNoteFontSize,
        });
        state.svg.setAttribute("viewBox", view.viewBox);
        state.svg.innerHTML = view.markup;
        renderSidebar(state);
        state.root.querySelector(".dco-sketch-undo").disabled = state.undo.length === 0;
        state.root.querySelector(".dco-sketch-redo").disabled = state.redo.length === 0;
        const saveState = state.root.querySelector(".dco-sketch-save-state");
        if (saveState) {
            saveState.classList.toggle("is-dirty", Boolean(state.hasChanges));
            saveState.textContent = state.hasChanges ? "● تعديلات غير محفوظة" : "✓ لا تغييرات غير محفوظة";
        }
        updateSelectionControls(state);
        updateNoteFontControls(state);
        updateZoomControls(state);
        updateCursorPreview(state);
    }

    function renderSidebar(state) {
        const view = sketchRenderer.sidebarView(state.elements);
        state.root.querySelector(".dco-sketch-dimensions").innerHTML = view.dimensions;
        state.root.querySelector(".dco-sketch-notes").innerHTML = view.notes;
        state.root.querySelector(".dco-sketch-progress").innerHTML = view.progress;
    }

    function clientPointToCanvas(svg, clientX, clientY) {
        try {
            const matrix = svg.getScreenCTM && svg.getScreenCTM();
            if (matrix && svg.createSVGPoint) {
                const point = svg.createSVGPoint();
                point.x = Number(clientX);
                point.y = Number(clientY);
                const transformed = point.matrixTransform(matrix.inverse());
                return {
                    x: Math.max(0, Math.min(CANVAS_WIDTH, transformed.x)),
                    y: Math.max(0, Math.min(CANVAS_HEIGHT, transformed.y)),
                };
            }
        } catch (error) {
            // Some older browsers can briefly expose a non-invertible matrix while resizing.
        }
        const rect = svg.getBoundingClientRect();
        return {
            x: Math.max(0, Math.min(CANVAS_WIDTH, (Number(clientX) - rect.left) * CANVAS_WIDTH / rect.width)),
            y: Math.max(0, Math.min(CANVAS_HEIGHT, (Number(clientY) - rect.top) * CANVAS_HEIGHT / rect.height)),
        };
    }

    function pointFromEvent(svg, event) {
        return clientPointToCanvas(svg, event.clientX, event.clientY);
    }

    function updateCursorPreview(state, point = state.hoverPoint, visible = state.pointerInside) {
        const preview = state.svg.querySelector(".dco-sketch-cursor-preview");
        if (!preview) return;
        if (
            !visible
            || !point
            || state.readOnly
            || state.spaceHeld
            || state.panning
            || ["note", "select"].includes(state.tool)
        ) {
            preview.setAttribute("display", "none");
            return;
        }
        const erasing = state.tool === "eraser";
        const ring = preview.querySelector(".dco-sketch-cursor-ring");
        const cross = preview.querySelector(".dco-sketch-cursor-cross");
        const color = erasing ? "#d64545" : state.color;
        preview.setAttribute("display", "");
        preview.setAttribute("transform", `translate(${point.x} ${point.y})`);
        ring.setAttribute("r", erasing ? state.eraserRadius : 4);
        ring.setAttribute("stroke", color);
        ring.setAttribute("fill", erasing ? "rgba(214,69,69,.10)" : "#fff");
        cross.setAttribute("stroke", color);
        cross.setAttribute("display", erasing ? "none" : "");
    }

    function updateSelectionControls(state) {
        const controls = state.root.querySelector(".dco-sketch-selection-controls");
        if (!controls) return;
        const selected = state.elements.find(element => element.id === state.selectedId);
        const visible = Boolean(selected) && state.tool === "select";
        controls.classList.toggle("is-visible", visible);
        controls.setAttribute("aria-hidden", visible ? "false" : "true");
        const edit = controls.querySelector(".dco-sketch-edit-selected");
        edit.disabled = !selected || !["dimension", "note"].includes(selected.type);
        edit.title = edit.disabled
            ? "تعديل النص متاح للقياس والملاحظة"
            : "تعديل نص العنصر المحدد";
    }

    function updateNoteFontControls(state) {
        const controls = state.root.querySelector(".dco-note-font-controls");
        if (!controls) return;
        const selected = state.elements.find(element =>
            element.id === state.selectedId && element.type === "note"
        );
        if (selected) {
            state.noteFontSize = clampNoteFontSize(selected.font_size || selected.fontSize);
        }
        const visible = !state.readOnly && (state.tool === "note" || Boolean(selected));
        controls.classList.toggle("is-visible", visible);
        controls.setAttribute("aria-hidden", visible ? "false" : "true");
        const select = controls.querySelector(".dco-note-font-size");
        const value = controls.querySelector(".dco-note-font-value");
        if (select) select.value = String(clampNoteFontSize(state.noteFontSize));
        if (value) value.textContent = `${clampNoteFontSize(state.noteFontSize)} px`;
    }

    function updateZoomControls(state) {
        const value = state.root.querySelector(".dco-sketch-zoom-value");
        const zoomIn = state.root.querySelector(".dco-sketch-zoom-in");
        const zoomOut = state.root.querySelector(".dco-sketch-zoom-out");
        if (!value || !zoomIn || !zoomOut) return;
        value.textContent = `${Math.round(state.zoom * 100)}%`;
        zoomIn.disabled = state.zoom >= MAX_ZOOM - 0.001;
        zoomOut.disabled = state.zoom <= MIN_ZOOM + 0.001;
    }

    function setZoom(state, zoom, anchor = state.hoverPoint) {
        const nextZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, Number(zoom) || MIN_ZOOM));
        const current = state.viewBox;
        const focus = anchor || {
            x: current.x + current.width / 2,
            y: current.y + current.height / 2,
        };
        const ratioX = current.width ? (focus.x - current.x) / current.width : 0.5;
        const ratioY = current.height ? (focus.y - current.y) / current.height : 0.5;
        const width = CANVAS_WIDTH / nextZoom;
        const height = CANVAS_HEIGHT / nextZoom;
        state.zoom = nextZoom;
        state.viewBox = clampViewBox({
            x: focus.x - width * ratioX,
            y: focus.y - height * ratioY,
            width,
            height,
        });
        renderCanvas(state);
    }

    function cancelScheduledRender(state) {
        if (state.renderFrame === null) return;
        const cancelFrame = window.cancelAnimationFrame || window.clearTimeout;
        cancelFrame(state.renderFrame);
        state.renderFrame = null;
    }

    function scheduleCanvasRender(state) {
        if (state.renderFrame !== null) return;
        const requestFrame = window.requestAnimationFrame || (callback => window.setTimeout(callback, 16));
        state.renderFrame = requestFrame(() => {
            state.renderFrame = null;
            renderCanvas(state);
        });
    }

    function snapshot(state, elements = state.elements) {
        state.undo.push(clone(elements));
        if (state.undo.length > 80) state.undo.shift();
        state.redo = [];
        state.hasChanges = true;
    }

    function addElement(state, element) {
        snapshot(state);
        state.elements.push(element);
        state.selectedId = element.id;
        state.draft = null;
        renderCanvas(state);
    }

    function selectElement(state, elementId, switchTool = true) {
        const selected = state.elements.find(element => element.id === elementId);
        state.selectedId = selected ? selected.id : "";
        if (selected && switchTool) selectTool(state, "select");
        else renderCanvas(state);
        return selected || null;
    }

    function deleteSelected(state) {
        if (!state.selectedId) return false;
        const index = state.elements.findIndex(element => element.id === state.selectedId);
        if (index < 0) return false;
        snapshot(state);
        state.elements.splice(index, 1);
        state.selectedId = "";
        renderCanvas(state);
        return true;
    }

    function applyEraser(state, startPoint, endPoint, targetId = "") {
        const eraserStart = [startPoint.x, startPoint.y];
        const eraserEnd = [endPoint.x, endPoint.y];
        let changed = false;
        const elements = [];
        state.elements.forEach(element => {
            if (element.type === "pen") {
                const result = sketchEngine.erasePenStroke(
                    element,
                    eraserStart,
                    eraserEnd,
                    state.eraserRadius,
                    () => id("pen")
                );
                changed = changed || result.changed;
                elements.push(...result.fragments);
                return;
            }
            if (targetId && element.id === targetId) {
                changed = true;
                return;
            }
            elements.push(element);
        });
        if (!changed) return false;
        if (!state.eraseChanged) {
            snapshot(state);
            state.eraseChanged = true;
        }
        state.elements = elements;
        scheduleCanvasRender(state);
        return true;
    }

    function insertTemplate(state, template) {
        const points = templatePoints(template);
        if (points.length < 2) return;
        addElement(state, {
            id: id("pen"),
            type: "pen",
            points,
            color: state.color,
        });
        selectTool(state, "select");
        const notice = state.root.querySelector(".dco-sketch-notice-text");
        notice.textContent = "تمت إضافة الشكل؛ اسحبه لتحريكه ثم أضف القياسات الحقيقية";
    }

    function appendPointerSamples(svg, event, points, forceLast = false) {
        const samples = typeof event.getCoalescedEvents === "function"
            ? event.getCoalescedEvents()
            : [event];
        const source = samples.length ? samples : [event];
        source.forEach(sample => {
            const mapped = clientPointToCanvas(svg, sample.clientX, sample.clientY);
            const point = [
                mapped.x,
                mapped.y,
            ];
            const previous = points[points.length - 1];
            if (!previous || pointDistance(previous, point) >= 1.25) points.push(point);
        });
        if (forceLast && source[source.length - 1] !== event) {
            const point = pointFromEvent(svg, event);
            const previous = points[points.length - 1];
            if (!previous || pointDistance(previous, [point.x, point.y]) >= 0.35) {
                points.push([point.x, point.y]);
            }
        }
    }

    function promptText(title, label, defaultValue, callback, actionLabel = "إضافة") {
        frappe.prompt(
            [{
                fieldname: "text",
                fieldtype: "Data",
                label,
                reqd: 1,
                default: defaultValue || "",
            }],
            values => callback(String(values.text || "").trim()),
            title,
            actionLabel
        );
    }

    function openInlineNoteEditor(state, point, existing = null) {
        if (state.inlineNoteEditor) state.inlineNoteEditor.remove();
        const fontSize = clampNoteFontSize(
            existing ? (existing.font_size || existing.fontSize) : state.noteFontSize
        );
        const editor = inlineNoteEditor.open({
            root: state.root,
            svg: state.svg,
            point,
            text: existing && existing.text,
            fontSize,
            color: existing && existing.color || state.color,
            canvas: { width: CANVAS_WIDTH, height: CANVAS_HEIGHT },
            onCommit(text) {
                if (existing) {
                    if (
                        text === String(existing.text || "")
                        && fontSize === clampNoteFontSize(existing.font_size || existing.fontSize)
                    ) return;
                    snapshot(state);
                    existing.text = text.slice(0, 500);
                    existing.font_size = fontSize;
                    existing.text_anchor = existing.text_anchor === "middle" ? "middle" : "end";
                    renderCanvas(state);
                    return;
                }
                addElement(state, {
                    id: id("note"),
                    type: "note",
                    x: Number(point.x),
                    y: Number(point.y),
                    text: text.slice(0, 500),
                    color: state.color,
                    font_size: fontSize,
                    text_anchor: "end",
                });
            },
            onClose() {
                if (state.inlineNoteEditor === editor) state.inlineNoteEditor = null;
            },
        });
        state.inlineNoteEditor = editor;
        return editor;
    }

    function targetElementId(event) {
        const target = event.target && event.target.closest
            ? event.target.closest("[data-element-id]")
            : null;
        return target ? target.dataset.elementId : "";
    }

    function editSelected(state) {
        const element = state.elements.find(item => item.id === state.selectedId);
        if (!element || !["dimension", "note"].includes(element.type)) return false;
        if (element.type === "note") {
            openInlineNoteEditor(state, {
                x: Number(element.x),
                y: Number(element.y),
            }, element);
            return true;
        }
        promptText(
            "تعديل القياس",
            "القيمة الحقيقية مع الوحدة",
            element.text || "",
            text => {
                if (!text || text === String(element.text || "")) return;
                snapshot(state);
                element.text = text.slice(0, 500);
                renderCanvas(state);
            },
            "حفظ التعديل"
        );
        return true;
    }

    function beginDrawing(state, event) {
        const wantsPan = Boolean(state.spaceHeld || event.button === 1);
        if (event.button !== undefined && event.button !== 0 && !wantsPan) return;
        let point = pointFromEvent(state.svg, event);
        state.pointerInside = true;
        state.hoverPoint = point;
        state.snapPoint = null;

        if (wantsPan) {
            state.pointerId = event.pointerId;
            state.panning = {
                clientX: Number(event.clientX),
                clientY: Number(event.clientY),
                viewBox: { ...state.viewBox },
            };
            state.svg.classList.add("is-panning");
            state.svg.setPointerCapture(event.pointerId);
            updateCursorPreview(state);
            event.preventDefault();
            return;
        }

        if (state.tool === "select") {
            const selected = selectElement(state, targetElementId(event), false);
            if (selected) {
                state.pointerId = event.pointerId;
                state.moving = {
                    start: point,
                    originalElements: clone(state.elements),
                    moved: false,
                };
                state.svg.setPointerCapture(event.pointerId);
            }
            event.preventDefault();
            return;
        }

        if (state.tool === "eraser") {
            state.pointerId = event.pointerId;
            state.erasing = true;
            state.eraseChanged = false;
            state.eraserLast = point;
            state.svg.setPointerCapture(event.pointerId);
            applyEraser(state, point, point, targetElementId(event));
            updateCursorPreview(state, point, true);
            event.preventDefault();
            return;
        }
        if (state.tool === "note") {
            openInlineNoteEditor(state, point);
            event.preventDefault();
            return;
        }

        if (["pen", "line", "dimension"].includes(state.tool)) {
            const anchor = nearestAnchor([point.x, point.y], state.elements);
            if (anchor) {
                point = { x: anchor[0], y: anchor[1] };
                state.hoverPoint = point;
                state.snapPoint = point;
            }
        }
        state.start = point;
        state.pointerId = event.pointerId;
        state.svg.setPointerCapture(event.pointerId);
        if (state.tool === "pen") {
            state.draft = { id: id("pen"), type: "pen", points: [[point.x, point.y]], color: state.color };
        } else if (state.tool === "line" || state.tool === "dimension") {
            state.draft = { id: id(state.tool), type: state.tool, x1: point.x, y1: point.y, x2: point.x, y2: point.y, color: state.color };
        } else if (state.tool === "rectangle") {
            state.draft = { id: id("rectangle"), type: "rectangle", x: point.x, y: point.y, width: 0, height: 0, color: state.color };
        } else if (state.tool === "ellipse") {
            state.draft = { id: id("ellipse"), type: "ellipse", cx: point.x, cy: point.y, rx: 0, ry: 0, color: state.color };
        }
        renderCanvas(state);
        event.preventDefault();
    }

    function continueDrawing(state, event) {
        const point = pointFromEvent(state.svg, event);
        state.pointerInside = true;
        state.hoverPoint = point;
        updateCursorPreview(state, point, true);

        if (state.panning && event.pointerId === state.pointerId) {
            const rect = state.svg.getBoundingClientRect();
            const dx = (Number(event.clientX) - state.panning.clientX)
                * state.panning.viewBox.width / Math.max(1, rect.width);
            const dy = (Number(event.clientY) - state.panning.clientY)
                * state.panning.viewBox.height / Math.max(1, rect.height);
            state.viewBox = clampViewBox({
                ...state.panning.viewBox,
                x: state.panning.viewBox.x - dx,
                y: state.panning.viewBox.y - dy,
            });
            scheduleCanvasRender(state);
            event.preventDefault();
            return;
        }
        if (state.moving && event.pointerId === state.pointerId) {
            const dx = point.x - state.moving.start.x;
            const dy = point.y - state.moving.start.y;
            state.moving.moved = state.moving.moved || Math.hypot(dx, dy) >= 1.5;
            state.elements = state.moving.originalElements.map(element =>
                element.id === state.selectedId ? translateElement(element, dx, dy) : clone(element)
            );
            scheduleCanvasRender(state);
            event.preventDefault();
            return;
        }
        if (state.erasing && event.pointerId === state.pointerId) {
            applyEraser(state, state.eraserLast || point, point);
            state.eraserLast = point;
            event.preventDefault();
            return;
        }
        if (!state.draft || event.pointerId !== state.pointerId) return;
        if (state.draft.type === "pen") {
            appendPointerSamples(state.svg, event, state.draft.points);
            const last = state.draft.points[state.draft.points.length - 1];
            const closeStart = state.draft.points.length > 8
                && polylineLength(state.draft.points) >= 70
                && pointDistance(last, state.draft.points[0]) <= ENDPOINT_SNAP_RADIUS * 1.35
                ? state.draft.points[0]
                : null;
            const anchor = closeStart || nearestAnchor(last, state.elements);
            state.snapPoint = anchor ? { x: anchor[0], y: anchor[1] } : null;
        } else {
            if (state.draft.type === "line" || state.draft.type === "dimension") {
                const aligned = snapLineEnd(state.start, point, Boolean(event.shiftKey));
                const anchor = nearestAnchor([aligned.x, aligned.y], state.elements);
                const endpoint = anchor ? { x: anchor[0], y: anchor[1] } : aligned;
                state.draft.x2 = endpoint.x;
                state.draft.y2 = endpoint.y;
                state.snapPoint = anchor ? endpoint : null;
            } else if (state.draft.type === "rectangle") {
                state.snapPoint = null;
                state.draft.x = Math.min(state.start.x, point.x);
                state.draft.y = Math.min(state.start.y, point.y);
                state.draft.width = Math.abs(point.x - state.start.x);
                state.draft.height = Math.abs(point.y - state.start.y);
            } else if (state.draft.type === "ellipse") {
                state.snapPoint = null;
                state.draft.cx = (state.start.x + point.x) / 2;
                state.draft.cy = (state.start.y + point.y) / 2;
                state.draft.rx = Math.abs(point.x - state.start.x) / 2;
                state.draft.ry = Math.abs(point.y - state.start.y) / 2;
            }
        }
        scheduleCanvasRender(state);
        event.preventDefault();
    }

    function finishDrawing(state, event) {
        if (state.panning && event.pointerId === state.pointerId) {
            cancelScheduledRender(state);
            state.panning = null;
            state.pointerId = null;
            state.svg.classList.remove("is-panning");
            try { state.svg.releasePointerCapture(event.pointerId); } catch (error) { /* pointer already released */ }
            renderCanvas(state);
            event.preventDefault();
            return;
        }
        if (state.moving && event.pointerId === state.pointerId) {
            cancelScheduledRender(state);
            if (event.type !== "pointercancel" && state.moving.moved) {
                snapshot(state, state.moving.originalElements);
            } else {
                state.elements = state.moving.originalElements;
            }
            state.moving = null;
            state.pointerId = null;
            try { state.svg.releasePointerCapture(event.pointerId); } catch (error) { /* pointer already released */ }
            renderCanvas(state);
            event.preventDefault();
            return;
        }
        if (state.erasing && event.pointerId === state.pointerId) {
            if (event.type !== "pointercancel") {
                const point = pointFromEvent(state.svg, event);
                state.hoverPoint = point;
                applyEraser(state, state.eraserLast || point, point);
            }
            cancelScheduledRender(state);
            state.erasing = false;
            state.eraseChanged = false;
            state.eraserLast = null;
            state.pointerId = null;
            try { state.svg.releasePointerCapture(event.pointerId); } catch (error) { /* pointer already released */ }
            renderCanvas(state);
            event.preventDefault();
            return;
        }
        if (!state.draft || event.pointerId !== state.pointerId) return;
        cancelScheduledRender(state);
        if (state.draft.type === "pen" && event.type !== "pointercancel") {
            appendPointerSamples(state.svg, event, state.draft.points, true);
        } else if (
            event.type !== "pointercancel"
            && (state.draft.type === "line" || state.draft.type === "dimension")
        ) {
            const point = pointFromEvent(state.svg, event);
            const aligned = snapLineEnd(state.start, point, Boolean(event.shiftKey));
            const anchor = nearestAnchor([aligned.x, aligned.y], state.elements);
            state.draft.x2 = anchor ? anchor[0] : aligned.x;
            state.draft.y2 = anchor ? anchor[1] : aligned.y;
        }
        const element = clone(state.draft);
        state.draft = null;
        state.pointerId = null;
        try { state.svg.releasePointerCapture(event.pointerId); } catch (error) { /* pointer already released */ }

        if (event.type === "pointercancel") {
            state.snapPoint = null;
            renderCanvas(state);
            return;
        }
        if (element.type === "pen") {
            element.points = snapPenEndpoints(
                normalizePenStroke(element.points),
                state.elements
            );
            state.snapPoint = null;
            if (element.points.length >= 2) addElement(state, element);
            else renderCanvas(state);
            return;
        }
        const tooSmall = element.type === "rectangle"
            ? element.width < 4 || element.height < 4
            : element.type === "ellipse"
                ? element.rx < 2 || element.ry < 2
                : Math.hypot(element.x2 - element.x1, element.y2 - element.y1) < 4;
        if (tooSmall) {
            state.snapPoint = null;
            renderCanvas(state);
            return;
        }
        if (element.type === "dimension") {
            state.snapPoint = null;
            renderCanvas(state);
            promptText("إضافة قياس حقيقي", "القيمة مع الوحدة، مثال: 85 سم", " سم", text => {
                if (!text) return;
                element.text = text.slice(0, 500);
                addElement(state, element);
            });
            return;
        }
        state.snapPoint = null;
        addElement(state, element);
    }

    function selectTool(state, tool, shouldRender = true) {
        state.tool = tool;
        state.svg.dataset.tool = tool;
        state.root.querySelectorAll(".dco-sketch-tool").forEach(button => {
            button.classList.toggle("is-active", button.dataset.tool === tool);
            button.setAttribute("aria-pressed", button.dataset.tool === tool ? "true" : "false");
        });
        const eraserControls = state.root.querySelector(".dco-sketch-eraser-controls");
        eraserControls.classList.toggle("is-visible", tool === "eraser");
        eraserControls.setAttribute("aria-hidden", tool === "eraser" ? "false" : "true");
        const notice = state.root.querySelector(".dco-sketch-notice-text");
        const messages = {
            eraser: "اسحب فوق الجزء المطلوب؛ خط القلم لن يُحذف كاملًا",
            pen: "ارسم بحرية؛ التنعيم وإغلاق النهايات يعملان أثناء الرسم",
            select: state.selectedId
                ? "اسحب العنصر لتحريكه، أو انقر مرتين لتعديل نصه"
                : "انقر على أي عنصر لتحديده وتحريكه أو حذفه",
            dimension: "اسحب سهم القياس ثم اكتب القيمة الحقيقية مع الوحدة",
            note: "انقر في موضع الملاحظة ثم اكتب تعليمات المصمم",
            line: "اسحب الخط؛ الأفقي والعمودي يُضبطان تلقائيًا",
            rectangle: "اسحب من أول زاوية حتى الزاوية المقابلة",
            ellipse: "اسحب من طرف الشكل إلى الطرف المقابل",
        };
        notice.textContent = messages[tool] || "ابدأ من النقطة الأولى واسحب حتى موضع النهاية";
        if (shouldRender) renderCanvas(state);
        else {
            updateSelectionControls(state);
            updateNoteFontControls(state);
            updateCursorPreview(state);
        }
    }

    function undo(state) {
        if (!state.undo.length) return;
        state.redo.push(clone(state.elements));
        state.elements = state.undo.pop();
        if (!state.elements.some(element => element.id === state.selectedId)) state.selectedId = "";
        state.hasChanges = true;
        renderCanvas(state);
    }

    function redo(state) {
        if (!state.redo.length) return;
        state.undo.push(clone(state.elements));
        state.elements = state.redo.pop();
        if (!state.elements.some(element => element.id === state.selectedId)) state.selectedId = "";
        state.hasChanges = true;
        renderCanvas(state);
    }

    function bindZoomControls(state) {
        state.root.querySelector(".dco-sketch-zoom-in").addEventListener("click", () => {
            setZoom(state, state.zoom * ZOOM_STEP);
        });
        state.root.querySelector(".dco-sketch-zoom-out").addEventListener("click", () => {
            setZoom(state, state.zoom / ZOOM_STEP);
        });
        state.root.querySelector(".dco-sketch-zoom-reset").addEventListener("click", () => {
            setZoom(state, MIN_ZOOM, {
                x: CANVAS_WIDTH / 2,
                y: CANVAS_HEIGHT / 2,
            });
        });
        state.svg.addEventListener("wheel", event => {
            if (!event.ctrlKey && !event.metaKey) return;
            event.preventDefault();
            state.hoverPoint = pointFromEvent(state.svg, event);
            setZoom(
                state,
                event.deltaY < 0 ? state.zoom * ZOOM_STEP : state.zoom / ZOOM_STEP,
                state.hoverPoint
            );
        }, { passive: false });
    }

    function bind(state) {
        state.root.querySelectorAll(".dco-sketch-tool").forEach(button => {
            button.addEventListener("click", () => selectTool(state, button.dataset.tool));
        });
        state.root.querySelectorAll(".dco-sketch-template").forEach(button => {
            button.addEventListener("click", () => insertTemplate(state, button.dataset.template));
        });
        state.root.querySelectorAll(".dco-sketch-color").forEach(button => {
            button.addEventListener("click", () => {
                state.color = button.dataset.color;
                state.root.querySelectorAll(".dco-sketch-color").forEach(item => item.classList.toggle("is-active", item === button));
                updateCursorPreview(state);
            });
        });
        const noteFontSize = state.root.querySelector(".dco-note-font-size");
        noteFontSize.addEventListener("change", () => {
            const nextSize = clampNoteFontSize(noteFontSize.value);
            state.noteFontSize = nextSize;
            const selected = state.elements.find(element =>
                element.id === state.selectedId && element.type === "note"
            );
            if (!selected || clampNoteFontSize(selected.font_size || selected.fontSize) === nextSize) {
                updateNoteFontControls(state);
                return;
            }
            snapshot(state);
            selected.font_size = nextSize;
            renderCanvas(state);
        });
        const eraserSize = state.root.querySelector(".dco-sketch-eraser-size");
        eraserSize.addEventListener("input", () => {
            state.eraserRadius = Math.max(
                MIN_ERASER_RADIUS,
                Math.min(MAX_ERASER_RADIUS, Number(eraserSize.value) || DEFAULT_ERASER_RADIUS)
            );
            state.root.querySelector(".dco-sketch-eraser-value").textContent = state.eraserRadius <= 14
                ? "صغيرة"
                : state.eraserRadius <= 24
                    ? "متوسطة"
                    : "كبيرة";
            updateCursorPreview(state);
        });
        state.root.querySelector(".dco-sketch-undo").addEventListener("click", () => undo(state));
        state.root.querySelector(".dco-sketch-redo").addEventListener("click", () => redo(state));
        state.root.querySelector(".dco-sketch-edit-selected").addEventListener("click", () => {
            editSelected(state);
        });
        state.root.querySelector(".dco-sketch-delete-selected").addEventListener("click", () => {
            if (!state.selectedId) return;
            frappe.confirm("هل تريد حذف العنصر المحدد فقط؟", () => deleteSelected(state));
        });
        state.root.querySelector(".dco-sketch-clear").addEventListener("click", () => {
            if (!state.elements.length) return;
            frappe.confirm("هل تريد مسح جميع عناصر الورقة؟", () => {
                snapshot(state);
                state.elements = [];
                state.selectedId = "";
                renderCanvas(state);
            });
        });
        state.root.querySelector(".dco-sketch-fullscreen-button").addEventListener("click", event => {
            state.dialog.$wrapper.toggleClass("dco-sketch-fullscreen");
            event.currentTarget.textContent = state.dialog.$wrapper.hasClass("dco-sketch-fullscreen")
                ? "× تصغير"
                : "⛶ ملء الشاشة";
        });
        bindZoomControls(state);
        state.root.addEventListener("click", event => {
            const item = event.target.closest && event.target.closest("[data-select-id]");
            if (!item) return;
            selectElement(state, item.dataset.selectId);
        });
        state.svg.addEventListener("pointerdown", event => beginDrawing(state, event));
        state.svg.addEventListener("pointermove", event => continueDrawing(state, event));
        state.svg.addEventListener("pointerup", event => finishDrawing(state, event));
        state.svg.addEventListener("pointercancel", event => finishDrawing(state, event));
        state.svg.addEventListener("pointerenter", event => {
            state.pointerInside = true;
            state.hoverPoint = pointFromEvent(state.svg, event);
            updateCursorPreview(state);
        });
        state.svg.addEventListener("pointerleave", () => {
            if (state.draft || state.erasing) return;
            state.pointerInside = false;
            updateCursorPreview(state);
        });
        state.svg.addEventListener("dblclick", event => {
            const selected = selectElement(state, targetElementId(event));
            if (selected) editSelected(state);
            event.preventDefault();
        });
        state.keyHandler = event => {
            if (!state.dialog.$wrapper.is(":visible")) return;
            const target = event.target;
            if (
                target
                && (/INPUT|TEXTAREA|SELECT/.test(target.tagName) || target.isContentEditable)
            ) return;
            if (event.code === "Space") {
                event.preventDefault();
                state.spaceHeld = true;
                state.svg.classList.add("is-pan-ready");
                updateCursorPreview(state);
            } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
                event.preventDefault();
                event.shiftKey ? redo(state) : undo(state);
            } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
                event.preventDefault();
                redo(state);
            } else if (event.key.toLowerCase() === "p") {
                event.preventDefault();
                selectTool(state, "pen");
            } else if (event.key.toLowerCase() === "e") {
                event.preventDefault();
                selectTool(state, "eraser");
            } else if (event.key.toLowerCase() === "v") {
                event.preventDefault();
                selectTool(state, "select");
            } else if (event.key === "Delete" || event.key === "Backspace") {
                if (!state.selectedId || state.tool !== "select") return;
                event.preventDefault();
                deleteSelected(state);
            } else if (event.key === "Escape") {
                if (!state.selectedId) return;
                event.preventDefault();
                state.selectedId = "";
                renderCanvas(state);
            } else if (event.key === "+" || event.key === "=") {
                event.preventDefault();
                setZoom(state, state.zoom * ZOOM_STEP);
            } else if (event.key === "-") {
                event.preventDefault();
                setZoom(state, state.zoom / ZOOM_STEP);
            } else if (event.key === "0") {
                event.preventDefault();
                setZoom(state, MIN_ZOOM, {
                    x: CANVAS_WIDTH / 2,
                    y: CANVAS_HEIGHT / 2,
                });
            }
        };
        state.keyUpHandler = event => {
            if (event.code !== "Space") return;
            state.spaceHeld = false;
            state.svg.classList.remove("is-pan-ready");
            updateCursorPreview(state);
        };
        document.addEventListener("keydown", state.keyHandler);
        document.addEventListener("keyup", state.keyUpHandler);
        state.dialog.$wrapper.on("hide.bs.modal.dco-special-shape-guard", event => {
            if (!state.hasChanges || state.allowClose) return;
            event.preventDefault();
            frappe.confirm(
                "لديك تعديلات لم تحفظ بعد. هل تريد إغلاق الرسم وفقدانها؟",
                () => {
                    state.allowClose = true;
                    state.dialog.hide();
                }
            );
        });
        state.dialog.$wrapper.on("hidden.bs.modal.dco-special-shape", () => {
            cancelScheduledRender(state);
            if (state.inlineNoteEditor) state.inlineNoteEditor.remove();
            document.removeEventListener("keydown", state.keyHandler);
            document.removeEventListener("keyup", state.keyUpHandler);
        });
    }

    function save(state) {
        if (!state.elements.length) {
            frappe.msgprint("ارسم الشكل أو أضف ملاحظة واحدة على الأقل قبل الحفظ.");
            return;
        }
        const payload = {
            version: 1,
            canvas: { width: CANVAS_WIDTH, height: CANVAS_HEIGHT },
            elements: clone(state.elements),
            meta: {
                purpose: "operator_documentation_only",
                piece_no: state.row.idx || state.row.piece_no || 0,
                blank_width_cm: Number(state.row.width_cm) || 0,
                blank_length_cm: Number(state.row.length_cm) || 0,
            },
        };
        state.row.special_shape_drawing_json = JSON.stringify(payload);
        state.row.special_shape_status = "Documented";
        state.frm.dirty();
        state.hasChanges = false;
        state.allowClose = true;
        Promise.resolve(
            state.frm.script_manager.trigger("piece_type", state.row.doctype, state.row.name)
        ).catch(error => console.error(error));
        state.dialog.hide();
        if (window.AlmdinaDoorCuttingFastEntry && window.AlmdinaDoorCuttingFastEntry.render) {
            window.AlmdinaDoorCuttingFastEntry.render(state.frm);
        }
        frappe.show_alert({
            message: state.row.special_shape_price_status === "Approved"
                ? "تم حفظ الرسم. سيلغى اعتماد السعر السابق عند حفظ الطلب لأن التصميم تغيّر."
                : "تم حفظ توثيق الدرفة الخاصة داخل الطلب.",
            indicator: state.row.special_shape_price_status === "Approved" ? "orange" : "green",
        }, 6);
    }

    function open(frm, row, options = {}) {
        installStyles();
        if ((row.piece_type || "Regular") !== "Special") {
            frappe.msgprint("حوّل نوع الدرفة إلى «خاصة» أولًا.");
            return;
        }

        const readOnly = Boolean(options.readOnly);
        const dialog = new frappe.ui.Dialog({
            title: `رسم الدرفة الخاصة رقم ${row.idx || row.piece_no || ""}`,
            size: "extra-large",
            fields: [{
                fieldname: "special_shape_canvas",
                fieldtype: "HTML",
                options: shellHtml(row),
            }],
            primary_action_label: readOnly ? "إغلاق" : "حفظ الرسم",
            primary_action() {
                readOnly ? dialog.hide() : save(state);
            },
        });
        dialog.$wrapper.addClass("dco-special-shape-modal");
        if (readOnly) dialog.$wrapper.addClass("dco-special-shape-readonly");
        dialog.show();

        const root = dialog.fields_dict.special_shape_canvas.$wrapper
            .find(".dco-special-sketch-shell").get(0);
        if (!root) {
            dialog.hide();
            frappe.msgprint("تعذر تجهيز نافذة الرسم. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            return;
        }
        const state = {
            frm,
            row,
            dialog,
            root,
            svg: root.querySelector(".dco-sketch-paper"),
            elements: parseDrawing(row.special_shape_drawing_json),
            undo: [],
            redo: [],
            draft: null,
            start: null,
            pointerId: null,
            pointerInside: false,
            hoverPoint: null,
            selectedId: "",
            moving: null,
            panning: null,
            spaceHeld: false,
            snapPoint: null,
            erasing: false,
            eraseChanged: false,
            eraserLast: null,
            eraserRadius: DEFAULT_ERASER_RADIUS,
            noteFontSize: DEFAULT_NOTE_FONT_SIZE,
            inlineNoteEditor: null,
            renderFrame: null,
            zoom: MIN_ZOOM,
            viewBox: {
                x: 0,
                y: 0,
                width: CANVAS_WIDTH,
                height: CANVAS_HEIGHT,
            },
            gridVisible: true,
            hasChanges: false,
            allowClose: false,
            tool: "pen",
            color: COLORS[0],
            readOnly,
        };
        if (readOnly) {
            root.querySelector(".dco-sketch-toolbar").style.display = "none";
            root.style.gridTemplateColumns = "minmax(0,1fr) 230px";
            state.svg.style.cursor = "default";
            root.querySelector(".dco-sketch-fullscreen-button").addEventListener("click", event => {
                dialog.$wrapper.toggleClass("dco-sketch-fullscreen");
                event.currentTarget.textContent = dialog.$wrapper.hasClass("dco-sketch-fullscreen")
                    ? "× تصغير"
                    : "⛶ ملء الشاشة";
            });
            bindZoomControls(state);
        } else {
            bind(state);
        }
        renderCanvas(state);
    }

    window.AlmdinaSpecialShapeEditor = {
        open,
        view(frm, row) { open(frm, row, { readOnly: true }); },
        parseDrawing,
        normalizePenStroke,
        clientPointToCanvas,
        erasePenStroke,
        snapLineEnd,
        snapPenEndpoints,
        translateElement,
        elementBounds,
        templatePoints,
        clampViewBox,
    };
})();
