(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.ShapeView;
    const G = root.Geometry;
    if (!Base || !G) throw new Error("Door Drawing V3 shape view must load before smart suggestion view");

    function esc(value) {
        const text = String(value ?? "");
        if (window.frappe && frappe.utils && frappe.utils.escape_html) return frappe.utils.escape_html(text);
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function pathD(c, object) {
        const points = (object.geometry.points || []).map(point => Base.worldToScreen(c, point));
        if (!points.length) return "";
        const commands = [`M ${points[0].x} ${points[0].y}`];
        for (let index = 1; index < points.length; index += 1) commands.push(`L ${points[index].x} ${points[index].y}`);
        if (object.geometry.closed) commands.push("Z");
        return commands.join(" ");
    }

    function candidateMarkup(c, candidate) {
        if (!candidate || !candidate.geometry) return "";
        if (candidate.type === "line") {
            const start = Base.worldToScreen(c, candidate.geometry.start);
            const end = Base.worldToScreen(c, candidate.geometry.end);
            return `<line class="ddv3-smart-suggestion-ghost" x1="${start.x}" y1="${start.y}" x2="${end.x}" y2="${end.y}"/>`;
        }
        if (candidate.type === "rectangle") {
            const origin = Base.worldToScreen(c, candidate.geometry.origin);
            const width = candidate.geometry.widthMm * c.viewport.scale;
            const height = candidate.geometry.heightMm * c.viewport.scale;
            return `<rect class="ddv3-smart-suggestion-ghost" x="${origin.x}" y="${origin.y - height}" width="${width}" height="${height}"/>`;
        }
        if (candidate.type === "circle") {
            const center = Base.worldToScreen(c, candidate.geometry.center);
            const radius = candidate.geometry.radiusMm * c.viewport.scale;
            return `<circle class="ddv3-smart-suggestion-ghost" cx="${center.x}" cy="${center.y}" r="${radius}"/>`;
        }
        if (candidate.type === "arc") {
            const start = Base.worldToScreen(c, G.arcStart(candidate));
            const end = Base.worldToScreen(c, G.arcEnd(candidate));
            const radius = candidate.geometry.radiusMm * c.viewport.scale;
            const largeArc = Math.abs(candidate.geometry.sweepAngleDeg) > 180 ? 1 : 0;
            const sweep = candidate.geometry.sweepAngleDeg > 0 ? 0 : 1;
            return `<path class="ddv3-smart-suggestion-ghost" d="M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArc} ${sweep} ${end.x} ${end.y}"/>`;
        }
        if (candidate.type === G.PATH_TYPE) {
            return `<path class="ddv3-smart-suggestion-ghost" d="${pathD(c, candidate)}"/>`;
        }
        return "";
    }

    function insertGhost(c, markup) {
        if (!markup || !c.canvas) return;
        const marker = c.canvas.querySelector(".ddv3-snap-axis-guide, .ddv3-snap-indicator");
        if (marker) marker.insertAdjacentHTML("beforebegin", markup);
        else c.canvas.insertAdjacentHTML("beforeend", markup);
    }

    function ensureHost(c) {
        const workspace = c && c.root && c.root.querySelector(".ddv3-workspace");
        if (!workspace) return null;
        let host = workspace.querySelector(".ddv3-smart-suggestion");
        if (!host) {
            host = document.createElement("div");
            host.className = "ddv3-smart-suggestion";
            host.dir = "rtl";
            host.setAttribute("aria-live", "polite");
            workspace.appendChild(host);
        }
        return host;
    }

    function tunePenCopy(c) {
        const button = c && c.root && c.root.querySelector('[data-ddv3-tool="pen"]');
        if (button) button.title = "القلم الذكي P · يحافظ على رسمك ويعرض التصحيح كاقتراح اختياري";
        const closeLabel = c && c.canvas && c.canvas.querySelector(".ddv3-pen-close-label");
        if (closeLabel) closeLabel.textContent = "إغلاق؟";
    }

    function renderSuggestion(c) {
        const host = ensureHost(c);
        if (!host) return;
        const state = c.smartSuggestion;
        if (!state || !state.suggestion || !state.candidate || c.readOnly) {
            host.hidden = true;
            host.innerHTML = "";
            return;
        }
        insertGhost(c, candidateMarkup(c, state.candidate));
        host.hidden = false;
        host.innerHTML = `<span class="ddv3-smart-suggestion-spark" aria-hidden="true">✦</span><span class="ddv3-smart-suggestion-copy"><b>اقتراح ذكي</b><span>${esc(state.suggestion.label)}</span></span><button type="button" class="ddv3-smart-suggestion-accept" data-ddv3-suggestion-accept>تطبيق</button><button type="button" class="ddv3-smart-suggestion-dismiss" data-ddv3-suggestion-dismiss aria-label="تجاهل الاقتراح" title="تجاهل">×</button>`;
    }

    function render(c) {
        const result = Base.render(c);
        tunePenCopy(c);
        renderSuggestion(c);
        return result;
    }

    root.ShapeView = Object.freeze({ ...Base, render });
    root.SmartSuggestionView = Object.freeze({ candidateMarkup, ensureHost, renderSuggestion, tunePenCopy });
})();
