(() => {
    "use strict";

    const geometry = window.AlmdinaSpecialShapeGeometry;
    const legacyEditor = window.AlmdinaSpecialShapeEditor;
    if (!geometry || !legacyEditor) return;

    const STYLE_ID = "dco-special-shape-builder-css";
    const TEMPLATES = [
        { key: "single-slope", icon: "◩", label: "طرف مائل", hint: "ميل من جهة واحدة" },
        { key: "double-clipped", icon: "⬡", label: "قصتان علويتان", hint: "زاويتان متماثلتان" },
        { key: "trapezoid", icon: "▱", label: "شبه منحرف", hint: "ميل من الجهتين" },
        { key: "l-notch", icon: "⌞", label: "فتحة زاوية L", hint: "نقرة داخل أحد الأركان" },
        { key: "arch", icon: "⌒", label: "قوس علوي", hint: "قوس مقسّم بدقة" },
        { key: "custom", icon: "✣", label: "شكل بالنقاط", hint: "ابدأ ثم أضف زوايا" },
    ];

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function num(value) {
        const result = Number(String(value ?? "").replace(",", "."));
        return Number.isFinite(result) ? result : 0;
    }

    function pieceDimensions(row) {
        return {
            width: num(row && row.width_cm),
            length: num(row && row.length_cm),
        };
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-special-geometry-modal .modal-dialog{max-width:min(1460px,97vw)!important;width:97vw!important}
            .dco-special-geometry-modal .modal-content{border:0;border-radius:18px;overflow:hidden;box-shadow:0 28px 90px rgba(15,23,42,.25)}
            .dco-special-geometry-modal .modal-header{padding:14px 20px;border-bottom:1px solid var(--border-color,#e2e8f0)}
            .dco-special-geometry-modal .modal-body{padding:0!important;background:#f3f6f8}
            .dco-special-geometry-modal .modal-footer{padding:11px 18px;background:#fff;border-top:1px solid #e2e8f0}
            .dco-shape-builder{direction:rtl;display:grid;grid-template-columns:220px minmax(0,1fr) 285px;min-height:700px;color:var(--text-color,#172033)}
            .dco-shape-templates,.dco-shape-inspector{background:var(--card-bg,#fff);padding:15px 13px;overflow:auto}
            .dco-shape-templates{border-left:1px solid var(--border-color,#e2e8f0)}
            .dco-shape-inspector{border-right:1px solid var(--border-color,#e2e8f0)}
            .dco-shape-side-heading{font-size:12px;font-weight:900;margin-bottom:4px}
            .dco-shape-side-hint{font-size:10px;line-height:1.65;color:#64748b;margin-bottom:12px}
            .dco-shape-template-list{display:flex;flex-direction:column;gap:7px}
            .dco-shape-template{display:flex;align-items:center;gap:10px;width:100%;min-height:58px;padding:8px 9px;border:1px solid #dce3e8;border-radius:12px;background:#fff;color:inherit;cursor:pointer;text-align:right;transition:.12s ease}
            .dco-shape-template:hover{border-color:#7cb7e8;background:#f6fbff}
            .dco-shape-template.is-active{border-color:#2490ef;background:#edf7ff;box-shadow:0 0 0 2px rgba(36,144,239,.1)}
            .dco-shape-template-icon{display:grid;place-items:center;width:39px;height:39px;border-radius:10px;background:#eef3f7;color:#174f79;font-size:23px;flex:0 0 auto}
            .dco-shape-template strong{display:block;font-size:11px}
            .dco-shape-template small{display:block;font-size:9px;color:#718096;margin-top:2px}
            .dco-shape-legacy-card{margin-top:14px;padding:10px;border:1px dashed #d4a24b;border-radius:12px;background:#fff9eb;font-size:10px;line-height:1.65;color:#79510d}
            .dco-shape-secondary{width:100%;min-height:36px;margin-top:8px;border:1px solid #d7dee4;border-radius:9px;background:#fff;color:#315064;font-size:10px;font-weight:900;cursor:pointer}
            .dco-shape-secondary:hover{border-color:#2490ef;color:#1674c5}
            .dco-shape-secondary.is-danger{color:#b42318;border-color:#efc1bc}
            .dco-shape-workspace{min-width:0;padding:13px;display:flex;flex-direction:column;gap:9px}
            .dco-shape-topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:10px 12px;border:1px solid #dde4e9;border-radius:12px;background:#fff}
            .dco-shape-meta{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
            .dco-shape-pill{display:inline-flex;align-items:center;gap:5px;padding:5px 9px;border-radius:999px;background:#f1f5f8;font-size:10px}
            .dco-shape-pill b{font-variant-numeric:tabular-nums}
            .dco-shape-status{background:#fff3d6;color:#835510}
            .dco-shape-status.is-valid{background:#e8f8ef;color:#12643f}
            .dco-shape-status.is-dirty{box-shadow:0 0 0 2px rgba(208,138,21,.13)}
            .dco-shape-toolbar{display:flex;gap:5px}
            .dco-shape-tool{min-width:72px;height:34px;border:1px solid #d8dfe5;border-radius:8px;background:#fff;font-size:10px;font-weight:800;cursor:pointer}
            .dco-shape-tool:hover:not(:disabled){border-color:#2490ef;color:#1674c5}
            .dco-shape-tool:disabled{opacity:.4;cursor:not-allowed}
            .dco-shape-canvas-wrap{position:relative;flex:1;min-height:585px;display:grid;place-items:center;padding:18px;border:1px solid #d8e0e6;border-radius:15px;background:linear-gradient(135deg,#e9eef2,#dfe6eb);overflow:hidden}
            .dco-shape-canvas{display:block;width:100%;height:100%;max-height:620px;background:#fff;border-radius:8px;box-shadow:0 10px 32px rgba(26,39,52,.13);touch-action:none;user-select:none}
            .dco-shape-empty{position:absolute;inset:50% auto auto 50%;transform:translate(-50%,-50%);width:min(390px,80%);padding:22px;border:1px dashed #aebdca;border-radius:15px;background:rgba(255,255,255,.95);text-align:center;pointer-events:none}
            .dco-shape-empty b{display:block;font-size:15px;margin-bottom:6px}
            .dco-shape-empty span{font-size:11px;line-height:1.7;color:#64748b}
            .dco-shape-polygon{fill:#dff2fc;stroke:#172033;stroke-width:1.4;vector-effect:non-scaling-stroke;stroke-linejoin:round}
            .dco-shape-blank{fill:url(#dco-shape-grid);stroke:#94a3b8;stroke-width:1;stroke-dasharray:6 5;vector-effect:non-scaling-stroke}
            .dco-shape-edge-hit{stroke:transparent;stroke-width:16;vector-effect:non-scaling-stroke;cursor:copy}
            .dco-shape-edge{stroke:#172033;stroke-width:1.4;vector-effect:non-scaling-stroke;pointer-events:none}
            .dco-shape-edge-add{fill:#fff;stroke:#2490ef;stroke-width:1.5;vector-effect:non-scaling-stroke;cursor:copy}
            .dco-shape-edge-plus{fill:#1674c5;font-size:4px;font-weight:900;text-anchor:middle;dominant-baseline:central;pointer-events:none}
            .dco-shape-vertex{fill:#fff;stroke:#1674c5;stroke-width:2;vector-effect:non-scaling-stroke;cursor:grab}
            .dco-shape-vertex.is-selected{fill:#2490ef;stroke:#fff;stroke-width:2.5}
            .dco-shape-vertex-label{fill:#fff;font-size:3.4px;font-weight:900;text-anchor:middle;dominant-baseline:central;pointer-events:none}
            .dco-shape-edge-label rect{fill:rgba(255,255,255,.92);stroke:#d5dee5;stroke-width:.6}
            .dco-shape-edge-label text{fill:#425466;font-size:3px;font-weight:800;text-anchor:middle;dominant-baseline:central}
            .dco-shape-helper{stroke:#2490ef;stroke-width:1;stroke-dasharray:4 3;vector-effect:non-scaling-stroke;pointer-events:none}
            .dco-shape-dimension{stroke:#536779;stroke-width:1;vector-effect:non-scaling-stroke}
            .dco-shape-dimension-text{fill:#324b5f;font-size:4px;font-weight:900;text-anchor:middle}
            .dco-shape-card{border:1px solid #dfe5ea;border-radius:12px;overflow:hidden;margin-bottom:10px}
            .dco-shape-card-title{padding:9px 10px;background:#f7f9fa;border-bottom:1px solid #e5e9ec;font-size:11px;font-weight:900}
            .dco-shape-card-body{padding:10px}
            .dco-shape-selected-empty{font-size:10px;line-height:1.7;color:#718096;text-align:center;padding:9px 4px}
            .dco-shape-input-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
            .dco-shape-input label{display:block;font-size:9px;font-weight:800;color:#64748b;margin-bottom:4px}
            .dco-shape-input-shell{display:flex;align-items:center;border:1px solid #d8e0e6;border-radius:9px;overflow:hidden}
            .dco-shape-input-shell input{width:100%;height:39px;border:0!important;box-shadow:none!important;padding:6px 8px;text-align:center;font-size:15px;font-weight:900}
            .dco-shape-input-shell span{padding:0 7px;border-right:1px solid #e5e9ec;color:#64748b;font-size:9px}
            .dco-shape-point-actions{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px}
            .dco-shape-point-actions button{min-height:33px;border:1px solid #d9e0e5;border-radius:8px;background:#fff;font-size:9px;font-weight:900;cursor:pointer}
            .dco-shape-point-actions button:hover{border-color:#2490ef;color:#1674c5}
            .dco-shape-point-actions .is-danger{color:#b42318;border-color:#efc1bc}
            .dco-shape-validation{padding:10px;border-radius:10px;background:#fff4f1;border:1px solid #efc0b9;color:#9d3025;font-size:10px;line-height:1.65}
            .dco-shape-validation.is-valid{background:#eaf8f1;border-color:#b8e1ca;color:#12633f}
            .dco-shape-validation b{display:block;margin-bottom:3px}
            .dco-shape-stats{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px}
            .dco-shape-stat{padding:7px;border-radius:8px;background:#f5f8fa;text-align:center}
            .dco-shape-stat b{display:block;font-size:13px;font-variant-numeric:tabular-nums}
            .dco-shape-stat span{font-size:8px;color:#64748b}
            .dco-shape-guide{font-size:10px;line-height:1.75;color:#5d6b78}
            .dco-shape-guide ol{margin:0;padding-right:18px}
            .dco-shape-guide li{margin-bottom:5px}
            .dco-shape-builder[data-readonly="1"]{grid-template-columns:minmax(0,1fr) 280px}
            .dco-shape-builder[data-readonly="1"] .dco-shape-templates{display:none}
            .dco-shape-builder[data-readonly="1"] .dco-shape-edge-hit,
            .dco-shape-builder[data-readonly="1"] .dco-shape-edge-add,
            .dco-shape-builder[data-readonly="1"] .dco-shape-edge-plus,
            .dco-shape-builder[data-readonly="1"] .dco-shape-vertex{cursor:default}
            @media(max-width:1080px){.dco-shape-builder{grid-template-columns:minmax(0,1fr) 265px;grid-template-areas:"templates templates" "workspace inspector";min-height:680px}.dco-shape-templates{grid-area:templates;border:0;border-bottom:1px solid #e2e8f0;padding:10px 12px}.dco-shape-workspace{grid-area:workspace}.dco-shape-inspector{grid-area:inspector;display:block}.dco-shape-template-list{display:grid;grid-template-columns:repeat(3,1fr)}.dco-shape-template{min-height:48px}.dco-shape-side-heading,.dco-shape-side-hint{display:none}.dco-shape-legacy-card{display:none}.dco-shape-canvas-wrap{min-height:470px}.dco-shape-builder[data-readonly="1"]{grid-template-areas:"workspace inspector";grid-template-columns:minmax(0,1fr) 265px}}
            @media(max-width:720px){.dco-special-geometry-modal .modal-dialog{width:100vw!important;margin:0!important}.dco-special-geometry-modal .modal-content{min-height:100vh;border-radius:0}.dco-shape-builder{display:flex;flex-direction:column;min-height:0}.dco-shape-templates{order:2;border:0;border-top:1px solid #e2e8f0}.dco-shape-template-list{display:grid;grid-template-columns:1fr 1fr}.dco-shape-workspace{padding:8px}.dco-shape-canvas-wrap{min-height:430px}.dco-shape-inspector{display:block;border:0;border-top:1px solid #e2e8f0}.dco-shape-builder[data-readonly="1"]{display:flex}}
        `;
        document.head.appendChild(style);
    }

    function shellHtml(row, readOnly) {
        const dimensions = pieceDimensions(row);
        const hasLegacy = Boolean(String(row.special_shape_drawing_json || "").trim());
        return `
            <div class="dco-shape-builder" data-readonly="${readOnly ? "1" : "0"}">
                <aside class="dco-shape-templates">
                    <div class="dco-shape-side-heading">اختر الشكل الأقرب</div>
                    <div class="dco-shape-side-hint">اختيار القالب يرسم الدرفة فورًا. بعد ذلك حرّك الزوايا أو أدخل مواقعها بالأرقام.</div>
                    <div class="dco-shape-template-list">
                        ${TEMPLATES.map(item => `
                            <button type="button" class="dco-shape-template" data-template="${item.key}">
                                <span class="dco-shape-template-icon">${item.icon}</span>
                                <span><strong>${item.label}</strong><small>${item.hint}</small></span>
                            </button>`).join("")}
                    </div>
                    <div class="dco-shape-legacy-card">
                        <b>الرسم الحر للتوضيح فقط</b><br>
                        استخدمه لكتابة تعليمات أو رسم تفصيل لا يدخل في مسار القص.
                        <button type="button" class="dco-shape-secondary dco-open-legacy">${hasLegacy ? "فتح الرسم التوضيحي" : "إضافة رسم توضيحي"}</button>
                    </div>
                </aside>
                <main class="dco-shape-workspace">
                    <div class="dco-shape-topbar">
                        <div class="dco-shape-meta">
                            <span class="dco-shape-pill">الدرفة <b>#${esc(row.idx || row.piece_no || "—")}</b></span>
                            <span class="dco-shape-pill">الخام <b dir="ltr">${esc(dimensions.width)} × ${esc(dimensions.length)} سم</b></span>
                            <span class="dco-shape-pill dco-shape-status">بانتظار اختيار الشكل</span>
                        </div>
                        ${readOnly ? "" : `
                            <div class="dco-shape-toolbar">
                                <button type="button" class="dco-shape-tool dco-shape-undo">↶ تراجع</button>
                                <button type="button" class="dco-shape-tool dco-shape-redo">↷ إعادة</button>
                                <button type="button" class="dco-shape-tool dco-shape-reset">إعادة القالب</button>
                            </div>`}
                    </div>
                    <div class="dco-shape-canvas-wrap">
                        <svg class="dco-shape-canvas" role="img" aria-label="الشكل الهندسي الحقيقي للدرفة الخاصة"></svg>
                        <div class="dco-shape-empty"><b>اختر شكلًا من القائمة</b><span>سيظهر هنا بالحجم النسبي الصحيح. القيم التي تدخلها بالسنتيمتر هي التي تصنع مسار القص.</span></div>
                    </div>
                </main>
                <aside class="dco-shape-inspector">
                    <div class="dco-shape-card">
                        <div class="dco-shape-card-title">الزاوية المحددة</div>
                        <div class="dco-shape-card-body dco-shape-point-editor"></div>
                    </div>
                    <div class="dco-shape-card">
                        <div class="dco-shape-card-title">فحص الشكل</div>
                        <div class="dco-shape-card-body">
                            <div class="dco-shape-validation"></div>
                            <div class="dco-shape-stats">
                                <div class="dco-shape-stat"><b class="dco-shape-stat-vertices">0</b><span>عدد الزوايا</span></div>
                                <div class="dco-shape-stat"><b class="dco-shape-stat-area">0</b><span>المساحة النهائية م²</span></div>
                            </div>
                        </div>
                    </div>
                    <div class="dco-shape-card">
                        <div class="dco-shape-card-title">طريقة العمل</div>
                        <div class="dco-shape-card-body dco-shape-guide">
                            <ol>
                                <li>اختر القالب الأقرب.</li>
                                <li>اسحب أي زاوية أو أدخل بعدها من اليسار والأعلى.</li>
                                <li>اضغط علامة <b>+</b> على أي ضلع لإضافة زاوية.</li>
                                <li>احفظ عندما تصبح حالة الشكل «جاهز للقص».</li>
                            </ol>
                        </div>
                    </div>
                    ${readOnly ? "" : `<button type="button" class="dco-shape-secondary is-danger dco-remove-geometry">حذف مسار القص الهندسي</button>`}
                    ${hasLegacy ? `<button type="button" class="dco-shape-secondary dco-view-legacy">عرض الرسم التوضيحي القديم</button>` : ""}
                </aside>
            </div>`;
    }

    function scaledGeometry(parsed, width, length) {
        if (!parsed || !parsed.blank_width_cm || !parsed.blank_length_cm) return null;
        return geometry.create(
            parsed.template,
            width,
            length,
            parsed.points.map(point => [
                geometry.rounded(point[0] * width / parsed.blank_width_cm),
                geometry.rounded(point[1] * length / parsed.blank_length_cm),
            ])
        );
    }

    function snapshot(state) {
        state.undo.push({ points: clone(state.points), template: state.template });
        if (state.undo.length > 60) state.undo.shift();
        state.redo = [];
        state.hasChanges = true;
    }

    function restore(state, value) {
        state.points = clone(value.points);
        state.template = value.template;
        if (state.selectedIndex >= state.points.length) state.selectedIndex = state.points.length - 1;
        state.hasChanges = true;
        render(state);
    }

    function validation(state) {
        if (!state.points.length) {
            return { valid: false, errors: ["اختر قالبًا أو ابدأ شكلًا بالنقاط."] };
        }
        return geometry.validate(
            geometry.create(state.template, state.width, state.length, state.points),
            state.width,
            state.length
        );
    }

    function svgPoint(state, event) {
        try {
            const point = state.svg.createSVGPoint();
            point.x = Number(event.clientX);
            point.y = Number(event.clientY);
            const transformed = point.matrixTransform(state.svg.getScreenCTM().inverse());
            return {
                x: geometry.clamp(transformed.x, 0, state.width),
                y: geometry.clamp(transformed.y, 0, state.length),
            };
        } catch (error) {
            const rect = state.svg.getBoundingClientRect();
            return {
                x: geometry.clamp((Number(event.clientX) - rect.left) / Math.max(1, rect.width) * state.width, 0, state.width),
                y: geometry.clamp((Number(event.clientY) - rect.top) / Math.max(1, rect.height) * state.length, 0, state.length),
            };
        }
    }

    function snapValue(value, maximum, candidates) {
        value = geometry.rounded(value, 1);
        const threshold = Math.max(0.35, maximum * 0.012);
        const anchors = [0, maximum, maximum / 2, ...(candidates || [])];
        const nearest = anchors.reduce((best, candidate) => (
            Math.abs(candidate - value) < Math.abs(best - value) ? candidate : best
        ), value);
        return Math.abs(nearest - value) <= threshold ? geometry.rounded(nearest) : value;
    }

    function snappedPoint(state, point, index) {
        const others = state.points.filter((_, pointIndex) => pointIndex !== index);
        return [
            snapValue(point.x, state.width, others.map(item => item[0])),
            snapValue(point.y, state.length, others.map(item => item[1])),
        ];
    }

    function edgeLabels(state) {
        if (state.points.length > 10) return "";
        return state.points.map((point, index) => {
            const next = state.points[(index + 1) % state.points.length];
            const x = (point[0] + next[0]) / 2;
            const y = (point[1] + next[1]) / 2;
            const label = geometry.edgeLength(point, next);
            const width = Math.max(9, String(label).length * 2.2 + 4);
            return `<g class="dco-shape-edge-label" transform="translate(${x} ${y})">
                <rect x="${-width / 2}" y="-3.3" width="${width}" height="6.6" rx="2"/>
                <text x="0" y=".2">${label}</text>
            </g>`;
        }).join("");
    }

    function helperMarkup(state) {
        const point = state.points[state.selectedIndex];
        if (!point || state.readOnly) return "";
        return `
            <path class="dco-shape-helper" d="M0 ${point[1]}H${point[0]}V0"/>
            <text class="dco-shape-dimension-text" x="${Math.max(4, point[0] / 2)}" y="${Math.max(5, point[1] - 2)}">${geometry.rounded(point[0], 1)} سم</text>
            <text class="dco-shape-dimension-text" x="${Math.max(5, point[0] + 3)}" y="${Math.max(5, point[1] / 2)}">${geometry.rounded(point[1], 1)} سم</text>`;
    }

    function canvasMarkup(state) {
        if (!state.points.length) return "";
        const margin = Math.max(8, Math.max(state.width, state.length) * 0.12);
        const grid = Math.max(1, Math.round(Math.max(state.width, state.length) / 12));
        const polygon = state.points.map(point => `${point[0]},${point[1]}`).join(" ");
        const showEdgeAdd = !state.readOnly && state.points.length <= 12;
        const showVertexLabels = state.points.length <= 12;
        const edges = state.points.map((point, index) => {
            const next = state.points[(index + 1) % state.points.length];
            const middle = [(point[0] + next[0]) / 2, (point[1] + next[1]) / 2];
            return `
                <line class="dco-shape-edge" x1="${point[0]}" y1="${point[1]}" x2="${next[0]}" y2="${next[1]}"/>
                ${showEdgeAdd ? `
                    <line class="dco-shape-edge-hit" data-edge-index="${index}" x1="${point[0]}" y1="${point[1]}" x2="${next[0]}" y2="${next[1]}"/>
                    <circle class="dco-shape-edge-add" data-edge-index="${index}" cx="${middle[0]}" cy="${middle[1]}" r="3.1"/>
                    <text class="dco-shape-edge-plus" x="${middle[0]}" y="${middle[1]}">+</text>` : ""}`;
        }).join("");
        const vertices = state.points.map((point, index) => `
            <circle class="dco-shape-vertex ${index === state.selectedIndex ? "is-selected" : ""}" data-vertex-index="${index}" cx="${point[0]}" cy="${point[1]}" r="${index === state.selectedIndex ? 4.2 : (showVertexLabels ? 3.5 : 2.2)}"/>
            ${showVertexLabels ? `<text class="dco-shape-vertex-label" x="${point[0]}" y="${point[1]}">${index + 1}</text>` : ""}
        `).join("");
        state.svg.setAttribute("viewBox", `${-margin} ${-margin} ${state.width + margin * 2} ${state.length + margin * 2}`);
        state.svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
        return `
            <defs>
                <pattern id="dco-shape-grid" width="${grid}" height="${grid}" patternUnits="userSpaceOnUse">
                    <path d="M${grid} 0H0V${grid}" fill="none" stroke="#e8edf1" stroke-width=".6"/>
                </pattern>
                <marker id="dco-shape-arrow" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto-start-reverse">
                    <path d="M6,0L0,3L6,6" fill="none" stroke="#536779" stroke-width="1"/>
                </marker>
            </defs>
            <rect class="dco-shape-blank" x="0" y="0" width="${state.width}" height="${state.length}"/>
            <line class="dco-shape-dimension" x1="0" y1="${-margin * .46}" x2="${state.width}" y2="${-margin * .46}" marker-start="url(#dco-shape-arrow)" marker-end="url(#dco-shape-arrow)"/>
            <text class="dco-shape-dimension-text" x="${state.width / 2}" y="${-margin * .58}">${state.width} سم</text>
            <line class="dco-shape-dimension" x1="${-margin * .46}" y1="0" x2="${-margin * .46}" y2="${state.length}" marker-start="url(#dco-shape-arrow)" marker-end="url(#dco-shape-arrow)"/>
            <text class="dco-shape-dimension-text" transform="translate(${-margin * .62} ${state.length / 2}) rotate(-90)" x="0" y="0">${state.length} سم</text>
            <polygon class="dco-shape-polygon" points="${polygon}"/>
            ${edges}
            ${edgeLabels(state)}
            ${helperMarkup(state)}
            ${vertices}`;
    }

    function pointEditorHtml(state) {
        const point = state.points[state.selectedIndex];
        if (!point) {
            return `<div class="dco-shape-selected-empty">${state.points.length ? "اضغط على إحدى دوائر الزوايا لتحديدها." : "اختر شكلًا أولًا، ثم حدد زاوية لتعديلها."}</div>`;
        }
        if (state.readOnly) {
            return `<div class="dco-shape-selected-empty">الزاوية ${state.selectedIndex + 1}<br><b>${geometry.rounded(point[0], 1)} سم من اليسار</b><br><b>${geometry.rounded(point[1], 1)} سم من الأعلى</b></div>`;
        }
        return `
            <div class="dco-shape-input-grid">
                <div class="dco-shape-input">
                    <label>المسافة من اليسار</label>
                    <div class="dco-shape-input-shell"><input type="number" min="0" max="${state.width}" step=".1" data-point-axis="x" value="${geometry.rounded(point[0], 1)}"><span>سم</span></div>
                </div>
                <div class="dco-shape-input">
                    <label>المسافة من الأعلى</label>
                    <div class="dco-shape-input-shell"><input type="number" min="0" max="${state.length}" step=".1" data-point-axis="y" value="${geometry.rounded(point[1], 1)}"><span>سم</span></div>
                </div>
            </div>
            <div class="dco-shape-point-actions">
                <button type="button" data-snap-point="left">إلى اليسار</button>
                <button type="button" data-snap-point="right">إلى اليمين</button>
                <button type="button" data-snap-point="top">إلى الأعلى</button>
                <button type="button" data-snap-point="bottom">إلى الأسفل</button>
                <button type="button" class="is-danger dco-delete-point">حذف الزاوية</button>
            </div>`;
    }

    function render(state) {
        state.svg.innerHTML = canvasMarkup(state);
        const empty = state.root.querySelector(".dco-shape-empty");
        if (empty) empty.style.display = state.points.length ? "none" : "";

        state.root.querySelectorAll(".dco-shape-template").forEach(button => {
            button.classList.toggle("is-active", button.dataset.template === state.template);
        });
        const pointEditor = state.root.querySelector(".dco-shape-point-editor");
        if (pointEditor) pointEditor.innerHTML = pointEditorHtml(state);

        const check = validation(state);
        const checkBox = state.root.querySelector(".dco-shape-validation");
        if (checkBox) {
            checkBox.classList.toggle("is-valid", check.valid);
            checkBox.innerHTML = check.valid
                ? "<b>✓ جاهز للقص</b>المسار مغلق، غير متقاطع، ومطابق لمقاس الخام."
                : `<b>راجع الشكل</b>${check.errors.map(error => `<div>• ${esc(error)}</div>`).join("")}`;
        }
        state.root.querySelector(".dco-shape-stat-vertices").textContent = state.points.length;
        state.root.querySelector(".dco-shape-stat-area").textContent = geometry.rounded(geometry.area(state.points) / 10000, 3);

        const status = state.root.querySelector(".dco-shape-status");
        status.classList.toggle("is-valid", check.valid);
        status.classList.toggle("is-dirty", state.hasChanges);
        status.textContent = check.valid
            ? (state.hasChanges ? "● جاهز — غير محفوظ" : "✓ مسار هندسي محفوظ")
            : "بانتظار اكتمال الشكل";

        if (!state.readOnly) {
            state.root.querySelector(".dco-shape-undo").disabled = !state.undo.length;
            state.root.querySelector(".dco-shape-redo").disabled = !state.redo.length;
            state.root.querySelector(".dco-shape-reset").disabled = !state.template || !state.points.length;
        }
    }

    function chooseTemplate(state, template) {
        snapshot(state);
        state.template = template;
        state.points = geometry.templatePoints(template, state.width, state.length);
        state.selectedIndex = 0;
        render(state);
    }

    function addPointToEdge(state, edgeIndex) {
        if (state.points.length >= geometry.MAX_VERTICES) {
            frappe.msgprint(`الحد الأقصى هو ${geometry.MAX_VERTICES} زاوية.`);
            return;
        }
        const start = state.points[edgeIndex];
        const end = state.points[(edgeIndex + 1) % state.points.length];
        if (!start || !end) return;
        snapshot(state);
        const insertIndex = edgeIndex + 1;
        state.points.splice(insertIndex, 0, [
            geometry.rounded((start[0] + end[0]) / 2, 1),
            geometry.rounded((start[1] + end[1]) / 2, 1),
        ]);
        state.template = "custom";
        state.selectedIndex = insertIndex;
        render(state);
    }

    function deleteSelectedPoint(state) {
        if (state.selectedIndex < 0 || state.points.length <= 3) {
            frappe.msgprint("الشكل يحتاج ثلاث زوايا على الأقل.");
            return;
        }
        snapshot(state);
        state.points.splice(state.selectedIndex, 1);
        state.template = "custom";
        state.selectedIndex = Math.min(state.selectedIndex, state.points.length - 1);
        render(state);
    }

    function updateSelectedPoint(state, x, y) {
        if (!state.points[state.selectedIndex]) return;
        snapshot(state);
        state.points[state.selectedIndex] = [
            geometry.clamp(geometry.rounded(x, 1), 0, state.width),
            geometry.clamp(geometry.rounded(y, 1), 0, state.length),
        ];
        state.template = "custom";
        render(state);
    }

    function openLegacy(state, readOnly = false) {
        const launch = () => {
            state.allowClose = true;
            state.dialog.hide();
            if (readOnly) legacyEditor.view(state.frm, state.row);
            else legacyEditor.open(state.frm, state.row);
        };
        if (!state.hasChanges) {
            launch();
            return;
        }
        frappe.confirm("لديك تعديل غير محفوظ في المسار الهندسي. هل تريد فتح الرسم التوضيحي وفقدان هذا التعديل؟", launch);
    }

    function bind(state) {
        state.root.addEventListener("click", event => {
            const template = event.target.closest && event.target.closest(".dco-shape-template");
            if (template && !state.readOnly) {
                chooseTemplate(state, template.dataset.template);
                return;
            }
            const edge = event.target.closest && event.target.closest("[data-edge-index]");
            if (edge && !state.readOnly) {
                addPointToEdge(state, Number(edge.dataset.edgeIndex));
                return;
            }
            const vertex = event.target.closest && event.target.closest("[data-vertex-index]");
            if (vertex) {
                state.selectedIndex = Number(vertex.dataset.vertexIndex);
                render(state);
                return;
            }
            if (event.target.closest && event.target.closest(".dco-delete-point")) {
                deleteSelectedPoint(state);
                return;
            }
            const snap = event.target.closest && event.target.closest("[data-snap-point]");
            if (snap) {
                const point = state.points[state.selectedIndex];
                if (!point) return;
                const values = {
                    left: [0, point[1]],
                    right: [state.width, point[1]],
                    top: [point[0], 0],
                    bottom: [point[0], state.length],
                }[snap.dataset.snapPoint];
                updateSelectedPoint(state, values[0], values[1]);
                return;
            }
            if (event.target.closest && event.target.closest(".dco-open-legacy")) {
                openLegacy(state, false);
                return;
            }
            if (event.target.closest && event.target.closest(".dco-view-legacy")) {
                openLegacy(state, true);
            }
        });

        state.root.addEventListener("change", event => {
            const input = event.target.closest && event.target.closest("[data-point-axis]");
            if (!input || state.readOnly) return;
            const point = state.points[state.selectedIndex];
            if (!point) return;
            updateSelectedPoint(
                state,
                input.dataset.pointAxis === "x" ? num(input.value) : point[0],
                input.dataset.pointAxis === "y" ? num(input.value) : point[1]
            );
        });
        state.root.addEventListener("focusin", event => {
            if (event.target.matches && event.target.matches("[data-point-axis]")) event.target.select();
        });

        if (!state.readOnly) {
            state.root.querySelector(".dco-shape-undo").addEventListener("click", () => {
                if (!state.undo.length) return;
                state.redo.push({ points: clone(state.points), template: state.template });
                restore(state, state.undo.pop());
            });
            state.root.querySelector(".dco-shape-redo").addEventListener("click", () => {
                if (!state.redo.length) return;
                state.undo.push({ points: clone(state.points), template: state.template });
                restore(state, state.redo.pop());
            });
            state.root.querySelector(".dco-shape-reset").addEventListener("click", () => {
                if (!state.template) return;
                chooseTemplate(state, state.template);
            });
            state.root.querySelector(".dco-remove-geometry").addEventListener("click", () => {
                if (!state.row.special_shape_geometry_json) {
                    frappe.show_alert({ message: "لا يوجد مسار هندسي محفوظ لحذفه.", indicator: "blue" });
                    return;
                }
                frappe.confirm("هل تريد حذف مسار القص الهندسي؟ سيبقى الرسم التوضيحي القديم إن وجد.", () => {
                    state.row.special_shape_geometry_json = "";
                    state.row.special_shape_status = String(state.row.special_shape_drawing_json || "").trim()
                        ? "Documented"
                        : "Needs Documentation";
                    state.frm.dirty();
                    state.allowClose = true;
                    state.dialog.hide();
                    refreshFastTable(state.frm);
                });
            });
        }

        state.svg.addEventListener("pointerdown", event => {
            if (state.readOnly) return;
            const vertex = event.target.closest && event.target.closest("[data-vertex-index]");
            if (!vertex) return;
            state.selectedIndex = Number(vertex.dataset.vertexIndex);
            state.originalTemplateBeforeDrag = state.template;
            state.dragging = {
                pointerId: event.pointerId,
                original: clone(state.points),
                moved: false,
            };
            state.svg.setPointerCapture(event.pointerId);
            event.preventDefault();
        });
        state.svg.addEventListener("pointermove", event => {
            if (!state.dragging || event.pointerId !== state.dragging.pointerId) return;
            const point = snappedPoint(state, svgPoint(state, event), state.selectedIndex);
            const current = state.points[state.selectedIndex];
            state.dragging.moved = state.dragging.moved || !current
                || Math.hypot(point[0] - current[0], point[1] - current[1]) > 0.05;
            state.points[state.selectedIndex] = point;
            state.template = "custom";
            state.hasChanges = true;
            render(state);
            event.preventDefault();
        });
        const finishDrag = event => {
            if (!state.dragging || event.pointerId !== state.dragging.pointerId) return;
            if (state.dragging.moved) {
                state.undo.push({
                    points: state.dragging.original,
                    template: state.originalTemplateBeforeDrag || state.template,
                });
                if (state.undo.length > 60) state.undo.shift();
                state.redo = [];
            } else {
                state.points = state.dragging.original;
            }
            state.dragging = null;
            state.originalTemplateBeforeDrag = "";
            try { state.svg.releasePointerCapture(event.pointerId); } catch (error) { /* already released */ }
            render(state);
        };
        state.svg.addEventListener("pointerup", finishDrag);
        state.svg.addEventListener("pointercancel", finishDrag);

        state.dialog.$wrapper.on("hide.bs.modal.dco-special-geometry-guard", event => {
            if (!state.hasChanges || state.allowClose || state.readOnly) return;
            event.preventDefault();
            frappe.confirm("لديك تعديلات هندسية لم تحفظ بعد. هل تريد الإغلاق وفقدانها؟", () => {
                state.allowClose = true;
                state.dialog.hide();
            });
        });
    }

    function refreshFastTable(frm) {
        if (window.AlmdinaDoorCuttingFastEntry && window.AlmdinaDoorCuttingFastEntry.render) {
            window.AlmdinaDoorCuttingFastEntry.render(frm);
        }
    }

    function save(state) {
        const payload = geometry.create(state.template, state.width, state.length, state.points);
        const check = geometry.validate(payload, state.width, state.length);
        if (!check.valid) {
            frappe.msgprint({
                title: "راجع الشكل قبل الحفظ",
                message: check.errors.map(error => `• ${esc(error)}`).join("<br>"),
                indicator: "orange",
            });
            return;
        }
        state.row.special_shape_geometry_json = geometry.serialize(payload);
        state.row.special_shape_status = "Documented";
        state.frm.dirty();
        state.hasChanges = false;
        state.allowClose = true;
        Promise.resolve(
            state.frm.script_manager.trigger("piece_type", state.row.doctype, state.row.name)
        ).catch(error => console.error(error));
        state.dialog.hide();
        refreshFastTable(state.frm);
        frappe.show_alert({
            message: state.row.special_shape_price_status === "Approved"
                ? "تم حفظ المسار الهندسي. سيلغى اعتماد السعر السابق عند حفظ الطلب لأن الشكل تغيّر."
                : "تم حفظ مسار القص الحقيقي وسيظهر في خطة القص وDXF.",
            indicator: state.row.special_shape_price_status === "Approved" ? "orange" : "green",
        }, 6);
    }

    function open(frm, row, options = {}) {
        if ((row.piece_type || "Regular") !== "Special") {
            frappe.msgprint("حوّل نوع الدرفة إلى «خاصة» أولًا.");
            return;
        }
        const dimensions = pieceDimensions(row);
        if (dimensions.width <= 0 || dimensions.length <= 0) {
            frappe.msgprint("أدخل عرض الدرفة وطولها أولًا، ثم افتح بناء الشكل.");
            return;
        }

        const readOnly = Boolean(options.readOnly);
        const existing = geometry.fromPiece(row);
        if (readOnly && !existing) {
            if (row.special_shape_drawing_json) legacyEditor.view(frm, row);
            else frappe.msgprint("لا يوجد مسار هندسي أو رسم توضيحي لهذه الدرفة.");
            return;
        }

        installStyles();
        const dialog = new frappe.ui.Dialog({
            title: readOnly
                ? `مسار الدرفة الخاصة رقم ${row.idx || row.piece_no || ""}`
                : `بناء الدرفة الخاصة رقم ${row.idx || row.piece_no || ""}`,
            size: "extra-large",
            fields: [{
                fieldname: "special_shape_builder",
                fieldtype: "HTML",
                options: shellHtml(row, readOnly),
            }],
            primary_action_label: readOnly ? "إغلاق" : "اعتماد مسار القص",
            primary_action() {
                readOnly ? dialog.hide() : save(state);
            },
        });
        dialog.$wrapper.addClass("dco-special-shape-modal dco-special-geometry-modal");
        dialog.show();

        const root = dialog.fields_dict.special_shape_builder.$wrapper
            .find(".dco-shape-builder").get(0);
        if (!root) {
            dialog.hide();
            frappe.msgprint("تعذر تجهيز محرر الشكل. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            return;
        }

        let initial = existing;
        let resized = false;
        if (
            existing
            && (
                Math.abs(existing.blank_width_cm - dimensions.width) > 0.001
                || Math.abs(existing.blank_length_cm - dimensions.length) > 0.001
            )
        ) {
            initial = scaledGeometry(existing, dimensions.width, dimensions.length);
            resized = true;
        }

        const state = {
            frm,
            row,
            dialog,
            root,
            svg: root.querySelector(".dco-shape-canvas"),
            width: dimensions.width,
            length: dimensions.length,
            points: initial ? clone(initial.points) : [],
            template: initial ? initial.template : "",
            selectedIndex: initial && initial.points.length ? 0 : -1,
            undo: [],
            redo: [],
            dragging: null,
            originalTemplateBeforeDrag: "",
            readOnly,
            hasChanges: resized,
            allowClose: false,
        };
        bind(state);
        render(state);
        if (resized) {
            frappe.show_alert({
                message: "تمت ملاءمة الشكل مع مقاس الدرفة الجديد. راجعه ثم احفظه.",
                indicator: "orange",
            }, 6);
        }
    }

    window.AlmdinaLegacySpecialShapeEditor = legacyEditor;
    window.AlmdinaSpecialShapeEditor = Object.freeze({
        open,
        view(frm, row) {
            if (geometry.fromPiece(row)) open(frm, row, { readOnly: true });
            else legacyEditor.view(frm, row);
        },
        legacy: legacyEditor,
    });
})();
