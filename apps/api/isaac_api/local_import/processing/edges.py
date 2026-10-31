"""Tabulated absorption-edge energies, with their source. Stdlib only.

Used ONLY to compute a calibration shift when the reference element and edge are
confirmed by a scientist or stated by evidence (never guessed from the measured E0).

Source of :data:`EDGE_TABLE_EV`: ``xraydb.xray_edge(element, edge).energy`` from xraydb
4.5.8 (installed with xraylarch 2026.3.1), whose edge energies are the Elam, Ravel &
Sieber (2002) compilation. The table is a snapshot so the lookup works and is reviewable
without xraydb; when xraydb is importable it is used instead and its version recorded.
``test_local_import_processing.py`` checks the snapshot against xraydb.
"""

from __future__ import annotations

EDGE_TABLE_SOURCE = "xraydb 4.5.8 xray_edge() (Elam, Ravel & Sieber 2002), snapshot 2026-10-28"

EDGE_TABLE_EV: dict[tuple[str, str], float] = {
    ("Ti", "K"): 4966.0,
    ("V", "K"): 5465.0,
    ("Cr", "K"): 5989.0,
    ("Mn", "K"): 6539.0,
    ("Fe", "K"): 7112.0,
    ("Co", "K"): 7709.0,
    ("Ni", "K"): 8333.0,
    ("Cu", "K"): 8979.0,
    ("Zn", "K"): 9659.0,
    ("Ir", "L3"): 11215.0,
    ("Pt", "L3"): 11564.0,
    ("Au", "L3"): 11919.0,
    ("Ru", "K"): 22117.0,
    ("Pd", "K"): 24350.0,
}


def edge_energy(element: str, edge: str) -> tuple[float | None, str]:
    """(energy_eV, source). xraydb when importable, else the snapshot; (None, reason) when unknown."""
    try:
        import xraydb  # type: ignore

        e = xraydb.xray_edge(element, edge)
        if e is not None:
            return float(e.energy), f"xraydb {getattr(xraydb, '__version__', '?')} xray_edge()"
    except Exception:  # noqa: BLE001 - absent or unknown element: fall back to the snapshot
        pass
    value = EDGE_TABLE_EV.get((element, edge))
    if value is None:
        return None, f"{element} {edge} not in the snapshot table"
    return value, EDGE_TABLE_SOURCE
