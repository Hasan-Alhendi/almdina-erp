# P0 Phase 2B — Native Save and atomic Cutting Plan print

## Integration boundary

The implementation branch starts at Phase 2A `074fe87556b9f4f6e0b137aa0ae70c0839f98a36` and merges `Develop` at `f6a3be632eb4fd13ae30afd7078b27b25bbb2492` in merge commit `3840d9ed3a45dc3e5597d39a93db6fa53f2afe89`. The merge had no file conflicts. The original Phase 1 regression suite passed 15/15 and Phase 2A ownership suite passed 4/4 before implementing 2B. Neither investigation branch nor Phase 2A branch was changed.

## Native Save ownership

In pinned Frappe v16.17.5, a Data control debounces its native `input` handler and reads `$input` when the handler executes. The same Form and controls are reused on route changes. The previous custom `controlValue` read an old `$input` (or `get_value`) during `before_save` and copied it into the new document. The underlying risk also affects dimensions and measurement controls, not only color.

At an actual DocumentContext generation transition, native scalar controls are reconciled synchronously to the new model. The native input/change event is tagged during DOM capture, before Frappe's handler, and `parse_validate_and_set_in_model` rejects a delayed event from an obsolete generation. Board text and dimensions accept custom projection only when a user input/change event was tagged with the current document token and the same DOM element/value. The `before_save` projection rechecks its token before and after `frm.set_value`; same-document unsaved input remains authoritative. The fast measurement shell carries order and generation attributes, and its row synchronization rejects a shell from an earlier visit. This uses native `frm.save()` / `savedocs`; no parallel save endpoint or permission bypass was introduced.

## Atomic print contract

The PlanTabs print action now passes its selected source tab and Plan row to the renderer. The renderer captures the DocumentContext token, order name, Plan row name and revision, canonical row geometry, current print permission, and a deep copy of the order's printable data. It requires a ready Plan Workspace whose server payload belongs to the same order. A supplied plan must match the selected row's geometry. It builds geometry from that verified row instead of reusing a visible DOM plan. After the asynchronous factory identity lookup, it revalidates visit generation, order, permission, row identity, revision, and geometry; a mismatch closes the pending window without emitting final HTML. Printed metadata contains the plan name and revision. Existing page layout, RTL, edge drawing, extra legend, and OFFCUT presentation remain in the renderer.

This contract intentionally fails closed when no owned Plan Workspace row is available. A direct renderer test was updated to supply a trusted row rather than bypass that boundary; its drawing and final print assertions remain intact.

## Verification

- Original Phase 1 Node regressions: **15/15 GREEN**, assertions unchanged.
- Phase 2A ownership regressions: **4/4 GREEN**.
- Phase 2B native input contract: GREEN; delayed Frappe native A input and stale custom A value rejected, and unsaved B board/dimension edits retained.
- Final HTML geometry/edge regression with trusted plan row: GREEN; wrong geometry, revision change, and A→B→A generation reuse are rejected; Custom/Approved print geometry remains valid.
- Full JS sweep: **135/139 passed**. The four failures (`dco_sticky_tabs_geometry`, `measurement_toolbar_shared_loop`, `order_entry_locale`, `plan_tab_capabilities`) reproduce on pristine `Develop` at `f6a3be63`: **Baseline**, zero newly identified failures in this sweep. The three path-based failures refer to pre-existing moved files; the measurement frame-loop test is also red on the base. No out-of-scope baseline assertions were changed.
- Pinned Desk Native Save, independent DB read, persisted System Plan A/B HTML, wrong-plan rejection, and route change mid-await are exercised by `cross-order-p0-runtime.yml`. A separate same-order controlled renderer fixture adds multiple sheets, OFFCUT and Extra and saves its HTML artifact. This controlled print cannot substitute for the two server-persisted plan prints. Record the actual CI result and artifacts before certification.

## Remaining release boundary

NEW Form in Desk remains a separate Recovery release blocker. Recovery code was not changed; NEW→Saved model identity promotion is retained, but this phase does not certify the blocked NEW Form workflow. No DB migration, DXF/nesting algorithm change, or printer dispatch was introduced.

**Certification status:** Pending pinned Desk runtime evidence and CI classification. Never infer a DB or final HTML result from the Node tests alone.
