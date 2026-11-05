# Initial implementation checks — 2026-11-05

Status: **research implementation only; NOT approved for default activation**.
Base: `0d3cf1dbe873686134a2648df7d0dd6996b8409f`.

Actual local runtime: Windows 11 (Python reports Windows-10 build 26200), Python
3.11.3, pytest 9.2.0, ezdxf 1.4.5, OR-Tools 9.15.6755, Node installed. These are
local observations, not certification of the Linux/Frappe production runtime.

## Checks actually run

- Focused combined regression command: ABC + existing board regrouping + domain
  strategies + plan Application + execution trace: **102 passed, 26 subtests**.
  This includes actual JS export/strict import at zero and positive trim.
- Domain/plan architecture and same-count quality, excluding the two
  `quality_time_is_reclaimed` parameters that can enter native CP-SAT:
  **62 passed, 60 subtests; 2 deselected**.
- Portfolio checks excluding three cases that enter CP-SAT: **8 passed,
  3 deselected**.
- Final alignment checks excluding two runtime-observation tests: **56 passed,
  1 failed, 2 deselected** in a standalone run. The failure was the absent Frappe
  module in an existing Uploaded-DXF test imported without the repository's test
  stub. Re-running that exact test with the existing `install_if_unavailable()`
  stub: **1 passed**. This does not establish a real Frappe integration pass.
- `git diff --check` and syntax compilation passed.

The last zero-budget regression and source-frozen smoke results are recorded in
the follow-up evidence commit. No tests were removed/weakened to make a green
full-suite claim. Pytest `--basetemp` used a workspace-owned venv path because
the existing shared pytest temp directory returned WinError 5.

## Native solver limitation

An attempted broader portfolio run hit a Windows native access violation in
`ortools.sat.python.cp_model.CpSolver.solve`, in the unchanged solver path.
A standalone one-Boolean CP-SAT probe outside application code also failed to
complete within 20 seconds and was terminated by its subprocess timeout. Solver
tests are therefore not certified locally. The installed dependency was not
removed or disabled to obtain a full-suite pass. Full Linux CI/Frappe checks
remain required; the benchmark's 48-piece input exceeds the existing exact
piece limit of 40 and does not exercise CP-SAT.

## Observed prototype failures, retained as limitations

An initial checkpoint placed after Auto seed completion did not start A/C on a
one-second request: the existing full Auto pass already consumed the deadline.
This prompted the tested first-kernel checkpoint and cooperative **opt-in A/C**
seed deadline. Defaults remain unchanged. Scheduling before a deadline check
cannot preempt a packing call that is already executing.

Preliminary operational smoke arms retained three boards and valid DXF, but
some had worse remnant/network results than an independently timed native run.
This is the expected adoption risk from displacing native work, not evidence
that the three mechanisms may be enabled. These exploratory runs also overlapped
other local checks and are not used as calibrated performance claims. The final
source-digested smoke will be published separately with individual rows. One
case/repetition cannot satisfy the known/holdout/repeatability gates.

The next research task is scheduling/selection efficacy, not production
activation, extra optimizer names or a manufacturing-rule relaxation. This
implementation makes that testable; it does not assert board savings, global
optimality, commercial-optimizer superiority or actual CNC-time savings.
