"""C7 of the 22 Nov 2026 plan (skill audit of 18 Nov 2026, findings 15 and 13): a command that only LOOKS writes nothing
to the bundle. SYNTHETIC data only.

* every read command leaves every file of the bundle folder byte for byte as it was, and the bundle's version (the
  sha256 of ``bundle.json``) with it, so a second reader (another session, the Local Imports page, the question site)
  never trips "the bundle changed since it was read";
* the parser values a read prints are still recorded (the blind protocol, contract §11): in
  ``exposures.pending.jsonl`` beside ``bundle.json``, read back by every load, and folded into ``bundle.json`` by the
  next command that records something;
* a bundle an older build wrote is upgraded by that next write, never by a look;
* ``bundle list <dir> processing-results`` lists only the results of live record groups; the rest are counted and
  listed with ``--all``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tests_support_records import BY, SEMANTICS  # noqa: E402
from test_local_import_records import _add_group  # noqa: E402

#: written beside bundle.json by a read that prints parser values; never part of what "the bundle" means here
NOT_THE_BUNDLE = {".bundle.lock", M.PENDING_EXPOSURES_FILE}


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    out = tmp_path_factory.mktemp("ro") / "bundle"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    M.group(out)
    _add_group(out)  # a record group with a processing result (g1 / p1)
    return out


@pytest.fixture()
def bdir(pristine, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(pristine, target)
    return target


def _snapshot(bdir: Path) -> dict[str, str]:
    return {str(p.relative_to(bdir)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(bdir.rglob("*")) if p.is_file() and p.name not in NOT_THE_BUNDLE}


def _ids(bdir: Path) -> dict:
    from isaac_api.local_import import questions as Q

    b = M.load(bdir)
    qs = Q.consolidate(b)["questions"]
    return {"run": b["runs"][0]["run_id"], "candidate": b["candidates"][0]["candidate_id"],
            "conflict": (b.get("conflicts") or [{}])[0].get("conflict_id"), "question": qs[0]["question_id"],
            "source": b["sources"][0]["source_id"]}


def _read_commands(bdir: Path, tmp_path: Path) -> list[list[str]]:
    d = str(bdir)
    ids = _ids(bdir)
    findings = tmp_path / "findings.json"
    findings.write_text(json.dumps({"format": "isaac.reading-findings", "findings": [
        {"field_path": "context.environment", "value": "in_situ", "applies_to": {"scope": "beamtime"},
         "source": {"path": "nowhere.txt", "locator": "line 1"}, "quote": "never written", "strength": "stated",
         "reasoning": "synthetic"}]}))
    cmds = [["bundle", "list", d, kind] for kind in
            ("runs", "conflicts", "candidates", "questions", "unread", "groups", "merge-candidates", "processed-outputs",
             "processing-results", "scan-notes", "athena-merges")]
    cmds += [["bundle", "list", d, "processing-results", "--all"], ["bundle", "list", d, "groups", "--all"],
             ["bundle", "show", d, "run", ids["run"]], ["bundle", "show", d, "candidate", ids["candidate"]],
             ["bundle", "show", d, "source", ids["source"]], ["bundle", "show", d, "question", ids["question"]],
             ["bundle", "show", d, "processing-result", "p1"],
             ["bundle", "check", d], ["bundle", "status", d], ["bundle", "status", d, "--json"],
             ["bundle", "questions", d], ["bundle", "questions", d, "--blocking-only", "--limit", "3"],
             ["bundle", "crosscheck-plan", d], ["bundle", "excerpt", d, ids["candidate"], "--source", str(SEMANTICS)],
             ["bundle", "reveal", d, ids["candidate"]],
             ["bundle", "check-readings", d, str(findings), "--root", str(SEMANTICS)],
             ["bundle", "propose-terms", d],
             ["bundle", "site", "export", d, "--out", str(tmp_path / "site"), "--site-template", str(tmp_path / "none")],
             ["bundle", "template", "export", d, "--out", str(tmp_path / "template.xlsx")]]
    if ids["conflict"]:
        cmds.append(["bundle", "show", d, "conflict", ids["conflict"]])
    return cmds


def test_no_read_command_writes_to_the_bundle(bdir, tmp_path, capsys):
    before, version = _snapshot(bdir), M.bundle_version(bdir)
    for argv in _read_commands(bdir, tmp_path):
        code = cli.main(argv)
        capsys.readouterr()
        assert code in (0, 1), (argv, code)  # check-readings exits 1 on its unfound quote
        assert _snapshot(bdir) == before, f"{argv} wrote to the bundle"
        assert M.bundle_version(bdir) == version, argv


def test_two_readers_never_trip_the_bundle_changed_since_it_was_read(bdir, capsys):
    version = M.bundle_version(bdir)  # what the first reader (a page, a session) showed
    assert cli.main(["bundle", "questions", str(bdir)]) == 0  # the second reader looks, and prints values
    assert cli.main(["bundle", "list", str(bdir), "candidates"]) == 0
    capsys.readouterr()
    # the first reader's answer is still accepted: nothing moved the version it read
    M.mutate(bdir, lambda b: None, expected_version=version)


def test_the_values_a_read_prints_are_recorded_beside_the_bundle_and_folded_in_by_the_next_write(bdir, capsys):
    cand = M.load(bdir)["candidates"][0]["candidate_id"]
    assert not M.exposures_for(M.load(bdir), "candidate", cand)
    assert cli.main(["bundle", "reveal", str(bdir), cand]) == 0
    capsys.readouterr()
    pending = bdir / M.PENDING_EXPOSURES_FILE
    assert pending.is_file()
    assert not [e for e in json.loads((bdir / "bundle.json").read_text())["exposures"] if e["target"]["id"] == cand]
    seen = M.exposures_for(M.load(bdir), "candidate", cand)  # every load reads it back
    assert [e["command"] for e in seen] == ["bundle reveal"]
    # the blind protocol holds: a reading given after the value was shown is not blind
    M.annotate(bdir, target_id=cand, value="anything", model_id="synthetic-model", basis="synthetic", blind=True)
    reading = M.load(bdir)["ai_interpretations"][-1]
    assert reading["blind"] is False
    # that write folded the pending exposures into bundle.json, kept their ids, and removed the file
    stored = json.loads((bdir / "bundle.json").read_text())
    assert [e["exposure_id"] for e in stored["exposures"] if e["target"]["id"] == cand] == [seen[0]["exposure_id"]]
    assert not pending.exists()
    assert B.validate_bundle(stored) == []


def test_a_pending_exposure_of_another_bundle_is_never_folded_in(bdir, capsys):
    cand = M.load(bdir)["candidates"][0]["candidate_id"]
    (bdir / M.PENDING_EXPOSURES_FILE).write_text(json.dumps(
        {"bundle_id": "some-other-import", "target": {"kind": "candidate", "id": cand}, "command": "bundle reveal",
         "at_utc": "2026-11-22T00:00:00Z"}) + "\n")
    assert not M.exposures_for(M.load(bdir), "candidate", cand)


def test_an_unreadable_pending_exposure_line_is_refused_not_skipped(bdir):
    (bdir / M.PENDING_EXPOSURES_FILE).write_text("{not json\n")
    with pytest.raises(M.MutationRefused) as exc:
        M.load(bdir)
    assert M.PENDING_EXPOSURES_FILE in str(exc.value)


def test_an_older_bundle_is_upgraded_by_the_next_write_never_by_a_look(bdir, capsys):
    data = json.loads((bdir / "bundle.json").read_text())
    data["format_version"] = "1.16.0"  # what a 1.16.0 build wrote (its shape is the same)
    (bdir / "bundle.json").write_text(json.dumps(data))
    before = _snapshot(bdir)
    assert cli.main(["bundle", "questions", str(bdir)]) == 0
    assert cli.main(["bundle", "status", str(bdir)]) == 0
    out = capsys.readouterr().out
    assert "1.16.0" in out and B.FORMAT_VERSION in out  # status says the upgrade is pending
    assert _snapshot(bdir) == before
    M.decide(bdir, target_ids=["experiment"], decision="defer", value=None, **BY)
    assert json.loads((bdir / "bundle.json").read_text())["format_version"] == B.FORMAT_VERSION


def test_results_of_groups_that_no_longer_exist_are_counted_not_listed(bdir, capsys):
    b = M.load(bdir)
    b["record_groups"] = [g for g in b["record_groups"] if g["group_id"] != "g1"]  # a regroup dropped g1
    M.save_bundle(bdir, b)
    assert cli.main(["bundle", "list", str(bdir), "processing-results"]) == 0
    page = json.loads(capsys.readouterr().out)
    assert "p1" not in [r["result_id"] for r in page["items"]]
    assert page["not_listed"] == {"group_no_longer_live": 1} and "--all" in page["not_listed_note"]
    assert cli.main(["bundle", "list", str(bdir), "processing-results", "--all"]) == 0
    every = json.loads(capsys.readouterr().out)
    [p1] = [r for r in every["items"] if r["result_id"] == "p1"]
    assert p1["group_status"] is None


def test_a_rejected_groups_results_are_not_listed_either(bdir, capsys):
    M.decide(bdir, target_ids=["g1"], decision="reject", value=None, **BY)
    assert cli.main(["bundle", "list", str(bdir), "processing-results"]) == 0
    page = json.loads(capsys.readouterr().out)
    assert "p1" not in [r["result_id"] for r in page["items"]] and page["not_listed"] == {"group_no_longer_live": 1}
