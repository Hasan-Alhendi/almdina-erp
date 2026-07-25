(() => {
    "use strict";

    const CANVAS_WIDTH = 1000;
    const CANVAS_HEIGHT = 650;
    const COLORS = ["#172033", "#c2352a", "#1769aa"];
    const TOOLS = [
        { key: "pen", icon: "✎", label: "قلم حر", hint: "ارسم الشكل بيدك" },
        { key: "line", icon: "╱", label: "خط", hint: "خط مستقيم" },
        { key: "rectangle", icon: "□", label: "مستطيل", hint: "شكل مستطيل" },
        { key: "ellipse", icon: "○", label: "دائرة", hint: "دائرة أو بيضاوي" },
        { key: "dimension", icon: "↔", label: "قياس", hint: "سهم مع قيمة حقيقية" },
        { key: "note", icon: "T", label: "ملاحظة", hint: "اكتب ملاحظة على الرسم" },
        { key: "eraser", icon: "⌫", label: "ممحاة", hint: "اضغط على أي عنصر لحذفه" },
    ];
    let sequence = 0;

    function esc(value) {
        return frappe.utils.escape_html(String(value ?? ""));
    }

    function escAttr(value) {
        return esc(value).replace(/`/g, "&#96;");
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

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
            .dco-special-sketch-shell{direction:rtl;display:grid;grid-template-columns:170px minmax(0,1fr) 230px;min-height:690px;color:var(--text-color,#172033)}
            .dco-sketch-toolbar{padding:14px 12px;background:var(--card-bg,#fff);border-left:1px solid var(--border-color,#e1e6eb);display:flex;flex-direction:column;gap:7px}
            .dco-sketch-toolbar-title{font-size:11px;color:var(--text-muted,#6c7680);font-weight:800;margin:2px 4px 5px}
            .dco-sketch-tool{display:flex;align-items:center;gap:9px;width:100%;min-height:42px;border:1px solid transparent;border-radius:10px;background:transparent;color:inherit;padding:7px 9px;cursor:pointer;text-align:right;transition:.12s ease}
            .dco-sketch-tool:hover{background:var(--subtle-fg,#f6f8fa);border-color:var(--border-color,#e1e6eb)}
            .dco-sketch-tool.is-active{background:rgba(36,144,239,.11);border-color:rgba(36,144,239,.34);color:var(--primary,#1674c5);font-weight:900}
            .dco-sketch-tool-icon{display:grid;place-items:center;width:27px;height:27px;border-radius:8px;background:var(--subtle-fg,#f0f3f5);font-size:17px;font-weight:900;flex:0 0 auto}
            .dco-sketch-tool small{display:block;font-size:9px;font-weight:400;opacity:.64;margin-top:1px}
            .dco-sketch-divider{height:1px;background:var(--border-color,#e4e7ea);margin:5px 0}
            .dco-sketch-history{display:grid;grid-template-columns:1fr 1fr;gap:6px}
            .dco-sketch-icon-button{min-height:38px;border:1px solid var(--border-color,#d8dde2);border-radius:9px;background:var(--card-bg,#fff);cursor:pointer;font-weight:800}
            .dco-sketch-icon-button:hover:not(:disabled){border-color:var(--primary,#2490ef);color:var(--primary,#1674c5)}
            .dco-sketch-icon-button:disabled{opacity:.38;cursor:not-allowed}
            .dco-sketch-colors{display:flex;gap:9px;padding:3px 5px}
            .dco-sketch-color{width:27px;height:27px;border:3px solid var(--card-bg,#fff);border-radius:999px;box-shadow:0 0 0 1px var(--border-color,#cfd6dc);cursor:pointer}
            .dco-sketch-color.is-active{box-shadow:0 0 0 3px rgba(36,144,239,.27)}
            .dco-sketch-center{min-width:0;padding:14px;display:flex;flex-direction:column;gap:10px}
            .dco-sketch-topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:10px 12px;border:1px solid var(--border-color,#e0e5e9);border-radius:12px;background:var(--card-bg,#fff)}
            .dco-sketch-piece-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
            .dco-sketch-meta-pill{display:inline-flex;align-items:center;gap:5px;padding:5px 9px;border-radius:999px;background:var(--subtle-fg,#f2f5f7);font-size:11px}
            .dco-sketch-meta-pill b{font-variant-numeric:tabular-nums}
            .dco-sketch-notice{display:flex;align-items:center;gap:7px;color:#8a5a12;background:#fff7df;border:1px solid #efd89a;border-radius:9px;padding:6px 10px;font-size:10px;font-weight:700}
            .dco-sketch-paper-wrap{position:relative;flex:1;display:grid;place-items:center;min-height:570px;padding:13px;border:1px solid var(--border-color,#d9dfe5);border-radius:15px;background:#e8ecef;overflow:auto}
            .dco-sketch-paper{display:block;width:100%;height:auto;max-height:calc(100vh - 250px);min-height:500px;background:#fff;border-radius:5px;box-shadow:0 9px 28px rgba(28,38,50,.14);touch-action:none;cursor:crosshair;user-select:none}
            .dco-sketch-paper[data-tool="eraser"]{cursor:not-allowed}
            .dco-sketch-paper[data-tool="note"]{cursor:text}
            .dco-sketch-element{pointer-events:all}
            .dco-sketch-note-bg{fill:#fff8c9;stroke:#e5cd62;stroke-width:1.5}
            .dco-sketch-sidebar{padding:14px 13px;background:var(--card-bg,#fff);border-right:1px solid var(--border-color,#e1e6eb);display:flex;flex-direction:column;gap:11px}
            .dco-sketch-side-card{border:1px solid var(--border-color,#e0e5e9);border-radius:12px;overflow:hidden}
            .dco-sketch-side-title{padding:9px 11px;background:var(--subtle-fg,#f7f9fa);font-size:11px;font-weight:900;border-bottom:1px solid var(--border-color,#e5e8eb)}
            .dco-sketch-side-content{padding:10px;max-height:250px;overflow:auto}
            .dco-sketch-empty{padding:12px 5px;text-align:center;color:var(--text-muted,#71808e);font-size:10px;line-height:1.7}
            .dco-sketch-list-item{display:flex;align-items:flex-start;gap:7px;padding:7px 3px;border-bottom:1px solid var(--border-color,#edf0f2);font-size:10px;line-height:1.5}
            .dco-sketch-list-item:last-child{border-bottom:0}
            .dco-sketch-list-badge{display:grid;place-items:center;min-width:22px;height:22px;border-radius:7px;background:rgba(36,144,239,.1);color:var(--primary,#1674c5);font-weight:900}
            .dco-sketch-guide{font-size:10px;line-height:1.75;color:var(--text-muted,#64717d);padding:2px 3px}
            .dco-sketch-guide b{color:var(--text-color,#172033)}
            .dco-sketch-fullscreen-button{border:1px solid var(--border-color,#d8dde2);border-radius:8px;background:var(--card-bg,#fff);min-height:34px;padding:5px 10px;cursor:pointer;font-size:11px;font-weight:800}
            @media(max-width:1050px){.dco-special-sketch-shell{grid-template-columns:145px minmax(0,1fr)}.dco-sketch-sidebar{display:none}}
            @media(max-width:700px){.dco-special-shape-modal .modal-dialog{width:100vw!important;margin:0!important}.dco-special-shape-modal .modal-content{min-height:100vh;border-radius:0}.dco-special-sketch-shell{display:flex;flex-direction:column;min-height:0}.dco-sketch-toolbar{order:2;flex-direction:row;overflow:auto;border:0;border-top:1px solid var(--border-color,#ddd);padding:8px}.dco-sketch-toolbar-title,.dco-sketch-divider,.dco-sketch-colors{display:none}.dco-sketch-tool{min-width:82px;flex-direction:column;justify-content:center;text-align:center}.dco-sketch-tool small{display:none}.dco-sketch-history{display:flex}.dco-sketch-icon-button{min-width:56px}.dco-sketch-center{padding:8px}.dco-sketch-paper-wrap{min-height:430px}.dco-sketch-paper{min-height:410px}}
        `;
        document.head.appendChild(style);
    }

    function shellHtml(row) {
        return `
            <div class="dco-special-sketch-shell">
                <aside class="dco-sketch-toolbar" aria-label="أدوات الرسم">
                    <div class="dco-sketch-toolbar-title">أدوات الورقة</div>
                    ${TOOLS.map(tool => `
                        <button type="button" class="dco-sketch-tool ${tool.key === "pen" ? "is-active" : ""}" data-tool="${tool.key}">
                            <span class="dco-sketch-tool-icon" aria-hidden="true">${tool.icon}</span>
                            <span>${tool.label}<small>${tool.hint}</small></span>
                        </button>`).join("")}
                    <div class="dco-sketch-divider"></div>
                    <div class="dco-sketch-toolbar-title">لون القلم</div>
                    <div class="dco-sketch-colors">
                        ${COLORS.map((color, index) => `<button type="button" class="dco-sketch-color ${index === 0 ? "is-active" : ""}" data-color="${color}" style="background:${color}" title="اختيار اللون"></button>`).join("")}
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
                        </div>
                        <div style="display:flex;align-items:center;gap:8px">
                            <div class="dco-sketch-notice"><span>!</span><span>رسم توثيقي للمصمم، وليس ملف CNC</span></div>
                            <button type="button" class="dco-sketch-fullscreen-button">⛶ ملء الشاشة</button>
                        </div>
                    </div>
                    <div class="dco-sketch-paper-wrap">
                        <svg class="dco-sketch-paper" data-tool="pen" viewBox="0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}" role="img" aria-label="ورقة رسم الدرفة الخاصة"></svg>
                    </div>
                </main>
                <aside class="dco-sketch-sidebar">
                    <div class="dco-sketch-side-card">
                        <div class="dco-sketch-side-title">القياسات المكتوبة</div>
                        <div class="dco-sketch-side-content dco-sketch-dimensions"></div>
                    </div>
                    <div class="dco-sketch-side-card">
                        <div class="dco-sketch-side-title">الملاحظات على الرسم</div>
                        <div class="dco-sketch-side-content dco-sketch-notes"></div>
                    </div>
                    <div class="dco-sketch-guide">
                        <b>طريقة سريعة:</b><br>
                        1. ارسم الشكل بالقلم.<br>
                        2. استخدم «قياس» وارسم سهمًا.<br>
                        3. اكتب القيمة الحقيقية مثل 85 سم.<br>
                        4. ضع ملاحظات المصمم على الورقة.<br><br>
                        لا يشترط أن يكون الرسم متناسبًا؛ القياسات المكتوبة هي المرجع.
                    </div>
                </aside>
            </div>`;
    }

    function pathData(points) {
        return (points || []).map((point, index) =>
            `${index ? "L" : "M"} ${Number(point[0]).toFixed(1)} ${Number(point[1]).toFixed(1)}`
        ).join(" ");
    }

    function textPosition(element) {
        const x = (Number(element.x1) + Number(element.x2)) / 2;
        const y = (Number(element.y1) + Number(element.y2)) / 2;
        return { x, y: y - 12 };
    }

    function elementMarkup(element, draft = false) {
        const color = escAttr(element.color || "#172033");
        const common = `data-element-id="${escAttr(element.id)}" class="dco-sketch-element" opacity="${draft ? ".55" : "1"}"`;
        if (element.type === "pen") {
            return `<path ${common} d="${pathData(element.points)}" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>`;
        }
        if (element.type === "line") {
            return `<line ${common} x1="${element.x1}" y1="${element.y1}" x2="${element.x2}" y2="${element.y2}" stroke="${color}" stroke-width="4" stroke-linecap="round"/>`;
        }
        if (element.type === "rectangle") {
            return `<rect ${common} x="${element.x}" y="${element.y}" width="${element.width}" height="${element.height}" rx="2" fill="none" stroke="${color}" stroke-width="4"/>`;
        }
        if (element.type === "ellipse") {
            return `<ellipse ${common} cx="${element.cx}" cy="${element.cy}" rx="${element.rx}" ry="${element.ry}" fill="none" stroke="${color}" stroke-width="4"/>`;
        }
        if (element.type === "dimension") {
            const position = textPosition(element);
            return `<g ${common}>
                <line x1="${element.x1}" y1="${element.y1}" x2="${element.x2}" y2="${element.y2}" stroke="${color}" stroke-width="2.5" marker-start="url(#dco-arrow-start)" marker-end="url(#dco-arrow-end)"/>
                <rect x="${position.x - Math.max(34, String(element.text || "").length * 7)}" y="${position.y - 18}" width="${Math.max(68, String(element.text || "").length * 14)}" height="27" rx="6" fill="#fff" stroke="${color}" stroke-width="1.2"/>
                <text x="${position.x}" y="${position.y + 1}" text-anchor="middle" font-family="Tahoma,Arial" font-size="17" font-weight="700" fill="${color}">${esc(element.text)}</text>
            </g>`;
        }
        if (element.type === "note") {
            const text = String(element.text || "");
            const displayText = text.length > 34 ? `${text.slice(0, 33)}…` : text;
            const width = Math.min(330, Math.max(120, displayText.length * 9));
            return `<g ${common}>
                <rect class="dco-sketch-note-bg" x="${element.x}" y="${element.y - 31}" width="${width}" height="42" rx="8"/>
                <text x="${Number(element.x) + 10}" y="${Number(element.y) - 5}" font-family="Tahoma,Arial" font-size="16" font-weight="700" fill="#4c421a">${esc(displayText)}</text>
            </g>`;
        }
        return "";
    }

    function renderCanvas(state) {
        const items = state.elements.map(element => elementMarkup(element)).join("");
        const draft = state.draft ? elementMarkup(state.draft, true) : "";
        state.svg.innerHTML = `
            <defs>
                <pattern id="dco-small-grid" width="20" height="20" patternUnits="userSpaceOnUse">
                    <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#edf0f2" stroke-width="1"/>
                </pattern>
                <pattern id="dco-grid" width="100" height="100" patternUnits="userSpaceOnUse">
                    <rect width="100" height="100" fill="url(#dco-small-grid)"/>
                    <path d="M 100 0 L 0 0 0 100" fill="none" stroke="#d7dde2" stroke-width="1.5"/>
                </pattern>
                <marker id="dco-arrow-start" markerWidth="9" markerHeight="9" refX="4.5" refY="4.5" orient="auto-start-reverse">
                    <path d="M9,0 L0,4.5 L9,9" fill="none" stroke="#172033" stroke-width="1.5"/>
                </marker>
                <marker id="dco-arrow-end" markerWidth="9" markerHeight="9" refX="4.5" refY="4.5" orient="auto">
                    <path d="M0,0 L9,4.5 L0,9" fill="none" stroke="#172033" stroke-width="1.5"/>
                </marker>
            </defs>
            <rect x="0" y="0" width="${CANVAS_WIDTH}" height="${CANVAS_HEIGHT}" fill="#fff"/>
            <rect x="0" y="0" width="${CANVAS_WIDTH}" height="${CANVAS_HEIGHT}" fill="url(#dco-grid)"/>
            ${items}${draft}`;
        renderSidebar(state);
        state.root.querySelector(".dco-sketch-undo").disabled = state.undo.length === 0;
        state.root.querySelector(".dco-sketch-redo").disabled = state.redo.length === 0;
    }

    function renderSidebar(state) {
        const dimensions = state.elements.filter(element => element.type === "dimension");
        const notes = state.elements.filter(element => element.type === "note");
        const empty = text => `<div class="dco-sketch-empty">${text}</div>`;
        state.root.querySelector(".dco-sketch-dimensions").innerHTML = dimensions.length
            ? dimensions.map((element, index) => `<div class="dco-sketch-list-item"><span class="dco-sketch-list-badge">↔</span><span><b>قياس ${index + 1}</b><br>${esc(element.text)}</span></div>`).join("")
            : empty("لم تضع قياسات بعد.<br>اختر أداة «قياس» وارسم سهمًا.");
        state.root.querySelector(".dco-sketch-notes").innerHTML = notes.length
            ? notes.map((element, index) => `<div class="dco-sketch-list-item"><span class="dco-sketch-list-badge">T</span><span><b>ملاحظة ${index + 1}</b><br>${esc(element.text)}</span></div>`).join("")
            : empty("لا توجد ملاحظات مكتوبة على الرسم.");
    }

    function pointFromEvent(svg, event) {
        const rect = svg.getBoundingClientRect();
        return {
            x: Math.max(0, Math.min(CANVAS_WIDTH, (event.clientX - rect.left) * CANVAS_WIDTH / rect.width)),
            y: Math.max(0, Math.min(CANVAS_HEIGHT, (event.clientY - rect.top) * CANVAS_HEIGHT / rect.height)),
        };
    }

    function snapshot(state) {
        state.undo.push(clone(state.elements));
        if (state.undo.length > 80) state.undo.shift();
        state.redo = [];
    }

    function addElement(state, element) {
        snapshot(state);
        state.elements.push(element);
        state.draft = null;
        renderCanvas(state);
    }

    function removeElement(state, elementId) {
        const index = state.elements.findIndex(element => element.id === elementId);
        if (index < 0) return;
        snapshot(state);
        state.elements.splice(index, 1);
        renderCanvas(state);
    }

    function simplifyPoints(points) {
        if (!points || points.length < 3) return points || [];
        const result = [points[0]];
        for (let index = 1; index < points.length - 1; index += 1) {
            const previous = result[result.length - 1];
            const current = points[index];
            const distance = Math.hypot(current[0] - previous[0], current[1] - previous[1]);
            if (distance >= 2.5) result.push(current);
        }
        result.push(points[points.length - 1]);
        return result;
    }

    function promptText(title, label, defaultValue, callback) {
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
            "إضافة"
        );
    }

    function beginDrawing(state, event) {
        if (event.button !== undefined && event.button !== 0) return;
        const point = pointFromEvent(state.svg, event);

        if (state.tool === "eraser") {
            const target = event.target.closest("[data-element-id]");
            if (target) removeElement(state, target.dataset.elementId);
            return;
        }
        if (state.tool === "note") {
            promptText("إضافة ملاحظة", "اكتب الملاحظة التي يراها المصمم", "", text => {
                if (!text) return;
                addElement(state, {
                    id: id("note"),
                    type: "note",
                    x: point.x,
                    y: point.y,
                    text: text.slice(0, 500),
                    color: state.color,
                });
            });
            return;
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
        if (!state.draft || event.pointerId !== state.pointerId) return;
        const point = pointFromEvent(state.svg, event);
        if (state.draft.type === "pen") {
            state.draft.points.push([point.x, point.y]);
        } else if (state.draft.type === "line" || state.draft.type === "dimension") {
            state.draft.x2 = point.x;
            state.draft.y2 = point.y;
        } else if (state.draft.type === "rectangle") {
            state.draft.x = Math.min(state.start.x, point.x);
            state.draft.y = Math.min(state.start.y, point.y);
            state.draft.width = Math.abs(point.x - state.start.x);
            state.draft.height = Math.abs(point.y - state.start.y);
        } else if (state.draft.type === "ellipse") {
            state.draft.cx = (state.start.x + point.x) / 2;
            state.draft.cy = (state.start.y + point.y) / 2;
            state.draft.rx = Math.abs(point.x - state.start.x) / 2;
            state.draft.ry = Math.abs(point.y - state.start.y) / 2;
        }
        renderCanvas(state);
        event.preventDefault();
    }

    function finishDrawing(state, event) {
        if (!state.draft || event.pointerId !== state.pointerId) return;
        const element = clone(state.draft);
        state.draft = null;
        state.pointerId = null;
        try { state.svg.releasePointerCapture(event.pointerId); } catch (error) { /* pointer already released */ }

        if (element.type === "pen") {
            element.points = simplifyPoints(element.points);
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
            renderCanvas(state);
            return;
        }
        if (element.type === "dimension") {
            renderCanvas(state);
            promptText("إضافة قياس حقيقي", "القيمة مع الوحدة، مثال: 85 سم", " سم", text => {
                if (!text) return;
                element.text = text.slice(0, 500);
                addElement(state, element);
            });
            return;
        }
        addElement(state, element);
    }

    function selectTool(state, tool) {
        state.tool = tool;
        state.svg.dataset.tool = tool;
        state.root.querySelectorAll(".dco-sketch-tool").forEach(button => {
            button.classList.toggle("is-active", button.dataset.tool === tool);
        });
    }

    function undo(state) {
        if (!state.undo.length) return;
        state.redo.push(clone(state.elements));
        state.elements = state.undo.pop();
        renderCanvas(state);
    }

    function redo(state) {
        if (!state.redo.length) return;
        state.undo.push(clone(state.elements));
        state.elements = state.redo.pop();
        renderCanvas(state);
    }

    function bind(state) {
        state.root.querySelectorAll(".dco-sketch-tool").forEach(button => {
            button.addEventListener("click", () => selectTool(state, button.dataset.tool));
        });
        state.root.querySelectorAll(".dco-sketch-color").forEach(button => {
            button.addEventListener("click", () => {
                state.color = button.dataset.color;
                state.root.querySelectorAll(".dco-sketch-color").forEach(item => item.classList.toggle("is-active", item === button));
            });
        });
        state.root.querySelector(".dco-sketch-undo").addEventListener("click", () => undo(state));
        state.root.querySelector(".dco-sketch-redo").addEventListener("click", () => redo(state));
        state.root.querySelector(".dco-sketch-clear").addEventListener("click", () => {
            if (!state.elements.length) return;
            frappe.confirm("هل تريد مسح جميع عناصر الورقة؟", () => {
                snapshot(state);
                state.elements = [];
                renderCanvas(state);
            });
        });
        state.root.querySelector(".dco-sketch-fullscreen-button").addEventListener("click", event => {
            state.dialog.$wrapper.toggleClass("dco-sketch-fullscreen");
            event.currentTarget.textContent = state.dialog.$wrapper.hasClass("dco-sketch-fullscreen")
                ? "× تصغير"
                : "⛶ ملء الشاشة";
        });
        state.svg.addEventListener("pointerdown", event => beginDrawing(state, event));
        state.svg.addEventListener("pointermove", event => continueDrawing(state, event));
        state.svg.addEventListener("pointerup", event => finishDrawing(state, event));
        state.svg.addEventListener("pointercancel", event => finishDrawing(state, event));

        state.keyHandler = event => {
            if (!state.dialog.$wrapper.is(":visible")) return;
            const target = event.target;
            if (target && /INPUT|TEXTAREA|SELECT/.test(target.tagName)) return;
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
                event.preventDefault();
                event.shiftKey ? redo(state) : undo(state);
            } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
                event.preventDefault();
                redo(state);
            }
        };
        document.addEventListener("keydown", state.keyHandler);
        state.dialog.$wrapper.on("hidden.bs.modal.dco-special-shape", () => {
            document.removeEventListener("keydown", state.keyHandler);
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
            title: `ورقة توثيق الدرفة الخاصة رقم ${row.idx || row.piece_no || ""}`,
            size: "extra-large",
            fields: [{
                fieldname: "special_shape_canvas",
                fieldtype: "HTML",
                options: shellHtml(row),
            }],
            primary_action_label: readOnly ? "إغلاق" : "حفظ التوثيق",
            primary_action() {
                readOnly ? dialog.hide() : save(state);
            },
        });
        dialog.$wrapper.addClass("dco-special-shape-modal");
        if (readOnly) dialog.$wrapper.addClass("dco-special-shape-readonly");
        dialog.show();

        const root = dialog.fields_dict.special_shape_canvas.$wrapper
            .find(".dco-special-sketch-shell").get(0);
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
            tool: "pen",
            color: COLORS[0],
            readOnly,
        };
        if (readOnly) {
            root.querySelector(".dco-sketch-toolbar").style.display = "none";
            root.querySelector(".dco-special-sketch-shell").style.gridTemplateColumns = "minmax(0,1fr) 230px";
            state.svg.style.cursor = "default";
            root.querySelector(".dco-sketch-fullscreen-button").addEventListener("click", event => {
                dialog.$wrapper.toggleClass("dco-sketch-fullscreen");
                event.currentTarget.textContent = dialog.$wrapper.hasClass("dco-sketch-fullscreen")
                    ? "× تصغير"
                    : "⛶ ملء الشاشة";
            });
        } else {
            bind(state);
        }
        renderCanvas(state);
    }

    window.AlmdinaSpecialShapeEditor = {
        open,
        view(frm, row) { open(frm, row, { readOnly: true }); },
        parseDrawing,
    };
})();
