"""Server-side service package for Almdina ERP.

Service modules are imported explicitly by their callers. The package initializer
must remain side-effect free so pure domain and optimizer tests can import
compatibility modules without loading Frappe or mutating another module at import
time.
"""

from __future__ import annotations


__all__: list[str] = []
