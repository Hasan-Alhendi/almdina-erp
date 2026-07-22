# Cutting Optimizer v2

## Purpose

The v2 optimizer extends the original 17 packing heuristics without removing them. It adds multi-start search, local improvement, time-bounded deep search, optional CP-SAT exact search, machine-aware feasibility, and industrial quality metrics.

## Operator modes

### Auto

Fast baseline comparison. Runs the available baseline methods and chooses using the industrial ranking.

### Auto Pro

Recommended daily mode.

- Runs every eligible packing method against multiple deterministic piece orderings.
- Orderings include area, long side, width, length, perimeter, short side, square-first, elongated-first and area ascending.
- Runs a local permutation improvement pass around the best layout.
- Keeps the historical manual algorithms available for direct selection.

### Deep Search

Starts from Auto Pro and continues deterministic seeded restarts within the configured search budget. It preserves the best plan found at all times.

### Optimal Search

For CNC/non-guillotine cases within the configured exact-piece limit, the engine may invoke OR-Tools CP-SAT with 2D no-overlap constraints and rotation support.

- `OPTIMAL`: the CP-SAT model proved the minimum board count for the modeled full-board problem.
- `FEASIBLE`: CP-SAT found a valid solution before the time limit but did not prove optimality.
- `HEURISTIC_FALLBACK`: the heuristic result remained preferable or exact solving was unavailable/not applicable.
- `GUILLOTINE_DEEP_SEARCH`: Panel Saw mode deliberately uses guillotine-only deep search rather than claiming a non-guillotine exact optimum.

The authoritative geometry validator still runs before approval.

## Machine profiles

### Auto

No additional machine restriction. Useful when the production method is not yet fixed.

### CNC Router

Allows non-guillotine nesting methods such as MaxRects and Skyline. Exact CP-SAT search is allowed for cases within the configured size limit.

### Panel Saw

Automatic search is restricted to Guillotine-family layouts so the result remains compatible with sequential edge-to-edge panel-saw cutting. Remnant packing also uses guillotine placement.

## Industrial ranking

Advanced modes compare plans lexicographically in this order:

1. No unplaced pieces.
2. Minimum number of full source sheets.
3. Machine feasibility (Panel Saw must not receive a non-guillotine automatic plan).
4. Larger reusable rectangular leftover.
5. Fewer estimated straight cut lines.
6. Shorter estimated straight-line cut length.
7. Fewer rotations.
8. Lower algorithmic complexity as a final deterministic tie-breaker.

Waste area remains reported. When all requested pieces are placed on the same count of identical full boards, raw waste area is mathematically fixed by total requested piece area; therefore the tie-breakers focus on leftover usability and production effort rather than pretending equal-board layouts have different raw waste.

## Remnants

Approval still prefers physically matching remnants when enabled. Matching remains constrained by Board Item, material, color and thickness. The remaining full-board demand is then optimized using the selected v2 mode and machine profile.

## Safety and auditability

- Approved plans remain immutable.
- Optimization mode, machine type, selected method, ordering strategy, attempt count, solver status, search time and industrial metrics are stored on the immutable `Cutting Plan` snapshot.
- Geometry validation remains mandatory before approval.
- Manual selection of all original 17 algorithms remains available.
- Optimal/Deep searches are time bounded and preserve the best valid plan found.

## Recommended defaults

- Daily orders: `Auto Pro`
- Important/high-value order where a few extra seconds are acceptable: `Deep Search`
- Small/medium CNC order where proving or improving board count matters: `Optimal Search`
- Panel Saw: choose `Panel Saw` machine profile; Auto Pro/Deep/Optimal will respect guillotine feasibility.

## Deployment note

The exact solver uses `ortools>=9.15,<10` declared in `pyproject.toml`. A deployment must rebuild the application image so the dependency is installed, then run site migration so the new DocType fields are synchronized.
