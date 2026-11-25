"""Bundle format 1.18.0: fill first, review at the end (DEC-96, the project owner's decision of 2026-11-25,
``docs/fill-first-design-2026-11-25.md``). SYNTHETIC data only: the committed multi-operator corpus (unmistakably fake:
year 2100, samples ZZ1..ZZ3), imported under a fake folder name, plus in-memory edits of that bundle.

* ``filled`` is a value state (never an extracted state), derived by a registered fill rule and re-derived by the
  validator, which refuses a stored ``filled`` no rule gives;
* ``isaac.fill.parser_exact.v1`` fills an undecided, undisputed parser value, with every exclusion the review named;
  ``isaac.fill.domain_from_acquisition.v1`` fills ``system.domain`` from acquisition-only runs;
* a scientist decision always wins; an agreeing AI reading does not block a fill, a disagreeing one does;
* a filled value is eligible, composed as ``inferred`` with a derivation entry naming its rule (the draft validator and
  ``isaac export`` accept it, and the sidecar names the rule), and only when every measured run of the group has it;
* a filled value is not asked, but stays addressable: ``decide --question``, a workbook row and a question-site card
  record a correction; answer memory never learns a fill;
* a 1.17.0 bundle is STALE, not INVALID, and its next write logs every filled value in ``eligibility_rederived``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path

import openpyxl
import pytest

from isaac_api.local_import import answer_memory as AM
from isaac_api.local_import import bundle as B
from isaac_api.local_import import cli
from isaac_api.local_import import mutations as M
from isaac_api.local_import import questions as Q
from isaac_api.local_import import records as R

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tests_support_records import REPO_ROOT, SEMANTICS, fake_upstream_env  # noqa: E402,F401

FOLDER = "SYN_BL00_2100-01_FillFirst"
BY = dict(by="SYN Scientist", orcid=None)
START = "timestamps.acquired_start_utc"
DOMAIN = "system.domain"


@pytest.fixture(scope="module", autouse=True)
def _vendored_schema_basis(tmp_path_factory):
    """No portal validator installed (as in CI), so the question set does not depend on the machine."""
    d = tmp_path_factory.mktemp("no-validator")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("ISAAC_PORTAL_VALIDATOR_DIR", str(d))
        mp.setenv("ISAAC_PORTAL_VALIDATOR_PYTHON", str(d / "python"))
        yield


@pytest.fixture(scope="module")
def pristine(tmp_path_factory):
    root = tmp_path_factory.mktemp("fill")
    src = root / FOLDER
    shutil.copytree(SEMANTICS, src)
    out = root / "bundle"
    assert cli.main(["import", str(src), "--out", str(out)]) == 0
    return out


@pytest.fixture()
def bdir(pristine, tmp_path):
    target = tmp_path / "bundle"
    shutil.copytree(pristine, target)
    return target


def _start(b, run_id="run-001"):
    """The run's #E epoch start time (the SPEC reader's UTC instant): the start candidate that has a value."""
    return next(c for c in b["candidates"] if c["target_field_path"] == START and c["run_id"] == run_id
                and c["value"] is not None)


def _local_start(b, run_id="run-001"):
    """The run's #D local start time (no value until a zone is stated): the open reading beside #E."""
    return next(c for c in b["candidates"] if c["target_field_path"] == START and c["run_id"] == run_id
                and c["value"] is None)


def _unblocked(b):
    """IN MEMORY: every #D reading taken off the start-time field, so each #E epoch is the run's ONLY reading of it
    (the shape a beamtime without #D lines has) — the base the exclusion tests edit."""
    b = copy.deepcopy(b)
    for c in b["candidates"]:
        if c["target_field_path"] == START and c["value"] is None:
            c["target_field_path"] = None
    return B.apply_derivations(b)


def _reject_local_starts(bdir: Path, *run_ids: str) -> None:
    """A scientist rejects each run's #D reading (it witnesses nothing then): the #E epoch is filled."""
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_local_start(b, r)["candidate_id"] for r in run_ids], decision="reject", value=None, **BY)


def _domain(b):
    return next(m for m in b["missing_values"] if m["target_field_path"] == DOMAIN and m["run_id"] is None)


def _derived(b):
    return B.apply_derivations(json.loads(json.dumps(b)))


def _by_id(b, cid):
    return next(c for c in b["candidates"] if c["candidate_id"] == cid)


# --- the state, the rules ---------------------------------------------------------------------------------------------


def test_filled_is_a_value_state_and_never_a_parser_state():
    assert B.STATE_FILLED == "filled" and B.STATE_FILLED in B.VALUE_STATES
    assert B.STATE_FILLED not in B.PARSER_STATES
    schema = B.bundle_schema()
    assert "filled" in schema["$defs"]["value_state"]["enum"]
    assert "filled" not in schema["$defs"]["extracted_state"]["enum"]
    assert set(schema["$defs"]["fill"]["properties"]["rule_id"]["enum"]) == set(B.FILL_RULES)
    assert set(B.FILL_RULES) == {B.FILL_PARSER_EXACT_RULE_ID, B.FILL_STORED_CONVENTION_RULE_ID, B.FILL_DOMAIN_RULE_ID}
    assert B.FORMAT_VERSION == "1.18.0" == B._VERSION_ORDER[-1]
    for rule_id, text in B.FILL_RULES.items():
        assert text.startswith(rule_id + ": ") and text.count(". ") == 0, rule_id  # one sentence, named by its id
    with pytest.raises(ValueError):
        B.derive_value_state(B.STATE_FILLED, decision=None, interpreted=False)
    with pytest.raises(ValueError):
        B.derive_value_state(B.STATE_CANDIDATE_EXTRACTED, decision=None, interpreted=False, fill_rule="isaac.fill.made_up")


def test_an_epoch_start_beside_an_open_local_start_is_not_filled_until_the_local_reading_is_settled(bdir):
    """REVIEW CRITICAL 1(a): every SPEC run holds an #E epoch start AND an #D local start (no value until a zone is
    stated, and asked). One open reading of the same field for the same run means no fill: before, the #E was filled
    and a scientist's answer to the #D question then disagreed with it, and the start time dropped out of the record."""
    b = M.load(bdir)
    assert B.validate_bundle(b) == [] and b["format_version"] == "1.18.0" and b["fill_rule_set"] == B.FILL_RULE_SET
    for run in b["runs"]:
        e, d = _start(b, run["run_id"]), _local_start(b, run["run_id"])
        assert e["value_state"] != B.STATE_FILLED and "fill" not in e, run["run_id"]
        assert d["value_state"] in (B.STATE_NEEDS_REVIEW, B.STATE_CONFLICTING)
    # the #D reading rejected: the #E epoch is the run's only reading, and it is filled
    _reject_local_starts(bdir, "run-001")
    c = _start(M.load(bdir))
    assert c["value_state"] == B.STATE_FILLED and c["fill"] == {"rule_id": B.FILL_PARSER_EXACT_RULE_ID, "value": c["value"]}
    assert c["eligibility_for_official_record"]["eligible"] is True
    assert "Filled by a registered rule" in c["eligibility_for_official_record"]["reason"]
    b = M.load(bdir)
    filled = [o for o in [*b["candidates"], *b["missing_values"]] if o["value_state"] == B.STATE_FILLED]
    # counts.filled counts candidates AND missing values (here the #E start and the domain)
    assert b["counts"]["filled"] == len(filled) == 2 and b["readiness"]["eligible_value_count"] == 2


def test_the_scientists_answer_to_the_local_start_question_goes_into_the_record(bdir):
    """REVIEW CRITICAL 1, end to end: the scientist answers the #D question with a UTC start; the record carries it
    (no disagreement with the #E epoch, which was never filled beside the open #D reading)."""
    _add_group(bdir)
    _answer_the_rest(bdir)
    b = M.load(bdir)
    M.decide(bdir, target_ids=[_local_start(b)["candidate_id"]], decision="correct", value="2100-01-01T00:10:00Z", **BY)
    b = M.load(bdir)
    draft, comp = R.compose_group(b, next(g for g in b["record_groups"] if g["group_id"] == "g1"), bdir)
    assert draft["fields"][START]["value"] == "2100-01-01T00:10:00Z" and draft["fields"][START]["status"] == "verified"
    assert not [x for x in comp["disagreements"] if x["path"] == START]


def test_a_decision_beats_a_fill_in_the_composer(bdir):
    """REVIEW CRITICAL 1(b): wherever a fill and a scientist's decision about the same field of the same run (or a
    beamtime-wide decision) both reach a group, the fill is dropped BEFORE the disagreement check."""
    _add_group(bdir)
    d_id = _local_start(M.load(bdir))["candidate_id"]
    b = _unblocked(M.load(bdir))
    e = _start(b)
    assert e["value_state"] == B.STATE_FILLED
    # beside it, the SAME run's other start reading confirmed by a scientist with another instant (in memory: the
    # stored states stand as a write would leave the #D's, and the #E keeps its fill)
    d = _by_id(b, d_id)
    d.update(target_field_path=START, value_state=B.STATE_SCIENTIST_CONFIRMED,
             eligibility_for_official_record={"eligible": True, "reason": "confirmed (synthetic)"})
    b["scientist_decisions"].append({"decision_id": "d-09999", "target": {"kind": "candidate", "id": d["candidate_id"]},
                                     "decision": "correct", "value": "2100-01-01T00:12:00Z",
                                     "decided_by": {"name": "SYN Scientist"}, "decided_utc": "2100-01-02T00:00:00Z",
                                     "method": "scientist_answer"})
    draft, comp = R.compose_group(b, next(g for g in b["record_groups"] if g["group_id"] == "g1"), bdir)
    assert draft["fields"][START] ["value"] == "2100-01-01T00:12:00Z" and draft["fields"][START]["status"] == "verified"
    assert any(n.get("candidate_id") == e["candidate_id"] and n["reason"] == R.FILL_BEATEN_BY_DECISION
               for n in comp["not_composed"])
    assert not comp["disagreements"]


def test_domain_from_acquisition_fills_system_domain_beside_a_reference_and_an_alignment_run(pristine, monkeypatch):
    b = json.loads((pristine / "bundle.json").read_text())
    m = _domain(b)
    assert m["value_state"] == B.STATE_FILLED and m["value"] is None
    assert m["fill"] == {"rule_id": B.FILL_DOMAIN_RULE_ID, "value": "experimental"}
    assert m["eligibility_for_official_record"]["eligible"] is True
    # REVIEW 5 (a real BL15-2 beamtime: pellet references and an alignment scan beside the samples, every one read by
    # the SPEC reader): the rule rests on the READER, so a reference and an alignment run are beamline measurements too
    mixed = copy.deepcopy(b)
    mixed["runs"][1]["source_type"], mixed["runs"][2]["source_type"] = "standard_or_reference", "alignment"
    assert {B.run_reader_id(mixed, r) for r in mixed["runs"]} == {"bl15_spec_acquisition_v1"}
    assert _domain(_derived(mixed))["value_state"] == B.STATE_FILLED
    # a headerless two-column run (a measurement or a computed spectrum, the file does not say): no fill
    two = copy.deepcopy(b)
    two["runs"][0]["reader"] = {"reader_id": "two_column_reader_v1"}
    assert _domain(_derived(two))["value_state"] == B.STATE_MISSING and "fill" not in _domain(_derived(two))
    # a source classified as a calculation's output: no fill
    monkeypatch.setattr(B, "CALCULATION_OUTPUT_SOURCE_TYPES", frozenset({"scan_export"}))
    assert _domain(_derived(b))["value_state"] == B.STATE_MISSING


def test_the_instrument_configuration_technique_rule_counts_as_parser_exact(pristine):
    """1.14.0's isaac.suggest.technique_from_configuration.v1 is THIS build's rule about these files (valued only when
    every run agrees), not a convention another beamtime resolved: it is filled. A valueless one is not."""
    b = json.loads((pristine / "bundle.json").read_text())
    orig = next(c for c in b["candidates"] if c["target_field_path"] == "system.technique")
    c = copy.deepcopy(orig)
    for other in b["candidates"]:
        if other["target_field_path"] == "system.technique":
            other["target_field_path"] = None  # as the rule leaves the macro-name readings: evidence, no technique
    c.update(candidate_id="cand-9999", statement_key="technique_from_configuration", run_id=None, value="HERFD-XAS",
             extracted_state=B.STATE_NEEDS_REVIEW,
             rule="isaac.suggest.technique_from_configuration.v1: suggested from the instrument (synthetic)")
    c["state_basis"].update(review_status="needs_review", proposable=False, unresolved_reason=None,
                            resolved_by_rule=None, not_proposable_reason="Suggested from the instrument configuration.")
    for e in c["evidence"]:
        e["relation"] = "supports"
        e["normalization"] = [{"step": "derive", "rule_id": "isaac.suggest.technique_from_configuration.v1",
                               "from": "9000", "to": "HERFD-XAS", "unit": None}]
    b["candidates"].append(c)
    got = _by_id(_derived(b), "cand-9999")
    assert got["value_state"] == B.STATE_FILLED and got["fill"]["rule_id"] == B.FILL_PARSER_EXACT_RULE_ID
    c["value"] = None  # the runs disagree: the rule offers no value
    assert _by_id(_derived(b), "cand-9999")["value_state"] == B.STATE_NEEDS_REVIEW


# --- every exclusion of parser_exact blocks a fill ------------------------------------------------------------------


def _excluded(b, edit) -> dict:
    """``edit`` applied to a copy of run-001's filled #E start (in the #D-free shape); the candidate as derived."""
    b = _unblocked(b)
    c = _start(b)
    assert c["value_state"] == B.STATE_FILLED  # the positive control: unedited, it is filled
    edit(b, c)
    return _by_id(_derived(b), c["candidate_id"])


def _set_path(c, path, value):
    c["target_field_path"], c["value"] = path, value


def _another_reading(b, c, **change):
    b["candidates"].append({**copy.deepcopy(c), "candidate_id": "cand-9997", **change})


@pytest.mark.parametrize("name, edit", [
    ("a convention resolved on another beamtime",
     lambda b, c: c["state_basis"].update(review_status="resolved", resolved_by_rule="bl15.convention.synthetic.v1")),
    ("a standing resolution", lambda b, c: c.update(standing_resolution={"rule": "synthetic"})),
    ("an inferred value (determinism inferred)", lambda b, c: c["state_basis"].update(determinism="inferred")),
    ("a value an engine rule derived",
     lambda b, c: c["evidence"][0]["normalization"].append(
         {"step": "derive", "rule_id": "bl15.notes.environment_statement.v1", "from": "x", "to": c["value"], "unit": None})),
    ("a contradicting witness",
     lambda b, c: c["evidence"].append({**c["evidence"][0], "evidence_id": c["evidence"][0]["evidence_id"] + "x",
                                        "relation": "contradicts", "literal_value": "SYN other"})),
    ("a passing-mention note", lambda b, c: c["state_basis"].update(not_proposable_reason=B.PASSING_MENTION_REASON)),
    ("a local clock time",
     lambda b, c: c["evidence"][0]["normalization"].append(
         {"step": B.LOCAL_CLOCK_READ_STEP, "rule_id": B.XDC_START_RULE_ID, "from": "x", "to": "y", "unit": None})),
    ("the potential scale", lambda b, c: _set_path(c, "context.electrochemistry.potential_scale",
                                                   B.allowed_values("context.electrochemistry.potential_scale")[0])),
    ("the control mode", lambda b, c: _set_path(c, B.CONTROL_MODE_PATH, B.allowed_values(B.CONTROL_MODE_PATH)[0])),
    ("a beamtime fact on a run-level field (DEC-69)",
     lambda b, c: (_set_path(c, "context.environment", B.allowed_values("context.environment")[0]),
                   c.update(run_id=None))),
    ("a conflict that names it", lambda b, c: b["conflicts"][0].update(candidate_id=c["candidate_id"])),
    ("a conflicting reading of the same run and field",
     lambda b, c: _another_reading(b, c, extracted_state=B.STATE_CONFLICTING, value=None)),
    ("an open reading of the same run and field (no value: the #D shape)",
     lambda b, c: _another_reading(b, c, extracted_state=B.STATE_NEEDS_REVIEW, value=None)),
    ("a differing reading of the same run and field",
     lambda b, c: _another_reading(b, c, value="2100-01-01T05:00:00+00:00")),
    ("a differing BEAMTIME reading of the same field",
     lambda b, c: _another_reading(b, c, run_id=None, value="2100-01-01T05:00:00+00:00")),
    ("a value its field refuses", lambda b, c: c.update(value="not an instant")),
])
def test_each_parser_exact_exclusion_blocks_the_fill(pristine, name, edit):
    b = json.loads((pristine / "bundle.json").read_text())
    got = _excluded(b, edit)
    assert got["value_state"] != B.STATE_FILLED and "fill" not in got, name
    assert got["eligibility_for_official_record"]["eligible"] is False, name


def test_an_agreeing_reading_and_a_rejected_one_do_not_block_the_fill(pristine):
    b = json.loads((pristine / "bundle.json").read_text())
    assert _excluded(b, lambda b, c: _another_reading(b, c))["value_state"] == B.STATE_FILLED  # the same instant

    def rejected(b, c):
        _another_reading(b, c, value=None)
        b["scientist_decisions"].append({"decision_id": "d-09998", "target": {"kind": "candidate", "id": "cand-9997"},
                                         "decision": "reject", "value": None, "decided_by": {"name": "SYN Scientist"}})
    assert _excluded(b, rejected)["value_state"] == B.STATE_FILLED


# --- file-name readings: only a POSITION-read number waits for the naming -------------------------------------------


def _read_by_position(b, c):
    """The witness as the file-name reader gives a bare number: its ORDINAL rule (the only position-based reading)."""
    for e in c["evidence"]:
        e["locator"], e["method_id"] = "filename token 1 [chars 3..5]", "bl15_filename_tokens_v1"
        e["normalization"] = [{"step": "normalize", "rule_id": "bl15.filenames.bare_integer_ordinal.v1",
                               "from": "01", "to": 1, "unit": None}]


def _read_by_shape(b, c):
    """The witness as the file-name reader gives a word or a unit-bearing token (e.g. `100mV`): by its own shape."""
    for e in c["evidence"]:
        e["locator"], e["method_id"] = "filename token 6 [chars 40..45]", "bl15_filename_tokens_v1"
        e["normalization"] = [{"step": "normalize", "rule_id": "bl15.filenames.millivolt_to_volt.v1",
                               "from": "100mV", "to": 0.1, "unit": "V"}]


def test_only_the_ordinal_reading_depends_on_token_positions():
    """REVIEW 3, the evidence: the file-name reader recognises every token by its shape or word wherever it sits
    (`dry`, `NoElectrolyte`, `100mV`), and its ONE ordering rule is the bare-integer ordinal (first bare number the
    legacy number, the second the sample/electrode number). Only that reading can be changed by a misread counter."""
    from isaac_api.bl15 import filenames as F

    assert "WHY NOT POSITIONAL" in F.__doc__
    assert F.RULE_BARE_INTEGER_ORDINAL.startswith("bl15.filenames.bare_integer_ordinal.v1: THE ONLY ORDERING RULE")
    assert B.POSITION_DEPENDENT_NAME_RULES == frozenset({"bl15.filenames.bare_integer_ordinal.v1"})


def test_a_position_read_number_is_filled_only_once_the_naming_is_settled_and_never_back(pristine):
    b = json.loads((pristine / "bundle.json").read_text())
    assert "grouping_questions" not in b and B.naming_check(b) == "not_grouped"
    # AT IMPORT (no grouping yet): a number read by its position waits; a word or a unit-bearing token does not
    assert _excluded(b, _read_by_position)["value_state"] == B.STATE_CANDIDATE_EXTRACTED
    assert _excluded(b, _read_by_shape)["value_state"] == B.STATE_FILLED
    # the grouping step ran and found no counter ambiguity (stored, readable): the number is filled
    grouped = {**copy.deepcopy(b), "grouping_questions": []}
    assert B.naming_check(grouped) == "grouped_no_counter_question"
    assert _excluded(grouped, _read_by_position)["value_state"] == B.STATE_FILLED
    # ...or it asks the counter question: still waiting
    asked = {**copy.deepcopy(b), "grouping_questions": [{"kind": "naming_counter_positions", "positions": [2],
                                                         "id": "syn", "text": "SYN?"}]}
    assert B.naming_check(asked) == "counter_question_open"
    assert _excluded(asked, _read_by_position)["value_state"] == B.STATE_CANDIDATE_EXTRACTED
    assert _excluded(asked, _read_by_shape)["value_state"] == B.STATE_FILLED  # never position-read
    # a scientist rules on the position (a counter, or not one): filled. The order through the workflow is
    # import (waits) -> group (filled, or waits for the question) -> answer (filled): blocked -> filled only.
    for decision, key in (("set_counter_positions", "positions"), (B.NOT_COUNTER_DECISION, "not_counter_positions")):
        x = copy.deepcopy(asked)
        x["scientist_decisions"] = [{"decision_id": "d-00001", "target": {"kind": "experiment", "id": "experiment"},
                                     "decision": decision, key: [2], "decided_by": {"name": "SYN Scientist"}}]
        assert B.naming_check(x) == "decided", decision
        assert _excluded(x, _read_by_position)["value_state"] == B.STATE_FILLED, decision


def test_the_grouping_step_records_a_readable_naming_outcome(bdir):
    from isaac_api.local_import import status as ST

    assert ST.status(bdir)["facts"]["naming"] == "not_grouped"
    M.group(bdir)
    assert M.load(bdir)["grouping_questions"] == [] and ST.status(bdir)["facts"]["naming"] == "grouped_no_counter_question"


# --- a stored convention: DEC-70's dry sample -> ex_situ --------------------------------------------------------------


def _dry_candidate(b, rule="bl15.environment.dry_sample_is_ex_situ.v1"):
    """IN MEMORY, the candidate DEC-70's rule gives a run whose own name says `dry` (the engine's shape: determinism
    inferred, its value derived by the rule from the dry token)."""
    base = copy.deepcopy(next(c for c in b["candidates"] if c["run_id"] == "run-001" and c["target_field_path"]))
    base.update(candidate_id="cand-9990", target_field_path="context.environment", value="ex_situ",
                statement_key="dry_state", extracted_state=B.STATE_CANDIDATE_EXTRACTED, standing_resolution=None,
                rule=f"{rule}: a dry sample is measured ex situ (synthetic)")
    base["state_basis"].update(review_status="ready", proposable=True, determinism="inferred", unresolved_reason=None,
                               not_proposable_reason=None, resolved_by_rule=None)
    base["evidence"] = [{**base["evidence"][0], "locator": "filename token 3 [chars 9..12]", "literal_value": "dry",
                         "method_id": "bl15_filename_tokens_v1", "relation": "supports",
                         "normalization": [{"step": "derive", "rule_id": rule, "from": "dry", "to": "ex_situ",
                                            "unit": None}]}]
    b["candidates"].append(base)
    return base


def test_the_dry_sample_convention_is_filled_under_its_own_rule_never_as_parser_exact(bdir):
    b = M.load(bdir)
    _dry_candidate(b)
    got = _by_id(_derived(b), "cand-9990")
    assert got["value_state"] == B.STATE_FILLED and got["fill"]["rule_id"] == B.FILL_STORED_CONVENTION_RULE_ID
    assert B.parser_exact_applies(b, got, B.fill_context(b)) is False  # inferred and derived: not a reading
    # composed: the derivation names BOTH the fill rule and the convention
    _add_group(bdir)
    b = M.load(bdir)
    _dry_candidate(b)
    b = _derived(b)
    draft, _ = R.compose_group(b, next(g for g in b["record_groups"] if g["group_id"] == "g1"), bdir)
    env = draft["fields"]["context.environment"]
    [d] = [e for e in env["evidence"] if e["source_type"] == "derivation"]
    assert env["status"] == "inferred" and env["value"] == "ex_situ"
    assert d["rule"] == B.FILL_STORED_CONVENTION_RULE_ID and d["convention_rule"] == "bl15.environment.dry_sample_is_ex_situ.v1"


def _lexicon_candidate(b, *, derive_rule="bl15.notes.cell_type_statement.v1"):
    """IN MEMORY, the candidate DEC-71's logbook lexicon gives a run whose own sample section says "Flow cell =
    10 ml/min": the reader's normalize step (the sentence's reading) and then its derive step mapping the term to the
    schema member, under ONE rule id (the shape the real BL15-2 replay showed)."""
    rule = "bl15.notes.cell_type_statement.v1"
    base = copy.deepcopy(next(c for c in b["candidates"] if c["run_id"] == "run-001" and c["target_field_path"]))
    base.update(candidate_id="cand-9991", target_field_path="context.electrochemistry.cell_type", value="flow_cell",
                statement_key="cell_type_statement", extracted_state=B.STATE_CANDIDATE_EXTRACTED,
                standing_resolution=None, rule=f"{rule}: the logbook names the cell (synthetic)")
    base["state_basis"].update(review_status="ready", proposable=True, determinism="deterministic",
                               unresolved_reason=None, not_proposable_reason=None, resolved_by_rule=None)
    reading = {"term": "Flow cell", "member": "flow_cell", "section": "Sample 1", "file_numbers": [1],
               "named_samples": [], "status": "member"}
    base["evidence"] = [{**base["evidence"][0], "locator": "line 12", "literal_value": "Flow cell = 99 ml/min",
                         "method_id": "bl15_beamtime_notes_v1", "relation": "supports",
                         "normalization": [{"step": "normalize", "rule_id": rule, "from": "Flow cell = 99 ml/min",
                                            "to": reading, "unit": None},
                                           {"step": "derive", "rule_id": derive_rule, "from": reading,
                                            "to": "flow_cell", "unit": None}]}]
    b["candidates"].append(base)
    return base


def test_a_logbook_term_the_reader_maps_to_its_member_is_a_reading_and_is_filled(bdir):
    """ROUND 3 REGRESSION 2 (a real BL15-2 replay: 15 runs reading a logbook flow-cell statement lost their fill): a derive
    step under the SAME rule as the witness's own reading (the lexicon mapping its term to the vocabulary, identified
    by its rule id, bundle._logbook_rule_ids) is reading, not inference: filled under parser_exact."""
    b = M.load(bdir)
    _lexicon_candidate(b)
    got = _by_id(_derived(b), "cand-9991")
    assert got["value_state"] == B.STATE_FILLED and got["fill"]["rule_id"] == B.FILL_PARSER_EXACT_RULE_ID
    assert B._inferred_derive_rule_ids(got) == set()


def test_a_value_another_rule_derived_is_not_a_reading(bdir):
    """...but a derive step under ANOTHER rule than the witness was read under (a DEC-70-style convention) is
    inference: parser_exact never fills it (stored_convention does, and only from its allowlist)."""
    b = M.load(bdir)
    _lexicon_candidate(b, derive_rule="bl15.environment.dry_sample_is_ex_situ.v1")
    got = _by_id(_derived(b), "cand-9991")
    assert got["value_state"] == B.STATE_CANDIDATE_EXTRACTED and "fill" not in got
    # and a lexicon derive with NO reading of its own under that rule is not the reader's mapping either
    b = M.load(bdir)
    c = _dry_candidate(b, rule="bl15.notes.environment_statement.v1")
    c["state_basis"]["determinism"] = "deterministic"
    got = _by_id(_derived(b), "cand-9990")
    assert got["value_state"] == B.STATE_CANDIDATE_EXTRACTED and "fill" not in got


# --- a decision wins; an AI reading --------------------------------------------------------------------------------


@pytest.mark.parametrize("decision, value, state", [
    ("correct", "2100-01-01T00:11:00+00:00", B.STATE_SCIENTIST_CONFIRMED),
    ("reject", None, B.STATE_REJECTED),
    ("defer", None, B.STATE_CANDIDATE_EXTRACTED),  # "I don't know" is still a decision: no fill over it
])
def test_a_decision_always_wins_over_a_fill(bdir, decision, value, state):
    _reject_local_starts(bdir, "run-001")
    cid = _start(M.load(bdir))["candidate_id"]
    assert _by_id(M.load(bdir), cid)["value_state"] == B.STATE_FILLED
    M.decide(bdir, target_ids=[cid], decision=decision, value=value, **BY)
    c = _by_id(M.load(bdir), cid)
    assert c["value_state"] == state and "fill" not in c
    if decision == "correct":
        assert c["eligibility_for_official_record"]["eligible"] is True
        assert B.final_value(c["value"], B.candidate_decision(M.load(bdir), c)) == value
    assert B.validate_bundle(M.load(bdir)) == []


def test_an_agreeing_ai_reading_keeps_the_fill_and_a_disagreeing_one_blocks_it(bdir):
    _reject_local_starts(bdir, "run-001", "run-002")
    b = M.load(bdir)
    agree, other = _start(b, "run-001"), _start(b, "run-002")
    assert agree["value_state"] == other["value_state"] == B.STATE_FILLED
    M.annotate(bdir, target_id=agree["candidate_id"], value=agree["value"], excerpt_locator=None, source_id=None,
               model_id="syn-model", blind=False, rationale="")
    M.annotate(bdir, target_id=other["candidate_id"], value="2100-06-01T00:00:00+00:00", excerpt_locator=None,
               source_id=None, model_id="syn-model", blind=False, rationale="")
    b = M.load(bdir)
    assert _by_id(b, agree["candidate_id"])["value_state"] == B.STATE_FILLED
    assert _by_id(b, other["candidate_id"])["value_state"] == B.STATE_NEEDS_REVIEW  # an AI reading alone: needs_review
    assert _by_id(b, other["candidate_id"])["eligibility_for_official_record"]["eligible"] is False
    # the domain: a reading that says computational blocks the fill of experimental
    M.annotate(bdir, target_id=_domain(b)["value_id"], value="computational", excerpt_locator=None, source_id=None,
               model_id="syn-model", blind=False, rationale="")
    assert _domain(M.load(bdir))["value_state"] == B.STATE_NEEDS_REVIEW
    assert B.validate_bundle(M.load(bdir)) == []


# --- the validator re-derives it --------------------------------------------------------------------------------------


def test_a_hand_written_filled_no_rule_gives_is_refused(pristine):
    b = json.loads((pristine / "bundle.json").read_text())
    c = next(c for c in b["candidates"] if c["value_state"] == B.STATE_NEEDS_REVIEW and c["value"] is not None)
    c["value_state"] = B.STATE_FILLED
    c["fill"] = {"rule_id": B.FILL_PARSER_EXACT_RULE_ID, "value": c["value"]}
    errors = B.validate_bundle(b)
    assert any(e.startswith(f"state: {c['candidate_id']} is filled but") for e in errors), errors
    assert any(e.startswith(f"state: {c['candidate_id']} fill ") for e in errors), errors
    # a fill block without the state: refused too; an unregistered rule id: the schema refuses it
    b2 = json.loads((pristine / "bundle.json").read_text())
    _domain(b2).pop("fill")
    assert any("fill None is not what" in e for e in B.validate_bundle(b2))
    b3 = json.loads((pristine / "bundle.json").read_text())
    _domain(b3)["fill"]["rule_id"] = "isaac.fill.made_up.v1"
    assert any("fill" in e or "rule_id" in e for e in B.validate_bundle(b3))


# --- an older bundle, or an older rule set: STALE, then logged ------------------------------------------------------


def _store_as_1_17_0(bdir: Path, monkeypatch) -> dict:
    """What a 1.17.0 build stored for the same files: the same bundle derived with no fill, labelled 1.17.0."""
    b = json.loads((bdir / "bundle.json").read_text())
    b["format_version"] = "1.17.0"
    b.pop("fill_rule_set", None)
    with monkeypatch.context() as mp:
        mp.setattr(B, "fills_apply", lambda bundle: False)
        B.apply_derivations(b)
    assert not any(o.get("fill") for o in [*b["candidates"], *b["missing_values"]]) and "filled" not in b["counts"]
    (bdir / "bundle.json").write_text(json.dumps(b))
    return b


def test_a_1_17_0_bundle_is_stale_not_invalid_and_its_next_write_logs_each_filled_value(bdir, monkeypatch, capsys):
    stored = _store_as_1_17_0(bdir, monkeypatch)
    assert B.validate_bundle(stored)  # this build derives fills its stored states do not have
    errors, stale = B.validate_allowing_stale(stored)
    assert errors == [] and stale
    moved = {(s["kind"], s["id"]) for s in stale}
    assert moved == {("missing_value", _domain(stored)["value_id"])}
    assert all(s["value_state"] == B.STATE_FILLED and s["eligible_before"] is False and s["eligible_now"] is True
               and B.FILL_DOMAIN_RULE_ID in s["reason"] for s in stale)
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(bdir)]) == 1
    out = capsys.readouterr().out
    assert out.startswith("STALE:") and "1.17.0" in out
    with pytest.raises(R.RecordsRefused, match="STALE"):
        R.load_validated(bdir)
    # the next write (any: here the consent) re-derives it, raises it to 1.18.0 and logs every moved value
    M.record_consent(bdir, by="SYN Scientist")
    saved = json.loads((bdir / "bundle.json").read_text())
    assert saved["format_version"] == "1.18.0" and saved["fill_rule_set"] == B.FILL_RULE_SET
    assert B.validate_bundle(saved) == []
    logged = {(r["kind"], r["id"]) for r in saved["eligibility_rederived"] if r["value_state"] == B.STATE_FILLED}
    assert logged == moved
    assert all(r["from_format_version"] == "1.17.0" and r["to_format_version"] == "1.18.0"
               for r in saved["eligibility_rederived"] if r["value_state"] == B.STATE_FILLED)
    [u] = [u for u in saved["format_upgrades"] if u["from_format_version"] == "1.17.0"]
    assert B.CHANGES_ADDED_IN["1.18.0"] in u["statement"]
    assert saved["counts"]["filled"] == len(moved)


def test_a_bundle_an_earlier_fill_rule_set_wrote_is_stale_and_re_derived_on_save(bdir, monkeypatch, capsys):
    """REVIEW 9: adding or changing a fill rule later (slice 2) must leave a stored 1.18.0 bundle STALE, never
    INVALID. Simulated: the bundle as a rule set WITHOUT the domain rule wrote it (fill_rule_set one lower)."""
    b = json.loads((bdir / "bundle.json").read_text())
    with monkeypatch.context() as mp:
        mp.setattr(B, "ACQUISITION_READER_IDS", frozenset())
        B.apply_derivations(b)
    b["fill_rule_set"] = B.FILL_RULE_SET - 1
    assert _domain(b)["value_state"] == B.STATE_MISSING
    (bdir / "bundle.json").write_text(json.dumps(b))
    assert B.fill_rule_set_stale(b) and B.validate_bundle(b)
    errors, stale = B.validate_allowing_stale(b)
    assert errors == [] and [(s["id"], s["value_state"]) for s in stale] == [(_domain(b)["value_id"], B.STATE_FILLED)]
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(bdir)]) == 1 and capsys.readouterr().out.startswith("STALE:")
    M.record_consent(bdir, by="SYN Scientist")
    saved = json.loads((bdir / "bundle.json").read_text())
    assert saved["fill_rule_set"] == B.FILL_RULE_SET and B.validate_bundle(saved) == [] and not B.fill_rule_set_stale(saved)
    assert [r["id"] for r in saved.get("eligibility_rederived") or ()] == [_domain(b)["value_id"]]
    assert _domain(saved)["value_state"] == B.STATE_FILLED
    # the same stored states under THIS rule set are a tamper: INVALID
    b["fill_rule_set"] = B.FILL_RULE_SET
    assert B.validate_allowing_stale(b)[0]


def test_a_bundle_too_old_to_be_raised_is_never_filled(pristine):
    b = json.loads((pristine / "bundle.json").read_text())
    b.pop("processed_outputs")
    b["format_version"] = "1.1.0"
    got = _derived(b)
    assert not any(o["value_state"] == B.STATE_FILLED for o in [*got["candidates"], *got["missing_values"]])
    assert "filled" not in got["counts"]


# --- composition, draft validation, export ---------------------------------------------------------------------------


def _add_group(bdir: Path, run_ids=("run-001",)) -> None:
    b = M.load(bdir)
    runs = [r for r in b["runs"] if r["run_id"] in run_ids]
    (bdir / "processing").mkdir(exist_ok=True)
    spec = bdir / "processing" / "g1_norm.txt"
    spec.write_text("# SYNTHETIC\n" + "\n".join(f"{1000 + 5 * i} {min(1.0, i / 10):.3f}" for i in range(21)) + "\n")
    b["record_groups"].append(
        {"group_id": "g1", "experiment_key": "exp", "member_run_keys": [r["run_key"] for r in runs],
         "basis": {"sample": "s", "technique": "t", "environment": None, "conditions": {}},
         "split_reasons": [], "status": "proposed", "questions": []})
    b["processing_results"].append(
        {"result_id": "p1", "group_id": "g1", "protocol_id": "isaac.xas.synthetic", "protocol_version": "0.1",
         "protocol_status": "draft_unreviewed", "source": "isaac_protocol",
         "inputs": [{"source_id": runs[0]["scans"][0]["source_id"], "scan": 1, "channel": "vortDT"}],
         "steps": [{"step": "normalize", "params": {}, "outcome": {}, "flags": []}],
         "outputs": {"files": [{"role": "normalized_spectrum", "relative_path": "processing/g1_norm.txt",
                                "sha256": hashlib.sha256(spec.read_bytes()).hexdigest()}],
                     "e0_eV": 1012.0, "edge_step": 1.0, "points": 21},
         "qc": {"metrics": {}, "verdict": "pass"}, "comparison": None, "state": "candidate_extracted"})
    M.save_bundle(bdir, b)


def _answer_the_rest(bdir: Path) -> None:
    """Every required value a fill does not supply, answered (the domain is left to its fill)."""
    b = M.load(bdir)

    def miss(path, run_id):
        return next(m["value_id"] for m in b["missing_values"] if m["target_field_path"] == path and m["run_id"] == run_id)

    def cand(path, run_id):
        return next(c["candidate_id"] for c in b["candidates"] if c["target_field_path"] == path and c["run_id"] == run_id)

    M.decide(bdir, target_ids=["g1"], decision="confirm", value=None, **BY)
    M.decide(bdir, target_ids=["p1"], decision="approve", value=None, qc_status="valid", **BY)
    M.decide(bdir, target_ids=[cand("sample.material.name", "run-001")], decision="correct", value="ZZ1 synthetic", **BY)
    M.decide(bdir, target_ids=[cand("system.technique", None)], decision="correct", value="HERFD-XAS", **BY)
    for path, value in [("attribution.produced_by.group", "SYN group"),
                        ("attribution.produced_by.organization", "SYN University")]:
        M.decide(bdir, target_ids=[miss(path, None)], decision="correct", value=value, **BY)
    for path, value in [("sample.sample_form", "powder"), ("context.environment", "ex_situ"),
                        ("context.temperature_K", 298.0)]:
        M.decide(bdir, target_ids=[miss(path, "run-001")], decision="correct", value=value, **BY)


def test_a_filled_value_composes_as_inferred_passes_the_draft_validator_and_isaac_export(bdir, fake_upstream_env,
                                                                                        tmp_path):
    from isaac_records.draft_validator import validate_draft
    from isaac_records.export import export_draft

    _add_group(bdir)
    _answer_the_rest(bdir)
    _reject_local_starts(bdir, "run-001")  # the #E epoch start is then the run's only reading: filled
    R.build_records(bdir)
    draft = json.loads((bdir / "drafts" / "g1.draft.json").read_text())
    comp = json.loads((bdir / "drafts" / "g1.composition.json").read_text())
    for path, rule in ((START, B.FILL_PARSER_EXACT_RULE_ID), (DOMAIN, B.FILL_DOMAIN_RULE_ID)):
        env = draft["fields"][path]
        assert env["status"] == "inferred", path
        [d] = [e for e in env["evidence"] if e.get("source_type") == "derivation"]
        assert d["rule"] == rule and d["rule_text"] == B.FILL_RULES[rule]
        assert any(e["source_type"] == "document" for e in env["evidence"]), path
        assert not any(e["source_type"] == "user_confirmation" for e in env["evidence"]), path
    # REVIEW 6: the domain cites a LITERAL header line its acquisition reader read (real locator, reader id), of the
    # group's own runs, and says in a note (never as a quote) what the rule rests on
    after = M.load(bdir)
    run = after["runs"][0]
    [w] = [e for e in draft["fields"][DOMAIN]["evidence"] if e["source_type"] == "document"]
    [f_line] = [e for e in after["extended_context"] if e.get("source_id") == run["acquisition_source_id"]
                and e["locator"] == "line 1 header #F"]
    assert (w["locator"], w["method_id"], w["quote"]) == ("line 1 header #F", "bl15_spec_acquisition_v1",
                                                          f_line["raw_literal"])  # the file's own #F line, verbatim
    [d] = [e for e in draft["fields"][DOMAIN]["evidence"] if e["source_type"] == "derivation"]
    assert "1 measured run" in d["note"] and "bl15_spec_acquisition_v1" in d["note"]
    assert draft["fields"][DOMAIN]["value"] == "experimental"
    assert draft["fields"][START]["value"] == "2100-01-01T00:10:00+00:00"
    assert draft["fields"]["sample.material.name"]["status"] == "verified"  # a confirmed value stays verified
    assert {f["path"] for f in comp["filled_by_rule"]} == {START, DOMAIN}
    report = validate_draft(draft)
    assert report.ok, report.errors
    assert not [w for w in report.warnings if w[0].startswith(("fields." + START, "fields." + DOMAIN))], report.warnings
    # THE TRUTH PLANE'S OWN EXPORT (`isaac export`): an official record whose sidecar names the rule
    result = export_draft(draft, REPO_ROOT)
    assert result.ok, (result.draft_report.errors, result.official_report and result.official_report.errors)
    assert result.record["system"]["domain"] == "experimental"
    text = json.dumps(result.sidecar)
    assert B.FILL_PARSER_EXACT_RULE_ID in text and B.FILL_DOMAIN_RULE_ID in text


def test_a_merged_group_whose_runs_are_not_all_filled_fills_nothing_for_that_field(bdir):
    _add_group(bdir, run_ids=("run-001", "run-002"))
    _reject_local_starts(bdir, "run-001")  # run-001's #E is filled; run-002's stays beside its open #D
    b = M.load(bdir)
    group = next(g for g in b["record_groups"] if g["group_id"] == "g1")
    draft, comp = R.compose_group(b, group, bdir)
    assert START not in draft["fields"]
    held = [n for n in comp["not_composed"] if n.get("path") == START]
    assert held and "filled by a rule for 1 of this record group's 2 measured runs only" in held[0]["reason"]
    # the beamtime-wide domain covers every run: it composes
    assert draft["fields"][DOMAIN]["status"] == "inferred"


def test_runs_of_one_group_filled_with_different_values_are_asked_and_said_by_state(bdir):
    """REVIEW 7: a merged group whose runs a rule filled with DIFFERENT values: the composer fills nothing and says
    so in words that fit (no scientist confirmed them), and a question asks those values (an optional field too)."""
    _add_group(bdir, run_ids=("run-001", "run-002"))
    _reject_local_starts(bdir, "run-001", "run-002")
    b = M.load(bdir)
    e1, e2 = _start(b, "run-001"), _start(b, "run-002")
    assert e1["value_state"] == e2["value_state"] == B.STATE_FILLED and e1["value"] != e2["value"]
    draft, comp = R.compose_group(b, next(g for g in b["record_groups"] if g["group_id"] == "g1"), bdir)
    [dis] = [x for x in comp["disagreements"] if x["path"] == START]
    assert dis["reason"].startswith("values a rule filled differ inside one record group")
    asked = Q.consolidate(b)
    assert {e1["candidate_id"], e2["candidate_id"]} <= _targets(asked)
    # the single-run fills of other groups' runs (none here) are not asked; the domain, filled for all, is not asked
    assert _domain(b)["value_id"] not in _targets(asked)


def test_a_potential_setpoint_without_a_scale_does_not_compose(bdir):
    """DEC-88's gate is kept: a set-point (here a filled one) composes only beside a confirmed or filled scale, and
    the scale is never filled by parser_exact."""
    _add_group(bdir)
    b = M.load(bdir)
    sp = next(c for c in b["candidates"] if c["target_field_path"] == R.SETPOINT_PATH and c["run_id"] == "run-001")
    sp["extracted_state"], sp["value"] = B.STATE_CANDIDATE_EXTRACTED, 0.1
    sp["state_basis"].update(review_status="ready", proposable=True, unresolved_reason=None, not_proposable_reason=None,
                             resolved_by_rule=None)
    for e in sp["evidence"]:
        e["relation"] = "supports"
    b = _derived(b)
    sp = _by_id(b, sp["candidate_id"])
    assert sp["value_state"] == B.STATE_FILLED  # `100mV` is read by its unit, not its position: no naming wait
    group = next(g for g in b["record_groups"] if g["group_id"] == "g1")
    draft, comp = R.compose_group(b, group, bdir)
    assert R.SETPOINT_PATH not in draft["fields"]
    assert any(n.get("path") == R.SETPOINT_PATH and n["reason"] == R.SETPOINT_NEEDS_SCALE for n in comp["not_composed"])
    scale = next(m for m in b["missing_values"] if m["target_field_path"] == R.SCALE_PATH and m["run_id"] == "run-001")
    assert scale["value_state"] == B.STATE_MISSING  # never filled


# --- not asked, still addressable ----------------------------------------------------------------------------------


def _targets(payload):
    return {t["id"] for q in payload["questions"] for t in q.get("targets") or ()}


def test_a_filled_value_is_not_asked_but_decide_question_records_a_correction(bdir):
    M.group(bdir)
    b = M.load(bdir)
    dom = _domain(b)["value_id"]
    assert dom not in _targets(Q.consolidate(b))  # not asked, not blocking
    answered = Q.consolidate(b, include_answered=True)
    q = next(q for q in answered["questions"] if dom in {t["id"] for t in q["targets"]})
    assert Q.filled_targets(b, Q.targets_for(answered, q["question_id"])) == [dom]
    M.decide_question(bdir, question_id=q["question_id"], decision="correct", value="computational", **BY)
    m = _domain(M.load(bdir))
    assert m["value_state"] == B.STATE_SCIENTIST_CONFIRMED and "fill" not in m
    assert B.final_value(None, B._decisions_by_target(M.load(bdir)["scientist_decisions"])[("missing_value", dom)]) == "computational"


def _unfilled_then_filled(bdir: Path, monkeypatch, make):
    """``make`` run while this build fills nothing (what an earlier export showed), then the bundle re-derived WITH
    fills: the domain is filled now, after the export asked it."""
    with monkeypatch.context() as mp:
        mp.setattr(B, "fills_apply", lambda bundle: False)
        M.save_bundle(bdir, M.load(bdir))
        assert _domain(M.load(bdir))["value_state"] == B.STATE_MISSING
        made = make()
    M.save_bundle(bdir, M.load(bdir))
    assert _domain(M.load(bdir))["value_state"] == B.STATE_FILLED
    return made


def test_a_question_site_answer_to_a_filled_value_is_recorded_not_called_no_longer_asked(bdir, monkeypatch, tmp_path):
    from isaac_api.local_import import question_site as S
    from isaac_api.local_import import question_site_import as SI

    M.group(bdir)
    site = tmp_path / "site"
    _unfilled_then_filled(bdir, monkeypatch, lambda: S.export_site(bdir, site, site_template=tmp_path / "no-template"))
    data = json.loads((site / "data" / "site-data.json").read_text())
    card = next(c for c in data["cards"] if (c["field"] or {}).get("path") == DOMAIN)
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({
        "format": SI.ANSWERS_FORMAT_ID, "format_version": "1.0.0", "bundle_id": data["bundle_id"],
        "bundle_version": data["bundle_version"], "exported_at": "2100-02-01T10:00:00Z", "log": [],
        "answers": [{"card_id": card["card_id"], "action": "value", "value": "computational", "typed": False,
                     "note": "", "by": "SYN Scientist", "at": "2100-02-01T10:00:00Z"}]}))
    rep = SI.import_answers(bdir, answers, site_data=site / "data" / "site-data.json", apply=True)
    [a] = rep["answers"]
    assert a["outcome"] == "recorded", a
    m = _domain(M.load(bdir))
    assert m["value_state"] == B.STATE_SCIENTIST_CONFIRMED


def test_a_site_card_over_a_filled_and_an_answered_target_is_not_recorded_over_the_answer(bdir):
    """REVIEW 4: a card whose question left the open list because ONE target was filled and ANOTHER was answered by a
    scientist since is not a fill correction: recording it through the question would write over the newer answer."""
    from isaac_api.local_import import question_site_import as SI

    _reject_local_starts(bdir, "run-001")
    b = M.load(bdir)
    filled_id, answered_id = _start(b)["candidate_id"], _domain(b)["value_id"]
    M.decide(bdir, target_ids=[answered_id], decision="correct", value="experimental", **BY)
    b = M.load(bdir)
    assert Q.filled_targets(b, [filled_id, answered_id]) == [filled_id]
    ctx = SI._Ctx(b, "bundle")
    fake = {"question_id": "Q-syn", "kind": "confirm_value", "targets": [{"kind": "candidate", "id": filled_id},
                                                                          {"kind": "missing_value", "id": answered_id}],
            "per_scope_targets": {}}
    ctx._answered = {"questions": [fake]}
    assert ctx.filled_cover({"question_id": "Q-syn"}) is False
    fake["targets"] = fake["targets"][:1]
    assert ctx.filled_cover({"question_id": "Q-syn"}) is True


def test_a_workbook_answer_to_a_filled_value_is_recorded(bdir, monkeypatch, tmp_path, capsys):
    M.group(bdir)
    dom = _domain(M.load(bdir))["value_id"]
    qid = _unfilled_then_filled(bdir, monkeypatch, lambda: next(
        q["question_id"] for q in Q.consolidate(M.load(bdir))["questions"]
        if dom in {t["id"] for t in q["targets"]}))
    xlsx = tmp_path / "SYN_questions.xlsx"
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("2 Missing (blocks export)")
    ws["A1"] = "SYN title line"
    header = ["Ref", "Folder", "Topic", "YOUR ANSWER", "ISAAC question ID"]
    for c, h in enumerate(header, start=1):
        ws.cell(2, c, h)
    for c, v in enumerate(["2-0001", FOLDER, "Domain (experimental or computational)", "computational", qid], start=1):
        ws.cell(3, c, v)
    wb.save(xlsx)
    capsys.readouterr()
    assert cli.main(["bundle", "answers", "import", str(bdir), str(xlsx), "--by", "SYN Scientist", "--apply"]) == 0
    capsys.readouterr()
    m = _domain(M.load(bdir))
    assert m["value_state"] == B.STATE_SCIENTIST_CONFIRMED, m


def test_answer_memory_never_learns_a_fill(bdir):
    b = M.load(bdir)
    assert any(o["value_state"] == B.STATE_FILLED for o in [*b["candidates"], *b["missing_values"]])
    assert AM.person_values(b) == [] and AM.entries_from_bundle(b) == []
    M.decide(bdir, target_ids=[next(m["value_id"] for m in b["missing_values"]
                                    if m["target_field_path"] == "system.facility.facility_name" and m["run_id"])],
             decision="correct", value="SYN Light Source", **BY)
    learned = AM.person_values(M.load(bdir))
    assert [v["field"] for v in learned] == ["system.facility.facility_name"]  # the decision only, never a fill


def test_status_and_check_count_filled_values(bdir, capsys):
    from isaac_api.local_import import status as ST

    facts = ST.status(bdir)
    assert facts["facts"]["values_filled"] == json.loads((bdir / "bundle.json").read_text())["counts"]["filled"] > 0
    assert any(line.startswith("Filled from the evidence by a rule") for line in facts["lines"])
    capsys.readouterr()
    assert cli.main(["bundle", "check", str(bdir)]) == 0
    assert "filled by a rule (candidates and missing values, not asked): 1" in capsys.readouterr().out


# --- round 3 --------------------------------------------------------------------------------------------------------


def test_a_defer_on_a_groups_answer_slot_beats_a_beamtime_wide_fill_and_the_slot_stays_asked(bdir):
    """ROUND 3 IMPORTANT 1 (the reviewer's repro): the domain is filled beamtime-wide; a scientist answers it for ONE
    group (an answer slot on its run), then defers that slot. The defer is a decision: the fill does not reach that
    run, the record leaves the domain out, and the slot is asked."""
    _add_group(bdir)
    b = M.load(bdir)
    dom = _domain(b)["value_id"]
    qid = next(q["question_id"] for q in Q.consolidate(b, include_answered=True)["questions"]
               if dom in {t["id"] for t in q["targets"]})
    M.decide_question(bdir, question_id=qid, only="group:g1", decision="correct", value="computational", **BY)
    b = M.load(bdir)
    [slot] = [m for m in b["missing_values"] if m["target_field_path"] == DOMAIN and m["run_id"] == "run-001"]
    M.decide(bdir, target_ids=[slot["value_id"]], decision="defer", value=None, **BY)
    b = M.load(bdir)
    assert _domain(b)["value_state"] == B.STATE_FILLED  # the beamtime-wide fill stands for the other groups
    draft, comp = R.compose_group(b, next(g for g in b["record_groups"] if g["group_id"] == "g1"), bdir)
    assert draft["fields"][DOMAIN] == {"value": None, "status": "missing", "evidence": []}  # left out, listed missing
    assert any(n.get("path") == DOMAIN and "decided otherwise (a defer included)" in n["reason"]
               for n in comp["not_composed"])
    assert slot["value_id"] in _targets(Q.consolidate(b))


def _scoped_technique(b):
    """IN MEMORY: the beamtime technique suggestion (HERFD-XAS) beside ONE run's own open technique reading (a
    reference pellet whose name says `transmission`: no value), and two groups: g1 = three sample runs, g2 = that run."""
    for other in b["candidates"]:
        if other["target_field_path"] == "system.technique":
            other["target_field_path"] = None
    base = next(c for c in b["candidates"] if c["run_id"] is None and c["evidence"])
    sug = copy.deepcopy(base)
    sug.update(candidate_id="cand-9980", statement_key="technique_from_configuration", run_id=None,
               target_field_path="system.technique", value="HERFD-XAS", extracted_state=B.STATE_NEEDS_REVIEW,
               standing_resolution=None,
               rule="isaac.suggest.technique_from_configuration.v1: suggested from the instrument (synthetic)")
    sug["state_basis"].update(review_status="needs_review", proposable=False, unresolved_reason=None,
                              resolved_by_rule=None, determinism="deterministic",
                              not_proposable_reason="Suggested from the instrument configuration.")
    sug["evidence"] = [{**base["evidence"][0], "relation": "supports",
                        "normalization": [{"step": "derive", "rule_id": "isaac.suggest.technique_from_configuration.v1",
                                           "from": "9000", "to": "HERFD-XAS", "unit": None}]}]
    own = copy.deepcopy(sug)
    own.update(candidate_id="cand-9981", statement_key="acquisition_method", run_id="run-004", value=None,
               rule="bl15_filename_tokens_v1: a technique word in the file name (synthetic)")
    own["evidence"] = [{**base["evidence"][0], "relation": "supports", "locator": "filename token 3 [chars 9..21]",
                        "literal_value": "transmission", "normalization": []}]
    b["candidates"] += [sug, own]
    keys = {r["run_id"]: r["run_key"] for r in b["runs"]}
    b["record_groups"] = [
        {"group_id": gid, "experiment_key": "exp", "member_run_keys": [keys[r] for r in runs], "status": "proposed",
         "basis": {"sample": "s", "technique": "t", "environment": None, "conditions": {}}, "split_reasons": [],
         "questions": []}
        for gid, runs in (("g1", ("run-001", "run-002", "run-003")), ("g2", ("run-004",)))]
    return B.apply_derivations(b)


def test_a_runs_own_dissent_blocks_a_beamtime_fill_only_for_that_runs_group(bdir):
    """ROUND 3 REGRESSION 3: one run's own open technique reading blocks the beamtime fill for that run (and so its
    group, which is asked) and NOT for the groups of the other runs, which compose it; composer, questions and status
    agree."""
    from isaac_api.local_import import status as ST

    b = _scoped_technique(M.load(bdir))
    sug = _by_id(b, "cand-9980")
    assert sug["value_state"] == B.STATE_FILLED  # a run's dissent no longer refuses the beamtime fill as a whole
    g1, g2 = (next(g for g in b["record_groups"] if g["group_id"] == x) for x in ("g1", "g2"))
    d1, _ = R.compose_group(b, g1, bdir)
    d2, c2 = R.compose_group(b, g2, bdir)
    assert d1["fields"]["system.technique"]["value"] == "HERFD-XAS" and d1["fields"]["system.technique"]["status"] == "inferred"
    assert d2["fields"]["system.technique"] == {"value": None, "status": "missing", "evidence": []}
    assert any(n.get("path") == "system.technique" and "run-004" in n["reason"] for n in c2["not_composed"])
    asked = _targets(Q.consolidate(b))
    assert "cand-9981" in asked and "cand-9980" not in asked  # the dissenting run's own reading is asked, not the fill
    assert Q.fills_asked(b) == set()  # the beamtime fill itself is asked by no question
    # status counts as filled-not-asked exactly the fills no question asks
    (bdir / "bundle.json").write_bytes(B.encode(b))
    filled = sum(1 for o in [*b["candidates"], *b["missing_values"]] if o["value_state"] == B.STATE_FILLED)
    assert ST.status(bdir)["facts"]["values_filled"] == filled - len(Q.fills_asked(b))


def test_status_leaves_out_a_fill_its_group_asks(bdir):
    """ROUND 3 MINOR 6: a fill the questions ask (its group's runs were filled with different values) is not counted
    as "filled, not asked"."""
    from isaac_api.local_import import status as ST

    _add_group(bdir, run_ids=("run-001", "run-002"))
    _reject_local_starts(bdir, "run-001", "run-002")
    b = M.load(bdir)
    asked = Q.fills_asked(b)
    assert {_start(b, "run-001")["candidate_id"], _start(b, "run-002")["candidate_id"]} <= asked
    filled = sum(1 for o in [*b["candidates"], *b["missing_values"]] if o["value_state"] == B.STATE_FILLED)
    assert ST.status(bdir)["facts"]["values_filled"] == filled - len(asked) == 1  # the domain only


def test_a_newer_fill_rule_set_is_refused_never_rewritten(bdir):
    """ROUND 3 MINOR 5: a bundle a NEWER rule set wrote is refused (as a newer format is), never taken as stale and
    rewritten by an older build."""
    b = json.loads((bdir / "bundle.json").read_text())
    b["fill_rule_set"] = B.FILL_RULE_SET + 1
    (bdir / "bundle.json").write_text(json.dumps(b))
    assert not B.fill_rule_set_stale(b)
    errors = B.validate_bundle(b)
    assert any("fill_rule_set" in e and "newer" in e for e in errors), errors
    assert B.validate_allowing_stale(b)[0]  # INVALID, not STALE
    before = (bdir / "bundle.json").read_bytes()
    with pytest.raises(M.MutationRefused, match="fill rule set"):
        M.record_consent(bdir, by="SYN Scientist")
    assert (bdir / "bundle.json").read_bytes() == before


def test_the_longest_upgrade_note_from_1_2_0_fits_the_6000_limit():
    """ROUND 3 MINOR 7: from 1.2.0, with every newly writable field, every missing import rule, and the run lists of
    1.11.0, 1.13.0 and 1.16.0 at their window of five plus "...", the statement fits the schema's bound."""
    limit = B.bundle_schema()["properties"]["format_upgrades"]["items"]["properties"]["statement"]["maxLength"]
    assert limit == 6000
    rules = [(st, rid) for _v, listed in B.IMPORT_RULES_ADDED_IN.items() for st, rid in listed]
    many = [f"run-{n:05d}" for n in range(10_000, 10_500)]
    statement = B.upgrade_statement("1.2.0", sorted(B._writable_paths()), rules, many, many[100:], many[200:])
    assert len(statement) <= limit, len(statement)


# --- round 4: a logbook line bound to its run only through a number read by position --------------------------------


CELL = "context.electrochemistry.cell_type"
_COUNTER_OPEN_AT_1 = [{"kind": "naming_counter_positions", "positions": [1], "id": "syn", "text": "SYN?"}]


@pytest.fixture()
def section_facts(tmp_path):
    """The synthetic section-facts beamtime (``test_local_import_logbook_section_facts.py``): section "Sample 4" says
    "Cell: H-cell" and lists NO file numbers, so it reaches run 09_04_YY1_film... only because that name's second bare
    integer is 04. Imported, not grouped."""
    from test_local_import_logbook_section_facts import _import

    return _import(tmp_path, group=False)


def _cell_of(b, prefix="09_04"):
    rid = next(r["run_id"] for r in b["runs"] if r["stem"].startswith(prefix))
    return next(c for c in b["candidates"] if c["run_id"] == rid and c.get("target_field_path") == CELL)


def _state_with(b, **change):
    x = copy.deepcopy(b)
    x.update(change)
    return _cell_of(B.apply_derivations(x))["value_state"]


def test_a_section_bound_only_by_the_names_sample_number_waits_for_the_naming(section_facts):
    """ROUND 4 IMPORTANT: the section's cell is filled only once the naming is settled — never at import (not grouped)
    nor while a counter question is open (here one naming position 1) — and then it is."""
    _, b = section_facts
    c = _cell_of(b)
    assert c["value"] == "h_cell" and "the number is the only link" in c["rule"]
    assert B.naming_check(b) == "not_grouped" and c["value_state"] == B.STATE_CANDIDATE_EXTRACTED and "fill" not in c
    assert _state_with(b, grouping_questions=_COUNTER_OPEN_AT_1) == B.STATE_CANDIDATE_EXTRACTED
    assert _state_with(b, grouping_questions=[]) == B.STATE_FILLED  # grouped, no counter question
    decided = [{"decision_id": "d-00001", "target": {"kind": "experiment", "id": "experiment"},
                "decision": B.NOT_COUNTER_DECISION, "not_counter_positions": [1], "decided_by": {"name": "SYN Scientist"}}]
    assert _state_with(b, grouping_questions=_COUNTER_OPEN_AT_1, scientist_decisions=decided) == B.STATE_FILLED


def test_a_section_that_lists_file_numbers_binds_by_the_legacy_number_and_is_not_position_gated(section_facts):
    """ROUND 4, the related case: a section that LISTS file numbers reaches a run through its legacy number, the
    logbook's File Number column equal to the number the name leads with. No counter decision changes which number
    that is (``runs[].legacy_number`` is read once at import, and a counter answer is read only by grouping), so it is
    not gated: filled even while a counter question naming position 1 is open."""
    out, b = section_facts
    x = copy.deepcopy(b)
    c = _cell_of(x)
    for e in c["evidence"]:
        for n in e["normalization"]:
            for side in ("to", "from"):
                if isinstance(n.get(side), dict):
                    n[side].update(file_numbers=[9], sample_number=None)
    c["rule"] = c["rule"].replace("the heading names no sample, so the number is the only link", "it lists the file")
    x["grouping_questions"] = _COUNTER_OPEN_AT_1
    assert B.naming_check(x) == "counter_question_open"
    assert _cell_of(B.apply_derivations(x))["value_state"] == B.STATE_FILLED
    # the evidence for "no counter decision changes the legacy number": decide position 1 IS a counter, regroup, and
    # every run keeps the legacy number the import read
    before = {r["run_id"]: r["legacy_number"] for r in M.load(out)["runs"]}
    M.decide(out, target_ids=["experiment"], decision="set_counter_positions", value=None, positions=[1], **BY)
    M.group(out)
    assert {r["run_id"]: r["legacy_number"] for r in M.load(out)["runs"]} == before


def test_a_beamtime_sentence_naming_samples_is_bound_by_the_name_number_too(section_facts):
    """...and a beamtime sentence naming samples ("samples 3 and 4") is mapped onto runs by the same second number
    (``named_applies``): gated the same way."""
    _, b = section_facts
    x = copy.deepcopy(b)
    c = _cell_of(x)
    for e in c["evidence"]:
        for n in e["normalization"]:
            for side in ("to", "from"):
                if isinstance(n.get(side), dict):
                    n[side].update(section=None, sample_number=None, named_samples=[4])
    assert _cell_of(B.apply_derivations(x))["value_state"] == B.STATE_CANDIDATE_EXTRACTED
    x["grouping_questions"] = []
    assert _cell_of(B.apply_derivations(x))["value_state"] == B.STATE_FILLED


def test_a_write_refused_for_a_newer_rule_set_says_why(bdir):
    """ROUND 4 MINOR 1: the refusal names the rule-set reason, as the validator does."""
    b = json.loads((bdir / "bundle.json").read_text())
    b["fill_rule_set"] = B.FILL_RULE_SET + 1
    (bdir / "bundle.json").write_text(json.dumps(b))
    with pytest.raises(M.MutationRefused) as refused:
        M.record_consent(bdir, by="SYN Scientist")
    assert f"fill rule set {B.FILL_RULE_SET + 1}, newer than this build's ({B.FILL_RULE_SET})" in str(refused.value)
