(() => {
    "use strict";

    const STYLE_ID = "dco-plan-content-layout-css-v3";
    const BOARD_GAP_PX = 12;
    const BOARD_VIEWPORT_HEIGHT_RATIO = 0.68;

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function sectionElement(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        if (!field || !field.$wrapper) return $();
        const section = field.$wrapper.closest(".form-section");
        return section.length ? section : field.$wrapper;
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-optimizer-card > .section-body,
            .dco-optimizer-card .section-body:first-of-type {
                display:flex !important;
                flex-wrap:wrap !important;
                align-items:flex-start !important;
            }
            .dco-plan-action-row {
                flex:0 0 100% !important;
                width:100% !important;
                max-width:100% !important;
                padding:2px 15px 0 !important;
                margin-top:2px !important;
            }
            .dco-plan-action-row > [data-fieldname="plan_control_actions"],
            .dco-plan-action-row > .frappe-control {
                width:100% !important;
                max-width:none !important;
                margin-bottom:0 !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-actions-shell {
                margin:0 !important;
                padding:14px !important;
                border:1px solid var(--border-color,#dfe3e8) !important;
                border-radius:14px !important;
                background:linear-gradient(180deg,rgba(248,250,252,.92),rgba(248,250,252,.55)) !important;
                box-shadow:none !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-actions-title {
                display:flex !important;
                align-items:center !important;
                justify-content:space-between !important;
                gap:12px !important;
                margin-bottom:11px !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-actions-title strong {
                font-size:13px !important;
                font-weight:900 !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-mode-hint {
                max-width:620px;
                padding:5px 9px;
                border-radius:999px;
                background:var(--card-bg,#fff);
                border:1px solid var(--border-color,#e2e8f0);
                font-size:10px !important;
                line-height:1.45 !important;
                color:var(--text-muted,#66717e);
            }
            [data-fieldname="plan_control_actions"] .dco-plan-actions {
                display:grid !important;
                grid-template-columns:repeat(2,minmax(190px,1fr)) !important;
                gap:9px !important;
                width:100% !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-actions > .btn {
                width:100% !important;
                min-width:0 !important;
                min-height:42px !important;
                margin:0 !important;
                border-radius:10px !important;
                font-weight:850 !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-document-actions {
                display:flex !important;
                align-items:center !important;
                gap:8px !important;
                flex-wrap:wrap !important;
                margin-top:11px !important;
                padding-top:11px !important;
                border-top:1px dashed var(--border-color,#dfe3e8) !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-document-actions .btn {
                min-height:36px !important;
                border-radius:9px !important;
                font-weight:800 !important;
                margin:0 !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-note {
                margin-top:10px !important;
                padding-top:9px !important;
                border-top:1px dashed var(--border-color,#dfe3e8) !important;
                color:var(--text-muted,#66717e);
            }
            [data-fieldname="cutting_plan_html"] .dco-plan-tabs {
                width:max-content;
                max-width:100%;
                display:flex !important;
                align-items:center !important;
                gap:4px !important;
                padding:4px !important;
                margin:0 0 12px auto !important;
                border:1px solid var(--border-color,#dfe3e8);
                border-radius:11px;
                background:var(--subtle-fg,#f6f8fa);
            }
            [data-fieldname="cutting_plan_html"] .dco-plan-tabs .btn {
                min-height:34px !important;
                border-radius:8px !important;
                border-color:transparent !important;
                box-shadow:none !important;
                font-weight:800 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-plan-tab-content > .dco-cutting-plan {
                margin-top:0 !important;
                padding-top:0 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-special-raw-coverage {
                margin-top:0 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert {
                display:flex !important;
                align-items:flex-start !important;
                gap:10px !important;
                direction:rtl !important;
                margin:0 0 12px !important;
                padding:11px 12px !important;
                border:1px solid #e0b34c !important;
                border-radius:11px !important;
                background:linear-gradient(135deg,#fff9e8,#fffdf6) !important;
                color:#5f4508 !important;
                box-shadow:none !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__icon {
                flex:0 0 auto;
                font-size:18px !important;
                line-height:1.25 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__body {
                min-width:0;
                flex:1 1 auto;
            }
            [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__title {
                display:block;
                margin-bottom:4px;
                font-size:12px !important;
                font-weight:900 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__note {
                margin:2px 0 0;
                font-size:11px !important;
                font-weight:700 !important;
                line-height:1.65 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__edges {
                display:flex;
                flex-wrap:wrap;
                gap:5px;
                margin-top:7px;
            }
            [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__edge {
                display:inline-flex;
                align-items:center;
                min-height:24px;
                padding:3px 7px;
                border:1px solid rgba(143,103,13,.22);
                border-radius:999px;
                background:rgba(255,255,255,.78);
                font-size:10px !important;
                font-weight:850 !important;
                white-space:nowrap;
            }

            /* Responsive board gallery: screen presentation only. Workshop print
               remains owned by door_cutting_order_cutting_plan_renderer.js. */
            [data-fieldname="cutting_plan_html"] .dco-board-gallery {
                display:grid !important;
                grid-template-columns:1fr;
                gap:${BOARD_GAP_PX}px !important;
                width:100%;
                margin:0;
                padding:0;
                align-items:start;
            }
            [data-fieldname="cutting_plan_html"] .dco-cutting-plan[data-board-columns="2"] .dco-board-gallery {
                grid-template-columns:repeat(2,minmax(0,1fr));
            }
            [data-fieldname="cutting_plan_html"] .dco-cutting-plan[data-board-columns="3"] .dco-board-gallery {
                grid-template-columns:repeat(3,minmax(0,1fr));
            }
            [data-fieldname="cutting_plan_html"] .dco-cutting-plan[data-board-columns="4"] .dco-board-gallery {
                grid-template-columns:repeat(4,minmax(0,1fr));
            }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery > .dco-sheet-card {
                min-width:0 !important;
                width:100% !important;
                max-width:100% !important;
                margin:0 !important;
                padding:9px !important;
                border:1px solid var(--border-color,#dfe3e8) !important;
                border-radius:13px !important;
                background:var(--card-bg,#fff) !important;
                box-shadow:0 3px 12px rgba(24,36,48,.045) !important;
                page-break-inside:avoid;
                break-inside:avoid;
                overflow:hidden;
                transition:border-color .16s ease,box-shadow .16s ease,transform .16s ease;
            }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery > .dco-sheet-card:hover {
                border-color:#b9c3cd !important;
                box-shadow:0 7px 20px rgba(24,36,48,.08) !important;
                transform:translateY(-1px);
            }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-title {
                display:grid !important;
                grid-template-columns:auto minmax(0,1fr) auto;
                align-items:center !important;
                gap:7px !important;
                min-height:31px;
                margin:0 0 7px !important;
                padding:0 1px 7px !important;
                border-bottom:1px solid var(--border-color,#edf0f3);
                font-size:11px !important;
                line-height:1.35 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-title > :first-child {
                font-size:12px !important;
                font-weight:900 !important;
                white-space:nowrap;
            }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-title > :nth-child(2) {
                min-width:0;
                color:var(--text-muted,#68737d);
                font-size:9.5px !important;
                font-weight:750 !important;
                white-space:nowrap;
                overflow:hidden;
                text-overflow:ellipsis;
            }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-board-focus-trigger {
                display:inline-flex;
                align-items:center;
                justify-content:center;
                min-width:31px;
                min-height:29px;
                padding:4px 7px;
                border:1px solid var(--border-color,#dce2e7);
                border-radius:8px;
                background:var(--subtle-fg,#f6f8fa);
                color:var(--text-color,#26313b);
                font-size:10px;
                font-weight:850;
                line-height:1;
                cursor:pointer;
            }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-board-focus-trigger:hover,
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-board-focus-trigger:focus-visible {
                border-color:#9caab6;
                background:var(--card-bg,#fff);
                outline:none;
                box-shadow:0 0 0 2px rgba(80,105,130,.12);
            }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-board {
                width:min(100%,var(--dco-board-screen-max-width,100%)) !important;
                height:auto !important;
                max-width:none !important;
                aspect-ratio:var(--dco-board-aspect,1 / 2) !important;
                margin:0 auto !important;
                background-size:20px 20px !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-piece {
                padding:1px !important;
                font-size:clamp(7px,.62vw,10px) !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-piece-kind-badge {
                padding:1px 3px !important;
                font-size:7px !important;
                line-height:1.2 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-cutting-plan[data-board-columns="4"] .dco-board-gallery .dco-sheet-title > :nth-child(2) {
                font-size:8.5px !important;
            }

            body.dco-board-focus-open { overflow:hidden !important; }
            .dco-board-focus {
                position:fixed;
                inset:0;
                z-index:10050;
                display:grid;
                place-items:center;
                padding:18px;
                background:rgba(20,27,34,.68);
                backdrop-filter:blur(3px);
            }
            .dco-board-focus__dialog {
                width:min(1080px,96vw);
                max-height:94vh;
                display:flex;
                flex-direction:column;
                overflow:hidden;
                border:1px solid rgba(255,255,255,.45);
                border-radius:16px;
                background:var(--card-bg,#fff);
                box-shadow:0 24px 80px rgba(0,0,0,.28);
                direction:rtl;
            }
            .dco-board-focus__header {
                flex:0 0 auto;
                display:flex;
                align-items:center;
                justify-content:space-between;
                gap:12px;
                padding:11px 13px;
                border-bottom:1px solid var(--border-color,#dfe3e8);
            }
            .dco-board-focus__header strong { font-size:13px;font-weight:900; }
            .dco-board-focus__close {
                width:34px;
                height:34px;
                display:inline-grid;
                place-items:center;
                border:1px solid var(--border-color,#dfe3e8);
                border-radius:9px;
                background:var(--subtle-fg,#f6f8fa);
                color:var(--text-color,#202a33);
                font-size:20px;
                line-height:1;
                cursor:pointer;
            }
            .dco-board-focus__body {
                min-height:0;
                flex:1 1 auto;
                overflow:auto;
                display:grid;
                place-items:start center;
                padding:14px;
                background:var(--subtle-fg,#f7f9fb);
            }
            .dco-board-focus .dco-sheet-card {
                width:100% !important;
                max-width:100% !important;
                margin:0 !important;
                padding:10px !important;
                border:0 !important;
                background:transparent !important;
                box-shadow:none !important;
            }
            .dco-board-focus .dco-sheet-title {
                display:flex !important;
                align-items:center !important;
                justify-content:space-between !important;
                gap:12px !important;
                margin:0 0 9px !important;
                font-size:12px !important;
            }
            .dco-board-focus .dco-board-focus-trigger { display:none !important; }
            .dco-board-focus .dco-sheet-board {
                width:var(--dco-focus-board-width,420px) !important;
                height:auto !important;
                max-width:100% !important;
                aspect-ratio:var(--dco-board-aspect,1 / 2) !important;
                margin:0 auto !important;
            }
            .dco-board-focus .dco-piece { font-size:10px !important; }
            .dco-board-focus .dco-piece-kind-badge { font-size:8px !important;padding:2px 5px !important; }

            @media (max-width:760px) {
                .dco-plan-action-row { padding-inline:8px !important; }
                [data-fieldname="plan_control_actions"] .dco-plan-actions {
                    grid-template-columns:1fr !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-actions-title {
                    align-items:flex-start !important;
                    flex-direction:column !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-mode-hint {
                    max-width:100% !important;
                    border-radius:9px !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-document-actions .btn {
                    flex:1 1 180px;
                }
                [data-fieldname="cutting_plan_html"] .dco-plan-tabs {
                    width:100%;
                    margin-inline:0 !important;
                }
                [data-fieldname="cutting_plan_html"] .dco-plan-tabs .btn {
                    flex:1 1 0;
                    min-width:0;
                }
                [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert {
                    gap:8px !important;
                    padding:10px !important;
                }
                [data-fieldname="cutting_plan_html"] .dco-board-gallery > .dco-sheet-card {
                    padding:8px !important;
                }
                [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-title {
                    grid-template-columns:auto minmax(0,1fr) auto;
                }
            }
            @media (max-width:520px) {
                [data-fieldname="plan_control_actions"] .dco-plan-document-actions .btn {
                    flex:1 1 100%;
                    width:100%;
                }
                [data-fieldname="cutting_plan_html"] .dco-plan-tabs {
                    align-items:stretch !important;
                    flex-direction:column !important;
                }
                [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__edges {
                    display:grid !important;
                    grid-template-columns:repeat(2,minmax(0,1fr));
                }
                [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__edge {
                    justify-content:center;
                }
                [data-fieldname="cutting_plan_html"] .dco-board-gallery {
                    gap:10px !important;
                }
                [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-board {
                    width:100% !important;
                }
                [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-title > :nth-child(2) {
                    white-space:normal;
                    line-height:1.45 !important;
                }
                .dco-board-focus { padding:6px; }
                .dco-board-focus__dialog { width:100%;max-height:97vh;border-radius:12px; }
                .dco-board-focus__body { padding:8px; }
            }
        `;
        document.head.appendChild(style);
    }

    function localizePlanSections(frm) {
        if (!isArabic()) return;
        const labels = {
            cut_geometry_section: "إعدادات تنفيذ القص",
            optimizer_section: "محرك خطة القص",
            plan_result_section: "نتيجة الخطة الحالية",
            plan_section: "توزيع القطع على الألواح",
            totals_section: "تفاصيل الحساب والتكلفة",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            if (frm.fields_dict[fieldname]) frm.set_df_property(fieldname, "label", label);
        });
    }

    function movePlanActionsToFullWidth(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        const section = sectionElement(frm, "optimizer_section");
        if (!field || !field.$wrapper || !field.$wrapper.length || !section.length) return;

        const body = section.find(".section-body").first();
        if (!body.length) return;

        let host = body.children(".dco-plan-action-row").first();
        if (!host.length) {
            host = $('<div class="dco-plan-action-row"></div>');
            body.append(host);
        }
        const wrapper = field.$wrapper.get(0);
        if (wrapper && !host.get(0).contains(wrapper)) {
            host.append(field.$wrapper);
        }
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function parsePlanSnapshot(frm) {
        const raw = frm && frm.doc && frm.doc.cutting_plan_json;
        if (!raw) return null;
        if (typeof raw === "object") return raw;
        try {
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === "object" ? parsed : null;
        } catch (error) {
            return null;
        }
    }

    function normalizedMarginNotes(plan) {
        if (!plan || typeof plan !== "object") return [];
        const policy = plan.margin_policy || {};
        const source = Array.isArray(plan.margin_notes)
            ? plan.margin_notes
            : (Array.isArray(policy.notes) ? policy.notes : []);
        return source
            .map(note => String(note || "").trim())
            .filter(Boolean);
    }

    function marginPolicySignature(plan, notes) {
        const policy = (plan && plan.margin_policy) || {};
        return JSON.stringify({
            notes,
            left_mm: policy.left_mm,
            right_mm: policy.right_mm,
            top_mm: policy.top_mm,
            bottom_mm: policy.bottom_mm,
        });
    }

    function marginEdgeBadges(policy) {
        const edges = [
            ["يمين", policy.right_mm],
            ["يسار", policy.left_mm],
            ["أعلى", policy.top_mm],
            ["أسفل", policy.bottom_mm],
        ];
        return edges
            .filter(([, value]) => value !== null && value !== undefined && value !== "")
            .map(([label, value]) => (
                `<span class="dco-margin-policy-alert__edge">${label}: ${escapeHtml(value)} مم</span>`
            ))
            .join("");
    }

    function buildMarginPolicyAlert(plan, notes, signature) {
        const policy = (plan && plan.margin_policy) || {};
        const alert = document.createElement("div");
        alert.className = "dco-margin-policy-alert";
        alert.dataset.marginSignature = signature;
        alert.setAttribute("role", "status");
        alert.setAttribute("aria-live", "polite");
        alert.innerHTML = `
            <span class="dco-margin-policy-alert__icon" aria-hidden="true">⚠</span>
            <div class="dco-margin-policy-alert__body">
                <strong class="dco-margin-policy-alert__title">تنبيه هامش التشذيب</strong>
                ${notes.map(note => `<div class="dco-margin-policy-alert__note">${escapeHtml(note)}</div>`).join("")}
                <div class="dco-margin-policy-alert__edges">${marginEdgeBadges(policy)}</div>
            </div>
        `;
        return alert;
    }

    function ensureMarginPolicyAlert(frm, planRoot) {
        const existing = planRoot.querySelector(":scope > .dco-margin-policy-alert");
        const plan = parsePlanSnapshot(frm);
        const notes = normalizedMarginNotes(plan);
        if (!notes.length) {
            if (existing) existing.remove();
            return;
        }

        const signature = marginPolicySignature(plan, notes);
        if (existing && existing.dataset.marginSignature === signature) return;

        const alert = buildMarginPolicyAlert(plan, notes, signature);
        if (existing) {
            existing.replaceWith(alert);
            return;
        }

        const firstSheet = planRoot.querySelector(":scope > .dco-sheet-card");
        const gallery = planRoot.querySelector(":scope > .dco-board-gallery");
        const anchor = firstSheet || gallery;
        if (anchor) {
            planRoot.insertBefore(alert, anchor);
        } else {
            planRoot.appendChild(alert);
        }
    }

    function desiredBoardColumns(width) {
        const available = Number(width || 0);
        if (available >= 1400) return 4;
        if (available >= 980) return 3;
        if (available >= 620) return 2;
        return 1;
    }

    function boardAspect(board) {
        if (!board) return 0.5;
        const width = parseFloat(board.style.width) || board.clientWidth || 0;
        const height = parseFloat(board.style.height) || board.clientHeight || 0;
        if (width > 0 && height > 0) return width / height;
        return 0.5;
    }

    function ensureBoardFocusButton(card) {
        const title = card && card.querySelector(":scope > .dco-sheet-title");
        if (!title || title.querySelector(":scope > .dco-board-focus-trigger")) return;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "dco-board-focus-trigger";
        button.setAttribute("aria-label", "تكبير اللوح");
        button.setAttribute("title", "تكبير اللوح");
        button.innerHTML = '<span aria-hidden="true">⤢</span>';
        title.appendChild(button);
    }

    function ensureBoardGallery(planRoot) {
        if (!planRoot) return null;
        let gallery = planRoot.querySelector(":scope > .dco-board-gallery");
        const directCards = [...planRoot.querySelectorAll(":scope > .dco-sheet-card")];

        if (!gallery && directCards.length) {
            gallery = document.createElement("div");
            gallery.className = "dco-board-gallery";
            planRoot.insertBefore(gallery, directCards[0]);
        }

        if (!gallery) return null;
        directCards.forEach(card => gallery.appendChild(card));
        return gallery;
    }

    function layoutBoardGallery(planRoot) {
        const gallery = ensureBoardGallery(planRoot);
        if (!gallery) return;

        const rootWidth = planRoot.clientWidth || gallery.clientWidth || 0;
        const columns = desiredBoardColumns(rootWidth);
        planRoot.dataset.boardColumns = String(columns);

        const availableColumnWidth = rootWidth > 0
            ? Math.max(160, (rootWidth - BOARD_GAP_PX * Math.max(0, columns - 1)) / columns - 20)
            : 320;
        const viewportHeight = Math.max(480, window.innerHeight || 720);

        gallery.querySelectorAll(":scope > .dco-sheet-card").forEach(card => {
            const board = card.querySelector(":scope > .dco-sheet-board");
            if (!board) return;
            const aspect = boardAspect(board);
            board.style.setProperty("--dco-board-aspect", `${aspect} / 1`);

            if (columns === 1) {
                board.style.removeProperty("--dco-board-screen-max-width");
            } else {
                const viewportWidthCap = viewportHeight * BOARD_VIEWPORT_HEIGHT_RATIO * aspect;
                const widthCap = Math.max(150, Math.min(availableColumnWidth, viewportWidthCap));
                board.style.setProperty("--dco-board-screen-max-width", `${Math.round(widthCap)}px`);
            }
            ensureBoardFocusButton(card);
        });
    }

    function closeBoardFocus() {
        const overlay = document.querySelector(".dco-board-focus");
        if (overlay) overlay.remove();
        if (document.body && document.body.classList) {
            document.body.classList.remove("dco-board-focus-open");
        }
    }

    function openBoardFocus(card) {
        if (!card) return;
        closeBoardFocus();

        const clone = card.cloneNode(true);
        clone.querySelectorAll(".dco-board-focus-trigger").forEach(button => button.remove());
        const board = clone.querySelector(".dco-sheet-board");
        const sourceBoard = card.querySelector(".dco-sheet-board");
        const aspect = boardAspect(sourceBoard);
        const maxByViewport = Math.max(220, (window.innerHeight || 720) * 0.72 * aspect);
        const maxByWidth = Math.max(220, (window.innerWidth || 1280) * 0.72);
        const focusWidth = Math.min(maxByViewport, maxByWidth);
        if (board) {
            board.style.setProperty("--dco-board-aspect", `${aspect} / 1`);
            board.style.setProperty("--dco-focus-board-width", `${Math.round(focusWidth)}px`);
        }

        const titleText = (card.querySelector(".dco-sheet-title > :first-child")?.textContent || "تفاصيل اللوح").trim();
        const overlay = document.createElement("div");
        overlay.className = "dco-board-focus";
        overlay.setAttribute("role", "dialog");
        overlay.setAttribute("aria-modal", "true");
        overlay.setAttribute("aria-label", titleText);
        overlay.innerHTML = `
            <div class="dco-board-focus__dialog">
                <div class="dco-board-focus__header">
                    <strong>${escapeHtml(titleText)}</strong>
                    <button type="button" class="dco-board-focus__close" aria-label="إغلاق">×</button>
                </div>
                <div class="dco-board-focus__body"></div>
            </div>
        `;
        overlay.querySelector(".dco-board-focus__body").appendChild(clone);
        overlay.addEventListener("click", event => {
            if (event.target === overlay || event.target.closest(".dco-board-focus__close")) {
                closeBoardFocus();
            }
        });
        document.body.appendChild(overlay);
        document.body.classList.add("dco-board-focus-open");
        overlay.querySelector(".dco-board-focus__close")?.focus();
    }

    function installBoardInteractions(root) {
        if (!root || root._dcoBoardGalleryInteractions) return;
        root.addEventListener("click", event => {
            const trigger = event.target.closest(".dco-board-focus-trigger");
            if (!trigger || !root.contains(trigger)) return;
            const card = trigger.closest(".dco-sheet-card");
            if (!card) return;
            event.preventDefault();
            event.stopPropagation();
            openBoardFocus(card);
        });
        root._dcoBoardGalleryInteractions = true;

        if (!document._dcoBoardFocusEscapeHandler) {
            document.addEventListener("keydown", event => {
                if (event.key === "Escape" && document.querySelector(".dco-board-focus")) {
                    closeBoardFocus();
                }
            });
            document._dcoBoardFocusEscapeHandler = true;
        }
    }

    function cleanRenderedPlan(frm) {
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;

        root.querySelectorAll(".dco-cutting-plan").forEach(planRoot => {
            const heading = planRoot.querySelector(":scope > h2");
            if (heading) heading.remove();

            planRoot.querySelectorAll(
                ":scope > .dco-plan-header-cards, :scope > .dco-summary-grid, :scope > .dco-piece-groups"
            ).forEach(el => el.remove());

            [...planRoot.children].forEach(child => {
                if (!(child instanceof HTMLElement)) return;
                if (child.classList.contains("dco-sheet-card")) return;
                if (child.classList.contains("dco-board-gallery")) return;
                if (child.classList.contains("dco-special-raw-coverage")) return;
                if (child.classList.contains("dco-margin-policy-alert")) return;
                const text = (child.textContent || "").replace(/\s+/g, " ").trim();
                const isDuplicatedHeader =
                    (text.includes("الطلب:") && (text.includes("الزبون:") || text.includes("اللوح:") || text.includes("الصنف:"))) ||
                    (text.includes("مقاس اللوح الكامل") && text.includes("سماكة القص"));
                const isMethodDuplicate = text.startsWith("طريقة الترتيب:") || text.includes("طريقة الترتيب:");
                if (isDuplicatedHeader || isMethodDuplicate) child.remove();
            });

            ensureMarginPolicyAlert(frm, planRoot);
            layoutBoardGallery(planRoot);
        });

        // The normal order form already has one authoritative optimizer/control
        // surface above the board layout. The DrawingPlan panel remains available
        // in shop-floor/inbox contexts where that form surface does not exist.
        root.querySelectorAll(
            ".dco-drawing-plan-panel-host, .dco-drawing-plan-panel"
        ).forEach(el => el.remove());
        installBoardInteractions(root);
    }

    function installObserver(frm) {
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root || root._dcoPlanContentObserver) return;

        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                cleanRenderedPlan(frm);
            });
        });
        observer.observe(root, { childList: true, subtree: true });
        root._dcoPlanContentObserver = observer;
    }

    function installResizeObserver(frm) {
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root || root._dcoPlanContentResizeObserver) return;

        let scheduled = false;
        const relayout = () => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                root.querySelectorAll(".dco-cutting-plan").forEach(layoutBoardGallery);
            });
        };

        if (typeof ResizeObserver === "function") {
            const observer = new ResizeObserver(relayout);
            observer.observe(root);
            root._dcoPlanContentResizeObserver = observer;
        } else {
            window.addEventListener("resize", relayout);
            root._dcoPlanContentResizeObserver = { disconnect() {} };
        }
    }

    function apply(frm) {
        installStyles();
        localizePlanSections(frm);
        movePlanActionsToFullWidth(frm);
        cleanRenderedPlan(frm);
        installObserver(frm);
        installResizeObserver(frm);
        requestAnimationFrame(() => {
            movePlanActionsToFullWidth(frm);
            cleanRenderedPlan(frm);
        });
        window.setTimeout(() => {
            movePlanActionsToFullWidth(frm);
            cleanRenderedPlan(frm);
        }, 350);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { apply(frm); },
        refresh(frm) { apply(frm); },
        cutting_plan_json(frm) { apply(frm); },
        packing_mode(frm) { requestAnimationFrame(() => movePlanActionsToFullWidth(frm)); },
        optimization_time_limit_sec(frm) { requestAnimationFrame(() => movePlanActionsToFullWidth(frm)); },
        refresh_plan_controls(frm) { requestAnimationFrame(() => apply(frm)); },
    });

    if (window && typeof window.addEventListener === "function") {
        window.addEventListener("almdina:permissions-updated", () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") apply(frm);
        });
    }
})();
