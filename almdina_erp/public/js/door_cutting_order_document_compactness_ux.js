(() => {
    "use strict";

    const STYLE_ID = "dco-document-compactness-css";
    const POLICY_FLAG = "__almdinaCompactDocumentPolicy";

    function installPrintPolicy() {
        const theme = window.AlmdinaOrderDocumentPrintTheme;
        if (!theme || typeof theme.css !== "function" || theme[POLICY_FLAG]) return;

        const baseCss = theme.css.bind(theme);
        window.AlmdinaOrderDocumentPrintTheme = Object.freeze({
            ...theme,
            [POLICY_FLAG]: true,
            css(mode, shapeCss = "") {
                return `${baseCss(mode, shapeCss)}
                    /* Customer-facing documents keep pricing details in the invoice table,
                       not in a duplicated financial strip below the order header. */
                    .financial-info{display:none!important}

                    /* A custom edge is an exception note, not a card. Keep it textual so
                       regular and exceptional rows retain nearly the same height. */
                    .custom-edge-summary{display:grid;gap:.45mm}
                    .custom-edge-line{
                        display:flex;align-items:baseline;flex-wrap:wrap;gap:.35mm 1mm;
                        padding:0;border:0;border-radius:0;background:transparent;text-align:right
                    }
                    .custom-edge-line span{font-weight:800;color:#59636d}
                    .custom-edge-line span::after{content:":";margin-inline-start:.25mm}
                    .custom-edge-line b{font-weight:900;overflow-wrap:anywhere}
                    .custom-edge-line em{display:none!important}
                `;
            },
        });
    }

    function installCostScreenStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-edge-default-note{display:none!important}
            .dco-custom-edge-list{display:grid!important;gap:3px!important}
            .dco-custom-edge-chip{
                display:flex!important;align-items:baseline!important;flex-wrap:wrap!important;
                gap:3px 6px!important;padding:0!important;border:0!important;border-radius:0!important;
                background:transparent!important;box-shadow:none!important;text-align:right!important
            }
            .dco-custom-edge-sides{
                color:var(--text-muted,#65717d)!important;font-size:10px!important;
                font-weight:800!important;line-height:1.35!important
            }
            .dco-custom-edge-sides::after{content:":";margin-inline-start:2px}
            .dco-custom-edge-chip b{
                color:var(--text-color,#26313b);font-size:11px!important;
                font-weight:900!important;line-height:1.35!important;overflow-wrap:anywhere
            }
            .dco-custom-edge-chip em{display:none!important}
            .dco-cost-table .dco-edge-detail-cell{min-width:220px!important}
            @media(max-width:760px){
                .dco-custom-edge-chip{width:100%!important}
            }
        `;
        document.head.appendChild(style);
    }

    installPrintPolicy();
    installCostScreenStyles();
})();
