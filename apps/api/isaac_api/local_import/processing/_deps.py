"""Lazy optional dependencies: numpy, xraylarch, matplotlib.

Nothing in the bundle/grouping path imports these. When they are missing, processing
returns ``processing_unavailable`` — it never fabricates a result.
"""

from __future__ import annotations

import importlib


class ProcessingUnavailable(RuntimeError):
    def __init__(self, missing: list[str], detail: str):
        super().__init__(detail)
        self.missing = missing
        self.detail = detail


def require() -> dict:
    """Import numpy + larch (+ matplotlib, optional) or raise ProcessingUnavailable."""
    missing, detail = [], []
    mods: dict = {}
    for name in ("numpy", "larch"):
        try:
            mods[name] = importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - any import failure is "unavailable"
            missing.append(name)
            detail.append(f"{name}: {type(exc).__name__}: {exc}")
    if missing:
        raise ProcessingUnavailable(
            missing,
            "XAS processing needs the optional `processing` extra (numpy, xraylarch): "
            "`pip install -e '.[processing]'`. " + "; ".join(detail),
        )
    try:
        import matplotlib

        matplotlib.use("Agg")
        mods["matplotlib"] = matplotlib
    except Exception:  # noqa: BLE001 - plots are optional; results say plot_unavailable
        mods["matplotlib"] = None
    return mods


def versions() -> dict:
    out = {}
    for name in ("numpy", "larch", "xraydb", "matplotlib"):
        try:
            m = importlib.import_module(name)
            out[name] = getattr(m, "__version__", "?")
        except Exception:  # noqa: BLE001
            out[name] = None
    return out
