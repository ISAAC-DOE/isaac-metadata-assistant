"""Absorption-edge and emission-line energies, as a snapshot of xraydb. Stdlib only at run time.

What reads it: the import's SUGGESTIONS (``local_import.suggestions``), never a value written on its own —

* which element's emission line an emission spectrometer is parked on (an emission motor held within
  :data:`LINE_TOLERANCE_EV` of a tabulated line of an element whose absorption edge the scan crosses suggests
  ``HERFD-XAS``);
* which absorption edge a scanned energy range crosses (suggests the absorbing element and edge).

SOURCE. Every number in ``xray_tables.json`` is ``xraydb.xray_edge(element, edge).energy`` or
``xraydb.xray_lines(element)[line].energy`` (with the line's ``initial_level``: the edge whose core hole it fills), from
the xraydb version the file names; xraydb's edge and line energies are the Elam, Ravel & Sieber (2002) compilation
(Radiation Physics and Chemistry 63, 121-128). Nothing is typed by hand: ``python -m
isaac_api.local_import.readers.xray_tables --write`` regenerates the file from an installed xraydb, and
``apps/api/tests/test_local_import_xray_tables.py`` checks the file's provenance and consistency everywhere, and, where
xraydb of the same major version is installed (the ``processing`` extra), that the energies and lines the table lists
agree with it to well under the line tolerance. The snapshot exists so the lookup works, and is reviewable, without
xraydb.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

TABLE_FILE = Path(__file__).with_name("xray_tables.json")
#: the edges and lines kept: the hard and tender X-ray absorption edges, and the lines a crystal analyser is set to
EDGES = ("K", "L1", "L2", "L3")
LINES = ("Ka1", "Ka2", "Kb1", "La1", "La2", "Lb1", "Lb2,15", "Lg1")
#: how close (eV) a parked emission energy must be to a tabulated line to be read as that line
LINE_TOLERANCE_EV = 2.0


@lru_cache(maxsize=1)
def tables() -> dict[str, Any]:
    """``{"source", "edges": {element: {edge: eV}}, "lines": {element: {line: [eV, initial_level]}}}``."""
    return json.loads(TABLE_FILE.read_text(encoding="utf-8"))


def source() -> str:
    return str(tables()["source"])


def edge_energy(element: str, edge: str) -> float | None:
    value = (tables()["edges"].get(element) or {}).get(edge)
    return float(value) if value is not None else None


def edges_between(low: float, high: float) -> list[dict]:
    """Every tabulated edge with ``low <= energy <= high``, ``[{element, edge, energy_eV}]`` by energy."""
    out = [{"element": el, "edge": edge, "energy_eV": float(e)}
           for el, edges in tables()["edges"].items() for edge, e in edges.items() if low <= e <= high]
    return sorted(out, key=lambda x: (x["energy_eV"], x["element"], x["edge"]))


def lines_near(energy: float, tolerance: float = LINE_TOLERANCE_EV) -> list[dict]:
    """Every tabulated emission line within ``tolerance`` eV of ``energy``: ``[{element, line, energy_eV, edge}]``
    (``edge``: the absorption edge whose core hole the line fills), nearest first."""
    out = [{"element": el, "line": line, "energy_eV": float(e), "edge": level}
           for el, lines in tables()["lines"].items() for line, (e, level) in lines.items() if abs(e - energy) <= tolerance]
    return sorted(out, key=lambda x: (abs(x["energy_eV"] - energy), x["element"], x["line"]))


def snapshot_from_xraydb() -> dict[str, Any]:
    """The snapshot an installed xraydb gives (what ``--write`` stores and the test compares with)."""
    import xraydb  # type: ignore

    edges: dict[str, dict[str, float]] = {}
    lines: dict[str, dict[str, list]] = {}
    for z in range(1, 99):
        element = xraydb.atomic_symbol(z)
        got = {edge: float(e.energy) for edge, e in (xraydb.xray_edges(element) or {}).items() if edge in EDGES}
        if got:
            edges[element] = dict(sorted(got.items()))
        found = {name: [float(l.energy), str(l.initial_level)] for name, l in (xraydb.xray_lines(element) or {}).items()
                 if name in LINES}
        if found:
            lines[element] = dict(sorted(found.items()))
    return {"source": f"xraydb {xraydb.__version__} xray_edges() / xray_lines() (Elam, Ravel & Sieber 2002)",
            "edges": edges, "lines": lines}


if __name__ == "__main__":  # pragma: no cover - regenerates the snapshot; never run by an import
    import sys

    if "--write" in sys.argv:
        TABLE_FILE.write_text(json.dumps(snapshot_from_xraydb(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {TABLE_FILE}")
    else:
        print(source())
