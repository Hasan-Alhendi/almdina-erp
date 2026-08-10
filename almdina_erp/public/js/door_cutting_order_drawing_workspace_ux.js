(() => {
    "use strict";

    const baseEditor = window.AlmdinaSpecialShapeEditor;
    if (!baseEditor) {
        console.error("Special-shape editor must load before drawing-workspace UX");
        return;
    }
    if (baseEditor.__drawingWorkspaceIntegrated) return;

    const STYLE_ID = "dco-drawing-workspace-css";
    const MOUNT_RETRIES = 18;

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-drawing-workspace-template-launcher{display:flex;align-items:center;gap:9px;width:100%;min-height:44px;margin:4px 0 6px;padding:7px 8px;border:1px solid #c8d8e4;border-radius:10px;background:#fff;color:#24465c;cursor:pointer;text-align:right;transition:.12s ease}
            .dco-drawing-workspace-template-launcher:hover,.dco-drawing-workspace-template-launcher.is-open{border-color:#2490ef;background:#f4faff;color:#0e639d;box-shadow:0 0 0 2px rgba(36,144,239,.08)}
            .dco-drawing-workspace-template-launcher-icon{display:grid;place-items:center;width:28px;height:28px;border-radius:8px;background:#edf5fb;color:#1769aa;font-size:16px;font-weight:900;flex:0 0 auto}
            .dco-drawing-workspace-template-launcher strong{display:block;font-size:9.5px}.dco-drawing-workspace-template-launcher small{display:block;margin-top:1px;color:#71808e;font-size:7.3px;font-weight:500}

            .dco-smart-template-palette.dco-drawing-workspace-gallery{position:fixed!important;z-index:1095!important;display:none!important;width:min(590px,calc(100vw - 36px));max-width:590px;margin:0!important;padding:12px!important;border:1px solid #cddbe5!important;border-radius:16px!important;background:rgba(255,255,255,.995)!important;box-shadow:0 24px 70px rgba(15,23,42,.22)!important;backdrop-filter:blur(10px)}
            .dco-smart-template-palette.dco-drawing-workspace-gallery.is-open{display:block!important}
            .dco-drawing-workspace-gallery .dco-smart-template-head{margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e5ebef}
            .dco-drawing-workspace-gallery .dco-smart-template-head strong{font-size:12px}.dco-drawing-workspace-gallery .dco-smart-template-head span{font-size:9px}
            .dco-drawing-workspace-gallery .dco-smart-template-list{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:8px!important;max-height:min(520px,64vh)!important;overflow:auto!important;padding:2px!important}
            .dco-drawing-workspace-gallery .dco-smart-template-card{display:grid!important;grid-template-columns:62px minmax(0,1fr)!important;align-items:center!important;gap:9px!important;min-height:86px!important;padding:9px!important;border-radius:12px!important;text-align:right!important}
            .dco-drawing-workspace-gallery .dco-smart-template-card-icon{width:58px!important;height:50px!important;border-radius:10px!important;background:#edf6fc!important}
            .dco-drawing-workspace-gallery .dco-smart-template-card-icon svg{width:50px!important;height:42px!important;display:block!important}
            .dco-drawing-workspace-gallery .dco-smart-template-card strong{font-size:10.5px!important;line-height:1.35!important}.dco-drawing-workspace-gallery .dco-smart-template-card small{margin-top:4px!important;font-size:8.2px!important;line-height:1.35!important}
            .dco-drawing-workspace-gallery .dco-smart-template-more{margin-top:9px!important;min-height:34px!important;font-size:9px!important}
            .dco-drawing-workspace-gallery-close{position:absolute;top:8px;left:8px;width:28px;height:28px;border:0;border-radius:8px;background:#f1f5f8;color:#526779;cursor:pointer;font-size:16px;line-height:1}.dco-drawing-workspace-gallery-close:hover{background:#e8f3fa;color:#0e639d}

            .dco-exact-line-tool.dco-drawing-workspace-primary-tool{position:relative;border-color:#2490ef;background:#edf8ff;color:#0e639d;box-shadow:0 0 0 2px rgba(36,144,239,.06)}
            .dco-drawing-workspace-recommended{display:inline-flex;align-items:center;margin-inline-start:5px;padding:2px 5px;border-radius:999px;background:#daf2e7;color:#12633f;font-size:6.5px;font-weight:900;vertical-align:middle}
            .dco-sketch-tool[data-tool="line"].dco-drawing-workspace-secondary-tool{opacity:.82}.dco-sketch-tool[data-tool="line"].dco-drawing-workspace-secondary-tool small{color:#8b6670!important}

            .dco-exact-line-hud.dco-drawing-workspace-side-panel{position:static!important;z-index:auto!important;top:auto!important;left:auto!important;right:auto!important;width:100%!important;margin:6px 0 9px!important;border-radius:11px!important;box-shadow:none!important;background:#f8fbfd!important;overflow:visible!important}
            .dco-drawing-workspace-side-panel .dco-exact-line-head{padding:8px!important}.dco-drawing-workspace-side-panel .dco-exact-line-head strong{font-size:9.5px!important}.dco-drawing-workspace-side-panel .dco-exact-line-badge{font-size:6.5px!important;padding:3px 5px!important}
            .dco-drawing-workspace-side-panel .dco-exact-line-body{padding:8px!important}.dco-drawing-workspace-side-panel .dco-exact-line-status{min-height:0!important;margin-bottom:7px!important;padding:6px!important;font-size:7.5px!important}
            .dco-exact-line-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-bottom:7px}.dco-exact-line-step{padding:5px 3px;border-radius:7px;background:#eef4f8;color:#536979;text-align:center;font-size:6.5px;font-weight:800;line-height:1.3}.dco-exact-line-step b{display:grid;place-items:center;width:17px;height:17px;margin:0 auto 3px;border-radius:50%;background:#1769aa;color:#fff;font-size:8px}
            .dco-drawing-workspace-side-panel .dco-exact-line-grid{grid-template-columns:1fr!important;margin-bottom:6px!important}.dco-drawing-workspace-side-panel .dco-exact-line-field label{font-size:7px!important}.dco-drawing-workspace-side-panel .dco-exact-line-shell input{height:40px!important;font-size:15px!important}.dco-drawing-workspace-side-panel .dco-exact-line-shell span{font-size:8px!important}
            .dco-drawing-workspace-add-side{width:100%;min-height:38px;margin:0 0 6px;border:1px solid #1769aa;border-radius:9px;background:#1769aa;color:#fff;cursor:pointer;font-size:9px;font-weight:900}.dco-drawing-workspace-add-side:hover{background:#0e5f95}.dco-drawing-workspace-add-side:active{transform:translateY(1px)}
            .dco-exact-line-advanced{margin:6px 0;border:1px solid #dbe5eb;border-radius:9px;background:#fff;overflow:hidden}.dco-exact-line-advanced summary{padding:7px 8px;cursor:pointer;color:#476174;font-size:7.5px;font-weight:900;user-select:none}.dco-exact-line-advanced-body{padding:0 7px 7px}.dco-exact-line-advanced .dco-exact-line-axis{margin:6px 0}.dco-exact-line-advanced .dco-exact-line-meta{margin:6px 0}.dco-exact-line-advanced .dco-exact-line-foot{margin-top:6px!important}
            .dco-drawing-workspace-side-panel .dco-exact-line-reset{min-height:31px!important;font-size:7.5px!important}

            @media(max-width:1050px){.dco-drawing-workspace-gallery .dco-smart-template-list{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
            @media(max-width:700px){.dco-drawing-workspace-template-launcher{display:none}.dco-smart-template-palette.dco-drawing-workspace-gallery{display:none!important}.dco-exact-line-hud.dco-drawing-workspace-side-panel{position:fixed!important;left:12px!important;right:12px!important;top:82px!important;width:auto!important;max-height:calc(100vh - 110px);overflow:auto!important;z-index:1090!important;box-shadow:0 16px 45px rgba(15,23,42,.2)!important}}
        `;
        document.head.appendChild(style);
    }

    function visibleModal() {
        const modals = Array.from(document.querySelectorAll(".dco-special-shape-modal"));
        return modals.reverse().find(modal =>
            !modal.classList.contains("dco-special-shape-readonly")
            && (modal.classList.contains("show") || modal.style.display === "block")
        ) || null;
    }

    function textNode(button) {
        return button && button.querySelector("span:last-child");
    }

    function patchLineTools(root) {
        const exactButton = root.querySelector(".dco-exact-line-tool");
        const normalLine = root.querySelector('.dco-sketch-tool[data-tool="line"]');
        if (!exactButton || !normalLine) return false;

        exactButton.classList.add("dco-drawing-workspace-primary-tool");
        const exactText = textNode(exactButton);
        if (exactText) {
            exactText.innerHTML = `<strong>ضلع بمقاس <span class="dco-drawing-workspace-recommended">الموصى به</span></strong><small>1 اضغط البداية · 2 وجّه · 3 أدخل الطول</small>`;
        }
        if (normalLine.parentNode && normalLine.previousElementSibling !== exactButton) {
            normalLine.parentNode.insertBefore(exactButton, normalLine);
        }
        normalLine.classList.add("dco-drawing-workspace-secondary-tool");
        const normalText = textNode(normalLine);
        if (normalText) normalText.innerHTML = "<strong>خط توضيحي</strong><small>للشرح فقط — ليس له قياس إنتاجي</small>";
        return true;
    }

    function patchExactLinePanel(root) {
        const toolbar = root.querySelector(".dco-sketch-toolbar");
        const exactButton = root.querySelector(".dco-exact-line-tool");
        const hud = root.querySelector(".dco-exact-line-hud");
        if (!toolbar || !exactButton || !hud) return false;
        if (hud.dataset.dcoWorkspaceReady === "1") return true;
        hud.dataset.dcoWorkspaceReady = "1";
        hud.classList.add("dco-drawing-workspace-side-panel");
        exactButton.insertAdjacentElement("afterend", hud);

        const body = hud.querySelector(".dco-exact-line-body");
        const status = hud.querySelector(".dco-exact-line-status");
        const grid = hud.querySelector(".dco-exact-line-grid");
        const angleField = grid && grid.children[1];
        const axis = hud.querySelector(".dco-exact-line-axis");
        const meta = hud.querySelector(".dco-exact-line-meta");
        const foot = hud.querySelector(".dco-exact-line-foot");
        const reset = hud.querySelector(".dco-exact-line-reset");
        const lengthInput = hud.querySelector("[data-exact-length]");
        if (!body || !status || !grid || !lengthInput) return true;

        const steps = document.createElement("div");
        steps.className = "dco-exact-line-steps";
        steps.innerHTML = `<div class="dco-exact-line-step"><b>1</b>اضغط نقطة البداية</div><div class="dco-exact-line-step"><b>2</b>وجّه الضلع</div><div class="dco-exact-line-step"><b>3</b>اكتب الطول</div>`;
        status.insertAdjacentElement("beforebegin", steps);

        const add = document.createElement("button");
        add.type = "button";
        add.className = "dco-drawing-workspace-add-side";
        add.textContent = "إضافة الضلع بهذا القياس";
        grid.insertAdjacentElement("afterend", add);
        add.addEventListener("click", () => {
            lengthInput.focus();
            lengthInput.dispatchEvent(new KeyboardEvent("keydown", {
                key: "Enter",
                code: "Enter",
                bubbles: true,
                cancelable: true,
            }));
        });

        if (angleField || axis || meta || foot) {
            const advanced = document.createElement("details");
            advanced.className = "dco-exact-line-advanced";
            const summary = document.createElement("summary");
            summary.textContent = "اتجاه وزاوية متقدمة";
            const advancedBody = document.createElement("div");
            advancedBody.className = "dco-exact-line-advanced-body";
            advanced.appendChild(summary);
            advanced.appendChild(advancedBody);
            add.insertAdjacentElement("afterend", advanced);
            if (angleField) {
                const angleGrid = document.createElement("div");
                angleGrid.className = "dco-exact-line-grid";
                angleGrid.appendChild(angleField);
                advancedBody.appendChild(angleGrid);
            }
            if (axis) advancedBody.appendChild(axis);
            if (meta) advancedBody.appendChild(meta);
            if (foot) advancedBody.appendChild(foot);
        }
        if (reset) reset.textContent = "اختيار نقطة بداية جديدة";

        exactButton.addEventListener("click", () => {
            window.setTimeout(() => {
                if (!exactButton.classList.contains("is-active")) return;
                try { exactButton.scrollIntoView({ block: "nearest", behavior: "smooth" }); } catch (error) { /* optional */ }
                lengthInput.focus();
            }, 0);
        });
        return true;
    }

    function galleryPosition(launcher, panel) {
        const rect = launcher.getBoundingClientRect();
        const width = Math.min(590, Math.max(320, window.innerWidth - 36));
        const left = Math.max(16, Math.min(window.innerWidth - width - 16, rect.left - width - 12));
        const top = Math.max(88, Math.min(window.innerHeight - 300, rect.top - 12));
        panel.style.left = `${left}px`;
        panel.style.right = "auto";
        panel.style.top = `${top}px`;
    }

    function closeGallery(controller) {
        if (!controller || !controller.panel) return;
        controller.panel.classList.remove("is-open");
        controller.launcher.classList.remove("is-open");
        controller.launcher.setAttribute("aria-expanded", "false");
    }

    function patchTemplates(modal, root) {
        const panel = root.querySelector(".dco-smart-template-palette");
        const toolbar = root.querySelector(".dco-sketch-toolbar");
        if (!panel || !toolbar) return false;
        if (panel.dataset.dcoWorkspaceGallery === "1") return true;
        panel.dataset.dcoWorkspaceGallery = "1";
        panel.classList.add("dco-drawing-workspace-gallery", "is-expanded");

        const launcher = document.createElement("button");
        launcher.type = "button";
        launcher.className = "dco-drawing-workspace-template-launcher";
        launcher.setAttribute("aria-expanded", "false");
        launcher.innerHTML = `<span class="dco-drawing-workspace-template-launcher-icon">▰</span><span><strong>القوالب الجاهزة</strong><small>افتح معرضًا واضحًا بدل القائمة الضيقة</small></span>`;
        panel.insertAdjacentElement("beforebegin", launcher);
        modal.appendChild(panel);

        const close = document.createElement("button");
        close.type = "button";
        close.className = "dco-drawing-workspace-gallery-close";
        close.setAttribute("aria-label", "إغلاق معرض القوالب");
        close.textContent = "×";
        panel.appendChild(close);

        const controller = { panel, launcher };
        const toggle = () => {
            const open = !panel.classList.contains("is-open");
            if (!open) return closeGallery(controller);
            galleryPosition(launcher, panel);
            panel.classList.add("is-open");
            launcher.classList.add("is-open");
            launcher.setAttribute("aria-expanded", "true");
        };
        launcher.addEventListener("click", event => {
            event.preventDefault();
            event.stopPropagation();
            toggle();
        });
        close.addEventListener("click", event => {
            event.preventDefault();
            event.stopPropagation();
            closeGallery(controller);
        });
        panel.addEventListener("click", event => {
            if (event.target.closest && event.target.closest("[data-smart-template]")) {
                window.setTimeout(() => closeGallery(controller), 0);
            }
        });
        const outside = event => {
            if (!panel.classList.contains("is-open")) return;
            if (panel.contains(event.target) || launcher.contains(event.target)) return;
            closeGallery(controller);
        };
        document.addEventListener("pointerdown", outside, true);
        const reposition = () => {
            if (panel.classList.contains("is-open")) galleryPosition(launcher, panel);
        };
        window.addEventListener("resize", reposition);

        if (window.jQuery) {
            window.jQuery(modal).one("hidden.bs.modal.dco-drawing-workspace", () => {
                document.removeEventListener("pointerdown", outside, true);
                window.removeEventListener("resize", reposition);
                closeGallery(controller);
            });
        }
        return true;
    }

    function mount() {
        installStyles();
        const modal = visibleModal();
        if (!modal) return false;
        const root = modal.querySelector(".dco-special-sketch-shell");
        if (!root || root.dataset.dcoDrawingWorkspace === "1") return Boolean(root);
        const lineReady = patchLineTools(root);
        const exactReady = patchExactLinePanel(root);
        const templatesReady = patchTemplates(modal, root);
        if (!lineReady || !exactReady || !templatesReady) return false;
        root.dataset.dcoDrawingWorkspace = "1";
        return true;
    }

    function scheduleMount(attempt = 0) {
        window.setTimeout(() => {
            if (mount()) return;
            if (attempt + 1 < MOUNT_RETRIES) scheduleMount(attempt + 1);
        }, attempt ? 45 : 0);
    }

    function open(frm, row, options = {}) {
        const result = baseEditor.open(frm, row, options);
        if (!options.readOnly) scheduleMount();
        return result;
    }

    function view(frm, row) {
        return baseEditor.view(frm, row);
    }

    window.AlmdinaSpecialShapeEditor = Object.freeze({
        ...baseEditor,
        __drawingWorkspaceIntegrated: true,
        open,
        view,
    });
    window.AlmdinaDrawingWorkspaceUX = Object.freeze({
        installStyles,
        mount,
        patchLineTools,
        patchExactLinePanel,
        patchTemplates,
    });
})();
