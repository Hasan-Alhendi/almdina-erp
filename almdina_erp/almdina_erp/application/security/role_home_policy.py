from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RoleHomePolicy:
    """Native Frappe Role.home_page state for a selected role set.

    Almdina deliberately does not resolve a landing page. Frappe owns that
    decision. This object only detects an ambiguous configuration before we save
    a role assignment that could make the effective landing route depend on role
    ordering.
    """

    by_role: tuple[tuple[str, str], ...]
    routes: tuple[str, ...]

    @property
    def has_conflict(self) -> bool:
        return len(self.routes) > 1


def normalize_home_route(value: object) -> str:
    route = str(value or "").strip()
    if not route:
        return ""
    if route.startswith(("http://", "https://", "/")):
        return route
    return f"/{route}"


def analyze_role_home_pages(
    roles: Sequence[str],
    home_pages: Mapping[str, object],
) -> RoleHomePolicy:
    by_role: list[tuple[str, str]] = []
    for role in roles:
        name = str(role or "").strip()
        if not name:
            continue
        route = normalize_home_route(home_pages.get(name))
        if route:
            by_role.append((name, route))

    routes = tuple(dict.fromkeys(route for _role, route in by_role))
    return RoleHomePolicy(by_role=tuple(by_role), routes=routes)


__all__ = ["RoleHomePolicy", "analyze_role_home_pages", "normalize_home_route"]
