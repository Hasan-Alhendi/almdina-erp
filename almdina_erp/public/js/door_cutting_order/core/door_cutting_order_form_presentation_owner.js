(() => {
    "use strict";

    const DOCTYPE = "Door Cutting Order";
    const ROOT_CLASS = "dco-operator-form";
    const PLACEHOLDER_CLASS = "dco-tabs-fixed-placeholder";
    const SURFACE_NAME = "dco-form-presentation";
    const OWNER_KEY = "__almdinaDcoFormPresentationOwner";
    const HIDE_EVENT = "hide.almdinaDcoFormPresentation";

    function node(value) {
        if (!value) return null;
        return value.nodeType ? value : (value[0] && value[0].nodeType ? value[0] : null);
    }

    function connected(value) {
        const element = node(value);
        return Boolean(element && element.isConnected);
    }

    function acquire(frm) {
        const root = node(frm && frm.wrapper);
        if (!connected(root)) return null;

        const pageWrapper = node(frm.page && frm.page.wrapper);
        const pageContainer = root.closest(".page-container")
            || root.closest(".desk-page")
            || (pageWrapper && (pageWrapper.closest(".page-container") || pageWrapper.closest(".desk-page")))
            || pageWrapper;
        const head = (pageContainer && pageContainer.querySelector(".page-head"))
            || (root.parentElement && root.parentElement.querySelector(".page-head"));
        const tabsList = root.querySelector(".form-tabs-list");
        const tabs = tabsList || root.querySelector(".form-tabs");
        if (!connected(head) || !connected(tabs)) return null;
        return { root, pageWrapper, pageContainer: pageContainer || root, head, tabs };
    }

    function primeShell(frm) {
        const root = node(frm && frm.wrapper);
        if (!connected(root)) return false;
        frm._dco_presentation_active = true;
        const pageWrapper = node(frm.page && frm.page.wrapper);
        const pageContainer = root.closest(".page-container")
            || root.closest(".desk-page")
            || (pageWrapper && (pageWrapper.closest(".page-container") || pageWrapper.closest(".desk-page")))
            || pageWrapper;
        const head = (pageContainer && pageContainer.querySelector(".page-head"))
            || (root.parentElement && root.parentElement.querySelector(".page-head"));
        root.classList.add(ROOT_CLASS);
        if (pageContainer && pageContainer.isConnected) pageContainer.classList.add("dco-form-presentation-shell");
        if (head && head.isConnected) head.classList.add("dco-responsive-head", "dco-stable-actions-head");
        return true;
    }

    function ensurePlaceholder(root, tabs) {
        const placeholders = [...root.querySelectorAll(`.${PLACEHOLDER_CLASS}`)];
        let placeholder = tabs.previousElementSibling;
        if (!placeholder || !placeholder.classList.contains(PLACEHOLDER_CLASS)) {
            placeholder = placeholders.find(item => item.isConnected) || null;
            if (!placeholder) {
                placeholder = document.createElement("div");
                placeholder.className = PLACEHOLDER_CLASS;
            }
            tabs.parentNode.insertBefore(placeholder, tabs);
        }
        placeholders.forEach(item => {
            if (item !== placeholder) item.remove();
        });
        return placeholder;
    }

    function presentationNodes(frm, createPlaceholder = true) {
        const current = acquire(frm);
        if (!current) return null;
        const placeholder = createPlaceholder
            ? ensurePlaceholder(current.root, current.tabs)
            : current.tabs.previousElementSibling;
        return { ...current, placeholder };
    }

    function clearShell(frm) {
        const root = frm._dco_presentation_root;
        const head = frm._dco_presentation_head;
        const pageContainer = frm._dco_presentation_page_container;
        const tabs = frm._dco_fixed_tabs;
        const placeholder = frm._dco_tabs_placeholder;
        if (root) root.classList.remove(ROOT_CLASS);
        if (pageContainer) pageContainer.classList.remove("dco-form-presentation-shell");
        if (head) head.classList.remove("dco-responsive-head", "dco-stable-actions-head");
        if (tabs) tabs.classList.remove("dco-sticky-tabs", "dco-tabs-is-fixed");
        if (placeholder && placeholder.isConnected) placeholder.remove();

        const header = window.AlmdinaDcoHeaderUx;
        if (header && typeof header.suspendPresentation === "function") header.suspendPresentation(frm);
        const toolbar = window.AlmdinaDcoToolbarStabilityUx;
        if (toolbar && typeof toolbar.suspendPresentation === "function") toolbar.suspendPresentation(frm);

        frm._dco_presentation_root = null;
        frm._dco_presentation_head = null;
        frm._dco_presentation_page_container = null;
        frm._dco_fixed_tabs = null;
        frm._dco_tabs_placeholder = null;
        frm._dco_presentation_active = false;
    }

    function bindPageLifecycle(frm, nodes) {
        const pageRoot = nodes.pageWrapper || nodes.pageContainer;
        if (!pageRoot || !pageRoot.isConnected) return;
        if (frm._dco_presentation_bound_page_root === pageRoot) return;
        const previous = frm._dco_presentation_bound_page_root;
        const previousHandler = frm._dco_presentation_hide_handler;
        if (previous && previousHandler && window.jQuery) {
            window.jQuery(previous).off(HIDE_EVENT, previousHandler);
        }
        const handleHide = () => {
            if (frm._dco_presentation_bound_page_root !== pageRoot) return;
            window.jQuery && window.jQuery(pageRoot).off(HIDE_EVENT, handleHide);
            frm._dco_presentation_bound_page_root = null;
            frm._dco_presentation_hide_handler = null;
            clearShell(frm);
        };
        if (window.jQuery) window.jQuery(pageRoot).on(HIDE_EVENT, handleHide);
        frm._dco_presentation_bound_page_root = pageRoot;
        frm._dco_presentation_hide_handler = handleHide;
    }

    function clearReplacedNodes(frm, current) {
        const previous = [
            [frm._dco_presentation_root, current.root, ROOT_CLASS],
            [frm._dco_presentation_page_container, current.pageContainer, "dco-form-presentation-shell"],
            [frm._dco_presentation_head, current.head, "dco-responsive-head", "dco-stable-actions-head"],
            [frm._dco_fixed_tabs, current.tabs, "dco-sticky-tabs", "dco-tabs-is-fixed"],
        ];
        previous.forEach(([oldNode, newNode, ...classes]) => {
            if (oldNode && oldNode !== newNode) oldNode.classList.remove(...classes);
        });
        if (frm._dco_tabs_placeholder && frm._dco_tabs_placeholder !== current.placeholder) {
            frm._dco_tabs_placeholder.remove();
        }
    }

    function isReady(frm) {
        const current = presentationNodes(frm, false);
        if (!current || !connected(current.placeholder)) return false;
        const ready = current.root.classList.contains(ROOT_CLASS)
            && current.pageContainer.classList.contains("dco-form-presentation-shell")
            && frm._dco_presentation_page_container === current.pageContainer
            && current.head.classList.contains("dco-responsive-head")
            && current.head.classList.contains("dco-stable-actions-head")
            && current.tabs.classList.contains("dco-sticky-tabs")
            && current.placeholder.isConnected
            && current.placeholder.nextElementSibling === current.tabs
            && frm._dco_fixed_tabs === current.tabs
            && frm._dco_tabs_placeholder === current.placeholder
            && frm._dco_presentation_head === current.head
            && frm._dco_presentation_root === current.root;
        const header = window.AlmdinaDcoHeaderUx;
        const toolbar = window.AlmdinaDcoToolbarStabilityUx;
        const adaptersReady = (!header || typeof header.isReady !== "function" || header.isReady(frm, current))
            && (!toolbar || typeof toolbar.isReady !== "function" || toolbar.isReady(frm, current.head));
        const sidebar = window.AlmdinaDcoFormSidebarController;
        return Boolean(
            ready
            && adaptersReady
            && (!sidebar || typeof sidebar.isPreferenceApplied !== "function" || sidebar.isPreferenceApplied(frm))
        );
    }

    function recover(frm) {
        if (!frm || frm.doctype !== DOCTYPE || frm._dco_presentation_active === false) return false;
        const current = presentationNodes(frm);
        if (!current) return false;
        clearReplacedNodes(frm, current);

        // The page shell owns these classes; feature renderers own only content
        // inside the form and never decide whether the DCO is themed.
        current.root.classList.add(ROOT_CLASS);
        current.pageContainer.classList.add("dco-form-presentation-shell");
        current.head.classList.add("dco-responsive-head", "dco-stable-actions-head");
        current.tabs.classList.add("dco-sticky-tabs");

        frm._dco_presentation_root = current.root;
        frm._dco_presentation_head = current.head;
        frm._dco_presentation_page_container = current.pageContainer;
        frm._dco_fixed_tabs = current.tabs;
        frm._dco_tabs_placeholder = current.placeholder;
        bindPageLifecycle(frm, current);

        const sidebar = window.AlmdinaDcoFormSidebarController;
        if (sidebar && typeof sidebar.mount === "function") sidebar.mount(frm);

        const header = window.AlmdinaDcoHeaderUx;
        if (header && typeof header.recoverPresentation === "function") {
            header.recoverPresentation(frm, current);
        }
        const toolbar = window.AlmdinaDcoToolbarStabilityUx;
        if (toolbar && typeof toolbar.recoverPresentation === "function") {
            toolbar.recoverPresentation(frm, current.head);
        }
        return isReady(frm);
    }

    const owner = Object.freeze({ recover, isReady });
    window[OWNER_KEY] = owner;
    window.AlmdinaDcoFormPresentationOwner = owner;

    const context = window.AlmdinaDocumentContext;
    if (context && typeof context.registerSurface === "function") {
        context.registerSurface(SURFACE_NAME, {
            isReady,
            recover,
        });
    }

    frappe.ui.form.on(DOCTYPE, {
        before_load(frm) { primeShell(frm); },
        onload_post_render(frm) { recover(frm); },
        refresh(frm) { recover(frm); },
    });

    if (typeof window.addEventListener === "function") {
        [
            "almdina:permissions-updated",
            "almdina:stage-context-ready",
            "almdina:surfaces-settled",
        ].forEach(eventName => {
            window.addEventListener(eventName, event => {
                const frm = (event && event.detail && event.detail.frm) || window.cur_frm;
                if (frm && frm.doctype === DOCTYPE && frm._dco_presentation_active && window.cur_frm === frm) recover(frm);
            });
        });
    }
})();
