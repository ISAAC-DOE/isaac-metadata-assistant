"""Phase-2 extraction seam: the stubs exist, construct, and stay isolated.

One import/type smoke test only — Phase 3 adds the real parsing logic and its
behavioral tests. This guarantees the seam is importable, envelope-shaped, and
does not pull in graphify.
"""

import sys


def test_extract_interface_seam():
    # Symbols exist.
    from isaac_records.extract import ArtifactKind, ExtractedField, Extractor

    assert {k.value for k in ArtifactKind} == {
        "xlsx", "csv", "json", "file_listing", "screenshot", "pdf", "notes",
    }
    assert hasattr(Extractor, "extract")

    # ExtractedField constructs and is envelope-shaped.
    f = ExtractedField(
        path="system.facility.beamline",
        value="15-2",
        status="verified",
        evidence=({"source_type": "spreadsheet", "locator": "Sheet 'Campaign Info', cell B5"},),
    )
    assert (f.path, f.value, f.status, f.unit) == ("system.facility.beamline", "15-2", "verified", None)
    assert f.evidence[0]["source_type"] == "spreadsheet"

    # Importing the seam must not pull in graphify.
    for mod in list(sys.modules):
        if mod == "graphify" or mod.startswith("graphify."):
            del sys.modules[mod]
    import isaac_records.extract  # noqa: F401

    assert not any(
        m == "graphify" or m.startswith("graphify.") for m in sys.modules
    ), "the extraction seam must not import graphify"
