from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
MANIFEST = ROOT / "frontend_assets.py"

def test_hooks_delegate_frontend_assets_to_one_manifest():
    hooks_source = HOOKS.read_text(encoding="utf-8")
    assert "from almdina_erp.frontend_assets import (" in hooks_source
    assert "app_include_js = [" not in hooks_source
    assert "doctype_js = {" not in hooks_source
    assert "doctype_list_js = {" not in hooks_source

    hooks = runpy.run_path(str(HOOKS))
    manifest = runpy.run_path(str(MANIFEST))
    for name in ("app_include_css", "app_include_js", "doctype_js", "doctype_list_js"):
        assert hooks[name] == manifest[name]


def test_global_asset_order_is_frozen_during_manifest_extraction():
    manifest = runpy.run_path(str(MANIFEST))
    css = manifest["app_include_css"]
    js = manifest["app_include_js"]
    responsive = "/assets/almdina_erp/css/door_cutting_order_responsive.css"
    presentation = "/assets/almdina_erp/css/door_cutting_order_form_presentation.css"
    sidebar = "/assets/almdina_erp/css/door_cutting_order_form_sidebar.css"
    assert css.count(presentation) == 1
    assert css.count(sidebar) == 1
    assert css.index(responsive) < css.index(presentation) < css.index(sidebar)
    assert len(js) == len(set(js)), "global app scripts must not be loaded twice"


def test_door_cutting_order_asset_order_is_frozen_during_manifest_extraction():
    manifest = runpy.run_path(str(MANIFEST))
    assets = manifest["doctype_js"]["Door Cutting Order"]
    context = "public/js/door_cutting_order/core/door_cutting_order_document_context.js"
    sidebar = "public/js/door_cutting_order/core/door_cutting_order_form_sidebar_controller.js"
    owner = "public/js/door_cutting_order/core/door_cutting_order_form_presentation_owner.js"
    edit = "public/js/door_cutting_order/core/door_cutting_order_edit_session_coordinator.js"
    header = "public/js/door_cutting_order/responsive/door_cutting_order_header_ux.js"
    toolbar = "public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js"
    for asset in (context, sidebar, owner, edit, header, toolbar):
        assert assets.count(asset) == 1, asset
    assert assets.index(context) < assets.index(sidebar) < assets.index(owner) < assets.index(edit)
    assert assets.index(owner) < assets.index(header) < assets.index(toolbar)
    assert manifest["doctype_js"]["Edge Banding Type"] == "public/js/edge_banding_type_ux.js"
    assert manifest["doctype_js"]["Production Routing"] == "public/js/production_routing_ux.js"
    assert manifest["doctype_js"]["Role"] == "public/js/role_form_ux.js"
    assert "Replacement Piece" not in manifest["doctype_js"]
    assert manifest["doctype_list_js"] == {
        "Door Cutting Order": "public/js/door_cutting_order/list_view/door_cutting_order_list.js",
    }
