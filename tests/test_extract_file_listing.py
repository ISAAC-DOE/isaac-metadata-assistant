"""Deterministic file-listing parser: asset candidates without a sha256.

Hermetic: reads only the committed synthetic listing fixture. Asserts the three
recognized product kinds (raw pointer, reduced product, notebook script) with
correct URIs / media types and ``file_listing`` evidence, that NO candidate carries
a sha256, and that ``archive_root`` recovers the ``ssrl-archive://`` root.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from isaac_records.extract import AssetCandidate, archive_root, parse_file_listing

REPO_ROOT = Path(__file__).resolve().parent.parent
LISTING_PATH = REPO_ROOT / "tests" / "fixtures" / "synthetic" / "raw_scan_listing.txt"


def _by_role(candidates):
    return {c.content_role: c for c in candidates}


def test_three_product_kinds_with_uris_and_media_types():
    candidates = parse_file_listing(LISTING_PATH)
    assert all(isinstance(c, AssetCandidate) for c in candidates)
    by_role = _by_role(candidates)

    raw = by_role["raw_data_pointer"]
    assert raw.uri == "ssrl-archive://BL15-2/2099_run_000/raw/"
    assert raw.media_type == "application/x-hdf5"

    reduced = by_role["reduction_product"]
    assert reduced.uri == "ssrl-archive://BL15-2/2099_run_000/reduced/CuO2_merged.xdi"
    assert reduced.media_type == "text/plain"

    notebook = by_role["processing_script"]
    assert notebook.uri == "ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb"
    assert notebook.media_type == "application/x-ipynb+json"


def test_each_candidate_has_one_file_listing_evidence():
    for c in parse_file_listing(LISTING_PATH):
        assert len(c.evidence) == 1, c
        e = c.evidence[0]
        assert e["source_type"] == "file_listing"
        assert e["source_file"] == "raw_scan_listing.txt"
        assert "ssrl-archive://" in e["locator"]
        assert e.get("quote")


def test_no_candidate_carries_a_sha256():
    # AssetCandidate has no sha256 field, and none is smuggled into evidence.
    assert not hasattr(AssetCandidate, "sha256")
    field_names = {f.name for f in dataclasses.fields(AssetCandidate)}
    assert "sha256" not in field_names

    for c in parse_file_listing(LISTING_PATH):
        assert "sha256" not in dataclasses.asdict(c)
        for e in c.evidence:
            assert "sha256" not in e
            assert "sha256" not in (e.get("quote") or "").lower()


def test_archive_root_recovered():
    assert archive_root(LISTING_PATH) == "ssrl-archive://BL15-2/2099_run_000/"
