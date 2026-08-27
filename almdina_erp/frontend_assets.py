"""Central frontend asset manifest for Almdina ERP.

The ordering in these lists is runtime-significant. Keep feature ownership here and
change ordering only with an explicit dependency/behavior change and regression
coverage.
"""

app_include_css = [
    "/assets/almdina_erp/css/door_cutting_order_responsive.css",
    "/assets/almdina_erp/css/door_cutting_order_extra_addons.css",
]

app_include_js = [
    "/assets/almdina_erp/js/permission_context.js",
    "/assets/almdina_erp/js/frontend_foundation.js",
    "/assets/almdina_erp/js/page_revisit_refresh.js",
    "/assets/almdina_erp/js/responsive_device.js",
    "/assets/almdina_erp/js/shop_floor_quick_actions.js",
    "/assets/almdina_erp/js/shared_shell.js",
    "/assets/almdina_erp/js/arabic_operator_ui.js",
    "/assets/almdina_erp/js/input_stability.js",
    "/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js",
    "/assets/almdina_erp/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js",
    "/assets/almdina_erp/js/door_cutting_order/cutting_plan/secure_dxf_export.js",
    "/assets/almdina_erp/js/door_cutting_order/cutting_plan/door_cutting_order_drawing_plan_ux.js",
]

doctype_js = {
    "Door Cutting Order": [
        # The document context owns the surface-readiness registry, so it must be
        # evaluated before any module that registers a probe with it.
        "public/js/door_cutting_order/core/door_cutting_order_document_context.js",
        "public/js/permission_context.js",
        # A5 aggregate workspace state exists before any Plan/Cost consumer.
        "public/js/door_cutting_order/core/door_cutting_order_workspace_store.js",
        # Freshness coordination is a shared application primitive. Feature state
        # owners register with it after evaluation; it owns no Plan/Cost policy.
        "public/js/door_cutting_order/core/door_cutting_order_workspace_sync_coordinator.js",
        "public/js/door_cutting_order/core/door_cutting_order_workspace_field_editor.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_state.js",
        # Plan previews are transient UI experiments layered over canonical Plan
        # workspace state. They must exist before any renderer/action consumes a
        # preview while the persisted workspace remains the source of truth.
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_session.js",
        "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_api.js",
        "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_state.js",
        # Frappe tab activation is a DCO lifecycle concern, not a responsibility
        # of the reusable workspace coordinator. Load this adapter only after both
        # derived workspace states have registered their activation fields.
        "public/js/door_cutting_order/core/door_cutting_order_workspace_activation_lifecycle.js",
        # DCO-specific dependency policy is deliberately separate from the shared
        # freshness primitive: only this feature knows which inputs affect Plan,
        # Cost, or the special-price basis.
        "public/js/door_cutting_order/order_entry/door_cutting_order_mutation_impact_policy.js",
        "public/js/door_cutting_order/printing/door_cutting_order_print_identity.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_cutting_plan_renderer.js",
        "public/js/door_cutting_order/order_entry/door_cutting_order_defaults.js",
        "public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js",
        "public/js/door_cutting_order/printing/door_cutting_order_shape_print.js",
        # Extra-door selection owns only customer requirements and cost impact;
        # it is evaluated before the operator renderer consumes its type-cell API.
        "public/js/door_cutting_order/order_entry/extra_addons/door_cutting_order_extra_addons_ux.js",
        "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js",
        # Presentation-only owner for the native Order tab fields. It does not
        # duplicate document state or save commands; it only arranges the existing
        # Frappe controls into the compact intake/material/measurements hierarchy.
        "public/js/door_cutting_order/order_entry/door_cutting_order_order_tab_layout_ux.js",
        # Qty+Enter is a focused keyboard behavior layered on the operator's
        # existing row materialization/model-sync contract; it owns no rendering.
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_fast_entry_keyboard_ux.js",
        # Measurement features keep their existing Frappe hook order; this owner
        # only centralizes cancellable frame/timer work for FE-ARCH-008.
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_lifecycle.js",
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_bulk_rows_ux.js",
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_keyboard_columns_ux.js",
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_compact_measurements_ux.js",
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js",
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_toolbar_ux.js",
        "public/js/door_cutting_order/drawing/special_shape_facade.js",
        "public/js/door_cutting_order/core/door_cutting_order_action_permission_guard.js",
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_resilience_ux.js",
        "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_table_performance_ux.js",
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js",
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_controls_ux.js",
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_double_click_guard.js",
        # Multi-edge/profile modules keep their feature APIs, while one structural
        # runtime owner prevents their historical broad observers from competing.
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_render_owner.js",
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_cut_dimensions_ux.js",
        "public/js/door_cutting_order/printing/door_cutting_order_document_print_theme.js",
        "public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js",
        "public/js/door_cutting_order/costing/door_cutting_order_multi_edge_documents_ux.js",
        "public/js/door_cutting_order/printing/door_cutting_order_document_compactness_ux.js",
        "public/js/door_cutting_order/costing/door_cutting_order_cost_presenter.js",
        # A5.2 keeps the existing visual presenter but feeds it exclusively from
        # Cost workspace state through a read-only compatibility projection.
        "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_presenter_adapter.js",
        "public/js/door_cutting_order/costing/door_cutting_order_cost_permissions_ux.js",
        # Preserve the established secure-document ownership chain: the financial
        # documents presenter must remain immediately after cost permissions.
        "public/js/door_cutting_order/costing/door_cutting_order_financial_documents_ux.js",
        "public/js/door_cutting_order/costing/door_cutting_order_customer_invoice_toolbar_ux.js",
        # Cost edit intent owns only the Cost workspace draft. Native DCO fields
        # remain read-only and detached controls occupy the same visual surface.
        "public/js/door_cutting_order/costing/door_cutting_order_cost_edit_session_ux.js",
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_color_ux.js",
        "public/js/door_cutting_order/order_entry/door_cutting_order_board_text_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_save_render_performance_ux.js",
        # The DXF upload owner is form-scoped and evaluated before plan_ux. This
        # guarantees the upload button always reaches the private + unattached
        # flow instead of plan_ux's legacy document-attached fallback.
        "public/js/door_cutting_order/cutting_plan/secure_dxf_upload.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_text_board_plan_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_fast_save_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js",
        # F6.3 keeps the existing content hook position while loading its local
        # presentation owners immediately before the orchestrator.
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_content_styles.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_board_presenter.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_content_ux.js",
        # Contextual actions are a presentation/controller layer over the already
        # loaded Plan workspace + command APIs. Tabs own placement; this owner owns
        # only the commands for whichever plan tab the operator is viewing.
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_context_actions_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_tabs_ux.js",
        # A5.2 replaces DCO plan JSON reads and the approved-plan side RPC with the
        # capability-scoped Plan workspace snapshot while preserving the same UI.
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_presenter_adapter.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_surface_bootstrap.js",
        "public/js/door_cutting_order/core/door_cutting_order_tab_permissions_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_permission_refresh_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_drawing_plan_ux.js",
        "public/js/door_cutting_order/responsive/door_cutting_order_header_ux.js",
        "public/js/door_cutting_order/production/shop_floor_order_ux.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_drawing_approval_ux.js",
        "public/js/door_cutting_order/cutting_plan/secure_dxf_export.js",
        "public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js",
        "public/js/door_cutting_order/core/door_cutting_order_revision_ux.js",
        # Explicit Order-save intent must win over any transient plan-checkpoint
        # preserve marker before Frappe evaluates after_save.
        "public/js/door_cutting_order/core/door_cutting_order_edit_save_intent_ux.js",
        "public/js/door_cutting_order/core/order_lifecycle.js",
        "public/js/input_stability.js",
        "public/js/door_cutting_order/responsive/door_cutting_order_mobile_cards_ux.js",
        # Explicit user intent remains separate from capability/stage policy.
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_edit_session_ux.js",
        # Preview presentation is a pure renderer; the interaction controller
        # owns Edit -> many previews -> exact Save/Cancel and delegates all visuals.
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_presenter.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_edit_ux.js",
        # The page coordinator owns only the visible top action and delegates
        # Order / Cutting Plan / Cost editing to their established session owners.
        "public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js",
        # Keep the read-only Plan settings card outside plan_control_actions so
        # command-surface rerenders cannot remove it.
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_settings_summary_ux.js",
        # A5.3 is presentation-only. It reads Plan/Cost workspace snapshots after
        # their edit/page coordinators and never becomes a state or command owner.
        "public/js/door_cutting_order/core/door_cutting_order_plan_cost_workspace_visual_ux.js",
        # Freshness UX is presentation-only and deliberately late: it annotates the
        # already-rendered Cost surface and never owns pricing or persistence.
        "public/js/door_cutting_order/core/door_cutting_order_workspace_freshness_ux.js",
        # Final field-status owner on purpose: no later compatibility layer may
        # re-open native plan inputs. Workspace-owned detached controls remain the
        # only writable Plan settings surface during a Plan edit session.
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_field_access_adapter.js",
    ],
    "Edge Banding Type": "public/js/edge_banding_type_ux.js",
    "Production Routing": "public/js/production_routing_ux.js",
    "Replacement Piece": [
        "public/js/permission_context.js",
        "public/js/replacement_piece.js",
    ],
}

doctype_list_js = {
    "Door Cutting Order": "public/js/door_cutting_order/list_view/door_cutting_order_list.js",
}
