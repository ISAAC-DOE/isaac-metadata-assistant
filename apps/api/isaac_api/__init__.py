"""FastAPI backend for the ISAAC Metadata Assistant local UI prototype.

Synthetic-only, local-first. This package is a thin presentation/orchestration
layer over the deterministic core (``isaac_records``): every validity, export,
audit, and warning verdict comes from the core functions the CLI already uses.
The backend adds NO validation logic of its own and never mutates the truth path.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
