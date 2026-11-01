"""LOCAL-P: without numpy/xraylarch, processing says ``processing_unavailable`` — never a
fabricated pass or fail. Runs without the optional extra (larch is hidden by monkeypatch)."""

from __future__ import annotations

import json
import sys

from isaac_api.local_import.processing import protocol as P
from isaac_api.local_import.processing.run import STATUS_FILE, process_bundle


def test_processing_unavailable_when_larch_is_missing(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "larch", None)  # import larch -> ImportError
    bundle = {"bundle_id": "syn", "source_root": {"label": "SYN"}, "runs": [], "candidates": [], "sources": [], "unread_files": []}
    out = process_bundle(tmp_path, bundle=bundle, created_utc="2026-10-28T00:00:00Z")
    assert out["status"] == "processing_unavailable" and "larch" in out["missing"]
    assert out["processing_results"] == []
    assert "pip install" in out["detail"]
    saved = json.loads((tmp_path / "processing" / STATUS_FILE).read_text())
    assert saved["status"] == "processing_unavailable"
    assert not (tmp_path / "processing" / "processing_results.json").exists()


def test_protocol_is_draft_and_every_parameter_is_documented():
    assert P.PROTOCOL_STATUS == "draft_unreviewed" and "Oscar" in P.PROTOCOL_NOTICE
    documented = set(P.PARAM_DOCS)
    for section, values in P.DEFAULT_PARAMS.items():
        for key in values:
            if key in ("robust_scale", "max_listed_points", "grid", "interpolation", "duplicate_energy_tolerance_eV", "make_flat", "enabled"):
                continue
            assert f"{section}.{key}" in documented, f"{section}.{key} undocumented"
    assert P.DEFAULT_PARAMS["deglitch"]["exclude_flagged"] is False
    try:
        P.resolve_params({"deglitch": {"no_such": 1}})
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("unknown parameter accepted")
