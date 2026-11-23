"""Bundle format 1.15.0: the ``export_despite_completeness`` record-group decision (review of PR 342, finding 5).
SYNTHETIC data only.

* the version is bumped by the existing mechanism, after 1.14.0, and a 1.14.0 bundle stays valid;
* the decision is valid only on a record group, with the record body it was decided for and why it was held;
* ``bundle decide`` never records it: ``bundle export --allow-indistinguishable --by`` does.
"""

from __future__ import annotations

import json
import shutil

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import mutations as M

from tests_support_records import BY, pristine_bundle  # noqa: F401


def test_the_version_follows_1_14_0_by_the_existing_mechanism():
    # 1.16.0 follows it (test_local_import_format_1_16.py)
    assert B._VERSION_ORDER.index("1.15.0") == B._VERSION_ORDER.index("1.14.0") + 1
    schema = B.bundle_schema()
    enum = schema["properties"]["format_version"]["enum"]
    assert enum.index("1.15.0") == enum.index("1.14.0") + 1
    assert "1.15.0" in schema["properties"]["format_version"]["description"]
    blocks = [b for b in schema.get("allOf") or ()
              if (b.get("if") or {}).get("properties", {}).get("format_version", {}).get("const") == "1.15.0"]
    assert blocks and blocks[0]["then"]["required"] == ["processed_outputs"]
    assert B.EXPORT_ANYWAY_DECISION in schema["$defs"]["scientist_decision"]["properties"]["decision"]["enum"]
    assert B.changes_since("1.14.0")[0] == B.CHANGES_ADDED_IN["1.15.0"]  # and each later version's, after it


@pytest.fixture()
def bdir(pristine_bundle, tmp_path):
    target = tmp_path / "b"
    shutil.copytree(pristine_bundle, target)
    M.group(target)
    return target


def _with(bdir, decision):
    b = json.loads((bdir / "bundle.json").read_text())
    b["scientist_decisions"].append({"decision_id": f"d-{len(b['scientist_decisions']) + 1:05d}", "chosen_reading_index": None,
                                     "decided_by": {"name": "SYN", "basis": "self_reported_local_user",
                                                    "identity": "local_unverified", "orcid_claimed": None},
                                     "decided_utc": "2026-11-22T00:00:00Z", "method": "scientist_answer", "note": None,
                                     **decision})
    return b


def test_the_decision_is_valid_only_on_a_record_group_with_its_body_and_reasons(bdir):
    gid = M.load(bdir)["record_groups"][0]["group_id"]
    good = {"target": {"kind": "record_group", "id": gid}, "decision": B.EXPORT_ANYWAY_DECISION,
            "value": {"body_sha256": "a" * 64, "held_by": ["indistinguishable_from_another_record"]}}
    assert B.validate_bundle(_with(bdir, good)) == []
    for bad in ({**good, "value": {"held_by": ["x"]}}, {**good, "value": {"body_sha256": "a" * 64, "held_by": []}},
                {**good, "target": {"kind": "experiment", "id": "experiment"}}):
        assert [e for e in B.validate_bundle(_with(bdir, bad)) if B.EXPORT_ANYWAY_DECISION in e or "record group" in e]


def test_an_older_bundle_stays_valid_and_decide_never_records_the_decision(bdir):
    b = json.loads((bdir / "bundle.json").read_text())
    b["format_version"] = "1.14.0"
    assert B.validate_bundle(b) == []
    gid = b["record_groups"][0]["group_id"]
    with pytest.raises(M.MutationRefused) as exc:
        M.decide(bdir, target_ids=[gid], decision=B.EXPORT_ANYWAY_DECISION, value=None, **BY)
    assert "--allow-indistinguishable" in str(exc.value)
    assert not [d for d in M.load(bdir)["scientist_decisions"] if d["decision"] == B.EXPORT_ANYWAY_DECISION]
