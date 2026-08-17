(() => {
    "use strict";

    function esc(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function contactLines(value) {
        return String(value || "")
            .split(/\r?\n/)
            .map(line => line.trim())
            .filter(Boolean);
    }

    function headerHtml(identity = {}, options = {}) {
        const contacts = contactLines(identity.print_factory_contacts);
        const title = String(options.title || "").trim();
        const meta = String(options.meta || "").trim();
        const badge = String(options.badge || "").trim();
        const badgeClass = String(options.badgeClass || "").trim();

        return `<header class="dco-unified-print-header">
            <div class="dco-unified-print-brand">
                <div class="dco-unified-print-factory-name">${esc(identity.print_factory_name || "")}</div>
                <div class="dco-unified-print-factory-description">${esc(identity.print_factory_description || "")}</div>
                <div class="dco-unified-print-factory-address">${esc(identity.print_factory_address || "")}</div>
                ${contacts.length ? `<div class="dco-unified-print-factory-contacts">${contacts.map(line => `<span>${esc(line)}</span>`).join("")}</div>` : ""}
            </div>
            <div class="dco-unified-print-document">
                <h1>${esc(title)}</h1>
                ${meta ? `<div class="dco-unified-print-meta">${esc(meta)}</div>` : ""}
                ${badge ? `<div class="dco-unified-print-badge ${esc(badgeClass)}">${esc(badge)}</div>` : ""}
            </div>
        </header>`;
    }

    function headerCss() {
        return `
            .dco-unified-print-header{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(42mm,.62fr);align-items:start;gap:5mm;padding-bottom:1.5mm;margin-bottom:1.6mm;border-bottom:1.2pt solid #172033}
            .dco-unified-print-brand{min-width:0;text-align:right;line-height:1.25;overflow-wrap:anywhere}
            .dco-unified-print-factory-name{font-size:12.8pt;font-weight:950;line-height:1.05;color:#172033}
            .dco-unified-print-factory-description{margin-top:.55mm;font-size:6.8pt;font-weight:800;line-height:1.35;color:#394550}
            .dco-unified-print-factory-address{margin-top:.42mm;font-size:6.35pt;font-weight:650;line-height:1.35;color:#5d6874}
            .dco-unified-print-factory-contacts{display:flex;flex-wrap:wrap;gap:.4mm 2.3mm;margin-top:.45mm;font-size:6.1pt;font-weight:700;line-height:1.3;color:#4f5a65}
            .dco-unified-print-factory-contacts span{white-space:nowrap}
            .dco-unified-print-document{min-width:0;text-align:left}
            .dco-unified-print-document h1{margin:0;font-size:14.8pt;font-weight:950;line-height:1.06;letter-spacing:-.1pt;color:#172033}
            .dco-unified-print-meta{margin-top:.8mm;font-size:6.5pt;font-weight:700;line-height:1.4;color:#5d6874;overflow-wrap:anywhere}
            .dco-unified-print-badge{display:inline-block;margin-top:1.2mm;padding:.8mm 1.6mm;border:.75pt solid #8c1d1d;border-radius:1.6mm;background:#fff0f0;color:#8c1d1d;font-size:6.3pt;font-weight:900;line-height:1.2}
        `;
    }

    function css(mode, shapeCss = "") {
        const measurements = mode === "measurements";
        const pageMargin = measurements ? "6mm" : "7mm";
        const bodySize = measurements ? "8.1pt" : "8.5pt";
        const tableSize = measurements ? "7.65pt" : "8.05pt";
        const rowPadding = measurements ? "1.05mm 1.1mm" : "1.35mm 1.3mm";
        const sketchHeight = measurements ? "27mm" : "31mm";
        const sketchWidth = measurements ? "54mm" : "62mm";

        return `
            @page{size:A4 portrait;margin:${pageMargin}}
            *{box-sizing:border-box}
            html,body{margin:0;padding:0;background:#fff;color:#172033;direction:rtl;font-family:Tahoma,"Segoe UI",Arial,sans-serif}
            body{font-size:${bodySize};line-height:1.28;-webkit-print-color-adjust:exact;print-color-adjust:exact;font-variant-numeric:tabular-nums}
            ${headerCss()}
            .info{display:grid;gap:1.2mm;margin:0 0 2.2mm}
            .shared-info{grid-template-columns:repeat(6,minmax(0,1fr))}
            .financial-info{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:1.2mm}
            .info>div{min-width:0;min-height:${measurements ? "10.5mm" : "11.5mm"};padding:1.35mm 1.55mm;border:.7pt solid #c7cdd3;border-radius:2.1mm;background:#fbfcfd;line-height:1.25;overflow-wrap:anywhere}
            .info b{display:block;margin-bottom:.55mm;color:#5d6874;font-size:${measurements ? "6.35pt" : "6.65pt"};font-weight:800}
            .title{margin:${measurements ? "2.1mm" : "3mm"} 0 1.2mm;font-size:${measurements ? "9.2pt" : "9.8pt"};font-weight:900;color:#172033}
            .table{width:100%;border-collapse:separate;border-spacing:0;table-layout:fixed;border:.75pt solid #98a2ac;border-radius:2mm;overflow:hidden}
            .table thead{display:table-header-group}
            .table th,.table td{padding:${rowPadding};text-align:center;vertical-align:middle;border-inline-start:.55pt solid #c5cbd1;border-bottom:.55pt solid #c5cbd1;line-height:1.2}
            .table th:first-child,.table td:first-child{border-inline-start:0}
            .table tbody tr:last-child td{border-bottom:0}
            .table th{background:#eef1f4;color:#303a44;font-size:${measurements ? "7.15pt" : "7.45pt"};font-weight:900;white-space:nowrap}
            .table tr{break-inside:avoid;page-break-inside:avoid}
            .right{text-align:right!important;white-space:normal}
            .measurements{font-size:${tableSize}}
            .measurements tbody tr:nth-child(even){background:#fbfcfd}
            .measurements th:nth-child(1),.measurements td:nth-child(1){width:4%}
            .measurements th:nth-child(2),.measurements td:nth-child(2){width:8%}
            .measurements th:nth-child(3),.measurements td:nth-child(3),.measurements th:nth-child(4),.measurements td:nth-child(4){width:9%}
            .measurements th:nth-child(5),.measurements td:nth-child(5){width:6%}
            .measurements th:nth-child(6),.measurements td:nth-child(6){width:28%}
            .measurements th:nth-child(7),.measurements td:nth-child(7){width:36%}
            .dimension{display:inline-flex;min-width:12mm;flex-direction:column;align-items:center;gap:.35mm;line-height:1}
            .dimension b{font-size:${measurements ? "9pt" : "9.35pt"};font-weight:900}
            .dimension-lines{display:flex;min-height:1.7mm;flex-direction:column;align-items:center;gap:.35mm}
            .dimension-edge-line{display:block;width:9mm;height:.55pt;border-radius:999px;background:#172033}
            .dimension-lines-0{visibility:hidden}
            .custom-edge-empty{display:block;min-height:2mm}
            .custom-edge-summary{display:grid;gap:.8mm}
            .custom-edge-line{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.25fr) auto;align-items:center;gap:1mm;padding:.8mm 1.1mm;border:.7pt solid #d7b54b;border-radius:1.6mm;background:#fff8df;text-align:right}
            .custom-edge-line span{font-size:${measurements ? "6.65pt" : "6.95pt"};font-weight:800;color:#4c5258}
            .custom-edge-line b{font-size:${measurements ? "7.15pt" : "7.45pt"};font-weight:900;overflow-wrap:anywhere}
            .custom-edge-line em{padding:.25mm 1mm;border:.65pt solid currentColor;border-radius:999px;color:#805b00;font-size:${measurements ? "5.9pt" : "6.15pt"};font-style:normal;font-weight:900;white-space:nowrap}
            .notes-cell{font-size:${measurements ? "7.35pt" : "7.65pt"};line-height:1.35}
            .row-with-drawing td{padding-top:1.6mm;padding-bottom:1.6mm}
            .invoice{font-size:8.05pt;break-inside:avoid;page-break-inside:avoid}
            .invoice th,.invoice td{padding:1.4mm 1.5mm}
            .invoice th:nth-child(1),.invoice td:nth-child(1){width:5%}
            .invoice th:nth-child(2),.invoice td:nth-child(2){width:47%}
            .invoice th:nth-child(3),.invoice td:nth-child(3){width:11%}
            .invoice th:nth-child(4),.invoice td:nth-child(4){width:10%}
            .invoice th:nth-child(5),.invoice td:nth-child(5),.invoice th:nth-child(6),.invoice td:nth-child(6){width:13.5%}
            .invoice-description{line-height:1.32}
            .line-note{display:block;margin-top:.65mm;color:#66717c;font-size:6.8pt;font-weight:500;line-height:1.3}
            .total{display:flex;justify-content:space-between;align-items:center;width:42%;margin:2.4mm 0 0 auto;padding:2mm 2.5mm;border:1.4pt solid #172033;border-radius:1.8mm;font-size:11pt;font-weight:900}
            .order-note{margin-top:2.2mm;padding:1.7mm 2mm;border:.7pt solid #b9c0c7;border-radius:1.8mm;font-size:7.5pt;line-height:1.4}
            .footer{display:flex;justify-content:space-between;margin-top:2.2mm;padding-top:1.1mm;border-top:.65pt solid #c4cad0;color:#6c7781;font-size:6.5pt}
            ${shapeCss}
            .dco-piece-notes{gap:1.1mm}
            .dco-piece-notes-text{font-size:${measurements ? "7.6pt" : "7.9pt"};font-weight:650;line-height:1.4}
            .dco-piece-sketch{padding:1mm 1.2mm .7mm;border:.7pt solid #aeb7bf;border-radius:1.8mm;background:#fff}
            .dco-piece-sketch svg{width:100%;height:${sketchHeight};max-width:${sketchWidth};margin:0 auto;overflow:visible}
            .dco-piece-sketch figcaption{margin-top:.5mm;color:#5e6974;font-size:6.7pt;font-weight:800;line-height:1.2}
            @media print{a{color:inherit;text-decoration:none}}
        `;
    }

    window.AlmdinaOrderDocumentPrintTheme = Object.freeze({
        css,
        headerCss,
        headerHtml,
    });
})();
