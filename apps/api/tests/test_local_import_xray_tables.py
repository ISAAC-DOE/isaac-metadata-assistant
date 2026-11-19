"""The emission-line and absorption-edge table the import's suggestions use (``readers.xray_tables``).

The table is a snapshot of xraydb, never typed by hand. What these pin:

* the file is self-consistent and carries its provenance: the xraydb version it was generated from and the
  compilation it rests on; every energy is a positive number; every line names the edge whose core hole it fills,
  and that edge is in the table for its element whenever the table keeps that kind of edge;
* where xraydb is installed (the ``processing`` extra), the values the table USES agree with it: the edge and line
  energies of the elements it lists, within :data:`TOLERANCE_EV`, and each line's edge. A newer xraydb may list more
  elements or lines, and that is no disagreement. An xraydb of another MAJOR version than the table records is not
  compared (the test says so and skips): its tables may have been recompiled, and the snapshot is regenerated with
  ``python -m isaac_api.local_import.readers.xray_tables --write`` and reviewed, never edited.
"""

from __future__ import annotations

import json
import math
import re

import pytest

from isaac_api.local_import.readers import xray_tables as X

#: how far (eV) an installed xraydb's energy may be from the snapshot's: well under the line tolerance the
#: suggestion applies (``X.LINE_TOLERANCE_EV``), so a value that moved by less cannot change a suggestion
TOLERANCE_EV = 0.5


def _table() -> dict:
    return json.loads(X.TABLE_FILE.read_text(encoding="utf-8"))


def _recorded_version() -> str:
    m = re.match(r"xraydb (\d+(?:\.\d+)*)\b", _table()["source"])
    assert m, "the table's source must name the xraydb version it was generated from"
    return m.group(1)


def test_the_table_has_its_provenance_and_is_self_consistent():
    table = _table()
    assert set(table) == {"source", "edges", "lines"}
    assert _recorded_version() and "Elam, Ravel & Sieber 2002" in table["source"]
    assert table["edges"] and table["lines"]
    for element, edges in table["edges"].items():
        assert re.fullmatch(r"[A-Z][a-z]?", element) and set(edges) <= set(X.EDGES)
        assert all(isinstance(e, (int, float)) and math.isfinite(e) and e > 0 for e in edges.values())
    for element, lines in table["lines"].items():
        assert set(lines) <= set(X.LINES)
        for name, (energy, level) in lines.items():
            assert isinstance(energy, (int, float)) and math.isfinite(energy) and energy > 0
            assert isinstance(level, str) and level
            if level in X.EDGES:  # an edge the table keeps: it is there, above the line it feeds
                edge = table["edges"].get(element, {}).get(level)
                assert edge is not None and edge > energy, (element, name, level)
    assert X.source() == table["source"]


def test_the_values_the_table_uses_agree_with_the_installed_xraydb():
    xraydb = pytest.importorskip("xraydb", reason="xraydb is in the processing extra; without it there is nothing to compare")
    installed = str(getattr(xraydb, "__version__", ""))
    recorded = _recorded_version()
    if installed.split(".")[0] != recorded.split(".")[0]:
        pytest.skip(f"the installed xraydb is {installed or 'of no stated version'}, another major version than the "
                    f"{recorded} the table records: regenerate the snapshot and review it")
    table = _table()
    far: list[str] = []
    for element, edges in table["edges"].items():
        have = xraydb.xray_edges(element) or {}
        for edge, energy in edges.items():
            if edge not in have:
                far.append(f"{element} {edge}: not in xraydb {installed}")
            elif abs(float(have[edge].energy) - energy) > TOLERANCE_EV:
                far.append(f"{element} {edge}: {energy} here, {have[edge].energy} in xraydb {installed}")
    for element, lines in table["lines"].items():
        have = xraydb.xray_lines(element) or {}
        for name, (energy, level) in lines.items():
            if name not in have:
                far.append(f"{element} {name}: not in xraydb {installed}")
            elif abs(float(have[name].energy) - energy) > TOLERANCE_EV or str(have[name].initial_level) != level:
                far.append(f"{element} {name}: {energy} ({level}) here, {have[name].energy} ({have[name].initial_level}) "
                           f"in xraydb {installed}")
    assert far == [], "; ".join(far[:20])
