# Initial implementation checks — 2026-11-05

Final delivery regression command (ABC, existing regrouping, strategies, plan
Application, execution trace, domain architecture and plan architecture):
**115 passed, 86 subtests passed**. This includes the last zero-budget and
retention-only regressions on the implemented source. Full Linux/Frappe CI and
the CP-SAT cases described below remain unverified locally.

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


## Source-frozen eight-arm smoke

Measured local source commit: `6e676fc7473de7aae204b5fef59d0dd197d6a306`; immutable tree `68f4613e5d757fd85548fce9eb2c072bc0231dc6`. The published implementation commit `b21998e018ea90aa725e2a7567fd5c83122dcf0b` has exactly that same tree. All workers report digest `4b9c9a34f4a393f3a1b9bd5690812c6ded72b862f2bf718d9caf3130af2ba5e2` and the run began from a clean worktree.

Command: `python scripts/benchmark_abc.py --cases regular-48 --budget 5 --share .2 --repeats 1 --strict --output RESULT.json`. One reconstructed case, one repetition, fresh sequential workers. No other agent test/benchmark process ran during this source-frozen batch. Other desktop activity/OS load is not controlled; these are diagnostic timings, not calibrated causal performance or P95 claims.

| Arm A/B/C | Boards | Largest remnant m² | Real network mm | Segments | Total seconds |
|---|---:|---:|---:|---:|---:|
| 000 | 3 | 2.625440 | 46391.0 | 80 | 7.305 |
| 001 | 3 | 2.505876 | 45220.0 | 64 | 7.730 |
| 010 | 3 | 2.505876 | 46839.0 | 75 | 6.564 |
| 011 | 3 | 2.505876 | 45531.0 | 77 | 8.033 |
| 100 | 3 | 2.505876 | 46839.0 | 75 | 7.353 |
| 101 | 3 | 2.505876 | 45531.0 | 77 | 7.910 |
| 110 | 3 | 2.505876 | 46899.0 | 75 | 8.104 |
| 111 | 3 | 2.505876 | 45851.0 | 73 | 7.850 |

All eight views passed actual JS DXF export and strict import with equal per-board family placements and complete identity inventories. Sheet display numbering and interchangeable copies may be rebound by import; the harness compares the documented material/family contract. This corrected an initial harness assertion that incorrectly required stable DXF display sheet numbers, including in the unmodified baseline.

**Adoption gate failed on this witness:** all arms still use three boards. ABC 111 shortened the real network from 46391 to 45851 mm and reduced segments from 80 to 73, but its largest protected remnant decreased from 2.625440 to 2.505876 m². The final industrial prefix therefore regressed against the independent native arm. Keeping an incumbent within the changed trajectory does not protect against discoveries lost when native work is displaced. Default activation is not justified. The 20% scheduling policy needs further work; this is not a successful optimization claim.

Final focused ABC regressions: **30 passed**, including first-kernel scheduling, retention-only native-finalist equality, zero-budget native fallback, source identity/Kerf and actual zero/positive-trim DXF roundtrips. The eight-arm harness and evidence make the next scheduling change reviewable without touching production defaults.
