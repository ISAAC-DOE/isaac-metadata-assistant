"""Bundle format 1.20.0: the folder, the people and the held potential (slice 3 of DEC-96, DEC-98;
``docs/fill-first-design-2026-11-25.md``). SYNTHETIC data only: the committed multi-operator corpus (unmistakably fake:
year 2100, samples ZZ1..ZZ3) imported under the invented folder ``SSRL_BL152_2031-01_Quillfeather_ZzTestCat`` (PI
"Quillfeather", project "ZzTestCat") with an invented readme and memo, plus in-memory edits of those bundles.

* ``isaac.fill.environment_from_held_potential.v1``: a sample measurement whose own files give a set-point, with
  corroboration that it was electrochemical, takes the environment convention the scientist gives ONCE for the
  beamtime (``set_environment_convention``: operando, in situ, or per run), asked by one experiment-scope question that
  covers each run's own environment question meanwhile; never a reference, a run whose name holds an environment
  word, one anything says had no electrolyte, one with a differing file value, answer or stated reading, or one whose
  set-point is conflicting or contradicted; the potential scale plays no part;
* ``isaac.fill.facility_from_folder.v1``: the facility and beamline the folder and the SPEC fingerprint agree on;
* ``isaac.fill.organization_from_facility.v1``: the producing organization is that facility;
* ``isaac.fill.group_from_folder_pi.v1``: the producing group from the PI the folder names, only beside a second source
  that agrees, with the full name when a labelled position gives exactly one, never when the readme, a data path or a
  labelled line names another PI;
* a decision always wins; a merged group composes a fill only when every measured run has it; question ids are
  unchanged; a rule set 2 bundle is STALE; the draft validator accepts the composed fields.
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R
from isaac_api.local_import import status as ST
from isaac_api.local_import import suggestions as S

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tests_support_records import REPO_ROOT, SEMANTICS, fake_upstream_env  # noqa: E402,F401
from test_local_import_fill_first import _add_group  # noqa: E402

FOLDER = "SSRL_BL152_2031-01_Quillfeather_ZzTestCat"
MEMO = "SYN_folder_memo.txt"
MODEL = "syn-reader-model"
BY = dict(by="SYN Scientist", orcid=None)
ENV = "context.environment"
FACILITY = "system.facility.facility_name"
BEAMLINE = "system.facility.beamline"
ORG = "attribution.produced_by.organization"
GROUP = "attribution.produced_by.group"
SETPOINT = "context.electrochemistry.potential_setpoint_V"
CONTROL = "context.electrochemistry.control_mode"
ELECTROLYTE = "context.electrochemistry.electrolyte.name"
README = ("# 2031-01_Quillfeather\n"
          "# SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. PI: Ada Quillfeather (synthetic)\n"
          "\nZz\n")
#: the invented memo: each quote below is on the line named (1-based)
MEMO_LINES = {
    1: "# SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. Every value below is invented.",
    3: "SYNTHETIC: every ZzTestCat scan ran under chronoamperometry on the synthetic potentiostat",
    5: "SYNTHETIC: the group of Bo Quillfeather prepared the cell",
    7: "SYNTHETIC: chronoamperometry at 1.5 V was used for sample ZZ9; ZZ1 was measured dry after the hold",
    8: "SYNTHETIC protocol for sample ZZ9 only: chronoamperometry at 1.5 V",
    9: "SYNTHETIC: chronoamperometry was planned for the next beamtime",
    10: "SYNTHETIC: chronoamperometry was run on sample ZZ1 throughout",
    11: "SYNTHETIC: all samples were measured under chronoamperometry",
    12: "SYNTHETIC: samples held by chronoamperometry at each potential",
    13: "SYNTHETIC: OCV for 5 min, then chronoamperometry at 1.4 V",
}
RUNS = [f"run-00{n}" for n in range(1, 10)]


@pytest.fixture(scope="module", autouse=True)
def _vendored_schema_basis(tmp_path_factory):
    """No portal validator installed (as in CI), so the question set does not depend on the machine."""
    d = tmp_path_factory.mktemp("no-validator")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(d))
        mp.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(d / "python"))
        yield


def _make_src(root: Path, folder: str = FOLDER, readme: str | None = README) -> Path:
    src = root / folder
    shutil.copytree(SEMANTICS, src)
    if readme is not None:
        (src / "readme.txt").write_text(readme, encoding="utf-8")
    (src / MEMO).write_text("\n".join(MEMO_LINES.get(n, f"synthetic memo filler line {n}") for n in range(1, 15)) + "\n",
                            encoding="utf-8")
    return src


def _import(root: Path, folder: str = FOLDER, readme: str | None = README) -> tuple[Path, Path]:
    src = _make_src(root, folder, readme)
    out = root / "bundle"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    return src, out


@pytest.fixture(scope="module")
def imported(tmp_path_factory) -> tuple[Path, Path]:
    return _import(tmp_path_factory.mktemp("folder"))


@pytest.fixture()
def bdir(imported, tmp_path) -> Path:
    target = tmp_path / "bundle"
    shutil.copytree(imported[1], target)
    return target


@pytest.fixture()
def src(imported) -> Path:
    return imported[0]


def _finding(path: str, value, line: int, *, runs=None, strength="stated") -> dict:
    return {"field_path": path, "value": value,
            "applies_to": {"scope": "runs", "runs": list(runs)} if runs else {"scope": "experiment"},
            "source": {"path": MEMO, "locator": f"line {line}"}, "quote": MEMO_LINES[line], "strength": strength,
            "reasoning": "synthetic"}


def _apply(bdir: Path, src: Path, *findings) -> dict:
    return M.annotate_from_readings(bdir, {"format": S.READINGS_FORMAT, "findings": list(findings)}, model_id=MODEL,
                                    apply=True, root=src)


def _chronoamperometry(bdir: Path, src: Path) -> None:
    """A checked stated reading of the logbook-like memo, for the whole beamtime: the data were taken under
    chronoamperometry (the corroboration that every run was electrochemical)."""
    done = _apply(bdir, src, _finding(CONTROL, "potentiostatic", 3))
    assert done["applied"] and done["quote_check"]["failed"] == 0


def _miss(b: dict, path: str, run_id: str | None) -> dict:
    return next(m for m in b["missing_values"] if m["target_field_path"] == path and m["run_id"] == run_id
                and not B.is_answer_slot(m))


def _derived(b: dict) -> dict:
    return B.apply_derivations(json.loads(json.dumps(b)))


def _rule(o: dict) -> str | None:
    return (o.get("fill") or {}).get("rule_id") if o.get("value_state") == B.STATE_FILLED else None


def _env_rules(b: dict) -> dict[str, str | None]:
    return {r: _rule(_miss(b, ENV, r)) for r in RUNS}


def _ai(target_id: str, value, n: int = 1) -> dict:
    """An in-memory AI reading of one target (unchecked: it can disagree, it can never fill)."""
    return {"interpretation_id": f"ai-syn-{n:04d}", "target": {"kind": "missing_value", "id": target_id},
            "proposed_value": value, "strength": "stated", "quote": "SYNTHETIC", "model": {"model_id": MODEL}}


# --- the rules, the version ------------------------------------------------------------------------------------------


def test_the_four_rules_are_registered_in_one_sentence_each_at_format_1_20_0_rule_set_3():
    assert B.FORMAT_VERSION == "1.20.0" == B._VERSION_ORDER[-1] and B.FILL_RULE_SET == 3
    assert B.FOLDER_FILL_RULES == {B.FILL_ENVIRONMENT_RULE_ID, B.FILL_FACILITY_RULE_ID, B.FILL_ORGANIZATION_RULE_ID,
                                   B.FILL_GROUP_RULE_ID} and B.FOLDER_FILL_RULES <= set(B.FILL_RULES)
    assert set(B.bundle_schema()["$defs"]["fill"]["properties"]["rule_id"]["enum"]) == set(B.FILL_RULES)
    for rule_id in B.FOLDER_FILL_RULES:
        text = B.FILL_RULES[rule_id]
        assert text.startswith(rule_id + ": ") and ". " not in text, rule_id
    assert "1.20.0" in B.CHANGES_ADDED_IN and all(r in B.CHANGES_ADDED_IN["1.20.0"] for r in B.FOLDER_FILL_RULES)
    assert "potential scale plays no part" in B.FILL_ENVIRONMENT_RULE
    assert B.ENVIRONMENT_CONVENTIONS == ("operando", "in_situ", "per_run")
    assert B.ENVIRONMENT_CONVENTION_DECISION in B.DECISIONS_BY_KIND["experiment"]
    assert B.ENVIRONMENT_CONVENTION_DECISION in B.bundle_schema()["$defs"]["scientist_decision"]["properties"]["decision"]["enum"]
    for text in (B.FILL_ENVIRONMENT_RULE, B.CHANGES_ADDED_IN["1.20.0"]):  # review I6: no real logbook words or set-points
        assert "must be collected" not in text and "60 mV" not in text


def test_the_import_keeps_the_readme_header_lines(imported):
    b = M.load(imported[1])
    assert B.validate_bundle(b) == []
    lines = b["experiment"]["beamtime_header_lines"]
    assert [(h["locator"], h["literal"]) for h in lines] == [
        ("line 1", "# 2031-01_Quillfeather"),
        ("line 2", "# SYNTHETIC FIXTURE -- NOT INSTRUMENT OUTPUT. PI: Ada Quillfeather (synthetic)")]
    assert {h["relative_path"] for h in lines} == {"readme.txt"}


# --- Rule B: the facility and beamline -------------------------------------------------------------------------------


def test_the_facility_and_beamline_the_folder_and_the_fingerprint_agree_on_are_filled_for_every_run(imported):
    b = M.load(imported[1])
    for r in RUNS:
        f, bl = _miss(b, FACILITY, r), _miss(b, BEAMLINE, r)
        assert f["fill"] == {"rule_id": B.FILL_FACILITY_RULE_ID, "value": "SSRL"}, r
        assert bl["fill"] == {"rule_id": B.FILL_FACILITY_RULE_ID, "value": "BL15-2"}, r  # the fingerprint's spelling
        assert f["eligibility_for_official_record"]["eligible"] and bl["eligibility_for_official_record"]["eligible"]
    for path in ("system.facility.site", "system.facility.organization", "system.facility.endstation"):
        assert _miss(b, path, "run-001")["value_state"] == B.STATE_MISSING, path  # no hint names them: asked
    # the fingerprint's own statement says the two together are a rule's evidence (no longer "hints, never answers")
    statement = b["experiment"]["acquisition_system"]["fingerprint"]["statement"]
    assert B.FILL_FACILITY_RULE_ID in statement and "Both are hints, never answers" not in statement


@pytest.mark.parametrize("folder", [
    "SSRL_BL62_2031-01_Quillfeather_ZzTestCat",   # another beamline than the fingerprint's
    "SYNF_BL152_2031-01_Quillfeather_ZzTestCat",  # another facility word than the fingerprint's
    "Quillfeather_ZzTestCat_2031-01",             # the folder names no beamline: only one source
])
def test_no_facility_fill_when_the_folder_and_the_fingerprint_disagree_or_one_is_missing(tmp_path, folder):
    _, out = _import(tmp_path, folder)
    b = M.load(out)
    assert B.validate_bundle(b) == []
    for r in RUNS:
        for path in (FACILITY, BEAMLINE):
            assert _miss(b, path, r)["value_state"] == B.STATE_MISSING, (folder, path, r)
    assert _miss(b, ORG, None)["value_state"] == B.STATE_MISSING  # no facility identified: no organization either


def test_no_facility_fill_without_the_fingerprint(bdir):
    b = M.load(bdir)
    assert _rule(_miss(_derived(b), FACILITY, "run-001")) == B.FILL_FACILITY_RULE_ID  # positive control
    del b["experiment"]["acquisition_system"]["fingerprint"]
    d = _derived(b)
    assert all(_miss(d, FACILITY, r)["value_state"] == B.STATE_MISSING for r in RUNS)
    assert _miss(d, ORG, None)["value_state"] == B.STATE_MISSING


def test_a_run_whose_own_files_carry_no_fingerprint_statement_is_not_filled(bdir):
    """Review I3: the fingerprint is the beamtime's, but each run's fill needs the run's OWN header lines."""
    b = M.load(bdir)
    for c in b["candidates"]:
        if c["run_id"] == "run-003" and c.get("statement_key") == "detector_column":
            for e in c["evidence"]:
                e["literal_value"] = "synenergy"  # a column no fingerprint names
    d = _derived(b)
    assert _miss(d, FACILITY, "run-003")["value_state"] == B.STATE_MISSING
    assert _miss(d, BEAMLINE, "run-003")["value_state"] == B.STATE_MISSING
    assert _rule(_miss(d, FACILITY, "run-004")) == B.FILL_FACILITY_RULE_ID  # the other runs still are


def test_a_scientist_naming_another_facility_for_one_run_stops_the_facility_and_organization_fills(bdir):
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, FACILITY, "run-002")["value_id"]], decision="correct",
             value="SYN Other Lightsource", **BY)
    b = M.load(bdir)
    assert _miss(b, FACILITY, "run-002")["value_state"] == B.STATE_SCIENTIST_CONFIRMED
    assert all(_miss(b, FACILITY, r)["value_state"] == B.STATE_MISSING for r in RUNS if r != "run-002")
    assert _miss(b, ORG, None)["value_state"] == B.STATE_MISSING  # the facility is disputed
    assert B.validate_bundle(b) == []


@pytest.mark.parametrize("path,run_id", [(FACILITY, "run-002"), (BEAMLINE, "run-005"), (ORG, None)])
def test_a_reject_of_any_facility_or_organization_fill_disputes_the_facility_for_the_whole_beamtime(bdir, path, run_id):
    """Review I2: a rejected fill says the identity is wrong somewhere, so Rules B and C stop everywhere."""
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, path, run_id)["value_id"]], decision="reject", value=None, **BY)
    b = M.load(bdir)
    assert B.validate_bundle(b) == []
    for r in RUNS:
        assert _miss(b, FACILITY, r)["value_state"] != B.STATE_FILLED, (path, r)
        assert _miss(b, BEAMLINE, r)["value_state"] != B.STATE_FILLED, (path, r)
    assert _miss(b, ORG, None)["value_state"] != B.STATE_FILLED


def test_a_defer_on_one_run_beats_its_fill_and_leaves_the_others_filled(bdir):
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, BEAMLINE, "run-003")["value_id"]], decision="defer", value=None, **BY)
    b = M.load(bdir)
    assert _miss(b, BEAMLINE, "run-003")["value_state"] == B.STATE_MISSING and "fill" not in _miss(b, BEAMLINE, "run-003")
    assert all(_rule(_miss(b, BEAMLINE, r)) == B.FILL_FACILITY_RULE_ID for r in RUNS if r != "run-003")
    # a correct with the same value keeps every fill and the identity
    M.decide(bdir, target_ids=[_miss(b, FACILITY, "run-004")["value_id"]], decision="correct", value="SSRL", **BY)
    b = M.load(bdir)
    assert _miss(b, FACILITY, "run-004")["value_state"] == B.STATE_SCIENTIST_CONFIRMED
    assert _rule(_miss(b, FACILITY, "run-005")) == B.FILL_FACILITY_RULE_ID and _rule(_miss(b, ORG, None))


def test_a_reading_naming_another_beamline_stops_the_fill(bdir):
    b = M.load(bdir)
    assert all(_rule(_miss(_derived(b), BEAMLINE, r)) == B.FILL_FACILITY_RULE_ID for r in RUNS)  # positive control
    b["ai_interpretations"].append(_ai(_miss(b, BEAMLINE, "run-006")["value_id"], "BL4-3"))
    d = _derived(b)
    assert all(_miss(d, BEAMLINE, r)["value_state"] != B.STATE_FILLED for r in RUNS)
    assert all(_miss(d, FACILITY, r)["value_state"] != B.STATE_FILLED for r in RUNS)


# --- Rule C: the organization ----------------------------------------------------------------------------------------


def test_the_organization_is_the_identified_facility(imported):
    b = M.load(imported[1])
    m = _miss(b, ORG, None)
    assert m["fill"] == {"rule_id": B.FILL_ORGANIZATION_RULE_ID, "value": "SSRL"}
    assert m["eligibility_for_official_record"]["eligible"] is True


def test_the_organization_is_not_filled_when_a_reading_names_another(bdir):
    b = M.load(bdir)
    assert _rule(_miss(_derived(b), ORG, None)) == B.FILL_ORGANIZATION_RULE_ID  # positive control
    b["ai_interpretations"].append(_ai(_miss(b, ORG, None)["value_id"], "SYN University"))
    d = _derived(b)
    assert _miss(d, ORG, None)["value_state"] != B.STATE_FILLED
    assert _rule(_miss(d, FACILITY, "run-001")) == B.FILL_FACILITY_RULE_ID  # another organization: the facility stands


def test_a_decision_on_the_organization_wins(bdir):
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, ORG, None)["value_id"]], decision="correct", value="SYN University", **BY)
    m = _miss(M.load(bdir), ORG, None)
    assert m["value_state"] == B.STATE_SCIENTIST_CONFIRMED and "fill" not in m


# --- Rule D: the group -----------------------------------------------------------------------------------------------


def test_the_group_is_the_full_name_a_labelled_readme_line_gives_with_the_agreeing_header_as_a_witness(imported):
    b = M.load(imported[1])
    m = _miss(b, GROUP, None)
    assert m["fill"] == {"rule_id": B.FILL_GROUP_RULE_ID, "value": "Ada Quillfeather group"}
    found = B.fill_context(b)["group"]
    assert [t["literal"] for t in found["agreeing"]] == ["# 2031-01_Quillfeather"]


@pytest.mark.parametrize("readme,value", [
    ("# 2031-01_Quillfeather\n\nZz\n", "Quillfeather group"),  # the readme agrees; no full name: the folder's token
    # review I5: a full name only from a labelled position, never from any capitalised words
    ("# 2031-01_Quillfeather\n# Thanks Ada Quillfeather (synthetic)\n", "Quillfeather group"),
    ("# 2031-01_Quillfeather\n# Beamtime Ada Quillfeather (synthetic)\n", "Quillfeather group"),
    ("# Users: Ada Quillfeather, Cy Zzyzx (synthetic)\n", "Ada Quillfeather group"),  # the labelled line is the source
])
def test_the_group_value_by_what_the_files_hold(tmp_path, readme, value):
    _, out = _import(tmp_path, readme=readme)
    m = _miss(M.load(out), GROUP, None)
    assert m["fill"] == {"rule_id": B.FILL_GROUP_RULE_ID, "value": value}


def test_the_folders_token_alone_is_not_filled(tmp_path):
    """Review C1: a second source must agree; the folder alone stays a question (with the folder as its hint)."""
    _, out = _import(tmp_path, readme="Zz\n")
    b = M.load(out)
    assert _miss(b, GROUP, None)["value_state"] == B.STATE_MISSING
    assert any(q for q in Q.consolidate(b)["questions"] if q.get("target_field_path") == GROUP
               or GROUP in (q.get("fields") or {}))
    # a data path that names the folder's PI is a second source
    f = next(e for e in b["extended_context"] if e["concept"] == "spec_file_declaration")
    f["raw_literal"] = f"/data/fifteen/2031-01_Quillfeather/{f['raw_literal']}"
    assert _miss(_derived(b), GROUP, None)["fill"] == {"rule_id": B.FILL_GROUP_RULE_ID, "value": "Quillfeather group"}
    # so is a contributor whose name ends in it (and it gives the full name)
    b = M.load(out)
    b["contributors"].append({"contributor_id": "person-099", "name": "Ada Quillfeather (synthetic)",
                              "labels": ["Operator"], "scope": "beamtime", "run_ids": [], "evidence": [],
                              "role": "provenance", "is_actor": False, "is_naming_profile": False,
                              "value_state": "source_recorded"})
    assert _miss(_derived(b), GROUP, None)["fill"] == {"rule_id": B.FILL_GROUP_RULE_ID, "value": "Ada Quillfeather group"}


@pytest.mark.parametrize("header", ["# 2031-01_Otherperson", "# 2031-01_OTHERPERSON"])  # whatever its case
def test_a_readme_naming_another_pi_in_the_same_place_means_no_group_fill(imported, tmp_path, header):
    assert _rule(_miss(M.load(imported[1]), GROUP, None)) == B.FILL_GROUP_RULE_ID  # positive control
    _, out = _import(tmp_path, readme=header + "\n# PI: Ada Quillfeather (synthetic)\n")
    b = M.load(out)
    assert _miss(b, GROUP, None)["value_state"] == B.STATE_MISSING
    assert _rule(_miss(b, FACILITY, "run-001")) == B.FILL_FACILITY_RULE_ID  # the facility rule does not care


@pytest.mark.parametrize("line", ["# PI: Bob Smith", "PI: Bob Smith", "# Users: Bob Smith, Cy Jones",
                                  "# PI: bob smith"])  # round 3, C-1: a PI line in lower case names a person too
def test_a_labelled_line_naming_other_people_means_no_group_fill(tmp_path, line):
    """Review C2: the readme's PI / users line names people and none of them is the folder's PI: asked."""
    _, control = _import(tmp_path / "control", readme="# 2031-01_Quillfeather\n")
    assert _rule(_miss(M.load(control), GROUP, None)) == B.FILL_GROUP_RULE_ID  # positive control: it would fire
    _, out = _import(tmp_path / "other", readme=f"# 2031-01_Quillfeather\n{line}\n")
    assert _miss(M.load(out), GROUP, None)["value_state"] == B.STATE_MISSING


def test_a_spec_data_path_naming_another_pi_means_no_group_fill_and_an_agreeing_one_is_a_witness(bdir):
    b = M.load(bdir)
    f = next(e for e in b["extended_context"] if e["concept"] == "spec_file_declaration")
    stem = f["raw_literal"]
    f["raw_literal"] = f"/data/fifteen/2031-01_Otherperson/{stem}"
    assert _miss(_derived(b), GROUP, None)["value_state"] == B.STATE_MISSING
    f["raw_literal"] = f"/data/fifteen/2031-01_Quillfeather/{stem}"
    d = _derived(b)
    assert _rule(_miss(d, GROUP, None)) == B.FILL_GROUP_RULE_ID
    assert f["raw_literal"] in [t["literal"] for t in B.fill_context(d)["group"]["agreeing"]]


@pytest.mark.parametrize("folder", [
    "SSRL_BL152_2031-01_XAS_ZzTestCat",           # an acronym / a technique, not a surname
    "SSRL_BL152_2031-01_Operando_ZzTestCat",      # a technique word
    "SSRL_BL152_2031-01_Beamtime_ZzTestCat",      # a housekeeping word
    "SSRL_BL152_2031-01_2031_ZzTestCat",          # a number
    "SSRL_BL152_2031-01_Pt_ZzTestCat",            # review C1: an element symbol
    "SSRL_BL152_2031-01_IrOx_ZzTestCat",          # a formula
    "SSRL_BL152_2031-01_Mehta-Lab_ZzTestCat",     # a lab's name
    "SSRL_BL152_2031-01_Quillfeather",            # no project: not the pattern
    "SSRL_BL152_Quillfeather_2031-01_ZzTestCat",  # the surname not after the month
])
def test_no_group_fill_when_the_folder_does_not_name_a_pi(tmp_path, folder):
    token = folder.split("_")[3] if folder.count("_") >= 4 else "Quillfeather"
    _, out = _import(tmp_path, folder, readme=f"# 2031-01_{token}\n")  # a second source would agree
    assert _miss(M.load(out), GROUP, None)["value_state"] == B.STATE_MISSING, folder


def test_the_surname_test():
    for tok in ("Quillfeather", "O'Quill-Feather", "McQuill", "Quillféather", "Brown", "Dyson"):
        assert B.surname_like(tok), tok
    for tok in ("SSRL", "XAS", "HERFD", "quillfeather", "Operando", "Beamtime", "Data", "2031", "BL152", "Q1",
                "January", "Pellets", "Q", "Pt", "IrOx", "TiON", "Co", "Cu-Zn", "Mehta-Lab", "Lab", "Group", "Team"):
        assert not B.surname_like(tok), tok


def test_no_group_fill_in_a_bundle_imported_before_the_readme_header_was_kept(bdir):
    b = M.load(bdir)
    assert _rule(_miss(_derived(b), GROUP, None)) == B.FILL_GROUP_RULE_ID  # positive control
    del b["experiment"]["beamtime_header_lines"]
    assert B.validate_bundle(_derived(b)) == []  # the field is optional
    assert _miss(_derived(b), GROUP, None)["value_state"] == B.STATE_MISSING


def test_a_reading_or_a_decision_naming_another_group_beats_the_folder(bdir):
    b = M.load(bdir)
    b["ai_interpretations"].append(_ai(_miss(b, GROUP, None)["value_id"], "SYN group"))
    assert _miss(_derived(b), GROUP, None)["value_state"] != B.STATE_FILLED
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, GROUP, None)["value_id"]], decision="defer", value=None, **BY)
    m = _miss(M.load(bdir), GROUP, None)
    assert m["value_state"] == B.STATE_MISSING and "fill" not in m


def test_a_checked_reading_naming_another_full_name_never_overrides_the_pi_line(bdir, src):
    """Round 3, C-1: the readme's PI line names Ada Quillfeather; a reading's "group of Bo Quillfeather" only backs up."""
    done = _apply(bdir, src, _finding("sample.sample_form", "pellet", 5))  # its quote: "the group of Bo Quillfeather"
    assert done["applied"] and done["quote_check"]["failed"] == 0
    assert _miss(M.load(bdir), GROUP, None)["fill"] == {"rule_id": B.FILL_GROUP_RULE_ID, "value": "Ada Quillfeather group"}


def test_two_full_names_at_backing_positions_fall_back_to_the_surname(tmp_path):
    _, out = _import(tmp_path, readme="# 2031-01_Quillfeather\n# Users: Ada Quillfeather, Bo Quillfeather\n")
    assert _miss(M.load(out), GROUP, None)["fill"] == {"rule_id": B.FILL_GROUP_RULE_ID, "value": "Quillfeather group"}


# --- Rule A: the held potential, and the beamtime's environment convention -------------------------------------------


def _env_q(b: dict) -> dict | None:
    return next((q for q in Q.consolidate(b)["questions"] if q["kind"] == Q.ENV_CONVENTION_KIND), None)


def _per_run_env_q(b: dict) -> dict:
    return next(q for q in Q.consolidate(b)["questions"] if q.get("target_field_path") == ENV)


def _convention(bdir: Path, value: str) -> None:
    M.decide_question(bdir, question_id=Q.ENV_CONVENTION_QUESTION_ID, decision=B.ENVIRONMENT_CONVENTION_DECISION,
                      value=value, **BY)


@pytest.fixture()
def held(bdir, src) -> Path:
    """The bundle with the corroboration (a checked chronoamperometry reading for the whole beamtime)."""
    _chronoamperometry(bdir, src)
    return bdir


def test_no_corroboration_no_question_and_no_fill(imported):
    """Every run's own name gives a set-point, but nothing says the runs were electrochemical (the file names'
    acid/base give no electrolyte value): no convention question, and each run's environment is asked."""
    b = M.load(imported[1])
    facts = B.fill_context(b)["held_potential"]["runs"]
    assert all(facts[r]["setpoints"] for r in RUNS) and not any(facts[r]["corroboration"] for r in RUNS)
    assert _env_q(b) is None and set(_env_rules(b).values()) == {None}
    assert _per_run_env_q(b)["blocking"] is True


def test_the_convention_is_asked_once_and_covers_each_runs_environment_question(imported, held):
    before = _per_run_env_q(M.load(imported[1]))
    b = M.load(held)
    assert B.validate_bundle(b) == [] and set(_env_rules(b).values()) == {None}  # nothing is filled before the answer
    q = _env_q(b)
    assert q["question_id"] == Q.ENV_CONVENTION_QUESTION_ID and q["blocking"] is True and q["scope"] == "experiment"
    assert q["allowed_values"] == ["operando", "in_situ", "per_run"]
    assert q["allowed_decisions"] == [B.ENVIRONMENT_CONVENTION_DECISION]
    assert len(q["covers_value_ids"]) == 9 and q["text"].startswith("9 measurements were taken in electrolyte")
    assert "at 0.1 V" in q["text"] and "operando or in situ" in q["text"]
    assert any(h["kind"] == "reading" and h["literal"] == MEMO_LINES[3] for h in q["hints"])
    assert any(h["kind"] == "file_literal" and h["literal"] == "100mV" for h in q["hints"])
    per_run = _per_run_env_q(b)
    assert per_run["question_id"] == before["question_id"]  # its id unchanged
    assert per_run["blocking"] is False and per_run["covered_by"] == Q.ENV_CONVENTION_QUESTION_ID
    blocking_env = [x for x in Q.consolidate(b)["questions"] if x["blocking"]
                    and (x["kind"] == Q.ENV_CONVENTION_KIND or x.get("target_field_path") == ENV)]
    assert [x["question_id"] for x in blocking_env] == [Q.ENV_CONVENTION_QUESTION_ID]  # one question, not one per run


@pytest.mark.parametrize("value", ["operando", "in_situ"])
def test_the_answer_fills_every_held_run_with_it(held, value):
    _convention(held, value)
    b = M.load(held)
    assert B.validate_bundle(b) == []
    assert set(_env_rules(b).values()) == {B.FILL_ENVIRONMENT_RULE_ID}
    m = _miss(b, ENV, "run-001")
    assert m["fill"] == {"rule_id": B.FILL_ENVIRONMENT_RULE_ID, "value": value}
    assert m["eligibility_for_official_record"]["eligible"] is True
    assert _env_q(b) is None  # answered: no longer asked
    assert not [q for q in Q.consolidate(b)["questions"] if q.get("target_field_path") == ENV]
    # the potential scale is not needed, and is not filled (DEC-88's gate on the set-point itself is kept)
    assert _miss(b, "context.electrochemistry.potential_scale", "run-001")["value_state"] == B.STATE_MISSING


def test_per_run_fills_nothing_and_gives_each_runs_question_back_under_its_id(held):
    covered = _per_run_env_q(M.load(held))
    _convention(held, "per_run")
    b = M.load(held)
    assert set(_env_rules(b).values()) == {None} and _env_q(b) is None
    q = _per_run_env_q(b)
    assert q["question_id"] == covered["question_id"] and q["blocking"] is True and not q.get("covered_by")
    assert len(q["targets"]) == 9


def test_the_convention_is_answered_on_the_experiment_target_too_and_refuses_other_values(held):
    with pytest.raises(M.MutationRefused, match="operando, in_situ or per_run"):
        M.decide(held, target_ids=["experiment"], decision=B.ENVIRONMENT_CONVENTION_DECISION, value="ex_situ", **BY)
    M.decide(held, target_ids=["experiment"], decision=B.ENVIRONMENT_CONVENTION_DECISION, value="operando", **BY)
    assert set(_env_rules(M.load(held)).values()) == {B.FILL_ENVIRONMENT_RULE_ID}
    with pytest.raises(M.MutationRefused):  # a run is no target of it
        M.decide(held, target_ids=[_miss(M.load(held), ENV, "run-001")["value_id"]],
                 decision=B.ENVIRONMENT_CONVENTION_DECISION, value="operando", **BY)


def test_answer_memory_never_learns_the_convention(held):
    from isaac_api.local_import import answer_memory as AM

    _convention(held, "operando")
    assert not [v for v in AM.person_values(M.load(held)) if v["field"] == ENV]


def test_a_scientists_answer_to_one_runs_electrolyte_corroborates_that_run_only(bdir):
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, ELECTROLYTE, "run-007")["value_id"]], decision="correct",
             value="SYN hydroxide", **BY)
    b = M.load(bdir)
    assert [B.is_answer_slot(m) for m in b["missing_values"] if m["value_id"] in _env_q(b)["covers_value_ids"]] == [False]
    assert _env_q(b)["covers_value_ids"] == [_miss(b, ENV, "run-007")["value_id"]]
    _convention(bdir, "operando")
    rules = _env_rules(M.load(bdir))
    assert rules["run-007"] == B.FILL_ENVIRONMENT_RULE_ID
    assert {r: v for r, v in rules.items() if r != "run-007"} == {r: None for r in RUNS if r != "run-007"}


@pytest.mark.parametrize("value", ["None (dry)", "none", "no electrolyte", "dry", "not used", "n/a", "N/A",
                                   "without electrolyte"])
def test_an_answer_of_no_electrolyte_blocks_and_never_corroborates(bdir, value):
    """Review C3: an answer (or a reading) saying there was no electrolyte never makes a run operando."""
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, ELECTROLYTE, "run-007")["value_id"]], decision="correct", value=value, **BY)
    b = M.load(bdir)
    assert _env_q(b) is None
    facts = B.fill_context(b)["held_potential"]["runs"]["run-007"]
    assert facts["blocked"] and not facts["corroboration"]


def test_a_beamtime_reading_of_no_electrolyte_blocks_every_run(held):
    b = M.load(held)
    assert _env_q(b) is not None  # positive control
    i = _ai(_miss(b, ELECTROLYTE, "run-007")["value_id"], "none", 9)
    i["scope"] = "experiment"
    b["ai_interpretations"].append(i)
    d = _derived(b)
    assert B.fill_context(d)["held_potential"]["beamtime"]["blocked"] and _env_q(d) is None


def test_the_control_words_of_a_quote():
    assert B._quote_names_echem_control("SYNTHETIC: the scans ran under chronoamperometry")
    assert B._quote_names_echem_control("the potentiostat held 1.2 V; then we moved")
    assert not B._quote_names_echem_control("no chronoamperometry was run (SYNTHETIC)")
    assert not B._quote_names_echem_control("we didn't use the potentiostat")
    assert not B._quote_names_echem_control("held at room temperature")


@pytest.fixture()
def answered(held) -> dict:
    """Corroborated and the convention answered operando: every run is filled (the positive control of each test)."""
    _convention(held, "operando")
    b = M.load(held)
    assert set(_env_rules(b).values()) == {B.FILL_ENVIRONMENT_RULE_ID}
    return b


def test_a_reference_run_is_never_filled(answered):
    b = copy.deepcopy(answered)
    next(r for r in b["runs"] if r["run_id"] == "run-002")["source_type"] = "standard_or_reference"
    rules = _env_rules(_derived(b))
    assert rules["run-002"] is None and rules["run-001"] == B.FILL_ENVIRONMENT_RULE_ID


@pytest.mark.parametrize("token", ["OCV", "OCP", "dry", "dried", "NoElectrolyte", "asIs", "as_is", "insitu", "exsitu",
                                   "ex-situ", "in_situ", "operando", "postmortem", "air", "ambient", "pristine", "OCV-1",
                                   "atOCV", "insitu1", "Insitu2", "dry2", "OCV3"])  # round 3: digits after any word
def test_a_run_whose_own_name_holds_an_environment_word_is_never_filled(answered, token):
    """Review C4: any environment word, open circuit, dry, as-is or no electrolyte in the run's own name: asked."""
    b = copy.deepcopy(answered)
    run = next(r for r in b["runs"] if r["run_id"] == "run-003")
    run["stem"] = run["stem"] + "_" + token
    rules = _env_rules(_derived(b))
    assert rules["run-003"] is None and rules["run-004"] == B.FILL_ENVIRONMENT_RULE_ID


def test_after_in_a_name_is_no_environment_word(answered):
    b = copy.deepcopy(answered)
    run = next(r for r in b["runs"] if r["run_id"] == "run-003")
    run["stem"] = "03_01_ZZ1_acid_after900Cycling_filter10_400mV"
    assert _env_rules(_derived(b))["run-003"] == B.FILL_ENVIRONMENT_RULE_ID


def test_a_reading_of_open_circuit_stops_the_fill(answered):
    b = copy.deepcopy(answered)
    assert _env_rules(_derived(b))["run-004"] == B.FILL_ENVIRONMENT_RULE_ID  # positive control, same fixture
    b["ai_interpretations"].append(_ai(_miss(b, CONTROL, "run-004")["value_id"], "open_circuit", 7))
    assert _env_rules(_derived(b))["run-004"] is None


def test_after_the_answer_a_stated_reading_that_differs_blocks_and_an_inferred_one_does_not(answered):
    b = copy.deepcopy(answered)
    stated = _ai(_miss(b, ENV, "run-005")["value_id"], "in_situ", 8)
    inferred = {**_ai(_miss(b, ENV, "run-006")["value_id"], "ex_situ", 10), "strength": "inferred"}
    b["ai_interpretations"] += [stated, inferred]
    rules = _env_rules(_derived(b))
    assert rules["run-005"] is None  # a stated reading of another environment: that run stays asked
    assert rules["run-006"] == B.FILL_ENVIRONMENT_RULE_ID  # the scientist settled the convention over the inference


def test_an_environment_candidate_for_the_run_means_ask(answered):
    b = copy.deepcopy(answered)
    sp = next(c for c in b["candidates"] if c["run_id"] == "run-006" and c["target_field_path"] == SETPOINT)
    dry = copy.deepcopy(sp)  # the dry convention's ex_situ (a candidate of the environment for that run)
    dry.update(candidate_id="cand-9999", engine_candidate_id="syn::environment", target_field_path=ENV,
               statement_key="environment", value="ex_situ", rule="bl15.environment.dry_sample_is_ex_situ.v1: synthetic")
    b["candidates"].append(dry)
    rules = _env_rules(_derived(b))
    assert rules["run-006"] is None and rules["run-001"] == B.FILL_ENVIRONMENT_RULE_ID


def test_a_conflicting_or_contradicted_set_point_gives_no_fill(answered):
    b = copy.deepcopy(answered)
    sp8 = next(c for c in b["candidates"] if c["run_id"] == "run-008" and c["target_field_path"] == SETPOINT)
    sp8["evidence"][0]["relation"] = "contradicts"
    sp9 = next(c for c in b["candidates"] if c["run_id"] == "run-009" and c["target_field_path"] == SETPOINT)
    sp9["extracted_state"] = B.STATE_CONFLICTING
    rules = _env_rules(_derived(b))
    assert rules["run-008"] is None and rules["run-009"] is None and rules["run-007"] == B.FILL_ENVIRONMENT_RULE_ID


def test_a_rejected_set_point_is_no_held_potential(held):
    _convention(held, "operando")
    b = M.load(held)
    sp = next(c for c in b["candidates"] if c["run_id"] == "run-001" and c["target_field_path"] == SETPOINT)
    M.decide(held, target_ids=[sp["candidate_id"]], decision="reject", value=None, **BY)
    rules = _env_rules(M.load(held))
    assert rules["run-001"] is None and rules["run-002"] == B.FILL_ENVIRONMENT_RULE_ID


def test_a_decision_on_a_runs_environment_beats_the_convention(held):
    b = M.load(held)
    M.decide(held, target_ids=[_miss(b, ENV, "run-001")["value_id"]], decision="defer", value=None, **BY)
    M.decide(held, target_ids=[_miss(b, ENV, "run-002")["value_id"]], decision="correct", value="ex_situ", **BY)
    _convention(held, "operando")
    b = M.load(held)
    assert _miss(b, ENV, "run-001")["value_state"] == B.STATE_MISSING
    assert _miss(b, ENV, "run-002")["value_state"] == B.STATE_SCIENTIST_CONFIRMED
    assert _env_rules(b)["run-003"] == B.FILL_ENVIRONMENT_RULE_ID


def test_a_group_set_to_reference_then_rejected_then_revived_is_never_refused(held):
    """Review I1: the fills read each group's status and role, so both are derived before them."""
    _add_group(held, run_ids=("run-001", "run-002"))
    for decision, value in (("set_role", "reference"), ("reject", None), ("confirm", None)):
        M.decide(held, target_ids=["g1"], decision=decision, value=value, **BY)  # never refused as INVALID
        b = M.load(held)
        assert B.validate_bundle(b) == [] and b["counts"]["filled"] == sum(
            1 for o in [*b["candidates"], *b["missing_values"]] if o["value_state"] == B.STATE_FILLED)
    g = next(g for g in M.load(held)["record_groups"] if g["group_id"] == "g1")
    assert g["status"] == "scientist_confirmed" and g["role"] == "reference"
    _convention(held, "operando")
    rules = _env_rules(M.load(held))
    assert rules["run-001"] is None and rules["run-002"] is None and rules["run-003"] == B.FILL_ENVIRONMENT_RULE_ID


# --- questions, status, the question site ----------------------------------------------------------------------------


def _ids(b: dict) -> set[str]:
    return {q["question_id"] for q in Q.consolidate(b)["questions"]}


def test_filled_values_are_left_out_of_their_questions_and_the_ids_do_not_move(held, monkeypatch):
    b = M.load(held)
    M.decide(held, target_ids=[_miss(b, ENV, "run-001")["value_id"]], decision="defer", value=None, **BY)
    _convention(held, "operando")
    b = M.load(held)
    with_fills = _ids(b)
    with monkeypatch.context() as mp:  # what rule set 2 derived: none of the slice 3 rules
        mp.setattr(B, "folder_fill_for", lambda *a, **k: None)
        mp.setattr(B, "environment_convention_targets", lambda *a, **k: [])
        without = _ids(_derived(b))
    assert with_fills <= without  # no question is new, none changed its id
    asked = Q.consolidate(b)["questions"]
    targets = {t["id"] for q in asked for t in q.get("targets") or ()}
    for r in RUNS:
        assert _miss(b, FACILITY, r)["value_id"] not in targets and _miss(b, BEAMLINE, r)["value_id"] not in targets
    assert _miss(b, ORG, None)["value_id"] not in targets and _miss(b, GROUP, None)["value_id"] not in targets
    q = next(q for q in asked if q.get("target_field_path") == ENV)
    assert [t["id"] for t in q["targets"]] == [_miss(b, ENV, "run-001")["value_id"]]  # only the deferred run is asked
    assert q["question_id"] in without
    assert len(q["left_out_as_filled"]) == 8 and "Left out, because a rule filled the value from the evidence" in q["text"]


def test_status_counts_the_new_fills(held):
    _convention(held, "operando")
    facts = ST.status(held)["facts"]
    b = M.load(held)
    filled = sum(1 for o in [*b["candidates"], *b["missing_values"]] if o["value_state"] == B.STATE_FILLED)
    assert filled >= 9 + 18 + 2 and facts["values_filled"] == filled - len(Q.fills_asked(b))


def test_the_convention_card_goes_to_the_question_site_and_its_answer_comes_back(held, tmp_path):
    from isaac_api.local_import import question_site as SITE
    from isaac_api.local_import import question_site_import as SI

    site = tmp_path / "site"
    SITE.export_site(held, site, site_template=tmp_path / "no-template")
    data = json.loads((site / "data" / "site-data.json").read_text())
    [card] = [c for c in data["cards"] if c["card_id"] == SITE.card_id(ENV, [SITE.ENV_CONVENTION_TARGET_ID])]
    assert card["blocking"] is True and card["section"] == "beamtime" and card["applies_to"]["count"] == 9
    assert [o["value"] for o in card["answer"]["options"]] == ["operando", "in_situ", "per_run"]
    assert "operando or in situ" in card["title"]
    # each run's own environment question is covered meanwhile: no second card asks it
    assert not [c for c in data["cards"] if (c.get("field") or {}).get("path") == ENV]
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({
        "format": SI.ANSWERS_FORMAT_ID, "format_version": "1.0.0", "bundle_id": data["bundle_id"],
        "bundle_version": data["bundle_version"], "exported_at": "2100-02-01T10:00:00Z", "log": [],
        "answers": [{"card_id": card["card_id"], "action": "value", "value": "in_situ", "typed": False,
                     "note": "", "by": "SYN Scientist", "at": "2100-02-01T10:00:00Z"}]}))
    rep = SI.import_answers(held, answers, site_data=site / "data" / "site-data.json", apply=True)
    [a] = rep["answers"]
    assert a["outcome"] == "recorded", a
    b = M.load(held)
    assert B.environment_convention_decision(b)["value"] == "in_situ"
    assert _miss(b, ENV, "run-001")["fill"] == {"rule_id": B.FILL_ENVIRONMENT_RULE_ID, "value": "in_situ"}
    again = SI.import_answers(held, answers, site_data=site / "data" / "site-data.json", apply=True)
    assert [x["outcome"] for x in again["answers"]] != ["recorded"]  # a second import records nothing new


# --- composition ------------------------------------------------------------------------------------------------------


def test_a_merged_group_composes_the_environment_only_when_every_run_has_it(held):
    _add_group(held, run_ids=("run-001", "run-002"))
    b = M.load(held)
    M.decide(held, target_ids=[_miss(b, ENV, "run-002")["value_id"]], decision="defer", value=None, **BY)
    _convention(held, "operando")
    b = M.load(held)
    group = next(g for g in b["record_groups"] if g["group_id"] == "g1")
    draft, comp = R.compose_group(b, group, held)
    assert draft["fields"][ENV] == {"value": None, "status": "missing", "evidence": []}
    not_composed = [n for n in comp["not_composed"] if n.get("path") == ENV]
    assert not_composed and "1 of this record group's 2 measured runs only" in not_composed[0]["reason"]
    assert draft["fields"][FACILITY]["status"] == "inferred"  # both runs filled: it composes


def test_the_new_fills_compose_as_inferred_with_their_rule_and_pass_the_draft_validator(held, monkeypatch):
    from isaac_records.draft_validator import validate_draft

    _add_group(held, run_ids=("run-001", "run-002"))
    _convention(held, "operando")
    b = M.load(held)
    group = next(g for g in b["record_groups"] if g["group_id"] == "g1")
    built = []
    real = B._fingerprint_witness_index
    monkeypatch.setattr(B, "_fingerprint_witness_index", lambda *a, **k: built.append(1) or real(*a, **k))
    draft, comp = R.compose_group(b, group, held)
    assert len(built) == 1  # review I4: the run-to-witness map is built once per composition, not per filled value
    expected = {ENV: ("operando", B.FILL_ENVIRONMENT_RULE_ID), FACILITY: ("SSRL", B.FILL_FACILITY_RULE_ID),
                BEAMLINE: ("BL15-2", B.FILL_FACILITY_RULE_ID), ORG: ("SSRL", B.FILL_ORGANIZATION_RULE_ID),
                GROUP: ("Ada Quillfeather group", B.FILL_GROUP_RULE_ID)}
    for path, (value, rule) in expected.items():
        env = draft["fields"][path]
        assert env["value"] == value and env["status"] == "inferred", path
        derivations = [e for e in env["evidence"] if e.get("source_type") == "derivation"]
        assert derivations and all(d["rule"] == rule and d["rule_text"] == B.FILL_RULES[rule] and d.get("note")
                                   for d in derivations), path  # one per contributing run
    env_ev = draft["fields"][ENV]["evidence"]
    assert any(e.get("quote") == "100mV" for e in env_ev)  # the run's own set-point token
    assert any(e.get("quote") == MEMO_LINES[3] and e.get("method") == "ai_interpretation" for e in env_ev)
    conv = B.environment_convention_decision(b)
    assert any(e.get("source_type") == "user_confirmation" and e.get("decision_id") == conv["decision_id"]
               and e.get("answer") == "operando" for e in env_ev)  # the scientist's convention answer
    for path in (FACILITY, BEAMLINE, ORG):  # review: the run's own SPEC header line the fingerprint matched
        assert any(e.get("method_id") == B.ACQUISITION_FINGERPRINT_RULE_ID and e.get("quote") == "vortDT"
                   for e in draft["fields"][path]["evidence"]), path
    group_ev = draft["fields"][GROUP]["evidence"]
    assert any(e.get("source_type") == "file_listing" and e.get("quote") == FOLDER for e in group_ev)
    assert any(e.get("quote") == "# 2031-01_Quillfeather" for e in group_ev)
    assert {f["path"] for f in comp["filled_by_rule"]} >= set(expected)
    report = validate_draft(draft)
    assert report.ok, report.errors
    assert not [w for w in report.warnings if w[0].startswith(tuple("fields." + p for p in expected))], report.warnings


def test_the_witness_indexes_are_built_once_per_fill_context(answered):
    ctx = B.fill_context(answered)
    m = _miss(answered, ENV, "run-001")
    B.folder_fill_witnesses(answered, m, ctx, ["run-001"])
    first = ctx["_witness_index"]
    B.folder_fill_witnesses(answered, _miss(answered, ENV, "run-002"), ctx, ["run-002"])
    assert ctx["_witness_index"] is first


# --- versioning --------------------------------------------------------------------------------------------------------


def test_a_rule_set_2_bundle_is_stale_and_its_next_write_re_derives_it(bdir, monkeypatch, capsys):
    b = json.loads((bdir / "bundle.json").read_text())
    with monkeypatch.context() as mp:  # what rule set 2 derived: none of the slice 3 rules
        mp.setattr(B, "folder_fill_for", lambda *a, **k: None)
        B.apply_derivations(b)
    b["fill_rule_set"], b["format_version"] = 2, "1.19.0"
    b["experiment"].pop("beamtime_header_lines")  # a 1.19.0 build kept none
    assert _miss(b, FACILITY, "run-001")["value_state"] == B.STATE_MISSING
    (bdir / "bundle.json").write_text(json.dumps(b))
    errors, stale = B.validate_allowing_stale(b)
    moved = {s["id"] for s in stale if s.get("fill_moved")}
    assert errors == [] and _miss(b, FACILITY, "run-001")["value_id"] in moved and _miss(b, ORG, None)["value_id"] in moved
    assert _miss(b, GROUP, None)["value_id"] not in moved  # no header lines: the group waits for a re-import
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(bdir)]) == 1 and capsys.readouterr().out.startswith("STALE:")
    M.record_consent(bdir, by="SYN Scientist")
    saved = json.loads((bdir / "bundle.json").read_text())
    assert saved["fill_rule_set"] == 3 and saved["format_version"] == "1.20.0" and B.validate_bundle(saved) == []
    assert _rule(_miss(saved, FACILITY, "run-001")) == B.FILL_FACILITY_RULE_ID
    assert _miss(saved, FACILITY, "run-001")["value_id"] in {r["id"] for r in saved["eligibility_rederived"]}
    [u] = [u for u in saved["format_upgrades"] if u["from_format_version"] == "1.19.0"]
    assert B.CHANGES_ADDED_IN["1.20.0"] in u["statement"]


def test_a_newer_rule_set_is_refused(bdir):
    b = M.load(bdir)
    b["fill_rule_set"] = 4
    assert any("fill_rule_set 4 is newer" in e for e in B.validate_bundle(b))


def test_a_stored_fill_no_rule_gives_is_refused(bdir):
    b = M.load(bdir)
    m = _miss(b, ENV, "run-001")  # no corroboration and no convention: no rule fills it
    m["value_state"], m["fill"] = B.STATE_FILLED, {"rule_id": B.FILL_ENVIRONMENT_RULE_ID, "value": "operando"}
    errors = B.validate_bundle(b)
    assert f"state: {m['value_id']} is filled but only missing is supported" in errors
    assert any(e.startswith(f"state: {m['value_id']} fill ") and "is not what the registered fill rules give (None)" in e
               for e in errors)


def test_a_convention_decision_off_its_list_is_refused_by_the_validator(held):
    _convention(held, "operando")
    b = M.load(held)
    assert B.validate_bundle(b) == []
    b["scientist_decisions"].append({**b["scientist_decisions"][-1], "decision_id": "d-09998", "value": "ex_situ"})
    assert "decision: d-09998 set_environment_convention needs --value operando, in_situ or per_run" in B.validate_bundle(b)


# --- round 3 ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("readme", [
    "# 2031-01_Quillfeather\n# PI: Bob Smith\n# Users: Ada Quillfeather, Cy Jones\n",
    "# 2031-01_Quillfeather\n# Users: Ada Quillfeather, Cy Jones\n# PI: Bob Smith\n",  # the reverse order
    "# 2031-01_Quillfeather\n# PI: Bob Smith; Users: Ada Quillfeather\n",  # one line
])
def test_a_pi_line_takes_precedence_over_a_users_line(tmp_path, readme):
    """Round 3, C-1: the readme says the PI is someone else; a users line naming the folder's PI never overrides it."""
    _, out = _import(tmp_path, readme=readme)
    assert _miss(M.load(out), GROUP, None)["value_state"] == B.STATE_MISSING


def test_a_pi_line_naming_the_folders_pi_wins_over_a_users_line_naming_others(tmp_path):
    _, out = _import(tmp_path, readme="# 2031-01_Quillfeather\n# PI: Ada Quillfeather\n# Users: Bob Smith, Cy Jones\n")
    assert _miss(M.load(out), GROUP, None)["fill"] == {"rule_id": B.FILL_GROUP_RULE_ID, "value": "Ada Quillfeather group"}


def test_a_later_reading_that_extends_the_answer_is_said_and_reopens_the_question(bdir, src):
    """Round 3, I-1: answered when ONE run qualified; a later reading brings eight more under it. The fill goes on
    (one answer for the beamtime), but status says so and the question re-opens, optional, under its own id."""
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_miss(b, ELECTROLYTE, "run-007")["value_id"]], decision="correct",
             value="SYN hydroxide", **BY)
    _convention(bdir, "operando")
    b = M.load(bdir)
    conv = B.environment_convention_decision(b)
    assert conv[B.ENVIRONMENT_CONVENTION_COVERS_KEY] == [_miss(b, ENV, "run-007")["value_id"]]
    assert _env_q(b) is None and ST.status(bdir)["facts"]["environment_convention"]["more_since_the_answer"] == 0
    _chronoamperometry(bdir, src)  # now every run qualifies
    b = M.load(bdir)
    assert B.validate_bundle(b) == [] and set(_env_rules(b).values()) == {B.FILL_ENVIRONMENT_RULE_ID}
    facts = ST.status(bdir)
    assert facts["facts"]["environment_convention"] == {"value": "operando", "decision_id": conv["decision_id"],
                                                        "question_id": Q.ENV_CONVENTION_QUESTION_ID,
                                                        "given_for": 1, "more_since_the_answer": 8}
    [line] = [x for x in facts["lines"] if "8 more measurement(s) now take it" in x]
    # round 4: the re-opened question has no site card, so the line says how to confirm it
    assert (f"--question {Q.ENV_CONVENTION_QUESTION_ID} --decision set_environment_convention --value operando" in line
            and "no card" in line)
    q = _env_q(b)
    assert q["question_id"] == Q.ENV_CONVENTION_QUESTION_ID and q["blocking"] is False
    assert "8 more measurements now take your answer" in q["text"] and len(q["extends_to_value_ids"]) == 8
    m = _miss(b, ENV, "run-001")
    group = {"group_id": "g-syn", "member_run_keys": [r["run_key"] for r in b["runs"] if r["run_id"] == "run-001"]}
    witnesses, note = B.folder_fill_witnesses(b, m, B.fill_context(b), ["run-001"])
    assert "qualified only after that answer" in note and group
    # answered again with the same value: a NEW statement (it covers them now), and the question closes
    _convention(bdir, "operando")
    b = M.load(bdir)
    assert len(B.environment_convention_decision(b)[B.ENVIRONMENT_CONVENTION_COVERS_KEY]) == 9
    assert _env_q(b) is None and ST.status(bdir)["facts"]["environment_convention"]["more_since_the_answer"] == 0


def test_a_run_no_record_is_built_from_is_neither_asked_nor_filled(answered):
    """Round 3, I-2: the fill reaches exactly the runs the question counts."""
    b = copy.deepcopy(answered)
    next(r for r in b["runs"] if r["run_id"] == "run-005")["run_candidate"] = False
    d = _derived(b)
    assert _env_rules(d)["run-005"] is None and _env_rules(d)["run-004"] == B.FILL_ENVIRONMENT_RULE_ID
    assert _miss(d, ENV, "run-005")["value_id"] not in B.environment_convention_covers_now(d)


def test_an_inferred_reading_whose_checked_quote_names_chronoamperometry_corroborates(bdir, src):
    """Round 3, I-3: corroboration is the checked QUOTE's words, never the reading's value: an inferred reading counts."""
    done = _apply(bdir, src, _finding(CONTROL, "potentiostatic", 3, strength="inferred"))
    assert done["applied"] and done["quote_check"]["failed"] == 0
    b = M.load(bdir)
    assert all(B.fill_context(b)["held_potential"]["beamtime"]["corroboration"] or
               B.fill_context(b)["held_potential"]["runs"][r]["corroboration"] for r in RUNS)
    assert len(_env_q(b)["covers_value_ids"]) == 9
    # its VALUE corroborates nothing: an inferred reading of a valued field whose quote names no control
    assert not B._quote_names_echem_control(MEMO_LINES[5])


def test_a_run_with_a_stated_reading_of_its_environment_is_asked_on_its_own_while_the_convention_is_open(held):
    """Round 3: the question says such a run "is still asked on its own" — so it is never covered by it."""
    b = M.load(held)
    b["ai_interpretations"].append(_ai(_miss(b, ENV, "run-005")["value_id"], "ex_situ", 11))
    d = _derived(b)
    q = _env_q(d)
    assert _miss(d, ENV, "run-005")["value_id"] not in q["covers_value_ids"] and len(q["covers_value_ids"]) == 8
    per_run = _per_run_env_q(d)
    assert [t["id"] for t in per_run["targets"]] == [_miss(d, ENV, "run-005")["value_id"]]
    assert per_run["blocking"] is True and len(per_run["covered_by_convention"]) == 8


def test_the_card_lists_what_the_answer_reaches_and_the_earlier_readings(bdir, src, tmp_path):
    from isaac_api.local_import import question_site as SITE

    _chronoamperometry(bdir, src)
    done = _apply(bdir, src, _finding(ENV, "in_situ", 3, runs=["01_01_ZZ1_acid_after500Cycling_filter10_100mV"],
                                      strength="inferred"))
    assert done["applied"]
    site = tmp_path / "site"
    SITE.export_site(bdir, site, site_template=tmp_path / "no-template")
    data = json.loads((site / "data" / "site-data.json").read_text())
    [card] = [c for c in data["cards"] if c["card_id"] == SITE.card_id(ENV, [SITE.ENV_CONVENTION_TARGET_ID])]
    assert "'01_01_ZZ1_acid_after500Cycling_filter10_100mV'" in card["detail"] and "and 6 more" in card["detail"]
    earlier = [c for c in card["context"] if c.get("label", "").startswith("An earlier reading suggested")]
    assert earlier and earlier[0]["rows"] == [["01_01_ZZ1_acid_after500Cycling_filter10_100mV", "in_situ"]]


# --- round 4 ----------------------------------------------------------------------------------------------------------


def _covered(b: dict) -> set[str]:
    q = _env_q(b)
    return {next(m["run_id"] for m in b["missing_values"] if m["value_id"] == v) for v in q["covers_value_ids"]} if q else set()


def test_a_clean_quote_of_any_strength_corroborates_every_run(bdir, src):
    """The positive control of the quote guards below: a clean quote corroborates the whole beamtime."""
    _apply(bdir, src, _finding(ENV, "operando", 3, strength="inferred"))
    assert _covered(M.load(bdir)) == set(RUNS)


@pytest.mark.parametrize("path,value", [(ENV, "ex_situ"), (CONTROL, "potentiostatic")])
def test_a_quote_that_says_one_sample_was_dry_corroborates_nothing(bdir, src, path, value):
    """Round 4 (reproduced by the review): "…used for sample ZZ9; ZZ1 was measured dry after the hold" never makes the
    ZZ1 runs operando, whatever the reading proposes."""
    done = _apply(bdir, src, _finding(path, value, 7, strength="inferred"))
    assert done["applied"] and done["quote_check"]["failed"] == 0
    b = M.load(bdir)
    assert _env_q(b) is None and not B.fill_context(b)["held_potential"]["beamtime"]["corroboration"]


def test_a_quote_about_another_sample_only_corroborates_no_run_of_these_samples(bdir, src):
    done = _apply(bdir, src, _finding(CONTROL, "potentiostatic", 8, strength="inferred"))  # "for sample ZZ9 only"
    assert done["applied"]
    assert _env_q(M.load(bdir)) is None


def test_a_quote_of_a_plan_corroborates_nothing(bdir, src):
    done = _apply(bdir, src, _finding(CONTROL, "potentiostatic", 9, strength="inferred"))  # "planned for the next beamtime"
    assert done["applied"]
    assert _env_q(M.load(bdir)) is None


def test_a_quote_naming_one_sample_corroborates_only_that_samples_runs(bdir, src):
    done = _apply(bdir, src, _finding(CONTROL, "potentiostatic", 10, strength="inferred"))  # "on sample ZZ1"
    assert done["applied"]
    assert _covered(M.load(bdir)) == {"run-001", "run-002", "run-003"}  # the ZZ1 runs (file-name token ZZ1)


def test_the_quote_guards():
    assert B._quote_says_not_held(MEMO_LINES[7]) and not B._quote_says_not_held(MEMO_LINES[3])
    assert not B._quote_names_echem_control(MEMO_LINES[9])  # a plan
    assert not B._quote_names_echem_control("chronoamperometry would be used if the cell held (SYNTHETIC)")
    assert B._quote_names_echem_control(MEMO_LINES[10])
    for said in ("measured at OCV", "an open circuit hold", "the as-is pellet", "ex situ reference", "no electrolyte"):
        assert B._quote_says_not_held(f"chronoamperometry, then {said} (SYNTHETIC)"), said


@pytest.mark.parametrize("readme", [
    "# 2031-01_Quillfeather\n# PI: Bob Smith and Ada Quillfeather\n",  # several people on a PI line: asked
    "# 2031-01_Quillfeather\n# PI: Ada Quillfeather; Bo Quillfeather (synthetic)\n",  # two of the same surname too
    "# 2031-01_Quillfeather\n# PI - Bob Smith\n",                       # a dash is a label separator too
    "# 2031-01_Quillfeather\nPI \u2013 Bob Smith\n",
])
def test_more_pi_lines_that_mean_ask(tmp_path, readme):
    _, out = _import(tmp_path, readme=readme)
    assert _miss(M.load(out), GROUP, None)["value_state"] == B.STATE_MISSING


def test_a_dash_separated_pi_line_naming_the_folders_pi_gives_the_full_name(tmp_path):
    _, out = _import(tmp_path, readme="# 2031-01_Quillfeather\n# PI \u2014 Ada Quillfeather\n")
    assert _miss(M.load(out), GROUP, None)["fill"] == {"rule_id": B.FILL_GROUP_RULE_ID, "value": "Ada Quillfeather group"}


@pytest.mark.parametrize("line", ["2031-01_Quillfeather ", "  2031-01_Quillfeather", "#2031-01_Quillfeather",
                                  "# 2031-01_Quillfeather  "])
def test_the_month_header_with_or_without_a_hash_agrees(tmp_path, line):
    """Round 4 (the coordinator's replay): a readme's first line ``2031-01_Quillfeather `` (no '#') is the header."""
    _, out = _import(tmp_path, readme=f"{line}\nZz\n")
    b = M.load(out)
    assert [h["literal"] for h in b["experiment"]["beamtime_header_lines"]] == [line.strip()]
    assert _miss(b, GROUP, None)["fill"] == {"rule_id": B.FILL_GROUP_RULE_ID, "value": "Quillfeather group"}


def test_a_month_token_inside_other_text_is_no_header(tmp_path):
    _, out = _import(tmp_path, readme="2031-01_Quillfeather beamtime notes\nZz\n")
    b = M.load(out)
    assert b["experiment"]["beamtime_header_lines"] == []
    assert _miss(b, GROUP, None)["value_state"] == B.STATE_MISSING  # the folder alone


# --- round 5 ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("line", [11, 12, 13])
def test_a_quote_about_all_samples_or_an_ocv_step_before_the_hold_corroborates_every_run(bdir, src, line):
    """Round 5: "samples were …" / "samples held …" name no sample (the code is case-sensitive); an OCV step tied to the
    chronoamperometry that follows it is no open-circuit measurement."""
    done = _apply(bdir, src, _finding(CONTROL, "potentiostatic", line, strength="inferred"))
    assert done["applied"] and done["quote_check"]["failed"] == 0
    assert _covered(M.load(bdir)) == set(RUNS)


@pytest.mark.parametrize("quote,corroborates", [
    ("SYNTHETIC: chronoamperometry on 3 May 2031", True),            # a date, not "may"
    ("SYNTHETIC: chronoamperometry from May 3 onwards", True),
    ("SYNTHETIC: we may use chronoamperometry", False),
    ("SYNTHETIC: the next scan ran under chronoamperometry", True),  # "next" alone is no plan
    ("SYNTHETIC: chronoamperometry next time", False),
    ("SYNTHETIC: if the potential drifted it was reset, then chronoamperometry continued", True),
    ("SYNTHETIC: chronoamperometry only if the cell held", False),   # the control's own clause is conditional
    ("SYNTHETIC: If the cell held we ran chronoamperometry", False),
    ("SYNTHETIC: chronoamperometry after OCV", True),
    ("SYNTHETIC: chronoamperometry, then measured at OCV", False),   # the OCV step came after: still blocked
    ("SYNTHETIC: chronoamperometry at 1.4 V. ZZ1 measured at OCV.", False),  # OCV elsewhere in the quote: blocked
    ("SYNTHETIC: dry N2 purge, then chronoamperometry", True),       # a purge, not a dry sample
    ("SYNTHETIC: dry box transfer, then chronoamperometry", True),
    ("SYNTHETIC: ZZ1 was dry; chronoamperometry for ZZ2", False),     # dry stays a whole-quote blocker
    ("SYNTHETIC: chronoamperometry, the as-is pellet", False),
])
def test_the_round_5_quote_guards(quote, corroborates):
    said = B._quote_names_echem_control(quote) and not B._quote_says_not_held(quote)
    assert said is corroborates, quote


@pytest.mark.parametrize("readme,value", [
    ("# 2031-01_Quillfeather\n# PI: Ada Quillfeather, University of Synthshire\n", "Ada Quillfeather group"),
    ("# 2031-01_Quillfeather\n# PI-Ada Quillfeather\n", "Ada Quillfeather group"),          # an unspaced dash label
    ("2031-01_Quillfeather_ZzTestCat\nZz\n", "Quillfeather group"),                        # month, PI and project
    ("# 2031-01_Quillfeather_ZzTestCat\nZz\n", "Quillfeather group"),
])
def test_the_round_5_readme_forms_that_fill(tmp_path, readme, value):
    _, out = _import(tmp_path, readme=readme)
    assert _miss(M.load(out), GROUP, None)["fill"] == {"rule_id": B.FILL_GROUP_RULE_ID, "value": value}


@pytest.mark.parametrize("readme", [
    "# 2031-01_Quillfeather\n# PI: Bob Smith, Institute of Synthetics\n",  # the institution dropped: Bob Smith is the PI
    "# 2031-01_Quillfeather\n# PI-Bob Smith\n",
    "# 2031-01_Quillfeather\nPI-Bob Smith\n",  # kept by the import without a '#' too
    "2031-01_Quillfeather_OtherCat\nZz\n",  # another project: no second source (the folder alone)
])
def test_the_round_5_readme_forms_that_do_not(tmp_path, readme):
    _, out = _import(tmp_path, readme=readme)
    assert _miss(M.load(out), GROUP, None)["value_state"] == B.STATE_MISSING


# --- round 6 ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("quote", [
    "SYNTHETIC: OCV then chronoamperometry for ZZ9, ZZ1 at OCV only",
    "SYNTHETIC: ZZ1 held at OCV, then chronoamperometry on ZZ2",
    "SYNTHETIC: chronoamperometry on ZZ2 after OCV; ZZ1 was kept in the dry box",
    "SYNTHETIC: ZZ1 was kept in the dry box, then chronoamperometry on ZZ2",
])
def test_a_quote_naming_a_sample_outside_the_control_clause_corroborates_nothing(answered, quote):
    """Round 6: the samples are read from the control's own clause; another sample named anywhere else in the quote
    means several samples in several states, so nothing is corroborated (my choice: nothing, never ZZ2 alone)."""
    ctx = B.fill_context(answered)
    assert B._quote_corroboration({"quote": quote, "proposed_value": "potentiostatic"}, CONTROL, ctx) == (False, None)


def test_a_quote_naming_one_sample_only_in_the_control_clause_corroborates_its_runs(answered):
    """The positive control: an OCV step before the hold, and ZZ2 named only in the control's clause."""
    ctx = B.fill_context(answered)
    ok, runs = B._quote_corroboration({"quote": "SYNTHETIC: OCV for 5 min, then chronoamperometry on ZZ2",
                                       "proposed_value": "potentiostatic"}, CONTROL, ctx)
    assert ok and runs == {"run-004", "run-005", "run-006"}


@pytest.mark.parametrize("quote", ["Note: if it held, chronoamperometry ran (SYNTHETIC)",
                                   "3 May: if it held, chronoamperometry ran (SYNTHETIC)",
                                   "SYNTHETIC: if it held, chronoamperometry ran"])
def test_a_leading_if_after_a_prefix_is_a_condition(quote):
    assert not B._quote_names_echem_control(quote)
