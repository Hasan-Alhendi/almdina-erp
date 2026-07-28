"""Backward-compatible names for the active Domain cutting engine adapter."""

from __future__ import annotations

from .domain_engine import DomainCuttingEngineAdapter, domain_cutting_engine


LegacyCuttingEngineAdapter = DomainCuttingEngineAdapter
legacy_cutting_engine = domain_cutting_engine


__all__ = ["LegacyCuttingEngineAdapter", "legacy_cutting_engine"]
