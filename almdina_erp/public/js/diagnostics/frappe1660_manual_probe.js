(() => {
    "use strict";

    /**
     * Manual Desk/DCO probe for Frappe 16.60 compatibility.
     * Not loaded by app_include. Paste in the browser console:
     *
     *   const s = document.createElement("script");
     *   s.src = "/assets/almdina_erp/js/diagnostics/frappe1660_manual_probe.js?v=" + Date.now();
     *   document.head.appendChild(s);
     *
     * Then run:  AlmdinaFrappe1660Probe.run()
     * Optional isolation (CSS only, permissions stay server-side):
     *   AlmdinaFrappe1660Probe.isolateTheme(true)  // disable Almdina desk CSS
     *   AlmdinaFrappe1660Probe.isolateTheme(false) // restore
     */

    const THEME_HREF_PART = "almdina_desk_theme.css";
    const SIDEBAR_HREF_PART = "almdina_desk_sidebar.css";

    function cssVar(name, element) {
        const el = element || document.documentElement;
        return getComputedStyle(el).getPropertyValue(name).trim();
    }

    function sidebarSnapshot() {
        const container = document.querySelector(".body-sidebar-container");
        const panel = document.querySelector(".body-sidebar");
        const items = document.querySelectorAll(".body-sidebar .sidebar-item-container, .body-sidebar .standard-sidebar-item");
        const style = panel ? getComputedStyle(panel) : null;
        return {
            containerPresent: Boolean(container),
            panelPresent: Boolean(panel),
            expanded: Boolean(container && container.classList.contains("expanded")),
            hiddenClass: Boolean(container && container.classList.contains("sidebar-hidden")),
            itemCount: items.length,
            deskSidebarBg: cssVar("--desk-sidebar-bg"),
            surfaceMenuBar: cssVar("--surface-menu-bar"),
            almPrimary: cssVar("--alm-primary"),
            panelBackground: style ? style.backgroundColor : null,
            panelColor: style ? style.color : null,
            panelDisplay: style ? style.display : null,
            panelWidth: style ? style.width : null,
            sharedShell: document.body.classList.contains("almdina-shared-shell"),
            dockPinned: document.body.classList.contains("dock-pinned"),
            dockActive: document.body.classList.contains("dock-active"),
            bootHomeShell: window.frappe && frappe.boot && frappe.boot.home_shell,
            bootHasModuleSidebars: Boolean(
                window.frappe
                && frappe.boot
                && frappe.boot.module_sidebars
                && Object.keys(frappe.boot.module_sidebars).length
            ),
            frappeSidebar: Boolean(window.frappe && frappe.app && frappe.app.sidebar),
        };
    }

    function freezeSnapshot() {
        const freeze = document.querySelector(".freeze-wrapper, .flex.freeze");
        return {
            freezePresent: Boolean(freeze),
            freezeDisplay: freeze ? getComputedStyle(freeze).display : null,
            freezeMessage: freeze ? (freeze.textContent || "").trim().slice(0, 200) : null,
        };
    }

    function networkSnapshot() {
        const entries = performance.getEntriesByType("resource") || [];
        const recent = entries.slice(-40).map((entry) => ({
            name: entry.name,
            duration: Math.round(entry.duration),
            transferSize: entry.transferSize,
        }));
        const pendingGuess = recent.filter((entry) => entry.duration === 0).length;
        return { recentResourceCount: recent.length, zeroDurationRecent: pendingGuess, recent };
    }

    function formSnapshot() {
        const frm = window.cur_frm;
        if (!frm || frm.doctype !== "Door Cutting Order") {
            return { active: false };
        }
        const context = window.AlmdinaDocumentContext;
        const settleRun = frm.__almdinaSurfaceSettleRun || null;
        return {
            active: true,
            name: frm.doc && frm.doc.name,
            isNew: Boolean(frm.is_new && frm.is_new()),
            presentationActive: frm._dco_presentation_active,
            presentationReady: Boolean(
                window.AlmdinaDcoFormPresentationOwner
                && AlmdinaDcoFormPresentationOwner.isReady(frm)
            ),
            sidebarPreferenceApplied: Boolean(
                window.AlmdinaDcoFormSidebarController
                && AlmdinaDcoFormSidebarController.isPreferenceApplied(frm)
            ),
            settleRunActive: Boolean(settleRun),
            registeredSurfaces: context && context._surfaces
                ? context._surfaces.size
                : null,
        };
    }

    function installCounters() {
        if (window.__almdinaFrappe1660Counters) return window.__almdinaFrappe1660Counters;
        const counters = {
            recoverCalls: 0,
            settleCalls: 0,
            permissionApplyFrames: 0,
            startedAt: Date.now(),
        };
        const owner = window.AlmdinaDcoFormPresentationOwner;
        if (owner && typeof owner.recover === "function" && !owner.__almdinaProbeWrapped) {
            const original = owner.recover.bind(owner);
            owner.recover = function probedRecover(frm) {
                counters.recoverCalls += 1;
                return original(frm);
            };
            owner.__almdinaProbeWrapped = true;
        }
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.settleSurfaces === "function" && !context.__almdinaProbeWrapped) {
            const originalSettle = context.settleSurfaces.bind(context);
            context.settleSurfaces = function probedSettle(frm, attempt) {
                counters.settleCalls += 1;
                return originalSettle(frm, attempt);
            };
            context.__almdinaProbeWrapped = true;
        }
        window.__almdinaFrappe1660Counters = counters;
        return counters;
    }

    function isolateTheme(disable) {
        const links = [...document.querySelectorAll("link[rel='stylesheet']")];
        links.forEach((link) => {
            const href = String(link.getAttribute("href") || "");
            if (!href.includes(THEME_HREF_PART) && !href.includes(SIDEBAR_HREF_PART)) return;
            if (disable) {
                if (!link.dataset.almdinaProbeHref) {
                    link.dataset.almdinaProbeHref = href;
                    link.setAttribute("href", "about:blank");
                }
            } else if (link.dataset.almdinaProbeHref) {
                link.setAttribute("href", link.dataset.almdinaProbeHref);
                delete link.dataset.almdinaProbeHref;
            }
        });
        return sidebarSnapshot();
    }

    function run() {
        const counters = installCounters();
        const report = {
            at: new Date().toISOString(),
            elapsedMs: Date.now() - counters.startedAt,
            counters: { ...counters },
            sidebar: sidebarSnapshot(),
            freeze: freezeSnapshot(),
            form: formSnapshot(),
            network: networkSnapshot(),
        };
        console.log("[AlmdinaFrappe1660Probe]", report);
        return report;
    }

    function watch(ms = 8000) {
        installCounters();
        const started = Date.now();
        const samples = [];
        const timer = setInterval(() => {
            samples.push(run());
            if (Date.now() - started >= ms) {
                clearInterval(timer);
                console.log("[AlmdinaFrappe1660Probe.watch done]", {
                    samples: samples.length,
                    recoverCalls: window.__almdinaFrappe1660Counters.recoverCalls,
                    settleCalls: window.__almdinaFrappe1660Counters.settleCalls,
                });
            }
        }, 500);
        return { stop() { clearInterval(timer); } };
    }

    window.AlmdinaFrappe1660Probe = Object.freeze({
        run,
        watch,
        isolateTheme,
        sidebarSnapshot,
        installCounters,
    });

    console.info(
        "AlmdinaFrappe1660Probe ready. Call AlmdinaFrappe1660Probe.run() or .watch(8000)."
    );
})();
