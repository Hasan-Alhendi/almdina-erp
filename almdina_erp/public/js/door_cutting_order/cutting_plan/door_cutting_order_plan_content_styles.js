(() => {
    "use strict";

    if (window.AlmdinaPlanContentStyles) return;

    const STYLE_ID = "dco-plan-content-layout-css-v7";
    const CSS_TEXT = `
        .dco-plan-actions-section {
            border:0 !important;
            box-shadow:none !important;
            margin-top:-4px !important;
            background:transparent !important;
        }
        .dco-plan-actions-section > .section-body {
            padding-top:0 !important;
        }
        .dco-plan-actions-native {
            width:100% !important;
            max-width:100% !important;
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
            gap:8px !important;
            direction:rtl !important;
            margin:0 0 10px !important;
            padding:8px 10px !important;
            border:1px solid #e0b34c !important;
            border-radius:10px !important;
            background:linear-gradient(135deg,#fff9e8,#fffdf6) !important;
            color:#5f4508 !important;
            box-shadow:none !important;
        }
        [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__icon {
            flex:0 0 auto;
            font-size:16px !important;
            line-height:1.25 !important;
        }
        [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__body {
            min-width:0;
            flex:1 1 auto;
        }
        [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__title {
            display:inline;
            margin-left:5px;
            font-size:11.5px !important;
            font-weight:900 !important;
        }
        [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__summary {
            display:inline;
            font-size:11px !important;
            font-weight:750 !important;
            line-height:1.55 !important;
        }
        [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__details {
            margin-top:4px;
        }
        [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__note {
            margin:1px 0 0;
            font-size:10.5px !important;
            font-weight:700 !important;
            line-height:1.55 !important;
        }
        [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__edges {
            display:flex;
            flex-wrap:wrap;
            gap:5px;
            margin-top:6px;
        }
        [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__edge {
            display:inline-flex;
            align-items:center;
            min-height:22px;
            padding:2px 7px;
            border:1px solid rgba(143,103,13,.22);
            border-radius:999px;
            background:rgba(255,255,255,.78);
            font-size:9.5px !important;
            font-weight:850 !important;
            white-space:nowrap;
        }
        [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__edge.is-zero {
            border-color:#d18a00;
            background:#fff2c9;
            color:#704700;
        }
        [data-fieldname="cutting_plan_html"] .dco-board-original-edge {
            position:absolute;
            z-index:30;
            pointer-events:none;
            color:#7a4d00;
        }
        [data-fieldname="cutting_plan_html"] .dco-board-original-edge--top {
            top:1px;
            left:0;
            right:0;
            border-top:3px dashed #d18a00;
        }
        [data-fieldname="cutting_plan_html"] .dco-board-original-edge--bottom {
            bottom:1px;
            left:0;
            right:0;
            border-bottom:3px dashed #d18a00;
        }
        [data-fieldname="cutting_plan_html"] .dco-board-original-edge--left {
            top:0;
            bottom:0;
            left:1px;
            border-left:3px dashed #d18a00;
        }
        [data-fieldname="cutting_plan_html"] .dco-board-original-edge--right {
            top:0;
            bottom:0;
            right:1px;
            border-right:3px dashed #d18a00;
        }
        [data-fieldname="cutting_plan_html"] .dco-board-original-edge__label {
            position:absolute;
            display:inline-flex;
            align-items:center;
            justify-content:center;
            min-height:17px;
            padding:1px 5px;
            border:1px solid rgba(209,138,0,.38);
            border-radius:999px;
            background:rgba(255,248,225,.94);
            box-shadow:0 1px 3px rgba(80,54,0,.08);
            color:#704700;
            direction:rtl;
            font-family:Tahoma,Arial,sans-serif;
            font-size:8px;
            font-weight:900;
            line-height:1.1;
            white-space:nowrap;
        }
        [data-fieldname="cutting_plan_html"] .dco-board-original-edge--top .dco-board-original-edge__label {
            top:3px;
            left:50%;
            transform:translateX(-50%);
        }
        [data-fieldname="cutting_plan_html"] .dco-board-original-edge--bottom .dco-board-original-edge__label {
            bottom:3px;
            left:50%;
            transform:translateX(-50%);
        }
        [data-fieldname="cutting_plan_html"] .dco-board-original-edge--left .dco-board-original-edge__label {
            top:50%;
            left:3px;
            transform:translate(-50%,-50%) rotate(-90deg);
        }
        [data-fieldname="cutting_plan_html"] .dco-board-original-edge--right .dco-board-original-edge__label {
            top:50%;
            right:3px;
            transform:translate(50%,-50%) rotate(90deg);
        }
        [data-fieldname="cutting_plan_html"] .dco-board-gallery {
            display:grid !important;
            grid-template-columns:1fr;
            gap:8px !important;
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
            padding:5px !important;
            border:1px solid var(--border-color,#e2e6ea) !important;
            border-radius:10px !important;
            background:var(--card-bg,#fff) !important;
            box-shadow:none !important;
            page-break-inside:avoid;
            break-inside:avoid;
            overflow:hidden;
            transition:border-color .16s ease,box-shadow .16s ease,transform .16s ease;
        }
        [data-fieldname="cutting_plan_html"] .dco-board-gallery > .dco-sheet-card:hover {
            border-color:#b9c3cd !important;
            box-shadow:0 3px 10px rgba(24,36,48,.055) !important;
            transform:translateY(-1px);
        }
        [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-title {
            display:grid !important;
            grid-template-columns:auto minmax(0,1fr) auto;
            align-items:center !important;
            gap:5px !important;
            min-height:27px;
            margin:0 0 4px !important;
            padding:0 0 5px !important;
            border-bottom:1px solid var(--border-color,#edf0f3);
            font-size:10.5px !important;
            line-height:1.3 !important;
        }
        [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-title > :first-child {
            font-size:11.5px !important;
            font-weight:900 !important;
            white-space:nowrap;
        }
        [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-title > :nth-child(2) {
            min-width:0;
            color:var(--text-muted,#68737d);
            font-size:9px !important;
            font-weight:750 !important;
            white-space:nowrap;
            overflow:hidden;
            text-overflow:ellipsis;
        }
        [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-board-focus-trigger {
            display:inline-flex;
            align-items:center;
            justify-content:center;
            min-width:27px;
            min-height:25px;
            padding:3px 6px;
            border:1px solid var(--border-color,#dce2e7);
            border-radius:7px;
            background:var(--subtle-fg,#f6f8fa);
            color:var(--text-color,#26313b);
            font-size:9.5px;
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
            padding:10px;
            background:rgba(20,27,34,.72);
            backdrop-filter:blur(3px);
        }
        .dco-board-focus__dialog {
            width:min(1320px,98vw);
            height:min(96vh,980px);
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
            gap:14px;
            min-height:58px;
            padding:9px 12px;
            border-bottom:1px solid var(--border-color,#dfe3e8);
            background:var(--card-bg,#fff);
        }
        .dco-board-focus__identity {
            min-width:0;
            display:flex;
            align-items:center;
            gap:10px;
            flex:1 1 auto;
        }
        .dco-board-focus__identity strong {
            flex:0 0 auto;
            font-size:14px;
            font-weight:900;
        }
        .dco-board-focus__stats {
            min-width:0;
            overflow:hidden;
            text-overflow:ellipsis;
            white-space:nowrap;
            color:var(--text-muted,#68737d);
            font-size:11px;
            font-weight:750;
        }
        .dco-board-focus__actions {
            flex:0 0 auto;
            display:flex;
            align-items:center;
            gap:7px;
        }
        .dco-board-focus__zoom {
            display:inline-flex;
            align-items:center;
            overflow:hidden;
            border:1px solid var(--border-color,#dfe3e8);
            border-radius:9px;
            background:var(--subtle-fg,#f6f8fa);
        }
        .dco-board-focus__zoom button,
        .dco-board-focus__fit {
            min-width:34px;
            height:34px;
            border:0;
            background:transparent;
            color:var(--text-color,#202a33);
            font-size:14px;
            font-weight:900;
            cursor:pointer;
        }
        .dco-board-focus__fit {
            padding:0 10px;
            border:1px solid var(--border-color,#dfe3e8);
            border-radius:9px;
            background:var(--subtle-fg,#f6f8fa);
            font-size:11px;
        }
        .dco-board-focus__zoom button:hover,
        .dco-board-focus__fit:hover {
            background:var(--card-bg,#fff);
        }
        .dco-board-focus__zoom-value {
            min-width:52px;
            text-align:center;
            font-size:10px;
            font-weight:850;
            color:var(--text-muted,#68737d);
        }
        .dco-board-focus__close {
            width:36px;
            height:36px;
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
            display:flex;
            align-items:flex-start;
            justify-content:center;
            padding:10px 18px 18px;
            background:var(--subtle-fg,#f7f9fb);
            overscroll-behavior:contain;
        }
        .dco-board-focus .dco-sheet-card {
            flex:0 0 auto;
            width:auto !important;
            max-width:none !important;
            margin:0 !important;
            padding:0 !important;
            border:0 !important;
            background:transparent !important;
            box-shadow:none !important;
        }
        .dco-board-focus .dco-sheet-title { display:none !important; }
        .dco-board-focus .dco-board-focus-trigger { display:none !important; }
        .dco-board-focus .dco-sheet-board {
            width:var(--dco-focus-board-width,480px) !important;
            height:auto !important;
            max-width:none !important;
            aspect-ratio:var(--dco-board-aspect,1 / 2) !important;
            margin:0 auto !important;
            background-size:24px 24px !important;
            box-shadow:0 8px 26px rgba(28,38,48,.12);
        }
        .dco-board-focus .dco-piece { font-size:clamp(10px,.72vw,13px) !important; }
        .dco-board-focus .dco-piece-kind-badge { font-size:8px !important;padding:2px 5px !important; }
        @media (max-width:760px) {
            .dco-plan-actions-section > .section-body { padding-inline:8px !important; }
            [data-fieldname="plan_control_actions"] .dco-plan-actions { grid-template-columns:1fr !important; }
            [data-fieldname="plan_control_actions"] .dco-plan-actions-title {
                align-items:flex-start !important;
                flex-direction:column !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-mode-hint {
                max-width:100% !important;
                border-radius:9px !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-document-actions .btn { flex:1 1 180px; }
            [data-fieldname="cutting_plan_html"] .dco-plan-tabs {
                width:100%;
                margin-inline:0 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-plan-tabs .btn {
                flex:1 1 0;
                min-width:0;
            }
            [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert {
                gap:7px !important;
                padding:8px 9px !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery > .dco-sheet-card { padding:5px !important; }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-title {
                grid-template-columns:auto minmax(0,1fr) auto;
            }
            .dco-board-focus__dialog {
                width:99vw;
                height:98vh;
                border-radius:12px;
            }
            .dco-board-focus__header {
                align-items:flex-start;
                gap:8px;
                flex-wrap:wrap;
            }
            .dco-board-focus__identity {
                flex:1 1 100%;
                order:1;
            }
            .dco-board-focus__actions {
                order:2;
                width:100%;
                justify-content:flex-start;
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
            [data-fieldname="cutting_plan_html"] .dco-margin-policy-alert__edge { justify-content:center; }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery { gap:8px !important; }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-board { width:100% !important; }
            [data-fieldname="cutting_plan_html"] .dco-board-gallery .dco-sheet-title > :nth-child(2) {
                white-space:normal;
                line-height:1.45 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-board-original-edge__label {
                font-size:7px;
                padding:1px 4px;
            }
            .dco-board-focus { padding:2px; }
            .dco-board-focus__dialog { width:100%;height:99vh;border-radius:10px; }
            .dco-board-focus__body { padding:8px; }
            .dco-board-focus__stats { font-size:10px; }
            .dco-board-focus__fit { display:none; }
        }
    `;

    function install() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = CSS_TEXT;
        document.head.appendChild(style);
    }

    window.AlmdinaPlanContentStyles = Object.freeze({ install });
})();
