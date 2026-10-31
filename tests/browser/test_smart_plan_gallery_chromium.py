"""Shipped gallery/session/renderer in Chromium; native save is tested in Frappe."""
import csv
import json
import os
from pathlib import Path

from test_error_diagnostics_chromium import browser, origin, ROOT  # noqa: F401


def setup_gallery(browser, origin, width):
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.goto(origin)
    with (ROOT / "almdina_erp/translations/ar.csv").open(newline="") as handle:
        catalog = {r[0]: r[1] for r in csv.reader(handle) if len(r) >= 2}
    plans = json.loads((ROOT / "almdina_erp/tests/fixtures/smart_plan_gallery.json").read_text())
    page.evaluate("""({catalog, plans}) => {
        document.documentElement.dir='rtl'; document.documentElement.lang='ar';
        document.body.innerHTML='<main id="workspace"></main>';
        window.__=(text,args=[])=>args.reduce((s,v,i)=>s.split(`{${i}}`).join(String(v)),catalog[text]||text);
        window.frappe={utils:{escape_html:text=>String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))},msgprint:()=>{throw Error('unexpected error dialog');}};
        window.calls={preview:0,select:0,commit:0,continue:0};
        window.settings={packing_mode:'smart',cutting_machine_type:'CNC Router',kerf_mm:3,trim_margin_mm:0,optimization_time_limit_sec:1};
        window.plans=plans.map((p,i)=>({...p,preview_candidate_id:'candidate-'+i}));
        window.candidates=plans.map((p,i)=>({candidate_id:'candidate-'+i,manufacturing_status:'Validated',summary:{
            settings,totals:{required_boards:p.sheets.length},quality:p.industrial_metrics,
            validation:{status:'Valid',needs_recalculation:false}}}));
        window.frm={doctype:'Door Cutting Order',doc:{name:'GALLERY',pieces:[],cutting_plan_json:JSON.stringify(plans[0])}};
        window.cur_frm=frm;window.savedBefore=frm.doc.cutting_plan_json;
        window.AlmdinaDocumentContext={formIdentity:f=>f.doc.name};
        window.AlmdinaPlanWorkspaceAPI={
            async preview(){calls.preview++;return {preview_version:2,preview_id:'token',order_name:'GALLERY',source_plan_name:'CP',
                source_plan_modified:'before',source_plan_revision:1,
                candidate_id:candidates[0].candidate_id,candidates,plan:window.plans[0],summary:candidates[0].summary,
                search_budget_sec:1,can_continue:true,expires_in_sec:900};},
            async selectCandidate(name,token,id){calls.select++;const i=candidates.findIndex(c=>c.candidate_id===id);
                return {preview_id:token,order_name:name,candidate_id:id,plan:window.plans[i],summary:candidates[i].summary};},
            async commitPreview(){calls.commit++;throw Error('selection must not save');},
            async continueSearch(){calls.continue++;return {...await this.preview(),preview_id:'next-token',can_continue:false};},
            async discardPreview(){}
        };
    }""", {"catalog": catalog, "plans": plans})
    public = ROOT / "almdina_erp/public"
    for script in [
        "almdina_ui.js",
        "door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js",
        "door_cutting_order/drawing/door_cutting_order_shape_output_contract.js",
        "door_cutting_order/cutting_plan/door_cutting_order_piece_geometry.js",
        "door_cutting_order/cutting_plan/door_cutting_order_cutting_plan_renderer.js",
        "door_cutting_order/cutting_plan/door_cutting_order_plan_preview_session.js",
        "door_cutting_order/cutting_plan/door_cutting_order_plan_preview_presenter.js",
    ]:
        page.add_script_tag(path=str(public / "js" / script))
    for css in ["almdina_components.css", "door_cutting_order_plan_workspace_layout.css"]:
        page.add_style_tag(path=str(public / "css" / css))
    page.add_style_tag(content="body{margin:16px;font:13px Arial;background:#f5f7fa;color:#172033;--card-bg:#fff;--border-color:#dce2e9;--text-muted:#687481}*{box-sizing:border-box}")
    page.evaluate("""async () => {
        const render=()=>{const owner=AlmdinaPlanPreviewSession;
            const canvas=AlmdinaCuttingPlanRender.build(frm,owner.previewPlan(frm));
            const root=document.getElementById('workspace');
            root.innerHTML=AlmdinaPlanPreviewPresenter.galleryMarkup(frm,canvas);
            AlmdinaPlanPreviewPresenter.bindGallery(frm,root);
        };
        window.AlmdinaPlanTabsUX={renderDualTabs:render};
        window.addEventListener('almdina:plan-preview-updated',render);
        await AlmdinaPlanPreviewSession.preview(frm,settings);render();
    }""")
    return page


def evidence(page, name):
    directory = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
    page.screenshot(path=str(directory / f"smart-gallery-{name}.png"), full_page=True)


def test_rtl_desktop_gallery_selects_without_save_or_optimization(browser, origin):
    page = setup_gallery(browser, origin, 1280)
    assert page.locator(".dco-candidate-card").count() == 5
    aside = page.locator(".dco-candidate-gallery").bounding_box()
    canvas = page.locator(".dco-candidate-canvas").bounding_box()
    assert aside["x"] + aside["width"] <= canvas["x"]
    assert page.locator(".dco-candidate-gallery").get_attribute("dir") == "rtl"
    assert "بدائل" in page.locator(".dco-candidate-gallery").inner_text()
    before = page.locator(".dco-candidate-canvas").inner_html()
    page.locator('[data-candidate-id="candidate-4"]').click()
    page.wait_for_function("AlmdinaPlanPreviewSession.snapshot(frm).payload.candidate_id==='candidate-4'")
    assert page.locator(".dco-candidate-canvas").inner_html() != before
    assert page.evaluate("frm.doc.cutting_plan_json===savedBefore")
    assert page.evaluate("calls") == {"preview": 1, "select": 1, "commit": 0, "continue": 0}
    evidence(page, "desktop-rtl")
    page.locator('[data-gallery-action="toggle"]').click()
    assert page.locator(".dco-candidate-layout").evaluate("el=>el.classList.contains('is-collapsed')")
    page.close()


def test_mobile_gallery_collapse_continue_and_single_plan(browser, origin):
    page = setup_gallery(browser, origin, 390)
    assert not page.locator(".dco-candidate-gallery__body").is_visible()
    page.locator('[data-gallery-action="toggle"]').click()
    assert page.locator(".dco-candidate-gallery__body").is_visible()
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    evidence(page, "mobile-rtl")
    page.locator('[data-gallery-action="continue"]').click()
    page.wait_for_function("AlmdinaPlanPreviewSession.snapshot(frm).previewId==='next-token'")
    assert page.locator('[data-gallery-action="continue"]').is_disabled()
    assert page.evaluate("calls.commit") == 0
    page.evaluate("candidates.splice(1);AlmdinaPlanPreviewSession.preview(frm,settings)")
    page.wait_for_function("document.querySelectorAll('.dco-candidate-card').length===1")
    assert "واحدة" in page.locator(".dco-candidate-gallery__intro").inner_text()
    page.close()
