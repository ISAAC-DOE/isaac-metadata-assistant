"""Bundle format 1.17.0 (C4 of the 22 Nov 2026 plan; skill audit of 18 Nov 2026, finding 10): the scientist's consent
to Claude reading their files, and their name, are kept in the bundle, so a second session does not ask them again;
``isaac bundle status`` says where things stand in a few plain lines. SYNTHETIC data only.

* the version is bumped by the existing mechanism, after 1.16.0, and a 1.16.0 bundle (and the 1.14.0 build's own
  bundle) stays valid and is upgraded on its first write, which says so;
* ``bundle consent --by`` appends one ``consents`` entry (append-only; the latest one is what holds); the same answer
  again records nothing and writes nothing; ``--withdraw`` records a withdrawal;
* the validator refuses a consent entry without a name, or with an answer other than given / withdrawn;
* ``bundle status`` names the scientist and the consent, counts runs, groups, records, questions and processing, and
  says what to do next; it writes nothing (``test_local_import_read_only.py`` runs it on every read check).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tests_support_records import SEMANTICS  # noqa: E402

BUNDLE_1_14_0 = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "local_import" / "bundle_1_14_0"


@pytest.fixture(autouse=True)
def _vendored_schema_basis(monkeypatch, tmp_path):
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(tmp_path / "no-validator"))
    monkeypatch.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(tmp_path / "no-validator" / "python"))


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    out = tmp_path_factory.mktemp("c4") / "bundle"
    assert cli.main(["import", str(SEMANTICS), "--out", str(out)]) == 0
    return out


@pytest.fixture()
def bdir(pristine, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(pristine, target)
    return target


def _run(capsys, *argv):
    code = cli.main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def test_the_version_follows_1_16_0_by_the_existing_mechanism():
    # 1.18.0 (DEC-96) follows 1.17.0 by the same mechanism: read by position, as the 1.16.0 test does
    assert B._VERSION_ORDER.index("1.17.0") == B._VERSION_ORDER.index("1.16.0") + 1
    schema = B.bundle_schema()
    enum = schema["properties"]["format_version"]["enum"]
    assert enum.index("1.17.0") == enum.index("1.16.0") + 1
    assert "1.17.0" in schema["properties"]["format_version"]["description"]
    blocks = [b for b in schema.get("allOf") or ()
              if (b.get("if") or {}).get("properties", {}).get("format_version", {}).get("const") == "1.17.0"]
    assert blocks and blocks[0]["then"]["required"] == ["processed_outputs"]
    assert "consents" in schema["properties"] and "consent" in schema["$defs"]
    assert B.changes_since("1.16.0")[0] == B.CHANGES_ADDED_IN["1.17.0"]
    assert "consent" in B.CHANGES_ADDED_IN["1.17.0"] and M.PENDING_EXPOSURES_FILE in B.CHANGES_ADDED_IN["1.17.0"]


def test_an_older_bundle_stays_valid_and_its_first_write_says_it_was_upgraded(bdir):
    data = json.loads((bdir / "bundle.json").read_text())
    data["format_version"] = "1.16.0"  # what a 1.16.0 build wrote (its shape is the same: consents is optional)
    (bdir / "bundle.json").write_text(json.dumps(data))
    assert B.validate_bundle(json.loads((bdir / "bundle.json").read_text())) == []
    M.record_consent(bdir, by="SYN Scientist")
    saved = json.loads((bdir / "bundle.json").read_text())
    assert saved["format_version"] == B.FORMAT_VERSION and B.validate_bundle(saved) == []
    [u] = [u for u in saved.get("format_upgrades") or () if u.get("from_format_version") == "1.16.0"]
    assert B.CHANGES_ADDED_IN["1.17.0"] in u["statement"]


def test_the_1_14_0_builds_bundle_is_read_by_status_and_upgraded_by_recording_consent(tmp_path, capsys):
    out = tmp_path / "b"
    shutil.copytree(BUNDLE_1_14_0, out)
    raw = (out / "bundle.json").read_bytes()
    code, text, _ = _run(capsys, "bundle", "status", str(out))
    assert code == 0 and "1.14.0" in text and "not recorded" in text
    assert (out / "bundle.json").read_bytes() == raw  # looking wrote nothing
    code, text, _ = _run(capsys, "bundle", "consent", str(out), "--by", "SYN Scientist")
    assert code == 0
    saved = json.loads((out / "bundle.json").read_text())
    assert saved["format_version"] == B.FORMAT_VERSION and B.validate_bundle(saved) == []
    assert [c["given_by"]["name"] for c in saved["consents"]] == ["SYN Scientist"]


def test_consent_is_recorded_once_with_the_scientists_name(bdir, capsys):
    code, text, _ = _run(capsys, "bundle", "consent", str(bdir), "--by", "  SYN Scientist ")
    assert code == 0
    out = json.loads(text)
    assert out["recorded"] is True and out["consent"]["given_by"]["name"] == "SYN Scientist"
    stored = json.loads((bdir / "bundle.json").read_text())
    [c] = stored["consents"]
    assert c["answer"] == "given" and c["scope"] == B.CONSENT_SCOPE and c["agreement"] == B.CONSENT_AGREEMENT
    assert c["given_by"] == {"name": "SYN Scientist", "basis": "self_reported_local_user", "identity": "local_unverified",
                             "orcid_claimed": None}
    assert c["folder"] == stored["source_root"]["label"] and c["consent_id"] == "consent-0001"
    assert B.current_consent(stored) == c
    # the same answer again records nothing and writes nothing
    version = M.bundle_version(bdir)
    code, text, _ = _run(capsys, "bundle", "consent", str(bdir), "--by", "SYN Scientist")
    assert code == 0 and json.loads(text)["recorded"] is False and M.bundle_version(bdir) == version


def test_a_withdrawal_is_recorded_and_is_what_holds_from_then_on(bdir, capsys):
    M.record_consent(bdir, by="SYN Scientist")
    code, text, _ = _run(capsys, "bundle", "consent", str(bdir), "--by", "SYN Scientist", "--withdraw")
    assert code == 0 and json.loads(text)["consent"]["answer"] == "withdrawn"
    stored = M.load(bdir)
    assert [c["answer"] for c in stored["consents"]] == ["given", "withdrawn"]  # append-only: the given one is kept
    assert B.current_consent(stored)["answer"] == "withdrawn"
    code, text, _ = _run(capsys, "bundle", "status", str(bdir))
    assert "WITHDRAWN" in text and "run nothing that prints names or values" in text


def test_consent_needs_a_name(bdir, capsys):
    version = M.bundle_version(bdir)
    code, _, err = _run(capsys, "bundle", "consent", str(bdir), "--by", "   ")
    assert code != 0 and "name" in err and M.bundle_version(bdir) == version
    code, _, err = _run(capsys, "bundle", "consent", str(bdir), "--by", "SYN", "--note", "x" * 2001)
    assert code != 0 and "2000" in err and M.bundle_version(bdir) == version


def test_the_validator_refuses_a_consent_without_a_name_or_with_another_answer(bdir):
    M.record_consent(bdir, by="SYN Scientist")
    good = json.loads((bdir / "bundle.json").read_text())
    for change in ({"answer": "maybe"}, {"given_by": {**good["consents"][0]["given_by"], "name": ""}},
                   {"scope": "anything"}):
        bad = json.loads(json.dumps(good))
        bad["consents"][0].update(change)
        assert B.validate_bundle(bad), change


def test_status_names_the_scientist_the_consent_and_the_next_step(bdir, capsys):
    code, text, _ = _run(capsys, "bundle", "status", str(bdir))
    lines = text.strip().splitlines()
    assert code == 0 and 6 <= len(lines) <= 9
    assert lines[0].startswith("Beamtime: ") and "Consent" in lines[1] and "not recorded" in lines[1]
    assert lines[-1].startswith("Next: ") and "bundle consent" in lines[-1]
    M.record_consent(bdir, by="SYN Scientist")
    code, text, _ = _run(capsys, "bundle", "status", str(bdir))
    assert "Scientist: SYN Scientist" in text and "do not ask again" in text
    assert "bundle consent" not in text.strip().splitlines()[-1]
    assert "Runs: " in text and "Open questions: " in text and "Records: " in text and "Processing: " in text


def test_status_json_gives_the_same_facts(bdir, capsys):
    M.record_consent(bdir, by="SYN Scientist")
    code, text, _ = _run(capsys, "bundle", "status", str(bdir), "--json")
    facts = json.loads(text)["facts"]
    assert code == 0 and facts["consent"]["answer"] == "given" and facts["consent"]["by"] == "SYN Scientist"
    assert facts["scientist"] == {"name": "SYN Scientist", "basis": "consent"}
    assert facts["runs"] == len(M.load(bdir)["runs"]) and facts["format"]["upgrade_on_next_write"] is False
    assert isinstance(facts["questions"]["blocking"], int) and facts["next"]


def test_status_without_consent_uses_the_name_on_the_latest_answer(bdir, capsys):
    M.decide(bdir, target_ids=["experiment"], decision="defer", value=None, by="SYN Answerer", orcid=None)
    code, text, _ = _run(capsys, "bundle", "status", str(bdir))
    assert "SYN Answerer (the name on the latest answer)" in text and "not recorded" in text


def test_status_of_a_folder_without_a_bundle_is_refused(tmp_path, capsys):
    code, _, err = _run(capsys, "bundle", "status", str(tmp_path))
    assert code == 6 and "bundle.json" in err
