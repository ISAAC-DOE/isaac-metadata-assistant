"""Deployment configuration helpers.

Kept import-light and side-effect free: both ``app.py`` and ``auth.py`` need the
base path, and putting it here avoids a circular import between them.
"""

from __future__ import annotations

import os


def base_path() -> str:
    """Normalized deploy base path from ``ISAAC_BASE_PATH``.

    Returns ``""`` (the default, preserving local-dev behavior byte-for-byte)
    or ``/<segments>`` with no trailing slash (e.g. ``/krish``).
    """
    raw = os.environ.get("ISAAC_BASE_PATH", "").strip()
    if not raw or raw == "/":
        return ""
    return "/" + raw.strip("/")
