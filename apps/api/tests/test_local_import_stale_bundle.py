"""A bundle an OLDER build stored is STALE, not INVALID, when this build can write more fields.

1.3.0 made ``context.electrochemistry.potential_setpoint_V`` writable. A 1.2.0 bundle in which a
scientist confirmed a set-point stored it as not eligible ("no write path"); re-deriving it here
makes it eligible. ``bundle check`` says STALE and names each value and the remedy; any mutation
(``build-records`` first of all, under the lock) re-derives it and logs it in
``eligibility_rederived``; a value composed only because of that is listed in the composition
report, never composed silently.

Two ways to get an old bundle: (1) simulated, always run: a fresh bundle relabelled 1.2.0 with
the set-point's eligibility as the 1.2.0 build stored it; (2) REAL, built by the committed code
of ed731bcc via ``git archive`` (skipped when that commit is not in this clone).

SYNTHETIC files only (the grouping CLI fixture).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import records as R

from test_local_import_grouping_cli import _folder

BY = "SYNTHETIC TEST"
POT = "context.electrochemistry.potential_setpoint_V"
SCALE = "context.electrochemistry.potential_scale"
UPGRADE = ("upgraded from 1.2.0; fields this build can newly write have no answer slots on runs that lacked a parsed "
           "value — re-import to get them")
OLD_COMMIT = "ed731bcc"  # the last commit whose build could not write the set-point
REPO = Path(__file__).resolve().parents[3]


def _json(b: Path) -> dict:
    return json.loads((b / "bundle.json").read_text())


def _answer_everything_old_builds_could(b: Path) -> str:
    """Confirm run-001's set-point candidate, give its scale, confirm its group. Returns the candidate id."""
    bd = M.load(b)
    pot = next(c for c in bd["candidates"] if c["target_field_path"] == POT and c["run_id"] == "run-001")
    scale = next(m for m in bd["missing_values"] if m["target_field_path"] == SCALE and m["run_id"] == "run-001")
    M.decide(b, target_ids=[pot["candidate_id"]], decision="confirm", value=None, by=BY, orcid=None)
    M.decide(b, target_ids=[scale["value_id"]], decision="correct", value="RHE", by=BY, orcid=None)
    key = next(r["run_key"] for r in bd["runs"] if r["run_id"] == "run-001")
    gid = next(g["group_id"] for g in bd["record_groups"] if key in g["member_run_keys"])
    M.decide(b, target_ids=[gid], decision="confirm", value=None, by=BY, orcid=None)
    return pot["candidate_id"]


def _simulated_old_bundle(tmp_path: Path) -> tuple[Path, str]:
    src, b = _folder(tmp_path), tmp_path / "bundle"
    assert cli.main(["import", str(src), "--out", str(b)]) == 0
    M.group(b)
    cid = _answer_everything_old_builds_could(b)
    data = _json(b)
    # what the 1.2.0 build stored: the confirmed set-point had no write path
    data["format_version"] = "1.2.0"
    from isaac_api import historical_import as hist

    for c in data["candidates"]:
        if c["target_field_path"] == POT:
            c["state_basis"]["not_proposable_summary"] = hist.PLAIN_REASON_NO_WRITE_PATH  # the 1.2.0 wording
        if c["target_field_path"] == POT and c["eligibility_for_official_record"]["eligible"]:
            c["eligibility_for_official_record"] = {"eligible": False, "reason": "Confirmed, but this build has no write path for its official field, so it stays evidence."}
            data["readiness"]["eligible_value_count"] -= 1
    (b / "bundle.json").write_text(json.dumps(data))
    return b, cid


@pytest.fixture()
def old_bundle(tmp_path):
    return _simulated_old_bundle(tmp_path)


def test_check_says_stale_not_invalid_and_names_each_value_and_the_remedy(old_bundle, capsys):
    b, cid = old_bundle
    assert B.validate_bundle(_json(b))  # the plain validator does refuse it
    errors, stale = B.validate_allowing_stale(_json(b))
    assert errors == [] and [s["id"] for s in stale] == [cid]
    assert stale[0]["reason"].startswith(f"this build can now write {POT}") and "a scientist confirmed it" in stale[0]["reason"]
    assert stale[0]["reason"].endswith("eligible now; composes only beside a confirmed potential_scale")
    assert stale[0]["decision_id"] == "d-00001"
    capsys.readouterr()
    code = cli.main(["bundle", "check", str(b)])
    out = capsys.readouterr().out
    assert code == cli.EXIT_INVALID  # non-zero: the CLI has no exit code of its own for STALE
    assert out.startswith("STALE:") and "INVALID" not in out.split("\n")[0]
    assert cid in out and f"this build can now write {POT}" in out and "Remedy:" in out and "build-records" in out
    assert UPGRADE in out
    # validate / export refuse it with the remedy rather than composing from stored eligibility
    with pytest.raises(R.RecordsRefused, match="STALE"):
        R.load_validated(b)


def test_the_same_disagreement_in_a_bundle_of_this_version_is_invalid_not_stale(old_bundle, capsys):
    b, _ = old_bundle
    data = _json(b)
    data["format_version"] = B.FORMAT_VERSION  # a 1.3.0 build would have derived it: this is a tamper
    (b / "bundle.json").write_text(json.dumps(data))
    errors, stale = B.validate_allowing_stale(data)
    assert stale == [] and any("eligibility disagrees" in e for e in errors)
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(b)]) == cli.EXIT_INVALID
    assert capsys.readouterr().out.startswith("INVALID:")


def test_build_records_rederives_under_the_lock_and_lists_what_only_this_build_composes(old_bundle):
    b, cid = old_bundle
    result = R.build_records(b)
    assert [x["id"] for x in result["eligibility_rederived_now"]] == [cid]
    data = _json(b)
    assert data["format_version"] == B.FORMAT_VERSION and B.validate_bundle(data) == []
    [log] = data["eligibility_rederived"]
    assert (log["kind"], log["id"], log["from_format_version"], log["to_format_version"]) == ("candidate", cid, "1.2.0", B.FORMAT_VERSION)
    assert log["eligible_before"] is False and log["eligible_now"] is True and log["value_state"] == B.STATE_SCIENTIST_CONFIRMED
    [d] = result["drafts"]
    comp = json.loads((b / R.DRAFTS_DIR / f"{d['group_id']}.composition.json").read_text())
    draft = json.loads((b / d["draft"]).read_text())
    assert draft["fields"][POT]["value"] == 0.4 and draft["fields"][SCALE]["value"] == "RHE"
    [listed] = comp["composed_only_by_this_build"]
    assert listed["candidate_id"] == cid and listed["path"] == POT and listed["from_format_version"] == "1.2.0"
    assert listed["decision_id"] == "d-00001" and "before this build upgraded the bundle from 1.2.0" in listed["reason"]
    assert log["decision_id"] == "d-00001"
    # the log persists: a second build still lists it, and nothing is logged twice
    again = R.build_records(b)
    assert "eligibility_rederived_now" not in again
    comp = json.loads((b / R.DRAFTS_DIR / f"{d['group_id']}.composition.json").read_text())
    assert [x["candidate_id"] for x in comp["composed_only_by_this_build"]] == [cid]
    assert len(_json(b)["eligibility_rederived"]) == 1


def test_any_mutation_rederives_and_logs_it(old_bundle, capsys):
    b, cid = old_bundle
    other = next(m for m in M.load(b)["missing_values"] if m["target_field_path"] == "context.environment")
    M.decide(b, target_ids=[other["value_id"]], decision="correct", value="in_situ", by=BY, orcid=None)
    data = _json(b)
    assert [r["id"] for r in data["eligibility_rederived"]] == [cid]  # read from the bundle as stored, not the new decision
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(b)]) == 0 and capsys.readouterr().out.startswith("VALID")


def _old_build(tmp_path: Path) -> Path:
    """The committed code of OLD_COMMIT, unpacked by `git archive` (never a checkout)."""
    if subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{OLD_COMMIT}^{{commit}}"], capture_output=True).returncode:
        pytest.skip(f"{OLD_COMMIT} is not in this clone (shallow CI checkout)")
    tree = tmp_path / "old_tree"
    tree.mkdir()
    tar = tmp_path / "old.tar"
    subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", "-o", str(tar), OLD_COMMIT,
                    "apps/api/isaac_api", "apps/api/tests", "src", "schema", "vocabulary", "tests/fixtures/bl15"], check=True)
    with tarfile.open(tar) as t:
        t.extractall(tree, filter="data")
    return tree


def test_a_bundle_the_committed_old_build_made_is_stale_then_rederived(tmp_path, capsys):
    tree = _old_build(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    make = (
        "import sys, json\n"
        "from pathlib import Path\n"
        "import isaac_api\n"
        f"assert Path(isaac_api.__file__).resolve().is_relative_to(Path({str(tree)!r}).resolve()), isaac_api.__file__\n"
        "from isaac_api.local_import import mutations as M, cli, bundle as B\n"
        "from test_local_import_grouping_cli import _folder\n"
        "from test_local_import_stale_bundle import _answer_everything_old_builds_could\n"
        f"tmp = Path({str(work)!r}); src, b = _folder(tmp), tmp / 'bundle'\n"
        "assert cli.main(['import', str(src), '--out', str(b)]) == 0\n"
        "M.group(b)\n"
        "print(_answer_everything_old_builds_could(b))\n"
        "print(B.FORMAT_VERSION)\n"
    )
    # the new test module is copied beside the old tests so the old build can run its helper
    (tree / "apps/api/tests/test_local_import_stale_bundle.py").write_text(Path(__file__).read_text())
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tree / "apps/api"), str(tree / "apps/api/tests"), str(tree / "src")])}
    done = subprocess.run([sys.executable, "-c", make], cwd=tree / "apps/api/tests", env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-2000:]
    cid, old_version = done.stdout.split()[-2:]
    assert old_version == "1.2.0"
    b = work / "bundle"
    stored = next(c for c in _json(b)["candidates"] if c["candidate_id"] == cid)
    assert stored["value_state"] == B.STATE_SCIENTIST_CONFIRMED and stored["eligibility_for_official_record"]["eligible"] is False
    from isaac_api import historical_import as hist

    assert stored["state_basis"]["not_proposable_summary"] == hist.PLAIN_REASON_NO_WRITE_PATH  # the old wording

    capsys.readouterr()
    assert cli.main(["bundle", "check", str(b)]) == cli.EXIT_INVALID
    out = capsys.readouterr().out
    assert out.startswith("STALE:") and cid in out
    result = R.build_records(b)
    assert [x["id"] for x in result["eligibility_rederived_now"]] == [cid]
    [d] = result["drafts"]
    comp = json.loads((b / R.DRAFTS_DIR / f"{d['group_id']}.composition.json").read_text())
    assert [x["candidate_id"] for x in comp["composed_only_by_this_build"]] == [cid]
    after = next(c for c in _json(b)["candidates"] if c["candidate_id"] == cid)
    assert after["state_basis"]["not_proposable_summary"] == B.LOCAL_WRITE_PATH_REASON
    assert after["state_basis"]["not_proposable_reason"] == stored["state_basis"]["not_proposable_reason"]  # engine text kept
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(b)]) == 0
    assert UPGRADE in capsys.readouterr().out


def test_the_upgrade_is_logged_once_said_everywhere_and_corrects_the_old_wording(old_bundle, capsys):
    from isaac_api import historical_import as hist

    b, cid = old_bundle
    before = next(c for c in _json(b)["candidates"] if c["candidate_id"] == cid)
    capsys.readouterr()
    other = next(m for m in M.load(b)["missing_values"] if m["target_field_path"] == "context.environment")
    M.decide(b, target_ids=[other["value_id"]], decision="correct", value="in_situ", by=BY, orcid=None)
    err = capsys.readouterr().err
    assert err.count(UPGRADE) == 1  # said once, by the write that upgraded it
    data = _json(b)
    [u] = data["format_upgrades"]
    assert (u["from_format_version"], u["to_format_version"], u["derived_by_format_version"]) == ("1.2.0", B.FORMAT_VERSION, B.FORMAT_VERSION)
    # from 1.2.0: the set-point (1.3.0), the control mode (1.5.0) and the current set-point (1.7.0) are newly writable
    assert u["decisions_before"] == 3 and u["statement"] == UPGRADE
    assert u["newly_writable_paths"] == sorted([POT, B.CONTROL_MODE_PATH, B.CURRENT_SETPOINT_PATH])
    assert u["upgraded_utc"].endswith("Z")
    # (a) the old "cannot write it yet" wording is corrected; the engine's own text is kept
    after = next(c for c in data["candidates"] if c["candidate_id"] == cid)
    assert before["state_basis"]["not_proposable_summary"] == hist.PLAIN_REASON_NO_WRITE_PATH
    assert after["state_basis"]["not_proposable_summary"] == B.LOCAL_WRITE_PATH_REASON
    assert after["state_basis"]["not_proposable_reason"] == before["state_basis"]["not_proposable_reason"]
    # summary.md and check say it; a second write logs and says nothing more
    assert UPGRADE in (b / "summary.md").read_text()
    M.decide(b, target_ids=[other["value_id"]], decision="correct", value="ex_situ", by=BY, orcid=None)
    assert UPGRADE not in capsys.readouterr().err and len(_json(b)["format_upgrades"]) == 1
    assert cli.main(["bundle", "check", str(b)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("VALID") and out.count(UPGRADE) == 1


def test_only_a_value_confirmed_before_the_upgrade_is_listed_as_composed_only_by_this_build(old_bundle):
    b, cid = old_bundle
    R.build_records(b)  # the upgrade
    bd = M.load(b)
    # run-002: its set-point and scale answered AFTER the upgrade, its group confirmed
    pot2 = next(c for c in bd["candidates"] if c["target_field_path"] == POT and c["run_id"] == "run-002")
    scale2 = next(m for m in bd["missing_values"] if m["target_field_path"] == SCALE and m["run_id"] == "run-002")
    M.decide(b, target_ids=[pot2["candidate_id"]], decision="confirm", value=None, by=BY, orcid=None)
    M.decide(b, target_ids=[scale2["value_id"]], decision="correct", value="RHE", by=BY, orcid=None)
    key2 = next(r["run_key"] for r in bd["runs"] if r["run_id"] == "run-002")
    g2 = next(g["group_id"] for g in bd["record_groups"] if key2 in g["member_run_keys"])
    M.decide(b, target_ids=[g2], decision="confirm", value=None, by=BY, orcid=None)
    R.build_records(b)
    comp2 = json.loads((b / R.DRAFTS_DIR / f"{g2}.composition.json").read_text())
    draft2 = json.loads((b / R.DRAFTS_DIR / f"{g2}.draft.json").read_text())
    assert draft2["fields"][POT]["value"] == pot2["value"]
    assert comp2["composed_only_by_this_build"] == []  # answered under the corrected wording
    # run-001's pre-upgrade confirmation is listed until a decision after the upgrade governs it
    key1 = next(r["run_key"] for r in bd["runs"] if r["run_id"] == "run-001")
    g1 = next(g["group_id"] for g in bd["record_groups"] if key1 in g["member_run_keys"])
    comp1 = json.loads((b / R.DRAFTS_DIR / f"{g1}.composition.json").read_text())
    assert [x["candidate_id"] for x in comp1["composed_only_by_this_build"]] == [cid]
    M.decide(b, target_ids=[cid], decision="correct", value=0.5, by=BY, orcid=None)
    R.build_records(b)
    comp1 = json.loads((b / R.DRAFTS_DIR / f"{g1}.composition.json").read_text())
    draft1 = json.loads((b / R.DRAFTS_DIR / f"{g1}.draft.json").read_text())
    assert draft1["fields"][POT]["value"] == 0.5 and comp1["composed_only_by_this_build"] == []
