"""Real Chromium, offline HTML and the existing preview controls (no Frappe site)."""

import os
from pathlib import Path
import shutil

import pytest

from almdina_erp.almdina_erp.application.cutting.search_report import SearchReport
from almdina_erp.almdina_erp.domain.cutting import optimizer
from almdina_erp.almdina_erp.domain.cutting.primitives import expand_piece_groups
from almdina_erp.almdina_erp.domain.cutting.search_trace import observe_search
from almdina_erp.almdina_erp.presentation.cutting.search_report_html import (
    render_search_report,
)


@pytest.fixture
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        executable = (
            os.environ.get("CHROMIUM_PATH")
            or shutil.which("chromium")
            or shutil.which("google-chrome")
        )
        instance = runtime.chromium.launch(executable_path=executable, headless=True)
        yield instance
        instance.close()


def recorded_round(previous=None):
    report = SearchReport(
        round_id=1 if previous else 0,
        parent_run_id=previous["run_id"] if previous else None,
    )
    if previous:
        report.metadata["previous_round"] = previous
    pieces = expand_piece_groups(
        [
            dict(
                piece_type="Glass", width_cm=22, length_cm=12, qty=1, glass_margin_mm=10
            ),
            dict(width_cm=4, length_cm=4, qty=1),
        ]
    )
    with observe_search(report):
        plan = optimizer.auto_fast(pieces, 40, 30, 0.3)
        report.gallery([], [plan], "published_preview")
    return report.export()


def test_report_offline_pages_rounds_and_exact_svg_contours(browser, tmp_path):
    previous = recorded_round()
    data = recorded_round(previous)
    # Text must stay text even when the browser parses the single-file artifact.
    data["candidates"][next(iter(data["candidates"]))][
        "source"
    ] = "<img src=x onerror=window.injected=1>"
    target = tmp_path / "report.html"
    target.write_text(render_search_report(data), encoding="utf-8")
    context = browser.new_context(offline=True, viewport={"width": 1280, "height": 800})
    page = context.new_page()
    errors, requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    page.goto(target.as_uri())
    assert page.locator("html").get_attribute("dir") == "rtl"
    assert data["report_id"] in page.locator("#report-identity").inner_text()
    for tab in ("journey", "candidates", "selection", "summary"):
        page.locator("#nav-" + tab).click()
        assert page.locator("#" + tab).is_visible()
    page.locator("#nav-journey").click()
    page.locator("#journey > details").first.locator("summary").first.click()
    assert page.locator("#journey details[open]").count() == 1
    page.locator("#nav-selection").click()
    page.locator("#selection .panel button").first.click()
    assert page.locator("#candidates svg path").count() >= 2
    signature = data["final_gallery"][0]["geometry_fingerprint"]
    recorded = data["geometries"][signature]["sheets"][0]["pieces"][0]
    expected = " ".join(
        "M " + " L ".join(" ".join(str(x) for x in p) for p in ring) + " Z"
        for ring in [recorded["outline_cm"], *recorded["holes_cm"]]
    )
    # Numeric formatting differs only for integral floats between Python and JS.
    path = page.locator("#candidates svg path").first.get_attribute("d")
    import re

    numbers = lambda value: [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", value)]
    assert numbers(path) == numbers(expected)
    assert path.count("M ") == 1 + len(recorded["holes_cm"])
    assert not page.locator("img").count()
    assert page.evaluate("window.injected") is None
    page.locator("#rounds select").select_option("1")
    assert previous["report_id"] in page.locator("#report-identity").inner_text()
    assert page.locator("#summary").is_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    for tab in ("candidates", "selection", "journey", "summary"):
        page.locator("#nav-" + tab).click()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not errors
    assert all(url.startswith("file:") for url in requests)
    context.close()


def test_existing_plan_controls_opt_in_permissions_lifecycle_and_repeated_refresh(
    browser,
):
    page = browser.new_page()
    page.set_content('<div id="actions"></div>')
    page.evaluate("""() => {
      class Wrapper {
        constructor(nodes) { this.nodes=nodes; this.length=nodes.length; }
        get(index) { return this.nodes[index]; }
        find(selector) { return new Wrapper(this.nodes.flatMap(n=>[...n.querySelectorAll(selector)])); }
        children(selector) { return new Wrapper(this.nodes.flatMap(n=>[...n.children].filter(c=>!selector||c.matches(selector)))); }
        first() { return new Wrapper(this.nodes.slice(0,1)); }
        remove() { this.nodes.forEach(n=>n.remove()); return this; }
        on() { return this; }
        append(value) { this.nodes.forEach(n=>n.insertAdjacentHTML('beforeend',value)); return this; }
      }
      window.$=value=>new Wrapper(typeof value==='string'?[...document.querySelectorAll(value)]:[value]);
      window.__=String;
      window.frappe={ui:{form:{on(){}}},call(){return Promise.resolve({message:{}});}};
      window.grants=new Set(['download_cutting_search_report','view_system_cutting_plan','recalculate_plan']);
      window.AlmdinaPermissions={canDocument(_frm,capability){return grants.has(capability);}};
      window.state={status:'ready',editing:false,data:{plans:{system_draft:{status:'Draft'}}}};
      window.AlmdinaPlanWorkspaceState={snapshot(){return state;}};
      window.AlmdinaPlanPreviewSession={preview(){},isBusy(){return false;}};
      window.cur_frm={doctype:'Door Cutting Order',doc:{name:'DCO-1',status:'Draft'},is_new:()=>false,
        fields_dict:{plan_control_actions:{$wrapper:$('#actions')}}};
    }""")
    root = (
        Path(__file__).resolve().parents[1]
        / "public/js/door_cutting_order/cutting_plan"
    )
    for name in (
        "door_cutting_order_plan_workspace_api.js",
        "door_cutting_order_plan_controls_ux.js",
    ):
        page.add_script_tag(path=str(root / name))
    apply = lambda: page.evaluate("AlmdinaPlanControlsUX.apply(cur_frm)")
    apply()
    check = page.locator(".dco-search-report-controls input")
    assert not check.is_checked()
    assert check.is_disabled()
    page.evaluate("state.editing=true")
    apply()
    assert check.is_enabled()
    check.check()
    apply()
    apply()
    assert page.locator(".dco-search-report-controls").count() == 1
    assert check.is_checked()
    page.evaluate(
        "cur_frm.__almdinaSearchReport={orderName:'DCO-1',report_id:'a'.repeat(32)};state.editing=false;"
    )
    apply()
    assert check.is_disabled()
    assert page.locator(".dco-search-report-controls a").count() == 2
    assert "report_id=" in page.locator(
        ".dco-search-report-controls a"
    ).first.get_attribute("href")
    page.evaluate("grants.delete('download_cutting_search_report')")
    apply()
    assert page.locator(".dco-search-report-controls").count() == 0
    page.evaluate(
        "grants.add('download_cutting_search_report');cur_frm.doc.name='DCO-2'"
    )
    apply()
    assert not page.locator(".dco-search-report-controls input").is_checked()
    assert page.locator(".dco-search-report-controls a").count() == 0
    page.close()
