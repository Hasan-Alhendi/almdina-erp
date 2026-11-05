# Verification record and limits

Measured source HEAD: `09576ea557ac6fadac11bc3fe407d7efc3dcd4cb`.
All tracked production Python/JS files remain unchanged. The ALNS code lives
only in scripts and research tests. Windows / Python 3.11.3 / OR-Tools 9.15.6755 /
ezdxf 1.4.5 / pytest 9.2.0 / Node 26.13.0.

## Successful checks

- 31 new ALNS tests pass, including six real-packer operator witnesses, zero and
  positive Kerf, fixed-work reproducibility, cancellation after improvement,
  identity preservation, forbidden rotation, protected shapes/OFFCUT, actual
  Application projection and JS/strict roundtrips at zero/positive trim, and
  expanded area-admissible neighborhoods/pre-screening.
- Isolated existing modules: board regrouping 37; same-count layout 52; ABC 30;
  Kerf clearance 6; Application 34; exact preview commit 10; lifecycle safety 25;
  fingerprint compatibility 63; Domain architecture 57; Stage13 5; Stage15 9;
  Smart lifecycle 8. All pass. The new 31 are counted separately above.
- Final alignment: 58 pass in the isolated module, one fails because that
  standalone test imports Frappe without installing the existing test stub.
  The exact failed test passes with the repository's standard
  `install_if_unavailable()` bootstrap; no test/assertion was edited.
- Total from completed isolated evidence and this bootstrap retry:
  **426 passed checks**, including the new 31. Partial passes in crashed workers
  are deliberately not added to that total.
- Three Node files exit 0: `plan_preview_state_ownership.test.js`,
  `plan_preview_save_phase_lock.test.js`, `plan_candidate_gallery.test.js`.
  The simulated “server rejected preview” message is an expected rejection
  witness in the Save test; its process passes.
- Official matrix: 84/84 final valid outcomes, all original piece quantities,
  362/362 actual JS Export → unchanged Strict Import roundtrip operations.
  These export checks apply to generated snapshots, not certification of the
  original designer DXF labels, DCO identities or machine NC.
- Python syntax compilation and `git diff --check` pass. SVG comparison files
  parse as valid XML. No production diff or migration.

## Failures retained and reproduced

1. First combined collection aborts in the unchanged permission suite because
   `frappe.as_json` is absent from the lightweight stub. `regression.xml` retains
   that collection error. This is not native Frappe permission certification.
2. Existing `test_smart_plan_portfolio.py::test_only_one_valid_geometry_is_not_padded_with_fake_alternatives`
   crashes inside `ortools...CpSolver.solve` / `optimizer.py:839` on this host.
   It reproduces in a fresh worker invoking the unchanged test, without
   importing any ALNS research code. Windows exit `3221225477` is retained in
   `verification-portfolio-repro/index.json` with the native stack in its TXT.
3. `test_smart_cutting_manufacturing.py` also encounters the same native solver
   crash in a small legacy case. The original module worker and a fresh worker
   with Windows fault dialogs suppressed retain the failure in
   `verification/` and `verification-manufacturing-repro/`. Suppressing dialogs
   makes the crash exit promptly; it does not make it pass. Two initial hung
   task-owned faulting workers were stopped explicitly after recording their
   stacks; no unrelated process was stopped.
4. The existing 243 discovery test at Trim .1 mm yields **4 rather than 3 boards**
   with its unchanged five-second Smart budget. It reproduces alone, with no
   ALNS opt-in/import, and is recorded in `verification/existing-243-point1.xml`.
   Production optimizer source is unchanged at HEAD. This is a baseline discovery
   failure in this environment, not a new assertion expectation or successful
   result. Whether more time/another host resolves it is not established here.

The underlying native solver fault has not been diagnosed. No solver dependency,
thread count, manufacturing rule or test assertion was changed to bypass it.
The two main cases have 48/69 pieces and an exact-piece limit of 40, so the normal
Smart path in those measurements does not invoke CP-SAT. Their successful
geometry/DXF evidence does not certify the crashing small-case solver path.

## Source freeze and reproduction

`source-snapshots/v1/` and `source-snapshots/v2/` contain **66 measured runtime
source files each**, every byte verified against the corresponding matrix's
source-manifest SHA-256. The two earlier script versions were recovered from
the surgical revision and accepted only after their hashes matched the original
measured v1 manifest exactly. Both failed and successful designs are reviewable.

Use the same Git HEAD/dependency versions plus the relevant snapshot overlay in
an isolated research checkout, retain the test exporter/importer at that HEAD,
and run the commands in `protocol.md`. Snapshot directories are evidence, not
standalone installed Frappe sites. Current CLI policy defaults retain v1's
three-board/original-order/no-prescreen policy; the follow-up flags explicitly
select the revised policy. A fresh output directory is required.

`verify_alns_study.py` now installs the repository's standard stub in fresh
workers and suppresses only Windows native-fault dialogs; it records native
failures rather than hanging. It refuses to overwrite an existing index.

Native Frappe install/migrate twice, native authorization integration, CI on a
new commit, full production corpus ALNS benchmarks, concurrent factory load,
physical CNC and live Preview/Save UAT are **not verified**. No new commit or
deployment was created. Do not describe the whole project test suite as green.
