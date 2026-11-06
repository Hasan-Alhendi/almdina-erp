"""Framework-free finite pattern-selection port; geometry stays in Domain."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class PatternColumn:
    counts: tuple[int, ...]
    remnant_units: int
    cutter_units: int
    internal_units: int
    segments: int


@dataclass(frozen=True, slots=True)
class PatternSelection:
    multiplicities: tuple[int, ...] = ()
    status: str = 'unavailable'
    phases: tuple[str, ...] = ()


PatternSolver = Callable[..., PatternSelection]


@dataclass(frozen=True, slots=True)
class ShelfColumn:
    counts: tuple[int, ...]
    thickness: int


@dataclass(frozen=True, slots=True)
class ShelfSelection:
    allocations: tuple[tuple[int, ...], ...] = ()
    status: str = 'unavailable'


def valid_selection(columns, demand, selection, max_boards):
    """Backend answers are proposals, never authority for source coverage."""
    if (not isinstance(selection,PatternSelection)
            or any(len(c.counts)!=len(demand) for c in columns)):
        return False
    values = selection.multiplicities
    return (len(values) == len(columns) and bool(values)
        and all(type(n) is int and 0 <= n <= max_boards for n in values)
        and 0 < sum(values) <= max_boards
        and all(sum(c.counts[g]*n for c,n in zip(columns,values)) == qty
                for g,qty in enumerate(demand)))
