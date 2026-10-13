"""Evidence collection on an ephemeral, version-pinned Frappe Desk site."""

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def test_cross_order_desk_runtime():
    fixture = json.loads(Path(os.environ["P0_FIXTURE_PATH"]).read_text())
    evidence_dir = Path(os.environ["P0_EVIDENCE_DIR"])
    evidence_dir.mkdir(parents=True, exist_ok=True)
    a, b = fixture["orders"]["A"], fixture["orders"]["B"]
    evidence = {"versions": fixture["versions"], "orders": fixture["orders"], "stages": {}}
    page = None
    diagnostics = []

    def stage(name, callback):
        try:
            evidence["stages"][name] = {"status": "OBSERVED", "value": callback()}
        except Exception as exc:
            evidence["stages"][name] = {"status": "NOT_TESTED", "reason": repr(exc)}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(accept_downloads=False)
            page.on("pageerror", lambda error: diagnostics.append({"kind": "pageerror", "message": str(error)[:500]}))
            page.on("console", lambda message: diagnostics.append({"kind": "console", "message": message.text[:500]})
                    if message.type == "error" else None)
            page.on("response", lambda response: diagnostics.append({"kind": "http", "url": response.url.split("?")[0],
                    "status": response.status}) if response.status >= 400 else None)
            page.goto(os.environ["FRAPPE_DESK_URL"] + "/login", wait_until="domcontentloaded")
            page.locator("#login_email").fill("Administrator")
            page.locator("#login_password").fill(os.environ["P0_ADMIN_PASSWORD"])
            page.locator(".btn-login").click()
            page.wait_for_function("!!window.frappe?.set_route && frappe.session?.user === 'Administrator'", timeout=60000)
            page.wait_for_function("!!window.frappe?.boot?.sysdefaults?.setup_complete && !!frappe.router && !!frappe.app", timeout=45000)

            def route(name, initial=False):
                if initial:
                    page.goto(os.environ["FRAPPE_DESK_URL"] + "/app/door-cutting-order/" + name,
                              wait_until="domcontentloaded", timeout=60000)
                else:
                    page.evaluate("name => frappe.set_route('Form', 'Door Cutting Order', name)", name)
                try:
                    page.wait_for_function("name => window.cur_frm?.doc?.name === name", arg=name, timeout=45000)
                except Exception:
                    snapshot = page.evaluate("""() => ({href:location.href,
                        route:frappe.get_route?.(),curName:window.cur_frm?.doc?.name,
                        doctype:window.cur_frm?.doctype,bootReady:!!frappe.boot?.sysdefaults?.setup_complete,
                        visibleText:document.body.innerText.slice(-1200)})""")
                    evidence["route_failure"] = {"requested": name, "initial": initial,
                                                 "snapshot": snapshot, "diagnostics": diagnostics[-30:]}
                    print("P0_ROUTE_DIAGNOSTIC=" + json.dumps(evidence["route_failure"], ensure_ascii=False), flush=True)
                    raise
                page.wait_for_function("!!window.AlmdinaCostWorkspaceState && !!window.AlmdinaCuttingPlanRender", timeout=45000)
                return page.evaluate("""() => ({
                    name: cur_frm.doc.name,
                    board: cur_frm.doc.board_description,
                    pieces: cur_frm.doc.pieces.map(p => ({name:p.name,width_cm:p.width_cm,length_cm:p.length_cm})),
                    input: cur_frm.fields_dict.board_description?.$input?.val() ?? null,
                    cost: AlmdinaCostWorkspaceState.snapshot(cur_frm),
                    plan: AlmdinaPlanWorkspaceState.snapshot(cur_frm)
                })""")

            state_a = route(a["name"], initial=True)
            page.evaluate("""() => {
                window.__p0FrmA = cur_frm;
                window.__p0DocA = cur_frm.doc;
                window.__p0Events = [];
                for (const event of ['before_load','onload','refresh']) {
                    frappe.ui.form.on('Door Cutting Order', {[event]: frm => {
                        window.__p0Events.push({event, name:frm.doc.name,
                            sameFrm:frm === window.__p0FrmA,
                            costStatus:window.AlmdinaCostWorkspaceState?.snapshot(frm)?.status,
                            planStatus:window.AlmdinaPlanWorkspaceState?.snapshot(frm)?.status});
                    }});
                }
            }""")
            state_b = route(b["name"])
            evidence["stages"]["lifecycle"] = {"status": "OBSERVED", "value": {
                "a": state_a, "b": state_b,
                "transition": page.evaluate("""() => ({sameFrm:cur_frm===window.__p0FrmA,
                    sameDoc:cur_frm.doc===window.__p0DocA,
                    events:window.__p0Events,
                    aCostReadOnB:AlmdinaCostWorkspaceState.snapshot(cur_frm)?.data?.order?.board_description,
                    model:cur_frm.doc.board_description,
                    input:cur_frm.fields_dict.board_description?.$input?.val() ?? null})""")}}

            def save_probe():
                # A real A-shaped workspace snapshot, projected through the production
                # presenter on B. Record this as controlled injection, not natural navigation.
                projected = page.evaluate("""args => {
                    const frm = cur_frm, owner = AlmdinaCostWorkspaceState;
                    const original = {board:frm.doc.board_description,
                        width:frm.doc.pieces[0].width_cm};
                    const store = owner.storeFor(frm);
                    const identity = AlmdinaDocumentContext.formIdentity(window.__p0FrmA);
                    store.reset(identity);
                    const requestId = store.beginLoad(identity);
                    store.resolveLoad(identity,requestId,{order_name:args.a.name,
                        order:{board_description:args.a.board},
                        pieces:[{name:args.a.piece_name,width_cm:args.a.width_cm}]});
                    const accepted = AlmdinaCostWorkspacePresenterAdapter.project(frm);
                    return {original, accepted, model:frm.doc.board_description,
                        width:frm.doc.pieces[0].width_cm,
                        input:frm.fields_dict.board_description?.$input?.val() ?? null,
                        state:owner.snapshot(frm)?.identity};
                }""", {"a": a})
                payloads = []

                def capture(request):
                    if "savedocs" in request.url:
                        payloads.append({"url": request.url, "body": request.post_data})

                page.on("request", capture)
                try:
                    save_result = page.evaluate("""async () => {
                        cur_frm.dirty();
                        try { await cur_frm.save(); return {ok:true,board:cur_frm.doc.board_description}; }
                        catch(error) { return {ok:false,error:String(error),board:cur_frm.doc.board_description}; }
                    }""")
                finally:
                    page.remove_listener("request", capture)
                # Read server state through frappe.client.get, which uses the DB rather
                # than the open form's local document cache.
                db = page.evaluate("""async name => {
                    const response = await frappe.call({method:'frappe.client.get',
                        args:{doctype:'Door Cutting Order',name}});
                    return {name:response.message.name,
                        board:response.message.board_description,
                        pieces:response.message.pieces.map(p=>({name:p.name,width_cm:p.width_cm}))};
                }""", b["name"])
                return {"method": "controlled A cost store projected on B via production presenter",
                        "projected": projected, "save": save_result,
                        "native_savedocs_requests": payloads, "db": db}

            stage("save", save_probe)
            # Re-open B to remove the save probe's local state before print evidence.
            page.reload(wait_until="domcontentloaded")
            state_b_print = route(b["name"])

            def print_probe():
                page.evaluate("args => {window.__p0Args=args}", {"a": a})
                # Capture popup writes and hold the real renderer at its async identity boundary.
                page.evaluate("""() => {
                    window.__p0PrintWrites=[];
                    window.__p0OldOpen=window.open;
                    window.open=()=>({document:{open(){},write(html){window.__p0PrintWrites.push(html)},close(){}},close(){}});
                    window.__p0OldIdentity=AlmdinaFactoryPrintIdentity;
                    window.AlmdinaFactoryPrintIdentity={...window.__p0OldIdentity,
                        get:()=>new Promise(resolve=>window.__p0ResolveIdentity=resolve)};
                    const a=window.__p0Args.a;
                    const plan={name:'P0-PLAN-A',revision:'P0-REV-A',
                        full_board_width_cm:122,full_board_length_cm:244,
                        usable_board_width_cm:122,usable_board_length_cm:244,
                        sheets:[{sheet_no:1,pieces:[{x:0,y:0,w:a.width_cm,h:a.length_cm,
                            original_w:a.width_cm,original_h:a.length_cm,
                            label:'P0-A-GEOMETRY',piece_type:'Regular',rotated:false}]}]};
                    window.__p0PrintResult=AlmdinaCuttingPlanRender.print(cur_frm,plan);
                }""")
                page.wait_for_function("!!window.__p0ResolveIdentity", timeout=10000)
                before = page.evaluate("""() => ({name:cur_frm.doc.name,
                    writes:window.__p0PrintWrites.length})""")
                # Route change while identity lookup is pending is a real Desk navigation.
                state_a_during = route(a["name"])
                page.evaluate("""() => window.__p0ResolveIdentity({})""")
                page.wait_for_function("window.__p0PrintWrites.length >= 2", timeout=10000)
                html = page.evaluate("window.__p0PrintWrites.at(-1)")
                (evidence_dir / "final-print.html").write_text(html, encoding="utf-8")
                result = page.evaluate("""async () => await window.__p0PrintResult""")
                return {"method": "production renderer with controlled A geometry and deferred identity; real B to A Desk route",
                        "before": before, "a_during": state_a_during, "result": result,
                        "html_file": "final-print.html", "html_checks": {
                            "dco_a": a["name"] in html, "dco_b": b["name"] in html,
                            "board_a": a["board"] in html, "board_b": b["board"] in html,
                            "geometry_a": "P0-A-GEOMETRY" in html,
                            "plan_name": "P0-PLAN-A" in html,
                            "revision": "P0-REV-A" in html,
                            "header": "dco-print" in html}}

            stage("print", print_probe)
            stage("recovery", lambda: page.evaluate("""() => ({
                available:!!window.AlmdinaDcoRecovery,
                api:window.AlmdinaDcoRecovery?Object.keys(window.AlmdinaDcoRecovery):[],
                currentName:cur_frm?.doc?.name,
                isNew:!!cur_frm?.is_new?.()
            })"""))
            page.screenshot(path=str(evidence_dir / "desk.png"), full_page=True)
        finally:
            evidence["diagnostics"] = diagnostics[-30:]
            if page:
                try:
                    page.screenshot(path=str(evidence_dir / "last-desk.png"), full_page=True)
                except Exception:
                    pass
            (evidence_dir / "runtime-evidence.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            browser.close()
    assert all(evidence["stages"].get(gate, {}).get("status") == "OBSERVED"
               for gate in ("lifecycle", "save", "print")), evidence
